#!/usr/bin/env python3
"""Test one simple Top-5 relevance gate: SSYK coherence OR single-phrase support.

Retrieval and ranking remain unchanged. The hypothesis is that many embarrassing visible
false positives are cross-occupation-family candidates whose merged BM25 document gets
support from words scattered across several teacher phrases. A candidate is therefore
kept when either:

1. it shares the structured SSYK-2012 code of rank 1, or
2. one single source-bound teacher phrase gives sufficiently strong query support.

The threshold/formula is selected only on 2023 historical Platsbanken task snippets with
zero loss of baseline Hit@5 targets. The selected rule is frozen and evaluated untouched
on 2024. Opened stress rows are never loaded here.

Cross-SSYK non-target reduction is only a relevance proxy: another SSYK candidate can
still be useful to a person. It is deliberately safer than treating every non-target
candidate as irrelevant.
"""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from evaluate_a593_language_diversity_falsifier import load_diverse_training, load_teacher
from evaluate_gemma_a149 import build_ranker
from evaluate_p80_display_lane_calibration import add_teacher
from evaluate_p80_display_natural_task_calibration import (
    CAL_YEAR,
    EVAL_YEAR,
    EXPECTED_UNIVERSE,
    TAXONOMY_URL,
    enrich_features,
    fetch_year_concept,
    wilson,
)
from evaluate_p80_display_relevance_calibration import candidate_features
from evaluate_p80_lexical_ablation import expected_hash, fetch
from evaluate_pareto_c1 import rank_c1

FORMULAS = (
    "phrase_idf_mass",
    "ratio_phrase_idf_mass",
    "phrase_shared_count",
    "ratio_phrase_shared_count",
)


def ssyk_code(concept: dict[str, Any]) -> str:
    value = concept.get("ssyk_code_2012")
    return str(value).strip() if value is not None else ""


def confidence(c: dict[str, Any], formula: str) -> float:
    ratio = float(c["score_ratio"])
    if formula == "phrase_idf_mass":
        return float(c["phrase_idf_mass"])
    if formula == "ratio_phrase_idf_mass":
        return ratio * float(c["phrase_idf_mass"])
    if formula == "phrase_shared_count":
        return float(c["phrase_shared_count"])
    if formula == "ratio_phrase_shared_count":
        return ratio * float(c["phrase_shared_count"])
    raise ValueError(formula)


def annotate_family(candidates: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]) -> None:
    if not candidates:
        return
    top_id = str(candidates[0]["concept_id"])
    top_code = ssyk_code(by_id[top_id])
    for c in candidates:
        cid = str(c["concept_id"])
        code = ssyk_code(by_id[cid])
        c["ssyk_code_2012"] = code
        # Rank 1 is always retained. Missing taxonomy codes never create accidental groups.
        c["same_ssyk_as_top1"] = bool(cid == top_id or (top_code and code and code == top_code))


def retained(c: dict[str, Any], formula: str, threshold: float) -> bool:
    return bool(c["same_ssyk_as_top1"] or confidence(c, formula) >= threshold)


