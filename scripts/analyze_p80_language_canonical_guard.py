#!/usr/bin/env python3
"""Explain canonical source-truth rank changes caused by the P80 language challenger."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evaluate_a593_language_diversity_falsifier import load_diverse_training, load_jsonl, load_teacher
from evaluate_gemma_a149 import build_ranker, rank_ids
from evaluate_p80_lexical_ablation import expected_hash, fetch

TAXONOMY_URL = "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json"


def pos(ranked: list[str], target: str) -> int | None:
    try:
        return ranked.index(target) + 1
    except ValueError:
        return None


def main() -> int:
    priority = json.loads(Path("research/evaluation/v31/p80-track2-priority-coverage.json").read_text())
    existing_ids = {str(row["concept_id"]) for row in priority["existing_diversified_v0"]}
    missing_ids = {str(row["concept_id"]) for row in priority["missing_diversified_v0"]}
    _, teacher = load_teacher(Path("research/enrichment/v31/gemma4-yv-a593/phrases.jsonl"))
    existing, _ = load_diverse_training(Path("research/training/v31/a593-language-diversity-training-v0.jsonl"))
    new, _ = load_diverse_training(Path("research/training/v31/p80-language-diversity-training-v0.jsonl"))
    challenger = {cid: list(values) for cid, values in teacher.items()}
    for cid, values in existing.items():
        if cid in existing_ids:
            challenger.setdefault(cid, []).extend(values)
    for cid, values in new.items():
        if cid in missing_ids:
            challenger.setdefault(cid, []).extend(values)

    registry = json.loads(Path("research/coverage/source-adapters.json").read_text())
    wire = fetch(TAXONOMY_URL)
    if hashlib.sha256(wire).hexdigest() != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    control_ranker, control_exact, control_surfaces = build_ranker(by_id, ids, teacher)
    challenger_ranker, challenger_exact, challenger_surfaces = build_ranker(by_id, ids, challenger)

    changes = []
    for case in load_jsonl(Path("research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl")):
        target = str(case["must"][0]["concept_id"])
        query = str(case["query"])
        c = rank_ids(control_ranker, control_exact, control_surfaces, query)
        h = rank_ids(challenger_ranker, challenger_exact, challenger_surfaces, query)
        cr, hr = pos(c, target), pos(h, target)
        if cr != hr or c[:1] != h[:1]:
            changes.append({
                "case_id": case["id"],
                "query_origin": case.get("query_origin"),
                "strata": case.get("strata"),
                "target_id": target,
                "target_label": case["must"][0].get("label"),
                "control_rank": cr,
                "challenger_rank": hr,
                "control_top5": c[:5],
                "challenger_top5": h[:5],
                "top1_regression": cr == 1 and hr != 1,
                "top1_gain": cr != 1 and hr == 1,
            })
    result = {
        "id": "YV-A593-P80-language-canonical-guard-diagnosis-v0",
        "candidate_universe": len(ids),
        "opened_17_88_loaded": False,
        "changed_cases": len(changes),
        "top1_regressions": sum(row["top1_regression"] for row in changes),
        "top1_gains": sum(row["top1_gain"] for row in changes),
        "changes": changes,
    }
    out = Path("research/evaluation/v31/p80-language-diversity-canonical-guard-diagnosis-v0.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
