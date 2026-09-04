#!/usr/bin/env python3
"""Build a reproducible semantic-coverage inventory for JobTech Taxonomy.

The inventory is intentionally descriptive. It does not calculate a single
"semantic quality score": missing a definition, an alternative label, an SSYK
parent or an ESCO mapping are different facts with different meanings.

The script uses only Python's standard library so it can run locally or in CI.
It writes:
  - concepts.jsonl      per-concept machine-readable rows
  - concepts.csv        flattened analysis table
  - aggregate.json      aggregate counts/coverage
  - gaps.csv            concepts with explicit missing dimensions
  - summary.md          human-readable report
  - source-manifest.json extraction metadata and warnings

Example:
    python scripts/semantic_coverage_inventory.py --version 31 \
        --output-dir artifacts/semantic-coverage-v31
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

API_BASE = "https://taxonomy.api.jobtechdev.se/v1/taxonomy"
REST_CONCEPTS_URL = f"{API_BASE}/main/concepts"
GRAPHQL_URL = f"{API_BASE}/graphql"

TARGET_TYPES = ("occupation-name", "skill", "job-title", "keyword")
DEFAULT_PAGE_SIZE = 500
USER_AGENT = "semantic-taxonomy-search-coverage-inventory/0.1"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def first_present(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default


def key_present(mapping: dict[str, Any], *keys: str) -> bool:
    return any(key in mapping for key in keys)


def list_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def fetch_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 90,
    retries: int = 3,
) -> Any:
    data = None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_error: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def fetch_concepts_rest(
    concept_type: str,
    version: str,
    warnings: list[str],
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Fetch concepts with offset pagination and defensive de-duplication."""
    by_id: dict[str, dict[str, Any]] = {}
    offset = 0
    previous_signature: tuple[str, ...] | None = None

    while True:
        query = urllib.parse.urlencode(
            {
                "type": concept_type,
                "version": version,
                "limit": page_size,
                "offset": offset,
            }
        )
        page = fetch_json(f"{REST_CONCEPTS_URL}?{query}")
        if not isinstance(page, list):
            raise RuntimeError(
                f"REST concepts response for {concept_type} was {type(page).__name__}, expected list"
            )

        ids = tuple(
            str(first_present(item, "taxonomy/id", "id", default=""))
            for item in page
            if isinstance(item, dict)
        )
        signature = ids[:10]
        if page and previous_signature is not None and signature == previous_signature:
            warnings.append(
                f"REST pagination repeated a page signature for {concept_type} at offset {offset}; "
                "stopped defensively."
            )
            break
        previous_signature = signature

        new_ids = 0
        for item in page:
            if not isinstance(item, dict):
                continue
            concept_id = str(first_present(item, "taxonomy/id", "id", default=""))
            if not concept_id:
                warnings.append(f"REST {concept_type} row without concept id at offset {offset}")
                continue
            if concept_id not in by_id:
                new_ids += 1
            by_id[concept_id] = item

        if len(page) < page_size:
            break
        if new_ids == 0:
            warnings.append(
                f"REST pagination yielded no new ids for {concept_type} at offset {offset}; stopped."
            )
            break
        offset += page_size

    return list(by_id.values())


def graphql(query: str) -> dict[str, Any]:
    result = fetch_json(GRAPHQL_URL, method="POST", payload={"query": query})
    if not isinstance(result, dict):
        raise RuntimeError(f"GraphQL response was {type(result).__name__}, expected object")
    if result.get("errors"):
        raise RuntimeError(json.dumps(result["errors"], ensure_ascii=False))
    data = result.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("GraphQL response missing data object")
    return data


