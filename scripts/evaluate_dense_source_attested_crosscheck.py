#!/usr/bin/env python3
"""Cross-check frozen dense challenger lanes on already-opened source-attested AF text.

This is a zero-tuning architecture cross-check, not blind validation. The model revision
and representations were fixed before this run. YV reuses the same strict leak-free
Yrkesinformation work_task selection as earlier diagnostics; KV uses the three existing
source-attested AF description sets totaling 81 cases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import zstandard as zstd
from sentence_transformers import SentenceTransformer

from build_kv_demo_asset import TEACHER_PATHS
from evaluate_c2_job_title_router import relation_parent_ids
from evaluate_dense_semantic_candidate_lane import concept_text
from evaluate_p80_lexical_ablation import as_list, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from occupational_information_coverage import find_explicit_taxonomy_ids, record_map

MODEL_NAME = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
OCC_INFO_URL = "https://data.arbetsformedlingen.se/yrke/yrkesinformation/yrkesinformation-interimslosning.json"
KV_PATHS = (
    "research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl",
    "research/benchmark/v31/training-skill-second-holdout/cases.jsonl",
    "research/benchmark/v31/training-skill-third-holdout/cases.jsonl",
)


def phrase_present(text: str, surface: str) -> bool:
    haystack = tokens(text)
    needle = tokens(surface)
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(haystack[i : i + width] == needle for i in range(len(haystack) - width + 1))


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


def rank_metrics(sims: np.ndarray, target_ids: list[str], ids: list[str]) -> dict[str, Any]:
    pos = {cid: i for i, cid in enumerate(ids)}
    top1 = hit5 = 0
    rr = 0.0
    rows = []
    for i, target in enumerate(target_ids):
        if target not in pos:
            rows.append({"target_id": target, "rank": None})
            continue
        order = np.argsort(-sims[i], kind="stable")
        target_index = pos[target]
        rank = int(np.flatnonzero(order == target_index)[0]) + 1
        top1 += rank == 1
        hit5 += rank <= 5
        rr += 1.0 / rank
        rows.append({"target_id": target, "rank": rank})
    n = len(target_ids)
    return {
        "cases": n,
        "top1": top1,
        "hit_at_5": hit5,
        "mrr": round(rr / n, 6) if n else 0.0,
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--output", default="artifacts/dense-source-attested-crosscheck-v31.json")
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args()

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    tax_url = "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json"
    ad_url = "https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t31/relevans-nyckelord.json.zst"
    relevant_url = "https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/v1/relevanta-kompetenser-t31.json.zst"

    wires = {
        "taxonomy": fetch(tax_url),
        "occupational_information": fetch(OCC_INFO_URL),
        "ad_language": fetch(ad_url),
        "relevant_skills": fetch(relevant_url),
    }
    adapters = {
        "taxonomy": "taxonomy-common-relations",
        "occupational_information": "occupational-information",
        "ad_language": "ad-keyword-corpus",
        "relevant_skills": "relevant-skills",
    }
    source_sha = {name: hashlib.sha256(body).hexdigest() for name, body in wires.items()}
    for name, adapter in adapters.items():
        if source_sha[name] != expected_hash(registry, adapter):
            raise RuntimeError(f"source drift: {name}")

    taxonomy = json.loads(wires["taxonomy"])
    occ_info = json.loads(wires["occupational_information"])
    ad_doc = json.loads(zstd.ZstdDecompressor().decompress(wires["ad_language"]))
    relevant_doc = json.loads(zstd.ZstdDecompressor().decompress(wires["relevant_skills"]))
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    all_ids = set(by_id)
    occupation_ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    skill_ids_all = {cid for cid, c in by_id.items() if c.get("type") == "skill"}
    if len(occupation_ids) != 2105:
        raise RuntimeError("occupation universe drift")

    # Reconstruct exactly the same strict YV source-attested selection used earlier.
    active_occ = set(occupation_ids)
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

    yv_cases: list[dict[str, str]] = []
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
        yv_cases.append({"id": slug, "query": query, "target_id": target})
    if len(yv_cases) != 17:
        raise RuntimeError(f"strict YV case drift: {len(yv_cases)} != 17")

    ad_data = ad_doc.get("data", {}).get("occupation_name")
    relevant_data = relevant_doc.get("data")
    if not isinstance(ad_data, dict) or not isinstance(relevant_data, dict):
        raise RuntimeError("YV evidence source shape drift")

    canonical_docs = ["passage: " + concept_text(by_id[cid]) for cid in occupation_ids]
    ad_ids = sorted(cid for cid in ad_data if cid in active_occ)
    ad_docs = []
    for cid in ad_ids:
        keywords = ad_data[cid].get("keywords") if isinstance(ad_data[cid], dict) else None
        if not isinstance(keywords, dict):
            raise RuntimeError(f"ad source drift: {cid}")
        ad_docs.append("passage: " + " | ".join(sorted((str(x) for x in keywords), key=norm)))
    relevant_docs = []
    for occ_id in occupation_ids:
        items = relevant_data[occ_id].get("relevant_skills") if isinstance(relevant_data.get(occ_id), dict) else None
        if not isinstance(items, list):
            raise RuntimeError(f"relevant source drift: {occ_id}")
        seen: set[str] = set()
        labels: list[str] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            sid = str(item["id"])
            if sid not in skill_ids_all or sid in seen:
                continue
            seen.add(sid)
            label = str(by_id[sid].get("preferred_label") or "").strip()
            if label:
                labels.append(label)
        relevant_docs.append("passage: " + " | ".join(labels))

    # Existing 81 source-attested KV cases. These frozen files use an explicit
    # `target` object rather than the generic must/acceptable benchmark schema.
    kv_cases: list[dict[str, Any]] = []
    for path in KV_PATHS:
        kv_cases.extend(load_jsonl(Path(path)))
    if len(kv_cases) != 81:
        raise RuntimeError(f"KV source-attested case drift: {len(kv_cases)} != 81")
    kv_ids = sorted(p80_skill_ids(pareto))
    teacher = teacher_map()
    kv_docs = ["passage: " + concept_text(by_id[cid], extra=teacher[cid]) for cid in kv_ids]
    kv_targets = []
    for row in kv_cases:
        target = row.get("target")
        cid = str(target.get("concept_id")) if isinstance(target, dict) and target.get("concept_id") else ""
        if not cid:
            candidates = [*(row.get("must") or []), *(row.get("acceptable") or [])]
            fallback_ids = [
                str(x["concept_id"])
                for x in candidates
                if isinstance(x, dict) and x.get("concept_id")
            ]
            if len(set(fallback_ids)) == 1:
                cid = fallback_ids[0]
        if not cid or cid not in kv_ids:
            raise RuntimeError(f"KV case must have one P80 scored target: {row.get('id')}")
        kv_targets.append(cid)

    model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION, trust_remote_code=False)

    def encode(texts: list[str]) -> np.ndarray:
        return np.asarray(
            model.encode(
                texts,
                batch_size=args.batch_size,
                normalize_embeddings=True,
                show_progress_bar=True,
            ),
            dtype=np.float32,
        )

    yv_q = encode(["query: " + row["query"] for row in yv_cases])
    yv_canonical = rank_metrics(
        yv_q @ encode(canonical_docs).T,
        [r["target_id"] for r in yv_cases],
        occupation_ids,
    )
    yv_ad = rank_metrics(
        yv_q @ encode(ad_docs).T,
        [r["target_id"] for r in yv_cases],
        ad_ids,
    )
    yv_relevant = rank_metrics(
        yv_q @ encode(relevant_docs).T,
        [r["target_id"] for r in yv_cases],
        occupation_ids,
    )

    kv_q = encode(["query: " + str(row["query"]) for row in kv_cases])
    kv_dense = rank_metrics(kv_q @ encode(kv_docs).T, kv_targets, kv_ids)

    # Oracle union is diagnostic complementarity only, never a fusion rule.
    yv_union_hit5 = 0
    for i in range(len(yv_cases)):
        ranks = [
            yv_canonical["rows"][i]["rank"],
            yv_ad["rows"][i]["rank"],
            yv_relevant["rows"][i]["rank"],
        ]
        yv_union_hit5 += any(rank is not None and rank <= 5 for rank in ranks)

    result = {
        "status": "already-opened source-attested cross-check; no tuning or runtime promotion",
        "model": {"name": MODEL_NAME, "revision": MODEL_REVISION},
        "source_sha256": source_sha,
        "yv_strict_work_task_17": {
            "canonical_dense": yv_canonical,
            "observed_ad_language_dense": yv_ad,
            "relevant_skill_labels_dense": yv_relevant,
            "oracle_union_hit_at_5": yv_union_hit5,
        },
        "kv_source_attested_81": {"canonical_plus_teacher_dense": kv_dense},
        "decision_contract": (
            "This cross-check may support architecture diagnosis only. The 17/81 cases were already opened in prior research; "
            "they cannot select thresholds, fusion weights, or establish independent user accuracy."
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
                "model": result["model"],
                "yv": {
                    k: {x: v for x, v in value.items() if x != "rows"}
                    if isinstance(value, dict)
                    else value
                    for k, value in result["yv_strict_work_task_17"].items()
                },
                "kv": {
                    k: {x: v for x, v in value.items() if x != "rows"}
                    for k, value in result["kv_source_attested_81"].items()
                },
                "output": str(out),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
