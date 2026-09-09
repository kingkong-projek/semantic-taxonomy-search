#!/usr/bin/env python3
"""Replay the frozen Top-5 linear relevance model on opened user-style stress rows.

Diagnostic only. Model weights, feature contract and threshold are loaded from the
already-frozen 2023->2024 result and MUST NOT be refit or retuned here.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from audit_p80_display_precision import family_rank
from evaluate_a593_language_diversity_falsifier import load_diverse_training, load_teacher
from evaluate_gemma_a149 import build_ranker
from evaluate_p80_display_lane_calibration import add_teacher
from evaluate_p80_display_linear_relevance import FEATURES, annotate_features, keep, probability
from evaluate_p80_display_ssyk_phrase_gate import SSYK_HIERARCHY_URL, build_ssyk4_map
from evaluate_p80_display_ssyk_unit_similarity import evidence_units
from evaluate_p80_display_relevance_calibration import candidate_features
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm
from evaluate_pareto_c1 import rank_c1

TAXONOMY_URL = (
    "https://data.jobtechdev.se/taxonomy/version/31/query/"
    "concepts-and-common-relations/concepts-and-common-relations.json"
)
EXPECTED_UNIVERSE = 2105
EXPECTED_RULE_ID = "YV-P80-display-linear-relevance-v0"


def displayed_family_rank(kept: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], expected: list[str]) -> tuple[int | None, int | None]:
    needles = [norm(x) for x in expected if norm(x)]
    if not needles:
        return None, None
    for display_rank, c in enumerate(kept, 1):
        label = norm(by_id[str(c["concept_id"])].get("preferred_label"))
        if any(needle in label for needle in needles):
            return display_rank, int(c["rank"])
    return None, None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    targetable = [r for r in rows if r["expected"] and not r["should_abstain"]]
    abstain = [r for r in rows if r["should_abstain"]]
    clarify = [r for r in rows if r["should_clarify"]]
    return {
        "cases": len(rows),
        "mean_displayed_before": round(sum(r["before_count"] for r in rows) / max(1, len(rows)), 3),
        "mean_displayed_after": round(sum(r["after_count"] for r in rows) / max(1, len(rows)), 3),
        "full_five_before": sum(r["before_count"] == 5 for r in rows),
        "full_five_after": sum(r["after_count"] == 5 for r in rows),
        "targetable": {
            "cases": len(targetable),
            "top1_before": sum(r["family_rank_before"] == 1 for r in targetable),
            "top1_after": sum(r["family_original_rank_after"] == 1 for r in targetable),
            "hit5_before": sum(r["family_rank_before"] is not None and r["family_rank_before"] <= 5 for r in targetable),
            "hit5_after": sum(r["family_display_rank_after"] is not None for r in targetable),
            "tail_hits_before": sum(r["family_rank_before"] is not None and 2 <= r["family_rank_before"] <= 5 for r in targetable),
            "tail_hits_after": sum(r["family_original_rank_after"] is not None and 2 <= r["family_original_rank_after"] <= 5 for r in targetable),
        },
        "explicit_abstention": {
            "cases": len(abstain),
            "empty_before": sum(r["before_count"] == 0 for r in abstain),
            "empty_after": sum(r["after_count"] == 0 for r in abstain),
            "full_five_before": sum(r["before_count"] == 5 for r in abstain),
            "full_five_after": sum(r["after_count"] == 5 for r in abstain),
        },
        "clarification": {
            "cases": len(clarify),
            "mean_displayed_before": round(sum(r["before_count"] for r in clarify) / max(1, len(clarify)), 3),
            "mean_displayed_after": round(sum(r["after_count"] for r in clarify) / max(1, len(clarify)), 3),
        },
    }


def main() -> int:
    registry = json.loads(Path("research/coverage/source-adapters.json").read_text(encoding="utf-8"))
    wire = fetch(TAXONOMY_URL)
    if hashlib.sha256(wire).hexdigest() != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != EXPECTED_UNIVERSE:
        raise RuntimeError("candidate universe drift")

    ssyk_wire = fetch(SSYK_HIERARCHY_URL)
    ssyk4 = build_ssyk4_map(json.loads(ssyk_wire))
    if set(ssyk4) != set(ids):
        raise RuntimeError("SSYK4 hierarchy coverage drift")

    frozen = json.loads(Path("research/evaluation/v31/p80-display-linear-relevance-v0.json").read_text(encoding="utf-8"))
    if frozen.get("id") != EXPECTED_RULE_ID:
        raise RuntimeError("frozen rule id drift")
    if frozen.get("feature_contract", {}).get("features") != list(FEATURES):
        raise RuntimeError("frozen feature contract drift")
    model = frozen.get("model") or {}
    if model.get("features") != list(FEATURES):
        raise RuntimeError("frozen model feature drift")
    threshold = float(frozen.get("display_rule", {}).get("threshold"))
    if not (0.0 < threshold < 1.0):
        raise RuntimeError("invalid frozen threshold")
    if not frozen.get("decision_gate", {}).get("strong_passed"):
        raise RuntimeError("frozen model did not pass strong 2024 gate")

    priority = json.loads(Path("research/evaluation/v31/p80-track2-priority-coverage.json").read_text(encoding="utf-8"))
    existing = {str(r["concept_id"]) for r in priority.get("existing_diversified_v0") or []}
    missing = {str(r["concept_id"]) for r in priority.get("missing_diversified_v0") or []}
    p80_ids = existing | missing
    if len(p80_ids) != 159:
        raise RuntimeError("P80 drift")

    _teacher_ids, base = load_teacher(Path("research/enrichment/v31/gemma4-yv-a593/phrases.jsonl"))
    a593, _ = load_diverse_training(Path("research/training/v31/a593-language-diversity-training-v0.jsonl"))
    p80, _ = load_diverse_training(Path("research/training/v31/p80-language-diversity-training-v0.jsonl"))
    rescue, rescue_meta = load_diverse_training(Path("research/training/v31/p80-source-thin-rescue-training-v0.jsonl"))
    if len(rescue_meta) != 22:
        raise RuntimeError("rescue metadata drift")

    teacher = {cid: list(values) for cid, values in base.items()}
    add_teacher(teacher, a593, existing)
    add_teacher(teacher, p80, missing)
    add_teacher(teacher, rescue, p80_ids)
    ranker, exact, surfaces = build_ranker(by_id, ids, teacher)

    phrase_map = {cid: list(values) for cid, values in base.items()}
    add_teacher(phrase_map, a593, existing)
    add_teacher(phrase_map, p80, missing)
    add_teacher(phrase_map, rescue, p80_ids)
    unit_map = {cid: evidence_units(by_id, cid, phrase_map) for cid in ids}

    stress = json.loads(Path("research/evaluation/v31/opened-live-semantic-stress-v1.json").read_text(encoding="utf-8"))
    cases = stress.get("yv") or []
    if len(cases) != 54:
        raise RuntimeError("opened YV stress drift")

    rows: list[dict[str, Any]] = []
    for case in cases:
        query = str(case["query"])
        scored = rank_c1(ranker, query, exact, surfaces)
        before = scored[:5]
        candidates = candidate_features(ranker, query, scored)
        annotate_features(ranker, query, candidates, by_id, ssyk4, phrase_map, unit_map)
        kept = [c for c in candidates if keep(c, model, threshold)]

        expected = [str(x) for x in case.get("expect") or []]
        rank_before = family_rank(scored, by_id, expected)
        display_after, original_after = displayed_family_rank(kept, by_id, expected)

        def render(c: dict[str, Any]) -> dict[str, Any]:
            cid = str(c["concept_id"])
            return {
                "original_rank": int(c["rank"]),
                "concept_id": cid,
                "label": str(by_id[cid].get("preferred_label") or cid),
                "ssyk_code_2012": ssyk4[cid],
                "same_ssyk_as_top1": bool(c["same_ssyk_as_top1"]),
                "score_ratio": round(float(c["score_ratio"]), 6),
                "probability": round(probability(c, model), 6),
            }

        rows.append({
            "id": str(case["id"]),
            "category": str(case["category"]),
            "query": query,
            "expected": expected,
            "should_abstain": bool(case.get("should_abstain")),
            "should_clarify": bool(case.get("should_clarify")),
            "family_rank_before": rank_before,
            "family_display_rank_after": display_after,
            "family_original_rank_after": original_after,
            "before_count": len(before),
            "after_count": len(kept),
            "before": [render(c) for c in candidates],
            "after": [render(c) for c in kept],
        })

    by_category: dict[str, Any] = {}
    for category in sorted({r["category"] for r in rows}):
        subset = [r for r in rows if r["category"] == category]
        by_category[category] = summarize(subset)

    result = {
        "id": "YV-P80-display-linear-relevance-opened-replay-v0",
        "status": "opened diagnostic only; frozen model and threshold replayed without refit or retuning",
        "opened_rows_used_to_fit_calibrate_or_tune": False,
        "candidate_universe": EXPECTED_UNIVERSE,
        "frozen_source": "research/evaluation/v31/p80-display-linear-relevance-v0.json",
        "frozen_threshold": threshold,
        "frozen_model": model,
        "overall": summarize(rows),
        "by_category": by_category,
        "spot_checks": {r["id"]: r for r in rows if r["id"] in {"yv01", "yv02"}},
        "rows": rows,
        "interpretation_boundary": "This opened replay can falsify transfer and expose qualitative failures. It cannot retune the model/threshold or establish human relevance precision.",
    }
    out = Path("research/evaluation/v31/p80-display-linear-relevance-opened-replay-v0.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": result["overall"], "spot_checks": result["spot_checks"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
