#!/usr/bin/env python3
"""Measure deprecated -> active compatibility for YV/KV taxonomy search.

Replacement relations are migration/history evidence, not synonym declarations.
The extractor builds the direct replaced_by graph locally and resolves each
relevant deprecated concept against an explicit active taxonomy version.

No deprecated concept is admitted to an active product destination by this tool.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GRAPHQL_URL = "https://taxonomy.api.jobtechdev.se/v1/taxonomy/graphql"
UA = "semantic-taxonomy-search-deprecated-compat/0.1"
TARGET_TYPES = ("occupation-name", "job-title", "skill", "keyword")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str, timeout: int = 180) -> tuple[bytes, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
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


def concept_list(document: Any) -> list[dict[str, Any]]:
    concepts = document.get("data", {}).get("concepts") if isinstance(document, dict) else None
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy snapshot missing data.concepts list")
    return [c for c in concepts if isinstance(c, dict)]


def as_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            candidate = item.get("label") or item.get("value") or item.get("preferred_label")
            if isinstance(candidate, str) and candidate.strip():
                result.append(candidate.strip())
    return result


def relation_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, dict) and item.get("id"):
            result.append(str(item["id"]))
        elif isinstance(item, str) and item:
            result.append(item)
    return result


@dataclass(frozen=True)
class Resolution:
    state: str
    active_targets: tuple[str, ...]
    max_depth: int
    paths: tuple[tuple[str, ...], ...]
    anomalies: tuple[str, ...]


def resolve_route(
    source_id: str,
    source_type: str,
    graph: dict[str, tuple[str, ...]],
    type_by_id: dict[str, str],
    deprecated_ids: set[str],
    active_ids: set[str],
) -> Resolution:
    active_targets: set[str] = set()
    paths: list[tuple[str, ...]] = []
    anomalies: set[str] = set()
    max_depth = 0

    def visit(current: str, path: tuple[str, ...]) -> None:
        nonlocal max_depth
        max_depth = max(max_depth, len(path) - 1)
        if current in path[:-1]:
            anomalies.add("cycle")
            paths.append(path)
            return

        if current != source_id and current in active_ids:
            current_type = type_by_id.get(current)
            if current_type != source_type:
                anomalies.add(f"type_mismatch:{current_type or 'UNKNOWN'}")
            else:
                active_targets.add(current)
            paths.append(path)
            return

        if current != source_id and current not in deprecated_ids:
            anomalies.add("missing_or_unknown_target")
            paths.append(path)
            return

        targets = graph.get(current, ())
        if not targets:
            paths.append(path)
            return

        for target in targets:
            target_type = type_by_id.get(target)
            if target_type is not None and target_type != source_type:
                anomalies.add(f"type_mismatch:{target_type}")
                paths.append(path + (target,))
                continue
            visit(target, path + (target,))

    visit(source_id, (source_id,))

    if any(a.startswith("type_mismatch:") for a in anomalies):
        state = "TYPE_MISMATCH"
    elif "cycle" in anomalies or "missing_or_unknown_target" in anomalies:
        state = "CYCLE_OR_INVALID"
    elif len(active_targets) == 1:
        state = "UNIQUE_ACTIVE_TARGET"
    elif len(active_targets) > 1:
        state = "MULTIPLE_ACTIVE_TARGETS"
    else:
        state = "NO_ACTIVE_TARGET"

    return Resolution(
        state=state,
        active_targets=tuple(sorted(active_targets)),
        max_depth=max_depth,
        paths=tuple(sorted(set(paths))),
        anomalies=tuple(sorted(anomalies)),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31")
    parser.add_argument("--output-dir", default="artifacts/deprecated-compatibility-v31")
    args = parser.parse_args()

    version = str(args.version)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    active_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    yv_url = f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{version}.json"

    active_body, active_doc = fetch_json(active_url)
    yv_body, yv_doc = fetch_json(yv_url)
    active = concept_list(active_doc)
    active_by_id = {str(c.get("id")): c for c in active if c.get("id")}
    active_ids = set(active_by_id)

    yv_rows = yv_doc.get("data") if isinstance(yv_doc, dict) else None
    if not isinstance(yv_rows, list):
        raise RuntimeError("YV data is not a list")
    yv_occ_ids = {
        str(row.get("id")) for row in yv_rows
        if isinstance(row, dict) and row.get("type") == "occupation-name" and row.get("id")
    }
    yv_job_ids = {
        str(row.get("id")) for row in yv_rows
        if isinstance(row, dict) and row.get("type") == "job-title" and row.get("id")
    }

    all_concepts: dict[str, dict[str, Any]] = {}
    query_sources: list[dict[str, Any]] = []

    for ctype in TARGET_TYPES:
        query = f'''query DeprecatedCompatibility {{
          concepts(type: "{ctype}", version: "{version}", include_deprecated: true, limit: 50000) {{
            id
            preferred_label
            type
            deprecated
            alternative_labels
            hidden_labels
            replaced_by {{ id preferred_label type deprecated }}
          }}
        }}'''
        body, doc, url = graphql(query)
        data = doc.get("data") if isinstance(doc, dict) else None
        rows = data.get("concepts") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise RuntimeError(f"GraphQL missing concepts list for type {ctype}")
        for concept in rows:
            if not isinstance(concept, dict) or not concept.get("id"):
                continue
            cid = str(concept["id"])
            existing = all_concepts.get(cid)
            if existing is not None and existing != concept:
                raise RuntimeError(f"concept {cid} returned inconsistently across type queries")
            all_concepts[cid] = concept
        query_sources.append({
            "type": ctype,
            "url": url,
            "response_bytes": len(body),
            "response_sha256": hashlib.sha256(body).hexdigest(),
            "returned_concepts": len(rows),
        })

    type_by_id: dict[str, str] = {
        cid: str(concept.get("type") or "") for cid, concept in all_concepts.items()
    }
    for cid, concept in active_by_id.items():
        type_by_id.setdefault(cid, str(concept.get("type") or ""))

    deprecated_ids = {
        cid for cid, concept in all_concepts.items() if concept.get("deprecated") is True
    }
    graph: dict[str, tuple[str, ...]] = {}
    direct_target_type_mismatches: list[dict[str, Any]] = []
    unknown_direct_targets: list[dict[str, Any]] = []

    for cid in sorted(deprecated_ids):
        concept = all_concepts[cid]
        targets = tuple(sorted(set(relation_ids(concept.get("replaced_by")))))
        graph[cid] = targets
        source_type = type_by_id.get(cid, "")
        relation_objects = concept.get("replaced_by") if isinstance(concept.get("replaced_by"), list) else []
        for target in relation_objects:
            if not isinstance(target, dict) or not target.get("id"):
                continue
            tid = str(target["id"])
            ttype = str(target.get("type") or type_by_id.get(tid) or "")
            if ttype:
                type_by_id.setdefault(tid, ttype)
            if ttype and ttype != source_type:
                direct_target_type_mismatches.append({
                    "source_id": cid,
                    "source_type": source_type,
                    "target_id": tid,
                    "target_type": ttype,
                })
            if tid not in all_concepts and tid not in active_ids:
                unknown_direct_targets.append({"source_id": cid, "target_id": tid, "target_type": ttype})

    routes: list[dict[str, Any]] = []
    state_counts = collections.Counter()
    state_by_type: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    direct_target_count = collections.Counter()
    depth_counts = collections.Counter()
    label_counts = collections.Counter()
    yv_resolution = collections.Counter()
    kv_resolution = collections.Counter()

    for cid in sorted(deprecated_ids):
        concept = all_concepts[cid]
        ctype = str(concept.get("type") or "")
        resolution = resolve_route(cid, ctype, graph, type_by_id, deprecated_ids, active_ids)
        state_counts[resolution.state] += 1
        state_by_type[ctype][resolution.state] += 1
        direct_target_count[len(graph.get(cid, ()))] += 1
        depth_counts[resolution.max_depth] += 1

        labels = [str(concept.get("preferred_label") or "").strip()]
        labels += as_strings(concept.get("alternative_labels"))
        labels += as_strings(concept.get("hidden_labels"))
        labels = sorted({label for label in labels if label})
        label_counts[ctype] += len(labels)

        product_status: dict[str, Any] = {}
        if ctype == "occupation-name":
            admitted = [tid for tid in resolution.active_targets if tid in yv_occ_ids]
            nonadmitted = [tid for tid in resolution.active_targets if tid not in yv_occ_ids]
            product_status = {"product": "YV", "admitted_active_targets": admitted, "nonadmitted_active_targets": nonadmitted}
            if resolution.state == "UNIQUE_ACTIVE_TARGET":
                yv_resolution["unique_occ_admitted" if admitted else "unique_occ_not_admitted"] += 1
        elif ctype == "job-title":
            admitted = [tid for tid in resolution.active_targets if tid in yv_job_ids]
            excluded = [tid for tid in resolution.active_targets if tid not in yv_job_ids]
            product_status = {"product": "YV", "admitted_active_targets": admitted, "excluded_active_job_title_targets": excluded}
            if resolution.state == "UNIQUE_ACTIVE_TARGET":
                yv_resolution["unique_job_admitted" if admitted else "unique_job_excluded"] += 1
        elif ctype == "skill":
            valid = [tid for tid in resolution.active_targets if type_by_id.get(tid) == "skill" and tid in active_ids]
            product_status = {"product": "KV", "active_skill_targets": valid}
            if resolution.state == "UNIQUE_ACTIVE_TARGET":
                kv_resolution["unique_active_skill" if valid else "unique_invalid_for_kv"] += 1

        routes.append({
            "legacy_concept_id": cid,
            "legacy_type": ctype,
            "legacy_preferred_label": concept.get("preferred_label"),
            "legacy_retrieval_labels": labels,
            "direct_replaced_by": list(graph.get(cid, ())),
            "resolution": resolution.state,
            "active_targets": list(resolution.active_targets),
            "max_chain_depth": resolution.max_depth,
            "replacement_paths": [list(path) for path in resolution.paths],
            "anomalies": list(resolution.anomalies),
            "product_status": product_status,
        })

    deprecated_by_type = collections.Counter(type_by_id[cid] for cid in deprecated_ids)
    active_by_type = collections.Counter(str(c.get("type") or "") for c in active_by_id.values())

    aggregate = {
        "schema_version": 1,
        "taxonomy_version": version,
        "generated_at": now_utc(),
        "sources": {
            "active_snapshot": {
                "url": active_url,
                "sha256": hashlib.sha256(active_body).hexdigest(),
                "bytes": len(active_body),
            },
            "graphql": query_sources,
            "yrkesvaljaren": {
                "url": yv_url,
                "sha256": hashlib.sha256(yv_body).hexdigest(),
                "bytes": len(yv_body),
            },
        },
        "relevant_types": list(TARGET_TYPES),
        "active_concepts_by_type": {k: active_by_type.get(k, 0) for k in TARGET_TYPES},
        "deprecated_concepts_by_type": {k: deprecated_by_type.get(k, 0) for k in TARGET_TYPES},
        "deprecated_total": len(deprecated_ids),
        "legacy_retrieval_labels_by_type": {k: label_counts.get(k, 0) for k in TARGET_TYPES},
        "direct_replacement_target_count_distribution": {str(k): v for k, v in sorted(direct_target_count.items())},
        "resolution_state_counts": dict(state_counts),
        "resolution_state_by_type": {
            ctype: dict(counter) for ctype, counter in sorted(state_by_type.items())
        },
        "max_chain_depth_distribution": {str(k): v for k, v in sorted(depth_counts.items())},
        "direct_target_type_mismatches": len(direct_target_type_mismatches),
        "unknown_direct_targets": len(unknown_direct_targets),
        "yv_product_resolution": dict(yv_resolution),
        "kv_product_resolution": dict(kv_resolution),
        "authority_boundary": (
            "replaced_by is canonical migration/history evidence, not synonymy; deprecated labels remain retrieval-only and product admission is applied after active target resolution"
        ),
    }

    anomalies = {
        "direct_target_type_mismatches": direct_target_type_mismatches,
        "unknown_direct_targets": unknown_direct_targets,
        "non_unique_or_invalid_routes": [
            route for route in routes if route["resolution"] != "UNIQUE_ACTIVE_TARGET"
        ],
        "unique_active_job_title_targets_excluded_from_yv": [
            route for route in routes
            if route["legacy_type"] == "job-title"
            and route["resolution"] == "UNIQUE_ACTIVE_TARGET"
            and route["product_status"].get("excluded_active_job_title_targets")
        ],
    }

    (out / "aggregate.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "routes.json").write_text(
        json.dumps(routes, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "anomalies.json").write_text(
        json.dumps(anomalies, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = [
        f"# Deprecated compatibility coverage — taxonomy v{version}",
        "",
        f"Deprecated concepts in YV/KV-relevant types: **{len(deprecated_ids):,}**.",
        "",
        "| Type | active | deprecated | legacy retrieval labels |",
        "|---|---:|---:|---:|",
    ]
    for ctype in TARGET_TYPES:
        lines.append(
            f"| `{ctype}` | {active_by_type.get(ctype, 0):,} | {deprecated_by_type.get(ctype, 0):,} | {label_counts.get(ctype, 0):,} |"
        )
    lines += [
        "",
        "Resolution states:",
        "",
        "```json",
        json.dumps(dict(state_counts), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "YV product-admission outcomes for unique routes:",
        "",
        "```json",
        json.dumps(dict(yv_resolution), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "KV outcomes for unique skill routes:",
        "",
        "```json",
        json.dumps(dict(kv_resolution), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Guardrail",
        "",
        "`replaced_by` is migration/history evidence, not synonymy. Deprecated labels remain retrieval-only; active target resolution does not bypass YV/KV product admission.",
        "",
    ]
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