def summarize(
    rows: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    formula: str,
    threshold: float,
) -> dict[str, Any]:
    baseline_hits = retained_hits = baseline_tail = retained_tail = 0
    before = after = non_target_before = non_target_after = 0
    cross_before = cross_after = zero = 0
    by_rank = {i: [0, 0] for i in range(1, 6)}

    for row in rows:
        target = str(row["concept_id"])
        target_code = ssyk_code(by_id[target])
        cs = row["candidates"]
        before += len(cs)
        target_row = next((c for c in cs if str(c["concept_id"]) == target), None)
        if target_row:
            baseline_hits += 1
            rank = int(target_row["rank"])
            by_rank[rank][0] += 1
            if rank >= 2:
                baseline_tail += 1

        kept = [c for c in cs if retained(c, formula, threshold)]
        after += len(kept)
        zero += int(not kept)

        for c in cs:
            cid = str(c["concept_id"])
            if cid == target:
                continue
            non_target_before += 1
            code = ssyk_code(by_id[cid])
            if target_code and code and code != target_code:
                cross_before += 1
        for c in kept:
            cid = str(c["concept_id"])
            if cid == target:
                continue
            non_target_after += 1
            code = ssyk_code(by_id[cid])
            if target_code and code and code != target_code:
                cross_after += 1

        if target_row and target_row in kept:
            retained_hits += 1
            rank = int(target_row["rank"])
            by_rank[rank][1] += 1
            if rank >= 2:
                retained_tail += 1

    n = len(rows)
    return {
        "queries": n,
        "baseline_hit5": baseline_hits,
        "retained_hit5": retained_hits,
        "hit5_retention": round(retained_hits / max(1, baseline_hits), 6),
        "hit5_retention_wilson95": wilson(retained_hits, baseline_hits),
        "baseline_tail_hits_rank2_5": baseline_tail,
        "retained_tail_hits_rank2_5": retained_tail,
        "tail_hit_retention": round(retained_tail / max(1, baseline_tail), 6),
        "tail_hit_retention_wilson95": wilson(retained_tail, baseline_tail),
        "mean_displayed_before": round(before / max(1, n), 6),
        "mean_displayed_after": round(after / max(1, n), 6),
        "non_target_reduction": round(1 - non_target_after / max(1, non_target_before), 6),
        "cross_ssyk_non_target_before": cross_before,
        "cross_ssyk_non_target_after": cross_after,
        "cross_ssyk_non_target_reduction": round(1 - cross_after / max(1, cross_before), 6),
        "zero_result_rate_after": round(zero / max(1, n), 6),
        "rank_retention": {
            str(rank): {
                "baseline": values[0],
                "retained": values[1],
                "rate": round(values[1] / max(1, values[0]), 6),
            }
            for rank, values in by_rank.items()
        },
    }


