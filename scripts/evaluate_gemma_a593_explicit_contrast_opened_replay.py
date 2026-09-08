#!/usr/bin/env python3
"""One-time opened replay of the prefrozen A593 explicit pair-contrast layer.

The corpus-internal gate, pair set and threshold-free decision rule were frozen before
this script reads the opened 17/88 diagnostics. Results must not tune this candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import evaluate_gemma_a149 as base
import evaluate_gemma_a593_explicit_contrast_layer as contrast
import evaluate_gemma_a593_hard_negative_distillation as hn
import evaluate_gemma_a593_relation_aware_negatives as rel
import evaluate_gemma_a593_sniper_contrasts as sniper
import evaluate_gemma_a593_sparse_paper_note as sparse
from evaluate_p80_lexical_ablation import expected_hash, fetch
from evaluate_yv_full_description_canonical import SOURCE_URL

CANDIDATE_ID = "YV-A593-explicit-pair-contrast-v0"


def build_full(cids, phrases, rows):
    slots = list(range(8))
    docs = [phrases[cid][slot] for cid in cids for slot in slots]
    base_vocab, base_idf = sparse.fit_idf(docs)
    positive = sparse.full_centroids(cids, phrases, slots, base_vocab, base_idf)
    protected, _ = rel.protected_neighbors(cids, positive)
    negative, _counts, hubs, _pairs, _skipped = rel.mine_relation_aware(
        cids, phrases, slots, base_vocab, base_idf, positive, protected
    )
    adjusted = hn.contrastive_centroids(positive, negative, hubs, rel.ALPHA)
    weights = hn.prune_quantize_signedless(adjusted)
    contrast_vocab, contrast_idf = sniper.extend_idf(base_vocab, base_idf, len(docs), rows)
    rules = contrast.compile_rules(rows, contrast_vocab, contrast_idf)
    return base_vocab, base_idf, weights, contrast_vocab, contrast_idf, rules


def rank_relation(query, cids, vocab, idf, weights):
    q = sparse.tfidf_vector(query, vocab, idf)
    if not q:
        return []
    scores = hn.scores_for(q, hn.inverted(weights))
    return [cid for cid in hn.ranked(cids, scores) if scores.get(cid, 0.0) > 0.0]


def rank_contrast(query, cids, base_vocab, base_idf, weights, contrast_vocab, contrast_idf, rules):
    q = sparse.tfidf_vector(query, base_vocab, base_idf)
    if not q:
        return []
    scores = hn.scores_for(q, hn.inverted(weights))
    cq = sparse.tfidf_vector(query, contrast_vocab, contrast_idf)
    adjusted, _decisions = contrast.apply_pair_swaps(scores, cq, rules)
    return [cid for cid in hn.ranked(cids, adjusted) if adjusted.get(cid, 0.0) > 0.0]


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
            "relation_family_rank": br,
            "contrast_family_rank": ar,
            "relation_top5": before["top5"],
            "contrast_top5": after["top5"],
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
            "relation_rank": br,
            "contrast_rank": ar,
            "relation_top5": before["top5"],
            "contrast_top5": after["top5"],
            "hit5_delta": int(ar is not None and ar <= 5) - int(br is not None and br <= 5),
            "top1_delta": int(ar == 1) - int(br == 1),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--sniper", default="research/training/v31/a593-gemma4-sniper-contrasts-v0.jsonl")
    ap.add_argument("--frozen-result", default="research/evaluation/v31/compile-time-semantic-a593-explicit-contrast-layer.json")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--output", default="artifacts/a593-explicit-contrast-opened-replay.json")
    args = ap.parse_args()

    frozen = json.loads(Path(args.frozen_result).read_text(encoding="utf-8"))
    if not frozen.get("opened_replay_gate_passed"):
        raise RuntimeError("explicit contrast corpus gate did not pass")
    candidate = frozen["candidate"]
    if candidate["id"] != CANDIDATE_ID or candidate["numeric_pair_boost"] or candidate["global_concept_weight_mutation"]:
        raise RuntimeError("explicit contrast design drift")

    cids, phrases = sparse.load_teacher(Path(args.teacher))
    rows = sniper.load_sniper(Path(args.sniper))
    base_vocab, base_idf, weights, contrast_vocab, contrast_idf, rules = build_full(cids, phrases, rows)

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    taxonomy_url = "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json"
    taxonomy_wire = fetch(taxonomy_url)
    if hashlib.sha256(taxonomy_wire).hexdigest() != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    taxonomy = json.loads(taxonomy_wire)
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active_occ = {cid for cid, c in by_id.items() if c.get("type") == "occupation-name"}
    if len(active_occ) != 2105 or not set(cids) <= active_occ:
        raise RuntimeError("occupation universe drift")

    source_wire = fetch(SOURCE_URL)
    if hashlib.sha256(source_wire).hexdigest() != expected_hash(registry, "occupational-information"):
        raise RuntimeError("occupational-information source drift")
    strict = base.strict_source_cases(json.loads(source_wire), by_id, active_occ)
    relation_strict_ranked = [rank_relation(row["query"], cids, base_vocab, base_idf, weights) for row in strict]
    contrast_strict_ranked = [
        rank_contrast(row["query"], cids, base_vocab, base_idf, weights, contrast_vocab, contrast_idf, rules)
        for row in strict
    ]
    relation_strict = base.rank_metrics(strict, relation_strict_ranked)
    contrast_strict = base.rank_metrics(strict, contrast_strict_ranked)

    covered_set = set(cids)
    covered = [row for row in strict if row["target_id"] in covered_set]
    relation_cov = base.rank_metrics(covered, [rank_relation(row["query"], cids, base_vocab, base_idf, weights) for row in covered])
    contrast_cov = base.rank_metrics(
        covered,
        [rank_contrast(row["query"], cids, base_vocab, base_idf, weights, contrast_vocab, contrast_idf, rules) for row in covered],
    )

    stress = json.loads(Path(args.stress).read_text(encoding="utf-8"))
    yv = stress.get("yv") or []
    if len(yv) != 54:
        raise RuntimeError("stress suite drift")
    relation_ranked = [rank_relation(str(row["query"]), cids, base_vocab, base_idf, weights) for row in yv]
    contrast_ranked = [
        rank_contrast(str(row["query"]), cids, base_vocab, base_idf, weights, contrast_vocab, contrast_idf, rules)
        for row in yv
    ]
    relation_stress = base.stress_summary(yv, by_id, relation_ranked)
    contrast_stress = base.stress_summary(yv, by_id, contrast_ranked)

    changed_stress = changed_stress_rows(relation_stress, contrast_stress)
    changed_strict = changed_strict_rows(relation_strict, contrast_strict)
    relation_targetable = targetable(relation_stress)
    contrast_targetable = targetable(contrast_stress)

    result = {
        "schema_version": 1,
        "status": "one-time opened diagnostic replay of prefrozen A593 explicit source-bound pair contrast layer; no runtime promotion",
        "candidate": candidate,
        "selection_evidence": {
            "corpus_gate": frozen["opened_replay_gate_passed"],
            "delta_all_vs_control": frozen["delta_all_vs_control"],
            "delta_targeted_vs_control": frozen["delta_targeted_vs_control"],
            "rule_guard_summary": {
                "shared_neutral": [frozen["rule_guard"]["shared"]["neutral_count"], frozen["rule_guard"]["shared"]["cases"]],
                "decisive_correct": [frozen["rule_guard"]["decisive"]["correct_side_count"], frozen["rule_guard"]["decisive"]["cases"]],
                "indistinguishable_neutral": [frozen["rule_guard"]["indistinguishable"]["neutral_count"], frozen["rule_guard"]["indistinguishable"]["cases"]],
            },
        },
        "lane_boundary": "standalone 593-occupation semantic description lane; ordinary YV lexical lookup remains separate",
        "strict_source_attested_17": {
            "relation_aware_all17": relation_strict,
            "contrast_all17": contrast_strict,
            "relation_aware_teacher_covered_only": relation_cov,
            "contrast_teacher_covered_only": contrast_cov,
            "changed_rows": changed_strict,
        },
        "opened_stress_54": {
            "relation_aware": relation_stress,
            "contrast": contrast_stress,
            "relation_aware_targetable40": relation_targetable,
            "contrast_targetable40": contrast_targetable,
            "changed_rows": changed_stress,
        },
        "opened_delta_vs_relation_aware": {
            "targetable40_top1": contrast_targetable["top1_family_hit"] - relation_targetable["top1_family_hit"],
            "targetable40_hit5": contrast_targetable["top5_family_hit"] - relation_targetable["top5_family_hit"],
            "strict17_top1": contrast_strict["top1"] - relation_strict["top1"],
            "strict17_hit5": contrast_strict["hit_at_5"] - relation_strict["hit_at_5"],
            "strict17_mrr": round(contrast_strict["mrr"] - relation_strict["mrr"], 6),
        },
        "evidence_warning": "Pair selection and the threshold-free rule were frozen before this replay. Opened 17/88 uses a known substring family-rank diagnostic and is not independent production accuracy evidence. Do not tune from these rows.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "relation_targetable40": relation_targetable,
        "contrast_targetable40": contrast_targetable,
        "delta": result["opened_delta_vs_relation_aware"],
        "strict_relation": {k: v for k, v in relation_strict.items() if k != "rows"},
        "strict_contrast": {k: v for k, v in contrast_strict.items() if k != "rows"},
        "changed_stress_cases": len(changed_stress),
        "changed_strict_cases": len(changed_strict),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
