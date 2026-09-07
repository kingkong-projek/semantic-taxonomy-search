#!/usr/bin/env python3
"""D0 reference challenger: proper Model2Vec static distillation of pinned E5.

Opened architecture diagnostic only. Vocabulary is compiled from source/evidence text,
never from evaluation queries. The large E5 transformer is used only at build time.
Runtime uses the distilled static word embeddings and cosine similarity.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import tarfile
from pathlib import Path
from typing import Any

import numpy as np
import zstandard as zstd
from model2vec.distill import distill_from_model
from transformers import AutoModel, AutoTokenizer

from evaluate_compile_time_tournament_round0 import (
    MODEL_NAME,
    MODEL_REVISION,
    VOCAB_LIMIT,
    build_vocab,
    kv_cases_and_targets,
    source_metrics,
    strict_yv_cases,
    teacher_map,
)
from evaluate_dense_semantic_candidate_lane import concept_text, summarize_opened_cases
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm

PCA_DIMS = 64
OCC_INFO_URL = "https://data.arbetsformedlingen.se/yrke/yrkesinformation/yrkesinformation-interimslosning.json"


def norm_rows(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.maximum(n, 1e-9)


def model2vec_scores(model: Any, queries: list[str], docs: list[str]) -> np.ndarray:
    q = norm_rows(np.asarray(model.encode(queries), dtype=np.float32))
    d = norm_rows(np.asarray(model.encode(docs), dtype=np.float32))
    return q @ d.T


def yv_multi_scores(model: Any, queries: list[str], canonical: list[str], relevant: list[str], ad_docs: list[str], ad_concepts: list[int]) -> np.ndarray:
    q = norm_rows(np.asarray(model.encode(queries), dtype=np.float32))
    can = norm_rows(np.asarray(model.encode(canonical), dtype=np.float32))
    rel = norm_rows(np.asarray(model.encode(relevant), dtype=np.float32))
    scores = np.maximum(q @ can.T, q @ rel.T)
    if ad_docs:
        ad = norm_rows(np.asarray(model.encode(ad_docs), dtype=np.float32))
        ad_scores = q @ ad.T
        for j, ci in enumerate(ad_concepts):
            scores[:, ci] = np.maximum(scores[:, ci], ad_scores[:, j])
    return scores


def compressed_model_size(model_dir: Path, temp_tar: Path) -> dict[str, int]:
    raw = sum(p.stat().st_size for p in model_dir.rglob("*") if p.is_file())
    with tarfile.open(temp_tar, "w") as tf:
        for p in sorted(model_dir.rglob("*")):
            if p.is_file():
                tf.add(p, arcname=p.relative_to(model_dir))
    data = temp_tar.read_bytes()
    gz = gzip.compress(data, compresslevel=9)
    temp_tar.with_suffix(".tar.gz").write_bytes(gz)
    return {"saved_model_raw_bytes": raw, "tar_gzip_bytes": len(gz)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--output", default="artifacts/model2vec-tournament-d0-v31.json")
    ap.add_argument("--model-dir", default="artifacts/model2vec-tournament-d0-model")
    args = ap.parse_args()

    stress = json.loads(Path(args.stress).read_text(encoding="utf-8"))
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

    yv_ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(yv_ids) != 2105:
        raise RuntimeError("YV universe drift")
    yv_pos = {cid: i for i, cid in enumerate(yv_ids)}
    yv_labels = [str(by_id[cid].get("preferred_label") or cid) for cid in yv_ids]
    canonical_docs = [concept_text(by_id[cid]) for cid in yv_ids]

    ad_data = ad_doc.get("data", {}).get("occupation_name")
    relevant_data = relevant_doc.get("data")
    if not isinstance(ad_data, dict) or not isinstance(relevant_data, dict):
        raise RuntimeError("YV evidence shape drift")
    ad_ids = sorted(cid for cid in ad_data if cid in yv_pos)
    ad_docs: list[str] = []
    ad_concepts: list[int] = []
    for cid in ad_ids:
        keywords = ad_data[cid].get("keywords") if isinstance(ad_data[cid], dict) else None
        if not isinstance(keywords, dict):
            raise RuntimeError(f"ad row drift: {cid}")
        ad_docs.append(" | ".join(sorted((str(x) for x in keywords), key=norm)))
        ad_concepts.append(yv_pos[cid])

    skill_ids = {cid for cid, c in by_id.items() if c.get("type") == "skill"}
    relevant_docs: list[str] = []
    for cid in yv_ids:
        row = relevant_data.get(cid)
        items = row.get("relevant_skills") if isinstance(row, dict) else None
        if not isinstance(items, list):
            raise RuntimeError(f"relevant row drift: {cid}")
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

    kv_cases, kv_targets, kv_ids = kv_cases_and_targets(pareto)
    kv_labels = [str(by_id[cid].get("preferred_label") or cid) for cid in kv_ids]
    teacher = teacher_map()
    kv_docs = [concept_text(by_id[cid], extra=teacher[cid]) for cid in kv_ids]

    vocab_source_docs = [*canonical_docs, *ad_docs, *relevant_docs, *kv_docs]
    vocab, _idf, _df = build_vocab(vocab_source_docs)
    if len(vocab) != VOCAB_LIMIT:
        raise RuntimeError(f"vocabulary drift: {len(vocab)}")

    transformer = AutoModel.from_pretrained(MODEL_NAME, revision=MODEL_REVISION, trust_remote_code=False)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, revision=MODEL_REVISION, trust_remote_code=False, use_fast=True)
    static = distill_from_model(
        model=transformer,
        tokenizer=tokenizer,
        vocabulary=vocab,
        device="cpu",
        pca_dims=PCA_DIMS,
        sif_coefficient=1e-4,
        quantize_to="int8",
        pooling="mean",
    )

    model_dir = Path(args.model_dir)
    if model_dir.exists():
        shutil.rmtree(model_dir)
    static.save_pretrained(model_dir)
    size = compressed_model_size(model_dir, Path("artifacts/model2vec-tournament-d0-model.tar"))

    yv_stress_q = [str(x["query"]) for x in stress["yv"]]
    kv_stress_q = [str(x["query"]) for x in stress["kv"]]
    yv_stress_scores = yv_multi_scores(static, yv_stress_q, canonical_docs, relevant_docs, ad_docs, ad_concepts)
    kv_stress_scores = model2vec_scores(static, kv_stress_q, kv_docs)

    yv_source = strict_yv_cases(occ_info, by_id, yv_ids)
    yv_source_q = [x["query"] for x in yv_source]
    yv_source_targets = [x["target_id"] for x in yv_source]
    yv_source_scores = yv_multi_scores(static, yv_source_q, canonical_docs, relevant_docs, ad_docs, ad_concepts)
    kv_source_scores = model2vec_scores(static, [str(x["query"]) for x in kv_cases], kv_docs)

    yv_stress = summarize_opened_cases(stress["yv"], yv_stress_scores, yv_labels)
    kv_stress = summarize_opened_cases(stress["kv"], kv_stress_scores, kv_labels)

    result = {
        "schema_version": 1,
        "status": "opened architecture diagnostic only; no runtime promotion",
        "entrant": "D0_Model2Vec_static_E5",
        "teacher": {"name": MODEL_NAME, "revision": MODEL_REVISION},
        "distillation": {
            "vocabulary_source": "taxonomy + AF ad language + AF relevant-skill labels + prefrozen KV teacher phrases; evaluation queries excluded",
            "vocabulary_size": len(vocab),
            "pca_dims": PCA_DIMS,
            "sif_coefficient": 1e-4,
            "quantize_to": "int8",
            "pooling": "mean",
        },
        "artifact_size": size,
        "opened_stress": {"yv": yv_stress["categories"], "kv": kv_stress["categories"]},
        "opened_source_attested": {
            "yv17": source_metrics(yv_source_scores, yv_source_targets, yv_ids),
            "kv81": source_metrics(kv_source_scores, kv_targets, kv_ids),
        },
        "source_sha256": source_sha,
        "decision_contract": (
            "D0 is a reference challenger under the compile-time tournament. Opened stress/source-attested data may diagnose "
            "architecture but may not tune/promote this configuration."
        ),
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "entrant": result["entrant"],
        "distillation": result["distillation"],
        "artifact_size": size,
        "opened_stress": result["opened_stress"],
        "opened_source_attested": {
            k: {x: v for x, v in m.items() if x != "ranks"}
            for k, m in result["opened_source_attested"].items()
        },
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
