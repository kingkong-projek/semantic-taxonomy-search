#!/usr/bin/env python3
"""A593 relation-aware hard-negative diagnostic.

Motivation from qualitative review: some of the strongest mined "hard negatives" are
not meaningfully distinguishable from the target under the frozen teacher language
(e.g. certified/non-certified variants with near-identical descriptions). Training a
one-vs-all student to push those apart can manufacture anti-signal.

For each of eight outer folds, protection is derived only from the seven training
phrase slots. A pair is protected from negative mining when its normalized char-3/4
TF-IDF concept centroids have cosine similarity >= 0.75. The held-out eighth phrase
never participates in the protection decision.

Fixed challengers:
1. relation-aware clamped hard-negative discount, alpha=0.75 (same runtime class as incumbent)
2. relation-aware one-pass pairwise PA student (tests whether sibling protection rescues the rejected pairwise class)

Opened 17/88 queries are not read here.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
from pathlib import Path

import evaluate_gemma_a593_hard_negative_distillation as hn
import evaluate_gemma_a593_pairwise_sparse_student as pa
import evaluate_gemma_a593_sparse_paper_note as sparse

PHRASES_PER_CONCEPT = 8
TOPK = 300
HARD_K = 3
ALPHA = 0.75
PROTECT_COSINE = 0.75


def summarize(ranks):
    return {
        "cases": len(ranks),
        "top1_count": sum(r == 1 for r in ranks),
        "top1_rate": round(sum(r == 1 for r in ranks) / len(ranks), 6),
        "hit_at_5_count": sum(r <= 5 for r in ranks),
        "hit_at_5_rate": round(sum(r <= 5 for r in ranks) / len(ranks), 6),
        "mrr": round(sum(1.0 / r for r in ranks) / len(ranks), 6),
        "median_rank": statistics.median(ranks),
    }


def labels_from_teacher(path: Path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[str(row["concept_id"])] = str(row.get("label") or row["concept_id"])
    return out


def protected_neighbors(cids, positive, threshold=PROTECT_COSINE):
    """Return train-only near-indistinguishable neighbors and their cosine scores."""
    inv = hn.inverted(positive)
    protected = {cid: set() for cid in cids}
    pair_scores = {}
    for cid in cids:
        scores = hn.scores_for(positive[cid], inv)
        for other, score in scores.items():
            if other == cid or score < threshold:
                continue
            protected[cid].add(other)
            key = tuple(sorted((cid, other)))
            pair_scores[key] = max(pair_scores.get(key, 0.0), score)
    return protected, pair_scores


def mine_relation_aware(cids, phrases, slots, vocab, idf, positive, protected):
    inv = hn.inverted(positive)
    negative_sum = {cid: collections.defaultdict(float) for cid in cids}
    negative_count = collections.Counter()
    pair_count = collections.Counter()
    skipped_protected = collections.Counter()

    for target in cids:
        blocked = protected[target]
        for slot in slots:
            q = sparse.tfidf_vector(phrases[target][slot], vocab, idf)
            scores = hn.scores_for(q, inv)
            wrongs = []
            for cid in hn.ranked(cids, scores):
                if cid == target:
                    continue
                if cid in blocked:
                    skipped_protected[(target, cid)] += 1
                    continue
                wrongs.append(cid)
                if len(wrongs) == HARD_K:
                    break
            for wrong in wrongs:
                negative_count[wrong] += 1
                pair_count[(target, wrong)] += 1
                for feature, value in q.items():
                    negative_sum[wrong][feature] += value

    max_count = max(negative_count.values(), default=1)
    negative = {}
    hubs = {}
    for cid in cids:
        count = negative_count[cid]
        hubs[cid] = 0.0 if not count else math.log1p(count) / math.log1p(max_count)
        negative[cid] = (
            {feature: value / count for feature, value in negative_sum[cid].items()}
            if count else {}
        )
    return negative, negative_count, hubs, pair_count, skipped_protected


def evaluate_weights(cids, phrases, holdout, vocab, idf, weights):
    inv = hn.inverted(weights)
    exact = []
    family = []
    return exact, family, inv


def eval_with_protection(cids, phrases, holdout, vocab, idf, weights, protected):
    inv = hn.inverted(weights)
    exact_ranks = []
    protected_ranks = []
    for target in cids:
        q = sparse.tfidf_vector(phrases[target][holdout], vocab, idf)
        order = hn.ranked(cids, hn.scores_for(q, inv))
        exact_ranks.append(order.index(target) + 1)
        acceptable = {target} | protected[target]
        protected_ranks.append(min(order.index(cid) + 1 for cid in acceptable))
    return exact_ranks, protected_ranks


def train_pa_protected(cids, phrases, slots, vocab, idf, positive, protected):
    weights = {cid: dict(values) for cid, values in positive.items()}
    inv = pa.build_inverted(weights)
    updates = 0
    skipped = 0
    hardest_pairs = collections.Counter()

    for target, slot in pa.stable_examples(cids, slots, 0):
        q = sparse.tfidf_vector(phrases[target][slot], vocab, idf)
        if not q:
            continue
        scores = pa.score_query(q, inv)
        wrong = None
        for cid in hn.ranked(cids, scores):
            if cid == target:
                continue
            if cid in protected[target]:
                skipped += 1
                continue
            wrong = cid
            break
        if wrong is None:
            continue
        hardest_pairs[(target, wrong)] += 1
        loss = 1.0 - (scores.get(target, 0.0) - scores.get(wrong, 0.0))
        if loss <= 0.0:
            continue
        tau = loss / 2.0
        for feature, value in q.items():
            pa.set_weight(weights, inv, target, feature, weights[target].get(feature, 0.0) + tau * value)
            pa.set_weight(weights, inv, wrong, feature, weights[wrong].get(feature, 0.0) - tau * value)
        updates += 1

    return weights, {
        "training_examples": len(cids) * len(slots),
        "updates": updates,
        "update_rate": round(updates / (len(cids) * len(slots)), 6),
        "protected_candidates_skipped_while_seeking_hardest_wrong": skipped,
        "top_hardest_pairs": [
            {"target_concept_id": a, "wrong_concept_id": b, "count": n}
            for (a, b), n in hardest_pairs.most_common(20)
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--incumbent", default="research/evaluation/v31/compile-time-semantic-a593-hard-negative-distillation.json")
    ap.add_argument("--rejected-pairwise", default="research/evaluation/v31/compile-time-semantic-a593-pairwise-sparse-student.json")
    ap.add_argument("--output", default="artifacts/a593-relation-aware-negatives.json")
    args = ap.parse_args()

    incumbent = json.loads(Path(args.incumbent).read_text(encoding="utf-8"))
    rejected = json.loads(Path(args.rejected_pairwise).read_text(encoding="utf-8"))
    if incumbent["selected_variant"] != "hard_negative_discount_alpha_0.75":
        raise RuntimeError("incumbent drift")
    if rejected.get("opened_replay_gate_passed") is not False:
        raise RuntimeError("pairwise rejection state drift")

    teacher_path = Path(args.teacher)
    cids, phrases = sparse.load_teacher(teacher_path)
    labels = labels_from_teacher(teacher_path)
    ranks = {
        "incumbent_clamped_a075": [],
        "relation_aware_clamped_a075": [],
        "relation_aware_pairwise_pa1": [],
    }
    family_ranks = {key: [] for key in ranks}
    fold_protected_counts = []
    skipped_total = collections.Counter()
    pairwise_stats = []

    for holdout in range(PHRASES_PER_CONCEPT):
        slots = [slot for slot in range(PHRASES_PER_CONCEPT) if slot != holdout]
        docs = [phrases[cid][slot] for cid in cids for slot in slots]
        vocab, idf = sparse.fit_idf(docs)
        positive = sparse.full_centroids(cids, phrases, slots, vocab, idf)
        protected, _ = protected_neighbors(cids, positive)
        fold_protected_counts.append(sum(len(v) for v in protected.values()) // 2)

        # Frozen incumbent, recomputed for parity.
        neg0, _count0, hubs0, _pairs0 = hn.mine_negative_profiles(cids, phrases, slots, vocab, idf, positive)
        inc = hn.contrastive_centroids(positive, neg0, hubs0, ALPHA)
        inc_q = hn.prune_quantize_signedless(inc)
        er, fr = eval_with_protection(cids, phrases, holdout, vocab, idf, inc_q, protected)
        ranks["incumbent_clamped_a075"].extend(er)
        family_ranks["incumbent_clamped_a075"].extend(fr)

        # Same clamped model, but near-indistinguishable train-only siblings cannot be negatives.
        neg, _counts, hubs, _pairs, skipped = mine_relation_aware(cids, phrases, slots, vocab, idf, positive, protected)
        skipped_total.update(skipped)
        adjusted = hn.contrastive_centroids(positive, neg, hubs, ALPHA)
        rel_q = hn.prune_quantize_signedless(adjusted)
        er, fr = eval_with_protection(cids, phrases, holdout, vocab, idf, rel_q, protected)
        ranks["relation_aware_clamped_a075"].extend(er)
        family_ranks["relation_aware_clamped_a075"].extend(fr)

        # Re-test the rejected pairwise class with the same protected sibling relation.
        trained, stats = train_pa_protected(cids, phrases, slots, vocab, idf, positive, protected)
        pairwise_stats.append(stats)
        pair_q = pa.signed_topk_quantized(trained)
        er, fr = eval_with_protection(cids, phrases, holdout, vocab, idf, pair_q, protected)
        ranks["relation_aware_pairwise_pa1"].extend(er)
        family_ranks["relation_aware_pairwise_pa1"].extend(fr)

    metrics = {key: summarize(value) for key, value in ranks.items()}
    family_metrics = {key: summarize(value) for key, value in family_ranks.items()}
    frozen_inc = incumbent["selected_metrics"]
    actual_inc = metrics["incumbent_clamped_a075"]
    if (actual_inc["top1_count"], actual_inc["hit_at_5_count"], actual_inc["mrr"]) != (
        frozen_inc["top1_count"], frozen_inc["hit_at_5_count"], frozen_inc["mrr"]
    ):
        raise RuntimeError(f"incumbent parity failed: {actual_inc} != {frozen_inc}")

    challengers = ["relation_aware_clamped_a075", "relation_aware_pairwise_pa1"]
    selected = max(challengers, key=lambda key: (metrics[key]["mrr"], metrics[key]["top1_rate"], metrics[key]["hit_at_5_rate"]))
    selected_metrics = metrics[selected]
    replay_gate = selected_metrics["mrr"] > frozen_inc["mrr"] and (
        selected_metrics["top1_count"] > frozen_inc["top1_count"]
        or selected_metrics["hit_at_5_count"] > frozen_inc["hit_at_5_count"]
    )

    # Full-corpus protected examples for qualitative inspection only; not used by folds.
    slots = list(range(PHRASES_PER_CONCEPT))
    docs = [phrases[cid][slot] for cid in cids for slot in slots]
    vocab, idf = sparse.fit_idf(docs)
    positive = sparse.full_centroids(cids, phrases, slots, vocab, idf)
    _protected_full, pair_scores = protected_neighbors(cids, positive)
    protected_examples = [
        {
            "left_concept_id": a,
            "left_label": labels.get(a, a),
            "right_concept_id": b,
            "right_label": labels.get(b, b),
            "teacher_centroid_cosine": round(score, 6),
        }
        for (a, b), score in sorted(pair_scores.items(), key=lambda item: (-item[1], item[0]))[:40]
    ]

    result = {
        "schema_version": 1,
        "status": "A593 relation-aware negative diagnostic; no opened evaluation queries used",
        "fixed_design": {
            "protection_definition": "within each outer fold, do-not-negative if seven-slot normalized char3/4 TF-IDF concept-centroid cosine >= 0.75",
            "protection_cosine": PROTECT_COSINE,
            "hard_negative_k": HARD_K,
            "alpha": ALPHA,
            "topk_features_per_concept": TOPK,
            "selection_rule": "highest MRR, then Top1, then Hit@5 across two predeclared challengers",
            "opened_replay_gate": "must beat frozen clamped-hard-negative incumbent on MRR and on at least one of Top1 or Hit@5",
        },
        "fold_protected_pair_counts": fold_protected_counts,
        "fold_protected_pair_count_mean": round(statistics.mean(fold_protected_counts), 3),
        "variants_exact_identity": metrics,
        "variants_indistinguishability_aware": family_metrics,
        "incumbent": frozen_inc,
        "selected_variant": selected,
        "selected_metrics": selected_metrics,
        "delta_vs_incumbent": {
            "top1_count": selected_metrics["top1_count"] - frozen_inc["top1_count"],
            "hit_at_5_count": selected_metrics["hit_at_5_count"] - frozen_inc["hit_at_5_count"],
            "mrr": round(selected_metrics["mrr"] - frozen_inc["mrr"], 6),
        },
        "opened_replay_gate_passed": replay_gate,
        "pairwise_training": {
            "mean_update_rate": round(statistics.mean(x["update_rate"] for x in pairwise_stats), 6),
            "mean_updates": round(statistics.mean(x["updates"] for x in pairwise_stats), 3),
            "mean_protected_candidates_skipped": round(statistics.mean(x["protected_candidates_skipped_while_seeking_hardest_wrong"] for x in pairwise_stats), 3),
        },
        "protected_negative_skips_top": [
            {"target_concept_id": a, "wrong_concept_id": b, "count": n}
            for (a, b), n in skipped_total.most_common(30)
        ],
        "full_corpus_protected_examples": protected_examples,
        "qualitative_interpretation_guard": "Protection means indistinguishable under the frozen training representation, not canonical identity equivalence. Exact taxonomy identities remain separate outputs.",
        "guard": "No opened 17/88 query is read. The held-out phrase never participates in fold protection. Do not tune the cosine threshold from opened outcomes.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "selected_variant": selected,
        "selected_metrics": selected_metrics,
        "incumbent": frozen_inc,
        "delta_vs_incumbent": result["delta_vs_incumbent"],
        "opened_replay_gate_passed": replay_gate,
        "fold_protected_pair_count_mean": result["fold_protected_pair_count_mean"],
        "pairwise_training": result["pairwise_training"],
        "top_protected_examples": protected_examples[:12],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
