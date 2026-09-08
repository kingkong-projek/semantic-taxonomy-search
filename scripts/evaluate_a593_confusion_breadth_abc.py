#!/usr/bin/env python3
"""Compare simple A/B/C entrants on frozen source-bound confusion descriptions.

The 66 test descriptions (3 per side x 11 distinguishable pairs) were already
frozen in a593-gemma4-sniper-contrasts-v0.jsonl. They were generated from public
canonical evidence without old A593 teacher phrases or opened 17/88 queries.

A = expanded sparse BM25 over canonical source + old A593 teacher phrases.
B = fixed supervised sparse B-v0 trained on all old A593 teacher phrases.
C = independently generated source-bound task atoms, token BM25, max atom score.

All entrants rank the same 22-concept hard-confusion cohort. No tuning occurs here.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

TOKEN_RE = re.compile(r"[0-9A-Za-zÅÄÖåäöÉéÜü]+", re.UNICODE)


def tokens(value: Any) -> list[str]:
    return [m.group(0).casefold() for m in TOKEN_RE.finditer(str(value or ""))]


class BM25:
    def __init__(self, documents: dict[str, list[str]], *, k1=1.2, b=0.75):
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.lengths = {doc_id: len(ts) for doc_id, ts in documents.items()}
        self.avgdl = sum(self.lengths.values()) / max(1, len(self.lengths))
        self.tf = {doc_id: collections.Counter(ts) for doc_id, ts in documents.items()}
        df = collections.Counter()
        for ts in documents.values():
            df.update(set(ts))
        n = len(documents)
        self.idf = {term: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def score(self, query: str, doc_id: str) -> float:
        tf = self.tf[doc_id]
        dl = self.lengths[doc_id]
        value = 0.0
        for term in set(tokens(query)):
            f = tf.get(term, 0)
            if not f:
                continue
            idf = self.idf.get(term, 0.0)
            denom = f + self.k1 * (1.0 - self.b + self.b * dl / max(self.avgdl, 1e-9))
            value += idf * (f * (self.k1 + 1.0) / denom)
        return value


def load_teacher(path: Path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    out = {}
    for row in rows:
        cid = str(row.get("concept_id") or "")
        phrases = [str(x).strip() for x in row.get("phrases") or [] if str(x).strip()]
        if cid and len(phrases) == 8:
            out[cid] = phrases
    if len(out) != 593:
        raise RuntimeError(f"A593 teacher drift: {len(out)}")
    return out


def load_cases(path: Path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    pairs = [row for row in rows if (row.get("contrast") or {}).get("distinguishable") is True]
    if len(pairs) != 11:
        raise RuntimeError(f"distinguishable pair drift: {len(pairs)}")
    cases = []
    cohort = []
    mate = {}
    for pair_index, row in enumerate(pairs):
        a = str(row["a_concept_id"])
        b = str(row["b_concept_id"])
        cohort.extend([a, b])
        mate[a] = b
        mate[b] = a
        contrast = row["contrast"]
        for side, cid, label in (("a", a, row["a_label"]), ("b", b, row["b_label"])):
            descriptions = contrast[f"{side}_descriptions"]
            if len(descriptions) != 3:
                raise RuntimeError("expected exactly 3 frozen descriptions per side")
            for description_index, query in enumerate(descriptions):
                cases.append({
                    "pair_index": pair_index,
                    "side": side,
                    "concept_id": cid,
                    "mate_id": mate[cid],
                    "label": str(label),
                    "description_index": description_index,
                    "query": str(query),
                })
    cohort = sorted(set(cohort))
    if len(cohort) != 22 or len(cases) != 66:
        raise RuntimeError(f"cohort/case drift: {len(cohort)} concepts, {len(cases)} cases")
    return cohort, cases


def taxonomy_evidence(path: Path, cohort: list[str]):
    payload = json.loads(path.read_text(encoding="utf-8"))
    by_id = {str(row["concept_id"]): row for row in payload.get("rows") or []}
    if set(by_id) != set(cohort):
        raise RuntimeError("task atom cohort mismatch")
    return by_id


def rank(scores: dict[str, float], target: str, cohort: list[str]):
    target_score = scores[target]
    return 1 + sum(
        1 for cid in cohort
        if scores[cid] > target_score or (scores[cid] == target_score and cid < target)
    )


def summarize(rows):
    n = len(rows)
    return {
        "cases": n,
        "top1_count": sum(r["rank"] == 1 for r in rows),
        "top1_rate": round(sum(r["rank"] == 1 for r in rows) / n, 6),
        "hit_at_5_count": sum(r["rank"] <= 5 for r in rows),
        "hit_at_5_rate": round(sum(r["rank"] <= 5 for r in rows) / n, 6),
        "mrr": round(sum(1.0 / r["rank"] for r in rows) / n, 6),
        "pairwise_correct_count": sum(r["target_score"] > r["mate_score"] for r in rows),
        "pairwise_correct_rate": round(sum(r["target_score"] > r["mate_score"] for r in rows) / n, 6),
        "pairwise_tie_count": sum(r["target_score"] == r["mate_score"] for r in rows),
    }


def evaluate_bm25(cases, cohort, ranker, score_fn):
    rows = []
    for case in cases:
        scores = {cid: score_fn(ranker, case["query"], cid) for cid in cohort}
        rows.append({
            **case,
            "rank": rank(scores, case["concept_id"], cohort),
            "target_score": round(scores[case["concept_id"]], 9),
            "mate_score": round(scores[case["mate_id"]], 9),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--contrasts", default="research/training/v31/a593-gemma4-sniper-contrasts-v0.jsonl")
    ap.add_argument("--task-atoms", default="research/evaluation/v31/compile-time-semantic-a593-confusion-task-atoms-v0.json")
    ap.add_argument("--taxonomy", required=True, help="v31 concepts-and-common-relations JSON downloaded in workflow")
    ap.add_argument("--output", default="artifacts/a593-confusion-breadth-abc.json")
    args = ap.parse_args()

    teacher = load_teacher(Path(args.teacher))
    cohort, cases = load_cases(Path(args.contrasts))
    if any(cid not in teacher for cid in cohort):
        raise RuntimeError("confusion cohort not fully covered by A593 teacher")

    taxonomy = json.loads(Path(args.taxonomy).read_text(encoding="utf-8"))
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    a_docs = {}
    for cid in cohort:
        concept = by_id[cid]
        source = [
            str(concept.get("preferred_label") or ""),
            str(concept.get("definition") or ""),
            *[str(x) for x in (concept.get("alternative_labels") or []) if isinstance(x, str)],
            *teacher[cid],
        ]
        a_docs[cid] = tokens(" ".join(source))
    a_ranker = BM25(a_docs)
    a_rows = evaluate_bm25(cases, cohort, a_ranker, lambda r, q, cid: r.score(q, cid))

    train_texts, train_labels = [], []
    for cid, phrases in teacher.items():
        for phrase in phrases:
            train_texts.append(phrase)
            train_labels.append(cid)
    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=30000,
        sublinear_tf=True, norm="l2", dtype=np.float32, lowercase=True,
    )
    x_train = vectorizer.fit_transform(train_texts)
    clf = SGDClassifier(
        loss="hinge", penalty="l2", alpha=1e-5, max_iter=2000, tol=1e-4,
        random_state=0, n_jobs=-1, average=True,
    )
    clf.fit(x_train, train_labels)
    x_query = vectorizer.transform([case["query"] for case in cases])
    raw = clf.decision_function(x_query)
    classes = [str(x) for x in clf.classes_]
    index = {cid: i for i, cid in enumerate(classes)}
    b_rows = []
    for row_index, case in enumerate(cases):
        scores = {cid: float(raw[row_index, index[cid]]) for cid in cohort}
        b_rows.append({
            **case,
            "rank": rank(scores, case["concept_id"], cohort),
            "target_score": round(scores[case["concept_id"]], 9),
            "mate_score": round(scores[case["mate_id"]], 9),
        })

    task_payload = json.loads(Path(args.task_atoms).read_text(encoding="utf-8"))
    if task_payload.get("contrast_cues_or_descriptions_sent_to_generator") is not False:
        raise RuntimeError("task atom leakage guard missing")
    atom_docs = {}
    atom_owner = {}
    seen = set()
    for row in task_payload.get("rows") or []:
        for side in ("a", "b"):
            cid = str(row[f"{side}_concept_id"])
            atoms = row[f"{side}_atoms"]
            if cid in seen or len(atoms) != 6:
                raise RuntimeError("invalid/duplicate task atom row")
            seen.add(cid)
            for atom_index, atom in enumerate(atoms):
                atom_id = f"{cid}#{atom_index}"
                atom_docs[atom_id] = tokens(atom)
                atom_owner[atom_id] = cid
    if seen != set(cohort):
        raise RuntimeError("task atoms do not cover hard cohort")
    c_ranker = BM25(atom_docs)
    c_rows = []
    for case in cases:
        scores = {cid: 0.0 for cid in cohort}
        for atom_id, cid in atom_owner.items():
            value = c_ranker.score(case["query"], atom_id)
            if value > scores[cid]:
                scores[cid] = value
        c_rows.append({
            **case,
            "rank": rank(scores, case["concept_id"], cohort),
            "target_score": round(scores[case["concept_id"]], 9),
            "mate_score": round(scores[case["mate_id"]], 9),
        })

    result = {
        "id": "YV-A593-hard-confusion-breadth-ABC-v0",
        "evidence_class": "frozen source-bound model-authored hard-confusion transfer evidence; not human accuracy",
        "concepts": len(cohort),
        "pairs": 11,
        "cases": len(cases),
        "opened_17_88_loaded": False,
        "test_queries": "the 3 per-side descriptions already frozen in a593-gemma4-sniper-contrasts-v0.jsonl; not used by A/B training or C task generation",
        "entrants": {
            "A_expanded_sparse_bm25": summarize(a_rows),
            "B_supervised_sparse_v0": summarize(b_rows),
            "C_task_atom_bm25_v0": summarize(c_rows),
        },
        "rows": {"A": a_rows, "B": b_rows, "C": c_rows},
        "guard": "Evaluator frozen before independent C task-atom output existed. Do not tune from these 66 rows.",
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["entrants"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