def choose_zero_loss(
    calibration: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    options: list[dict[str, Any]] = []
    for formula in FORMULAS:
        required = []
        for row in calibration:
            target = str(row["concept_id"])
            target_row = next((c for c in row["candidates"] if str(c["concept_id"]) == target), None)
            if target_row and not target_row["same_ssyk_as_top1"]:
                required.append(confidence(target_row, formula))
        # If all calibration targets are protected by the top-1 SSYK family, an infinite
        # threshold would be valid but would not test phrase rescue. Skip that degenerate case.
        if not required:
            continue
        threshold = min(required)
        metrics = summarize(calibration, by_id, formula, threshold)
        if metrics["retained_hit5"] != metrics["baseline_hit5"]:
            raise RuntimeError(f"zero-loss selection invariant failed for {formula}")
        options.append({"formula": formula, "threshold": threshold, "calibration": metrics})

    if not options:
        raise RuntimeError("no SSYK+phrase rule available")
    options.sort(key=lambda x: (
        x["calibration"]["mean_displayed_after"],
        -x["calibration"]["cross_ssyk_non_target_reduction"],
        -x["calibration"]["non_target_reduction"],
        x["formula"],
    ))
    return options[0], options


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

    with_ssyk = sum(bool(ssyk_code(by_id[cid])) for cid in ids)

    priority = json.loads(Path("research/evaluation/v31/p80-track2-priority-coverage.json").read_text(encoding="utf-8"))
    existing = {str(r["concept_id"]) for r in priority.get("existing_diversified_v0") or []}
    missing = {str(r["concept_id"]) for r in priority.get("missing_diversified_v0") or []}
    p80 = existing | missing
    if len(p80) != 159:
        raise RuntimeError("P80 drift")

    _teacher_ids, base = load_teacher(Path("research/enrichment/v31/gemma4-yv-a593/phrases.jsonl"))
    a593, _ = load_diverse_training(Path("research/training/v31/a593-language-diversity-training-v0.jsonl"))
    p80t, _ = load_diverse_training(Path("research/training/v31/p80-language-diversity-training-v0.jsonl"))
    rescue, rescue_meta = load_diverse_training(Path("research/training/v31/p80-source-thin-rescue-training-v0.jsonl"))
    rescue_ids = set(rescue_meta)
    if len(rescue_ids) != 22:
        raise RuntimeError("rescue identity drift")
    primary_ids = sorted(p80 - rescue_ids)

    teacher = {cid: list(values) for cid, values in base.items()}
    add_teacher(teacher, a593, existing)
    add_teacher(teacher, p80t, missing)
    add_teacher(teacher, rescue, p80)
    ranker, exact, surfaces = build_ranker(by_id, ids, teacher)

    phrase_map = {cid: list(values) for cid, values in base.items()}
    add_teacher(phrase_map, a593, existing)
    add_teacher(phrase_map, p80t, missing)
    add_teacher(phrase_map, rescue, p80)

    groups = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(fetch_year_concept, cid, by_id[cid], year, search_limit=25, accepted=5): (cid, year)
            for cid in primary_ids for year in (CAL_YEAR, EVAL_YEAR)
        }
        for fut in as_completed(futures):
            groups.append(fut.result())

    cases = [row for group in groups for row in group["accepted"]]
    rows = []
    for case in cases:
        scored = rank_c1(ranker, case["query"], exact, surfaces)
        candidates = candidate_features(ranker, case["query"], scored)
        enrich_features(ranker, case["query"], candidates, phrase_map)
        annotate_family(candidates, by_id)
        rows.append({**case, "candidates": candidates})

    calibration = [row for row in rows if row["year"] == CAL_YEAR]
    evaluation = [row for row in rows if row["year"] == EVAL_YEAR]
    selected, frontier = choose_zero_loss(calibration, by_id)
    evaluation_metrics = summarize(evaluation, by_id, selected["formula"], float(selected["threshold"]))

    strong = (
        evaluation_metrics["hit5_retention"] >= 0.98
        and evaluation_metrics["tail_hit_retention"] >= 0.98
        and evaluation_metrics["cross_ssyk_non_target_reduction"] >= 0.25
    )
    promising = (
        evaluation_metrics["hit5_retention"] >= 0.95
        and evaluation_metrics["tail_hit_retention"] >= 0.95
        and evaluation_metrics["cross_ssyk_non_target_reduction"] >= 0.40
    )

    result = {
        "id": "YV-P80-display-ssyk-phrase-gate-v0",
        "evidence_class": "natural historical Platsbanken task-text proxy; structured target and taxonomy SSYK family, not human relevance judgment",
        "candidate_universe": EXPECTED_UNIVERSE,
        "occupation_names_with_ssyk_code_2012": with_ssyk,
        "ranker_changed": False,
        "opened_17_88_loaded": False,
        "signal": "retain Top-5 candidate when same SSYK-2012 as rank1 OR strong best-single-teacher-phrase support",
        "selection_contract": "2023 zero baseline-Hit@5 target loss; among frozen phrase formulas minimize visible candidates",
        "sample": {
            "calibration_queries": len(calibration),
            "evaluation_queries": len(evaluation),
            "calibration_concepts": len({r["concept_id"] for r in calibration}),
            "evaluation_concepts": len({r["concept_id"] for r in evaluation}),
            "rescue_source-overlap_ids_excluded": len(rescue_ids),
        },
        "selected": selected,
        "calibration_frontier": frontier,
        "evaluation": evaluation_metrics,
        "decision_gate": {
            "strong": "2024 Hit@5 retention >=98%, rank2-5 retention >=98%, cross-SSYK non-target reduction >=25%",
            "promising": "2024 Hit@5 retention >=95%, rank2-5 retention >=95%, cross-SSYK non-target reduction >=40%",
            "strong_passed": strong,
            "promising_passed": promising,
            "if_strong_or_promising": "freeze unchanged and replay opened stress diagnostically",
            "if_neither": "reject this simple family+phrase display gate; do not threshold-tune it further",
        },
        "interpretation_boundary": "Different SSYK is a conservative proxy for likely irrelevance, not a human relevance label. Same-SSYK alternatives are intentionally not counted as false suggestions.",
    }
    out = Path("research/evaluation/v31/p80-display-ssyk-phrase-gate-v0.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
