#!/usr/bin/env python3
"""Test SSYK coherence OR symmetric similarity to one coherent evidence unit.

This is a new bounded display-relevance mechanism, not a retune of prior thresholds.
Retrieval/order stay fixed. A visible Top-5 candidate is retained when either it shares
rank-1's SSYK4 group or one *single* source-bound evidence unit (canonical definition or
teacher phrase) is symmetrically similar to the query.

Why: merged BM25 and query-coverage-only phrase checks can reward a candidate for a few
generic query terms while ignoring that most of the candidate evidence unit says
something else. Symmetric TF-IDF cosine/Dice penalize that one-sided overlap.

2023 natural task snippets select formula/threshold with zero baseline Hit@5 loss.
Untouched 2024 is evaluation. Opened stress rows are never loaded here.
"""
from __future__ import annotations

import hashlib
import json
import math
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
    fetch_year_concept,
    wilson,
)
from evaluate_p80_display_relevance_calibration import candidate_features
from evaluate_p80_display_ssyk_phrase_gate import SSYK_HIERARCHY_URL, build_ssyk4_map
from evaluate_p80_lexical_ablation import as_list, expected_hash, fetch, norm, tokens
from evaluate_pareto_c1 import rank_c1

FORMULAS = (
    "unit_tfidf_cosine",
    "ratio_unit_tfidf_cosine",
    "unit_idf_dice",
    "ratio_unit_idf_dice",
)


def evidence_units(by_id: dict[str, dict[str, Any]], cid: str, phrase_map: dict[str, list[str]]) -> list[str]:
    concept = by_id[cid]
    label = str(concept.get("preferred_label") or "").strip()
    definition = str(concept.get("definition") or "").strip()
    units: list[str] = []
    if definition and norm(definition) != norm(label):
        units.append(definition)
    units.extend(str(x).strip() for x in phrase_map.get(cid, []) if str(x).strip())
    # Alternative labels are identity surfaces, not task descriptions; do not inflate
    # free-text relevance with short title-like units.
    return units


def best_unit_similarity(ranker, query: str, units: list[str]) -> dict[str, float | int]:
    q = set(tokens(query))
    if not q or not units:
        return {"unit_tfidf_cosine": 0.0, "unit_idf_dice": 0.0, "unit_shared_count": 0}
    max_idf = max(ranker.idf.values(), default=1.0)
    q_weight = {t: float(ranker.idf.get(t, max_idf)) for t in q}
    q_norm = math.sqrt(sum(w * w for w in q_weight.values())) or 1.0
    q_mass = sum(q_weight.values()) or 1.0
    best = (0.0, 0.0, 0)
    for unit in units:
        u = set(tokens(unit))
        if not u:
            continue
        u_weight = {t: float(ranker.idf.get(t, max_idf)) for t in u}
        u_norm = math.sqrt(sum(w * w for w in u_weight.values())) or 1.0
        u_mass = sum(u_weight.values()) or 1.0
        shared = q & u
        dot = sum(q_weight[t] * u_weight[t] for t in shared)
        cosine = dot / (q_norm * u_norm)
        shared_mass = sum(q_weight[t] for t in shared)
        dice = 2.0 * shared_mass / (q_mass + u_mass)
        candidate = (cosine, dice, len(shared))
        if candidate > best:
            best = candidate
    return {
        "unit_tfidf_cosine": best[0],
        "unit_idf_dice": best[1],
        "unit_shared_count": best[2],
    }


def confidence(c: dict[str, Any], formula: str) -> float:
    ratio = float(c["score_ratio"])
    if formula == "unit_tfidf_cosine":
        return float(c["unit_tfidf_cosine"])
    if formula == "ratio_unit_tfidf_cosine":
        return ratio * float(c["unit_tfidf_cosine"])
    if formula == "unit_idf_dice":
        return float(c["unit_idf_dice"])
    if formula == "ratio_unit_idf_dice":
        return ratio * float(c["unit_idf_dice"])
    raise ValueError(formula)


