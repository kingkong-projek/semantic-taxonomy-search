#!/usr/bin/env python3
"""Calibrate a simple length-robust display signal on natural task text.

2023 historical Platsbanken task-oriented snippets are calibration only. The selected
formula/threshold must retain every baseline Hit@5 target in calibration. The rule is
then frozen and evaluated untouched on 2024. Retrieval and the 2,105 candidate universe
remain unchanged; opened 17/88 is never loaded.

This remains proxy evidence: a structured ad occupation is a target label, not a human
judgment that every sibling result is irrelevant. Raw ad text is never committed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from evaluate_a593_language_diversity_falsifier import load_diverse_training, load_teacher
from evaluate_gemma_a149 import build_ranker
from evaluate_p80_display_lane_calibration import add_teacher, best_phrase_support
from evaluate_p80_display_lane_historical_ads import (
    HISTORICAL_SEARCH, ad_description, ad_id, fetch_json, occupation_id,
    publication_date, strip_markup, title_surfaces,
)
from evaluate_p80_display_relevance_calibration import candidate_features
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm, tokens
from evaluate_pareto_c1 import rank_c1

TAXONOMY_URL = (
    "https://data.jobtechdev.se/taxonomy/version/31/query/"
    "concepts-and-common-relations/concepts-and-common-relations.json"
)
EXPECTED_UNIVERSE = 2105
CAL_YEAR = 2023
EVAL_YEAR = 2024
MAX_WORDS = 50
MIN_WORDS = 12
TASK_MARKERS = (
    "arbetsuppgift",
    "du kommer att",
    "arbetet innebar",
    "rollen innebar",
    "i rollen",
    "i ditt arbete",
    "dina huvudsakliga",
    "huvudsakliga arbetsuppgifter",
    "uppdraget innebar",
    "arbetsdagen",
)
FORMULAS = (
    "score_ratio",
    "max_shared_count",
    "max_idf_mass",
    "ratio_max_shared_count",
    "ratio_max_idf_mass",
    "ratio_phrase_idf_mass",
)


def wilson(success: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total <= 0:
        return None
    p = success / total
    d = 1 + z * z / total
    center = (p + z * z / (2 * total)) / d
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / d
    return [round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6)]


def task_query(text: str, forbidden: list[str]) -> tuple[str | None, int]:
    clean = strip_markup(text)
    if not clean:
        return None, 0
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if s.strip()]
    allowed: list[str | None] = []
    removed = 0
    for sentence in sentences:
        n = norm(sentence)
        if any(surface and surface in n for surface in forbidden):
            allowed.append(None)
            removed += 1
        else:
            allowed.append(sentence)
    start = None
    for i, sentence in enumerate(allowed):
        if not sentence:
            continue
        n = norm(sentence)
        if any(marker in n for marker in TASK_MARKERS):
            start = i
            break
    if start is None:
        return None, removed
    selected: list[str] = []
    for sentence in allowed[start:start + 4]:
        if sentence:
            selected.append(sentence)
    words = " ".join(selected).split()
    if len(words) < MIN_WORDS:
        return None, removed
    return " ".join(words[:MAX_WORDS]), removed


def fetch_year_concept(cid: str, concept: dict[str, Any], year: int, *, search_limit: int, accepted: int) -> dict[str, Any]:
    params = {
        "published-after": f"{year}-01-01T00:00:00",
        "published-before": f"{year + 1}-01-01T00:00:00",
        "occupation-name": cid,
        "offset": 0,
        "limit": search_limit,
        "request-timeout": 60,
    }
    payload = fetch_json(HISTORICAL_SEARCH + "?" + urllib.parse.urlencode(params))
    hits = payload.get("hits") if isinstance(payload, dict) else None
    if not isinstance(hits, list):
        raise RuntimeError(f"unexpected historical search schema for {cid}/{year}")
    forbidden = title_surfaces(concept)
    rows: list[dict[str, Any]] = []
    rejected = {"wrong_structured_target": 0, "missing_description": 0, "no_task_snippet": 0}
    for hit in sorted((h for h in hits if isinstance(h, dict)), key=ad_id):
        aid = ad_id(hit)
        if not aid:
            continue
        structured = occupation_id(hit)
        if structured and structured != cid:
            rejected["wrong_structured_target"] += 1
            continue
        body = ad_description(hit)
        if not body:
            rejected["missing_description"] += 1
            continue
        query, removed = task_query(body, forbidden)
        if not query:
            rejected["no_task_snippet"] += 1
            continue
        rows.append({
            "concept_id": cid,
            "year": year,
            "ad_id": aid,
            "publication_date": publication_date(hit),
            "query": query,
            "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
            "query_word_count": len(query.split()),
            "title_sentences_removed": removed,
        })
        if len(rows) >= accepted:
            break
    return {"concept_id": cid, "year": year, "hits_returned": len(hits), "accepted": rows, "rejected": rejected}


def enrich_features(ranker, query: str, candidates: list[dict[str, Any]], phrase_map: dict[str, list[str]]) -> None:
    qtokens = sorted(set(tokens(query)))
    max_idf = max(ranker.idf.values(), default=1.0)
    query_mass = sum(float(ranker.idf.get(t, max_idf)) for t in qtokens) or 1.0
    for c in candidates:
        phrase = best_phrase_support(ranker, query, phrase_map.get(c["concept_id"], []))
        c.update(phrase)
        merged_mass = float(c["idf_coverage"]) * query_mass
        phrase_mass = float(phrase["phrase_idf_coverage"]) * query_mass
        c["merged_idf_mass"] = merged_mass
        c["phrase_idf_mass"] = phrase_mass
        c["max_idf_mass"] = max(merged_mass, phrase_mass)
        c["max_shared_count"] = max(int(c["shared_count"]), int(phrase["phrase_shared_count"]))


def conf(c: dict[str, Any], formula: str) -> float:
    ratio = float(c["score_ratio"])
    if formula == "score_ratio":
        return ratio
    if formula == "max_shared_count":
        return float(c["max_shared_count"])
    if formula == "max_idf_mass":
        return float(c["max_idf_mass"])
    if formula == "ratio_max_shared_count":
        return ratio * float(c["max_shared_count"])
    if formula == "ratio_max_idf_mass":
        return ratio * float(c["max_idf_mass"])
    if formula == "ratio_phrase_idf_mass":
        return ratio * float(c["phrase_idf_mass"])
    raise ValueError(formula)


def summarize(rows: list[dict[str, Any]], formula: str, threshold: float) -> dict[str, Any]:
    baseline_hits = retained_hits = baseline_tail = retained_tail = 0
    before = after = neg_before = neg_after = zero = top1 = 0
    by_rank = {i: [0, 0] for i in range(1, 6)}
    for row in rows:
        target = row["concept_id"]
        candidates = row["candidates"]
        before += len(candidates)
        neg_before += sum(c["concept_id"] != target for c in candidates)
        target_row = next((c for c in candidates if c["concept_id"] == target), None)
        if target_row:
            baseline_hits += 1
            rank = int(target_row["rank"])
            top1 += int(rank == 1)
            by_rank[rank][0] += 1
            if rank >= 2:
                baseline_tail += 1
        kept = [c for c in candidates if conf(c, formula) >= threshold]
        after += len(kept)
        neg_after += sum(c["concept_id"] != target for c in kept)
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
        "concepts": len({r["concept_id"] for r in rows}),
        "baseline_top1": top1,
        "baseline_hit5": baseline_hits,
        "baseline_tail_hits_rank2_5": baseline_tail,
        "retained_hit5": retained_hits,
        "retained_tail_hits_rank2_5": retained_tail,
        "hit5_retention": round(retained_hits / max(1, baseline_hits), 6),
        "hit5_retention_wilson95": wilson(retained_hits, baseline_hits),
        "tail_hit_retention": round(retained_tail / max(1, baseline_tail), 6),
        "tail_hit_retention_wilson95": wilson(retained_tail, baseline_tail),
        "mean_displayed_before": round(before / max(1, n), 6),
        "mean_displayed_after": round(after / max(1, n), 6),
        "exact_target_negative_reduction": round(1 - neg_after / max(1, neg_before), 6),
        "zero_result_rate_after": round(zero / max(1, n), 6),
        "rank_retention": {
            str(rank): {
                "baseline": values[0],
                "retained": values[1],
                "rate": round(values[1] / max(1, values[0]), 6),
                "wilson95": wilson(values[1], values[0]),
            }
            for rank, values in by_rank.items()
        },
    }


def choose_zero_loss(calibration: list[dict[str, Any]]) -> tuple[str, float, dict[str, Any], list[dict[str, Any]]]:
    frontier = []
    for formula in FORMULAS:
        positives = []
        for row in calibration:
            target = row["concept_id"]
            target_row = next((c for c in row["candidates"] if c["concept_id"] == target), None)
            if target_row:
                positives.append(conf(target_row, formula))
        if not positives:
            continue
        threshold = min(positives)
        metrics = summarize(calibration, formula, threshold)
        if metrics["retained_hit5"] != metrics["baseline_hit5"]:
            raise RuntimeError(f"zero-loss selection invariant failed for {formula}")
        frontier.append({"formula": formula, "threshold": threshold, "calibration": metrics})
    if not frontier:
        raise RuntimeError("no calibration formula available")
    frontier.sort(key=lambda x: (
        x["calibration"]["mean_displayed_after"],
        -x["calibration"]["exact_target_negative_reduction"],
        x["formula"],
    ))
    selected = frontier[0]
    return selected["formula"], float(selected["threshold"]), selected["calibration"], frontier


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--teacher", default="research/enrichment/v31/gemma4-yv-a593/phrases.jsonl")
    ap.add_argument("--priority", default="research/evaluation/v31/p80-track2-priority-coverage.json")
    ap.add_argument("--a593-train", default="research/training/v31/a593-language-diversity-training-v0.jsonl")
    ap.add_argument("--p80-train", default="research/training/v31/p80-language-diversity-training-v0.jsonl")
    ap.add_argument("--rescue-train", default="research/training/v31/p80-source-thin-rescue-training-v0.jsonl")
    ap.add_argument("--output", default="research/evaluation/v31/p80-display-natural-task-calibration-v0.json")
    ap.add_argument("--search-limit", type=int, default=25)
    ap.add_argument("--ads-per-concept", type=int, default=5)
    args = ap.parse_args()

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    wire = fetch(TAXONOMY_URL)
    if hashlib.sha256(wire).hexdigest() != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != EXPECTED_UNIVERSE:
        raise RuntimeError("candidate universe drift")

    priority = json.loads(Path(args.priority).read_text(encoding="utf-8"))
    existing_ids = {str(r["concept_id"]) for r in priority.get("existing_diversified_v0") or []}
    missing_ids = {str(r["concept_id"]) for r in priority.get("missing_diversified_v0") or []}
    p80_ids = existing_ids | missing_ids
    if len(p80_ids) != 159:
        raise RuntimeError("P80 membership drift")

    _teacher_ids, base_teacher = load_teacher(Path(args.teacher))
    a593_train, _ = load_diverse_training(Path(args.a593_train))
    p80_train, _ = load_diverse_training(Path(args.p80_train))
    rescue_train, rescue_meta = load_diverse_training(Path(args.rescue_train))
    rescue_ids = set(rescue_meta)
    if len(rescue_ids) != 22:
        raise RuntimeError("rescue identity set drift")
    primary_ids = sorted(p80_ids - rescue_ids)

    teacher = {cid: list(v) for cid, v in base_teacher.items()}
    add_teacher(teacher, a593_train, existing_ids)
    add_teacher(teacher, p80_train, missing_ids)
    add_teacher(teacher, rescue_train, p80_ids)
    ranker, exact, surfaces = build_ranker(by_id, ids, teacher)
    phrase_map: dict[str, list[str]] = {cid: list(v) for cid, v in base_teacher.items()}
    add_teacher(phrase_map, a593_train, existing_ids)
    add_teacher(phrase_map, p80_train, missing_ids)
    add_teacher(phrase_map, rescue_train, p80_ids)

    groups: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(fetch_year_concept, cid, by_id[cid], year, search_limit=args.search_limit, accepted=args.ads_per_concept): (cid, year)
            for cid in primary_ids for year in (CAL_YEAR, EVAL_YEAR)
        }
        for fut in as_completed(futures):
            groups.append(fut.result())
    groups.sort(key=lambda x: (x["year"], x["concept_id"]))

    cases = [row for group in groups for row in group["accepted"]]
    rows = []
    for case in cases:
        scored = rank_c1(ranker, case["query"], exact, surfaces)
        candidates = candidate_features(ranker, case["query"], scored)
        enrich_features(ranker, case["query"], candidates, phrase_map)
        rows.append({**case, "candidates": candidates})
    calibration = [r for r in rows if r["year"] == CAL_YEAR]
    evaluation = [r for r in rows if r["year"] == EVAL_YEAR]
    formula, threshold, cal_metrics, frontier = choose_zero_loss(calibration)
    eval_metrics = summarize(evaluation, formula, threshold)

    def source_summary(year: int) -> dict[str, Any]:
        gs = [g for g in groups if g["year"] == year]
        rs = [r for r in rows if r["year"] == year]
        counts = [r["query_word_count"] for r in rs]
        return {
            "year": year,
            "queries": len(rs),
            "concepts": len({r["concept_id"] for r in rs}),
            "concepts_with_no_accepted_task_snippet": sum(not g["accepted"] for g in gs),
            "api_hits_returned": sum(g["hits_returned"] for g in gs),
            "mean_query_words": round(sum(counts) / max(1, len(counts)), 3),
            "rejected": {
                key: sum(g["rejected"][key] for g in gs)
                for key in ("wrong_structured_target", "missing_description", "no_task_snippet")
            },
        }

    manifest = [
        {
            "year": r["year"], "concept_id": r["concept_id"], "ad_id": r["ad_id"],
            "publication_date": r["publication_date"], "query_sha256": r["query_sha256"],
            "query_word_count": r["query_word_count"], "title_sentences_removed": r["title_sentences_removed"],
        }
        for r in rows
    ]
    result = {
        "id": "YV-P80-display-natural-task-calibration-v0",
        "evidence_class": "historical Platsbanken natural task-text proxy with structured occupation-name target; not human relevance judgment",
        "candidate_universe": 2105,
        "ranker_changed": False,
        "opened_17_88_loaded": False,
        "source_family_overlap_rescue_ids_excluded": len(rescue_ids),
        "task_extraction": {
            "markers_frozen_before_results": list(TASK_MARKERS),
            "max_words": MAX_WORDS,
            "min_words": MIN_WORDS,
            "headline_used": False,
            "target_title_sentences_removed": True,
            "raw_text_committed": False,
        },
        "split": {"calibration_year": CAL_YEAR, "evaluation_year": EVAL_YEAR},
        "selection_contract": {
            "formula_family": list(FORMULAS),
            "threshold": "minimum target confidence among all baseline Hit@5 calibration targets for each formula",
            "hard_constraint": "zero baseline Hit@5 target losses in 2023 calibration",
            "objective": "among zero-loss formulas minimize displayed candidates; tie-break by greater exact-target-negative reduction",
            "no_query_coverage_features": True,
        },
        "sample": {"calibration": source_summary(CAL_YEAR), "evaluation": source_summary(EVAL_YEAR)},
        "selected": {"formula": formula, "threshold": threshold, "calibration": cal_metrics},
        "calibration_frontier": frontier,
        "evaluation": eval_metrics,
        "interpretation_boundary": "Natural ad task text is a stronger language proxy than model-authored holdout but still not user self-description or human relevance truth. No production promotion without later human evidence.",
        "manifest": manifest,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"sample": result["sample"], "selected": result["selected"], "evaluation": eval_metrics}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
