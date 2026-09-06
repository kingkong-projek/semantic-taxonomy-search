#!/usr/bin/env python3
"""Evaluate a deliberately narrow Track-1 fallback for excluded exact YV titles.

Candidate rule (diagnostic only): preserve current product results unchanged unless
an exact generator-excluded title currently exposes no generator-mapped occupation.
Then route only if the ambiguity is bounded by an existing product boundary:
- too_many_parents with exactly 4 mapped occupations (the minimum overflow above
  the generator's >3 exclusion threshold), or
- redundant_label with exactly 1 mapped occupation.

When the rule applies, all mapped occupation identities are treated as explicit
query-only disambiguation destinations; the excluded job-title never becomes a
selectable YV identity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TOTAL_RETAINED_YV_QUERY_VOLUME = 3_136_136_606


def pct(n: int, d: int) -> float:
    return round(100 * n / d, 3) if d else 0.0


def applies(row: dict) -> bool:
    if row["current"]["first_target_rank"] is not None:
        return False
    if row["reason"] == "too_many_parents" and row["target_parent_count"] == 4:
        return True
    if row["reason"] == "redundant_label" and row["target_parent_count"] == 1:
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ranking", required=True)
    ap.add_argument("--output", default="artifacts/yv-minimal-excluded-fallback-v31.json")
    args = ap.parse_args()

    ranking = json.loads(Path(args.ranking).read_text(encoding="utf-8"))
    rows = ranking.get("detail")
    if not isinstance(rows, list) or len(rows) != 205:
        raise RuntimeError(f"expected 205 ranking rows, got {len(rows) if isinstance(rows, list) else 'invalid'}")

    residual = [r for r in rows if r["current"]["first_target_rank"] is None]
    triggered = [r for r in residual if applies(r)]
    remaining = [r for r in residual if not applies(r)]

    total_excluded_volume = sum(int(r["observed_count"]) for r in rows)
    residual_volume = sum(int(r["observed_count"]) for r in residual)
    triggered_volume = sum(int(r["observed_count"]) for r in triggered)
    remaining_volume = sum(int(r["observed_count"]) for r in remaining)
    currently_covered_volume = total_excluded_volume - residual_volume
    candidate_covered_volume = currently_covered_volume + triggered_volume

    if residual_volume != 3_978_003:
        raise RuntimeError(f"unexpected current residual volume {residual_volume}; source/measurement drift")

    result = {
        "schema_version": 1,
        "taxonomy_version": 31,
        "role": "Track-1 counterfactual; query-only excluded-title fallback, not a product change",
        "source": {
            "ranking_workflow_run_id": ranking.get("source", {}).get("workflow_run_id"),
            "ranking_sources": ranking.get("source"),
            "selector_contract": ranking.get("selector_contract"),
        },
        "candidate_rule": {
            "precondition": "exact generator-excluded title and current product result exposes no generator-mapped occupation",
            "too_many_parents": "apply only when mapped occupation count is exactly 4, the minimum overflow above the generator's >3 cutoff",
            "redundant_label": "apply only when mapped occupation count is exactly 1",
            "destination": "allowed occupation-name identities only; excluded job-title remains query vocabulary, never a selectable identity",
            "existing_behavior_preservation": "if current search already exposes a generator-mapped route, do nothing",
        },
        "current_residual": {
            "cases": len(residual),
            "observed_exact_volume": residual_volume,
            "share_of_excluded_exact_volume_pct": pct(residual_volume, total_excluded_volume),
            "share_of_all_retained_yv_query_volume_pct": pct(residual_volume, TOTAL_RETAINED_YV_QUERY_VOLUME),
        },
        "candidate_effect": {
            "triggered_cases": len(triggered),
            "triggered_observed_volume": triggered_volume,
            "share_of_current_residual_volume_rescued_pct": pct(triggered_volume, residual_volume),
            "resulting_weighted_any_parent_top5_pct": pct(candidate_covered_volume, total_excluded_volume),
            "remaining_no_parent_cases": len(remaining),
            "remaining_observed_volume": remaining_volume,
            "remaining_share_of_all_retained_yv_query_volume_pct": pct(remaining_volume, TOTAL_RETAINED_YV_QUERY_VOLUME),
        },
        "triggered_high_volume": [
            {
                "query": r["query"],
                "reason": r["reason"],
                "observed_count": r["observed_count"],
                "mapped_parent_count": r["target_parent_count"],
            }
            for r in sorted(triggered, key=lambda x: -int(x["observed_count"]))[:20]
        ],
        "remaining_high_volume": [
            {
                "query": r["query"],
                "reason": r["reason"],
                "observed_count": r["observed_count"],
                "mapped_parent_count": r["target_parent_count"],
            }
            for r in sorted(remaining, key=lambda x: -int(x["observed_count"]))[:20]
        ],
        "guardrails": [
            "This counterfactual measures reachability only; it does not prove that every mapped occupation is equally intended.",
            "The candidate is deliberately fallback-only, so it does not rerank Säljare, Jurist, Projektledare, Kock, or any other already-grounded current result.",
            "Titles with five or more mapped occupations remain unchanged because the evidence does not justify flattening larger ambiguity sets into ordinary results.",
            "Track 2 semantic/description fallback remains separate and paused.",
        ],
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
