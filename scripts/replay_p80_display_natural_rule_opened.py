#!/usr/bin/env python3
"""Replay the frozen natural-task display rule on the opened YV stress corpus.

This is diagnostic only. The formula and threshold are loaded from the already-frozen
2023->2024 natural-task calibration and MUST NOT be changed here. Opened rows cannot
select or tune the rule.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_a593_language_diversity_falsifier import load_diverse_training, load_teacher
from evaluate_gemma_a149 import build_ranker
from evaluate_p80_display_lane_calibration import add_teacher
from evaluate_p80_display_natural_task_calibration import (
    EXPECTED_UNIVERSE,
    TAXONOMY_URL,
    conf,
    enrich_features,
)
from evaluate_p80_display_relevance_calibration import candidate_features
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm
from evaluate_pareto_c1 import rank_c1

REGISTRY = Path("research/coverage/source-adapters.json")
TEACHER = Path("research/enrichment/v31/gemma4-yv-a593/phrases.jsonl")
PRIORITY = Path("research/evaluation/v31/p80-track2-priority-coverage.json")
A593_TRAIN = Path("research/training/v31/a593-language-diversity-training-v0.jsonl")
P80_TRAIN = Path("research/training/v31/p80-language-diversity-training-v0.jsonl")
RESCUE_TRAIN = Path("research/training/v31/p80-source-thin-rescue-training-v0.jsonl")
FROZEN_RULE = Path("research/evaluation/v31/p80-display-natural-task-calibration-v0.json")
OPENED = Path("research/evaluation/v31/p80-display-relevance-opened-replay-v0.json")
OUTPUT = Path("research/evaluation/v31/p80-display-natural-rule-opened-replay-v0.json")


def family_match(label: str, expected: list[str]) -> bool:
    nl = norm(label)
    return any(norm(x) in nl or nl in norm(x) for x in expected if norm(x))


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    targetable = [r for r in rows if r["expected"]]
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
            "top1_after": sum(r["family_rank_after"] == 1 for r in targetable),
            "hit5_before": sum(r["family_rank_before"] is not None for r in targetable),
            "hit5_after": sum(r["family_rank_after"] is not None for r in targetable),
            "tail_hits_before": sum(r["family_rank_before"] is not None and r["family_rank_before"] >= 2 for r in targetable),
            "tail_hits_after": sum(r["family_rank_after"] is not None and r["family_rank_after"] >= 2 for r in targetable),
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
    frozen = json.loads(FROZEN_RULE.read_text(encoding="utf-8"))
    formula = str(frozen["selected"]["formula"])
    threshold = float(frozen["selected"]["threshold"])
    if frozen.get("opened_17_88_loaded"):
        raise RuntimeError("frozen rule unexpectedly used opened rows")

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    wire = fetch(TAXONOMY_URL)
    if hashlib.sha256(wire).hexdigest() != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != EXPECTED_UNIVERSE:
        raise RuntimeError("candidate universe drift")

    priority = json.loads(PRIORITY.read_text(encoding="utf-8"))
    existing_ids = {str(r["concept_id"]) for r in priority.get("existing_diversified_v0") or []}
    missing_ids = {str(r["concept_id"]) for r in priority.get("missing_diversified_v0") or []}
    p80_ids = existing_ids | missing_ids
    if len(p80_ids) != 159:
        raise RuntimeError("P80 membership drift")

    _teacher_ids, base_teacher = load_teacher(TEACHER)
    a593_train, _ = load_diverse_training(A593_TRAIN)
    p80_train, _ = load_diverse_training(P80_TRAIN)
    rescue_train, rescue_meta = load_diverse_training(RESCUE_TRAIN)
    if len(rescue_meta) != 22:
        raise RuntimeError("rescue identity drift")

    teacher = {cid: list(v) for cid, v in base_teacher.items()}
    add_teacher(teacher, a593_train, existing_ids)
    add_teacher(teacher, p80_train, missing_ids)
    add_teacher(teacher, rescue_train, p80_ids)
    ranker, exact, surfaces = build_ranker(by_id, ids, teacher)
    phrase_map = {cid: list(v) for cid, v in base_teacher.items()}
    add_teacher(phrase_map, a593_train, existing_ids)
    add_teacher(phrase_map, p80_train, missing_ids)
    add_teacher(phrase_map, rescue_train, p80_ids)

    opened = json.loads(OPENED.read_text(encoding="utf-8"))
    source_rows = opened.get("rows") or []
    if len(source_rows) != 54:
        raise RuntimeError(f"opened stress row drift: {len(source_rows)}")

    rows: list[dict[str, Any]] = []
    for src in source_rows:
        query = str(src["query"])
        expected = [str(x) for x in src.get("expected") or []]
        scored = rank_c1(ranker, query, exact, surfaces)
        candidates = candidate_features(ranker, query, scored)
        enrich_features(ranker, query, candidates, phrase_map)
        before = []
        after = []
        for c in candidates:
            label = str(by_id[c["concept_id"]].get("preferred_label") or c["concept_id"])
            row = {
                "concept_id": c["concept_id"],
                "label": label,
                "original_rank": int(c["rank"]),
                "confidence": round(conf(c, formula), 6),
                "family_match": family_match(label, expected),
            }
            before.append(row)
            if conf(c, formula) >= threshold:
                after.append(row)

        def family_rank(values: list[dict[str, Any]]) -> int | None:
            hit = next((r for r in values if r["family_match"]), None)
            return int(hit["original_rank"]) if hit else None

        rows.append({
            "id": src["id"],
            "category": src["category"],
            "query": query,
            "expected": expected,
            "should_abstain": bool(src.get("should_abstain")),
            "should_clarify": bool(src.get("should_clarify")),
            "before": before,
            "after": after,
            "before_count": len(before),
            "after_count": len(after),
            "family_rank_before": family_rank(before),
            "family_rank_after": family_rank(after),
        })

    by_category = {
        cat: summarize([r for r in rows if r["category"] == cat])
        for cat in sorted({r["category"] for r in rows})
    }
    result = {
        "id": "YV-P80-display-natural-rule-opened-replay-v0",
        "candidate_universe": EXPECTED_UNIVERSE,
        "ranker": "frozen P80 diversified + source-thin rescue A-family ranker",
        "rule": {"formula": formula, "threshold": threshold, "source": str(FROZEN_RULE)},
        "opened_rows_used_to_select_or_tune_rule": False,
        "interpretation_boundary": "Opened stress replay is diagnostic only. Do not change the formula or threshold from these outcomes.",
        "overall": summarize(rows),
        "by_category": by_category,
        "rows": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"rule": result["rule"], "overall": result["overall"], "by_category": by_category}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
