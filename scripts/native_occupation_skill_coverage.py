#!/usr/bin/env python3
"""Measure native v31 occupation->skill relations and exact KV projections."""

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

USER_AGENT = "semantic-taxonomy-search-native-occ-skill/0.3"
GRAPHQL_URL = "https://taxonomy.api.jobtechdev.se/v1/taxonomy/graphql"
REGULATED_COLLECTION_LABEL = "Reglerande behörigheter"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str, timeout: int = 180) -> tuple[bytes, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
    return body, json.loads(body)


def graphql(query: str) -> tuple[bytes, Any, str]:
    url = GRAPHQL_URL + "?" + urllib.parse.urlencode({"query": query})
    body, doc = fetch_json(url)
    if not isinstance(doc, dict) or doc.get("errors"):
        raise RuntimeError(f"GraphQL error: {json.dumps(doc, ensure_ascii=False)[:2000]}")
    return body, doc, url


def pct(n: int, d: int) -> float | None:
    return None if not d else round(100.0 * n / d, 3)


def compare(left: set[tuple[str, str]], right: set[tuple[str, str]]) -> dict[str, Any]:
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--output-dir", default="artifacts/native-occupation-skill-v31")
    args = ap.parse_args()
    version = str(args.version)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    taxonomy_url = (
        f"https://data.jobtechdev.se/taxonomy/version/{version}/query/"
        "concepts-and-common-relations/concepts-and-common-relations.json"
    )
    kv_url = f"https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t{version}.json"
    taxonomy_body, taxonomy = fetch_json(taxonomy_url)
    kv_body, kv = fetch_json(kv_url)

    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy snapshot missing data.concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids_by_type: dict[str, set[str]] = defaultdict(set)
    for cid, c in by_id.items():
        ids_by_type[str(c.get("type") or "")].add(cid)
    occupations = ids_by_type["occupation-name"]
    skills = ids_by_type["skill"]

    query = f'''query NativeOccupationSkills {{
      occupations: concepts(type: "occupation-name", version: "{version}", limit: 10000) {{
        id preferred_label type
        essential(type: "skill") {{ id preferred_label type }}
        optional(type: "skill") {{ id preferred_label type }}
      }}
      skill_collections: concepts(type: "skill-collection", version: "{version}", limit: 1000) {{
        id preferred_label type
        related(type: "skill") {{ id preferred_label type }}
      }}
    }}'''
    gql_body, gql, gql_url = graphql(query)
    data = gql.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("GraphQL response missing data")
    gql_occupations = data.get("occupations")
    collections = data.get("skill_collections")
    if not isinstance(gql_occupations, list) or not isinstance(collections, list):
        raise RuntimeError("GraphQL response missing expected lists")

    gql_ids = {str(c.get("id")) for c in gql_occupations if isinstance(c, dict) and c.get("id")}
    if gql_ids != occupations:
        raise RuntimeError(
            f"GraphQL occupation universe drift: missing={len(occupations-gql_ids)} extra={len(gql_ids-occupations)}"
        )

    native: dict[str, set[tuple[str, str]]] = {"essential": set(), "optional": set()}
    native_skill_ids: dict[str, set[str]] = {"essential": set(), "optional": set()}
    nonempty = Counter()
    invalid_native: list[dict[str, str]] = []
    for occ in gql_occupations:
        if not isinstance(occ, dict):
            continue
        oid = str(occ.get("id") or "")
        for field in ("essential", "optional"):
            rels = occ.get(field) or []
            if not isinstance(rels, list):
                raise RuntimeError(f"{field} is not list for {oid}")
            if rels:
                nonempty[field] += 1
            for skill in rels:
                if not isinstance(skill, dict) or not skill.get("id"):
                    continue
                sid = str(skill["id"])
                native[field].add((oid, sid))
                native_skill_ids[field].add(sid)
                canonical = by_id.get(sid)
                if canonical is None or canonical.get("type") != "skill" or skill.get("type") != "skill":
                    invalid_native.append({"source_id": oid, "field": field, "target_id": sid})

    matching = [
        c for c in collections
        if isinstance(c, dict) and c.get("preferred_label") == REGULATED_COLLECTION_LABEL
    ]
    if len(matching) != 1:
        labels = sorted(str(c.get("preferred_label")) for c in collections if isinstance(c, dict))
        raise RuntimeError(f"expected one regulated collection; got {len(matching)}; labels={labels}")
    regulated_collection = matching[0]
    related = regulated_collection.get("related") or []
    if not isinstance(related, list):
        raise RuntimeError("regulated collection related is not list")
    regulated_skill_ids = {
        str(s["id"]) for s in related if isinstance(s, dict) and s.get("id")
    }
    invalid_collection = sorted(regulated_skill_ids - skills)
    regulated_native = {pair for pair in native["essential"] if pair[1] in regulated_skill_ids}
    nonregulated_native = native["essential"] - regulated_native

    kv_data = kv.get("data")
    if not isinstance(kv_data, dict):
        raise RuntimeError("KV missing data")
    declared_version = str(kv.get("metadata", {}).get("labour_market_taxonomy_version") or "")
    if version not in declared_version:
        raise RuntimeError(f"KV version mismatch: {declared_version!r}")
    field_map = {
        "essential": "essential_skills",
        "optional": "optional_skills",
        "regulated": "regulated_skills",
    }
    kv_pairs: dict[str, set[tuple[str, str]]] = {k: set() for k in field_map}
    invalid_kv: list[dict[str, str]] = []
    for oid, record in kv_data.items():
        if not isinstance(record, dict) or record.get("type") != "occupation-name":
            continue
        for semantic, field in field_map.items():
            mapping = record.get(field) or {}
            if not isinstance(mapping, dict):
                raise RuntimeError(f"KV {field} is not object for {oid}")
            for sid_value in mapping.values():
                sid = str(sid_value or "")
                if not sid:
                    continue
                kv_pairs[semantic].add((oid, sid))
                if oid not in occupations or sid not in skills:
                    invalid_kv.append({"source_id": oid, "field": field, "target_id": sid})

    comparisons = {
        "optional_native_vs_kv_optional": compare(native["optional"], kv_pairs["optional"]),
        "essential_native_vs_kv_essential": compare(native["essential"], kv_pairs["essential"]),
        "native_regulated_essential_vs_kv_regulated": compare(regulated_native, kv_pairs["regulated"]),
        "native_nonregulated_essential_vs_kv_essential": compare(nonregulated_native, kv_pairs["essential"]),
        "native_essential_vs_kv_essential_plus_regulated": compare(
            native["essential"], kv_pairs["essential"] | kv_pairs["regulated"]
        ),
    }

    aggregate = {
        "schema_version": 3,
        "taxonomy_version": version,
        "generated_at": now_utc(),
        "sources": {
            "taxonomy_snapshot": {"url": taxonomy_url, "bytes": len(taxonomy_body), "sha256": hashlib.sha256(taxonomy_body).hexdigest()},
            "taxonomy_graphql": {"url": gql_url, "response_bytes": len(gql_body), "response_sha256": hashlib.sha256(gql_body).hexdigest(), "explicit_version": version},
            "kompetensvaljaren": {"url": kv_url, "bytes": len(kv_body), "sha256": hashlib.sha256(kv_body).hexdigest(), "declared_taxonomy_version": declared_version},
        },
        "native": {
            "occupation_sources": len(gql_ids),
            "active_occupation_universe": len(occupations),
            "invalid_relation_occurrences": len(invalid_native),
            "fields": {
                field: {
                    "sources_nonempty": nonempty[field],
                    "source_coverage_pct": pct(nonempty[field], len(occupations)),
                    "edge_count": len(native[field]),
                    "unique_skill_ids": len(native_skill_ids[field]),
                    "active_skill_coverage_pct": pct(len(native_skill_ids[field] & skills), len(skills)),
                }
                for field in ("essential", "optional")
            },
            "regulated_collection": {
                "id": regulated_collection.get("id"),
                "preferred_label": regulated_collection.get("preferred_label"),
                "related_active_skill_ids": len(regulated_skill_ids & skills),
                "invalid_target_ids": len(invalid_collection),
                "essential_edges_using_regulated_skill": len(regulated_native),
                "nonregulated_essential_edges": len(nonregulated_native),
            },
        },
        "kv_invalid_occurrences": len(invalid_kv),
        "comparison_to_kv": comparisons,
    }
    (out / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "anomalies.json").write_text(json.dumps({
        "invalid_native": invalid_native,
        "invalid_regulated_collection_targets": invalid_collection,
        "invalid_kv": invalid_kv,
        "native_essential_not_in_kv_union": sorted([list(x) for x in native["essential"] - (kv_pairs["essential"] | kv_pairs["regulated"])]),
        "kv_essential_regulated_not_native": sorted([list(x) for x in (kv_pairs["essential"] | kv_pairs["regulated"]) - native["essential"]]),
        "native_optional_not_kv": sorted([list(x) for x in native["optional"] - kv_pairs["optional"]]),
        "kv_optional_not_native": sorted([list(x) for x in kv_pairs["optional"] - native["optional"]]),
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"# Native occupation→skill coverage — taxonomy v{version}", "",
        f"GraphQL occupation universe: **{len(gql_ids):,} / {len(occupations):,}** active occupations.", "",
        "| Native field | non-empty occupations | coverage | edges | unique skills | active skill coverage |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for field in ("essential", "optional"):
        row = aggregate["native"]["fields"][field]
        lines.append(f"| `{field}` | {row['sources_nonempty']:,} | {row['source_coverage_pct']}% | {row['edge_count']:,} | {row['unique_skill_ids']:,} | {row['active_skill_coverage_pct']}% |")
    lines += [
        "", "## KV relationship", "",
        f"Collection `{regulated_collection.get('preferred_label')}` ({regulated_collection.get('id')}) contains **{len(regulated_skill_ids):,}** active skill IDs.",
        f"Native essential edges targeting that collection: **{len(regulated_native):,}**.", "",
        "| Comparison | left | right | intersection | left-only | right-only | exact |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for name, row in comparisons.items():
        lines.append(f"| `{name}` | {row['left_edges']:,} | {row['right_edges']:,} | {row['intersection_edges']:,} | {row['left_only_edges']:,} | {row['right_only_edges']:,} | {row['exact_equal']} |")
    lines += [
        "", "## Guardrails", "",
        "- Native `essential` / `optional` are curated taxonomy relation types, not relevance scores.",
        "- KV equivalence/partitioning is accepted only on exact directed-pair equality.",
        "- `regulated_skills` keeps its distinct KV name/provenance even if it partitions native `essential`.",
        "- GraphQL is pinned to explicit taxonomy version and identities are checked against immutable v31.", "",
    ]
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
