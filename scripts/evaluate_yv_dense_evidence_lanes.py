#!/usr/bin/env python3
"""Probe dense YV retrieval over provenance-separated evidence representations.

Opened diagnostic only. The multilingual E5 model revision is pinned from the preceding
canonical-dense run. Canonical occupation text, observed AF ad language, and AF Relevanta
kompetenser labels are encoded as separate lanes. No fusion weights, thresholds, or
runtime policy are selected on the opened stress suite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import zstandard as zstd
from sentence_transformers import SentenceTransformer

from evaluate_dense_semantic_candidate_lane import concept_text, summarize_opened_cases
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm

MODEL_NAME = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"


def category_oracle(cases: list[dict[str, Any]], lane_rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    row_maps = {name: {r["id"]: r for r in rows} for name, rows in lane_rows.items()}
    out: dict[str, Any] = {}
    for category in sorted({str(c["category"]) for c in cases}):
        target = [c for c in cases if c["category"] == category and (c.get("expect") or [])]
        if not target:
            continue
        top5 = top20 = 0
        rescued_by: dict[str, int] = {name: 0 for name in lane_rows}
        for case in target:
            ranks = {
                name: row_maps[name][case["id"]]["expected_family_rank"]
                for name in lane_rows
            }
            if any(rank is not None and rank <= 5 for rank in ranks.values()):
                top5 += 1
            if any(rank is not None and rank <= 20 for rank in ranks.values()):
                top20 += 1
            for name, rank in ranks.items():
                if rank is not None and rank <= 5 and not any(
                    other_rank is not None and other_rank <= 5
                    for other_name, other_rank in ranks.items()
                    if other_name != name
                ):
                    rescued_by[name] += 1
        out[category] = {
            "target_cases": len(target),
            "oracle_union_hit_at_5": top5,
            "oracle_union_hit_at_20": top20,
            "unique_top5_rescues_by_lane": rescued_by,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--output", default="artifacts/yv-dense-evidence-lanes-v31.json")
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args()

    stress = json.loads(Path(args.stress).read_text(encoding="utf-8"))
    cases = list(stress.get("yv") or [])
    if len(cases) != 54:
        raise RuntimeError("opened YV stress suite drift")
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))

    taxonomy_url = "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json"
    ad_url = "https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t31/relevans-nyckelord.json.zst"
    relevant_url = "https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/v1/relevanta-kompetenser-t31.json.zst"

    taxonomy_wire = fetch(taxonomy_url)
    ad_wire = fetch(ad_url)
    relevant_wire = fetch(relevant_url)
    source_sha = {
        "taxonomy": hashlib.sha256(taxonomy_wire).hexdigest(),
        "ad_language": hashlib.sha256(ad_wire).hexdigest(),
        "relevant_skills": hashlib.sha256(relevant_wire).hexdigest(),
    }
    for key, adapter in (
        ("taxonomy", "taxonomy-common-relations"),
        ("ad_language", "ad-keyword-corpus"),
        ("relevant_skills", "relevant-skills"),
    ):
        if source_sha[key] != expected_hash(registry, adapter):
            raise RuntimeError(f"source drift: {key}")

    taxonomy = json.loads(taxonomy_wire)
    ad_doc = json.loads(zstd.ZstdDecompressor().decompress(ad_wire))
    relevant_doc = json.loads(zstd.ZstdDecompressor().decompress(relevant_wire))
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    occupation_ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(occupation_ids) != 2105:
        raise RuntimeError(f"occupation universe drift: {len(occupation_ids)}")

    canonical_labels = [str(by_id[cid].get("preferred_label") or cid) for cid in occupation_ids]
    canonical_docs = ["passage: " + concept_text(by_id[cid]) for cid in occupation_ids]

    ad_data = ad_doc.get("data", {}).get("occupation_name")
    if not isinstance(ad_data, dict):
        raise RuntimeError("ad language source shape drift")
    ad_ids = sorted(cid for cid in ad_data if cid in by_id and by_id[cid].get("type") == "occupation-name")
    if len(ad_ids) != 1051:
        raise RuntimeError(f"ad occupation coverage drift: {len(ad_ids)}")
    ad_labels = [str(by_id[cid].get("preferred_label") or cid) for cid in ad_ids]
    ad_docs: list[str] = []
    for cid in ad_ids:
        keywords = ad_data[cid].get("keywords") if isinstance(ad_data[cid], dict) else None
        if not isinstance(keywords, dict):
            raise RuntimeError(f"ad keyword record drift: {cid}")
        terms = sorted((str(term) for term in keywords), key=norm)
        ad_docs.append("passage: " + " | ".join(terms))

    relevant_data = relevant_doc.get("data")
    if not isinstance(relevant_data, dict) or set(relevant_data) != set(occupation_ids):
        raise RuntimeError("relevant-skill occupation universe drift")
    skill_ids = {cid for cid, c in by_id.items() if c.get("type") == "skill"}
    relevant_labels = canonical_labels
    relevant_docs: list[str] = []
    for occ_id in occupation_ids:
        items = relevant_data[occ_id].get("relevant_skills") if isinstance(relevant_data[occ_id], dict) else None
        if not isinstance(items, list):
            raise RuntimeError(f"relevant skill record drift: {occ_id}")
        labels: list[str] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            skill_id = str(item["id"])
            if skill_id not in skill_ids:
                raise RuntimeError(f"non-active skill in relevant source: {skill_id}")
            if skill_id in seen:
                continue
            seen.add(skill_id)
            label = str(by_id[skill_id].get("preferred_label") or "").strip()
            if label:
                labels.append(label)
        relevant_docs.append("passage: " + " | ".join(labels))

    model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION, trust_remote_code=False)
    queries = ["query: " + str(c["query"]) for c in cases]
    q = np.asarray(model.encode(queries, batch_size=args.batch_size, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)

    lane_specs = {
        "canonical": (canonical_docs, canonical_labels),
        "observed_ad_language": (ad_docs, ad_labels),
        "relevant_skill_labels": (relevant_docs, relevant_labels),
    }
    lane_results: dict[str, Any] = {}
    rows_by_lane: dict[str, list[dict[str, Any]]] = {}
    for name, (docs, labels) in lane_specs.items():
        emb = np.asarray(model.encode(docs, batch_size=args.batch_size, normalize_embeddings=True, show_progress_bar=True), dtype=np.float32)
        summary = summarize_opened_cases(cases, q @ emb.T, labels)
        lane_results[name] = {"categories": summary["categories"], "rows": summary["rows"]}
        rows_by_lane[name] = summary["rows"]

    result = {
        "status": "opened diagnostic only; evidence lanes remain provenance-separated and no fusion is promoted",
        "model": {"name": MODEL_NAME, "revision": MODEL_REVISION},
        "source_sha256": source_sha,
        "representations": {
            "canonical": "preferred label + distinct canonical definition + canonical alternative labels",
            "observed_ad_language": "AF occupation-linked employer-language keyword terms only",
            "relevant_skill_labels": "preferred labels of AF Relevanta kompetenser skills linked to each occupation",
        },
        "opened_stress": lane_results,
        "oracle_complementarity": category_oracle(cases, rows_by_lane),
        "decision_contract": (
            "Use only to classify whether YV's dense failure is representation-bound. Do not choose fusion, "
            "weights, thresholds, or runtime promotion from this opened assistant-authored suite."
        ),
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "model": result["model"],
        "categories_by_lane": {name: data["categories"] for name, data in lane_results.items()},
        "oracle_complementarity": result["oracle_complementarity"],
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
