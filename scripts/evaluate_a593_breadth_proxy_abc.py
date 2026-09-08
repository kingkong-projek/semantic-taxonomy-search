#!/usr/bin/env python3
"""Evaluate frozen simple architecture breadth entrants A/B/C on one proxy.

The evaluator is frozen before the proxy output is inspected. It compares:
A) flattened expanded-text BM25;
B) the already-fixed supervised sparse B-v0 formulation;
C) task/activity atoms scored as atom documents with max-per-concept aggregation.

No opened 17/88 inputs are loaded.
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
STYLES = (
    "direct_task",
    "colloquial_first_person",
    "indirect_narrative",
    "noisy_telegraphic",
)


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def tokens(value: Any) -> list[str]:
    return [m.group(0).casefold() for m in TOKEN_RE.finditer(str(value or ""))]


class BM25:
    def __init__(self, documents: dict[str, list[str]], *, k1: float = 1.2, b: float = 0.75):
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.lengths = {doc_id: len(ts) for doc_id, ts in documents.items()}
        self.avgdl = sum(self.lengths.values()) / max(1, len(self.lengths))
        self.tf = {doc_id: collections.Counter(ts) for doc_id, ts in documents.items()}
        df: collections.Counter[str] = collections.Counter()
        for ts in documents.values():
            df.update(set(ts))
        n = len(documents)
        self.idf = {
            term: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def score(self, query: str, doc_id: str) -> float:
        q = set(tokens(query))
        tf = self.tf[doc_id]
        dl = self.lengths[doc_id]
        value = 0.0
        for term in q:
            f = tf.get(term, 0)
            if not f:
                continue
            idf = self.idf.get(term, 0.0)
            denom = f + self.k1 * (1.0 - self.b + self.b * dl / max(self.avgdl, 1e-9))
            value += idf * (f * (self.k1 + 1.0) / denom)
        return value


def load_teacher(path: Path) -> dict[str, list[str]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    phrases = {}
    for row in rows:
        cid = str(row.get("concept_id") or "")
        values = [str(x).strip() for x in row.get("phrases") or [] if str(x).strip()]
        if cid and len(values) == 8:
            phrases[cid] = values
    if len(phrases) != 593:
        raise RuntimeError(f"A593 teacher drift: {len(phrases)}")
    return phrases


def load_proxy(path: Path, teacher: dict[str, list[str]]):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("opened_17_88_used_for_selection_or_prompting") is not False:
        raise RuntimeError("proxy opened-query guard missing")
    rows = []
    for row in payload.get("rows") or []:
        cid = str(row.get("concept_id") or "")
        queries = row.get("heldout_queries") or {}
        atoms = [str(x).strip() for x in row.get("task_atoms") or [] if str(x).strip()]
        if cid not in teacher or row.get("task_usable") is not True or row.get("query_usable") is not True:
            continue
        if len(atoms) != 4 or set(queries) != set(STYLES):
            continue
        rows.append(row)
    if len(rows) < 8:
        raise RuntimeError(f"too few usable proxy rows: {len(rows)}")
    return payload, rows


def summarize(case_rows):
    ranks = [row["rank"] for row in case_rows]
    return {
        "cases": len(ranks),
        "top1_count": sum(rank == 1 for rank in ranks),
        "top1_rate": round(sum(rank == 1 for rank in ranks) / max(1, len(ranks)), 6),
        "hit_at_5_count": sum(rank <= 5 for rank in ranks),
        "hit_at_5_rate": round(sum(rank <= 5 for rank in ranks) / max(1, len(ranks)), 6),
        "mrr": round(sum(1.0 / rank for rank in ranks) / max(1, len(ranks)), 6),
    }


def summarize_by_style(rows):
    return {
        style: summarize([row for row in rows if row["style"] == style])
        for style in STYLES
    }


def rank_from_mapping(scores: dict[str, float], target: str, cids: list[str]) -> int:
    target_score = scores[target]
    return 1 + sum(
        1
        for cid in cids
        if scores[cid] > target_score or (scores[cid] == target_score and cid < target)
    )


def build_cases(proxy_rows):
    cases = []
    for row in proxy_rows:
        cid = str(row["concept_id"])
        for style in STYLES:
            cases.append({
                "concept_id": cid,
                "label": str(row.get("label") or cid),
                "style": style,
                "query": str(row["heldout_queries"][style]),
            })
    return cases


def evaluate_a(cids, proxy_rows, teacher, cases):
    evidence_by_id = {str(row["concept_id"]): row.get("source_evidence") or {} for row in proxy_rows}
    documents = {}
    for cid in cids:
        evidence = evidence_by_id[cid]
        text = " ".join(
            [
                str(evidence.get("canonical_label") or ""),
                str(evidence.get("definition") or ""),
                *[str(x) for x in evidence.get("alternative_labels") or []],
                *teacher[cid],
            ]
        )
        documents[cid] = tokens(text)
    ranker = BM25(documents)
    rows = []
    for case in cases:
        scores = {cid: ranker.score(case["query"], cid) for cid in cids}
        rank = rank_from_mapping(scores, case["concept_id"], cids)
        rows.append({**case, "rank": rank})
    return rows


def evaluate_b(cids, teacher, cases):
    train_texts = []
    train_labels = []
    for cid in cids:
        for phrase in teacher[cid]:
            train_texts.append(phrase)
            train_labels.append(cid)
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=2,
        max_features=30000,
        sublinear_tf=True,
        norm="l2",
        dtype=np.float32,
        lowercase=True,
    )
    x_train = vectorizer.fit_transform(train_texts)
    clf = SGDClassifier(
        loss="hinge",
        penalty="l2",
        alpha=1e-5,
        max_iter=2000,
        tol=1e-4,
        random_state=0,
        n_jobs=-1,
        average=True,
    )
    clf.fit(x_train, train_labels)
    query_texts = [case["query"] for case in cases]
    scores = clf.decision_function(vectorizer.transform(query_texts))
    classes = [str(x) for x in clf.classes_]
    class_index = {cid: i for i, cid in enumerate(classes)}
    rows = []
    for row_index, case in enumerate(cases):
        mapping = {cid: float(scores[row_index, class_index[cid]]) for cid in cids}
        rank = rank_from_mapping(mapping, case["concept_id"], cids)
        rows.append({**case, "rank": rank})
    return rows


def evaluate_c(cids, proxy_rows, cases):
    atom_docs = {}
    atom_to_cid = {}
    for row in proxy_rows:
        cid = str(row["concept_id"])
        for index, atom in enumerate(row["task_atoms"]):
            atom_id = f"{cid}#{index}"
            atom_docs[atom_id] = tokens(atom)
            atom_to_cid[atom_id] = cid
    ranker = BM25(atom_docs)
    rows = []
    for case in cases:
        concept_scores = {cid: 0.0 for cid in cids}
        for atom_id, cid in atom_to_cid.items():
            value = ranker.score(case["query"], atom_id)
            if value > concept_scores[cid]:
                concept_scores[cid] = value
        rank = rank_from_mapping(concept_scores, case["concept_id"], cids)
        rows.append({**case, "rank": rank})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--proxy", default="research/evaluation/v31/compile-time-semantic-a593-breadth-proxy-v0.json")
    ap.add_argument("--output", default="artifacts/a593-breadth-proxy-abc.json")
    args = ap.parse_args()

    teacher = load_teacher(Path(args.teacher))
    proxy_payload, proxy_rows = load_proxy(Path(args.proxy), teacher)
    cids = sorted(str(row["concept_id"]) for row in proxy_rows)
    cases = build_cases(proxy_rows)

    a_rows = evaluate_a(cids, proxy_rows, teacher, cases)
    b_rows = evaluate_b(cids, teacher, cases)
    c_rows = evaluate_c(cids, proxy_rows, cases)

    result = {
        "id": "YV-A593-breadth-ABC-proxy-v0",
        "evidence_class": "prefrozen synthetic architecture-selection evidence; not human accuracy",
        "proxy_id": proxy_payload.get("id"),
        "concepts": len(cids),
        "cases": len(cases),
        "candidate_universe": "only usable concepts frozen into breadth proxy v0; same universe for A/B/C",
        "opened_17_88_loaded": False,
        "entrants": {
            "A_expanded_sparse_bm25": {
                "mechanism": "canonical source evidence + 8 frozen A593 teacher phrases flattened per concept; token BM25",
                "overall": summarize(a_rows),
                "by_style": summarize_by_style(a_rows),
            },
            "B_supervised_sparse_v0": {
                "mechanism": "fixed B-v0 char_wb 3-5 TF-IDF + one-vs-rest hinge SGD; trained on 8 old teacher phrases per concept",
                "overall": summarize(b_rows),
                "by_style": summarize_by_style(b_rows),
            },
            "C_task_atom_bm25_v0": {
                "mechanism": "4 independently generated source-bound task atoms per concept; token BM25 over atoms; concept score=max atom score",
                "overall": summarize(c_rows),
                "by_style": summarize_by_style(c_rows),
            },
        },
        "rows": {
            "A": a_rows,
            "B": b_rows,
            "C": c_rows,
        },
        "guard": "Evaluator implementation was frozen before proxy output was inspected. Do not tune from proxy rows; a later larger/fresh proxy or human evidence is required for promotion.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"A": result["entrants"]["A_expanded_sparse_bm25"]["overall"], "B": result["entrants"]["B_supervised_sparse_v0"]["overall"], "C": result["entrants"]["C_task_atom_bm25_v0"]["overall"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
