#!/usr/bin/env python3
"""Build the untouched lower-volume holdout from the two frozen review pools.

The first 34 rows were consumed as the C0->C1 development slice. This script takes the
remaining 36 rows in exactly the same deterministic volume ordering. It infers no labels.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real-query", default="research/benchmark/v31/yv-real-query-review/review-packet.jsonl")
    ap.add_argument("--excluded-routing", default="research/benchmark/v31/yv-profile-safety/excluded-routing-review.jsonl")
    ap.add_argument("--development-rows", type=int, default=34)
    ap.add_argument("--output-dir", default="artifacts/pareto-holdout-batch-v31")
    args = ap.parse_args()

    real = read_jsonl(Path(args.real_query))
    excluded = read_jsonl(Path(args.excluded_routing))
    if len(real) != 50 or len(excluded) != 20:
        raise RuntimeError(f"expected 50 + 20 frozen review rows, got {len(real)} + {len(excluded)}")

    merged: list[dict[str, Any]] = []
    for row in real:
        merged.append({
            "source_pool": "observed_unbound_query",
            "source_id": row["id"],
            "query": row["query"],
            "observed_count": int(row["observed_count"]),
            "candidate_context": row.get("candidate_context", {}),
            "source": row.get("source", {}),
            "taxonomy_version": row["taxonomy_version"],
            "adjudication": row["adjudication"],
        })
    for row in excluded:
        merged.append({
            "source_pool": "yv_excluded_title_routing",
            "source_id": row["id"],
            "query": row["query"],
            "observed_count": int(row["observed_count"]),
            "job_title_id": row["job_title_id"],
            "yv_exclusion_reason": row["yv_exclusion_reason"],
            "candidate_occupation_identities": row.get("candidate_occupation_identities", []),
            "source": row.get("source", {}),
            "taxonomy_version": row["taxonomy_version"],
            "adjudication": row["adjudication"],
        })

    if any(r.get("adjudication", {}).get("status") != "PENDING_HUMAN_REVIEW" for r in merged):
        raise RuntimeError("source review population unexpectedly contains adjudicated rows")

    merged.sort(key=lambda r: (-r["observed_count"], r["source_pool"], str(r["query"]).casefold(), r["source_id"]))
    if len(merged) != 70 or args.development_rows != 34:
        raise RuntimeError("frozen review/development split drift")

    total = sum(r["observed_count"] for r in merged)
    development = merged[:args.development_rows]
    holdout = merged[args.development_rows:]
    if len(holdout) != 36:
        raise RuntimeError(f"expected 36 holdout rows, got {len(holdout)}")

    development_volume = sum(r["observed_count"] for r in development)
    holdout_volume = sum(r["observed_count"] for r in holdout)
    if round(100 * development_volume / total, 3) != 80.738:
        raise RuntimeError("development Pareto share drift")

    for rank, row in enumerate(holdout, args.development_rows + 1):
        row["pareto_rank"] = rank

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "holdout.jsonl").open("w", encoding="utf-8") as f:
        for row in holdout:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    manifest = {
        "schema_version": 1,
        "taxonomy_version": 31,
        "status": "UNADJUDICATED_HOLDOUT",
        "source_rows": len(merged),
        "development_rows": len(development),
        "holdout_rows": len(holdout),
        "source_pool_observed_volume": total,
        "development_observed_volume": development_volume,
        "development_share_pct": round(100 * development_volume / total, 3),
        "holdout_observed_volume": holdout_volume,
        "holdout_share_pct": round(100 * holdout_volume / total, 3),
        "holdout_by_pool": {
            "observed_unbound_query": sum(1 for r in holdout if r["source_pool"] == "observed_unbound_query"),
            "yv_excluded_title_routing": sum(1 for r in holdout if r["source_pool"] == "yv_excluded_title_routing"),
        },
        "selection": "same deterministic descending observed-volume ordering as development batch; rows 35-70 were untouched by C1 design",
        "authority_boundary": "holdout selection is behavioral/Pareto only; no destination labels inferred",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
