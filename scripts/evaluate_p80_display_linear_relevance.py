#!/usr/bin/env python3
"""Fit one tiny deterministic Top-5 relevance classifier without changing retrieval/order.

Goal: distinguish a genuinely useful lower-ranked candidate from an obviously unrelated
visible candidate. This is deliberately the last simple candidate-level discrimination
experiment before considering whether more semantic information is required.

Evidence protocol:
- historical Platsbanken task snippets only;
- 2023 concepts are deterministically split 4/5 fit, 1/5 calibration;
- 2024 is untouched evaluation;
- positive label = the structured occupation target when it appears in Top-5;
- safe negative label = a Top-5 candidate from a different SSYK4 than the target;
- same-SSYK non-target candidates are unlabeled/ignored, never taught as negatives;
- rank is NOT a model feature;
- display rule automatically retains candidates sharing rank-1 SSYK4, otherwise applies
  the frozen linear probability threshold;
- threshold is the minimum probability among calibration targets that are not already
  protected by rank-1 SSYK4, giving zero calibration target loss;
- opened stress rows are never loaded here.

The model is standard-library logistic regression with fixed optimization constants.
If it wins, browser runtime cost is only a feature calculation plus a small weight vector.
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
    enrich_features,
    fetch_year_concept,
    wilson,
)
from evaluate_p80_display_relevance_calibration import candidate_features
from evaluate_p80_display_ssyk_phrase_gate import SSYK_HIERARCHY_URL, build_ssyk4_map
from evaluate_p80_display_ssyk_unit_similarity import best_unit_similarity, evidence_units
from evaluate_p80_lexical_ablation import expected_hash, fetch
from evaluate_pareto_c1 import rank_c1

FEATURES = (
    "score_ratio",
    "idf_coverage",
    "token_coverage",
    "shared_count_scaled",
    "phrase_idf_coverage",
    "phrase_token_coverage",
    "phrase_shared_count_scaled",
    "unit_tfidf_cosine",
    "unit_idf_dice",
    "ssyk_group_count_scaled",
    "ssyk_group_mass_fraction",
)
FIT_STEPS = 800
LEARNING_RATE = 0.05
L2 = 0.01


def concept_split(cid: str) -> str:
    bucket = int(hashlib.sha256(f"p80-display-linear-v0:{cid}".encode()).hexdigest()[:8], 16) % 5
    return "calibration" if bucket == 0 else "fit"


def annotate_features(
    ranker,
    query: str,
    candidates: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    ssyk4: dict[str, str],
    phrase_map: dict[str, list[str]],
    unit_map: dict[str, list[str]],
) -> None:
    if not candidates:
        return
    enrich_features(ranker, query, candidates, phrase_map)
    top_code = ssyk4[str(candidates[0]["concept_id"])]
    group_counts: dict[str, int] = {}
    group_mass: dict[str, float] = {}
    total_mass = 0.0
    for c in candidates:
        cid = str(c["concept_id"])
        code = ssyk4[cid]
        mass = float(c["score_ratio"])
        group_counts[code] = group_counts.get(code, 0) + 1
        group_mass[code] = group_mass.get(code, 0.0) + mass
        total_mass += mass
    total_mass = total_mass or 1.0
    for c in candidates:
        cid = str(c["concept_id"])
        code = ssyk4[cid]
        c["ssyk_code_2012"] = code
        c["same_ssyk_as_top1"] = bool(code == top_code)
        c.update(best_unit_similarity(ranker, query, unit_map[cid]))
        c["shared_count_scaled"] = float(c["shared_count"]) / 10.0
        c["phrase_shared_count_scaled"] = float(c["phrase_shared_count"]) / 10.0
        c["ssyk_group_count_scaled"] = group_counts[code] / 5.0
        c["ssyk_group_mass_fraction"] = group_mass[code] / total_mass


def vector(c: dict[str, Any]) -> list[float]:
    return [float(c[name]) for name in FEATURES]


def standardizer(xs: list[list[float]]) -> tuple[list[float], list[float]]:
    if not xs:
        raise RuntimeError("no fit examples")
    d = len(xs[0])
    means = [sum(row[j] for row in xs) / len(xs) for j in range(d)]
    scales = []
    for j in range(d):
        var = sum((row[j] - means[j]) ** 2 for row in xs) / len(xs)
        scales.append(max(1e-6, math.sqrt(var)))
    return means, scales


def zvec(x: list[float], means: list[float], scales: list[float]) -> list[float]:
    return [(v - m) / s for v, m, s in zip(x, means, scales, strict=True)]


def sigmoid(x: float) -> float:
    if x >= 0:
        e = math.exp(-min(x, 60.0))
        return 1.0 / (1.0 + e)
    e = math.exp(max(x, -60.0))
    return e / (1.0 + e)


def fit_logistic(examples: list[tuple[list[float], int]]) -> dict[str, Any]:
    positives = sum(y == 1 for _x, y in examples)
    negatives = sum(y == 0 for _x, y in examples)
    if positives < 10 or negatives < 10:
        raise RuntimeError(f"insufficient fit labels: pos={positives} neg={negatives}")
    raw_x = [x for x, _y in examples]
    means, scales = standardizer(raw_x)
    data = [(zvec(x, means, scales), y) for x, y in examples]
    d = len(FEATURES)
    weights = [0.0] * d
    bias = 0.0
    pos_weight = negatives / positives
    neg_weight = 1.0
    weight_sum = positives * pos_weight + negatives * neg_weight

    for _ in range(FIT_STEPS):
        gw = [0.0] * d
        gb = 0.0
        for x, y in data:
            p = sigmoid(bias + sum(w * v for w, v in zip(weights, x, strict=True)))
            cw = pos_weight if y == 1 else neg_weight
            err = (p - y) * cw
            gb += err
            for j in range(d):
                gw[j] += err * x[j]
        for j in range(d):
            gw[j] = gw[j] / weight_sum + L2 * weights[j]
            weights[j] -= LEARNING_RATE * gw[j]
        bias -= LEARNING_RATE * gb / weight_sum

    return {
        "features": list(FEATURES),
        "means": means,
        "scales": scales,
        "weights": weights,
        "bias": bias,
        "fit_positive_examples": positives,
        "fit_safe_negative_examples": negatives,
        "steps": FIT_STEPS,
        "learning_rate": LEARNING_RATE,
        "l2": L2,
        "positive_class_weight": pos_weight,
    }


def probability(c: dict[str, Any], model: dict[str, Any]) -> float:
    x = zvec(vector(c), model["means"], model["scales"])
    return sigmoid(float(model["bias"]) + sum(float(w) * v for w, v in zip(model["weights"], x, strict=True)))


def keep(c: dict[str, Any], model: dict[str, Any], threshold: float) -> bool:
    return bool(c["same_ssyk_as_top1"] or probability(c, model) >= threshold)


def summarize(rows: list[dict[str, Any]], ssyk4: dict[str, str], model: dict[str, Any], threshold: float) -> dict[str, Any]:
    bh = rh = bt = rt = before = after = safe_before = safe_after = zero = 0
    by_rank = {i: [0, 0] for i in range(1, 6)}
    for row in rows:
        target = str(row["concept_id"])
        target_code = ssyk4[target]
        cs = row["candidates"]
        before += len(cs)
        tr = next((c for c in cs if str(c["concept_id"]) == target), None)
        if tr:
            bh += 1
            rank = int(tr["rank"])
            by_rank[rank][0] += 1
            bt += int(rank >= 2)
        kept = [c for c in cs if keep(c, model, threshold)]
        after += len(kept)
        zero += int(not kept)
        for c in cs:
            cid = str(c["concept_id"])
            if cid != target and ssyk4[cid] != target_code:
                safe_before += 1
        for c in kept:
            cid = str(c["concept_id"])
            if cid != target and ssyk4[cid] != target_code:
                safe_after += 1
        if tr and tr in kept:
            rh += 1
            rank = int(tr["rank"])
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
        "safe_cross_ssyk_negative_before": safe_before,
        "safe_cross_ssyk_negative_after": safe_after,
        "safe_cross_ssyk_negative_reduction": round(1 - safe_after / max(1, safe_before), 6),
        "zero_result_rate_after": round(zero / max(1, n), 6),
        "rank_retention": {
            str(rank): {"baseline": v[0], "retained": v[1], "rate": round(v[1] / max(1, v[0]), 6)}
            for rank, v in by_rank.items()
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
        annotate_features(ranker, case["query"], cs, by_id, ssyk4, phrase_map, unit_map)
        rows.append({**case, "candidates": cs})

    fit_rows = [r for r in rows if r["year"] == CAL_YEAR and concept_split(str(r["concept_id"])) == "fit"]
    cal_rows = [r for r in rows if r["year"] == CAL_YEAR and concept_split(str(r["concept_id"])) == "calibration"]
    eval_rows = [r for r in rows if r["year"] == EVAL_YEAR]

    fit_examples: list[tuple[list[float], int]] = []
    for row in fit_rows:
        target = str(row["concept_id"])
        target_code = ssyk4[target]
        for c in row["candidates"]:
            cid = str(c["concept_id"])
            if cid == target:
                fit_examples.append((vector(c), 1))
            elif ssyk4[cid] != target_code:
                fit_examples.append((vector(c), 0))
            # Same-SSYK non-target = unlabeled, deliberately ignored.

    model = fit_logistic(fit_examples)

    required_probs = []
    calibration_cross_family_targets = 0
    for row in cal_rows:
        target = str(row["concept_id"])
        tr = next((c for c in row["candidates"] if str(c["concept_id"]) == target), None)
        if tr and not tr["same_ssyk_as_top1"]:
            calibration_cross_family_targets += 1
            required_probs.append(probability(tr, model))
    if not required_probs:
        raise RuntimeError("no cross-family calibration targets; cannot select visibility threshold")
    threshold = min(required_probs)

    cal_metrics = summarize(cal_rows, ssyk4, model, threshold)
    if cal_metrics["retained_hit5"] != cal_metrics["baseline_hit5"]:
        raise RuntimeError("zero-loss calibration invariant failed")
    eval_metrics = summarize(eval_rows, ssyk4, model, threshold)

    strong = (
        eval_metrics["hit5_retention"] >= 0.98
        and eval_metrics["tail_hit_retention"] >= 0.98
        and eval_metrics["safe_cross_ssyk_negative_reduction"] >= 0.35
    )
    promising = (
        eval_metrics["hit5_retention"] >= 0.95
        and eval_metrics["tail_hit_retention"] >= 0.95
        and eval_metrics["safe_cross_ssyk_negative_reduction"] >= 0.50
    )

    result = {
        "id": "YV-P80-display-linear-relevance-v0",
        "evidence_class": "natural historical Platsbanken task-text proxy with structured target; safe negatives are different-SSYK4 only",
        "candidate_universe": EXPECTED_UNIVERSE,
        "ranker_changed": False,
        "rank_order_changed": False,
        "opened_17_88_loaded": False,
        "label_contract": {
            "positive": "structured target when present in Top5",
            "safe_negative": "non-target Top5 candidate in different SSYK4 from structured target",
            "ignored": "same-SSYK4 non-target candidate",
        },
        "feature_contract": {"features": list(FEATURES), "rank_feature_used": False, "same_ssyk_as_top1_is_model_feature": False},
        "split": {
            "fit": "2023 deterministic concept hash buckets 1-4/5",
            "calibration": "2023 deterministic concept hash bucket 0/5",
            "evaluation": "all accepted 2024 natural task snippets",
            "fit_queries": len(fit_rows),
            "calibration_queries": len(cal_rows),
            "evaluation_queries": len(eval_rows),
            "fit_concepts": len({r['concept_id'] for r in fit_rows}),
            "calibration_concepts": len({r['concept_id'] for r in cal_rows}),
            "evaluation_concepts": len({r['concept_id'] for r in eval_rows}),
        },
        "model": {
            **model,
            "means": [round(float(x), 12) for x in model["means"]],
            "scales": [round(float(x), 12) for x in model["scales"]],
            "weights": [round(float(x), 12) for x in model["weights"]],
            "bias": round(float(model["bias"]), 12),
        },
        "display_rule": {
            "rule": "keep when same SSYK4 as rank1 OR linear relevance probability >= threshold",
            "threshold": threshold,
            "threshold_selection": "minimum probability among 2023 calibration targets not protected by rank1 SSYK4",
            "calibration_cross_family_targets": calibration_cross_family_targets,
            "calibration": cal_metrics,
        },
        "evaluation": eval_metrics,
        "decision_gate": {
            "strong": "2024 Hit@5 retention >=98%, rank2-5 retention >=98%, safe cross-SSYK negative reduction >=35%",
            "promising": "2024 Hit@5 retention >=95%, rank2-5 retention >=95%, safe cross-SSYK negative reduction >=50%",
            "strong_passed": strong,
            "promising_passed": promising,
            "if_strong_or_promising": "freeze unchanged and replay opened user-style stress diagnostically",
            "if_neither": "stop hand-built/linear display discrimination; reassess whether additional semantic evidence is required",
        },
        "interpretation_boundary": "Structured ad target plus cross-SSYK safe negatives are stronger than generic non-target proxies but are still not human judgments of every visible suggestion.",
    }
    out = Path("research/evaluation/v31/p80-display-linear-relevance-v0.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"split": result["split"], "model": {"fit_positive_examples": model["fit_positive_examples"], "fit_safe_negative_examples": model["fit_safe_negative_examples"]}, "display_rule": result["display_rule"], "evaluation": eval_metrics, "decision_gate": result["decision_gate"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
