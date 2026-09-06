#!/usr/bin/env python3
"""Build a compact Pareto adjudication batch from already-frozen review populations.

No labels are inferred here. The script only merges and ranks existing pending-review
rows by observed volume so adjudication effort starts with the highest-value cases.
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
    ap.add_argument("--target-share", type=float, default=0.80)
    ap.add_argument("--output-dir", default="artifacts/pareto-adjudication-batch-v31")
    args = ap.parse_args()

    real = read_jsonl(Path(args.real_query))
    excluded = read_jsonl(Path(args.excluded_routing))
    if len(real) != 50 or len(excluded) != 20:
        raise RuntimeError(f"expected 50 + 20 frozen review rows, got {len(real)} + {len(excluded)}")

    merged: list[dict[str, Any]] = []
    for row in real:
        if row.get("adjudication", {}).get("status") != "PENDING_HUMAN_REVIEW":
            raise RuntimeError(f"real-query row not pending: {row.get('id')}")
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
        if row.get("adjudication", {}).get("status") != "PENDING_HUMAN_REVIEW":
            raise RuntimeError(f"excluded-routing row not pending: {row.get('id')}")
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

    merged.sort(key=lambda r: (-r["observed_count"], r["source_pool"], str(r["query"]).casefold(), r["source_id"]))
    total = sum(r["observed_count"] for r in merged)
    selected: list[dict[str, Any]] = []
    cumulative = 0
    for rank, row in enumerate(merged, 1):
        cumulative += row["observed_count"]
        row = dict(row)
        row["pareto_rank"] = rank
        row["cumulative_pool_share_pct"] = round(100 * cumulative / total, 3)
        selected.append(row)
        if cumulative / total >= args.target_share:
            break

    if len(selected) != 34:
        raise RuntimeError(f"expected current frozen P80 review batch to be 34 rows, got {len(selected)}")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "batch.jsonl").open("w", encoding="utf-8") as f:
        for row in selected:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    manifest = {
        "schema_version": 1,
        "taxonomy_version": 31,
        "status": "PENDING_ADJUDICATION",
        "source_rows": len(merged),
        "selected_rows": len(selected),
        "selection": "descending observed_count across the two frozen pending-review pools until cumulative observed volume reaches at least 80%",
        "source_pool_observed_volume": total,
        "selected_observed_volume": sum(r["observed_count"] for r in selected),
        "selected_share_pct": round(100 * sum(r["observed_count"] for r in selected) / total, 3),
        "selected_by_pool": {
            "observed_unbound_query": sum(1 for r in selected if r["source_pool"] == "observed_unbound_query"),
            "yv_excluded_title_routing": sum(1 for r in selected if r["source_pool"] == "yv_excluded_title_routing"),
        },
        "authority_boundary": "selection is behavioral/Pareto only; adjudication is separate and must record provenance explicitly",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
