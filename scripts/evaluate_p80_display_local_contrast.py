#!/usr/bin/env python3
"""Test one bounded candidate-level signal: local evidence contrast inside Top-5.

The retrieval ranker and ordering are unchanged. 2023 natural Platsbanken task text
selects one zero-loss display threshold. Untouched 2024 natural task text evaluates it.
Opened stress rows are not loaded here.
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
    CAL_YEAR, EVAL_YEAR, EXPECTED_UNIVERSE, TAXONOMY_URL,
    fetch_year_concept, wilson,
)
from evaluate_p80_display_relevance_calibration import candidate_features
from evaluate_p80_lexical_ablation import expected_hash, fetch, tokens
from evaluate_pareto_c1 import rank_c1

FORMULAS = (
    "local_idf_mass",
    "ratio_local_idf_mass",
    "inverse_df_idf_mass",
    "ratio_inverse_df_idf_mass",
    "exclusive_idf_mass",
    "ratio_exclusive_idf_mass",
)


def add_local_contrast(ranker, query: str, candidates: list[dict[str, Any]]) -> None:
    qtokens = sorted(set(tokens(query)))
    dfs = {t: sum(bool(ranker.tf[c["concept_id"]].get(t, 0)) for c in candidates) for t in qtokens}
    for c in candidates:
        cid = c["concept_id"]
        shared = [t for t in qtokens if ranker.tf[cid].get(t, 0)]
        local = 0.0
        inv = 0.0
        exclusive = 0.0
        for t in shared:
            df = max(1, dfs[t])
            gidf = float(ranker.idf.get(t, 0.0))
            local += gidf * math.log(6.0 / (1.0 + df))
            inv += gidf / df
            if df == 1:
                exclusive += gidf
        c["local_idf_mass"] = local
        c["inverse_df_idf_mass"] = inv
        c["exclusive_idf_mass"] = exclusive


def confidence(c: dict[str, Any], formula: str) -> float:
    ratio = float(c["score_ratio"])
    if formula == "local_idf_mass":
        return float(c["local_idf_mass"])
    if formula == "ratio_local_idf_mass":
        return ratio * float(c["local_idf_mass"])
    if formula == "inverse_df_idf_mass":
        return float(c["inverse_df_idf_mass"])
    if formula == "ratio_inverse_df_idf_mass":
        return ratio * float(c["inverse_df_idf_mass"])
    if formula == "exclusive_idf_mass":
        return float(c["exclusive_idf_mass"])
    if formula == "ratio_exclusive_idf_mass":
        return ratio * float(c["exclusive_idf_mass"])
    raise ValueError(formula)


def summarize(rows: list[dict[str, Any]], formula: str, threshold: float) -> dict[str, Any]:
    bh = rh = bt = rt = before = after = neg_before = neg_after = zero = 0
    by_rank = {i: [0, 0] for i in range(1, 6)}
    for row in rows:
        target = row["concept_id"]
        cs = row["candidates"]
        before += len(cs)
        neg_before += sum(c["concept_id"] != target for c in cs)
        target_row = next((c for c in cs if c["concept_id"] == target), None)
        if target_row:
            bh += 1
            r = int(target_row["rank"])
            by_rank[r][0] += 1
            if r >= 2: bt += 1
        kept = [c for c in cs if confidence(c, formula) >= threshold]
        after += len(kept)
        neg_after += sum(c["concept_id"] != target for c in kept)
        zero += int(not kept)
        if target_row and target_row in kept:
            rh += 1
            r = int(target_row["rank"])
            by_rank[r][1] += 1
            if r >= 2: rt += 1
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
        "exact_target_negative_reduction": round(1 - neg_after / max(1, neg_before), 6),
        "zero_result_rate_after": round(zero / max(1, n), 6),
        "rank_retention": {str(r): {"baseline": v[0], "retained": v[1], "rate": round(v[1]/max(1,v[0]),6)} for r,v in by_rank.items()},
    }


def choose_zero_loss(rows: list[dict[str, Any]]) -> dict[str, Any]:
    options = []
    for formula in FORMULAS:
        positives = []
        for row in rows:
            target = next((c for c in row["candidates"] if c["concept_id"] == row["concept_id"]), None)
            if target:
                positives.append(confidence(target, formula))
        if not positives:
            continue
        threshold = min(positives)
        metrics = summarize(rows, formula, threshold)
        if metrics["retained_hit5"] != metrics["baseline_hit5"]:
            raise RuntimeError("zero-loss invariant failed")
        options.append({"formula": formula, "threshold": threshold, "calibration": metrics})
    options.sort(key=lambda x: (x["calibration"]["mean_displayed_after"], -x["calibration"]["exact_target_negative_reduction"], x["formula"]))
    if not options:
        raise RuntimeError("no local-contrast formula")
    return {"selected": options[0], "frontier": options}


def main() -> int:
    registry = json.loads(Path("research/coverage/source-adapters.json").read_text())
    wire = fetch(TAXONOMY_URL)
    if hashlib.sha256(wire).hexdigest() != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid,c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != EXPECTED_UNIVERSE: raise RuntimeError("candidate universe drift")

    priority = json.loads(Path("research/evaluation/v31/p80-track2-priority-coverage.json").read_text())
    existing = {str(r["concept_id"]) for r in priority.get("existing_diversified_v0") or []}
    missing = {str(r["concept_id"]) for r in priority.get("missing_diversified_v0") or []}
    p80 = existing | missing
    if len(p80) != 159: raise RuntimeError("P80 drift")

    _ids, base = load_teacher(Path("research/enrichment/v31/gemma4-yv-a593/phrases.jsonl"))
    a593,_ = load_diverse_training(Path("research/training/v31/a593-language-diversity-training-v0.jsonl"))
    p80t,_ = load_diverse_training(Path("research/training/v31/p80-language-diversity-training-v0.jsonl"))
    rescue,rescue_meta = load_diverse_training(Path("research/training/v31/p80-source-thin-rescue-training-v0.jsonl"))
    rescue_ids = set(rescue_meta)
    primary_ids = sorted(p80 - rescue_ids)
    teacher = {cid:list(v) for cid,v in base.items()}
    add_teacher(teacher,a593,existing); add_teacher(teacher,p80t,missing); add_teacher(teacher,rescue,p80)
    ranker, exact, surfaces = build_ranker(by_id, ids, teacher)

    groups=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        fs={pool.submit(fetch_year_concept,cid,by_id[cid],year,search_limit=25,accepted=5):(cid,year) for cid in primary_ids for year in (CAL_YEAR,EVAL_YEAR)}
        for f in as_completed(fs): groups.append(f.result())
    cases=[r for g in groups for r in g["accepted"]]
    rows=[]
    for case in cases:
        scored=rank_c1(ranker,case["query"],exact,surfaces)
        cs=candidate_features(ranker,case["query"],scored)
        add_local_contrast(ranker,case["query"],cs)
        rows.append({**case,"candidates":cs})
    cal=[r for r in rows if r["year"]==CAL_YEAR]
    ev=[r for r in rows if r["year"]==EVAL_YEAR]
    chosen=choose_zero_loss(cal)
    sel=chosen["selected"]
    result={
        "id":"YV-P80-display-local-contrast-v0",
        "evidence_class":"natural historical Platsbanken task-text proxy; structured target, not human relevance judgment",
        "candidate_universe":2105,
        "ranker_changed":False,
        "opened_17_88_loaded":False,
        "signal":"Top-5-local query-term discrimination only; no query coverage and no reranking",
        "selection_contract":"2023 zero baseline-Hit@5 loss; among frozen formula family minimize visible candidates",
        "selected":sel,
        "calibration_frontier":chosen["frontier"],
        "evaluation":summarize(ev,sel["formula"],float(sel["threshold"])),
        "sample":{"calibration_queries":len(cal),"evaluation_queries":len(ev),"calibration_concepts":len({r['concept_id'] for r in cal}),"evaluation_concepts":len({r['concept_id'] for r in ev})},
    }
    out=Path("research/evaluation/v31/p80-display-local-contrast-v0.json")
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))
    return 0

if __name__ == "__main__": raise SystemExit(main())
