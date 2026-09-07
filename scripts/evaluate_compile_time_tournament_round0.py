#!/usr/bin/env python3
"""Round 0 of the compile-time semantic tournament.

Opened architecture diagnostic only. No opened query text enters training/vocabulary.
A pinned multilingual E5 teacher is used only at build time to compile two tiny runtime
students:

B0: sparse token -> top-k concept weights.
C0: 32d int8 static token embeddings + int8 concept prototypes.

Both runtime artifacts require only the repository's simple tokenizer, table lookup and
score accumulation/vector dot products. No transformer or ML runtime ships to browser.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import zstandard as zstd
from sentence_transformers import SentenceTransformer
from sklearn.decomposition import PCA

from build_kv_demo_asset import TEACHER_PATHS
from evaluate_c2_job_title_router import relation_parent_ids
from evaluate_dense_semantic_candidate_lane import concept_text, summarize_opened_cases
from evaluate_p80_lexical_ablation import as_list, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from occupational_information_coverage import find_explicit_taxonomy_ids, record_map

MODEL_NAME = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
VOCAB_LIMIT = 16_384
LOW_RANK_DIMS = 32
SPARSE_TOPK = 4
OCC_INFO_URL = "https://data.arbetsformedlingen.se/yrke/yrkesinformation/yrkesinformation-interimslosning.json"
KV_PATHS = (
    "research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl",
    "research/benchmark/v31/training-skill-second-holdout/cases.jsonl",
    "research/benchmark/v31/training-skill-third-holdout/cases.jsonl",
)


def teacher_map() -> dict[str, list[str]]:
    rows: list[dict[str, Any]] = []
    for path in TEACHER_PATHS:
        rows.extend(load_jsonl(Path(path)))
    out: dict[str, list[str]] = {}
    for row in rows:
        cid = str(row["concept_id"])
        phrases = [str(x).strip() for x in row.get("phrases") or [] if str(x).strip()]
        if cid in out or len(phrases) != 3:
            raise RuntimeError(f"teacher drift: {cid}")
        out[cid] = phrases
    if len(out) != 316:
        raise RuntimeError(f"teacher count drift: {len(out)}")
    return out


def phrase_present(text: str, surface: str) -> bool:
    haystack = tokens(text)
    needle = tokens(surface)
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(haystack[i : i + width] == needle for i in range(len(haystack) - width + 1))


def strict_yv_cases(occ_info: dict[str, Any], by_id: dict[str, dict[str, Any]], occupation_ids: list[str]) -> list[dict[str, str]]:
    active_occ = set(occupation_ids)
    all_ids = set(by_id)
    records = record_map(occ_info.get("data"))
    metadata = occ_info.get("metadata")
    occupations_meta = metadata.get("occupations") if isinstance(metadata, dict) else None
    if not isinstance(occupations_meta, list):
        raise RuntimeError("Yrkesinformation metadata drift")
    job_title_surfaces_by_parent: dict[str, set[str]] = defaultdict(set)
    for concept in by_id.values():
        if concept.get("type") != "job-title":
            continue
        label = str(concept.get("preferred_label") or "").strip()
        if not label:
            continue
        for parent in relation_parent_ids(concept, by_id):
            job_title_surfaces_by_parent[parent].add(label)
    cases: list[dict[str, str]] = []
    for meta in occupations_meta:
        if not isinstance(meta, dict):
            continue
        slug = str(meta.get("slug") or "")
        record = records.get(slug)
        if not isinstance(record, dict):
            continue
        explicit = find_explicit_taxonomy_ids(record, all_ids) & active_occ
        if len(explicit) != 1:
            continue
        target = next(iter(explicit))
        query = str(record.get("work_task") or "").strip()
        if len(query) < 40:
            continue
        concept = by_id[target]
        surfaces = {
            str(concept.get("preferred_label") or ""),
            *as_list(concept.get("alternative_labels")),
            *job_title_surfaces_by_parent.get(target, set()),
        }
        if any(surface and phrase_present(query, surface) for surface in surfaces):
            continue
        cases.append({"id": slug, "query": query, "target_id": target})
    if len(cases) != 17:
        raise RuntimeError(f"strict YV case drift: {len(cases)} != 17")
    return cases


def kv_cases_and_targets(pareto: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    cases: list[dict[str, Any]] = []
    for path in KV_PATHS:
        cases.extend(load_jsonl(Path(path)))
    if len(cases) != 81:
        raise RuntimeError(f"KV case drift: {len(cases)}")
    kv_ids = sorted(p80_skill_ids(pareto))
    targets: list[str] = []
    for row in cases:
        target = row.get("target")
        cid = str(target.get("concept_id")) if isinstance(target, dict) and target.get("concept_id") else ""
        if not cid or cid not in kv_ids:
            raise RuntimeError(f"KV target drift: {row.get('id')}")
        targets.append(cid)
    return cases, targets, kv_ids


def build_vocab(source_docs: list[str]) -> tuple[list[str], dict[str, float], dict[str, int]]:
    frequency: Counter[str] = Counter()
    document_frequency: Counter[str] = Counter()
    for text in source_docs:
        row = tokens(text)
        frequency.update(row)
        document_frequency.update(set(row))
    # Deterministic frequency-ranked domain vocabulary. No benchmark/stress query text.
    vocab = [term for term, _ in sorted(frequency.items(), key=lambda x: (-x[1], x[0]))[:VOCAB_LIMIT]]
    n_docs = max(len(source_docs), 1)
    idf = {term: math.log((n_docs + 1.0) / (document_frequency[term] + 1.0)) + 1.0 for term in vocab}
    return vocab, idf, dict(document_frequency)


def normalize_rows(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.maximum(norms, 1e-9)


def target_rank(scores: np.ndarray, target_index: int) -> int:
    order = np.argsort(-scores, kind="stable")
    return int(np.flatnonzero(order == target_index)[0]) + 1


def source_metrics(score_rows: np.ndarray, targets: list[str], ids: list[str]) -> dict[str, Any]:
    pos = {cid: i for i, cid in enumerate(ids)}
    top1 = hit5 = 0
    rr = 0.0
    ranks: list[int | None] = []
    for i, cid in enumerate(targets):
        if cid not in pos:
            ranks.append(None)
            continue
        rank = target_rank(score_rows[i], pos[cid])
        ranks.append(rank)
        top1 += rank == 1
        hit5 += rank <= 5
        rr += 1.0 / rank
    return {
        "cases": len(targets),
        "top1": top1,
        "hit_at_5": hit5,
        "mrr": round(rr / len(targets), 6) if targets else 0.0,
        "ranks": ranks,
    }


def family_stress_summary(cases: list[dict[str, Any]], scores: np.ndarray, labels: list[str]) -> dict[str, Any]:
    return summarize_opened_cases(cases, scores, labels)


def quantize_unit_rows(x: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(normalize_rows(x) * 127.0), -127, 127).astype(np.int8)


def dequantize_unit_rows(q: np.ndarray) -> np.ndarray:
    return normalize_rows(q.astype(np.float32) / 127.0)


def runtime_c_scores(
    queries: list[str],
    vocab_pos: dict[str, int],
    token_vectors: np.ndarray,
    proto_vectors: np.ndarray,
    proto_concepts: np.ndarray,
    concept_count: int,
) -> np.ndarray:
    out = np.full((len(queries), concept_count), -1.0, dtype=np.float32)
    for qi, query in enumerate(queries):
        indices = [vocab_pos[t] for t in tokens(query) if t in vocab_pos]
        if not indices:
            out[qi, :] = 0.0
            continue
        q = token_vectors[indices].mean(axis=0, dtype=np.float32)
        n = float(np.linalg.norm(q))
        if n <= 1e-9:
            out[qi, :] = 0.0
            continue
        q /= n
        sims = proto_vectors @ q
        # Multiple provenance-separated prototypes may map to one YV concept.
        out[qi, :] = -1.0
        np.maximum.at(out[qi], proto_concepts, sims)
    return out


def runtime_b_scores(
    queries: list[str],
    vocab_pos: dict[str, int],
    idf_values: np.ndarray,
    top_indices: np.ndarray,
    top_weights_q: np.ndarray,
    concept_count: int,
) -> np.ndarray:
    out = np.zeros((len(queries), concept_count), dtype=np.float32)
    weights = top_weights_q.astype(np.float32) / 32767.0
    for qi, query in enumerate(queries):
        seen = {vocab_pos[t] for t in tokens(query) if t in vocab_pos}
        for fi in seen:
            scale = float(idf_values[fi])
            for slot in range(top_indices.shape[1]):
                ci = int(top_indices[fi, slot])
                out[qi, ci] += scale * float(weights[fi, slot])
    return out


def sparse_topk(feature_emb: np.ndarray, prototype_emb: np.ndarray, proto_concepts: np.ndarray, concept_count: int, batch: int = 256) -> tuple[np.ndarray, np.ndarray]:
    all_idx = np.empty((feature_emb.shape[0], SPARSE_TOPK), dtype=np.uint16)
    all_w = np.empty((feature_emb.shape[0], SPARSE_TOPK), dtype=np.int16)
    for start in range(0, feature_emb.shape[0], batch):
        stop = min(start + batch, feature_emb.shape[0])
        sims = feature_emb[start:stop] @ prototype_emb.T
        concept_scores = np.full((stop - start, concept_count), -1.0, dtype=np.float32)
        for p in range(prototype_emb.shape[0]):
            np.maximum(concept_scores[:, int(proto_concepts[p])], sims[:, p])
        idx = np.argpartition(-concept_scores, SPARSE_TOPK - 1, axis=1)[:, :SPARSE_TOPK]
        row = np.arange(stop - start)[:, None]
        vals = concept_scores[row, idx]
        order = np.argsort(-vals, axis=1, kind="stable")
        idx = idx[row, order]
        vals = vals[row, order]
        all_idx[start:stop] = idx.astype(np.uint16)
        all_w[start:stop] = np.clip(np.rint(vals * 32767.0), -32767, 32767).astype(np.int16)
    return all_idx, all_w


def write_sparse_asset(path: Path, vocab: list[str], idf: dict[str, float], yv_idx: np.ndarray, yv_w: np.ndarray, kv_idx: np.ndarray, kv_w: np.ndarray) -> dict[str, int]:
    buf = bytearray(b"STSB0\x00")
    buf += struct.pack("<IHH", len(vocab), SPARSE_TOPK, 0)
    max_idf = max(idf.values()) if idf else 1.0
    for i, term in enumerate(vocab):
        raw = term.encode("utf-8")
        if len(raw) > 65535:
            raise RuntimeError("unexpected token length")
        buf += struct.pack("<H", len(raw)) + raw
        idf_q = int(round(idf[term] / max_idf * 65535.0))
        buf += struct.pack("<H", max(0, min(65535, idf_q)))
        for idx, weight in zip(yv_idx[i], yv_w[i]):
            buf += struct.pack("<Hh", int(idx), int(weight))
        for idx, weight in zip(kv_idx[i], kv_w[i]):
            buf += struct.pack("<Hh", int(idx), int(weight))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(buf))
    gz = gzip.compress(bytes(buf), compresslevel=9)
    path.with_suffix(path.suffix + ".gz").write_bytes(gz)
    return {"raw_bytes": len(buf), "gzip_bytes": len(gz)}


def write_lowrank_asset(
    path: Path,
    vocab: list[str],
    token_q: np.ndarray,
    yv_proto_q: np.ndarray,
    yv_proto_concepts: np.ndarray,
    kv_proto_q: np.ndarray,
    kv_proto_concepts: np.ndarray,
) -> dict[str, int]:
    buf = bytearray(b"STSC0\x00")
    buf += struct.pack("<IHHII", len(vocab), LOW_RANK_DIMS, 0, len(yv_proto_q), len(kv_proto_q))
    for i, term in enumerate(vocab):
        raw = term.encode("utf-8")
        buf += struct.pack("<H", len(raw)) + raw + token_q[i].tobytes(order="C")
    for q, ci in zip(yv_proto_q, yv_proto_concepts):
        buf += struct.pack("<H", int(ci)) + q.tobytes(order="C")
    for q, ci in zip(kv_proto_q, kv_proto_concepts):
        buf += struct.pack("<H", int(ci)) + q.tobytes(order="C")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(buf))
    gz = gzip.compress(bytes(buf), compresslevel=9)
    path.with_suffix(path.suffix + ".gz").write_bytes(gz)
    return {"raw_bytes": len(buf), "gzip_bytes": len(gz)}


def compact_categories(summary: dict[str, Any]) -> dict[str, Any]:
    return summary["categories"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--output", default="artifacts/compile-time-tournament-round0-v31.json")
    ap.add_argument("--asset-dir", default="artifacts/compile-time-tournament-round0-assets")
    ap.add_argument("--batch-size", type=int, default=64)
    args = ap.parse_args()

    stress = json.loads(Path(args.stress).read_text(encoding="utf-8"))
    if len(stress.get("yv") or []) != 54 or len(stress.get("kv") or []) != 34:
        raise RuntimeError("opened stress suite drift")
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))

    urls = {
        "taxonomy": "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json",
        "ad_language": "https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t31/relevans-nyckelord.json.zst",
        "relevant_skills": "https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/v1/relevanta-kompetenser-t31.json.zst",
        "occupational_information": OCC_INFO_URL,
    }
    adapters = {
        "taxonomy": "taxonomy-common-relations",
        "ad_language": "ad-keyword-corpus",
        "relevant_skills": "relevant-skills",
        "occupational_information": "occupational-information",
    }
    wires = {name: fetch(url) for name, url in urls.items()}
    source_sha = {name: hashlib.sha256(body).hexdigest() for name, body in wires.items()}
    for name, adapter in adapters.items():
        if source_sha[name] != expected_hash(registry, adapter):
            raise RuntimeError(f"source drift: {name}")

    taxonomy = json.loads(wires["taxonomy"])
    ad_doc = json.loads(zstd.ZstdDecompressor().decompress(wires["ad_language"]))
    relevant_doc = json.loads(zstd.ZstdDecompressor().decompress(wires["relevant_skills"]))
    occ_info = json.loads(wires["occupational_information"])
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    occupation_ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(occupation_ids) != 2105:
        raise RuntimeError("occupation universe drift")
    yv_pos = {cid: i for i, cid in enumerate(occupation_ids)}
    yv_labels = [str(by_id[cid].get("preferred_label") or cid) for cid in occupation_ids]

    kv_cases, kv_targets, kv_ids = kv_cases_and_targets(pareto)
    kv_labels = [str(by_id[cid].get("preferred_label") or cid) for cid in kv_ids]
    teacher = teacher_map()

    canonical_docs = [concept_text(by_id[cid]) for cid in occupation_ids]
    ad_data = ad_doc.get("data", {}).get("occupation_name")
    relevant_data = relevant_doc.get("data")
    if not isinstance(ad_data, dict) or not isinstance(relevant_data, dict):
        raise RuntimeError("YV evidence shape drift")
    ad_ids = sorted(cid for cid in ad_data if cid in yv_pos)
    if len(ad_ids) != 1051:
        raise RuntimeError("ad coverage drift")
    ad_docs: list[str] = []
    for cid in ad_ids:
        keywords = ad_data[cid].get("keywords") if isinstance(ad_data[cid], dict) else None
        if not isinstance(keywords, dict):
            raise RuntimeError(f"ad row drift {cid}")
        ad_docs.append(" | ".join(sorted((str(x) for x in keywords), key=norm)))

    skill_ids = {cid for cid, c in by_id.items() if c.get("type") == "skill"}
    relevant_docs: list[str] = []
    for cid in occupation_ids:
        row = relevant_data.get(cid)
        items = row.get("relevant_skills") if isinstance(row, dict) else None
        if not isinstance(items, list):
            raise RuntimeError(f"relevant row drift {cid}")
        labels: list[str] = []
        seen: set[str] = set()
        for item in items:
            sid = str(item.get("id")) if isinstance(item, dict) and item.get("id") else ""
            if not sid or sid not in skill_ids or sid in seen:
                continue
            seen.add(sid)
            label = str(by_id[sid].get("preferred_label") or "").strip()
            if label:
                labels.append(label)
        relevant_docs.append(" | ".join(labels))

    kv_docs = [concept_text(by_id[cid], extra=teacher[cid]) for cid in kv_ids]

    # Domain vocabulary is compiled strictly from source/evidence documents, never from
    # opened stress/source-attested query text.
    vocab_source_docs = [*canonical_docs, *ad_docs, *relevant_docs, *kv_docs]
    vocab, idf, document_frequency = build_vocab(vocab_source_docs)
    vocab_pos = {term: i for i, term in enumerate(vocab)}
    idf_values = np.asarray([idf[t] for t in vocab], dtype=np.float32)

    model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION, trust_remote_code=False)

    def encode(texts: list[str], prefix: str) -> np.ndarray:
        return np.asarray(
            model.encode(
                [prefix + x for x in texts],
                batch_size=args.batch_size,
                normalize_embeddings=True,
                show_progress_bar=True,
            ),
            dtype=np.float32,
        )

    feature_emb = encode(vocab, "query: ")
    yv_canonical_emb = encode(canonical_docs, "passage: ")
    yv_relevant_emb = encode(relevant_docs, "passage: ")
    yv_ad_emb = encode(ad_docs, "passage: ")
    kv_proto_emb = encode(kv_docs, "passage: ")

    # Preserve provenance-separated YV representations as separate prototypes; scoring
    # takes max per canonical concept rather than concatenating evidence.
    yv_proto_emb = np.concatenate([yv_canonical_emb, yv_relevant_emb, yv_ad_emb], axis=0)
    yv_proto_concepts = np.asarray(
        [*range(len(occupation_ids)), *range(len(occupation_ids)), *[yv_pos[cid] for cid in ad_ids]],
        dtype=np.uint16,
    )
    kv_proto_concepts = np.arange(len(kv_ids), dtype=np.uint16)

    # B0: compile teacher similarity into sparse lookup weights.
    yv_b_idx, yv_b_w = sparse_topk(feature_emb, yv_proto_emb, yv_proto_concepts, len(occupation_ids))
    kv_b_idx, kv_b_w = sparse_topk(feature_emb, kv_proto_emb, kv_proto_concepts, len(kv_ids))

    # C0: a single PCA is fitted only on teacher-produced source feature/prototype
    # embeddings, then all vectors are normalized and int8 quantized.
    pca_training = np.concatenate([feature_emb, yv_proto_emb, kv_proto_emb], axis=0)
    pca = PCA(n_components=LOW_RANK_DIMS, svd_solver="randomized", random_state=0)
    pca.fit(pca_training)
    feature_low = normalize_rows(pca.transform(feature_emb).astype(np.float32))
    yv_proto_low = normalize_rows(pca.transform(yv_proto_emb).astype(np.float32))
    kv_proto_low = normalize_rows(pca.transform(kv_proto_emb).astype(np.float32))
    feature_q = quantize_unit_rows(feature_low)
    yv_proto_q = quantize_unit_rows(yv_proto_low)
    kv_proto_q = quantize_unit_rows(kv_proto_low)
    feature_runtime = dequantize_unit_rows(feature_q)
    yv_proto_runtime = dequantize_unit_rows(yv_proto_q)
    kv_proto_runtime = dequantize_unit_rows(kv_proto_q)

    asset_dir = Path(args.asset_dir)
    b_size = write_sparse_asset(asset_dir / "b0-sparse.bin", vocab, idf, yv_b_idx, yv_b_w, kv_b_idx, kv_b_w)
    c_size = write_lowrank_asset(
        asset_dir / "c0-lowrank.bin",
        vocab,
        feature_q,
        yv_proto_q,
        yv_proto_concepts,
        kv_proto_q,
        kv_proto_concepts,
    )

    yv_stress_queries = [str(x["query"]) for x in stress["yv"]]
    kv_stress_queries = [str(x["query"]) for x in stress["kv"]]
    yv_b_stress = runtime_b_scores(yv_stress_queries, vocab_pos, idf_values, yv_b_idx, yv_b_w, len(occupation_ids))
    kv_b_stress = runtime_b_scores(kv_stress_queries, vocab_pos, idf_values, kv_b_idx, kv_b_w, len(kv_ids))
    yv_c_stress = runtime_c_scores(yv_stress_queries, vocab_pos, feature_runtime, yv_proto_runtime, yv_proto_concepts, len(occupation_ids))
    kv_c_stress = runtime_c_scores(kv_stress_queries, vocab_pos, feature_runtime, kv_proto_runtime, kv_proto_concepts, len(kv_ids))

    yv_source = strict_yv_cases(occ_info, by_id, occupation_ids)
    yv_source_queries = [x["query"] for x in yv_source]
    yv_source_targets = [x["target_id"] for x in yv_source]
    kv_source_queries = [str(x["query"]) for x in kv_cases]

    yv_b_source = runtime_b_scores(yv_source_queries, vocab_pos, idf_values, yv_b_idx, yv_b_w, len(occupation_ids))
    kv_b_source = runtime_b_scores(kv_source_queries, vocab_pos, idf_values, kv_b_idx, kv_b_w, len(kv_ids))
    yv_c_source = runtime_c_scores(yv_source_queries, vocab_pos, feature_runtime, yv_proto_runtime, yv_proto_concepts, len(occupation_ids))
    kv_c_source = runtime_c_scores(kv_source_queries, vocab_pos, feature_runtime, kv_proto_runtime, kv_proto_concepts, len(kv_ids))

    b_yv_stress = family_stress_summary(stress["yv"], yv_b_stress, yv_labels)
    b_kv_stress = family_stress_summary(stress["kv"], kv_b_stress, kv_labels)
    c_yv_stress = family_stress_summary(stress["yv"], yv_c_stress, yv_labels)
    c_kv_stress = family_stress_summary(stress["kv"], kv_c_stress, kv_labels)

    result = {
        "schema_version": 1,
        "status": "opened architecture diagnostic only; no runtime promotion",
        "teacher": {"name": MODEL_NAME, "revision": MODEL_REVISION},
        "anti_leakage": (
            "vocabulary, PCA and sparse weights use only taxonomy/AF evidence and prefrozen KV teacher phrases; "
            "opened stress and source-attested query text are evaluation-only"
        ),
        "frozen_round0": {
            "vocab_limit": VOCAB_LIMIT,
            "actual_vocab_size": len(vocab),
            "low_rank_dims": LOW_RANK_DIMS,
            "sparse_topk": SPARSE_TOPK,
            "pca_explained_variance_ratio_sum": round(float(pca.explained_variance_ratio_.sum()), 6),
            "source_document_count": len(vocab_source_docs),
            "source_sha256": source_sha,
        },
        "entrants": {
            "B0_sparse_feature_to_concept": {
                "runtime": "token lookup + IDF-weighted deterministic accumulation; no ML dependency",
                "artifact_size": b_size,
                "opened_stress": {
                    "yv": compact_categories(b_yv_stress),
                    "kv": compact_categories(b_kv_stress),
                },
                "opened_source_attested": {
                    "yv17": source_metrics(yv_b_source, yv_source_targets, occupation_ids),
                    "kv81": source_metrics(kv_b_source, kv_targets, kv_ids),
                },
            },
            "C0_int8_lowrank_static": {
                "runtime": "token lookup + mean 32d int8 vectors + dot products; no ML dependency",
                "artifact_size": c_size,
                "opened_stress": {
                    "yv": compact_categories(c_yv_stress),
                    "kv": compact_categories(c_kv_stress),
                },
                "opened_source_attested": {
                    "yv17": source_metrics(yv_c_source, yv_source_targets, occupation_ids),
                    "kv81": source_metrics(kv_c_source, kv_targets, kv_ids),
                },
            },
        },
        "non_claims": [
            "B0 or C0 is ready for runtime promotion",
            "opened stress/source-attested metrics estimate user accuracy",
            "a confidence/abstention threshold has been selected",
            "the tournament is complete; A/doc2query and static Model2Vec remain separate entrants",
        ],
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "teacher": result["teacher"],
        "frozen_round0": result["frozen_round0"],
        "entrants": {
            name: {
                "artifact_size": data["artifact_size"],
                "opened_stress": data["opened_stress"],
                "opened_source_attested": {
                    k: {x: v for x, v in metrics.items() if x != "ranks"}
                    for k, metrics in data["opened_source_attested"].items()
                },
            }
            for name, data in result["entrants"].items()
        },
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
