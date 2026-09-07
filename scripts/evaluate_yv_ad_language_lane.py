#!/usr/bin/env python3
"""Measure the AF ad-keyword lane independently of the full canonical YV lane.

This is an opened development diagnostic, not a promoted retrieval configuration.
Queries come from Yrkesinformation `work_task` text for records with exactly one explicit
active v31 occupation-name ID. The Yrkesinformation text is never ingested into either
retrieval lane. Cases containing the target occupation/job-title surface are excluded.

The observed lane intentionally uses only the keyword strings as a plain BM25 document.
Published weighted_frequency/TFIDF/BM25/RCA values remain uninterpreted here; this pass
asks the narrower question whether observed employer vocabulary adds lexical recall at all.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import zstandard as zstd

from evaluate_c2_job_title_router import build_c1_index, relation_parent_ids
from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, norm, tokens
from evaluate_pareto_c1 import rank_c1
from occupational_information_coverage import find_explicit_taxonomy_ids, record_map

OCC_INFO_URL = (
    "https://data.arbetsformedlingen.se/yrke/yrkesinformation/"
    "yrkesinformation-interimslosning.json"
)


def phrase_present(text: str, surface: str) -> bool:
    """Match a complete token sequence, insensitive to punctuation/case."""
    haystack = tokens(text)
    needle = tokens(surface)
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(haystack[index:index + width] == needle for index in range(len(haystack) - width + 1))


def positive_bm25_rank(ranker: BM25, query: str) -> list[str]:
    qtokens = tokens(query)
    scored = [
        (cid, ranker.score(qtokens, cid))
        for cid in ranker.documents
    ]
    scored = [(cid, score) for cid, score in scored if score > 0.0]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [cid for cid, _ in scored]


def lane_metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"cases": 0, "top1": None, "hit_at_5": None, "mrr": None, "nonempty": None}
    top1 = sum(row[key]["rank"] == 1 for row in rows)
    hit5 = sum(
        isinstance(row[key]["rank"], int) and row[key]["rank"] <= 5
        for row in rows
    )
    nonempty = sum(bool(row[key]["top5"]) for row in rows)
    rr = sum(
        0.0 if row[key]["rank"] is None else 1.0 / int(row[key]["rank"])
        for row in rows
    )
    return {
        "cases": n,
        "top1": round(top1 / n, 6),
        "hit_at_5": round(hit5 / n, 6),
        "mrr": round(rr / n, 6),
        "nonempty": round(nonempty / n, 6),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--output", default="artifacts/yv-ad-language-lane-diagnostic-v31.json")
    args = ap.parse_args()

    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    ad_url = (
        "https://data.arbetsformedlingen.se/yrke/narliggande-yrken/"
        f"v1/t{version}/relevans-nyckelord.json.zst"
    )

    taxonomy_wire = fetch(taxonomy_url)
    taxonomy_sha = hashlib.sha256(taxonomy_wire).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")

    occ_info_wire = fetch(OCC_INFO_URL)
    occ_info_sha = hashlib.sha256(occ_info_wire).hexdigest()
    if occ_info_sha != expected_hash(registry, "occupational-information"):
        raise RuntimeError(f"occupational-information source drift: {occ_info_sha}")

    ad_wire = fetch(ad_url)
    ad_sha = hashlib.sha256(ad_wire).hexdigest()
    if ad_sha != expected_hash(registry, "ad-keyword-corpus"):
        raise RuntimeError(f"ad-keyword source drift: {ad_sha}")

    taxonomy = json.loads(taxonomy_wire)
    occ_info = json.loads(occ_info_wire)
    ad_doc = json.loads(zstd.ZstdDecompressor().decompress(ad_wire))

    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active_occ = {
        cid for cid, concept in by_id.items() if concept.get("type") == "occupation-name"
    }
    if len(active_occ) != 2105:
        raise RuntimeError(f"active occupation universe drift: {len(active_occ)}")

    full_ids = sorted(active_occ)
    canonical_ranker, canonical_exact, canonical_surface_tokens = build_c1_index(by_id, full_ids)

    ad_data = ad_doc.get("data")
    if not isinstance(ad_data, dict) or not isinstance(ad_data.get("occupation_name"), dict):
        raise RuntimeError("ad keyword corpus missing data.occupation_name")
    ad_occ = ad_data["occupation_name"]
    if set(ad_occ) - active_occ:
        raise RuntimeError("ad keyword corpus contains non-active occupation IDs")
    if len(ad_occ) != 1051:
        raise RuntimeError(f"ad occupation context drift: {len(ad_occ)}")

    ad_documents: dict[str, list[str]] = {}
    ad_exact: dict[str, set[str]] = {}
    distinct_terms: set[str] = set()
    for cid, record in sorted(ad_occ.items()):
        if not isinstance(record, dict) or not isinstance(record.get("keywords"), dict):
            raise RuntimeError(f"invalid ad keyword record: {cid}")
        keyword_strings = [str(term) for term in record["keywords"]]
        distinct_terms.update(keyword_strings)
        ad_documents[cid] = tokens(" ".join(keyword_strings))
        ad_exact[cid] = set()
    if len(distinct_terms) != 11085:
        raise RuntimeError(f"distinct ad keyword drift: {len(distinct_terms)}")
    ad_ranker = BM25(ad_documents, ad_exact)

    all_ids = set(by_id)
    records = record_map(occ_info.get("data"))
    metadata = occ_info.get("metadata")
    occupations_meta = metadata.get("occupations") if isinstance(metadata, dict) else None
    if not isinstance(occupations_meta, list):
        raise RuntimeError("Yrkesinformation missing metadata.occupations")

    job_title_surfaces_by_parent: dict[str, set[str]] = defaultdict(set)
    for concept in by_id.values():
        if concept.get("type") != "job-title":
            continue
        label = str(concept.get("preferred_label") or "").strip()
        if not label:
            continue
        for parent in relation_parent_ids(concept, by_id):
            job_title_surfaces_by_parent[parent].add(label)

    rows: list[dict[str, Any]] = []
    exclusions: dict[str, int] = defaultdict(int)
    for meta in occupations_meta:
        if not isinstance(meta, dict):
            continue
        slug = str(meta.get("slug") or "")
        record = records.get(slug)
        if not isinstance(record, dict):
            exclusions["missing_record"] += 1
            continue
        explicit = find_explicit_taxonomy_ids(record, all_ids) & active_occ
        if len(explicit) != 1:
            exclusions["not_unique_explicit_active_occupation"] += 1
            continue
        target = next(iter(explicit))
        query = str(record.get("work_task") or "").strip()
        if len(query) < 40:
            exclusions["work_task_too_short"] += 1
            continue

        concept = by_id[target]
        target_surfaces = {
            str(concept.get("preferred_label") or ""),
            *as_list(concept.get("alternative_labels")),
            *job_title_surfaces_by_parent.get(target, set()),
        }
        if any(surface and phrase_present(query, surface) for surface in target_surfaces):
            exclusions["contains_target_or_job_title_surface"] += 1
            continue

        canonical_scored = rank_c1(
            canonical_ranker, query, canonical_exact, canonical_surface_tokens
        )
        canonical_ranked = [cid for cid, _, _ in canonical_scored]
        ad_ranked = positive_bm25_rank(ad_ranker, query)

        canonical_rank = canonical_ranked.index(target) + 1 if target in canonical_ranked else None
        ad_rank = ad_ranked.index(target) + 1 if target in ad_ranked else None

        rows.append({
            "source_slug": slug,
            "target_id": target,
            "target_label": concept.get("preferred_label"),
            "target_has_ad_language": target in ad_occ,
            "query": query,
            "full_canonical_2105": {
                "rank": canonical_rank,
                "top5": canonical_ranked[:5],
            },
            "observed_ad_keyword_bm25": {
                "rank": ad_rank,
                "top5": ad_ranked[:5],
            },
        })

    if not rows:
        raise RuntimeError("no leak-free source-attested work_task cases")

    covered = [row for row in rows if row["target_has_ad_language"]]
    uncovered = [row for row in rows if not row["target_has_ad_language"]]
    canonical_hit5 = {
        row["source_slug"]
        for row in rows
        if isinstance(row["full_canonical_2105"]["rank"], int)
        and row["full_canonical_2105"]["rank"] <= 5
    }
    ad_hit5 = {
        row["source_slug"]
        for row in rows
        if isinstance(row["observed_ad_keyword_bm25"]["rank"], int)
        and row["observed_ad_keyword_bm25"]["rank"] <= 5
    }

    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "status": "opened_source_attested_development_diagnostic_not_human_validation",
        "lane_semantics": {
            "full_canonical_2105": (
                "all active occupation-name identities; preferred label + distinct canonical "
                "definition + canonical alternative labels; C1 long-description BM25 semantics"
            ),
            "observed_ad_keyword_bm25": (
                "only AF occupation-linked ad keyword strings; one textual occurrence per "
                "published keyword; no source metric weighting and no fusion"
            ),
        },
        "anti_leakage": (
            "Yrkesinformation work_task is evaluation-only; normalized token-sequence matching "
            "excludes target preferred/alternative labels and related active job-title surfaces, "
            "including next to punctuation"
        ),
        "source_sha256": {
            "taxonomy": taxonomy_sha,
            "occupational_information": occ_info_sha,
            "ad_keywords": ad_sha,
        },
        "case_count": len(rows),
        "target_ad_language_coverage": {
            "covered_cases": len(covered),
            "uncovered_cases": len(uncovered),
        },
        "metrics": {
            "all": {
                "full_canonical_2105": lane_metrics(rows, "full_canonical_2105"),
                "observed_ad_keyword_bm25": lane_metrics(rows, "observed_ad_keyword_bm25"),
            },
            "target_has_ad_language": {
                "full_canonical_2105": lane_metrics(covered, "full_canonical_2105"),
                "observed_ad_keyword_bm25": lane_metrics(covered, "observed_ad_keyword_bm25"),
            },
            "target_lacks_ad_language": {
                "full_canonical_2105": lane_metrics(uncovered, "full_canonical_2105"),
                "observed_ad_keyword_bm25": lane_metrics(uncovered, "observed_ad_keyword_bm25"),
            },
        },
        "complementarity_at_5": {
            "canonical_hit_cases": len(canonical_hit5),
            "ad_hit_cases": len(ad_hit5),
            "hit_in_either_lane_cases": len(canonical_hit5 | ad_hit5),
            "ad_rescues_canonical_miss_cases": len(ad_hit5 - canonical_hit5),
            "canonical_rescues_ad_miss_cases": len(canonical_hit5 - ad_hit5),
            "both_hit_cases": len(canonical_hit5 & ad_hit5),
            "neither_hit_cases": len(rows) - len(canonical_hit5 | ad_hit5),
        },
        "excluded": dict(sorted(exclusions.items())),
        "cases": rows,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "cases": len(rows),
        "covered_targets": len(covered),
        "metrics": result["metrics"],
        "complementarity_at_5": result["complementarity_at_5"],
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
