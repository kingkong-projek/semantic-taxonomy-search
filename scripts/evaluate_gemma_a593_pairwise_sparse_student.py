#!/usr/bin/env python3
"""A593 genuinely discriminative sparse-student probe.

This is the smallest model-class step beyond centroid/hard-negative reweighting.
For each of eight outer folds, seven Gemma phrase slots per occupation are training
queries and the eighth slot is untouched evaluation. A one-pass multiclass
Passive-Aggressive update explicitly enforces:

    score(correct occupation) > score(highest-scoring wrong occupation) + 1

The student starts from the positive TF-IDF centroid, updates only the correct and
current hardest wrong concept for each training phrase, then prunes to 300 signed
features/concept and globally quantizes to int8. Runtime is still deterministic sparse
TF-IDF + dot products. No opened 17/88 query participates.

Two fixed challengers only:
- char34_pairwise_pa1_top300
- char34_bigram_pairwise_pa1_top300

There is no hyperparameter sweep. Adjacent word-bigram context is the exact same
context probe frozen in the preceding signed/context diagnostic.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import statistics
from pathlib import Path

import evaluate_gemma_a593_signed_context_sparse as sc
import evaluate_gemma_a593_sparse_paper_note as sparse

PHRASES_PER_CONCEPT = 8
TOPK = 300
MARGIN = 1.0
EPOCHS = 1


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


def build_inverted(weights):
    inv = collections.defaultdict(dict)
    for cid, values in weights.items():
        for feature, value in values.items():
            if value:
                inv[feature][cid] = value
    return inv


def score_query(q, inv):
    scores = collections.defaultdict(float)
    for feature, q_weight in q.items():
        for cid, c_weight in inv.get(feature, {}).items():
            scores[cid] += q_weight * c_weight
    return scores


def hardest_wrong(cids, target, scores):
    return min(
        (cid for cid in cids if cid != target),
        key=lambda cid: (-scores.get(cid, 0.0), cid),
    )


def set_weight(weights, inv, cid, feature, value):
    if abs(value) < 1e-15:
        weights[cid].pop(feature, None)
        current = inv.get(feature)
        if current is not None:
            current.pop(cid, None)
            if not current:
                inv.pop(feature, None)
    else:
        weights[cid][feature] = value
        inv[feature][cid] = value


def stable_examples(cids, slots, epoch):
    examples = [(cid, slot) for cid in cids for slot in slots]
    return sorted(
        examples,
        key=lambda item: hashlib.sha256(
            f"a593-pa|{epoch}|{item[0]}|{item[1]}".encode("utf-8")
        ).digest(),
    )


def train_pa(cids, phrases, slots, vocab, idf, positive, *, context):
    weights = {cid: dict(values) for cid, values in positive.items()}
    inv = build_inverted(weights)
    updates = 0
    cumulative_loss = 0.0
    hardest_pairs = collections.Counter()

    for epoch in range(EPOCHS):
        for target, slot in stable_examples(cids, slots, epoch):
            q = sc.vector(phrases[target][slot], vocab, idf, context=context)
            if not q:
                continue
            scores = score_query(q, inv)
            wrong = hardest_wrong(cids, target, scores)
            target_score = scores.get(target, 0.0)
            wrong_score = scores.get(wrong, 0.0)
            loss = MARGIN - (target_score - wrong_score)
            hardest_pairs[(target, wrong)] += 1
            if loss <= 0.0:
                continue

            # PA-I without a C cap. q is L2-normalized, and the joint target/wrong
            # update has squared norm 2 * ||q||^2 = 2.
            tau = loss / 2.0
            for feature, value in q.items():
                set_weight(
                    weights,
                    inv,
                    target,
                    feature,
                    weights[target].get(feature, 0.0) + tau * value,
                )
                set_weight(
                    weights,
                    inv,
                    wrong,
                    feature,
                    weights[wrong].get(feature, 0.0) - tau * value,
                )
            updates += 1
            cumulative_loss += loss

    return weights, {
        "training_examples": len(cids) * len(slots) * EPOCHS,
        "updates": updates,
        "update_rate": round(updates / (len(cids) * len(slots) * EPOCHS), 6),
        "mean_positive_loss_over_updates": round(cumulative_loss / max(1, updates), 6),
        "top_hardest_pairs": [
            {"target_concept_id": target, "wrong_concept_id": wrong, "count": count}
            for (target, wrong), count in hardest_pairs.most_common(20)
        ],
    }


def signed_topk_quantized(weights):
    pruned = {}
    for cid, original in weights.items():
        values = dict(
            sorted(original.items(), key=lambda item: (-abs(item[1]), item[0]))[:TOPK]
        )
        norm = math.sqrt(sum(value * value for value in values.values()))
        if norm:
            values = {feature: value / norm for feature, value in values.items()}
        pruned[cid] = values

    maximum = max(abs(value) for values in pruned.values() for value in values.values())
    scale = 127.0 / maximum
    quantized = {}
    for cid, values in pruned.items():
        current = {}
        for feature, value in values.items():
            q = round(value * scale)
            if q == 0:
                q = 1 if value > 0 else -1
            current[feature] = max(-127, min(127, q))
        quantized[cid] = current
    return quantized


def evaluate(cids, phrases, holdout, vocab, idf, quantized, *, context):
    inv = sc.inverted(quantized)
    ranks = []
    for target in cids:
        q = sc.vector(phrases[target][holdout], vocab, idf, context=context)
        scores = sc.scores_for(q, inv)
        order = sc.ranked(cids, scores)
        ranks.append(order.index(target) + 1)
    return ranks


def build_full(cids, phrases, *, context):
    slots = list(range(PHRASES_PER_CONCEPT))
    docs = [phrases[cid][slot] for cid in cids for slot in slots]
    vocab, idf = sc.fit_idf(docs, context=context)
    positive = sc.centroids(cids, phrases, slots, vocab, idf, context=context)
    trained, train_stats = train_pa(
        cids, phrases, slots, vocab, idf, positive, context=context
    )
    quantized = signed_topk_quantized(trained)
    artifact = sc.runtime_blob(cids, idf, quantized, signed=True)
    artifact["training"] = train_stats
    return artifact


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument(
        "--control",
        default="research/evaluation/v31/compile-time-semantic-a593-sparse-paper-note.json",
    )
    ap.add_argument(
        "--incumbent-hard-negative",
        default="research/evaluation/v31/compile-time-semantic-a593-hard-negative-distillation.json",
    )
    ap.add_argument("--output", default="artifacts/a593-pairwise-sparse-student.json")
    args = ap.parse_args()

    control = json.loads(Path(args.control).read_text(encoding="utf-8"))
    incumbent = json.loads(Path(args.incumbent_hard_negative).read_text(encoding="utf-8"))
    if control["selected_candidate"]["variant"] != "char34_centroid_u8_top300":
        raise RuntimeError("top300 control drift")
    if incumbent["selected_variant"] != "hard_negative_discount_alpha_0.75":
        raise RuntimeError("hard-negative incumbent drift")

    cids, phrases = sparse.load_teacher(Path(args.teacher))
    ranks = {
        "char34_top300_control": [],
        "char34_pairwise_pa1_top300": [],
        "char34_bigram_pairwise_pa1_top300": [],
    }
    update_stats = {False: [], True: []}

    for holdout in range(PHRASES_PER_CONCEPT):
        slots = [slot for slot in range(PHRASES_PER_CONCEPT) if slot != holdout]
        docs = [phrases[cid][slot] for cid in cids for slot in slots]
        for context in (False, True):
            vocab, idf = sc.fit_idf(docs, context=context)
            positive = sc.centroids(cids, phrases, slots, vocab, idf, context=context)
            if not context:
                control_q = sc.positive_topk_quantized(positive)
                ranks["char34_top300_control"].extend(
                    sc.evaluate_holdout(
                        cids, phrases, holdout, vocab, idf, control_q, context=False
                    )
                )

            trained, stats = train_pa(
                cids, phrases, slots, vocab, idf, positive, context=context
            )
            update_stats[context].append(stats)
            quantized = signed_topk_quantized(trained)
            key = (
                "char34_bigram_pairwise_pa1_top300"
                if context else "char34_pairwise_pa1_top300"
            )
            ranks[key].extend(
                evaluate(
                    cids, phrases, holdout, vocab, idf, quantized, context=context
                )
            )

    metrics = {key: summarize(values) for key, values in ranks.items()}
    expected = control["char_centroid_variants"]["char34_centroid_u8_top300"]
    actual = metrics["char34_top300_control"]
    if (actual["top1_count"], actual["hit_at_5_count"], actual["mrr"]) != (
        expected["top1_count"], expected["hit_at_5_count"], expected["mrr"]
    ):
        raise RuntimeError("control parity failed")

    challenger_keys = [
        "char34_pairwise_pa1_top300",
        "char34_bigram_pairwise_pa1_top300",
    ]
    selected = max(
        challenger_keys,
        key=lambda key: (
            metrics[key]["mrr"],
            metrics[key]["top1_rate"],
            metrics[key]["hit_at_5_rate"],
        ),
    )
    incumbent_metrics = incumbent["selected_metrics"]
    winner = metrics[selected]
    replay_gate = (
        winner["mrr"] > incumbent_metrics["mrr"]
        and (
            winner["top1_count"] > incumbent_metrics["top1_count"]
            or winner["hit_at_5_count"] > incumbent_metrics["hit_at_5_count"]
        )
    )

    artifacts = {
        "char34_pairwise_pa1_top300": build_full(cids, phrases, context=False),
        "char34_bigram_pairwise_pa1_top300": build_full(cids, phrases, context=True),
    }
    result = {
        "schema_version": 1,
        "status": "A593 corpus-internal pairwise sparse-student diagnostic; no opened evaluation queries used",
        "corpus": {
            "concepts": len(cids),
            "phrases": len(cids) * PHRASES_PER_CONCEPT,
            "outer_folds": PHRASES_PER_CONCEPT,
        },
        "fixed_design": {
            "algorithm": "one-pass multiclass Passive-Aggressive initialized from positive TF-IDF centroids",
            "margin": MARGIN,
            "epochs": EPOCHS,
            "hard_negative": "highest-scoring wrong concept under current student for each training phrase",
            "topk_features_per_concept": TOPK,
            "quantization": "global int8 after per-concept L2 normalization",
            "challenger_selection_rule": "highest MRR, then Top1, then Hit@5 across the two predeclared pairwise challengers",
            "opened_replay_gate": "challenger must beat frozen clamped-hard-negative incumbent on MRR and on at least one of Top1 or Hit@5",
        },
        "variants": metrics,
        "incumbent_hard_negative": incumbent_metrics,
        "selected_variant": selected,
        "selected_metrics": winner,
        "delta_vs_incumbent": {
            "top1_count": winner["top1_count"] - incumbent_metrics["top1_count"],
            "hit_at_5_count": winner["hit_at_5_count"] - incumbent_metrics["hit_at_5_count"],
            "mrr": round(winner["mrr"] - incumbent_metrics["mrr"], 6),
        },
        "opened_replay_gate_passed": replay_gate,
        "artifacts": artifacts,
        "fold_training_summary": {
            "char34": {
                "mean_updates": round(statistics.mean(x["updates"] for x in update_stats[False]), 3),
                "mean_update_rate": round(statistics.mean(x["update_rate"] for x in update_stats[False]), 6),
            },
            "char34_bigram": {
                "mean_updates": round(statistics.mean(x["updates"] for x in update_stats[True]), 3),
                "mean_update_rate": round(statistics.mean(x["update_rate"] for x in update_stats[True]), 6),
            },
        },
        "selected_candidate": {
            "id": "YV-A593-" + selected.replace("_", "-") + "-v0",
            "runtime_shape": "char3/4 TF-IDF with optional adjacent stemmed bigrams + signed int8 sparse concept dot products",
            "teacher_dependency_at_runtime": False,
            "artifact": artifacts[selected],
        },
        "guard": (
            "Selection and replay-gate decisions use only frozen Gemma outer-fold evidence plus the previously frozen corpus-internal incumbent metrics. "
            "Do not inspect opened 17/88 outcomes unless opened_replay_gate_passed is true."
        ),
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "selected_variant": selected,
                "selected_metrics": winner,
                "incumbent": incumbent_metrics,
                "delta_vs_incumbent": result["delta_vs_incumbent"],
                "opened_replay_gate_passed": replay_gate,
                "artifact": artifacts[selected],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
