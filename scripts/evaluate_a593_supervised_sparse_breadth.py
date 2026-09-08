#!/usr/bin/env python3
"""Construction diagnostic for breadth entrant B: supervised sparse classifier.

This is deliberately not a promotion test. It uses only the frozen A593 teacher
corpus and a fixed phrase-slot split to ask a narrow architecture question:
with essentially the same char-ngram representation, does a discriminative
objective have a materially higher ceiling than an occupation centroid?

Opened 17/88 queries are never loaded here.
"""
from __future__ import annotations

import argparse
import gzip
import json
import statistics
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import normalize

EXPECTED_CONCEPTS = 593
PHRASES_PER_CONCEPT = 8
TRAIN_SLOTS = tuple(range(7))
TEST_SLOT = 7
MAX_FEATURES = 30000
TOP_WEIGHTS_PER_CONCEPT = 300
RANDOM_STATE = 0


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
        "top1_count": int(sum(rank == 1 for rank in ranks)),
        "top1_rate": round(sum(rank == 1 for rank in ranks) / len(ranks), 6),
        "hit_at_5_count": int(sum(rank <= 5 for rank in ranks)),
        "hit_at_5_rate": round(sum(rank <= 5 for rank in ranks) / len(ranks), 6),
        "mrr": round(sum(1.0 / rank for rank in ranks) / len(ranks), 6),
        "median_rank": float(statistics.median(ranks)),
    }


def ranks_from_scores(scores: np.ndarray, classes: list[str], targets: list[str]):
    class_to_index = {cid: i for i, cid in enumerate(classes)}
    ranks = []
    for row_index, target in enumerate(targets):
        target_index = class_to_index[target]
        target_score = float(scores[row_index, target_index])
        rank = 1
        for candidate_index, cid in enumerate(classes):
            value = float(scores[row_index, candidate_index])
            if value > target_score or (value == target_score and cid < target):
                rank += 1
        ranks.append(rank)
    return ranks


def prune_rows(matrix: np.ndarray, topk: int):
    rows = []
    cols = []
    data = []
    for row_index in range(matrix.shape[0]):
        values = matrix[row_index]
        if topk >= len(values):
            chosen = np.arange(len(values))
        else:
            chosen = np.argpartition(np.abs(values), -topk)[-topk:]
        chosen = chosen[np.argsort(chosen)]
        for col_index in chosen:
            value = float(values[col_index])
            if value == 0.0:
                continue
            rows.append(row_index)
            cols.append(int(col_index))
            data.append(value)
    return sparse.csr_matrix((data, (rows, cols)), shape=matrix.shape, dtype=np.float32)


def quantize_signed_per_row(matrix: sparse.csr_matrix):
    q_rows = []
    q_cols = []
    q_data = []
    scales = np.zeros(matrix.shape[0], dtype=np.float32)
    for row_index in range(matrix.shape[0]):
        start, end = matrix.indptr[row_index], matrix.indptr[row_index + 1]
        cols = matrix.indices[start:end]
        vals = matrix.data[start:end]
        max_abs = float(np.max(np.abs(vals))) if len(vals) else 0.0
        scale = max_abs / 127.0 if max_abs else 1.0
        scales[row_index] = scale
        for col_index, value in zip(cols, vals):
            quantized = int(np.clip(np.rint(float(value) / scale), -127, 127)) if max_abs else 0
            if quantized:
                q_rows.append(row_index)
                q_cols.append(int(col_index))
                q_data.append(quantized)
    quantized = sparse.csr_matrix(
        (np.asarray(q_data, dtype=np.int8), (q_rows, q_cols)),
        shape=matrix.shape,
        dtype=np.int8,
    )
    return quantized, scales


def dequantized_scores(x_test, quantized, scales, intercept=None):
    q_float = quantized.astype(np.float32)
    weighted = sparse.diags(scales).dot(q_float)
    scores = x_test.dot(weighted.T).toarray()
    if intercept is not None:
        scores += np.asarray(intercept, dtype=np.float32)[None, :]
    return scores


def compact_size(vocabulary: dict[str, int], quantized: sparse.csr_matrix, scales, intercept=None):
    features = [None] * len(vocabulary)
    for token, index in vocabulary.items():
        features[index] = token
    feature_blob = ("\0".join(features) + "\0").encode("utf-8")
    feature_id_bytes = 2 if len(features) < 65536 else 4
    nonzero = int(quantized.nnz)
    payload = bytearray(feature_blob)
    payload.extend(b"\0" * (quantized.shape[0] * 2))  # per-row count
    payload.extend(b"\0" * (nonzero * (feature_id_bytes + 1)))  # feature id + int8 weight
    payload.extend(np.asarray(scales, dtype=np.float32).tobytes())
    if intercept is not None:
        payload.extend(np.asarray(intercept, dtype=np.float32).tobytes())
    return {
        "feature_count": len(features),
        "feature_id_bytes": feature_id_bytes,
        "nonzero_weight_count": nonzero,
        "compact_binary_raw_bytes_estimate": len(payload),
        "compact_binary_gzip9_bytes_estimate": len(gzip.compress(bytes(payload), compresslevel=9)),
        "layout_note": "UTF-8 NUL feature dictionary + per-class count + feature id + int8 weight + float32 scale/intercept; gzip estimate uses zero-filled structural payload and is optimistic for ids/weights",
    }


