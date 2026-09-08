#!/usr/bin/env python3
"""A593 corpus-internal hard-negative distillation over the frozen Gemma phrases.

No opened 17/88 evaluation query participates. For each outer prompt-slot holdout,
seven phrase slots build the positive char-3/4-gram concept centroids. Those same
training phrases then mine their nearest *wrong* concepts. A concept-specific negative
profile records which query features repeatedly make that concept a plausible false
candidate; those features are discounted before the held-out slot is evaluated.

This is deliberately a small, interpretable extension of the frozen top300 sparse
centroid candidate, not a new runtime model class.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import math
import statistics
from pathlib import Path

import evaluate_gemma_a593_sparse_paper_note as sparse

PHRASES_PER_CONCEPT = 8
TOPK = 300
HARD_K = 3
ALPHAS = (0.25, 0.5, 0.75, 1.0)
HUB_LAMBDAS = (0.15, 0.3, 0.5)


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


def inverted(weights):
    inv = collections.defaultdict(list)
    for cid, values in weights.items():
        for feature, weight in values.items():
            inv[feature].append((cid, weight))
    return inv


def scores_for(q, inv):
    scores = collections.defaultdict(float)
    for feature, q_weight in q.items():
        for cid, c_weight in inv.get(feature, ()):
            scores[cid] += q_weight * c_weight
    return scores


def ranked(cids, scores, score_factor=None):
    if score_factor is None:
        score_factor = {}
    return sorted(
        cids,
        key=lambda cid: (-(scores.get(cid, 0.0) * score_factor.get(cid, 1.0)), cid),
    )


def mine_negative_profiles(cids, phrases, slots, vocab, idf, positive_centroids):
    inv = inverted(positive_centroids)
    negative_sum = {cid: collections.defaultdict(float) for cid in cids}
    negative_count = collections.Counter()
    pair_count = collections.Counter()

    for target in cids:
        for slot in slots:
            q = sparse.tfidf_vector(phrases[target][slot], vocab, idf)
            scores = scores_for(q, inv)
            wrongs = [cid for cid in ranked(cids, scores) if cid != target][:HARD_K]
            for wrong in wrongs:
                negative_count[wrong] += 1
                pair_count[(target, wrong)] += 1
                current = negative_sum[wrong]
                for feature, value in q.items():
                    current[feature] += value

    negative_profile = {}
    max_count = max(negative_count.values(), default=1)
    hub_strength = {}
    for cid in cids:
        count = negative_count[cid]
        hub_strength[cid] = 0.0 if not count else math.log1p(count) / math.log1p(max_count)
        if count:
            negative_profile[cid] = {
                feature: value / count for feature, value in negative_sum[cid].items()
            }
        else:
            negative_profile[cid] = {}
    return negative_profile, negative_count, hub_strength, pair_count


def contrastive_centroids(positive, negative, hub_strength, alpha):
    adjusted = {}
    for cid, values in positive.items():
        neg = negative[cid]
        hub = hub_strength[cid]
        current = {
            feature: max(0.0, value - alpha * hub * neg.get(feature, 0.0))
            for feature, value in values.items()
        }
        current = {feature: value for feature, value in current.items() if value > 0.0}
        norm = math.sqrt(sum(value * value for value in current.values()))
        if norm:
            current = {feature: value / norm for feature, value in current.items()}
        adjusted[cid] = current
    return adjusted


def prune_quantize_signedless(centroids):
    return sparse.prune_quantize(centroids, TOPK)[0]


def eval_queries(cids, phrases, holdout, vocab, idf, weights, score_factor=None):
    inv = inverted(weights)
    ranks = []
    for target in cids:
        q = sparse.tfidf_vector(phrases[target][holdout], vocab, idf)
        scores = scores_for(q, inv)
        order = ranked(cids, scores, score_factor)
        ranks.append(order.index(target) + 1)
    return ranks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--selected", default="research/evaluation/v31/compile-time-semantic-a593-sparse-paper-note.json")
    ap.add_argument("--output", default="artifacts/a593-hard-negative-distillation.json")
    args = ap.parse_args()

    selected = json.loads(Path(args.selected).read_text(encoding="utf-8"))
    if selected["selected_candidate"]["variant"] != "char34_centroid_u8_top300":
        raise RuntimeError("top300 selection drift")

    cids, phrases = sparse.load_teacher(Path(args.teacher))
    raw_ranks = []
    contrast_ranks = {alpha: [] for alpha in ALPHAS}
    hub_ranks = {lam: [] for lam in HUB_LAMBDAS}
    hub_counts_total = collections.Counter()
    pair_counts_total = collections.Counter()

    for holdout in range(PHRASES_PER_CONCEPT):
        slots = [slot for slot in range(PHRASES_PER_CONCEPT) if slot != holdout]
        docs = [phrases[cid][slot] for cid in cids for slot in slots]
        vocab, idf = sparse.fit_idf(docs)
        positive = sparse.full_centroids(cids, phrases, slots, vocab, idf)
        negative, neg_counts, hub_strength, pair_counts = mine_negative_profiles(
            cids, phrases, slots, vocab, idf, positive
        )
        hub_counts_total.update(neg_counts)
        pair_counts_total.update(pair_counts)

        baseline_q, _ = sparse.prune_quantize(positive, TOPK)
        raw_ranks.extend(eval_queries(cids, phrases, holdout, vocab, idf, baseline_q))

        for alpha in ALPHAS:
            adjusted = contrastive_centroids(positive, negative, hub_strength, alpha)
            adjusted_q = prune_quantize_signedless(adjusted)
            contrast_ranks[alpha].extend(
                eval_queries(cids, phrases, holdout, vocab, idf, adjusted_q)
            )

        for lam in HUB_LAMBDAS:
            factor = {cid: 1.0 / (1.0 + lam * hub_strength[cid]) for cid in cids}
            hub_ranks[lam].extend(
                eval_queries(cids, phrases, holdout, vocab, idf, baseline_q, factor)
            )

    variants = {
        "baseline_char34_top300": summarize(raw_ranks),
    }
    for alpha in ALPHAS:
        variants[f"hard_negative_discount_alpha_{alpha}"] = summarize(contrast_ranks[alpha])
    for lam in HUB_LAMBDAS:
        variants[f"score_hub_penalty_lambda_{lam}"] = summarize(hub_ranks[lam])

    candidate_keys = [key for key in variants if key != "baseline_char34_top300"]
    selected_key = max(
        candidate_keys,
        key=lambda key: (
            variants[key]["hit_at_5_rate"],
            variants[key]["mrr"],
            variants[key]["top1_rate"],
        ),
    )
    baseline = variants["baseline_char34_top300"]
    winner = variants[selected_key]
    result = {
        "schema_version": 1,
        "status": "A593 corpus-internal hard-negative diagnostic; no opened evaluation queries used",
        "corpus": {"concepts": len(cids), "phrases": len(cids) * PHRASES_PER_CONCEPT, "outer_folds": 8},
        "base_candidate": "YV-A593-char34-centroid-u8-top300-v0",
        "hard_negative_mining": {
            "wrong_candidates_per_training_phrase": HARD_K,
            "definition": "top wrong concepts under positive training centroids; target excluded; no opened query used",
            "hub_strength": "log1p(false-candidate count) normalized by fold maximum",
            "contrast": "positive centroid feature minus alpha * hub_strength * mean hard-negative query feature; clamp at zero, renormalize, prune top300, uint8",
        },
        "variants": variants,
        "selected_variant": selected_key,
        "selected_metrics": winner,
        "delta_vs_top300": {
            "top1_count": winner["top1_count"] - baseline["top1_count"],
            "hit_at_5_count": winner["hit_at_5_count"] - baseline["hit_at_5_count"],
            "mrr": round(winner["mrr"] - baseline["mrr"], 6),
        },
        "top_false_candidate_hubs": [
            {"concept_id": cid, "false_candidate_count": count}
            for cid, count in hub_counts_total.most_common(25)
        ],
        "top_directed_hard_negative_pairs": [
            {"target_concept_id": target, "wrong_concept_id": wrong, "count": count}
            for (target, wrong), count in pair_counts_total.most_common(40)
        ],
        "guard": "Selection uses only Gemma-authored outer-fold holdouts. Freeze any winning variant before an opened 17/88 replay; do not tune from opened outcomes.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