def fetch_graphql_profiles(
    concept_type: str,
    version: str,
    relation_fields: str,
    warnings: list[str],
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, dict[str, Any]]:
    """Fetch relation profiles. GraphQL pagination is de-duplicated by ID.

    There was a historical Taxonomy API issue where a concept could occur on
    multiple GraphQL pages. We therefore never assume page uniqueness.
    """
    by_id: dict[str, dict[str, Any]] = {}
    offset = 0
    previous_signature: tuple[str, ...] | None = None

    while True:
        query = f'''query Coverage {{
          concepts(type: "{concept_type}", version: "{version}", limit: {page_size}, offset: {offset}) {{
            id
            type
            preferred_label
            {relation_fields}
          }}
        }}'''
        data = graphql(query)
        page = data.get("concepts") or []
        if not isinstance(page, list):
            raise RuntimeError(f"GraphQL concepts for {concept_type} was not a list")

        ids = tuple(str(item.get("id", "")) for item in page if isinstance(item, dict))
        signature = ids[:10]
        if page and previous_signature is not None and signature == previous_signature:
            warnings.append(
                f"GraphQL pagination repeated a page signature for {concept_type} at offset {offset}; "
                "stopped defensively."
            )
            break
        previous_signature = signature

        new_ids = 0
        for item in page:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            cid = str(item["id"])
            if cid not in by_id:
                new_ids += 1
            by_id[cid] = item

        if len(page) < page_size:
            break
        if new_ids == 0:
            warnings.append(
                f"GraphQL pagination yielded no new ids for {concept_type} at offset {offset}; stopped."
            )
            break
        offset += page_size

    return by_id


OCCUPATION_RELATION_FIELDS = """
related(type: ["job-title", "keyword"]) { id type preferred_label }
broader(type: ["ssyk-level-4", "isco-level-4"]) { id type preferred_label }
essential(type: "skill") { id type preferred_label }
optional(type: "skill") { id type preferred_label }
exact_match(type: "esco-occupation") { id type preferred_label }
broad_match(type: "esco-occupation") { id type preferred_label }
narrow_match(type: "esco-occupation") { id type preferred_label }
close_match(type: "esco-occupation") { id type preferred_label }
substituted_by(type: "occupation-name") { id type preferred_label }
substitutes(type: "occupation-name") { id type preferred_label }
"""

SKILL_RELATION_FIELDS = """
broader { id type preferred_label }
related { id type preferred_label }
exact_match(type: "esco-skill") { id type preferred_label }
broad_match(type: "esco-skill") { id type preferred_label }
narrow_match(type: "esco-skill") { id type preferred_label }
close_match(type: "esco-skill") { id type preferred_label }
"""

JOB_TITLE_RELATION_FIELDS = """
related(type: "occupation-name") { id type preferred_label }
"""

KEYWORD_RELATION_FIELDS = """
related(type: "occupation-name") { id type preferred_label }
"""


def relation_count(profile: dict[str, Any] | None, field: str, *, target_type: str | None = None) -> int:
    if not profile:
        return 0
    values = list_value(profile.get(field))
    if target_type is None:
        return len(values)
    return sum(1 for item in values if isinstance(item, dict) and item.get("type") == target_type)


def base_row(raw: dict[str, Any], version: str) -> dict[str, Any]:
    concept_id = str(first_present(raw, "taxonomy/id", "id", default=""))
    concept_type = str(first_present(raw, "taxonomy/type", "type", default=""))
    label = str(first_present(raw, "taxonomy/preferred-label", "preferred_label", default="") or "")
    definition = str(first_present(raw, "taxonomy/definition", "definition", default="") or "")
    alt_labels = list_value(
        first_present(raw, "taxonomy/alternative-labels", "alternative_labels", default=[])
    )
    hidden_labels = list_value(
        first_present(raw, "taxonomy/hidden-labels", "hidden_labels", default=[])
    )
    quality = first_present(raw, "taxonomy/quality-level", "quality_level", default=None)
    deprecated_present = key_present(raw, "taxonomy/deprecated", "deprecated")
    deprecated_value = first_present(raw, "taxonomy/deprecated", "deprecated", default=None)
    relation_meta = first_present(raw, "taxonomy/relations", "relations", default={})
    if not isinstance(relation_meta, dict):
        relation_meta = {}

    normalized_label = normalize_text(label)
    normalized_definition = normalize_text(definition)
    definition_nonempty = bool(normalized_definition)
    definition_distinct = bool(normalized_definition and normalized_definition != normalized_label)

    return {
        "taxonomy_version": version,
        "id": concept_id,
        "type": concept_type,
        "preferred_label": label,
        "definition": definition,
        "definition_nonempty": definition_nonempty,
        "definition_distinct_from_label": definition_distinct,
        "definition_same_as_label": bool(normalized_definition and normalized_definition == normalized_label),
        "definition_chars": len(definition.strip()),
        "alternative_labels": [str(v) for v in alt_labels if v is not None],
        "alternative_label_count": len([v for v in alt_labels if str(v).strip()]),
        "hidden_labels": [str(v) for v in hidden_labels if v is not None],
        "hidden_label_count": len([v for v in hidden_labels if str(v).strip()]),
        "quality_level": quality,
        "quality_level_present": quality is not None,
        "deprecated_field_present": deprecated_present,
        "deprecated": deprecated_value,
        "rest_relation_counts": relation_meta,
    }