def centroid_weights(x_train, y_train, classes):
    class_to_index = {cid: i for i, cid in enumerate(classes)}
    sums = sparse.lil_matrix((len(classes), x_train.shape[1]), dtype=np.float32)
    counts = np.zeros(len(classes), dtype=np.float32)
    for row_index, cid in enumerate(y_train):
        class_index = class_to_index[cid]
        sums[class_index] += x_train[row_index]
        counts[class_index] += 1.0
    centroids = sums.tocsr()
    for class_index, count in enumerate(counts):
        if count:
            centroids.data[centroids.indptr[class_index] : centroids.indptr[class_index + 1]] /= count
    return normalize(centroids, norm="l2", axis=1, copy=False)


def prune_sparse_positive(matrix: sparse.csr_matrix, topk: int):
    rows = []
    cols = []
    data = []
    for row_index in range(matrix.shape[0]):
        start, end = matrix.indptr[row_index], matrix.indptr[row_index + 1]
        row_cols = matrix.indices[start:end]
        row_vals = matrix.data[start:end]
        if len(row_vals) > topk:
            chosen = np.argpartition(row_vals, -topk)[-topk:]
            row_cols = row_cols[chosen]
            row_vals = row_vals[chosen]
        order = np.argsort(row_cols)
        for col_index, value in zip(row_cols[order], row_vals[order]):
            if value:
                rows.append(row_index)
                cols.append(int(col_index))
                data.append(float(value))
    return sparse.csr_matrix((data, (rows, cols)), shape=matrix.shape, dtype=np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--output", default="artifacts/a593-supervised-sparse-breadth.json")
    args = ap.parse_args()

    cids, phrases = load_teacher(Path(args.teacher))
    train_texts = []
    train_labels = []
    for cid in cids:
        for slot in TRAIN_SLOTS:
            train_texts.append(phrases[cid][slot])
            train_labels.append(cid)
    test_texts = [phrases[cid][TEST_SLOT] for cid in cids]
    test_targets = list(cids)

    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=2,
        max_features=MAX_FEATURES,
        sublinear_tf=True,
        norm="l2",
        dtype=np.float32,
        lowercase=True,
    )
    x_train = vectorizer.fit_transform(train_texts)
    x_test = vectorizer.transform(test_texts)

    centroid = centroid_weights(x_train, train_labels, cids)
    centroid_pruned = prune_sparse_positive(centroid, TOP_WEIGHTS_PER_CONCEPT)
    centroid_q, centroid_scales = quantize_signed_per_row(centroid_pruned)
    centroid_scores = dequantized_scores(x_test, centroid_q, centroid_scales)
    centroid_ranks = ranks_from_scores(centroid_scores, cids, test_targets)

    clf = SGDClassifier(
        loss="hinge",
        penalty="l2",
        alpha=1e-5,
        max_iter=2000,
        tol=1e-4,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        average=True,
    )
    clf.fit(x_train, train_labels)
    classes = [str(x) for x in clf.classes_]
    raw_scores = clf.decision_function(x_test)
    raw_ranks = ranks_from_scores(raw_scores, classes, test_targets)

    pruned = prune_rows(np.asarray(clf.coef_, dtype=np.float32), TOP_WEIGHTS_PER_CONCEPT)
    quantized, scales = quantize_signed_per_row(pruned)
    pruned_scores = dequantized_scores(x_test, quantized, scales, clf.intercept_)
    pruned_ranks = ranks_from_scores(pruned_scores, classes, test_targets)

    result = {
        "candidate": {
            "id": "YV-A593-supervised-sparse-B-construction-v0",
            "evidence_class": "construction diagnostic only; not promotion evidence",
            "representation": "TF-IDF char_wb 3-5 grams",
            "objective": "multiclass one-vs-rest linear hinge SGD",
            "runtime_shape": "sparse query features -> signed sparse class weights -> class scores",
            "opened_17_88_loaded": False,
        },
        "fixed_split": {
            "train_slots": list(TRAIN_SLOTS),
            "test_slot": TEST_SLOT,
            "train_cases": len(train_texts),
            "test_cases": len(test_texts),
            "concepts": len(cids),
        },
        "feature_config": {
            "max_features": MAX_FEATURES,
            "actual_features": len(vectorizer.vocabulary_),
            "min_df": 2,
            "top_weights_per_concept": TOP_WEIGHTS_PER_CONCEPT,
        },
        "same_feature_centroid_control_quantized_top300": summarize(centroid_ranks),
        "supervised_unpruned": summarize(raw_ranks),
        "supervised_signed_int8_top300": summarize(pruned_ranks),
        "delta_pruned_vs_centroid": {
            "top1_count": int(sum(rank == 1 for rank in pruned_ranks) - sum(rank == 1 for rank in centroid_ranks)),
            "hit_at_5_count": int(sum(rank <= 5 for rank in pruned_ranks) - sum(rank <= 5 for rank in centroid_ranks)),
            "mrr": round(
                sum(1.0 / rank for rank in pruned_ranks) / len(pruned_ranks)
                - sum(1.0 / rank for rank in centroid_ranks) / len(centroid_ranks),
                6,
            ),
        },
        "compiled_size_estimate": compact_size(vectorizer.vocabulary_, quantized, scales, clf.intercept_),
        "guard": "Do not select architecture from this teacher-slot diagnostic. Common prefrozen cross-style transfer proxy remains required before B/C comparison.",
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
