#!/usr/bin/env python3
"""Replay the independently selected P80 display rule on opened YV stress rows.

The rule MUST already exist in p80-display-relevance-calibration-v0.json. This script
never selects or modifies it. Opened 17/88 rows remain diagnostic only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from audit_p80_display_precision import TAXONOMY_URL, add_teacher
from evaluate_a593_language_diversity_falsifier import load_diverse_training, load_teacher
from evaluate_gemma_a149 import build_ranker
from evaluate_p80_display_relevance_calibration import candidate_features, keep_candidate
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm
from evaluate_pareto_c1 import rank_c1


def matches_expected(cid: str, by_id: dict[str, dict[str, Any]], expected: list[str]) -> bool:
    label = norm(by_id[cid].get("preferred_label"))
    return any(norm(x) and norm(x) in label for x in expected)


def visible_family_rank(candidates: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], expected: list[str]) -> int | None:
    for i, c in enumerate(candidates, 1):
        if matches_expected(str(c["concept_id"]), by_id, expected):
            return i
    return None


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
            "hit5_before": sum(r["family_rank_before"] is not None for r in targetable),
            "hit5_after": sum(r["family_rank_after"] is not None for r in targetable),
            "top1_before": sum(r["family_rank_before"] == 1 for r in targetable),
            "top1_after": sum(r["family_rank_after"] == 1 for r in targetable),
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--teacher", default="research/enrichment/v31/gemma4-yv-a593/phrases.jsonl")
    ap.add_argument("--priority", default="research/evaluation/v31/p80-track2-priority-coverage.json")
    ap.add_argument("--a593-diverse", default="research/training/v31/a593-language-diversity-training-v0.jsonl")
    ap.add_argument("--p80-diverse", default="research/training/v31/p80-language-diversity-training-v0.jsonl")
    ap.add_argument("--rescue", default="research/training/v31/p80-source-thin-rescue-training-v0.jsonl")
    ap.add_argument("--calibration", default="research/evaluation/v31/p80-display-relevance-calibration-v0.json")
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--output", default="research/evaluation/v31/p80-display-relevance-opened-replay-v0.json")
    args = ap.parse_args()

    calibration = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
    if not calibration.get("decision_gate", {}).get("passed"):
        raise RuntimeError("display calibration gate did not pass")
    rule = calibration.get("selected_rule") or {}

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    wire = fetch(TAXONOMY_URL)
    if hashlib.sha256(wire).hexdigest() != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != 2105:
        raise RuntimeError("candidate universe drift")

    priority = json.loads(Path(args.priority).read_text(encoding="utf-8"))
    existing_ids = {str(r["concept_id"]) for r in priority.get("existing_diversified_v0") or []}
    missing_ids = {str(r["concept_id"]) for r in priority.get("missing_diversified_v0") or []}
    p80_ids = existing_ids | missing_ids
    if len(p80_ids) != 159:
        raise RuntimeError("P80 membership drift")

    _teacher_ids, base_teacher = load_teacher(Path(args.teacher))
    a593, _ = load_diverse_training(Path(args.a593_diverse))
    p80, _ = load_diverse_training(Path(args.p80_diverse))
    rescue, rescue_meta = load_diverse_training(Path(args.rescue))
    if len(rescue_meta) != 22:
        raise RuntimeError("rescue metadata drift")
    teacher = {cid: list(v) for cid, v in base_teacher.items()}
    add_teacher(teacher, a593, existing_ids)
    add_teacher(teacher, p80, missing_ids)
    add_teacher(teacher, rescue, p80_ids)
    ranker, exact, surfaces = build_ranker(by_id, ids, teacher)

    stress = json.loads(Path(args.stress).read_text(encoding="utf-8"))
    rows = []
    for case in stress.get("yv") or []:
        query = str(case["query"])
        scored = rank_c1(ranker, query, exact, surfaces)
        before = candidate_features(ranker, query, scored)
        after = [c for c in before if keep_candidate(c, rule)]
        expected = [str(x) for x in case.get("expect") or []]
        rows.append({
            "id": case["id"],
            "category": case["category"],
            "query": query,
            "expected": expected,
            "should_abstain": bool(case.get("should_abstain")),
            "should_clarify": bool(case.get("should_clarify")),
            "before_count": len(before),
            "after_count": len(after),
            "family_rank_before": visible_family_rank(before, by_id, expected),
            "family_rank_after": visible_family_rank(after, by_id, expected),
            "before": [{"rank": c["rank"], "label": str(by_id[c["concept_id"]].get("preferred_label") or c["concept_id"]), "score_ratio": round(c["score_ratio"], 4), "token_coverage": round(c["token_coverage"], 4), "idf_coverage": round(c["idf_coverage"], 4), "shared_count": c["shared_count"]} for c in before],
            "after": [{"original_rank": c["rank"], "label": str(by_id[c["concept_id"]].get("preferred_label") or c["concept_id"])} for c in after],
        })

    by_category = {}
    for category in sorted({r["category"] for r in rows}):
        by_category[category] = summarize([r for r in rows if r["category"] == category])
    result = {
        "id": "YV-P80-display-relevance-opened-replay-v0",
        "status": "opened diagnostic replay only; frozen display rule selected without these rows",
        "opened_rows_used_to_select_rule": False,
        "rule_source": "research/evaluation/v31/p80-display-relevance-calibration-v0.json",
        "selected_rule": rule,
        "overall": summarize(rows),
        "by_category": by_category,
        "rows": rows,
        "interpretation_boundary": "This can diagnose transfer shape and obvious fail-open behavior but cannot promote the rule as human relevance truth.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": result["overall"], "by_category": result["by_category"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
