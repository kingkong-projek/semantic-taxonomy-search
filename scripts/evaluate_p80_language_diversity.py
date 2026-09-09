#!/usr/bin/env python3
"""Evaluate P80 language enrichment with the A ranker fixed over all 2,105 YV IDs.

Control is the frozen A593 corpus. Challenger adds only source-bound diversified
phrases for P80 occupations: the already frozen usable P80 subset from v0 plus the
new P80-missing expansion. Opened 17/88 data are deliberately not loaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_a593_language_diversity_falsifier import STYLE_KEYS, load_diverse_training, load_jsonl, load_teacher, metric_delta, summarize
from evaluate_gemma_a149 import build_ranker, canonical_guard, rank_ids
from evaluate_p80_lexical_ablation import expected_hash, fetch

TAXONOMY_URL = "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json"
EXPECTED_P80 = 159
EXPECTED_EXISTING = 41
EXPECTED_MISSING = 118
EXPECTED_UNIVERSE = 2105


def rank_position(ranked: list[str], target: str) -> int:
    try:
        return ranked.index(target) + 1
    except ValueError:
        return len(ranked) + 1


def load_holdout(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in load_jsonl(path):
        cid = str(row.get("concept_id") or "")
        if not cid or cid in out:
            raise RuntimeError(f"invalid/duplicate holdout row: {cid!r}")
        out[cid] = row
    return out


def weighted_summary(rows: list[dict[str, Any]], rank_key: str) -> dict[str, Any]:
    total = sum(float(row["occurrences"]) for row in rows)
    if total <= 0:
        return {"weighted_cases": 0.0, "top1_rate": 0.0, "hit_at_5_rate": 0.0, "mrr": 0.0}
    top1 = sum(float(row["occurrences"]) for row in rows if int(row[rank_key]) == 1) / total
    hit5 = sum(float(row["occurrences"]) for row in rows if int(row[rank_key]) <= 5) / total
    mrr = sum(float(row["occurrences"]) / int(row[rank_key]) for row in rows) / total
    return {"weighted_cases": round(total, 3), "top1_rate": round(top1, 6), "hit_at_5_rate": round(hit5, 6), "mrr": round(mrr, 6)}


def rate_delta(control: dict[str, Any], challenger: dict[str, Any]) -> dict[str, Any]:
    return {
        "top1_rate_pp": round(100 * (challenger["top1_rate"] - control["top1_rate"]), 4),
        "hit_at_5_rate_pp": round(100 * (challenger["hit_at_5_rate"] - control["hit_at_5_rate"]), 4),
        "mrr": round(challenger["mrr"] - control["mrr"], 6),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", default="research/enrichment/v31/gemma4-yv-a593/phrases.jsonl")
    ap.add_argument("--priority", default="research/evaluation/v31/p80-track2-priority-coverage.json")
    ap.add_argument("--existing-training", default="research/training/v31/a593-language-diversity-training-v0.jsonl")
    ap.add_argument("--existing-holdout", default="research/evaluation/v31/a593-language-diversity-holdout-v0.jsonl")
    ap.add_argument("--new-training", default="research/training/v31/p80-language-diversity-training-v0.jsonl")
    ap.add_argument("--new-holdout", default="research/evaluation/v31/p80-language-diversity-holdout-v0.jsonl")
    ap.add_argument("--generation", default="research/evaluation/v31/p80-language-diversity-generation-v0.json")
    ap.add_argument("--source-truth", default="research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl")
    ap.add_argument("--output", default="research/evaluation/v31/p80-language-diversity-result-v0.json")
    args = ap.parse_args()

    priority = json.loads(Path(args.priority).read_text(encoding="utf-8"))
    existing_priority = priority.get("existing_diversified_v0") or []
    missing_priority = priority.get("missing_diversified_v0") or []
    if (int((priority.get("p80") or {}).get("occupation_count", -1)), len(existing_priority), len(missing_priority)) != (EXPECTED_P80, EXPECTED_EXISTING, EXPECTED_MISSING):
        raise RuntimeError("P80 priority population drift")
    occurrence = {str(row["concept_id"]): int(row["occurrences"]) for row in [*existing_priority, *missing_priority]}
    p80_ids = set(occurrence)
    existing_ids = {str(row["concept_id"]) for row in existing_priority}
    missing_ids = {str(row["concept_id"]) for row in missing_priority}
    if len(p80_ids) != EXPECTED_P80 or existing_ids & missing_ids:
        raise RuntimeError("P80 partition invalid")

    generation = json.loads(Path(args.generation).read_text(encoding="utf-8"))
    if generation.get("generation", {}).get("opened_17_88_loaded") is True or generation.get("selection", {}).get("opened_outcomes_used") is True:
        raise RuntimeError("generation leakage marker")

    registry = json.loads(Path("research/coverage/source-adapters.json").read_text(encoding="utf-8"))
    taxonomy_wire = fetch(TAXONOMY_URL)
    taxonomy_sha = hashlib.sha256(taxonomy_wire).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations") or taxonomy_sha != generation.get("taxonomy_sha256"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(taxonomy_wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid, concept in by_id.items() if concept.get("type") == "occupation-name")
    if len(ids) != EXPECTED_UNIVERSE or not p80_ids <= set(ids):
        raise RuntimeError("full active YV universe drift")

    _, a593_teacher = load_teacher(Path(args.teacher))
    existing_diverse, existing_meta = load_diverse_training(Path(args.existing_training))
    new_diverse, new_meta = load_diverse_training(Path(args.new_training))
    existing_diverse = {cid: values for cid, values in existing_diverse.items() if cid in existing_ids}
    new_diverse = {cid: values for cid, values in new_diverse.items() if cid in missing_ids}
    if set(existing_diverse) - p80_ids or set(new_diverse) - p80_ids:
        raise RuntimeError("non-P80 diversified phrase entered P80 challenger")

    challenger_teacher = {cid: list(values) for cid, values in a593_teacher.items()}
    for source in (existing_diverse, new_diverse):
        for cid, values in source.items():
            challenger_teacher.setdefault(cid, []).extend(values)

    control_ranker, control_exact, control_surfaces = build_ranker(by_id, ids, a593_teacher)
    challenger_ranker, challenger_exact, challenger_surfaces = build_ranker(by_id, ids, challenger_teacher)

    existing_holdout = load_holdout(Path(args.existing_holdout))
    new_holdout = load_holdout(Path(args.new_holdout))
    training_meta = {cid: row for cid, row in existing_meta.items() if cid in existing_ids}
    training_meta.update({cid: row for cid, row in new_meta.items() if cid in missing_ids})
    holdout_meta = {cid: row for cid, row in existing_holdout.items() if cid in existing_ids}
    holdout_meta.update({cid: row for cid, row in new_holdout.items() if cid in missing_ids})

    rows: list[dict[str, Any]] = []
    usable_concepts: set[str] = set()
    for cid in sorted(p80_ids, key=lambda value: (-occurrence[value], value)):
        train = training_meta.get(cid)
        hold = holdout_meta.get(cid)
        if not train or not hold or not train.get("usable") or not hold.get("usable"):
            continue
        usable_concepts.add(cid)
        for style in STYLE_KEYS:
            query = (hold.get("queries") or {}).get(style)
            if not isinstance(query, str) or not query.strip():
                continue
            control_ranked = rank_ids(control_ranker, control_exact, control_surfaces, query)
            challenger_ranked = rank_ids(challenger_ranker, challenger_exact, challenger_surfaces, query)
            rows.append({
                "concept_id": cid,
                "label": str(by_id[cid].get("preferred_label") or cid),
                "p80_occurrences": occurrence[cid],
                "occurrences": occurrence[cid],
                "style": style,
                "query": query,
                "control_rank": rank_position(control_ranked, cid),
                "challenger_rank": rank_position(challenger_ranked, cid),
                "control_top5": control_ranked[:5],
                "challenger_top5": challenger_ranked[:5],
            })
    if len(usable_concepts) < 80 or len(rows) < 240:
        raise RuntimeError(f"P80 holdout too small: concepts={len(usable_concepts)} cases={len(rows)}")

    control = summarize(rows, "control_rank")
    challenger = summarize(rows, "challenger_rank")
    delta = metric_delta(control, challenger)
    weighted_control = weighted_summary(rows, "control_rank")
    weighted_challenger = weighted_summary(rows, "challenger_rank")
    weighted_delta = rate_delta(weighted_control, weighted_challenger)

    by_style: dict[str, Any] = {}
    for style in STYLE_KEYS:
        subset = [row for row in rows if row["style"] == style]
        c = summarize(subset, "control_rank")
        h = summarize(subset, "challenger_rank")
        wc = weighted_summary(subset, "control_rank")
        wh = weighted_summary(subset, "challenger_rank")
        by_style[style] = {"control": c, "challenger": h, "delta": metric_delta(c, h), "demand_weighted_control": wc, "demand_weighted_challenger": wh, "demand_weighted_delta": rate_delta(wc, wh)}

    source_truth = load_jsonl(Path(args.source_truth))
    if len(source_truth) != 333:
        raise RuntimeError(f"canonical source-truth drift: {len(source_truth)}")
    canonical_control = canonical_guard(source_truth, control_ranker, control_exact, control_surfaces)
    canonical_challenger = canonical_guard(source_truth, challenger_ranker, challenger_exact, challenger_surfaces)
    canonical_no_regression = (
        canonical_challenger["top1"] >= canonical_control["top1"]
        and canonical_challenger["hit_at_5"] >= canonical_control["hit_at_5"]
    )

    style_deltas = {style: by_style[style]["delta"]["top1_rate_pp"] for style in STYLE_KEYS}
    semantic_styles = ("shift_story", "plain_search", "outcome_context")
    coverage_ok = len(usable_concepts) >= 100
    materiality = (
        coverage_ok
        and delta["top1_rate_pp"] >= 5.0
        and min(style_deltas.values()) > -5.0
        and max(style_deltas[style] for style in semantic_styles) >= 5.0
        and weighted_delta["top1_rate_pp"] > 0.0
        and canonical_no_regression
    )

    result = {
        "id": "YV-A593-P80-language-diversity-v0",
        "evidence_class": "prefrozen source-bound synthetic P80 mechanism test; not human accuracy",
        "candidate": {
            "control": "frozen A593 over all 2,105 active YV identities",
            "challenger": "same ranker/full 2,105 universe + frozen diversified P80 language where source evidence supports it",
            "ranker_changed": False,
            "candidate_universe": EXPECTED_UNIVERSE,
            "candidate_universe_changed": False,
            "opened_17_88_loaded": False,
        },
        "p80": {
            "occupation_count": EXPECTED_P80,
            "existing_diversified_v0_usable_for_challenger": len(existing_diverse),
            "new_diversified_usable_for_challenger": len(new_diverse),
            "jointly_usable_holdout_concepts": len(usable_concepts),
            "holdout_cases": len(rows),
        },
        "primary_p80_holdout": {
            "control": control,
            "challenger": challenger,
            "delta": delta,
            "demand_weighted_control": weighted_control,
            "demand_weighted_challenger": weighted_challenger,
            "demand_weighted_delta": weighted_delta,
            "by_style": by_style,
            "paired_changes": {
                "rank_improved": sum(row["challenger_rank"] < row["control_rank"] for row in rows),
                "rank_worsened": sum(row["challenger_rank"] > row["control_rank"] for row in rows),
                "rank_unchanged": sum(row["challenger_rank"] == row["control_rank"] for row in rows),
                "top1_gains": sum(row["control_rank"] != 1 and row["challenger_rank"] == 1 for row in rows),
                "top1_losses": sum(row["control_rank"] == 1 and row["challenger_rank"] != 1 for row in rows),
                "hit5_gains": sum(row["control_rank"] > 5 and row["challenger_rank"] <= 5 for row in rows),
                "hit5_losses": sum(row["control_rank"] <= 5 and row["challenger_rank"] > 5 for row in rows),
            },
        },
        "canonical_source_truth_guard": {"control": canonical_control, "challenger": canonical_challenger, "no_regression": canonical_no_regression},
        "materiality_gate": {
            "passed": materiality,
            "coverage_passed": coverage_ok,
            "rule": "P80 jointly usable >=100; overall Top1 >=+5pp; no style <=-5pp; one semantic style >=+5pp; demand-weighted Top1 positive; canonical Top1/Hit@5 non-regressing",
        },
        "generation": generation,
        "decision": {
            "if_pass": "freeze challenger and run the already-planned small independent human P80 confirmation before promotion",
            "if_fail": "do not add architecture; inspect coverage/error distribution and keep current A593 deployed",
        },
        "evidence_warning": "The holdout is separately generated but model-authored. It tests the mechanism under full-universe competition; it does not replace independent human evaluation.",
        "rows": rows,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "p80_jointly_usable": len(usable_concepts),
        "cases": len(rows),
        "control": control,
        "challenger": challenger,
        "delta": delta,
        "demand_weighted_delta": weighted_delta,
        "canonical_guard": result["canonical_source_truth_guard"],
        "materiality_gate": result["materiality_gate"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
