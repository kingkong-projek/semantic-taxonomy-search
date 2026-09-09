#!/usr/bin/env python3
"""Evaluate source-thin P80 rescue against the current P80 challenger over all 2,105 occupations.

Primary: separate rescue holdout for the 22 canonical-thin occupations.
Safety: frozen 426-case P80 holdout + 333 canonical source-truth rows.
Opened 17/88 is never loaded. Ranker and candidate universe are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_a593_language_diversity_falsifier import STYLE_KEYS, load_diverse_training, load_jsonl, load_teacher, metric_delta, summarize
from evaluate_gemma_a149 import build_ranker, rank_ids
from evaluate_p80_lexical_ablation import expected_hash, fetch
from evaluate_p80_language_diversity import load_holdout, rank_position

TAXONOMY_URL = "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json"
EXPECTED_UNIVERSE = 2105
EXPECTED_RESCUE = 22


def eval_rows(holdout: dict[str, dict[str, Any]], allowed_ids: set[str], meta: dict[str, dict[str, Any]], control, challenger) -> list[dict[str, Any]]:
    cr, ce, cs = control
    hr, he, hs = challenger
    rows = []
    for cid in sorted(allowed_ids):
        train = meta.get(cid)
        hold = holdout.get(cid)
        if not train or not hold or not train.get("usable") or not hold.get("usable"):
            continue
        for style in STYLE_KEYS:
            query = (hold.get("queries") or {}).get(style)
            if not isinstance(query, str) or not query.strip():
                continue
            a = rank_ids(cr, ce, cs, query)
            b = rank_ids(hr, he, hs, query)
            rows.append({"concept_id": cid, "style": style, "query": query, "control_rank": rank_position(a, cid), "challenger_rank": rank_position(b, cid)})
    return rows


def summarize_pair(rows: list[dict[str, Any]]) -> dict[str, Any]:
    c = summarize(rows, "control_rank")
    h = summarize(rows, "challenger_rank")
    by_style = {}
    for style in STYLE_KEYS:
        subset = [r for r in rows if r["style"] == style]
        sc = summarize(subset, "control_rank")
        sh = summarize(subset, "challenger_rank")
        by_style[style] = {"control": sc, "challenger": sh, "delta": metric_delta(sc, sh)}
    return {
        "control": c,
        "challenger": h,
        "delta": metric_delta(c, h),
        "by_style": by_style,
        "paired_changes": {
            "rank_improved": sum(r["challenger_rank"] < r["control_rank"] for r in rows),
            "rank_worsened": sum(r["challenger_rank"] > r["control_rank"] for r in rows),
            "top1_gains": sum(r["control_rank"] != 1 and r["challenger_rank"] == 1 for r in rows),
            "top1_losses": sum(r["control_rank"] == 1 and r["challenger_rank"] != 1 for r in rows),
            "hit5_gains": sum(r["control_rank"] > 5 and r["challenger_rank"] <= 5 for r in rows),
            "hit5_losses": sum(r["control_rank"] <= 5 and r["challenger_rank"] > 5 for r in rows),
        },
    }


def canonical_guard(rows: list[dict[str, Any]], control, challenger) -> dict[str, Any]:
    cr, ce, cs = control
    hr, he, hs = challenger
    out = []
    for row in rows:
        target = str((row.get("must") or [{}])[0].get("concept_id") or "")
        query = str(row.get("query") or "")
        a = rank_ids(cr, ce, cs, query)
        b = rank_ids(hr, he, hs, query)
        out.append({
            "id": row.get("id"), "query_origin": row.get("query_origin"), "target": target,
            "control_rank": rank_position(a, target), "challenger_rank": rank_position(b, target),
        })
    exact = [r for r in out if r["query_origin"] == "canonical_label"]
    return {
        "cases": len(out),
        "control_top1": sum(r["control_rank"] == 1 for r in out),
        "challenger_top1": sum(r["challenger_rank"] == 1 for r in out),
        "control_hit5": sum(r["control_rank"] <= 5 for r in out),
        "challenger_hit5": sum(r["challenger_rank"] <= 5 for r in out),
        "exact_label_cases": len(exact),
        "exact_label_control_top1": sum(r["control_rank"] == 1 for r in exact),
        "exact_label_challenger_top1": sum(r["challenger_rank"] == 1 for r in exact),
        "changed": [r for r in out if r["control_rank"] != r["challenger_rank"]],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", default="research/enrichment/v31/gemma4-yv-a593/phrases.jsonl")
    ap.add_argument("--priority", default="research/evaluation/v31/p80-track2-priority-coverage.json")
    ap.add_argument("--existing-training", default="research/training/v31/a593-language-diversity-training-v0.jsonl")
    ap.add_argument("--p80-training", default="research/training/v31/p80-language-diversity-training-v0.jsonl")
    ap.add_argument("--existing-holdout", default="research/evaluation/v31/a593-language-diversity-holdout-v0.jsonl")
    ap.add_argument("--p80-holdout", default="research/evaluation/v31/p80-language-diversity-holdout-v0.jsonl")
    ap.add_argument("--rescue-training", default="research/training/v31/p80-source-thin-rescue-training-v0.jsonl")
    ap.add_argument("--rescue-holdout", default="research/evaluation/v31/p80-source-thin-rescue-holdout-v0.jsonl")
    ap.add_argument("--generation", default="research/evaluation/v31/p80-source-thin-rescue-generation-v0.json")
    ap.add_argument("--source-truth", default="research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl")
    ap.add_argument("--output", default="research/evaluation/v31/p80-source-thin-rescue-result-v0.json")
    args = ap.parse_args()

    generation = json.loads(Path(args.generation).read_text(encoding="utf-8"))
    if generation.get("opened_17_88_loaded") or generation.get("retrieval_outcomes_used"):
        raise RuntimeError("rescue generation leakage marker")

    priority = json.loads(Path(args.priority).read_text(encoding="utf-8"))
    existing_ids = {str(r["concept_id"]) for r in priority.get("existing_diversified_v0") or []}
    missing_ids = {str(r["concept_id"]) for r in priority.get("missing_diversified_v0") or []}
    p80_ids = existing_ids | missing_ids
    if len(p80_ids) != 159:
        raise RuntimeError("P80 population drift")

    registry = json.loads(Path("research/coverage/source-adapters.json").read_text(encoding="utf-8"))
    wire = fetch(TAXONOMY_URL)
    sha = hashlib.sha256(wire).hexdigest()
    if sha != expected_hash(registry, "taxonomy-common-relations") or sha != generation.get("taxonomy_sha256"):
        raise RuntimeError("taxonomy drift")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != EXPECTED_UNIVERSE:
        raise RuntimeError("candidate universe drift")

    _, base_teacher = load_teacher(Path(args.teacher))
    existing, existing_meta = load_diverse_training(Path(args.existing_training))
    p80_new, p80_meta = load_diverse_training(Path(args.p80_training))
    rescue, rescue_meta = load_diverse_training(Path(args.rescue_training))
    existing = {cid: v for cid, v in existing.items() if cid in existing_ids}
    p80_new = {cid: v for cid, v in p80_new.items() if cid in missing_ids}
    if len(rescue_meta) != EXPECTED_RESCUE or set(rescue_meta) - p80_ids:
        raise RuntimeError("rescue identity drift")
    rescue_ids = set(rescue_meta)

    current_teacher = {cid: list(v) for cid, v in base_teacher.items()}
    for source in (existing, p80_new):
        for cid, values in source.items():
            current_teacher.setdefault(cid, []).extend(values)
    rescue_teacher = {cid: list(v) for cid, v in current_teacher.items()}
    for cid, values in rescue.items():
        rescue_teacher.setdefault(cid, []).extend(values)

    current = build_ranker(by_id, ids, current_teacher)
    challenger = build_ranker(by_id, ids, rescue_teacher)

    rescue_hold = load_holdout(Path(args.rescue_holdout))
    primary_rows = eval_rows(rescue_hold, rescue_ids, rescue_meta, current, challenger)
    usable_primary = len({r["concept_id"] for r in primary_rows})
    if usable_primary < 10:
        raise RuntimeError(f"rescue holdout too small: {usable_primary}")
    primary = summarize_pair(primary_rows)

    existing_hold = load_holdout(Path(args.existing_holdout))
    p80_hold = load_holdout(Path(args.p80_holdout))
    safety_meta = {cid: row for cid, row in existing_meta.items() if cid in existing_ids}
    safety_meta.update({cid: row for cid, row in p80_meta.items() if cid in missing_ids and cid not in rescue_ids})
    safety_hold = {cid: row for cid, row in existing_hold.items() if cid in existing_ids}
    safety_hold.update({cid: row for cid, row in p80_hold.items() if cid in missing_ids and cid not in rescue_ids})
    safety_ids = set(safety_meta) & set(safety_hold)
    safety_rows = eval_rows(safety_hold, safety_ids, safety_meta, current, challenger)
    safety = summarize_pair(safety_rows)

    source_truth = load_jsonl(Path(args.source_truth))
    if len(source_truth) != 333:
        raise RuntimeError("source-truth drift")
    canonical = canonical_guard(source_truth, current, challenger)

    style_deltas = [primary["by_style"][s]["delta"]["top1_rate_pp"] for s in STYLE_KEYS if primary["by_style"][s]["control"]["cases"]]
    gate = (
        usable_primary >= 15
        and primary["delta"]["top1_rate_pp"] >= 5.0
        and primary["delta"]["hit_at_5_rate_pp"] >= 0.0
        and min(style_deltas) > -5.0
        and safety["delta"]["top1_rate_pp"] >= -1.0
        and safety["delta"]["hit_at_5_rate_pp"] >= -1.0
        and canonical["challenger_hit5"] >= canonical["control_hit5"]
        and canonical["exact_label_challenger_top1"] >= canonical["exact_label_control_top1"]
    )

    result = {
        "id": "YV-P80-source-thin-rescue-v0",
        "evidence_class": "prefrozen source-enrichment synthetic mechanism test; not human accuracy",
        "candidate": {
            "control": "current frozen P80 challenger over all 2,105 active occupations",
            "challenger": "same ranker/universe + source-enriched diversified phrases for canonical-thin P80 identities",
            "ranker_changed": False, "candidate_universe": EXPECTED_UNIVERSE, "opened_17_88_loaded": False,
        },
        "rescue": {"requested_concepts": EXPECTED_RESCUE, "usable_concepts": usable_primary, "primary_holdout": primary},
        "existing_p80_safety_holdout": {"concepts": len({r["concept_id"] for r in safety_rows}), "cases": len(safety_rows), **safety},
        "canonical_guard": canonical,
        "materiality_gate": {
            "passed": gate,
            "rule": "rescue usable>=15; rescue Top1>=+5pp and Hit@5 nonnegative; no style <=-5pp; existing-P80 Top1/Hit@5 each >=-1pp; canonical Hit@5 and exact-label Top1 nonregressing",
        },
        "generation": generation,
        "decision": {
            "if_pass": "keep rescue in the frozen P80 candidate for future human confirmation; no architecture change",
            "if_fail": "retain current P80 candidate; do not rescue with additional model layers",
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "usable_rescue_concepts": usable_primary,
        "primary": primary,
        "safety_delta": safety["delta"],
        "canonical_guard": {k: v for k, v in canonical.items() if k != "changed"},
        "gate": result["materiality_gate"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
