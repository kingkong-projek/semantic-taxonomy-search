#!/usr/bin/env python3
"""Evaluate the prefrozen A593 training-language distribution falsifier.

This script intentionally keeps the A-family ranker fixed. It compares:
  control: canonical source evidence + the frozen 8 A593 teacher phrases;
  challenger: identical ranker/data + the separately frozen diversified phrases.

The primary proxy is the separately generated held-out corpus. Opened 17/88 files are
never loaded. The existing frozen 66-case hard-confusion descriptions are secondary
replay evidence only.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_gemma_a149 import build_ranker, rank_ids
from evaluate_p80_lexical_ablation import expected_hash, fetch

TAXONOMY_URL = (
    "https://data.jobtechdev.se/taxonomy/version/31/query/"
    "concepts-and-common-relations/concepts-and-common-relations.json"
)
EXPECTED_A593 = 593
STYLE_KEYS = ("shift_story", "plain_search", "compressed_note", "outcome_context")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_teacher(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    rows = load_jsonl(path)
    if len(rows) != EXPECTED_A593:
        raise RuntimeError(f"teacher row drift: {len(rows)} != {EXPECTED_A593}")
    ids: list[str] = []
    teacher: dict[str, list[str]] = {}
    for row in rows:
        cid = str(row.get("concept_id") or "")
        phrases = [str(x).strip() for x in row.get("phrases") or [] if str(x).strip()]
        if not cid or cid in teacher or len(phrases) != 8:
            raise RuntimeError(f"invalid teacher row {cid!r}")
        ids.append(cid)
        teacher[cid] = phrases
    return ids, teacher


def load_diverse_training(path: Path) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    rows = load_jsonl(path)
    out: dict[str, list[str]] = {}
    meta: dict[str, dict[str, Any]] = {}
    for row in rows:
        cid = str(row.get("concept_id") or "")
        if not cid or cid in meta:
            raise RuntimeError("invalid/duplicate diversified training row")
        values = row.get("phrases") or {}
        phrases = [str(x).strip() for x in values.values() if isinstance(x, str) and x.strip()]
        meta[cid] = row
        if row.get("usable") and len(phrases) >= 3:
            out[cid] = phrases
    return out, meta


def rank_position(ranked: list[str], target: str) -> int:
    try:
        return ranked.index(target) + 1
    except ValueError:
        return len(ranked) + 1


def summarize(rows: list[dict[str, Any]], rank_key: str) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"cases": 0, "top1_count": 0, "top1_rate": 0.0, "hit_at_5_count": 0, "hit_at_5_rate": 0.0, "mrr": 0.0}
    ranks = [int(row[rank_key]) for row in rows]
    return {
        "cases": n,
        "top1_count": sum(r == 1 for r in ranks),
        "top1_rate": round(sum(r == 1 for r in ranks) / n, 6),
        "hit_at_5_count": sum(r <= 5 for r in ranks),
        "hit_at_5_rate": round(sum(r <= 5 for r in ranks) / n, 6),
        "mrr": round(sum(1.0 / r for r in ranks) / n, 6),
        "median_rank": sorted(ranks)[n // 2],
    }


def metric_delta(control: dict[str, Any], challenger: dict[str, Any]) -> dict[str, Any]:
    return {
        "top1_count": challenger["top1_count"] - control["top1_count"],
        "top1_rate_pp": round(100.0 * (challenger["top1_rate"] - control["top1_rate"]), 4),
        "hit_at_5_count": challenger["hit_at_5_count"] - control["hit_at_5_count"],
        "hit_at_5_rate_pp": round(100.0 * (challenger["hit_at_5_rate"] - control["hit_at_5_rate"]), 4),
        "mrr": round(challenger["mrr"] - control["mrr"], 6),
    }


def evaluate_holdout(
    holdout_path: Path,
    training_meta: dict[str, dict[str, Any]],
    baseline_ranker,
    baseline_exact,
    baseline_surfaces,
    challenger_ranker,
    challenger_exact,
    challenger_surfaces,
) -> dict[str, Any]:
    rows = []
    for row in load_jsonl(holdout_path):
        cid = str(row.get("concept_id") or "")
        train = training_meta.get(cid)
        if not train or not train.get("usable") or not row.get("usable"):
            continue
        queries = row.get("queries") or {}
        for style in STYLE_KEYS:
            query = queries.get(style)
            if not isinstance(query, str) or not query.strip():
                continue
            base = rank_ids(baseline_ranker, baseline_exact, baseline_surfaces, query)
            chall = rank_ids(challenger_ranker, challenger_exact, challenger_surfaces, query)
            brank = rank_position(base, cid)
            crank = rank_position(chall, cid)
            rows.append({
                "concept_id": cid,
                "label": row.get("label"),
                "selection_reason": row.get("selection_reason"),
                "style": style,
                "query": query,
                "control_rank": brank,
                "challenger_rank": crank,
                "rank_delta": brank - crank,
                "control_top5": base[:5],
                "challenger_top5": chall[:5],
            })
    if len({row["concept_id"] for row in rows}) < 80 or len(rows) < 240:
        raise RuntimeError(f"heldout proxy too small after validity filtering: concepts={len({r['concept_id'] for r in rows})}, cases={len(rows)}")
    control = summarize(rows, "control_rank")
    challenger = summarize(rows, "challenger_rank")
    by_style = {}
    for style in STYLE_KEYS:
        subset = [x for x in rows if x["style"] == style]
        c = summarize(subset, "control_rank")
        h = summarize(subset, "challenger_rank")
        by_style[style] = {"control": c, "challenger": h, "delta": metric_delta(c, h)}
    by_selection = {}
    for reason in sorted({str(x["selection_reason"]) for x in rows}):
        subset = [x for x in rows if x["selection_reason"] == reason]
        c = summarize(subset, "control_rank")
        h = summarize(subset, "challenger_rank")
        by_selection[reason] = {"control": c, "challenger": h, "delta": metric_delta(c, h)}
    changed = {
        "rank_improved": sum(x["challenger_rank"] < x["control_rank"] for x in rows),
        "rank_worsened": sum(x["challenger_rank"] > x["control_rank"] for x in rows),
        "rank_unchanged": sum(x["challenger_rank"] == x["control_rank"] for x in rows),
        "top1_gains": sum(x["control_rank"] != 1 and x["challenger_rank"] == 1 for x in rows),
        "top1_losses": sum(x["control_rank"] == 1 and x["challenger_rank"] != 1 for x in rows),
        "hit5_gains": sum(x["control_rank"] > 5 and x["challenger_rank"] <= 5 for x in rows),
        "hit5_losses": sum(x["control_rank"] <= 5 and x["challenger_rank"] > 5 for x in rows),
    }
    overall_delta = metric_delta(control, challenger)
    style_deltas = {style: by_style[style]["delta"]["top1_rate_pp"] for style in STYLE_KEYS}
    semantic_styles = ("shift_story", "plain_search", "outcome_context")
    materiality_passed = (
        overall_delta["top1_rate_pp"] >= 5.0
        and min(style_deltas.values()) > -5.0
        and max(style_deltas[s] for s in semantic_styles) >= 5.0
    )
    return {
        "control": control,
        "challenger": challenger,
        "delta": overall_delta,
        "by_style": by_style,
        "by_selection_reason": by_selection,
        "paired_changes": changed,
        "materiality_gate": {
            "rule": "overall Top1 >= +5pp; no style <= -5pp; at least one non-telegraphic user-language style >= +5pp",
            "passed": materiality_passed,
        },
        "rows": rows,
    }


def evaluate_hard_confusion(
    path: Path,
    baseline_ranker,
    baseline_exact,
    baseline_surfaces,
    challenger_ranker,
    challenger_exact,
    challenger_surfaces,
) -> dict[str, Any]:
    rows = []
    for pair_index, pair in enumerate(load_jsonl(path)):
        contrast = pair.get("contrast") or {}
        if not contrast.get("distinguishable"):
            continue
        for side in ("a", "b"):
            target = str(pair.get(f"{side}_concept_id") or "")
            descriptions = contrast.get(f"{side}_descriptions") or []
            for i, query in enumerate(descriptions):
                if not isinstance(query, str) or not query.strip():
                    continue
                base = rank_ids(baseline_ranker, baseline_exact, baseline_surfaces, query)
                chall = rank_ids(challenger_ranker, challenger_exact, challenger_surfaces, query)
                rows.append({
                    "pair_index": pair_index,
                    "side": side,
                    "target": target,
                    "description_index": i,
                    "control_rank": rank_position(base, target),
                    "challenger_rank": rank_position(chall, target),
                })
    if len(rows) != 66:
        raise RuntimeError(f"hard-confusion replay drift: {len(rows)} != 66")
    c = summarize(rows, "control_rank")
    h = summarize(rows, "challenger_rank")
    return {"control": c, "challenger": h, "delta": metric_delta(c, h), "rows": rows}


def compact_increment_size(diverse: dict[str, list[str]]) -> dict[str, int]:
    raw = json.dumps(diverse, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"raw_bytes": len(raw), "gzip9_bytes": len(gzip.compress(raw, compresslevel=9)), "phrases": sum(len(v) for v in diverse.values())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--training", default="research/training/v31/a593-language-diversity-training-v0.jsonl")
    ap.add_argument("--holdout", default="research/evaluation/v31/a593-language-diversity-holdout-v0.jsonl")
    ap.add_argument("--generation-summary", default="research/evaluation/v31/a593-language-diversity-generation-v0.json")
    ap.add_argument("--confusions", default="research/training/v31/a593-gemma4-sniper-contrasts-v0.jsonl")
    ap.add_argument("--output", default="artifacts/a593-language-diversity-result-v0.json")
    args = ap.parse_args()

    ids, old_teacher = load_teacher(Path(args.teacher))
    diverse, training_meta = load_diverse_training(Path(args.training))
    generation = json.loads(Path(args.generation_summary).read_text(encoding="utf-8"))
    if generation.get("opened_17_88_loaded") is True:
        raise RuntimeError("generation summary indicates opened-query leakage")

    registry = json.loads(Path("research/coverage/source-adapters.json").read_text(encoding="utf-8"))
    taxonomy_wire = fetch(TAXONOMY_URL)
    actual_hash = hashlib.sha256(taxonomy_wire).hexdigest()
    expected = expected_hash(registry, "taxonomy-common-relations")
    if actual_hash != expected or actual_hash != generation.get("taxonomy_sha256"):
        raise RuntimeError("taxonomy source drift versus generation")
    taxonomy = json.loads(taxonomy_wire)
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    if any(cid not in by_id for cid in ids):
        raise RuntimeError("A593 identity missing from taxonomy")

    challenger_teacher = {cid: list(values) for cid, values in old_teacher.items()}
    for cid, values in diverse.items():
        if cid not in challenger_teacher:
            raise RuntimeError(f"diversified phrase for non-A593 concept {cid}")
        challenger_teacher[cid] = challenger_teacher[cid] + values

    baseline_ranker, baseline_exact, baseline_surfaces = build_ranker(by_id, ids, old_teacher)
    challenger_ranker, challenger_exact, challenger_surfaces = build_ranker(by_id, ids, challenger_teacher)

    holdout = evaluate_holdout(
        Path(args.holdout), training_meta,
        baseline_ranker, baseline_exact, baseline_surfaces,
        challenger_ranker, challenger_exact, challenger_surfaces,
    )
    hard_confusion = evaluate_hard_confusion(
        Path(args.confusions),
        baseline_ranker, baseline_exact, baseline_surfaces,
        challenger_ranker, challenger_exact, challenger_surfaces,
    )

    result = {
        "id": "YV-A593-language-diversity-v0",
        "evidence_class": "prefrozen source-bound synthetic training-distribution falsifier; not human accuracy",
        "candidate": {
            "control": "unchanged A593 canonical source + 8 frozen Gemma phrases, flattened token BM25",
            "challenger": "same ranker and A593 universe + separately generated lexically distant source-bound phrases on selected concepts",
            "ranker_changed": false,
            "candidate_universe_changed": false,
            "opened_17_88_loaded": false,
        },
        "generation_summary": generation,
        "diversified_training": {
            "usable_concepts": len(diverse),
            **compact_increment_size(diverse),
        },
        "primary_heldout_proxy": holdout,
        "secondary_hard_confusion_replay": hard_confusion,
        "decision": {
            "materiality_gate_passed": holdout["materiality_gate"]["passed"],
            "next_if_pass": "one frozen opened 17/88 replay, then decide whether to scale diversified language",
            "next_if_fail": "do not scale language generation or add architecture layers; record plateau and reassess evidence/API escape hatch",
        },
        "evidence_warning": "Heldout and hard-confusion data are model-authored/source-bound. They can falsify transfer mechanisms but are not independent user accuracy evidence.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "id": result["id"],
        "usable_concepts": result["diversified_training"]["usable_concepts"],
        "increment_gzip9_bytes": result["diversified_training"]["gzip9_bytes"],
        "heldout_control": holdout["control"],
        "heldout_challenger": holdout["challenger"],
        "heldout_delta": holdout["delta"],
        "materiality_gate_passed": holdout["materiality_gate"]["passed"],
        "hard_confusion_delta": hard_confusion["delta"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
