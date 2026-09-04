#!/usr/bin/env python3
"""Measure v31 keyword/search-concept and occupation substitutability semantics.

These distributions are deliberately kept separate from the common-relations
snapshot because they answer different questions:

* keyword-concepts-with-relations tells us which canonical domains the 1,484
  keyword concepts actually point to. A keyword is not assumed to be YV/KV
  vocabulary merely because its type is named `keyword`.
* substitutability-relations-between-occupations carries the curated 25/75
  relation strength that the common relation ID lists do not express.

The extractor validates every relation target against the same immutable v31
active concept snapshot used by the rest of Gate 1.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

USER_AGENT = "semantic-taxonomy-search-special-relations/0.1"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str, timeout: int = 180) -> tuple[bytes, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
    return body, json.loads(body)


def pct(n: int, d: int) -> float | None:
    return None if not d else round(100.0 * n / d, 3)


def concept_list(document: Any) -> list[dict[str, Any]]:
    concepts = document.get("data", {}).get("concepts") if isinstance(document, dict) else None
    if not isinstance(concepts, list):
        raise RuntimeError("source missing data.concepts list")
    return [c for c in concepts if isinstance(c, dict)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31")
    parser.add_argument("--output-dir", default="artifacts/taxonomy-special-relations-v31")
    args = parser.parse_args()

    version = str(args.version)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    keyword_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/keyword-concepts-with-relations/keyword-concepts-with-relations.json"
    )
    substitutability_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/substitutability-relations-between-occupations/"
        "substitutability-relations-between-occupations.json"
    )

    taxonomy_body, taxonomy_doc = fetch_json(taxonomy_url)
    keyword_body, keyword_doc = fetch_json(keyword_url)
    substitutability_body, substitutability_doc = fetch_json(substitutability_url)

    active = concept_list(taxonomy_doc)
    by_id = {str(c.get("id")): c for c in active if c.get("id")}
    ids_by_type: dict[str, set[str]] = defaultdict(set)
    for cid, concept in by_id.items():
        ids_by_type[str(concept.get("type") or "")].add(cid)

    # ---------------------------------------------------------------- keyword
    keyword_concepts = concept_list(keyword_doc)
    keyword_ids = {str(c.get("id")) for c in keyword_concepts if c.get("id")}
    wrong_keyword_type: list[str] = []
    unknown_keyword_ids: list[str] = []
    target_type_edges = Counter()
    keywords_with_target_type: dict[str, set[str]] = defaultdict(set)
    target_ids_by_type: dict[str, set[str]] = defaultdict(set)
    unknown_targets: list[dict[str, str]] = []
    keyword_relation_counts: list[int] = []

    for keyword in keyword_concepts:
        kid = str(keyword.get("id") or "")
        canonical = by_id.get(kid)
        if canonical is None:
            unknown_keyword_ids.append(kid)
        elif canonical.get("type") != "keyword":
            wrong_keyword_type.append(kid)
        related = keyword.get("related") or []
        if not isinstance(related, list):
            raise RuntimeError(f"keyword {kid} related field is not a list")
        keyword_relation_counts.append(len(related))
        for target in related:
            if not isinstance(target, dict) or not target.get("id"):
                continue
            tid = str(target["id"])
            canonical_target = by_id.get(tid)
            if canonical_target is None:
                unknown_targets.append({"keyword_id": kid, "target_id": tid})
                ttype = str(target.get("type") or "UNKNOWN")
            else:
                ttype = str(canonical_target.get("type") or "")
            target_type_edges[ttype] += 1
            keywords_with_target_type[ttype].add(kid)
            target_ids_by_type[ttype].add(tid)

    direct_target_types = ("occupation-name", "job-title", "skill")
    direct_keyword = {}
    for ttype in direct_target_types:
        direct_keyword[ttype] = {
            "source_keywords": len(keywords_with_target_type.get(ttype, set())),
            "source_keyword_pct": pct(len(keywords_with_target_type.get(ttype, set())), len(keyword_concepts)),
            "edges": target_type_edges.get(ttype, 0),
            "unique_target_ids": len(target_ids_by_type.get(ttype, set())),
            "target_space_coverage_pct": pct(
                len(target_ids_by_type.get(ttype, set()) & ids_by_type.get(ttype, set())),
                len(ids_by_type.get(ttype, set())),
            ),
        }

    # -------------------------------------------------------- substitutability
    occupation_concepts = concept_list(substitutability_doc)
    active_occupations = ids_by_type.get("occupation-name", set())
    source_ids = {str(c.get("id")) for c in occupation_concepts if c.get("id")}
    relation_fields = ("substituted_by", "substitutes")
    source_nonempty = Counter()
    edge_counts = Counter()
    strength_counts: dict[str, Counter[int]] = {field: Counter() for field in relation_fields}
    unique_directed_edges: dict[str, set[tuple[str, str, int]]] = {field: set() for field in relation_fields}
    target_ids: dict[str, set[str]] = {field: set() for field in relation_fields}
    invalid_relations: list[dict[str, str]] = []

    for concept in occupation_concepts:
        source_id = str(concept.get("id") or "")
        for field in relation_fields:
            relations = concept.get(field) or []
            if not isinstance(relations, list):
                raise RuntimeError(f"{field} for {source_id} is not a list")
            if relations:
                source_nonempty[field] += 1
            for relation in relations:
                if not isinstance(relation, dict) or not relation.get("id"):
                    continue
                target_id = str(relation["id"])
                try:
                    strength = int(relation.get("substitutability_percentage"))
                except (TypeError, ValueError):
                    strength = -1
                edge_counts[field] += 1
                strength_counts[field][strength] += 1
                unique_directed_edges[field].add((source_id, target_id, strength))
                target_ids[field].add(target_id)
                source_ok = source_id in active_occupations
                target_ok = target_id in active_occupations
                if not source_ok or not target_ok or relation.get("type") != "occupation-name":
                    invalid_relations.append({
                        "field": field,
                        "source_id": source_id,
                        "target_id": target_id,
                        "relation_type": str(relation.get("type")),
                    })

    # Relation reciprocity is informational only; the two fields have different
    # direction semantics and are not forced to be identical.
    substitutes_pairs = {(s, t, p) for s, t, p in unique_directed_edges["substitutes"]}
    substituted_by_reverse = {(t, s, p) for s, t, p in unique_directed_edges["substituted_by"]}
    reciprocal_overlap = substitutes_pairs & substituted_by_reverse

    aggregate = {
        "schema_version": 1,
        "taxonomy_version": version,
        "generated_at": now_utc(),
        "sources": {
            "taxonomy": {"url": taxonomy_url, "bytes": len(taxonomy_body), "sha256": hashlib.sha256(taxonomy_body).hexdigest()},
            "keyword_concepts": {"url": keyword_url, "bytes": len(keyword_body), "sha256": hashlib.sha256(keyword_body).hexdigest()},
            "substitutability": {"url": substitutability_url, "bytes": len(substitutability_body), "sha256": hashlib.sha256(substitutability_body).hexdigest()},
        },
        "keyword_concepts": {
            "concepts": len(keyword_concepts),
            "active_keyword_universe": len(ids_by_type.get("keyword", set())),
            "coverage_pct": pct(len(keyword_ids & ids_by_type.get("keyword", set())), len(ids_by_type.get("keyword", set()))),
            "unknown_keyword_ids": len(unknown_keyword_ids),
            "wrong_keyword_types": len(wrong_keyword_type),
            "unknown_relation_targets": len(unknown_targets),
            "total_related_edges": sum(target_type_edges.values()),
            "target_type_edges": dict(target_type_edges.most_common()),
            "keywords_with_target_type": {k: len(v) for k, v in sorted(keywords_with_target_type.items())},
            "direct_yv_kv_targets": direct_keyword,
            "relation_count": {
                "min": min(keyword_relation_counts) if keyword_relation_counts else None,
                "max": max(keyword_relation_counts) if keyword_relation_counts else None,
                "zero": sum(v == 0 for v in keyword_relation_counts),
            },
        },
        "substitutability": {
            "concepts": len(occupation_concepts),
            "active_occupation_universe": len(active_occupations),
            "source_coverage_pct": pct(len(source_ids & active_occupations), len(active_occupations)),
            "invalid_relation_occurrences": len(invalid_relations),
            "fields": {
                field: {
                    "sources_nonempty": source_nonempty[field],
                    "source_coverage_pct": pct(source_nonempty[field], len(active_occupations)),
                    "edge_occurrences": edge_counts[field],
                    "unique_directed_edges_with_strength": len(unique_directed_edges[field]),
                    "unique_target_ids": len(target_ids[field]),
                    "strength_counts": {str(k): v for k, v in sorted(strength_counts[field].items())},
                }
                for field in relation_fields
            },
            "substitutes_vs_reverse_substituted_by_overlap": len(reciprocal_overlap),
            "substitutes_unique_edges": len(substitutes_pairs),
            "reverse_substituted_by_unique_edges": len(substituted_by_reverse),
        },
    }

    (out / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "keyword-target-types.json").write_text(json.dumps({
        "target_type_edges": dict(target_type_edges.most_common()),
        "keywords_with_target_type": {k: sorted(v) for k, v in sorted(keywords_with_target_type.items())},
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "anomalies.json").write_text(json.dumps({
        "unknown_keyword_ids": unknown_keyword_ids,
        "wrong_keyword_types": wrong_keyword_type,
        "unknown_keyword_relation_targets": unknown_targets,
        "invalid_substitutability_relations": invalid_relations,
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"# Taxonomy special relation coverage — v{version}",
        "",
        "## Keyword/search-concept view",
        "",
        f"Keyword concepts: **{len(keyword_concepts):,}** / **{len(ids_by_type.get('keyword', set())):,}** active.",
        "",
        "| Direct target space | source keywords | keyword share | edges | unique target IDs | target-space coverage |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for ttype in direct_target_types:
        row = direct_keyword[ttype]
        lines.append(
            f"| `{ttype}` | {row['source_keywords']:,} | {row['source_keyword_pct']}% | {row['edges']:,} | "
            f"{row['unique_target_ids']:,} | {row['target_space_coverage_pct']}% |"
        )
    lines += [
        "",
        "All relation target types, by edge count:",
        "",
        "```json",
        json.dumps(dict(target_type_edges.most_common()), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Occupation substitutability",
        "",
        f"Source concepts: **{len(occupation_concepts):,}** / **{len(active_occupations):,}** active occupation-name concepts.",
        "",
        "| Direction field | sources non-empty | coverage | edges | 25% | 75% |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for field in relation_fields:
        row = aggregate["substitutability"]["fields"][field]
        lines.append(
            f"| `{field}` | {row['sources_nonempty']:,} | {row['source_coverage_pct']}% | {row['edge_occurrences']:,} | "
            f"{row['strength_counts'].get('25', 0):,} | {row['strength_counts'].get('75', 0):,} |"
        )
    lines += [
        "",
        "## Guardrails",
        "",
        "- Keyword concepts are reported by typed target domain; the whole keyword vocabulary is never assumed to be YV/KV vocabulary.",
        "- A keyword→occupation or keyword→skill relation is recall evidence, not synonymy.",
        "- `substitutes` and `substituted_by` remain directional.",
        "- 25 and 75 are preserved as source semantics; neither means canonical equivalence.",
        "",
    ]
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
