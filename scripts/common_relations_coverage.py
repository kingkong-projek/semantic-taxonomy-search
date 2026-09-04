#!/usr/bin/env python3
"""Measure typed common-relation coverage in an immutable taxonomy version.

Uses Arbetsförmedlingen's versioned `concepts-and-common-relations` data file
as the reproducible graph backbone. Relation lists contain IDs, so this script
builds a complete ID -> concept metadata index first and only then classifies
relation targets. It never treats a generic relation name such as `related` as
having one fixed semantic meaning.

Outputs:
  concepts.jsonl       one row per occupation-name/skill/job-title/keyword
  aggregate.json       coverage by source type, relation and target type
  summary.md           human-readable report
  source-manifest.json exact URL/hash/bytes used
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

TARGET_TYPES = {"occupation-name", "skill", "job-title", "keyword"}
RELATION_FIELDS = (
    "broad_match",
    "broader",
    "close_match",
    "exact_match",
    "narrow_match",
    "narrower",
    "possible_combinations",
    "related",
    "replaced_by",
    "replaces",
    "substituted_by",
    "substitutes",
    "unlikely_combinations",
)
USER_AGENT = "semantic-taxonomy-search-common-relations-coverage/0.1"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def pct(n: int, d: int) -> str:
    return "n/a" if not d else f"{100*n/d:.1f}%"


def fetch_snapshot(version: str) -> tuple[str, bytes, list[dict[str, Any]]]:
    url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/"
        "concepts-and-common-relations.json"
    )
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        payload = response.read()
    document = json.loads(payload)
    concepts = document.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("snapshot does not contain data.concepts list")
    return url, payload, concepts


def relation_ids(concept: dict[str, Any], field: str) -> list[str]:
    value = concept.get(field)
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, dict) and item.get("id"):
            result.append(str(item["id"]))
        elif isinstance(item, str):
            result.append(item)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31")
    parser.add_argument("--output-dir", default="artifacts/common-relations-v31")
    args = parser.parse_args()

    version = str(args.version)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    generated_at = now_utc()

    url, payload, concepts = fetch_snapshot(version)
    digest = hashlib.sha256(payload).hexdigest()

    by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids: list[str] = []
    for concept in concepts:
        if not isinstance(concept, dict) or not concept.get("id"):
            continue
        cid = str(concept["id"])
        if cid in by_id:
            duplicate_ids.append(cid)
        by_id[cid] = concept

    target_concepts = [c for c in concepts if isinstance(c, dict) and c.get("type") in TARGET_TYPES]

    rows: list[dict[str, Any]] = []
    unresolved_target_ids: Counter[str] = Counter()
    aggregate_edges: Counter[tuple[str, str, str]] = Counter()
    concepts_with_relation: Counter[tuple[str, str, str]] = Counter()
    any_relation_field: Counter[tuple[str, str]] = Counter()

    for concept in target_concepts:
        source_type = str(concept["type"])
        row: dict[str, Any] = {
            "taxonomy_version": version,
            "id": str(concept["id"]),
            "type": source_type,
            "preferred_label": str(concept.get("preferred_label") or ""),
        }
        typed_counts: Counter[tuple[str, str]] = Counter()

        for relation in RELATION_FIELDS:
            ids = relation_ids(concept, relation)
            row[f"{relation}__total"] = len(ids)
            if ids:
                any_relation_field[(source_type, relation)] += 1

            for target_id in ids:
                target = by_id.get(target_id)
                if target is None:
                    target_type = "__unresolved__"
                    unresolved_target_ids[target_id] += 1
                else:
                    target_type = str(target.get("type") or "__missing_type__")
                typed_counts[(relation, target_type)] += 1
                aggregate_edges[(source_type, relation, target_type)] += 1

        for (relation, target_type), count in sorted(typed_counts.items()):
            row[f"{relation}__{target_type}"] = count
            concepts_with_relation[(source_type, relation, target_type)] += 1

        # Stable high-value semantic dimensions. Missing means measured zero,
        # because the full immutable common-relations graph was available.
        if source_type == "occupation-name":
            row["job_title_count"] = typed_counts[("related", "job-title")]
            row["keyword_count"] = typed_counts[("related", "keyword")]
            row["ssyk4_parent_count"] = typed_counts[("broader", "ssyk-level-4")]
            row["isco4_parent_count"] = typed_counts[("broader", "isco-level-4")]
            row["esco_exact_count"] = typed_counts[("exact_match", "esco-occupation")]
            row["esco_broad_count"] = typed_counts[("broad_match", "esco-occupation")]
            row["esco_narrow_count"] = typed_counts[("narrow_match", "esco-occupation")]
            row["esco_close_count"] = typed_counts[("close_match", "esco-occupation")]
            row["substituted_by_occupation_count"] = typed_counts[("substituted_by", "occupation-name")]
            row["substitutes_occupation_count"] = typed_counts[("substitutes", "occupation-name")]
        elif source_type == "skill":
            row["skill_headline_parent_count"] = typed_counts[("broader", "skill-headline")]
            row["ssyk4_related_count"] = typed_counts[("related", "ssyk-level-4")]
            row["esco_exact_count"] = typed_counts[("exact_match", "esco-skill")]
            row["esco_broad_count"] = typed_counts[("broad_match", "esco-skill")]
            row["esco_narrow_count"] = typed_counts[("narrow_match", "esco-skill")]
            row["esco_close_count"] = typed_counts[("close_match", "esco-skill")]
        elif source_type == "job-title":
            row["occupation_name_related_count"] = typed_counts[("related", "occupation-name")]
        elif source_type == "keyword":
            row["occupation_name_related_count"] = typed_counts[("related", "occupation-name")]
            row["skill_related_count"] = typed_counts[("related", "skill")]

        rows.append(row)

    rows.sort(key=lambda r: (r["type"], norm(r["preferred_label"]), r["id"]))
    totals = Counter(str(c["type"]) for c in target_concepts)

    relation_matrix: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
    for source_type in sorted(TARGET_TYPES):
        source_total = totals[source_type]
        by_relation: dict[str, dict[str, dict[str, int]]] = {}
        for relation in RELATION_FIELDS:
            target_types = sorted(
                {
                    target_type
                    for (src, rel, target_type), edge_count in aggregate_edges.items()
                    if src == source_type and rel == relation and edge_count > 0
                }
            )
            if not target_types and any_relation_field[(source_type, relation)] == 0:
                continue
            target_map: dict[str, dict[str, int]] = {}
            for target_type in target_types:
                target_map[target_type] = {
                    "concepts_with_any": concepts_with_relation[(source_type, relation, target_type)],
                    "edges": aggregate_edges[(source_type, relation, target_type)],
                }
            by_relation[relation] = {
                "__all_targets__": {
                    "concepts_with_any": any_relation_field[(source_type, relation)],
                    "edges": sum(
                        aggregate_edges[(source_type, relation, target_type)]
                        for target_type in target_types
                    ),
                },
                **target_map,
            }
        relation_matrix[source_type] = by_relation

    aggregate = {
        "schema_version": 1,
        "taxonomy_version": version,
        "generated_at": generated_at,
        "snapshot": {
            "url": url,
            "sha256": digest,
            "bytes": len(payload),
            "all_concepts": len(concepts),
            "unique_ids": len(by_id),
            "duplicate_id_count": len(duplicate_ids),
            "unresolved_relation_target_id_count": len(unresolved_target_ids),
            "unresolved_relation_edge_count": sum(unresolved_target_ids.values()),
        },
        "target_type_totals": dict(sorted(totals.items())),
        "relation_matrix": relation_matrix,
    }

    with (out / "concepts.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    (out / "aggregate.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "source-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "taxonomy_version": version,
                "retrieved_at": generated_at,
                "url": url,
                "sha256": digest,
                "bytes": len(payload),
                "dataset": "concepts-and-common-relations",
                "unresolved_relation_targets": dict(unresolved_target_ids.most_common()),
                "duplicate_ids": duplicate_ids,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    lines = [
        f"# Common relation coverage — taxonomy v{version}",
        "",
        f"Snapshot SHA-256: `{digest}`",
        f"All concepts in snapshot: **{len(concepts):,}**",
        f"Unique IDs: **{len(by_id):,}**",
        f"Unresolved relation target IDs: **{len(unresolved_target_ids):,}**",
        "",
        "Relation names are always reported together with target concept type. A `related` edge is not treated as one universal semantic relation.",
        "",
    ]

    high_value = {
        "occupation-name": [
            ("related", "job-title"),
            ("related", "keyword"),
            ("broader", "ssyk-level-4"),
            ("broader", "isco-level-4"),
            ("exact_match", "esco-occupation"),
            ("broad_match", "esco-occupation"),
            ("narrow_match", "esco-occupation"),
            ("close_match", "esco-occupation"),
            ("substituted_by", "occupation-name"),
            ("substitutes", "occupation-name"),
        ],
        "skill": [
            ("broader", "skill-headline"),
            ("related", "ssyk-level-4"),
            ("exact_match", "esco-skill"),
            ("broad_match", "esco-skill"),
            ("narrow_match", "esco-skill"),
            ("close_match", "esco-skill"),
        ],
        "job-title": [("related", "occupation-name")],
        "keyword": [("related", "occupation-name"), ("related", "skill")],
    }

    for source_type in ("occupation-name", "skill", "job-title", "keyword"):
        total = totals[source_type]
        lines.extend([f"## {source_type}", "", f"Concepts: **{total:,}**", ""])
        lines.append("| Relation | Target type | concepts with any | coverage | edges |")
        lines.append("|---|---|---:|---:|---:|")
        for relation, target_type in high_value[source_type]:
            cell = relation_matrix.get(source_type, {}).get(relation, {}).get(target_type, {})
            n = int(cell.get("concepts_with_any", 0))
            edges = int(cell.get("edges", 0))
            lines.append(f"| `{relation}` | `{target_type}` | {n:,} | {pct(n, total)} | {edges:,} |")
        lines.append("")

    lines.extend(
        [
            "## Guardrails",
            "",
            "- This distribution covers the common relation fields it publishes; absence here is a measured zero only for those fields.",
            "- `essential` and `optional` occupation→skill relations are not fields in this distribution and remain a separate adapter/gate.",
            "- Mapping relations (`exact`, `broad`, `narrow`, `close`) are never collapsed.",
            "- `related` is always interpreted together with source and target types.",
            "",
        ]
    )
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