def enrich_relations(row: dict[str, Any], profile: dict[str, Any] | None) -> None:
    ctype = row["type"]
    if ctype == "occupation-name":
        row.update(
            {
                "job_title_count": relation_count(profile, "related", target_type="job-title"),
                "keyword_count": relation_count(profile, "related", target_type="keyword"),
                "ssyk_level_4_parent_count": relation_count(profile, "broader", target_type="ssyk-level-4"),
                "isco_level_4_parent_count": relation_count(profile, "broader", target_type="isco-level-4"),
                "essential_skill_count": relation_count(profile, "essential"),
                "optional_skill_count": relation_count(profile, "optional"),
                "esco_exact_match_count": relation_count(profile, "exact_match"),
                "esco_broad_match_count": relation_count(profile, "broad_match"),
                "esco_narrow_match_count": relation_count(profile, "narrow_match"),
                "esco_close_match_count": relation_count(profile, "close_match"),
                "substituted_by_count": relation_count(profile, "substituted_by"),
                "substitutes_count": relation_count(profile, "substitutes"),
            }
        )
    elif ctype == "skill":
        row.update(
            {
                "broader_relation_count": relation_count(profile, "broader"),
                "related_relation_count": relation_count(profile, "related"),
                "esco_exact_match_count": relation_count(profile, "exact_match"),
                "esco_broad_match_count": relation_count(profile, "broad_match"),
                "esco_narrow_match_count": relation_count(profile, "narrow_match"),
                "esco_close_match_count": relation_count(profile, "close_match"),
            }
        )
    elif ctype in {"job-title", "keyword"}:
        row["occupation_name_relation_count"] = relation_count(
            profile, "related", target_type="occupation-name"
        )


def mapping_total(row: dict[str, Any]) -> int:
    return sum(
        int(row.get(field, 0) or 0)
        for field in (
            "esco_exact_match_count",
            "esco_broad_match_count",
            "esco_narrow_match_count",
            "esco_close_match_count",
        )
    )


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"total": len(rows), "by_type": {}}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["type"]].append(row)

    for ctype, items in sorted(grouped.items()):
        quality = Counter(str(r["quality_level"]) for r in items if r.get("quality_level_present"))
        relation_fields = sorted(
            {
                key
                for r in items
                for key, value in r.items()
                if key.endswith("_count") and key not in {"alternative_label_count", "hidden_label_count"}
            }
        )
        relation_coverage = {
            field: {
                "concepts_with_any": sum(1 for r in items if int(r.get(field, 0) or 0) > 0),
                "total_edges": sum(int(r.get(field, 0) or 0) for r in items),
            }
            for field in relation_fields
        }
        result["by_type"][ctype] = {
            "total": len(items),
            "definition_nonempty": sum(bool(r.get("definition_nonempty")) for r in items),
            "definition_distinct_from_label": sum(
                bool(r.get("definition_distinct_from_label")) for r in items
            ),
            "definition_same_as_label": sum(bool(r.get("definition_same_as_label")) for r in items),
            "with_alternative_labels": sum(int(r.get("alternative_label_count", 0)) > 0 for r in items),
            "with_hidden_labels": sum(int(r.get("hidden_label_count", 0)) > 0 for r in items),
            "quality_level_present": sum(bool(r.get("quality_level_present")) for r in items),
            "quality_level_distribution": dict(sorted(quality.items())),
            "deprecated_true": sum(r.get("deprecated") is True for r in items),
            "deprecated_field_present": sum(bool(r.get("deprecated_field_present")) for r in items),
            "with_any_esco_mapping": sum(mapping_total(r) > 0 for r in items),
            "relation_coverage": relation_coverage,
        }
    return result