def annotate(candidates: list[dict[str, Any]], ssyk4: dict[str, str]) -> None:
    if not candidates:
        return
    top = str(candidates[0]["concept_id"])
    top_code = ssyk4[top]
    for c in candidates:
        cid = str(c["concept_id"])
        c["ssyk_code_2012"] = ssyk4[cid]
        c["same_ssyk_as_top1"] = bool(cid == top or ssyk4[cid] == top_code)


def retained(c: dict[str, Any], formula: str, threshold: float) -> bool:
    return bool(c["same_ssyk_as_top1"] or confidence(c, formula) >= threshold)


def summarize(rows: list[dict[str, Any]], ssyk4: dict[str, str], formula: str, threshold: float) -> dict[str, Any]:
    bh = rh = bt = rt = before = after = nt_before = nt_after = cross_before = cross_after = zero = 0
    by_rank = {i: [0, 0] for i in range(1, 6)}
    for row in rows:
        target = str(row["concept_id"])
        target_code = ssyk4[target]
        cs = row["candidates"]
        before += len(cs)
        target_row = next((c for c in cs if str(c["concept_id"]) == target), None)
        if target_row:
            bh += 1
            rank = int(target_row["rank"])
            by_rank[rank][0] += 1
            bt += int(rank >= 2)
        kept = [c for c in cs if retained(c, formula, threshold)]
        after += len(kept)
        zero += int(not kept)
        for c in cs:
            cid = str(c["concept_id"])
            if cid == target:
                continue
            nt_before += 1
            cross_before += int(ssyk4[cid] != target_code)
        for c in kept:
            cid = str(c["concept_id"])
            if cid == target:
                continue
            nt_after += 1
            cross_after += int(ssyk4[cid] != target_code)
        if target_row and target_row in kept:
            rh += 1
            rank = int(target_row["rank"])
            by_rank[rank][1] += 1
            rt += int(rank >= 2)
    n = len(rows)
    return {
        "queries": n,
        "baseline_hit5": bh,
        "retained_hit5": rh,
        "hit5_retention": round(rh / max(1, bh), 6),
        "hit5_retention_wilson95": wilson(rh, bh),
        "baseline_tail_hits_rank2_5": bt,
        "retained_tail_hits_rank2_5": rt,
        "tail_hit_retention": round(rt / max(1, bt), 6),
        "tail_hit_retention_wilson95": wilson(rt, bt),
        "mean_displayed_before": round(before / max(1, n), 6),
        "mean_displayed_after": round(after / max(1, n), 6),
        "non_target_reduction": round(1 - nt_after / max(1, nt_before), 6),
        "cross_ssyk_non_target_before": cross_before,
        "cross_ssyk_non_target_after": cross_after,
        "cross_ssyk_non_target_reduction": round(1 - cross_after / max(1, cross_before), 6),
        "zero_result_rate_after": round(zero / max(1, n), 6),
        "rank_retention": {
            str(rank): {"baseline": v[0], "retained": v[1], "rate": round(v[1] / max(1, v[0]), 6)}
            for rank, v in by_rank.items()
        },
    }


