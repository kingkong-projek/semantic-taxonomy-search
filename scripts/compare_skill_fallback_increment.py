#!/usr/bin/env python3
"""Compare the pinned current KV selector against frozen semantic KV-C0 on the same blind holdout."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_HOLDOUT_SHA = "79816eb2020b100bf8260b8f1807069288c30dbabd457bfffbfe3f49735c6675"
EXPECTED_PRODUCT_COMMIT = "0eba98e3a91079a43c1eaf6da09dfabe11e5bc8b"
EXPECTED_FUSE = "7.5.0"
EXPECTED_KV_SHA = "da83f26bf316971caa407364d8feae6f791203bff5758e674cace3d919e4b524"


def pct(n: float, d: float) -> float:
    return round(100.0 * n / d, 3) if d else 0.0


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", default="research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl")
    ap.add_argument("--product", required=True)
    ap.add_argument("--semantic", default="research/evaluation/v31/skill-fresh-holdout.json")
    ap.add_argument("--output", default="artifacts/skill-fallback-increment-v31.json")
    args = ap.parse_args()

    benchmark_path = Path(args.benchmark)
    actual_sha = hashlib.sha256(benchmark_path.read_bytes()).hexdigest()
    if actual_sha != EXPECTED_HOLDOUT_SHA:
        raise RuntimeError(f"blind holdout drift: {actual_sha}")
    cases = load_jsonl(benchmark_path)
    if len(cases) != 35:
        raise RuntimeError(f"benchmark count drift: {len(cases)}")

    product = json.loads(Path(args.product).read_text(encoding="utf-8"))
    semantic = json.loads(Path(args.semantic).read_text(encoding="utf-8"))
    if product.get("pinned_selector", {}).get("commit") != EXPECTED_PRODUCT_COMMIT:
        raise RuntimeError("product selector commit drift")
    if product.get("pinned_selector", {}).get("fuse_js_version") != EXPECTED_FUSE:
        raise RuntimeError("product Fuse version drift")
    if product.get("source", {}).get("sha256") != EXPECTED_KV_SHA:
        raise RuntimeError("product KV source drift")
    if product.get("cases") != 35:
        raise RuntimeError("product case count drift")

    c0 = semantic.get("configurations", {}).get("KV-C0")
    details = semantic.get("cases_detail", {}).get("KV-C0")
    if not isinstance(c0, dict) or not isinstance(details, list) or len(details) != 35:
        raise RuntimeError("semantic KV-C0 result drift")
    semantic_by_id = {str(r["id"]): r for r in details}
    product_by_id = {str(r["id"]): r for r in product.get("cases_detail", [])}
    case_ids = {str(c["id"]) for c in cases}
    if set(semantic_by_id) != case_ids or set(product_by_id) != case_ids:
        raise RuntimeError("case identity mismatch across benchmark/product/semantic")

    counts = {"both_hit": 0, "product_only": 0, "semantic_rescue": 0, "both_miss": 0}
    weights = {k: 0 for k in counts}
    rows = []
    total_weight = 0
    for case in cases:
        cid = str(case["id"])
        weight = int(case["target"]["occurrence_proxy"])
        total_weight += weight
        prow = product_by_id[cid]
        srow = semantic_by_id[cid]
        product_hit = str(case["target"]["concept_id"]) in [str(x) for x in prow.get("top5_ids", [])]
        semantic_hit = bool(srow.get("result_hit5"))
        if product_hit and semantic_hit:
            category = "both_hit"
        elif product_hit:
            category = "product_only"
        elif semantic_hit:
            category = "semantic_rescue"
        else:
            category = "both_miss"
        counts[category] += 1
        weights[category] += weight
        rows.append({
            "id": cid,
            "target_id": str(case["target"]["concept_id"]),
            "target_label": str(case["target"]["label"]),
            "occurrence_proxy": weight,
            "product_hit_at_5": product_hit,
            "semantic_c0_hit_at_5": semantic_hit,
            "category": category,
            "semantic_top5_ids": srow.get("result_top5_ids", []),
        })

    product_hits = counts["both_hit"] + counts["product_only"]
    semantic_hits = counts["both_hit"] + counts["semantic_rescue"]
    product_hit_weight = weights["both_hit"] + weights["product_only"]
    semantic_hit_weight = weights["both_hit"] + weights["semantic_rescue"]
    product_pct = pct(product_hits, len(cases))
    semantic_pct = pct(semantic_hits, len(cases))
    product_weighted_pct = pct(product_hit_weight, total_weight)
    semantic_weighted_pct = pct(semantic_hit_weight, total_weight)

    out = {
        "schema_version": 1,
        "taxonomy_version": 31,
        "role": "incremental KV description-fallback comparison on frozen blind source-attested holdout",
        "benchmark": {
            "path": args.benchmark,
            "sha256": actual_sha,
            "cases": len(cases),
            "occurrence_proxy_weight": total_weight,
            "traffic_weight": False,
        },
        "product_baseline": {
            "repository": "kingkong-projek/yrkesvaljaren",
            "commit": EXPECTED_PRODUCT_COMMIT,
            "fuse_js_version": EXPECTED_FUSE,
            "path_replayed": product["pinned_selector"]["path_replayed"],
            "context": product["pinned_selector"]["context"],
            "discovery_hit_at_5_pct": product_pct,
            "weighted_discovery_hit_at_5_pct": product_weighted_pct,
            "no_result_cases": int(product.get("no_result_cases", 0)),
        },
        "semantic_fallback": {
            "configuration": "KV-C0",
            "retrieval_documents": "P80 skill preferred labels + real canonical definitions + canonical alternative labels only",
            "discovery_hit_at_5_pct": semantic_pct,
            "weighted_discovery_hit_at_5_pct": semantic_weighted_pct,
            "canonical_regression_cases": 617,
            "canonical_regression_discovery_hit_at_5_pct": semantic.get("source_truth_regression", {}).get("discovery_hit_at_5_pct"),
        },
        "increment": {
            "discovery_hit_at_5_percentage_points": round(semantic_pct - product_pct, 3),
            "weighted_discovery_hit_at_5_percentage_points": round(semantic_weighted_pct - product_weighted_pct, 3),
            "fallback_eligible_cases": len(cases) - product_hits,
            "fallback_eligible_pct": pct(len(cases) - product_hits, len(cases)),
            "semantic_rescues": counts["semantic_rescue"],
            "rescue_rate_among_product_misses_pct": pct(counts["semantic_rescue"], len(cases) - product_hits),
            "weighted_rescue_rate_among_product_misses_pct": pct(weights["semantic_rescue"], total_weight - product_hit_weight),
        },
        "contingency": counts,
        "contingency_occurrence_proxy_weight": weights,
        "remaining_residual_case_ids": [r["id"] for r in rows if r["category"] == "both_miss"],
        "cases_detail": rows,
        "interpretation_boundary": "This measures incremental fallback value on this frozen source-attested description benchmark. Occurrence proxy is not user traffic, and the opened residual must not be reused as independent validation after tuning.",
    }
    if out["product_baseline"]["discovery_hit_at_5_pct"] != 0.0 or out["product_baseline"]["no_result_cases"] != 35:
        raise RuntimeError("unexpected pinned product result drift")
    if out["semantic_fallback"]["discovery_hit_at_5_pct"] != 31.429:
        raise RuntimeError("unexpected KV-C0 result drift")
    if out["increment"]["semantic_rescues"] != 11 or counts["both_miss"] != 24:
        raise RuntimeError("increment contingency drift")

    p = Path(args.output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "product_discovery_at_5": product_pct,
        "semantic_discovery_at_5": semantic_pct,
        "increment_pp": out["increment"]["discovery_hit_at_5_percentage_points"],
        "weighted_increment_pp": out["increment"]["weighted_discovery_hit_at_5_percentage_points"],
        "contingency": counts,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
