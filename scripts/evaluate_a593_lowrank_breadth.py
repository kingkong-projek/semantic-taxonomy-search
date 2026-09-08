#!/usr/bin/env python3
"""Final simple single-stage breadth falsifier: low-rank latent sparse student.

Fixed architecture, no sweep:
- char_wb 3-5 TF-IDF, max 30k features;
- supervised class aggregation into occupation centroids;
- one fixed 64-dimensional TruncatedSVD projection learned from class centroids;
- cosine ranking in the 64-d latent space;
- int8 projection + int8 class-vector diagnostic for plausible browser form.

Two frozen tests are reported:
1) A593 phrase slot 0-6 -> slot 7 construction holdout;
2) the 66 already-frozen source-bound hard-confusion descriptions.

Opened 17/88 is never loaded. No hyperparameter sweep is performed.
"""
from __future__ import annotations

import argparse
import gzip
import json
import statistics
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

EXPECTED_CONCEPTS = 593
PHRASES_PER_CONCEPT = 8
DIM = 64
MAX_FEATURES = 30000


def load_teacher(path: Path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    phrases = {}
    for row in rows:
        cid = str(row.get("concept_id") or "")
        values = [str(x).strip() for x in row.get("phrases") or [] if str(x).strip()]
        if not cid or cid in phrases or len(values) != PHRASES_PER_CONCEPT:
            raise RuntimeError(f"invalid teacher row {cid!r}")
        phrases[cid] = values
    if len(phrases) != EXPECTED_CONCEPTS:
        raise RuntimeError(f"teacher drift: {len(phrases)} != {EXPECTED_CONCEPTS}")
    return sorted(phrases), phrases


def class_centroids(x, labels, classes):
    class_index = {cid: i for i, cid in enumerate(classes)}
    rows, cols, data = [], [], []
    counts = np.zeros(len(classes), dtype=np.float32)
    accumulator = [dict() for _ in classes]
    for row_index, cid in enumerate(labels):
        ci = class_index[cid]
        counts[ci] += 1.0
        row = x.getrow(row_index)
        for col, value in zip(row.indices, row.data):
            accumulator[ci][int(col)] = accumulator[ci].get(int(col), 0.0) + float(value)
    for ci, values in enumerate(accumulator):
        denom = max(float(counts[ci]), 1.0)
        for col, value in values.items():
            rows.append(ci)
            cols.append(col)
            data.append(value / denom)
    matrix = sparse.csr_matrix((data, (rows, cols)), shape=(len(classes), x.shape[1]), dtype=np.float32)
    return normalize(matrix, norm="l2", axis=1, copy=False)


def rank_rows(scores: np.ndarray, classes: list[str], targets: list[str]):
    idx = {cid: i for i, cid in enumerate(classes)}
    ranks = []
    for ri, target in enumerate(targets):
        ti = idx[target]
        target_score = float(scores[ri, ti])
        rank = 1
        for ci, cid in enumerate(classes):
            value = float(scores[ri, ci])
            if value > target_score or (value == target_score and cid < target):
                rank += 1
        ranks.append(rank)
    return ranks


def summarize(ranks):
    return {
        "cases": len(ranks),
        "top1_count": int(sum(r == 1 for r in ranks)),
        "top1_rate": round(sum(r == 1 for r in ranks) / len(ranks), 6),
        "hit_at_5_count": int(sum(r <= 5 for r in ranks)),
        "hit_at_5_rate": round(sum(r <= 5 for r in ranks) / len(ranks), 6),
        "mrr": round(sum(1.0 / r for r in ranks) / len(ranks), 6),
        "median_rank": float(statistics.median(ranks)),
    }


def fit_space(train_texts, train_labels, classes):
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
    x = vectorizer.fit_transform(train_texts)
    centroids = class_centroids(x, train_labels, classes)
    svd = TruncatedSVD(n_components=DIM, algorithm="randomized", n_iter=7, random_state=0)
    latent_centroids = normalize(svd.fit_transform(centroids), norm="l2", axis=1)
    return vectorizer, centroids, svd, latent_centroids.astype(np.float32)


def quantize_rows(matrix: np.ndarray):
    scales = np.max(np.abs(matrix), axis=1).astype(np.float32) / 127.0
    scales[scales == 0] = 1.0
    q = np.clip(np.rint(matrix / scales[:, None]), -127, 127).astype(np.int8)
    return q, scales


def quantized_projection(svd: TruncatedSVD, x_query):
    components = np.asarray(svd.components_, dtype=np.float32)
    q_components, component_scales = quantize_rows(components)
    dequant_components = q_components.astype(np.float32) * component_scales[:, None]
    projected = np.asarray(x_query.dot(dequant_components.T), dtype=np.float32)
    return normalize(projected, norm="l2", axis=1), q_components, component_scales


def quantized_class_vectors(latent_centroids: np.ndarray):
    q_classes, class_scales = quantize_rows(latent_centroids)
    dequant = q_classes.astype(np.float32) * class_scales[:, None]
    dequant = normalize(dequant, norm="l2", axis=1)
    return dequant.astype(np.float32), q_classes, class_scales


def compact_estimate(vectorizer, q_components, component_scales, q_classes, class_scales):
    features = [None] * len(vectorizer.vocabulary_)
    for token, index in vectorizer.vocabulary_.items():
        features[index] = token
    vocab_blob = ("\0".join(features) + "\0").encode("utf-8")
    idf = np.asarray(vectorizer.idf_, dtype=np.float32).tobytes()
    payload = bytearray(vocab_blob)
    payload.extend(idf)
    payload.extend(q_components.tobytes())
    payload.extend(np.asarray(component_scales, dtype=np.float32).tobytes())
    payload.extend(q_classes.tobytes())
    payload.extend(np.asarray(class_scales, dtype=np.float32).tobytes())
    return {
        "feature_count": len(features),
        "latent_dim": DIM,
        "projection_int8_values": int(q_components.size),
        "class_int8_values": int(q_classes.size),
        "raw_bytes": len(payload),
        "gzip9_bytes": len(gzip.compress(bytes(payload), compresslevel=9)),
        "layout": "NUL UTF-8 feature dictionary + float32 IDF + int8 64xF projection + 64 float32 component scales + int8 593x64 class vectors + 593 float32 class scales",
    }


def load_confusion_cases(path: Path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    pairs = [row for row in rows if (row.get("contrast") or {}).get("distinguishable") is True]
    if len(pairs) != 11:
        raise RuntimeError(f"confusion pair drift: {len(pairs)}")
    cohort, cases = [], []
    for pair_index, row in enumerate(pairs):
        a = str(row["a_concept_id"])
        b = str(row["b_concept_id"])
        cohort.extend([a, b])
        for side, cid, mate in (("a", a, b), ("b", b, a)):
            descs = (row["contrast"] or {}).get(f"{side}_descriptions") or []
            if len(descs) != 3:
                raise RuntimeError("confusion description drift")
            for di, query in enumerate(descs):
                cases.append({
                    "pair_index": pair_index,
                    "side": side,
                    "concept_id": cid,
                    "mate_id": mate,
                    "description_index": di,
                    "query": str(query),
                })
    cohort = sorted(set(cohort))
    if len(cohort) != 22 or len(cases) != 66:
        raise RuntimeError("hard-confusion cohort drift")
    return cohort, cases


def hard_confusion_metrics(scores, classes, cases, cohort):
    class_idx = {cid: i for i, cid in enumerate(classes)}
    cohort_idx = [class_idx[cid] for cid in cohort]
    cohort_pos = {cid: i for i, cid in enumerate(cohort)}
    cohort_scores = scores[:, cohort_idx]
    ranks = rank_rows(cohort_scores, cohort, [case["concept_id"] for case in cases])
    pair_correct = pair_tie = 0
    rows = []
    for ri, (case, rank) in enumerate(zip(cases, ranks, strict=True)):
        target_score = float(cohort_scores[ri, cohort_pos[case["concept_id"]]])
        mate_score = float(cohort_scores[ri, cohort_pos[case["mate_id"]]])
        pair_correct += int(target_score > mate_score)
        pair_tie += int(target_score == mate_score)
        rows.append({**case, "rank": rank, "target_score": round(target_score, 9), "mate_score": round(mate_score, 9)})
    result = summarize(ranks)
    result.update({
        "pairwise_correct_count": pair_correct,
        "pairwise_correct_rate": round(pair_correct / len(cases), 6),
        "pairwise_tie_count": pair_tie,
    })
    return result, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--contrasts", default="research/training/v31/a593-gemma4-sniper-contrasts-v0.jsonl")
    ap.add_argument("--abc", default="research/evaluation/v31/compile-time-semantic-a593-hard-confusion-breadth-abc.json")
    ap.add_argument("--output", default="artifacts/a593-lowrank-breadth.json")
    args = ap.parse_args()

    classes, phrases = load_teacher(Path(args.teacher))

    # Construction holdout: fixed slots 0-6 train, slot 7 test.
    train_texts, train_labels = [], []
    for cid in classes:
        for slot in range(7):
            train_texts.append(phrases[cid][slot])
            train_labels.append(cid)
    test_texts = [phrases[cid][7] for cid in classes]
    vectorizer, full_centroids, svd, latent_centroids = fit_space(train_texts, train_labels, classes)
    x_test = vectorizer.transform(test_texts)
    full_scores = np.asarray(x_test.dot(full_centroids.T).toarray(), dtype=np.float32)
    full_ranks = rank_rows(full_scores, classes, classes)
    latent_query = normalize(svd.transform(x_test), norm="l2", axis=1)
    latent_scores = np.asarray(latent_query.dot(latent_centroids.T), dtype=np.float32)
    latent_ranks = rank_rows(latent_scores, classes, classes)
    q_query, q_components, component_scales = quantized_projection(svd, x_test)
    q_classes, q_class_values, class_scales = quantized_class_vectors(latent_centroids)
    q_scores = np.asarray(q_query.dot(q_classes.T), dtype=np.float32)
    q_ranks = rank_rows(q_scores, classes, classes)
    construction_size = compact_estimate(vectorizer, q_components, component_scales, q_class_values, class_scales)

    # Hard-confusion transfer: fit on all 8 old teacher phrases, test only frozen contrast descriptions.
    all_texts, all_labels = [], []
    for cid in classes:
        for phrase in phrases[cid]:
            all_texts.append(phrase)
            all_labels.append(cid)
    hv, _, hsvd, hcentroids = fit_space(all_texts, all_labels, classes)
    cohort, cases = load_confusion_cases(Path(args.contrasts))
    hq = hv.transform([case["query"] for case in cases])
    hq_lat = normalize(hsvd.transform(hq), norm="l2", axis=1)
    hscore = np.asarray(hq_lat.dot(hcentroids.T), dtype=np.float32)
    hard_float, hard_rows = hard_confusion_metrics(hscore, classes, cases, cohort)
    hq_quant, hcomp, hcomp_scales = quantized_projection(hsvd, hq)
    hclass_quant, hclass_values, hclass_scales = quantized_class_vectors(hcentroids)
    hq_score = np.asarray(hq_quant.dot(hclass_quant.T), dtype=np.float32)
    hard_quant, hard_quant_rows = hard_confusion_metrics(hq_score, classes, cases, cohort)
    hard_size = compact_estimate(hv, hcomp, hcomp_scales, hclass_values, hclass_scales)

    abc = json.loads(Path(args.abc).read_text(encoding="utf-8"))
    a_hard = abc["entrants"]["A_expanded_sparse_bm25"]

    result = {
        "id": "YV-A593-lowrank-E-v0",
        "evidence_class": "final simple single-stage architecture breadth falsifier; no opened 17/88",
        "architecture": {
            "features": "char_wb 3-5 TF-IDF, min_df=2, max_features=30000",
            "class_representation": "mean labeled teacher phrase TF-IDF centroid",
            "projection": "fixed rank-64 TruncatedSVD over class centroids",
            "runtime": "sparse TF-IDF query -> 64-d linear projection -> cosine against 593 64-d concept vectors",
            "sweep": False,
            "opened_17_88_loaded": False,
        },
        "construction_slot7": {
            "same_feature_full_centroid_control": summarize(full_ranks),
            "lowrank64_float": summarize(latent_ranks),
            "lowrank64_int8_projection_and_classes": summarize(q_ranks),
            "compiled_artifact_estimate": construction_size,
        },
        "hard_confusion_66": {
            "A_expanded_sparse_reference": a_hard,
            "lowrank64_float": hard_float,
            "lowrank64_int8_projection_and_classes": hard_quant,
            "compiled_artifact_estimate": hard_size,
            "rows_float": hard_rows,
            "rows_quantized": hard_quant_rows,
        },
        "guard": "DIM/features/objective were fixed before this run. Do not rescue a miss with a sweep; if it fails, breadth round ends with A as the surviving simple family.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "construction": result["construction_slot7"],
        "hard_confusion": {k: v for k, v in result["hard_confusion_66"].items() if not k.startswith("rows_")},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
