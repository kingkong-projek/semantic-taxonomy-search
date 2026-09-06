#!/usr/bin/env python3
"""Build canonical review context for KV-100 misses and sampled hits.

The purpose is adjudication, not score rewriting. Every raw miss remains a raw miss even if
review later concludes that the synthetic target was ambiguous or weaker than a returned
candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_model_authored_kv_100 import rank_pos
from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, build_docs, rank
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1


def concept_context(concept: dict[str, Any] | None) -> dict[str, Any]:
    concept = concept or {}
    return {
        "concept_id": str(concept.get("id") or ""),
        "preferred_label": str(concept.get("preferred_label") or ""),
        "definition": str(concept.get("definition") or ""),
        "alternative_labels": [str(x) for x in (concept.get("alternative_labels") or [])],
        "hidden_labels": [str(x) for x in (concept.get("hidden_labels") or [])],
        "type": str(concept.get("type") or ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--cases", default="research/benchmark/v31/model-authored-kv-100/cases.jsonl")
    ap.add_argument("--output", default="artifacts/model-authored-kv-100-review-context-v31.json")
    args = ap.parse_args()

    cases = load_jsonl(Path(args.cases))
    if len(cases) != 100:
        raise RuntimeError(f"case count drift: {len(cases)}")
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    version = str(args.version)

    taxonomy_body = fetch(f"https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json")
    taxonomy_sha = hashlib.sha256(taxonomy_body).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(taxonomy_body).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    training_body = fetch_training()
    training_sha = hashlib.sha256(training_body).hexdigest()
    if training_sha != TRAINING_SHA:
        raise RuntimeError("training source drift")
    training_json = json.loads(training_body)
    modules = (training_json.get("data") or training_json.get("moduler") or training_json.get("modules")) if isinstance(training_json, dict) else training_json
    if not isinstance(modules, list):
        raise RuntimeError("unexpected training source root")

    ids = p80_skill_ids(pareto)
    docs, exact, _coverage = build_docs(by_id, ids, modules, set(), set())
    c0 = BM25(docs["KV-C0"], exact)
    g1 = BM25(docs["KV-G1-single-desc"], exact)

    rows = []
    for case in cases:
        q = str(case["query"])
        a = rank(c0, exact, q)
        b = rank(g1, exact, q)
        fused = fuse_preserve_c0_top1(a, b, 4)
        target = str(case["target"]["concept_id"])
        pos = rank_pos(fused, target)
        rows.append({
            "id": case["id"],
            "query": q,
            "difficulty": case.get("difficulty"),
            "target_authored": case["target"],
            "target_canonical": concept_context(by_id.get(target)),
            "fusion_rank": pos,
            "fusion_hit5": bool(pos is not None and pos <= 5),
            "fusion_top5": [concept_context(by_id.get(sid)) for sid in fused[:5]],
        })

    misses = [r for r in rows if not r["fusion_hit5"]]
    hits = [r for r in rows if r["fusion_hit5"]]
    hits.sort(key=lambda r: hashlib.sha256(str(r["id"]).encode("utf-8")).hexdigest())
    sample = hits[:15]

    result = {
        "schema_version": 1,
        "status": "adjudication context; never changes raw KV-100 score",
        "taxonomy_version": int(version),
        "taxonomy_sha256": taxonomy_sha,
        "training_sha256": training_sha,
        "review_policy": "review all 47-or-current misses and deterministic 15 nominal hits; classify target quality and returned-candidate plausibility before interpreting model failure",
        "review_labels": [
            "strong_target_model_miss",
            "target_reasonable_but_multi_intent",
            "returned_candidate_equally_or_more_reasonable",
            "synthetic_target_not_inferable",
            "taxonomy_boundary_or_near_duplicate",
            "needs_domain_review"
        ],
        "misses": misses,
        "deterministic_hit_sample": sample,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"misses": len(misses), "sample_hits": len(sample), "output": args.output}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
