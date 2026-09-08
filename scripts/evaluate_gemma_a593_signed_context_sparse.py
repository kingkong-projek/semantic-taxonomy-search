#!/usr/bin/env python3
"""A593 signed hard-negative + cheap context sparse diagnostic.

Selection uses only the frozen 593-concept / 4,744-phrase Gemma corpus. For each
of eight outer folds, one prompt slot per concept is held out and the other seven
slots build the student. No opened 17/88 query participates.

Four fixed candidates are compared, without a hyperparameter search:
1. char34_top300_control: prior character 3/4-gram centroid family.
2. char34_signed_a075_top300: allow hard-negative evidence to become signed int8.
3. char34_bigram_top300: add adjacent Swedish-Snowball word-bigram context features.
4. char34_bigram_signed_a075_top300: combine cheap context with signed negatives.

alpha=0.75 and hard-k=3 are inherited from the already-frozen A593 hard-negative
checkpoint. Runtime remains feature extraction + TF-IDF + sparse dot products.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import math
import statistics
import struct
from pathlib import Path

import evaluate_gemma_a593_sparse_paper_note as sparse
from evaluate_gemma_a593_phrase_representation import stemmed_tokens

PHRASES_PER_CONCEPT = 8
TOPK = 300
HARD_K = 3
ALPHA = 0.75
MIN_DF = 2


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


def text_features(text, *, context):
    out = ["c:" + feature for feature in sparse.char_wb_ngrams(text)]
    if context:
        stems = [token for token in stemmed_tokens(text) if token]
        out.extend(
            "b:" + left + "_" + right
            for left, right in zip(stems, stems[1:])
        )
    return out


def fit_idf(documents, *, context):
    df = collections.Counter()
    for text in documents:
        df.update(set(text_features(text, context=context)))
    vocab = {feature for feature, count in df.items() if count >= MIN_DF}
    n = len(documents)
    idf = {
        feature: math.log((1 + n) / (1 + df[feature])) + 1.0
        for feature in vocab
    }
    return vocab, idf


def vector(text, vocab, idf, *, context):
    counts = collections.Counter(
        feature for feature in text_features(text, context=context) if feature in vocab
    )
    values = {
        feature: (1.0 + math.log(count)) * idf[feature]
        for feature, count in counts.items()
    }
    norm = math.sqrt(sum(value * value for value in values.values()))
    if norm:
        values = {feature: value / norm for feature, value in values.items()}
    return values


def centroids(cids, phrases, slots, vocab, idf, *, context):
    out = {}
    for cid in cids:
        values = collections.defaultdict(float)
        for slot in slots:
            for feature, value in vector(
                phrases[cid][slot], vocab, idf, context=context
            ).items():
                values[feature] += value
        norm = math.sqrt(sum(value * value for value in values.values()))
        if norm:
            values = collections.defaultdict(
                float, {feature: value / norm for feature, value in values.items()}
            )
        out[cid] = dict(values)
    return out


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


def ranked(cids, scores):
    return sorted(cids, key=lambda cid: (-scores.get(cid, 0.0), cid))


def mine_negative_profiles(cids, phrases, slots, vocab, idf, positive, *, context):
    inv = inverted(positive)
    negative_sum = {cid: collections.defaultdict(float) for cid in cids}
    negative_count = collections.Counter()
    pair_count = collections.Counter()

    for target in cids:
        for slot in slots:
            q = vector(phrases[target][slot], vocab, idf, context=context)
            scores = scores_for(q, inv)
            wrongs = [cid for cid in ranked(cids, scores) if cid != target][:HARD_K]
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
    return negative, negative_count, hubs, pair_count


def positive_topk_quantized(positive):
    pruned = {}
    for cid, original in positive.items():
        values = dict(sorted(original.items(), key=lambda item: (-item[1], item[0]))[:TOPK])
        norm = math.sqrt(sum(value * value for value in values.values()))
        if norm:
            values = {feature: value / norm for feature, value in values.items()}
        pruned[cid] = values
    maximum = max(value for values in pruned.values() for value in values.values())
    scale = 255.0 / maximum
    return {
        cid: {
            feature: max(1, min(255, round(value * scale)))
            for feature, value in values.items()
        }
        for cid, values in pruned.items()
    }


def signed_topk_quantized(positive, negative, hubs):
    adjusted = {}
    for cid in positive:
        pos = positive[cid]
        neg = negative[cid]
        hub = hubs[cid]
        union = set(pos) | set(neg)
        values = {
            feature: pos.get(feature, 0.0) - ALPHA * hub * neg.get(feature, 0.0)
            for feature in union
        }
        values = {feature: value for feature, value in values.items() if value != 0.0}
        values = dict(
            sorted(values.items(), key=lambda item: (-abs(item[1]), item[0]))[:TOPK]
        )
        norm = math.sqrt(sum(value * value for value in values.values()))
        if norm:
            values = {feature: value / norm for feature, value in values.items()}
        adjusted[cid] = values

    maximum = max(abs(value) for values in adjusted.values() for value in values.values())
    scale = 127.0 / maximum
    quantized = {}
    for cid, values in adjusted.items():
        current = {}
        for feature, value in values.items():
            q = round(value * scale)
            if q == 0:
                q = 1 if value > 0 else -1
            current[feature] = max(-127, min(127, q))
        quantized[cid] = current
    return quantized


def evaluate_holdout(cids, phrases, holdout, vocab, idf, weights, *, context):
    inv = inverted(weights)
    ranks = []
    for target in cids:
        q = vector(phrases[target][holdout], vocab, idf, context=context)
        order = ranked(cids, scores_for(q, inv))
        ranks.append(order.index(target) + 1)
    return ranks


def runtime_blob(cids, idf, weights, *, signed):
    # Only features actually used by concept weights need ship. Query features absent
    # from the index cannot affect a score.
    features = sorted({feature for values in weights.values() for feature in values})
    if len(features) >= 65536:
        raise RuntimeError("selected feature dictionary no longer fits uint16")
    feature_id = {feature: index for index, feature in enumerate(features)}
    blob = bytearray()
    dictionary = "\0".join(features).encode("utf-8")
    blob.extend(struct.pack("<I", len(dictionary)))
    blob.extend(dictionary)
    blob.append(0)
    # Runtime-complete accounting: TF-IDF query weighting requires one IDF value per
    # retained feature. float32 is intentionally simple/conservative here.
    for feature in features:
        blob.extend(struct.pack("<f", float(idf[feature])))
    for cid in cids:
        values = weights[cid]
        blob.extend(struct.pack("<H", len(values)))
        for feature, weight in sorted(values.items(), key=lambda item: feature_id[item[0]]):
            if signed:
                blob.extend(struct.pack("<Hb", feature_id[feature], int(weight)))
            else:
                blob.extend(struct.pack("<HB", feature_id[feature], int(weight)))
    raw = bytes(blob)
    return {
        "feature_count": len(features),
        "nonzero_weight_count": sum(len(values) for values in weights.values()),
        "runtime_complete_raw_bytes": len(raw),
        "runtime_complete_gzip9_bytes": len(gzip.compress(raw, compresslevel=9, mtime=0)),
        "includes_idf_float32": True,
        "weight_storage": "int8" if signed else "uint8",
        "feature_id_storage": "uint16",
    }


def build_full_variant(cids, phrases, *, context, signed):
    slots = list(range(PHRASES_PER_CONCEPT))
    docs = [phrases[cid][slot] for cid in cids for slot in slots]
    vocab, idf = fit_idf(docs, context=context)
    positive = centroids(cids, phrases, slots, vocab, idf, context=context)
    if signed:
        negative, counts, hubs, pairs = mine_negative_profiles(
            cids, phrases, slots, vocab, idf, positive, context=context
        )
        weights = signed_topk_quantized(positive, negative, hubs)
        mining = {
            "false_candidate_assignments": sum(counts.values()),
            "unique_directed_pairs": len(pairs),
        }
    else:
        weights = positive_topk_quantized(positive)
        mining = None
    return runtime_blob(cids, idf, weights, signed=signed), mining


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument(
        "--control",
        default="research/evaluation/v31/compile-time-semantic-a593-sparse-paper-note.json",
    )
    ap.add_argument(
        "--hard-negative",
        default="research/evaluation/v31/compile-time-semantic-a593-hard-negative-distillation.json",
    )
    ap.add_argument("--output", default="artifacts/a593-signed-context-sparse.json")
    args = ap.parse_args()

    control = json.loads(Path(args.control).read_text(encoding="utf-8"))
    if control["selected_candidate"]["variant"] != "char34_centroid_u8_top300":
        raise RuntimeError("top300 control drift")
    hard = json.loads(Path(args.hard_negative).read_text(encoding="utf-8"))
    if hard["selected_variant"] != "hard_negative_discount_alpha_0.75":
        raise RuntimeError("frozen hard-negative alpha drift")

    cids, phrases = sparse.load_teacher(Path(args.teacher))
    variants = {
        "char34_top300_control": [],
        "char34_signed_a075_top300": [],
        "char34_bigram_top300": [],
        "char34_bigram_signed_a075_top300": [],
    }

    for holdout in range(PHRASES_PER_CONCEPT):
        slots = [slot for slot in range(PHRASES_PER_CONCEPT) if slot != holdout]
        docs = [phrases[cid][slot] for cid in cids for slot in slots]

        for context in (False, True):
            vocab, idf = fit_idf(docs, context=context)
            positive = centroids(cids, phrases, slots, vocab, idf, context=context)
            positive_q = positive_topk_quantized(positive)
            base_key = "char34_bigram_top300" if context else "char34_top300_control"
            variants[base_key].extend(
                evaluate_holdout(
                    cids, phrases, holdout, vocab, idf, positive_q, context=context
                )
            )

            negative, _counts, hubs, _pairs = mine_negative_profiles(
                cids, phrases, slots, vocab, idf, positive, context=context
            )
            signed_q = signed_topk_quantized(positive, negative, hubs)
            signed_key = (
                "char34_bigram_signed_a075_top300"
                if context else "char34_signed_a075_top300"
            )
            variants[signed_key].extend(
                evaluate_holdout(
                    cids, phrases, holdout, vocab, idf, signed_q, context=context
                )
            )

    metrics = {key: summarize(ranks) for key, ranks in variants.items()}
    control_metrics = metrics["char34_top300_control"]
    expected = control["char_centroid_variants"]["char34_centroid_u8_top300"]
    if (
        control_metrics["top1_count"],
        control_metrics["hit_at_5_count"],
        control_metrics["mrr"],
    ) != (expected["top1_count"], expected["hit_at_5_count"], expected["mrr"]):
        raise RuntimeError(
            f"control parity failed: {control_metrics} != prior {expected}"
        )

    candidate_keys = [key for key in metrics if key != "char34_top300_control"]
    winner = max(
        candidate_keys,
        key=lambda key: (
            metrics[key]["hit_at_5_rate"],
            metrics[key]["mrr"],
            metrics[key]["top1_rate"],
        ),
    )
    winner_context = "bigram" in winner
    winner_signed = "signed" in winner

    artifacts = {}
    for key, context, signed in (
        ("char34_top300_control", False, False),
        ("char34_signed_a075_top300", False, True),
        ("char34_bigram_top300", True, False),
        ("char34_bigram_signed_a075_top300", True, True),
    ):
        artifact, mining = build_full_variant(
            cids, phrases, context=context, signed=signed
        )
        artifacts[key] = artifact
        if mining is not None:
            artifacts[key]["hard_negative_mining"] = mining

    result = {
        "schema_version": 1,
        "status": "A593 corpus-internal signed/context sparse diagnostic; no opened evaluation queries used",
        "corpus": {
            "concepts": len(cids),
            "phrases": len(cids) * PHRASES_PER_CONCEPT,
            "outer_folds": PHRASES_PER_CONCEPT,
        },
        "fixed_design": {
            "topk_features_per_concept": TOPK,
            "hard_negative_wrong_candidates_per_phrase": HARD_K,
            "signed_alpha": ALPHA,
            "context_feature": "adjacent Swedish-Snowball stemmed word bigram prefixed b:",
            "base_feature": "word-boundary character 3/4-gram prefixed c:",
            "selection_rule": "highest Hit@5, then MRR, then Top1 among the three predeclared challengers; no opened-query tuning",
        },
        "variants": metrics,
        "artifacts": artifacts,
        "selected_variant": winner,
        "selected_metrics": metrics[winner],
        "selected_candidate": {
            "id": "YV-A593-" + winner.replace("_", "-") + "-v0",
            "context_features": winner_context,
            "signed_hard_negative_weights": winner_signed,
            "runtime_shape": "deterministic sparse TF-IDF feature extraction + int8/uint8 concept dot products",
            "teacher_dependency_at_runtime": False,
            "artifact": artifacts[winner],
        },
        "delta_vs_char34_top300": {
            "top1_count": metrics[winner]["top1_count"] - control_metrics["top1_count"],
            "hit_at_5_count": metrics[winner]["hit_at_5_count"] - control_metrics["hit_at_5_count"],
            "mrr": round(metrics[winner]["mrr"] - control_metrics["mrr"], 6),
        },
        "size_accounting_note": (
            "Earlier A593 compact-binary figures stored the feature dictionary and concept weights but omitted IDF values required by runtime TF-IDF. "
            "The runtime-complete figures here include float32 IDF for every retained feature; quality metrics are unaffected."
        ),
        "guard": (
            "All selection evidence is Gemma-authored outer-fold holdout evidence. Freeze the winning candidate before any opened 17/88 replay; "
            "opened outcomes may diagnose/falsify but must not select features or variants."
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
                "selected_variant": winner,
                "selected_metrics": metrics[winner],
                "delta_vs_control": result["delta_vs_char34_top300"],
                "artifacts": artifacts,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
