#!/usr/bin/env python3
"""A593 corpus-internal sparse distillation diagnostic.

No opened 17/88 evaluation queries participate in candidate selection.

The experiment starts from a literal "paper note" idea (concept-specific token
weights) and then tests a stronger but still tiny deterministic representation:
character 3/4-gram TF-IDF centroids distilled per occupation, pruned to a fixed number
of features and globally quantized to uint8. Runtime semantics are table lookup + dot
products; no model inference ships to the client.
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import math
import re
import statistics
import struct
from pathlib import Path
from typing import Iterable

from evaluate_gemma_a593_phrase_representation import stemmed_tokens

EXPECTED_CONCEPTS = 593
PHRASES_PER_CONCEPT = 8
TOPK_VALUES = (100, 200, 300)
WS_RE = re.compile(r"\s+")


def load_teacher(path: Path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != EXPECTED_CONCEPTS:
        raise RuntimeError(f"teacher concept drift: {len(rows)} != {EXPECTED_CONCEPTS}")
    phrases = {}
    for row in rows:
        cid = str(row.get("concept_id") or "")
        values = [str(x).strip() for x in row.get("phrases") or [] if str(x).strip()]
        if not cid or cid in phrases or len(values) != PHRASES_PER_CONCEPT:
            raise RuntimeError(f"invalid teacher row for {cid!r}")
        phrases[cid] = values
    return sorted(phrases), phrases


def summarize(ranks):
    return {
        "cases": len(ranks),
        "top1_count": sum(rank == 1 for rank in ranks),
        "top1_rate": round(sum(rank == 1 for rank in ranks) / len(ranks), 6),
        "hit_at_5_count": sum(rank <= 5 for rank in ranks),
        "hit_at_5_rate": round(sum(rank <= 5 for rank in ranks) / len(ranks), 6),
        "mrr": round(sum(1.0 / rank for rank in ranks) / len(ranks), 6),
        "median_rank": statistics.median(ranks),
    }


def rank_of_target(cids, scores, target):
    target_score = scores.get(target, 0.0)
    return 1 + sum(
        1
        for candidate in cids
        if scores.get(candidate, 0.0) > target_score
        or (scores.get(candidate, 0.0) == target_score and candidate < target)
    )


def evaluate_paper_note(cids, phrases):
    ranks = []
    all_slots = set(range(PHRASES_PER_CONCEPT))
    for holdout in range(PHRASES_PER_CONCEPT):
        slots = sorted(all_slots - {holdout})
        df = collections.Counter()
        counts = {}
        for cid in cids:
            current = collections.Counter()
            for slot in slots:
                current.update(set(stemmed_tokens(phrases[cid][slot])))
            counts[cid] = current
            df.update(current.keys())
        weights = {}
        for cid, current in counts.items():
            weights[cid] = {
                token: math.log(1.0 + (len(cids) - df[token] + 0.5) / (df[token] + 0.5))
                * math.sqrt(count / len(slots))
                for token, count in current.items()
            }
        inverted = collections.defaultdict(list)
        for cid, current in weights.items():
            for token, value in current.items():
                inverted[token].append((cid, value))
        for target in cids:
            scores = collections.defaultdict(float)
            for token in set(stemmed_tokens(phrases[target][holdout])):
                for candidate, value in inverted.get(token, ()):
                    scores[candidate] += value
            ranks.append(rank_of_target(cids, scores, target))
    return summarize(ranks)


def char_wb_ngrams(text):
    text = WS_RE.sub(" ", text.casefold()).strip()
    result = []
    for word in text.split(" "):
        if not word:
            continue
        padded = f" {word} "
        for n in (3, 4):
            if len(padded) >= n:
                result.extend(padded[i : i + n] for i in range(len(padded) - n + 1))
    return result


def fit_idf(documents):
    df = collections.Counter()
    for text in documents:
        df.update(set(char_wb_ngrams(text)))
    vocab = {feature for feature, count in df.items() if count >= 2}
    n = len(documents)
    return vocab, {feature: math.log((1 + n) / (1 + df[feature])) + 1.0 for feature in vocab}


def tfidf_vector(text, vocab, idf):
    counts = collections.Counter(feature for feature in char_wb_ngrams(text) if feature in vocab)
    values = {feature: (1.0 + math.log(count)) * idf[feature] for feature, count in counts.items()}
    norm = math.sqrt(sum(value * value for value in values.values()))
    if norm:
        values = {feature: value / norm for feature, value in values.items()}
    return values


def full_centroids(cids, phrases, slots, vocab, idf):
    centroids = {}
    for cid in cids:
        values = collections.defaultdict(float)
        for slot in slots:
            for feature, value in tfidf_vector(phrases[cid][slot], vocab, idf).items():
                values[feature] += value
        norm = math.sqrt(sum(value * value for value in values.values()))
        if norm:
            values = collections.defaultdict(float, {feature: value / norm for feature, value in values.items()})
        centroids[cid] = dict(values)
    return centroids


def prune_quantize(centroids, topk):
    pruned = {}
    for cid, original in centroids.items():
        values = dict(sorted(original.items(), key=lambda item: (-item[1], item[0]))[:topk])
        norm = math.sqrt(sum(value * value for value in values.values()))
        if norm:
            values = {feature: value / norm for feature, value in values.items()}
        pruned[cid] = values
    max_weight = max(value for values in pruned.values() for value in values.values())
    scale = 255.0 / max_weight
    quantized = {
        cid: {feature: max(1, min(255, round(value * scale))) for feature, value in values.items()}
        for cid, values in pruned.items()
    }
    return quantized, max_weight


def compact_binary(cids, vocab, quantized):
    features = sorted(vocab)
    if len(features) >= 65536:
        raise RuntimeError("feature vocabulary no longer fits uint16")
    feature_id = {feature: index for index, feature in enumerate(features)}
    blob = bytearray("\0".join(features).encode("utf-8"))
    blob.append(0)
    for cid in cids:
        values = quantized[cid]
        blob.extend(struct.pack("<H", len(values)))
        for feature, weight in sorted(values.items(), key=lambda item: feature_id[item[0]]):
            blob.extend(struct.pack("<HB", feature_id[feature], weight))
    return bytes(blob)


def evaluate_centroid_variants(cids, phrases):
    all_slots = set(range(PHRASES_PER_CONCEPT))
    ranks = {topk: [] for topk in TOPK_VALUES}
    raw_sizes = {topk: [] for topk in TOPK_VALUES}
    gzip_sizes = {topk: [] for topk in TOPK_VALUES}
    feature_counts = []
    nonzero_counts = {topk: [] for topk in TOPK_VALUES}

    for holdout in range(PHRASES_PER_CONCEPT):
        slots = sorted(all_slots - {holdout})
        documents = [phrases[cid][slot] for cid in cids for slot in slots]
        vocab, idf = fit_idf(documents)
        feature_counts.append(len(vocab))
        centroids = full_centroids(cids, phrases, slots, vocab, idf)
        queries = {cid: tfidf_vector(phrases[cid][holdout], vocab, idf) for cid in cids}

        for topk in TOPK_VALUES:
            quantized, _ = prune_quantize(centroids, topk)
            inverted = collections.defaultdict(list)
            for cid, values in quantized.items():
                for feature, weight in values.items():
                    inverted[feature].append((cid, weight))
            for target in cids:
                scores = collections.defaultdict(float)
                for feature, query_weight in queries[target].items():
                    for candidate, candidate_weight in inverted.get(feature, ()):
                        scores[candidate] += query_weight * candidate_weight
                ranks[topk].append(rank_of_target(cids, scores, target))
            blob = compact_binary(cids, vocab, quantized)
            raw_sizes[topk].append(len(blob))
            gzip_sizes[topk].append(len(gzip.compress(blob, compresslevel=9)))
            nonzero_counts[topk].append(sum(len(values) for values in quantized.values()))

    result = {}
    for topk in TOPK_VALUES:
        current = summarize(ranks[topk])
        current.update(
            {
                "topk_features_per_concept": topk,
                "quantization": "global uint8 over normalized centroid weights",
                "char_wb_ngram_range": [3, 4],
                "min_phrase_df": 2,
                "fold_feature_count_mean": round(sum(feature_counts) / len(feature_counts)),
                "fold_nonzero_weight_count_mean": round(sum(nonzero_counts[topk]) / len(nonzero_counts[topk])),
                "fold_artifact_raw_bytes_mean": round(sum(raw_sizes[topk]) / len(raw_sizes[topk])),
                "fold_artifact_gzip9_bytes_mean": round(sum(gzip_sizes[topk]) / len(gzip_sizes[topk])),
            }
        )
        result[f"char34_centroid_u8_top{topk}"] = current
    return result


def full_artifact_size(cids, phrases, topk):
    slots = list(range(PHRASES_PER_CONCEPT))
    documents = [phrases[cid][slot] for cid in cids for slot in slots]
    vocab, idf = fit_idf(documents)
    centroids = full_centroids(cids, phrases, slots, vocab, idf)
    quantized, max_weight = prune_quantize(centroids, topk)
    blob = compact_binary(cids, vocab, quantized)
    return {
        "feature_count": len(vocab),
        "nonzero_weight_count": sum(len(values) for values in quantized.values()),
        "compact_binary_raw_bytes": len(blob),
        "compact_binary_gzip9_bytes": len(gzip.compress(blob, compresslevel=9)),
        "weight_max_before_global_u8_quantization": round(max_weight, 9),
        "binary_layout": "NUL-separated UTF-8 feature dictionary + uint16 feature ids + uint8 weights",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--baseline", default="research/evaluation/v31/compile-time-semantic-a593-phrase-representation.json")
    ap.add_argument("--output", default="artifacts/a593-sparse-paper-note.json")
    args = ap.parse_args()

    cids, phrases = load_teacher(Path(args.teacher))
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    paper_note = evaluate_paper_note(cids, phrases)
    centroid = evaluate_centroid_variants(cids, phrases)
    selected = max(
        centroid,
        key=lambda key: (
            centroid[key]["hit_at_5_rate"],
            centroid[key]["mrr"],
            centroid[key]["top1_rate"],
            -centroid[key]["fold_artifact_gzip9_bytes_mean"],
        ),
    )
    topk = int(selected.rsplit("top", 1)[1])
    result = {
        "schema_version": 1,
        "status": "A593 corpus-internal sparse distillation diagnostic; no opened evaluation queries used",
        "corpus": {"concepts": len(cids), "teacher_phrases": len(cids) * PHRASES_PER_CONCEPT, "folds": 8},
        "reference": {
            "flattened_raw": baseline["variants"]["flattened_raw"]["overall"],
            "flattened_snowball_sv": baseline["variants"]["flattened_snowball_sv"]["overall"],
        },
        "literal_paper_note": {
            "id": "stemmed-token-stability-x-concept-idf",
            "definition": "weight = concept-IDF * sqrt(training-phrase-presence / 7)",
            "overall": paper_note,
        },
        "char_centroid_variants": centroid,
        "selected_candidate": {
            "id": f"YV-A593-char34-centroid-u8-top{topk}-v0",
            "variant": selected,
            "selection_rule": "highest corpus-internal Hit@5, then MRR, then Top1, then smaller gzip bytes among fixed 100/200/300 candidates",
            "selection_evidence": centroid[selected],
            "full_eight_phrase_artifact": full_artifact_size(cids, phrases, topk),
            "runtime_shape": "char_wb 3/4-grams + TF-IDF query + sparse uint8 concept-centroid dot products",
            "teacher_dependency_at_runtime": False,
        },
        "guard": "Gemma-authored training-distribution evidence only. Freeze this candidate before any opened 17/88 replay; never tune it from those outcomes.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
