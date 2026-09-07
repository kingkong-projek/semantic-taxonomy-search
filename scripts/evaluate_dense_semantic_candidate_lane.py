#!/usr/bin/env python3
"""Evaluate a provenance-separated dense semantic candidate lane on opened stress data.

This script is deliberately diagnostic. It does not fuse, tune, or promote a runtime
change. It asks one architecture question exposed by the live stress replay: can a
small multilingual embedding model retrieve plausible canonical targets that lexical
BM25 places far outside a practical rerank window?

The opened assistant-authored stress suite is NEVER treated as blind accuracy. Frozen
source-truth suites are reported only as a representation/regression guard.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from huggingface_hub import model_info
from sentence_transformers import SentenceTransformer

from build_kv_demo_asset import TEACHER_PATHS
from evaluate_p80_lexical_ablation import as_list, expected_hash, fetch, load_jsonl, norm
from evaluate_skill_c0_training_validation import p80_skill_ids

MODEL_NAME = "intfloat/multilingual-e5-small"


def teacher_map() -> dict[str, list[str]]:
    rows: list[dict[str, Any]] = []
    for path in TEACHER_PATHS:
        rows.extend(load_jsonl(Path(path)))
    if len(rows) != 316:
        raise RuntimeError(f"teacher count drift: {len(rows)} != 316")
    out: dict[str, list[str]] = {}
    for row in rows:
        cid = str(row["concept_id"])
        phrases = [str(x).strip() for x in row.get("phrases") or [] if str(x).strip()]
        if cid in out or len(phrases) != 3:
            raise RuntimeError(f"teacher identity/phrase drift: {cid}")
        out[cid] = phrases
    return out


def concept_text(concept: dict[str, Any], *, extra: list[str] | None = None) -> str:
    label = str(concept.get("preferred_label") or "").strip()
    definition = str(concept.get("definition") or "").strip()
    if norm(definition) == norm(label):
        definition = ""
    alternatives = [str(x).strip() for x in as_list(concept.get("alternative_labels"))]
    parts = [label, definition, *alternatives, *(extra or [])]
    return " | ".join(x for x in parts if x)


def family_rank(labels: list[str], expected: list[str], order: np.ndarray) -> int | None:
    needles = [norm(x) for x in expected if norm(x)]
    if not needles:
        return None
    for rank, index in enumerate(order, start=1):
        label = norm(labels[int(index)])
        if any(needle in label for needle in needles):
            return rank
    return None


def summarize_opened_cases(cases: list[dict[str, Any]], sims: np.ndarray, labels: list[str]) -> dict[str, Any]:
    by_category: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for i, case in enumerate(cases):
        order = np.argsort(-sims[i], kind="stable")
        expected = [str(x) for x in case.get("expect") or []]
        rank = family_rank(labels, expected, order)
        top = [
            {"rank": j + 1, "label": labels[int(idx)], "score": round(float(sims[i, int(idx)]), 6)}
            for j, idx in enumerate(order[:5])
        ]
        row = {
            "id": case["id"],
            "category": case["category"],
            "query": case["query"],
            "expected_label_families": expected,
            "expected_family_rank": rank,
            "top5": top,
            "max_similarity": top[0]["score"] if top else None,
            "should_clarify": bool(case.get("should_clarify")),
            "should_abstain": bool(case.get("should_abstain")),
        }
        rows.append(row)

    categories = sorted({str(c["category"]) for c in cases})
    for category in categories:
        subset = [r for r in rows if r["category"] == category]
        target = [r for r in subset if r["expected_label_families"]]
        entry: dict[str, Any] = {"cases": len(subset)}
        if target:
            entry.update(
                {
                    "target_cases": len(target),
                    "top1_family_hit": sum(r["expected_family_rank"] == 1 for r in target),
                    "top5_family_hit": sum(
                        r["expected_family_rank"] is not None and r["expected_family_rank"] <= 5 for r in target
                    ),
                    "top20_family_hit": sum(
                        r["expected_family_rank"] is not None and r["expected_family_rank"] <= 20 for r in target
                    ),
                    "top50_family_hit": sum(
                        r["expected_family_rank"] is not None and r["expected_family_rank"] <= 50 for r in target
                    ),
                    "median_expected_rank": float(np.median([r["expected_family_rank"] for r in target if r["expected_family_rank"] is not None]))
                    if any(r["expected_family_rank"] is not None for r in target)
                    else None,
                }
            )
        negative = [r for r in subset if r["should_abstain"] or (r["should_clarify"] and not r["expected_label_families"])]
        if negative:
            scores = [float(r["max_similarity"]) for r in negative]
            entry["negative_or_clarify_max_similarity"] = {
                "count": len(scores),
                "min": round(min(scores), 6),
                "median": round(float(np.median(scores)), 6),
                "max": round(max(scores), 6),
            }
        by_category[category] = entry
    return {"categories": by_category, "rows": rows}


def source_truth_guard(
    path: Path,
    model: SentenceTransformer,
    doc_embeddings: np.ndarray,
    ids: list[str],
    *,
    batch_size: int,
) -> dict[str, Any]:
    cases = load_jsonl(path)
    queries = ["query: " + str(row["query"]) for row in cases]
    q = model.encode(queries, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)
    sims = np.asarray(q, dtype=np.float32) @ doc_embeddings.T
    id_to_index = {cid: i for i, cid in enumerate(ids)}
    top1 = top5 = 0
    mrr = 0.0
    missing_targets = 0
    for i, row in enumerate(cases):
        target_ids = [str(x["concept_id"]) for x in [*(row.get("must") or []), *(row.get("acceptable") or [])]]
        target_indices = {id_to_index[cid] for cid in target_ids if cid in id_to_index}
        if not target_indices:
            missing_targets += 1
            continue
        order = np.argsort(-sims[i], kind="stable")
        rank = next((r for r, idx in enumerate(order, start=1) if int(idx) in target_indices), None)
        if rank == 1:
            top1 += 1
        if rank is not None and rank <= 5:
            top5 += 1
        if rank:
            mrr += 1.0 / rank
    if missing_targets:
        raise RuntimeError(f"source-truth target universe drift in {path}: {missing_targets}")
    return {
        "cases": len(cases),
        "top1": top1,
        "hit_at_5": top5,
        "mrr": round(mrr / len(cases), 6) if cases else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--output", default="artifacts/dense-semantic-candidate-lane-v31.json")
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args()

    stress = json.loads(Path(args.stress).read_text(encoding="utf-8"))
    if len(stress.get("yv") or []) != 54 or len(stress.get("kv") or []) != 34:
        raise RuntimeError("opened stress suite drift")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    taxonomy_url = "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json"
    taxonomy_body = fetch(taxonomy_url)
    taxonomy_sha = hashlib.sha256(taxonomy_body).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(taxonomy_body).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    yv_ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(yv_ids) != 2105:
        raise RuntimeError(f"YV target universe drift: {len(yv_ids)}")
    yv_labels = [str(by_id[cid].get("preferred_label") or cid) for cid in yv_ids]
    yv_docs = ["passage: " + concept_text(by_id[cid]) for cid in yv_ids]

    kv_ids = sorted(p80_skill_ids(pareto))
    if len(kv_ids) != 316:
        raise RuntimeError(f"KV target universe drift: {len(kv_ids)}")
    teacher = teacher_map()
    if set(teacher) != set(kv_ids):
        raise RuntimeError("teacher/P80 identity drift")
    kv_labels = [str(by_id[cid].get("preferred_label") or cid) for cid in kv_ids]
    kv_docs = ["passage: " + concept_text(by_id[cid], extra=teacher[cid]) for cid in kv_ids]

    info = model_info(MODEL_NAME)
    revision = str(info.sha or "")
    if len(revision) < 7:
        raise RuntimeError("could not resolve model revision")
    model = SentenceTransformer(MODEL_NAME, revision=revision, trust_remote_code=False)

    yv_emb = np.asarray(
        model.encode(yv_docs, batch_size=args.batch_size, normalize_embeddings=True, show_progress_bar=True),
        dtype=np.float32,
    )
    kv_emb = np.asarray(
        model.encode(kv_docs, batch_size=args.batch_size, normalize_embeddings=True, show_progress_bar=True),
        dtype=np.float32,
    )

    yv_queries = ["query: " + str(x["query"]) for x in stress["yv"]]
    kv_queries = ["query: " + str(x["query"]) for x in stress["kv"]]
    yv_q = np.asarray(model.encode(yv_queries, batch_size=args.batch_size, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)
    kv_q = np.asarray(model.encode(kv_queries, batch_size=args.batch_size, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)
    yv_sims = yv_q @ yv_emb.T
    kv_sims = kv_q @ kv_emb.T

    result = {
        "status": "opened diagnostic only; no runtime promotion or fusion selected",
        "model": {
            "name": MODEL_NAME,
            "resolved_revision": revision,
            "representation": {
                "yv": "canonical preferred label + distinct definition + canonical alternatives",
                "kv": "canonical preferred label + distinct definition + canonical alternatives + existing frozen three teacher phrases",
                "query_prefix": "query: ",
                "document_prefix": "passage: ",
            },
        },
        "sources": {"taxonomy_sha256": taxonomy_sha, "stress_path": args.stress},
        "opened_stress": {
            "yv": summarize_opened_cases(stress["yv"], yv_sims, yv_labels),
            "kv": summarize_opened_cases(stress["kv"], kv_sims, kv_labels),
        },
        "source_truth_representation_guard": {
            "yv": source_truth_guard(
                Path("research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl"),
                model,
                yv_emb,
                yv_ids,
                batch_size=args.batch_size,
            ),
            "kv": source_truth_guard(
                Path("research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl"),
                model,
                kv_emb,
                kv_ids,
                batch_size=args.batch_size,
            ),
        },
        "decision_contract": (
            "Use this run only to determine whether a separate dense candidate lane has architectural signal. "
            "Do not tune thresholds, fusion weights, or promote the model on this opened assistant-authored suite."
        ),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    compact = {
        "model": result["model"],
        "opened_stress": {
            stream: result["opened_stress"][stream]["categories"] for stream in ("yv", "kv")
        },
        "source_truth_representation_guard": result["source_truth_representation_guard"],
        "output": str(out),
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
