#!/usr/bin/env python3
"""Regression-check the full YV occupation universe on frozen source-truth cases.

This is not a natural-language quality benchmark. The 333 frozen YV cases are canonical
labels, canonical definitions and canonical alternative labels bound to 159 P80 targets.
The purpose is narrower: expanding the same deterministic canonical ranker from the old
P80/C2 candidate universe to all 2,105 active occupation-name identities must not create
unacceptable representation/regression failures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_c2_job_title_router import build_c1_index
from evaluate_p80_lexical_ablation import expected_hash, fetch, load_jsonl
from evaluate_pareto_c1 import BOUNDARY_IDS, p80_ids, rank_c1


def evaluate(cases: list[dict[str, Any]], ranker, exact, surface_tokens) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    by_origin: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        expected = {str(x["concept_id"]) for x in case["must"]}
        scored = rank_c1(ranker, str(case["query"]), exact, surface_tokens)
        ranked = [cid for cid, _, _ in scored]
        positions = [ranked.index(cid) + 1 for cid in expected if cid in ranked]
        first = min(positions) if positions else None
        row = {
            "id": case["id"],
            "query_origin": str(case["query_origin"]),
            "expected": sorted(expected),
            "rank": first,
            "top1": bool(first == 1),
            "hit_at_5": bool(isinstance(first, int) and first <= 5),
            "hit_at_10": bool(isinstance(first, int) and first <= 10),
            "rr": 0.0 if first is None else 1.0 / first,
            "top5": ranked[:5],
        }
        rows.append(row)
        by_origin[row["query_origin"]].append(row)

    def agg(group: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(group)
        return {
            "cases": n,
            "top1": round(sum(r["top1"] for r in group) / n, 6) if n else None,
            "hit_at_5": round(sum(r["hit_at_5"] for r in group) / n, 6) if n else None,
            "hit_at_10": round(sum(r["hit_at_10"] for r in group) / n, 6) if n else None,
            "mrr": round(sum(r["rr"] for r in group) / n, 6) if n else None,
        }

    misses = [
        {
            "id": r["id"],
            "query_origin": r["query_origin"],
            "expected": r["expected"],
            "rank": r["rank"],
            "top5": r["top5"],
        }
        for r in rows if not r["top1"]
    ]
    return {
        "overall": agg(rows),
        "by_query_origin": {k: agg(v) for k, v in sorted(by_origin.items())},
        "top1_miss_count": len(misses),
        "top1_misses": misses,
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--benchmark", default="research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl")
    ap.add_argument("--output", default="artifacts/yv-full-universe-source-truth-regression-v31.json")
    args = ap.parse_args()

    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    benchmark_path = Path(args.benchmark)
    cases = load_jsonl(benchmark_path)
    if len(cases) != 333:
        raise RuntimeError(f"frozen YV source-truth case count drift: {len(cases)}")
    origin_counts: dict[str, int] = defaultdict(int)
    target_ids: set[str] = set()
    for case in cases:
        origin_counts[str(case["query_origin"])] += 1
        target_ids.update(str(x["concept_id"]) for x in case["must"])
    if dict(origin_counts) != {
        "canonical_label": 159,
        "canonical_definition": 137,
        "alternative_label": 37,
    }:
        raise RuntimeError(f"frozen YV source-truth origin drift: {dict(origin_counts)}")
    if len(target_ids) != 159:
        raise RuntimeError(f"frozen YV target count drift: {len(target_ids)}")

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    wire = fetch(taxonomy_url)
    taxonomy_sha = hashlib.sha256(wire).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError(f"taxonomy source drift: {taxonomy_sha}")
    taxonomy = json.loads(wire)
    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active_occ = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(active_occ) != 2105:
        raise RuntimeError(f"active occupation universe drift: {len(active_occ)}")
    if not target_ids <= set(active_occ):
        raise RuntimeError("frozen YV source-truth contains non-active occupation target")

    p80 = sorted(p80_ids(pareto))
    if len(p80) != 159 or set(p80) != target_ids:
        raise RuntimeError("frozen source-truth targets differ from frozen P80 occupation membership")
    c2 = sorted(set(p80) | BOUNDARY_IDS)
    if len(c2) != 165:
        raise RuntimeError(f"C2 candidate universe drift: {len(c2)}")

    configs = {
        "p80_canonical_159": p80,
        "c2_canonical_165": c2,
        "full_canonical_2105": active_occ,
    }
    results: dict[str, Any] = {}
    for name, ids in configs.items():
        ranker, exact, surface_tokens = build_c1_index(by_id, ids)
        results[name] = evaluate(cases, ranker, exact, surface_tokens)

    baseline_rows = {r["id"]: r for r in results["c2_canonical_165"]["rows"]}
    full_rows = {r["id"]: r for r in results["full_canonical_2105"]["rows"]}
    rank_regressions = []
    rank_improvements = []
    for case_id in sorted(full_rows):
        old = baseline_rows[case_id]["rank"]
        new = full_rows[case_id]["rank"]
        if isinstance(old, int) and isinstance(new, int):
            if new > old:
                rank_regressions.append({"id": case_id, "old_rank": old, "new_rank": new})
            elif new < old:
                rank_improvements.append({"id": case_id, "old_rank": old, "new_rank": new})

    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "status": "frozen_source_truth_regression_not_natural_language_validation",
        "purpose": (
            "measure candidate-universe competition when the same canonical YV description ranker expands "
            "from P80/C2 to all active occupation-name identities"
        ),
        "benchmark": {
            "path": str(benchmark_path),
            "sha256": hashlib.sha256(benchmark_path.read_bytes()).hexdigest(),
            "cases": len(cases),
            "targets": len(target_ids),
            "origin_counts": dict(sorted(origin_counts.items())),
            "authority": "canonical source-attested regression suite; not natural paraphrase accuracy",
        },
        "source": {"taxonomy_url": taxonomy_url, "taxonomy_sha256": taxonomy_sha},
        "candidate_counts": {name: len(ids) for name, ids in configs.items()},
        "results": results,
        "c2_to_full_rank_changes": {
            "regression_count": len(rank_regressions),
            "improvement_count": len(rank_improvements),
            "regressions": rank_regressions,
            "improvements": rank_improvements,
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "benchmark": result["benchmark"],
        "candidate_counts": result["candidate_counts"],
        "metrics": {name: data["overall"] for name, data in results.items()},
        "rank_changes": result["c2_to_full_rank_changes"],
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
