#!/usr/bin/env python3
"""Measure the deterministic value of canonical taxonomy aliases for current YV/KV.

This is a Track-1 ablation, not semantic retrieval. It consumes the source-attested
should-find cases and the replay of the current selectors, then asks what would
change if an exact normalized canonical alternative/hidden-label lane were checked
before fuzzy matching.

Only non-colliding source-attested cases are decision-bearing. Deprecated/replaced
labels are intentionally excluded: replacement is migration evidence, not synonymy.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any

CANONICAL_PROVENANCE = {"canonical_alternative_label", "canonical_hidden_label"}


def pct(n: int | float, d: int | float) -> float:
    return round(100.0 * n / d, 3) if d else 0.0


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def is_canonical_alias(row: dict[str, Any]) -> bool:
    return bool(CANONICAL_PROVENANCE.intersection(row.get("surface_provenance") or []))


def summarize(rows: list[dict[str, Any]], product: str) -> dict[str, Any]:
    all_rows = [r for r in rows if r.get("product") == product and is_canonical_alias(r)]
    strict = [r for r in all_rows if not r.get("preferred_label_collision")]
    collisions = [r for r in all_rows if r.get("preferred_label_collision")]
    hits = [r for r in strict if r.get("discovery_at_5")]
    misses = [r for r in strict if not r.get("discovery_at_5")]
    no_results = [r for r in strict if r.get("no_results")]

    # The exact canonical alias lane is deterministic for these strict cases because
    # the builder retained only surfaces whose authoritative rows resolve to one
    # target, and the evaluator removed collisions with another current preferred
    # label. The lane changes query evidence only; returned identity/display label
    # remains canonical.
    rescue = misses

    by_provenance: dict[str, dict[str, int | float]] = {}
    for provenance in sorted(CANONICAL_PROVENANCE):
        p_rows = [r for r in strict if provenance in (r.get("surface_provenance") or [])]
        p_miss = [r for r in p_rows if not r.get("discovery_at_5")]
        by_provenance[provenance] = {
            "cases": len(p_rows),
            "current_hit_at_5": len(p_rows) - len(p_miss),
            "current_hit_at_5_pct": pct(len(p_rows) - len(p_miss), len(p_rows)),
            "deterministic_rescue_cases": len(p_miss),
        }

    if product == "YV":
        weight_field = "observed_yv_query_count"
        weight_name = "observed_exact_query_volume"
    else:
        weight_field = "target_occurrence_proxy"
        weight_name = "target_occurrence_proxy"

    total_weight = sum(int(r.get(weight_field) or 0) for r in strict)
    current_hit_weight = sum(int(r.get(weight_field) or 0) for r in hits)
    rescue_weight = sum(int(r.get(weight_field) or 0) for r in rescue)

    top_rescues = sorted(
        rescue,
        key=lambda r: (-int(r.get(weight_field) or 0), str(r.get("query") or "").casefold()),
    )[:30]

    return {
        "canonical_alias_cases_before_preferred_collision_filter": len(all_rows),
        "preferred_label_collision_cases": len(collisions),
        "strict_unique_alias_cases": len(strict),
        "current_hit_at_5": len(hits),
        "current_hit_at_5_pct": pct(len(hits), len(strict)),
        "current_miss_at_5": len(misses),
        "current_no_result_cases": len(no_results),
        "deterministic_exact_alias_rescue_cases": len(rescue),
        "post_alias_hit_at_5_pct_if_lane_precedes_fuzzy": 100.0 if strict else 0.0,
        weight_name: total_weight,
        f"current_{weight_name}_hit_at_5_pct": pct(current_hit_weight, total_weight),
        f"rescued_{weight_name}": rescue_weight,
        f"rescued_{weight_name}_pct": pct(rescue_weight, total_weight),
        "by_provenance": by_provenance,
        "top_rescues": [
            {
                "query": r.get("query"),
                "target": r.get("target"),
                "surface_provenance": r.get("surface_provenance"),
                weight_field: int(r.get(weight_field) or 0),
                "selector_lane": r.get("selector_lane"),
                "no_results": bool(r.get("no_results")),
                "current_top5": r.get("top5"),
            }
            for r in top_rescues
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="artifacts/findability-should-find-v31/cases.jsonl")
    ap.add_argument("--evaluation", default="artifacts/findability-should-find-v31/evaluation.json")
    ap.add_argument("--manifest", default="artifacts/findability-should-find-v31/manifest.json")
    ap.add_argument("--output", default="artifacts/findability-should-find-v31/canonical-alias-rescue.json")
    args = ap.parse_args()

    cases = load_jsonl(Path(args.cases))
    evaluation = json.loads(Path(args.evaluation).read_text(encoding="utf-8"))
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    detail = evaluation.get("cases_detail")
    if not isinstance(detail, list):
        raise RuntimeError("evaluation missing cases_detail")

    # Guard that the evaluation and source reconstruction describe the same packet.
    case_ids = {str(c.get("id")) for c in cases}
    detail_ids = {str(c.get("id")) for c in detail}
    if case_ids != detail_ids:
        raise RuntimeError("cases/evaluation id sets differ")

    result = {
        "schema_version": 1,
        "taxonomy_version": 31,
        "track": "1-current-yv-kv-findability",
        "intervention": "exact normalized canonical alternative/hidden-label lane before fuzzy",
        "authority_boundary": (
            "canonical alternative/hidden labels are query evidence only; returned identity and preferred display label stay canonical. "
            "Deprecated/replaced labels are excluded from this ablation."
        ),
        "source_manifest_alias_surface_collisions": manifest.get("canonical_alias_surface_collisions"),
        "selector_contract": evaluation.get("selector_contract"),
        "YV": summarize(detail, "YV"),
        "KV": summarize(detail, "KV"),
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    compact = {
        "track": result["track"],
        "intervention": result["intervention"],
        "source_manifest_alias_surface_collisions": result["source_manifest_alias_surface_collisions"],
        "YV": {k: v for k, v in result["YV"].items() if k not in {"top_rescues", "by_provenance"}},
        "KV": {k: v for k, v in result["KV"].items() if k not in {"top_rescues", "by_provenance"}},
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
