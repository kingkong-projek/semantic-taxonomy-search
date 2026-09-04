#!/usr/bin/env python3
"""Measure native v31 occupation-name -> skill relations and compare to KV.

The Taxonomy documentation defines `essential` and `optional` relations directly
between occupation-name and skill concepts.  These must be measured independently
before we decide whether similarly named Kompetensväljaren layers are the same
source semantics or merely analogous derived fields.

This extractor queries the published GraphQL API with an explicit immutable
Taxonomy version, validates every returned identity against the v31 common
snapshot, and compares directed relation pairs with the published KV v31 read
model.  It also tests whether KV `regulated_skills` is exactly the subset of
native essential relations whose skill belongs to the `Reglerade behörigheter`
skill collection.
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

USER_AGENT = "semantic-taxonomy-search-native-occ-skill/0.1"
GRAPHQL_URL = "https://taxonomy.api.jobtechdev.se/v1/taxonomy/graphql"
REGULATED_COLLECTION_LABEL = "Reglerade behörigheter"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_bytes(url: str, accept: str = "application/json", timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def fetch_json(url: str, timeout: int = 180) -> tuple[bytes, Any]:
    body = fetch_bytes(url, timeout=timeout)
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
      concepts(type: "occupation-name", version: "{version}", limit: 10000) {{
        id
        preferred_label
        type
        essential(type: "skill") {{
          id
          preferred_label
          type
          related(type: "skill-collection") {{
            id
            preferred_label
            type
          }}
        }}
        optional(type: "skill") {{
          id
          preferred_label
          type
        }}
      }}
    }}'''

    gql_body, gql_doc, gql_url = graphql(query)
    gql_concepts = gql_doc.get("data", {}).get("concepts")
    if not isinstance(gql_concepts, list):
        raise RuntimeError("GraphQL response missing data.concepts")

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
    regulated_native_pairs: set[tuple[str, str]] = set()
    regulated_collection_ids: set[str] = set()

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
                if field == "essential":
                    collections = skill.get("related") or []
                    if not isinstance(collections, list):
                        raise RuntimeError(f"essential skill related field is not list for {sid}")
                    for collection in collections:
                        if not isinstance(collection, dict):
                            continue
                        if collection.get("preferred_label") == REGULATED_COLLECTION_LABEL:
                            regulated_native_pairs.add((oid, sid))
                            if collection.get("id"):
                                regulated_collection_ids.add(str(collection["id"]))

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

    comparison: dict[str, Any] = {}
    for field in relation_fields:
        native = native_pairs[field]
        kv = kv_pairs[field]
        comparison[field] = {
            "native_edges": len(native),
            "kv_edges": len(kv),
            "intersection_edges": len(native & kv),
            "native_only_edges": len(native - kv),
            "kv_only_edges": len(kv - native),
            "jaccard": round(len(native & kv) / len(native | kv), 6) if (native | kv) else 1.0,
        }

    regulated_comparison = {
        "native_regulated_essential_edges": len(regulated_native_pairs),
        "kv_regulated_edges": len(kv_pairs["regulated"]),
        "intersection_edges": len(regulated_native_pairs & kv_pairs["regulated"]),
        "native_only_edges": len(regulated_native_pairs - kv_pairs["regulated"]),
        "kv_only_edges": len(kv_pairs["regulated"] - regulated_native_pairs),
        "collection_ids": sorted(regulated_collection_ids),
    }

    aggregate = {
        "schema_version": 1,
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
        },
        "kv_invalid_occurrences": len(invalid_kv),
        "comparison_to_kv": comparison,
        "regulated_subset_comparison": regulated_comparison,
    }

    (out / "aggregate.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "anomalies.json").write_text(
        json.dumps(
            {
                "invalid_native": invalid_native,
                "invalid_kv": invalid_kv,
                "essential_native_only": sorted([list(x) for x in native_pairs["essential"] - kv_pairs["essential"]]),
                "essential_kv_only": sorted([list(x) for x in kv_pairs["essential"] - native_pairs["essential"]]),
                "optional_native_only": sorted([list(x) for x in native_pairs["optional"] - kv_pairs["optional"]]),
                "optional_kv_only": sorted([list(x) for x in kv_pairs["optional"] - native_pairs["optional"]]),
                "regulated_native_only": sorted([list(x) for x in regulated_native_pairs - kv_pairs["regulated"]]),
                "regulated_kv_only": sorted([list(x) for x in kv_pairs["regulated"] - regulated_native_pairs]),
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
        "## Exact directed-pair comparison to Kompetensväljaren",
        "",
        "| Field | native | KV | intersection | native-only | KV-only | Jaccard |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for field in relation_fields:
        row = comparison[field]
        lines.append(
            f"| `{field}` | {row['native_edges']:,} | {row['kv_edges']:,} | {row['intersection_edges']:,} | "
            f"{row['native_only_edges']:,} | {row['kv_only_edges']:,} | {row['jaccard']} |"
        )
    lines += [
        "",
        "## Regulated subset",
        "",
        f"Native essential edges whose skill is in `{REGULATED_COLLECTION_LABEL}`: **{regulated_comparison['native_regulated_essential_edges']:,}**.",
        f"KV regulated edges: **{regulated_comparison['kv_regulated_edges']:,}**.",
        f"Intersection: **{regulated_comparison['intersection_edges']:,}**; native-only: **{regulated_comparison['native_only_edges']:,}**; KV-only: **{regulated_comparison['kv_only_edges']:,}**.",
        "",
        "## Guardrails",
        "",
        "- `essential` and `optional` are native curated relation types, not generic relevance scores.",
        "- Similar KV field names are treated as a hypothesis until directed-pair equality is measured.",
        "- `regulated_skills` is tested as a subset hypothesis, not assumed from naming.",
        "- GraphQL is pinned to the explicit Taxonomy version and every identity is validated against the immutable v31 snapshot.",
        "",
    ]
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
