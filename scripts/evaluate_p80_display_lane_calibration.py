#!/usr/bin/env python3
"""Test a bounded lane-aware display relevance signal for P80 YV.

The retrieval ranker and candidate universe are unchanged. The experiment asks whether
preserving phrase-level enrichment evidence separately from the merged BM25 document
helps decide which already-ranked top-5 candidates are worth displaying.

Threshold/formula selection uses only the deterministic calibration concept split from
v0. The untouched evaluation concepts decide the synthetic gate. Opened 17/88 rows are
not loaded here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_a593_language_diversity_falsifier import load_diverse_training, load_teacher
from evaluate_gemma_a149 import build_ranker
from evaluate_p80_display_relevance_calibration import (
    STYLES, candidate_features, load_cases, split_for,
)
from evaluate_p80_lexical_ablation import expected_hash, fetch, tokens
from evaluate_pareto_c1 import rank_c1

TAXONOMY_URL = (
    "https://data.jobtechdev.se/taxonomy/version/31/query/"
    "concepts-and-common-relations/concepts-and-common-relations.json"
)


def add_teacher(dst: dict[str, list[str]], src: dict[str, list[str]], allowed: set[str] | None = None) -> None:
    for cid, values in src.items():
        if allowed is not None and cid not in allowed:
            continue
        dst.setdefault(cid, []).extend(values)


def best_phrase_support(ranker, query: str, phrases: list[str]) -> dict[str, float | int]:
    qtokens = sorted(set(tokens(query)))
    max_idf = max(ranker.idf.values(), default=1.0)
    query_mass = sum(float(ranker.idf.get(t, max_idf)) for t in qtokens) or 1.0
    best = {"phrase_idf_coverage": 0.0, "phrase_token_coverage": 0.0, "phrase_shared_count": 0}
    for phrase in phrases:
        ptokens = set(tokens(phrase))
        shared = [t for t in qtokens if t in ptokens]
        idf_cov = sum(float(ranker.idf.get(t, max_idf)) for t in shared) / query_mass
        tok_cov = len(shared) / max(1, len(qtokens))
        candidate = (idf_cov, tok_cov, len(shared))
        current = (
            float(best["phrase_idf_coverage"]),
            float(best["phrase_token_coverage"]),
            int(best["phrase_shared_count"]),
        )
        if candidate > current:
            best = {
                "phrase_idf_coverage": idf_cov,
                "phrase_token_coverage": tok_cov,
                "phrase_shared_count": len(shared),
            }
    return best


def confidence(c: dict[str, Any], formula: str) -> float:
    r = float(c["score_ratio"])
    merged = float(c["idf_coverage"])
    phrase = float(c["phrase_idf_coverage"])
    if formula == "merged":
        return r * merged
    if formula == "phrase":
        return phrase
    if formula == "ratio_phrase":
        return r * phrase
    if formula == "ratio_max_support":
        return r * max(merged, phrase)
    if formula == "ratio_mean_support":
        return r * (merged + phrase) / 2.0
    raise ValueError(formula)


def summarize(rows: list[dict[str, Any]], formula: str, threshold: float) -> dict[str, Any]:
    baseline_hits = retained_hits = baseline_tail = retained_tail = 0
    shown = negative = zero = 0
    by_rank = {i: [0, 0] for i in range(1, 6)}
    for row in rows:
        target = row["concept_id"]
        target_row = next((c for c in row["candidates"] if c["concept_id"] == target), None)
        if target_row:
            baseline_hits += 1
            rank = int(target_row["rank"])
            by_rank[rank][0] += 1
            if rank >= 2:
                baseline_tail += 1
        kept = [c for c in row["candidates"] if confidence(c, formula) >= threshold]
        shown += len(kept)
        negative += sum(c["concept_id"] != target for c in kept)
        zero += int(not kept)
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
        "baseline_tail_hits": baseline_tail,
        "retained_tail_hits": retained_tail,
        "tail_hit_retention": round(retained_tail / max(1, baseline_tail), 6),
        "mean_displayed": round(shown / max(1, n), 6),
        "mean_exact_target_negative_displayed": round(negative / max(1, n), 6),
        "zero_result_rate": round(zero / max(1, n), 6),
        "rank_retention": {
            str(rank): {
                "baseline": values[0],
                "retained": values[1],
                "rate": round(values[1] / max(1, values[0]), 6),
            }
            for rank, values in by_rank.items()
        },
    }


def choose(calibration: list[dict[str, Any]]) -> tuple[str, float, dict[str, Any]]:
    formulas = ("merged", "phrase", "ratio_phrase", "ratio_max_support", "ratio_mean_support")
    thresholds = [i / 100 for i in range(0, 61, 2)]
    feasible = []
    for formula in formulas:
        for threshold in thresholds:
            metrics = summarize(calibration, formula, threshold)
            if metrics["hit5_retention"] < 0.98 or metrics["tail_hit_retention"] < 0.98:
                continue
            key = (
                metrics["mean_exact_target_negative_displayed"],
                metrics["mean_displayed"],
                -metrics["hit5_retention"],
                threshold,
                formula,
            )
            feasible.append((key, formula, threshold, metrics))
    if not feasible:
        raise RuntimeError("no lane-aware rule satisfies frozen calibration retention constraints")
    feasible.sort(key=lambda x: x[0])
    _key, formula, threshold, metrics = feasible[0]
    return formula, threshold, metrics


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--teacher", default="research/enrichment/v31/gemma4-yv-a593/phrases.jsonl")
    ap.add_argument("--priority", default="research/evaluation/v31/p80-track2-priority-coverage.json")
    ap.add_argument("--a593-train", default="research/training/v31/a593-language-diversity-training-v0.jsonl")
    ap.add_argument("--p80-train", default="research/training/v31/p80-language-diversity-training-v0.jsonl")
    ap.add_argument("--rescue-train", default="research/training/v31/p80-source-thin-rescue-training-v0.jsonl")
    ap.add_argument("--a593-holdout", default="research/evaluation/v31/a593-language-diversity-holdout-v0.jsonl")
    ap.add_argument("--p80-holdout", default="research/evaluation/v31/p80-language-diversity-holdout-v0.jsonl")
    ap.add_argument("--rescue-holdout", default="research/evaluation/v31/p80-source-thin-rescue-holdout-v0.jsonl")
    ap.add_argument("--output", default="research/evaluation/v31/p80-display-lane-calibration-v0.json")
    args = ap.parse_args()

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
    if len(existing_ids | missing_ids) != 159:
        raise RuntimeError("P80 membership drift")

    _teacher_ids, base_teacher = load_teacher(Path(args.teacher))
    a593_train, _ = load_diverse_training(Path(args.a593_train))
    p80_train, _ = load_diverse_training(Path(args.p80_train))
    rescue_train, rescue_meta = load_diverse_training(Path(args.rescue_train))
    if len(rescue_meta) != 22:
        raise RuntimeError("rescue metadata drift")

    merged_teacher = {cid: list(v) for cid, v in base_teacher.items()}
    add_teacher(merged_teacher, a593_train, existing_ids)
    add_teacher(merged_teacher, p80_train, missing_ids)
    add_teacher(merged_teacher, rescue_train, existing_ids | missing_ids)
    ranker, exact, surfaces = build_ranker(by_id, ids, merged_teacher)

    # Phrase evidence stays provenance-aware here; this does not change retrieval.
    phrase_map: dict[str, list[str]] = {cid: list(v) for cid, v in base_teacher.items()}
    add_teacher(phrase_map, a593_train, existing_ids)
    add_teacher(phrase_map, p80_train, missing_ids)
    add_teacher(phrase_map, rescue_train, existing_ids | missing_ids)

    cases = load_cases(
        Path(args.a593_holdout), Path(args.p80_holdout), Path(args.rescue_holdout),
        existing_ids, missing_ids, a593_train, p80_train, rescue_train,
    )
    rows = []
    for case in cases:
        scored = rank_c1(ranker, case["query"], exact, surfaces)
        candidates = candidate_features(ranker, case["query"], scored)
        for c in candidates:
            c.update(best_phrase_support(ranker, case["query"], phrase_map.get(c["concept_id"], [])))
            c["is_target"] = c["concept_id"] == case["concept_id"]
        rows.append({**case, "candidates": candidates})

    calibration = [r for r in rows if split_for(r["concept_id"]) == "calibration"]
    evaluation = [r for r in rows if split_for(r["concept_id"]) == "evaluation"]
    formula, threshold, cal = choose(calibration)
    baseline = summarize(evaluation, formula, 0.0)
    gated = summarize(evaluation, formula, threshold)
    reduction = 1.0 - gated["mean_exact_target_negative_displayed"] / max(1e-12, baseline["mean_exact_target_negative_displayed"])
    passed = (
        gated["hit5_retention"] >= 0.98
        and gated["tail_hit_retention"] >= 0.98
        and reduction >= 0.25
    )
    result = {
        "id": "YV-P80-display-lane-calibration-v0",
        "evidence_class": "prefrozen model-authored P80 holdout; candidate-level mechanism evidence, not human relevance accuracy",
        "opened_17_88_loaded": False,
        "candidate_universe": 2105,
        "ranker_changed": False,
        "experiment": "preserve phrase-level enrichment evidence separately for display calibration only",
        "split": {
            "calibration_queries": len(calibration),
            "evaluation_queries": len(evaluation),
            "calibration_concepts": len({r['concept_id'] for r in calibration}),
            "evaluation_concepts": len({r['concept_id'] for r in evaluation}),
            "policy": "same deterministic concept split as p80-display-relevance-calibration-v0",
        },
        "rule_family": list(("merged", "phrase", "ratio_phrase", "ratio_max_support", "ratio_mean_support")),
        "selection_constraint": "calibration overall and rank2-5 target retention >=98%; minimize exact-target-negative visible candidates",
        "selected": {"formula": formula, "threshold": threshold, "calibration": cal},
        "evaluation": {
            "baseline": baseline,
            "gated": gated,
            "negative_reduction": round(reduction, 6),
        },
        "decision_gate": {
            "rule": "untouched evaluation overall Hit@5 retention >=98%; rank2-5 retention >=98%; >=25% exact-target-negative reduction",
            "passed": passed,
            "if_pass": "freeze rule then replay opened stress diagnostically without changing it",
            "if_fail": "do not add a lane-aware display layer",
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
