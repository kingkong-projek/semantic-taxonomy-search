#!/usr/bin/env python3
"""Opened replay of the prefrozen A593 relation-aware + sniper sparse candidate.

The sniper pair set and fixed correction (+0.50 own, -0.25 opposite) were frozen using
only A593 corpus-internal evidence before this replay. Opened 17/88 outcomes are
strictly diagnostic and must not tune the candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import evaluate_gemma_a149 as base
import evaluate_gemma_a593_hard_negative_distillation as hn
import evaluate_gemma_a593_relation_aware_negatives as rel
import evaluate_gemma_a593_sniper_contrasts as sniper
import evaluate_gemma_a593_sparse_paper_note as sparse
from evaluate_p80_lexical_ablation import expected_hash, fetch
from evaluate_yv_full_description_canonical import SOURCE_URL

CANDIDATE_ID = "YV-A593-char34-top300-relation-sniper-v0"


def build_relation_lane(cids, phrases):
    slots = list(range(8))
    docs = [phrases[cid][slot] for cid in cids for slot in slots]
    vocab, idf = sparse.fit_idf(docs)
    positive = sparse.full_centroids(cids, phrases, slots, vocab, idf)
    protected, _ = rel.protected_neighbors(cids, positive)
    negative, _counts, hubs, _pairs, _skipped = rel.mine_relation_aware(
        cids, phrases, slots, vocab, idf, positive, protected
    )
    adjusted = hn.contrastive_centroids(positive, negative, hubs, rel.ALPHA)
    quantized = hn.prune_quantize_signedless(adjusted)
    return vocab, idf, quantized


def rank_query(query, cids, vocab, idf, weights):
    q = sparse.tfidf_vector(query, vocab, idf)
    if not q:
        return []
    inv = hn.inverted(weights)
    scores = hn.scores_for(q, inv)
    order = hn.ranked(cids, scores)
    return [cid for cid in order if scores.get(cid, 0.0) > 0.0]


def targetable(summary):
    names = ("direct", "colloquial", "noisy", "indirect")
    cats = summary["categories"]
    return {
        "cases": 40,
        "top1_family_hit": sum(cats[n]["top1_family_hit"] for n in names),
        "top5_family_hit": sum(cats[n]["top5_family_hit"] for n in names),
    }


def changed_stress_rows(control, challenger):
    out = []
    for before, after in zip(control["rows"], challenger["rows"], strict=True):
        if (before["expected_family_rank"], before["top5"], before["empty"]) == (
            after["expected_family_rank"], after["top5"], after["empty"]
        ):
            continue
        br = before["expected_family_rank"]
        ar = after["expected_family_rank"]
        out.append({
            "id": before["id"],
            "category": before["category"],
            "query": before["query"],
            "expected": before["expected"],
            "relation_family_rank": br,
            "sniper_family_rank": ar,
            "relation_top5": before["top5"],
            "sniper_top5": after["top5"],
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
            "sniper_rank": ar,
            "relation_top5": before["top5"],
            "sniper_top5": after["top5"],
            "hit5_delta": int(ar is not None and ar <= 5) - int(br is not None and br <= 5),
            "top1_delta": int(ar == 1) - int(br == 1),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--sniper", default="research/training/v31/a593-gemma4-sniper-contrasts-v0.jsonl")
    ap.add_argument("--sniper-result", default="research/evaluation/v31/compile-time-semantic-a593-sniper-contrasts.json")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--output", default="artifacts/a593-sniper-opened-replay.json")
    args = ap.parse_args()

    frozen = json.loads(Path(args.sniper_result).read_text(encoding="utf-8"))
    if not frozen.get("opened_replay_gate_passed"):
        raise RuntimeError("sniper corpus gate did not pass")
    fixed = frozen["fixed_design"]
    if fixed["own_sniper_beta"] != sniper.OWN_BETA or fixed["opposite_sniper_gamma"] != sniper.OPPOSITE_GAMMA:
        raise RuntimeError("sniper correction drift")

    cids, phrases = sparse.load_teacher(Path(args.teacher))
    sniper_rows = sniper.load_sniper(Path(args.sniper))
    relation_vocab, relation_idf, relation_weights = build_relation_lane(cids, phrases)
    sniper_vocab, sniper_idf, sniper_weights = sniper.full_candidate(cids, phrases, sniper_rows)

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
    relation_strict_ranked = [rank_query(row["query"], cids, relation_vocab, relation_idf, relation_weights) for row in strict]
    sniper_strict_ranked = [rank_query(row["query"], cids, sniper_vocab, sniper_idf, sniper_weights) for row in strict]
    relation_strict = base.rank_metrics(strict, relation_strict_ranked)
    sniper_strict = base.rank_metrics(strict, sniper_strict_ranked)

    covered_set = set(cids)
    covered = [row for row in strict if row["target_id"] in covered_set]
    relation_cov = base.rank_metrics(
        covered,
        [rank_query(row["query"], cids, relation_vocab, relation_idf, relation_weights) for row in covered],
    )
    sniper_cov = base.rank_metrics(
        covered,
        [rank_query(row["query"], cids, sniper_vocab, sniper_idf, sniper_weights) for row in covered],
    )

    stress = json.loads(Path(args.stress).read_text(encoding="utf-8"))
    yv = stress.get("yv") or []
    if len(yv) != 54:
        raise RuntimeError("stress suite drift")
    relation_ranked = [rank_query(str(row["query"]), cids, relation_vocab, relation_idf, relation_weights) for row in yv]
    sniper_ranked = [rank_query(str(row["query"]), cids, sniper_vocab, sniper_idf, sniper_weights) for row in yv]
    relation_stress = base.stress_summary(yv, by_id, relation_ranked)
    sniper_stress = base.stress_summary(yv, by_id, sniper_ranked)

    changed_stress = changed_stress_rows(relation_stress, sniper_stress)
    changed_strict = changed_strict_rows(relation_strict, sniper_strict)
    result = {
        "schema_version": 1,
        "status": "one-time opened diagnostic replay of prefrozen A593 relation-aware + sniper candidate; no runtime promotion",
        "candidate": {
            "id": CANDIDATE_ID,
            "base": "relation-aware clamped hard-negative alpha=0.75",
            "own_sniper_beta": sniper.OWN_BETA,
            "opposite_sniper_gamma": sniper.OPPOSITE_GAMMA,
            "topk_features_per_concept": sniper.TOPK,
            "runtime_shape": "char_wb 3/4-gram TF-IDF + uint8 sparse concept weights; source-grounded contrast intelligence compiled into weights",
            "teacher_dependency_at_runtime": False,
        },
        "selection_evidence": {
            "corpus_gate": frozen["opened_replay_gate_passed"],
            "all_4744": frozen["all_4744"],
            "targeted_teacher_holdouts": frozen["targeted_teacher_holdouts"],
        },
        "lane_boundary": "standalone 593-occupation semantic description lane; ordinary YV lexical lookup remains separate",
        "strict_source_attested_17": {
            "relation_aware_all17": relation_strict,
            "sniper_all17": sniper_strict,
            "relation_aware_teacher_covered_only": relation_cov,
            "sniper_teacher_covered_only": sniper_cov,
            "changed_rows": changed_strict,
        },
        "opened_stress_54": {
            "relation_aware": relation_stress,
            "sniper": sniper_stress,
            "relation_aware_targetable40": targetable(relation_stress),
            "sniper_targetable40": targetable(sniper_stress),
            "changed_rows": changed_stress,
        },
        "opened_delta_vs_relation_aware": {
            "targetable40_top1": targetable(sniper_stress)["top1_family_hit"] - targetable(relation_stress)["top1_family_hit"],
            "targetable40_hit5": targetable(sniper_stress)["top5_family_hit"] - targetable(relation_stress)["top5_family_hit"],
            "strict17_top1": sniper_strict["top1"] - relation_strict["top1"],
            "strict17_hit5": sniper_strict["hit_at_5"] - relation_strict["hit_at_5"],
            "strict17_mrr": round(sniper_strict["mrr"] - relation_strict["mrr"], 6),
        },
        "evidence_warning": "Pair selection and correction weights were frozen before this replay. Opened 17/88 uses a known substring family-rank diagnostic and is not independent production accuracy evidence. Do not tune from these rows.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "relation_targetable40": result["opened_stress_54"]["relation_aware_targetable40"],
        "sniper_targetable40": result["opened_stress_54"]["sniper_targetable40"],
        "delta": result["opened_delta_vs_relation_aware"],
        "strict_relation": {k: v for k, v in relation_strict.items() if k != "rows"},
        "strict_sniper": {k: v for k, v in sniper_strict.items() if k != "rows"},
        "changed_stress_cases": len(changed_stress),
        "changed_strict_cases": len(changed_strict),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