def missing_dimensions(row: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not row.get("definition_distinct_from_label"):
        missing.append("distinct_definition")
    if int(row.get("alternative_label_count", 0) or 0) == 0:
        missing.append("alternative_labels")

    if row["type"] == "occupation-name":
        if int(row.get("job_title_count", 0) or 0) == 0:
            missing.append("job_titles")
        if int(row.get("keyword_count", 0) or 0) == 0:
            missing.append("keywords")
        if int(row.get("ssyk_level_4_parent_count", 0) or 0) == 0:
            missing.append("ssyk_level_4_parent")
        if int(row.get("essential_skill_count", 0) or 0) + int(row.get("optional_skill_count", 0) or 0) == 0:
            missing.append("native_skill_relations")
        if mapping_total(row) == 0:
            missing.append("esco_mapping")
    elif row["type"] == "skill":
        if mapping_total(row) == 0:
            missing.append("esco_mapping")
        if int(row.get("broader_relation_count", 0) or 0) + int(row.get("related_relation_count", 0) or 0) == 0:
            missing.append("native_graph_context")
    elif row["type"] in {"job-title", "keyword"}:
        if int(row.get("occupation_name_relation_count", 0) or 0) == 0:
            missing.append("occupation_name_relation")
    return missing


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def pct(numerator: int, denominator: int) -> str:
    if not denominator:
        return "n/a"
    return f"{100 * numerator / denominator:.1f}%"


def build_summary(aggregate: dict[str, Any], warnings: list[str], version: str, generated_at: str) -> str:
    lines = [
        f"# Semantic Coverage Inventory — taxonomy v{version}",
        "",
        f"Generated: `{generated_at}`",
        "",
        "This report describes coverage. It does not assign a single semantic-quality score.",
        "",
    ]

    for ctype, stats in aggregate.get("by_type", {}).items():
        total = int(stats["total"])
        lines.extend(
            [
                f"## {ctype}",
                "",
                f"- Concepts: **{total}**",
                f"- Non-empty definition field: **{stats['definition_nonempty']}** ({pct(stats['definition_nonempty'], total)})",
                f"- Definition distinct from preferred label: **{stats['definition_distinct_from_label']}** ({pct(stats['definition_distinct_from_label'], total)})",
                f"- Definition equal to preferred label: **{stats['definition_same_as_label']}** ({pct(stats['definition_same_as_label'], total)})",
                f"- At least one alternative label: **{stats['with_alternative_labels']}** ({pct(stats['with_alternative_labels'], total)})",
                f"- At least one hidden label: **{stats['with_hidden_labels']}** ({pct(stats['with_hidden_labels'], total)})",
                f"- Quality-level present: **{stats['quality_level_present']}** ({pct(stats['quality_level_present'], total)})",
                f"- At least one ESCO mapping: **{stats['with_any_esco_mapping']}** ({pct(stats['with_any_esco_mapping'], total)})",
                "",
            ]
        )
        if stats.get("quality_level_distribution"):
            lines.append(
                "Quality-level distribution: `"
                + json.dumps(stats["quality_level_distribution"], ensure_ascii=False, sort_keys=True)
                + "`"
            )
            lines.append("")
        if stats.get("relation_coverage"):
            lines.append("### Relation coverage")
            lines.append("")
            lines.append("| Relation dimension | concepts with any | coverage | edges |")
            lines.append("|---|---:|---:|---:|")
            for field, rel in stats["relation_coverage"].items():
                lines.append(
                    f"| `{field}` | {rel['concepts_with_any']} | {pct(rel['concepts_with_any'], total)} | {rel['total_edges']} |"
                )
            lines.append("")

    if warnings:
        lines.extend(["## Extraction warnings", ""])
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
    else:
        lines.extend(["## Extraction warnings", "", "None.", ""])

    lines.extend(
        [
            "## Interpretation guardrails",
            "",
            "- `definition_nonempty` is not the same as a real description; the important hard measure is `definition_distinct_from_label`.",
            "- A graph edge only means the documented relation type. It does not imply synonymy.",
            "- ESCO broad/narrow/close/exact mappings are deliberately counted separately in the raw per-concept output.",
            "- Behavioural and corpus-derived AF datasets are not included in this first native-taxonomy extraction; they are separate adapters in the research plan.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31", help="Taxonomy version to freeze (default: 31)")
    parser.add_argument(
        "--output-dir",
        default="artifacts/semantic-coverage-v31",
        help="Directory for generated inventory",
    )
    parser.add_argument(
        "--skip-graphql",
        action="store_true",
        help="Only inventory REST concept fields, without relation profiles",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version = str(args.version)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = utc_now()
    warnings: list[str] = []

    raw_by_type: dict[str, list[dict[str, Any]]] = {}
    for concept_type in TARGET_TYPES:
        print(f"Fetching REST concepts: {concept_type} v{version}", flush=True)
        raw_by_type[concept_type] = fetch_concepts_rest(concept_type, version, warnings)
        print(f"  -> {len(raw_by_type[concept_type])} unique concepts", flush=True)

    profiles: dict[str, dict[str, dict[str, Any]]] = {ctype: {} for ctype in TARGET_TYPES}
    if not args.skip_graphql:
        graphql_specs = {
            "occupation-name": OCCUPATION_RELATION_FIELDS,
            "skill": SKILL_RELATION_FIELDS,
            "job-title": JOB_TITLE_RELATION_FIELDS,
            "keyword": KEYWORD_RELATION_FIELDS,
        }
        for concept_type, fields in graphql_specs.items():
            print(f"Fetching GraphQL relation profiles: {concept_type} v{version}", flush=True)
            try:
                profiles[concept_type] = fetch_graphql_profiles(
                    concept_type, version, fields, warnings
                )
                print(f"  -> {len(profiles[concept_type])} unique profiles", flush=True)
            except Exception as exc:  # preserve partial inventory instead of fabricating coverage
                warnings.append(f"GraphQL relation extraction failed for {concept_type}: {exc}")
                print(f"  !! GraphQL profile failed: {exc}", file=sys.stderr, flush=True)

    rows: list[dict[str, Any]] = []
    for concept_type in TARGET_TYPES:
        for raw in raw_by_type[concept_type]:
            row = base_row(raw, version)
            profile = profiles.get(concept_type, {}).get(row["id"])
            row["graphql_profile_present"] = profile is not None
            enrich_relations(row, profile)
            row["esco_mapping_count"] = mapping_total(row)
            row["missing_dimensions"] = missing_dimensions(row)
            rows.append(row)

    rows.sort(key=lambda r: (r.get("type", ""), normalize_text(r.get("preferred_label")), r.get("id", "")))
    aggregate = aggregate_rows(rows)

    write_jsonl(output_dir / "concepts.jsonl", rows)
    write_csv(output_dir / "concepts.csv", rows)
    write_json(output_dir / "aggregate.json", aggregate)

    gap_rows = [
        {
            "id": row["id"],
            "type": row["type"],
            "preferred_label": row["preferred_label"],
            "missing_dimension_count": len(row["missing_dimensions"]),
            "missing_dimensions": row["missing_dimensions"],
        }
        for row in rows
        if row["missing_dimensions"]
    ]
    gap_rows.sort(
        key=lambda r: (-int(r["missing_dimension_count"]), r["type"], normalize_text(r["preferred_label"]))
    )
    write_csv(output_dir / "gaps.csv", gap_rows)

    manifest = {
        "schema_version": 1,
        "generated_at": generated_at,
        "taxonomy_version": version,
        "api_base": API_BASE,
        "target_types": list(TARGET_TYPES),
        "script": "scripts/semantic_coverage_inventory.py",
        "python": sys.version,
        "warnings": warnings,
        "sources": [
            {
                "name": "JobTech Taxonomy REST concepts",
                "url": REST_CONCEPTS_URL,
                "semantics": "canonical concept text/metadata",
            },
            {
                "name": "JobTech Taxonomy GraphQL",
                "url": GRAPHQL_URL,
                "semantics": "typed taxonomy relation coverage",
                "enabled": not args.skip_graphql,
            },
        ],
    }
    write_json(output_dir / "source-manifest.json", manifest)

    summary = build_summary(aggregate, warnings, version, generated_at)
    (output_dir / "summary.md").write_text(summary, encoding="utf-8")

    print("\n" + summary, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
