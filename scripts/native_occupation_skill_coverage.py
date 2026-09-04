#!/usr/bin/env python3
"""Measure native v31 occupation-name -> skill relations and compare to KV.

Taxonomy documents `essential` and `optional` as native curated relation types.
Kompetensväljaren publishes `essential_skills`, `optional_skills` and a separate
`regulated_skills` layer. This extractor establishes their exact relation rather
than treating similar field names as equivalent by assumption.

All API calls are pinned to an explicit published taxonomy version and returned
identities are validated against the immutable common v31 snapshot.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

USER_AGENT = "semantic-taxonomy-search-native-occ-skill/0.2"
GRAPHQL_URL = "https://taxonomy.api.jobtechdev.se/v1/taxonomy/graphql"
REGULATED_COLLECTION_LABEL = "Reglerade behörigheter"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str, timeout: int = 180) -> tuple[bytes, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
    return body, json.loads(body)


def graphql(query: str, timeout: int = 180) -> tuple[bytes, Any, str]:
    url = GRAPHQL_URL + "?" + urllib.parse.urlencode({"query": query})
    body, doc = fetch_json(url, timeout=timeout)
    if not isinstance(doc, dict):
        raise RuntimeError("GraphQL response is not an object")
    if doc.get("errors"):
        raise RuntimeError(f"GraphQL returned errors: {json.dumps(doc['errors'], ensure_ascii=False)}")
    return body, doc, url


def pct(n: int, d: int) -> float | None:
    return None if not d else round(100.0 * n / d, 3)


def compare_pairs(left: set[tuple[str, str]], right: set[tuple[str, str]]) -> dict[str, Any]:
    union = left | right
    return {
        "left_edges": len(left),
        "right_edges": len(right),
        "intersection_edges": len(left & right),
        "left_only_edges": len(left - right),
        "right_only_edges": len(right - left),
        "jaccard": round(len(left & right) / len(union), 6) if union else 1.0,
        "exact_equal": left == right,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31")
    parser.add_argument("--output-dir", default="artifacts/native-occupation-skill-v31")
    args = parser.parse_args()

    version = str(args.version)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    kv_url = f"https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t{version}.json"

    taxonomy_body, taxonomy_doc = fetch_json(taxonomy_url)
    kv_body, kv_doc = fetch_json(kv_url)

    concepts = taxonomy_doc.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy snapshot missing data.concepts")

    by_id: dict[str, dict[str, Any]] = {}
    ids_by_type: dict[str, set[str]] = defaultdict(set)
    for concept in concepts:
        if not isinstance(concept, dict) or not concept.get("id"):
            continue
        cid = str(concept["id"])
        ctype = str(concept.get("type") or "")
        by_id[cid] = concept
        ids_by_type[ctype].add(cid)

    query = f'''query NativeOccupationSkills {{
      occupations: concepts(type: "occupation-name", version: "{version}", limit: 10000) {{
        id
        preferred_label
        type
        essential(type: "skill") {{ id preferred_label type }}
        optional(type: "skill") {{ id preferred_label type }}
      }}
      skill_collections: concepts(type: "skill-collection", version: "{version}", limit: 1000) {{
        id
        preferred_label
        type
        related(type: "skill") {{ id preferred_label type }}
      }}
    }}'''

    gql_body, gql_doc, gql_url = graphql(query)
    gql_data = gql_doc.get("data")
    if not isinstance(gql_data, dict):
        raise RuntimeError("GraphQL response missing data object")
    gql_concepts = gql_data.get("occupations")
    skill_collections = gql_data.get("skill_collections")
    if not isinstance(gql_concepts, list) or not isinstance(skill_collections, list):
        raise RuntimeError("GraphQL response missing occupations or skill_collections")

    active_occupations = ids_by_type.get("occupation-name", set())
    active_skills = ids_by_type.get("skill", set())
    gql_occ_ids = {str(c.get("id")) for c in gql_concepts if isinstance(c, dict) and c.get("id")}
    if gql_occ_ids != active_occupations:
        raise RuntimeError(
            f"GraphQL occupation universe drift: gql={len(gql_occ_ids)} active={len(active_occupations)} "
            f"missing={len(active_occupations - gql_occ_ids)} extra={len(gql_occ_ids - active_occupations)}"
        )

    relation_fields = ("essential", "optional")
    native_pairs: dict[str, set[tuple[str, str]]] = {field: set() for field in relation_fields}
    native_skill_ids: dict[str, set[str]] = {field: set() for field in relation_fields}
    native_nonempty = Counter()
    invalid_native: list[dict[str, str]] = []

    for occupation in gql_concepts:
        if not isinstance(occupation, dict):
            continue
        oid = str(occupation.get("id") or "")
        if occupation.get("type") != "occupation-name":
            invalid_native.append({"source_id": oid, "field": "source", "reason": "wrong source type"})
        for field in relation_fields:
            rels = occupation.get(field) or []
            if not isinstance(rels, list):
                raise RuntimeError(f"GraphQL {field} is not a list for {oid}")
            if rels:
                native_nonempty[field] += 1
            for skill in rels:
                if not isinstance(skill, dict) or not skill.get("id"):
                    continue
                sid = str(skill["id"])
                native_pairs[field].add((oid, sid))
                native_skill_ids[field].add(sid)
                canonical = by_id.get(sid)
                if canonical is None or canonical.get("type") != "skill" or skill.get("type") != "skill":
                    invalid_native.append({
                        "source_id": oid,
                        "field": field,
                        "target_id": sid,
                        "reason": "target is not active skill",
                    })

    regulated_collections = [
        collection for collection in skill_collections
        if isinstance(collection, dict) and collection.get("preferred_label") == REGULATED_COLLECTION_LABEL
    ]
    if len(regulated_collections) != 1:
        labels = sorted(str(c.get("preferred_label")) for c in skill_collections if isinstance(c, dict))
        raise RuntimeError(
            f"expected exactly one {REGULATED_COLLECTION_LABEL!r} skill collection, got {len(regulated_collections)}; "
            f"available labels={labels}"
        )
    regulated_collection = regulated_collections[0]
    regulated_skill_ids: set[str] = set()
    invalid_collection_targets: list[str] = []
    related_skills = regulated_collection.get("related") or []
    if not isinstance(related_skills, list):
        raise RuntimeError("regulated skill collection related field is not a list")
    for skill in related_skills:
        if not isinstance(skill, dict) or not skill.get("id"):
            continue
        sid = str(skill["id"])
        regulated_skill_ids.add(sid)
        canonical = by_id.get(sid)
        if canonical is None or canonical.get("type") != "skill" or skill.get("type") != "skill":
            invalid_collection_targets.append(sid)

    regulated_native_pairs = {
        pair for pair in native_pairs["essential"] if pair[1] in regulated_skill_ids
    }
    nonregulated_native_essential_pairs = native_pairs["essential"] - regulated_native_pairs

    # KV comparison: only occupation-name context records are valid here.
    kv_data = kv_doc.get("data")
    if not isinstance(kv_data, dict):
        raise RuntimeError("KV missing data object")
    declared_version = str(kv_doc.get("metadata", {}).get("labour_market_taxonomy_version") or "")
    if version not in declared_version:
        raise RuntimeError(f"KV taxonomy version mismatch: {declared_version!r}")

    kv_field_map = {
        "essential": "essential_skills",
        "optional": "optional_skills",
        "regulated": "regulated_skills",
    }
    kv_pairs: dict[str, set[tuple[str, str]]] = {name: set() for name in kv_field_map}
    invalid_kv: list[dict[str, str]] = []

    for oid, record in kv_data.items():
        if not isinstance(record, dict) or record.get("type") != "occupation-name":
            continue
        if oid not in active_occupations:
            invalid_kv.append({"source_id": oid, "field": "source", "reason": "non-active occupation"})
        for semantic_name, kv_field in kv_field_map.items():
            mapping = record.get(kv_field) or {}
            if not isinstance(mapping, dict):
                raise RuntimeError(f"KV {kv_field} for {oid} is not object")
            for _label, sid_value in mapping.items():
                sid = str(sid_value or "")
                if not sid:
                    continue
                kv_pairs[semantic_name].add((oid, sid))
                if sid not in active_skills:
                    invalid_kv.append({"source_id": oid, "field": kv_field, "target_id": sid, "reason": "non-active skill"})

    comparison = {
        "optional_native_vs_kv_optional": compare_pairs(native_pairs["optional"], kv_pairs["optional"]),
        "essential_native_vs_kv_essential": compare_pairs(native_pairs["essential"], kv_pairs["essential"]),
        "native_regulated_essential_vs_kv_regulated": compare_pairs(regulated_native_pairs, kv_pairs["regulated"]),
        "native_nonregulated_essential_vs_kv_essential": compare_pairs(
            nonregulated_native_essential_pairs, kv_pairs["essential"]
        ),
        "native_essential_vs_kv_essential_plus_regulated": compare_pairs(
            native_pairs["essential"], kv_pairs["essential"] | kv_pairs["regulated"]
        ),
    }

    aggregate = {
        "schema_version": 2,
        "taxonomy_version": version,
        "generated_at": now_utc(),
        "sources": {
            "taxonomy_snapshot": {
                "url": taxonomy_url,
                "bytes": len(taxonomy_body),
                "sha256": hashlib.sha256(taxonomy_body).hexdigest(),
            },
            "taxonomy_graphql": {
                "url": gql_url,
                "response_bytes": len(gql_body),
                "response_sha256": hashlib.sha256(gql_body).hexdigest(),
                "explicit_version": version,
            },
            "kompetensvaljaren": {
                "url": kv_url,
                "bytes": len(kv_body),
                "sha256": hashlib.sha256(kv_body).hexdigest(),
                "declared_taxonomy_version": declared_version,
            },
        },
        "native": {
            "occupation_sources": len(gql_occ_ids),
            "active_occupation_universe": len(active_occupations),
            "invalid_relation_occurrences": len(invalid_native),
            "fields": {
                field: {
                    "sources_nonempty": native_nonempty[field],
                    "source_coverage_pct": pct(native_nonempty[field], len(active_occupations)),
                    "edge_count": len(native_pairs[field]),
                    "unique_skill_ids": len(native_skill_ids[field]),
                    "active_skill_coverage_pct": pct(len(native_skill_ids[field] & active_skills), len(active_skills)),
                }
                for field in relation_fields
            },
            "regulated_collection": {
                "id": regulated_collection.get("id"),
                "preferred_label": regulated_collection.get("preferred_label"),
                "related_active_skill_ids": len(regulated_skill_ids & active_skills),
                "invalid_target_ids": len(invalid_collection_targets),
                "essential_edges_using_regulated_skill": len(regulated_native_pairs),
                "nonregulated_essential_edges": len(nonregulated_native_essential_pairs),
            },
        },
        "kv_invalid_occurrences": len(invalid_kv),
        "comparison_to_kv": comparison,
    }

    (out / "aggregate.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "anomalies.json").write_text(
        json.dumps(
            {
                "invalid_native": invalid_native,
                "invalid_regulated_collection_targets": invalid_collection_targets,
                "invalid_kv": invalid_kv,
                "native_essential_not_in_kv_union": sorted(
                    [list(x) for x in native_pairs["essential"] - (kv_pairs["essential"] | kv_pairs["regulated"])]
                ),
                "kv_essential_regulated_not_native": sorted(
                    [list(x) for x in (kv_pairs["essential"] | kv_pairs["regulated"]) - native_pairs["essential"]]
                ),
                "native_optional_not_kv": sorted([list(x) for x in native_pairs["optional"] - kv_pairs["optional"]]),
                "kv_optional_not_native": sorted([list(x) for x in kv_pairs["optional"] - native_pairs["optional"]]),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    lines = [
        f"# Native occupation→skill coverage — taxonomy v{version}",
        "",
        f"GraphQL occupation universe: **{len(gql_occ_ids):,} / {len(active_occupations):,}** active occupations.",
        "",
        "| Native field | non-empty occupations | coverage | edges | unique skills | active skill coverage |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for field in relation_fields:
        row = aggregate["native"]["fields"][field]
        lines.append(
            f"| `{field}` | {row['sources_nonempty']:,} | {row['source_coverage_pct']}% | "
            f"{row['edge_count']:,} | {row['unique_skill_ids']:,} | {row['active_skill_coverage_pct']}% |"
        )

    lines += [
        "",
        "## KV relationship",
        "",
        f"Regulated collection `{regulated_collection.get('preferred_label')}` ({regulated_collection.get('id')}) "
        f"contains **{len(regulated_skill_ids):,}** active skill IDs.",
        f"Native essential edges using one of those skills: **{len(regulated_native_pairs):,}**.",
        "",
        "| Comparison | left | right | intersection | left-only | right-only | exact |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name, row in comparison.items():
        lines.append(
            f"| `{name}` | {row['left_edges']:,} | {row['right_edges']:,} | {row['intersection_edges']:,} | "
            f"{row['left_only_edges']:,} | {row['right_only_edges']:,} | {row['exact_equal']} |"
        )

    lines += [
        "",
        "## Guardrails",
        "",
        "- Native `essential` / `optional` are curated taxonomy relation types, not relevance scores.",
        "- KV equivalence or partitioning is accepted only when exact directed-pair equality is measured.",
        "- `regulated_skills` remains a separately named KV provenance layer even if it partitions native `essential`.",
        "- GraphQL is pinned to the explicit taxonomy version and identities are validated against the immutable snapshot.",
        "",
    ]
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