def choose_zero_loss(calibration: list[dict[str, Any]], ssyk4: dict[str, str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    options = []
    for formula in FORMULAS:
        required = []
        for row in calibration:
            target = str(row["concept_id"])
            tr = next((c for c in row["candidates"] if str(c["concept_id"]) == target), None)
            if tr and not tr["same_ssyk_as_top1"]:
                required.append(confidence(tr, formula))
        if not required:
            continue
        threshold = min(required)
        metrics = summarize(calibration, ssyk4, formula, threshold)
        if metrics["retained_hit5"] != metrics["baseline_hit5"]:
            raise RuntimeError(f"zero-loss invariant failed for {formula}")
        options.append({"formula": formula, "threshold": threshold, "calibration": metrics})
    if not options:
        raise RuntimeError("no coherent-unit rule")
    options.sort(key=lambda x: (
        x["calibration"]["mean_displayed_after"],
        -x["calibration"]["cross_ssyk_non_target_reduction"],
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

    ssyk_wire = fetch(SSYK_HIERARCHY_URL)
    ssyk4 = build_ssyk4_map(json.loads(ssyk_wire))
    if set(ssyk4) != set(ids):
        raise RuntimeError("SSYK hierarchy coverage drift")

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
    primary = sorted(p80 - rescue_ids)

    teacher = {cid: list(v) for cid, v in base.items()}
    add_teacher(teacher, a593, existing)
    add_teacher(teacher, p80t, missing)
    add_teacher(teacher, rescue, p80)
    ranker, exact, surfaces = build_ranker(by_id, ids, teacher)

    phrase_map = {cid: list(v) for cid, v in base.items()}
    add_teacher(phrase_map, a593, existing)
    add_teacher(phrase_map, p80t, missing)
    add_teacher(phrase_map, rescue, p80)
    unit_map = {cid: evidence_units(by_id, cid, phrase_map) for cid in ids}

    groups = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        fs = {
            pool.submit(fetch_year_concept, cid, by_id[cid], year, search_limit=25, accepted=5): (cid, year)
            for cid in primary for year in (CAL_YEAR, EVAL_YEAR)
        }
        for f in as_completed(fs):
            groups.append(f.result())

    rows = []
    for case in [r for g in groups for r in g["accepted"]]:
        scored = rank_c1(ranker, case["query"], exact, surfaces)
        cs = candidate_features(ranker, case["query"], scored)
        annotate(cs, ssyk4)
        for c in cs:
            c.update(best_unit_similarity(ranker, case["query"], unit_map[str(c["concept_id"])]))
        rows.append({**case, "candidates": cs})

    cal = [r for r in rows if r["year"] == CAL_YEAR]
    ev = [r for r in rows if r["year"] == EVAL_YEAR]
    selected, frontier = choose_zero_loss(cal, ssyk4)
    metrics = summarize(ev, ssyk4, selected["formula"], float(selected["threshold"]))
    strong = metrics["hit5_retention"] >= 0.98 and metrics["tail_hit_retention"] >= 0.98 and metrics["cross_ssyk_non_target_reduction"] >= 0.25
    promising = metrics["hit5_retention"] >= 0.95 and metrics["tail_hit_retention"] >= 0.95 and metrics["cross_ssyk_non_target_reduction"] >= 0.40

    result = {
        "id": "YV-P80-display-ssyk-unit-similarity-v0",
        "evidence_class": "natural historical Platsbanken task-text proxy; structured target and SSYK4 proxy, not human relevance judgment",
        "candidate_universe": EXPECTED_UNIVERSE,
        "ranker_changed": False,
        "opened_17_88_loaded": False,
        "mechanism": "same SSYK4 as rank1 OR symmetric TF-IDF similarity to one canonical-definition/teacher-phrase evidence unit",
        "selection_contract": "2023 zero baseline-Hit@5 loss; choose smallest visible list among frozen symmetric-similarity formulas",
        "sample": {"calibration_queries": len(cal), "evaluation_queries": len(ev), "calibration_concepts": len({r['concept_id'] for r in cal}), "evaluation_concepts": len({r['concept_id'] for r in ev})},
        "selected": selected,
        "calibration_frontier": frontier,
        "evaluation": metrics,
        "decision_gate": {
            "strong": "2024 Hit@5 >=98%, rank2-5 >=98%, cross-SSYK non-target reduction >=25%",
            "promising": "2024 Hit@5 >=95%, rank2-5 >=95%, cross-SSYK non-target reduction >=40%",
            "strong_passed": strong,
            "promising_passed": promising,
            "if_strong_or_promising": "freeze unchanged and replay opened stress diagnostically",
            "if_neither": "reject coherent-unit gate without retuning on opened data",
        },
        "interpretation_boundary": "Cross-SSYK is a conservative relevance proxy. The later opened replay may falsify transfer but may not alter this rule.",
    }
    out = Path("research/evaluation/v31/p80-display-ssyk-unit-similarity-v0.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
