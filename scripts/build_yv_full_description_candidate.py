#!/usr/bin/env python3
"""Build the full-universe YV description candidate used for Track-2 research.

This is deliberately separate from the frozen 165-target C2 demo. It compiles:
- every active v31 occupation-name as a canonical BM25 document;
- exact active job-title preferred-label -> typed occupation-name parent routes;
- the pinned AF ad-keyword corpus as a separate observed-language lane.

The lanes remain separate in the artifact. In particular, ad-derived terms are not
promoted to canonical synonyms and their published metrics are preserved verbatim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import zstandard as zstd

from build_yv_demo_asset import bm25_postings
from evaluate_c2_job_title_router import build_c1_index, relation_parent_ids
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm


def load_checked_json(url: str, expected_sha: str, *, compressed: bool = False) -> tuple[bytes, Any]:
    wire = fetch(url)
    actual = hashlib.sha256(wire).hexdigest()
    if actual != expected_sha:
        raise RuntimeError(f"source drift for {url}: expected {expected_sha}, got {actual}")
    raw = zstd.ZstdDecompressor().decompress(wire) if compressed else wire
    return wire, json.loads(raw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--coverage-aggregate", default="research/coverage/v31/unified-target-coverage-aggregate.json")
    ap.add_argument("--output", default="artifacts/yv-full-description-candidate-v31.json")
    args = ap.parse_args()

    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    coverage = json.loads(Path(args.coverage_aggregate).read_text(encoding="utf-8"))
    expected_count = int(coverage["target_counts"]["yv_occupation_name"])

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    ad_url = (
        "https://data.arbetsformedlingen.se/yrke/narliggande-yrken/"
        f"v1/t{version}/relevans-nyckelord.json.zst"
    )
    taxonomy_wire, taxonomy = load_checked_json(
        taxonomy_url, expected_hash(registry, "taxonomy-common-relations")
    )
    ad_wire, ad_doc = load_checked_json(
        ad_url, expected_hash(registry, "ad-keyword-corpus"), compressed=True
    )

    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing data.concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    occupation_ids = sorted(
        cid for cid, concept in by_id.items() if concept.get("type") == "occupation-name"
    )
    if len(occupation_ids) != expected_count:
        raise RuntimeError(
            f"active occupation-name universe drift: expected {expected_count}, got {len(occupation_ids)}"
        )

    ranker, exact_surfaces, surface_tokens = build_c1_index(by_id, occupation_ids)

    exact_index: dict[str, list[int]] = defaultdict(list)
    for index, cid in enumerate(occupation_ids):
        for surface in sorted(exact_surfaces[cid]):
            exact_index[surface].append(index)

    # Keep the same source-attested exact-title routing semantics as C2, but do not
    # restrict routed parents to the old 165-target P80 prototype.
    label_to_parent_ids: dict[str, set[str]] = defaultdict(set)
    label_to_job_ids: dict[str, set[str]] = defaultdict(set)
    for cid, concept in by_id.items():
        if concept.get("type") != "job-title":
            continue
        label = norm(concept.get("preferred_label"))
        if not label:
            continue
        parents = relation_parent_ids(concept, by_id)
        if not parents:
            continue
        label_to_parent_ids[label].update(parents)
        label_to_job_ids[label].add(cid)

    routes = {
        label: sorted(parent_ids)
        for label, parent_ids in sorted(label_to_parent_ids.items())
    }
    routed_parent_ids = sorted({cid for parent_ids in routes.values() for cid in parent_ids})

    ad_data = ad_doc.get("data")
    if not isinstance(ad_data, dict) or not isinstance(ad_data.get("occupation_name"), dict):
        raise RuntimeError("ad keyword corpus missing data.occupation_name")
    ad_occ = ad_data["occupation_name"]

    unknown_ad_ids = sorted(set(ad_occ) - set(occupation_ids))
    if unknown_ad_ids:
        raise RuntimeError(f"ad keyword corpus contains unknown occupation IDs: {unknown_ad_ids[:5]}")

    observed_lane: dict[str, Any] = {}
    distinct_terms: set[str] = set()
    for cid in sorted(ad_occ):
        record = ad_occ[cid]
        if not isinstance(record, dict):
            raise RuntimeError(f"invalid ad keyword record for {cid}")
        keywords = record.get("keywords")
        if not isinstance(keywords, dict):
            raise RuntimeError(f"invalid ad keywords for {cid}")
        preserved_keywords: dict[str, dict[str, float | int]] = {}
        for term, metrics in sorted(keywords.items(), key=lambda item: norm(item[0])):
            if not isinstance(metrics, dict):
                raise RuntimeError(f"invalid metrics for ad keyword {term!r} / {cid}")
            kept: dict[str, float | int] = {}
            for metric in ("weighted_frequency", "TFIDF", "BM25", "RCA"):
                value = metrics.get(metric)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    kept[metric] = value
            if not kept:
                raise RuntimeError(f"ad keyword has no published metrics: {term!r} / {cid}")
            preserved_keywords[str(term)] = kept
            distinct_terms.add(str(term))
        observed_lane[cid] = {
            "number_of_ads": record.get("number_of_ads"),
            "keywords": preserved_keywords,
        }

    metadata = ad_doc.get("metadata")
    asset = {
        "schema_version": 1,
        "engine": "YV-description-full-v0",
        "status": "research_candidate_not_demo_or_product",
        "taxonomy_version": int(version),
        "canonical_lane": {
            "semantics": "BM25 over preferred label + distinct canonical definition + canonical alternative labels",
            "document_ids": occupation_ids,
            "labels": [str(by_id[cid].get("preferred_label") or cid) for cid in occupation_ids],
            "postings": bm25_postings(ranker, occupation_ids),
            "exact_surfaces": {surface: rows for surface, rows in sorted(exact_index.items())},
            "surface_tokens": [sorted(surface_tokens[cid]) for cid in occupation_ids],
        },
        "exact_job_title_routes": {
            "semantics": "active job-title preferred label -> typed occupation-name parents; retrieval vocabulary only",
            "routes": routes,
            "matching_job_title_ids": {
                label: sorted(job_ids) for label, job_ids in sorted(label_to_job_ids.items())
            },
        },
        "observed_ad_language_lane": {
            "semantics": (
                "occupation-linked employer-language keywords from the pinned AF corpus; "
                "separate non-canonical evidence, with source metrics preserved"
            ),
            "occupations": observed_lane,
            "source_metadata": metadata if isinstance(metadata, dict) else {},
        },
        "metadata": {
            "taxonomy_sha256": hashlib.sha256(taxonomy_wire).hexdigest(),
            "ad_keyword_wire_sha256": hashlib.sha256(ad_wire).hexdigest(),
            "occupation_target_count": len(occupation_ids),
            "canonical_real_definition_count": sum(
                1
                for cid in occupation_ids
                if norm(by_id[cid].get("definition"))
                and norm(by_id[cid].get("definition")) != norm(by_id[cid].get("preferred_label"))
            ),
            "canonical_alternative_label_target_count": sum(
                1 for cid in occupation_ids if by_id[cid].get("alternative_labels")
            ),
            "job_title_route_surface_count": len(routes),
            "routed_parent_count": len(routed_parent_ids),
            "observed_ad_language_occupation_count": len(observed_lane),
            "observed_ad_language_distinct_term_count": len(distinct_terms),
            "retrieval_contract": (
                "full active occupation-name destination universe; canonical and observed-language lanes "
                "remain provenance-separated; no teacher/model-generated text"
            ),
        },
    }

    if asset["metadata"]["occupation_target_count"] != 2105:
        raise RuntimeError("v31 invariant drift: expected exactly 2105 active occupation-name targets")
    if asset["metadata"]["observed_ad_language_occupation_count"] != 1051:
        raise RuntimeError("v31 invariant drift: expected exactly 1051 ad-language occupation contexts")
    if asset["metadata"]["observed_ad_language_distinct_term_count"] != 11085:
        raise RuntimeError("v31 invariant drift: expected exactly 11085 distinct ad-language terms")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(asset, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "engine": asset["engine"],
                "targets": asset["metadata"]["occupation_target_count"],
                "canonical_real_definitions": asset["metadata"]["canonical_real_definition_count"],
                "job_title_route_surfaces": asset["metadata"]["job_title_route_surface_count"],
                "routed_parents": asset["metadata"]["routed_parent_count"],
                "ad_language_occupations": asset["metadata"]["observed_ad_language_occupation_count"],
                "ad_language_distinct_terms": asset["metadata"]["observed_ad_language_distinct_term_count"],
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
