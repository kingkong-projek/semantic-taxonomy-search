#!/usr/bin/env python3
"""One-time opened 17/88 replay for the prefrozen A593 language-diversity candidate.

The candidate, diversified corpus and +5pp gate were frozen before this script reads
opened diagnostics. This replay must not be used to tune phrases, ranker or thresholds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import evaluate_gemma_a149 as base
import evaluate_a593_language_diversity_falsifier as lang
from evaluate_p80_lexical_ablation import expected_hash, fetch
from evaluate_yv_full_description_canonical import SOURCE_URL

TAXONOMY_URL = lang.TAXONOMY_URL


def targetable(summary):
    names = ("direct", "colloquial", "noisy", "indirect")
    cats = summary["categories"]
    return {
        "cases": 40,
        "top1_family_hit": sum(cats[name]["top1_family_hit"] for name in names),
        "top5_family_hit": sum(cats[name]["top5_family_hit"] for name in names),
    }


def changed_stress_rows(control, challenger):
    out = []
    for before, after in zip(control["rows"], challenger["rows"], strict=True):
        if (before["expected_family_rank"], before["top5"], before["empty"]) == (
            after["expected_family_rank"], after["top5"], after["empty"]
        ):
            continue
        br, ar = before["expected_family_rank"], after["expected_family_rank"]
        out.append({
            "id": before["id"],
            "category": before["category"],
            "query": before["query"],
            "expected": before["expected"],
            "control_family_rank": br,
            "challenger_family_rank": ar,
            "control_top5": before["top5"],
            "challenger_top5": after["top5"],
            "hit5_delta": int(ar is not None and ar <= 5) - int(br is not None and br <= 5),
            "top1_delta": int(ar == 1) - int(br == 1),
        })
    return out


def changed_strict_rows(control, challenger):
    out = []
    for before, after in zip(control["rows"], challenger["rows"], strict=True):
        if (before["rank"], before["top5"]) == (after["rank"], after["top5"]):
            continue
        br, ar = before["rank"], after["rank"]
        out.append({
            "source_slug": before["source_slug"],
            "target_id": before["target_id"],
            "target_label": before["target_label"],
            "control_rank": br,
            "challenger_rank": ar,
            "control_top5": before["top5"],
            "challenger_top5": after["top5"],
            "hit5_delta": int(ar is not None and ar <= 5) - int(br is not None and br <= 5),
            "top1_delta": int(ar == 1) - int(br == 1),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--training", default="research/training/v31/a593-language-diversity-training-v0.jsonl")
    ap.add_argument("--frozen-result", default="research/evaluation/v31/a593-language-diversity-result-v0.json")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--output", default="artifacts/a593-language-diversity-opened-replay.json")
    args = ap.parse_args()

    frozen = json.loads(Path(args.frozen_result).read_text(encoding="utf-8"))
    if not frozen.get("decision", {}).get("materiality_gate_passed"):
        raise RuntimeError("language-diversity prefrozen gate did not pass")
    if frozen.get("candidate", {}).get("ranker_changed") is not False:
        raise RuntimeError("candidate ranker design drift")

    ids, old_teacher = lang.load_teacher(Path(args.teacher))
    diverse, _training_meta = lang.load_diverse_training(Path(args.training))
    challenger_teacher = {cid: list(values) for cid, values in old_teacher.items()}
    for cid, values in diverse.items():
        if cid not in challenger_teacher:
            raise RuntimeError(f"diversified phrase for non-A593 concept {cid}")
        challenger_teacher[cid].extend(values)

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    taxonomy_wire = fetch(TAXONOMY_URL)
    if hashlib.sha256(taxonomy_wire).hexdigest() != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    taxonomy = json.loads(taxonomy_wire)
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active_occ = {cid for cid, c in by_id.items() if c.get("type") == "occupation-name"}
    if len(active_occ) != 2105 or not set(ids) <= active_occ:
        raise RuntimeError("occupation universe drift")

    control_ranker, control_exact, control_surfaces = base.build_ranker(by_id, ids, old_teacher)
    challenger_ranker, challenger_exact, challenger_surfaces = base.build_ranker(by_id, ids, challenger_teacher)

    def control_rank(query):
        return base.rank_ids(control_ranker, control_exact, control_surfaces, query)

    def challenger_rank(query):
        return base.rank_ids(challenger_ranker, challenger_exact, challenger_surfaces, query)

    source_wire = fetch(SOURCE_URL)
    if hashlib.sha256(source_wire).hexdigest() != expected_hash(registry, "occupational-information"):
        raise RuntimeError("occupational-information source drift")
    strict = base.strict_source_cases(json.loads(source_wire), by_id, active_occ)
    control_strict = base.rank_metrics(strict, [control_rank(row["query"]) for row in strict])
    challenger_strict = base.rank_metrics(strict, [challenger_rank(row["query"]) for row in strict])

    covered_set = set(ids)
    covered = [row for row in strict if row["target_id"] in covered_set]
    control_cov = base.rank_metrics(covered, [control_rank(row["query"]) for row in covered])
    challenger_cov = base.rank_metrics(covered, [challenger_rank(row["query"]) for row in covered])

    stress = json.loads(Path(args.stress).read_text(encoding="utf-8"))
    yv = stress.get("yv") or []
    if len(yv) != 54:
        raise RuntimeError("stress suite drift")
    control_stress = base.stress_summary(yv, by_id, [control_rank(str(row["query"])) for row in yv])
    challenger_stress = base.stress_summary(yv, by_id, [challenger_rank(str(row["query"])) for row in yv])
    control_targetable = targetable(control_stress)
    challenger_targetable = targetable(challenger_stress)

    changed_stress = changed_stress_rows(control_stress, challenger_stress)
    changed_strict = changed_strict_rows(control_strict, challenger_strict)

    result = {
        "schema_version": 1,
        "status": "one-time opened diagnostic replay of prefrozen A593 language-diversity candidate; no tuning",
        "candidate": frozen["candidate"],
        "prefrozen_selection": {
            "materiality_gate_passed": True,
            "heldout_delta": frozen["primary_heldout_proxy"]["delta"],
            "hard_confusion_delta": frozen["secondary_hard_confusion_replay"]["delta"],
            "diversified_training": frozen["diversified_training"],
        },
        "lane_boundary": "standalone 593-occupation semantic description lane; ordinary YV lexical lookup remains separate",
        "strict_source_attested_17": {
            "control_all17": control_strict,
            "challenger_all17": challenger_strict,
            "control_teacher_covered_only": control_cov,
            "challenger_teacher_covered_only": challenger_cov,
            "changed_rows": changed_strict,
        },
        "opened_stress_54": {
            "control": control_stress,
            "challenger": challenger_stress,
            "control_targetable40": control_targetable,
            "challenger_targetable40": challenger_targetable,
            "changed_rows": changed_stress,
        },
        "opened_delta_vs_control": {
            "targetable40_top1": challenger_targetable["top1_family_hit"] - control_targetable["top1_family_hit"],
            "targetable40_hit5": challenger_targetable["top5_family_hit"] - control_targetable["top5_family_hit"],
            "strict17_top1": challenger_strict["top1"] - control_strict["top1"],
            "strict17_hit5": challenger_strict["hit_at_5"] - control_strict["hit_at_5"],
            "strict17_mrr": round(challenger_strict["mrr"] - control_strict["mrr"], 6),
        },
        "evidence_warning": "Candidate and language corpus were frozen before this replay. Opened 17/88 is diagnostic, includes a known substring family-rank heuristic, and is not independent production accuracy evidence. Do not tune from these rows.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "control_targetable40": control_targetable,
        "challenger_targetable40": challenger_targetable,
        "delta": result["opened_delta_vs_control"],
        "strict_control": {k: v for k, v in control_strict.items() if k != "rows"},
        "strict_challenger": {k: v for k, v in challenger_strict.items() if k != "rows"},
        "changed_stress_cases": len(changed_stress),
        "changed_strict_cases": len(changed_strict),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
