#!/usr/bin/env python3
"""Measure native text coverage from an immutable taxonomy snapshot.

This extractor deliberately uses the same versioned
`concepts-and-common-relations` distribution as the graph inventory. That gives
text and graph research one exact source snapshot/hash and avoids live-API
pagination or GraphQL failure modes.

It measures presence and shape only. A non-empty definition that merely repeats
the preferred label is not counted as descriptive text.
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

TARGET_TYPES = ("occupation-name", "skill", "job-title", "keyword")
USER_AGENT = "semantic-taxonomy-search-native-text-coverage/0.2"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def pct(n: int, d: int) -> str:
    return "n/a" if not d else f"{100*n/d:.1f}%"


def fetch_snapshot(version: str) -> tuple[str, bytes, list[dict[str, Any]]]:
    url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/"
        "concepts-and-common-relations.json"
    )
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
    document = json.loads(payload)
    concepts = document.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("snapshot does not contain data.concepts list")
    return url, payload, concepts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31")
    parser.add_argument("--output-dir", default="artifacts/native-text-v31")
    args = parser.parse_args()

    version = str(args.version)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    generated_at = now_utc()

    url, payload, concepts = fetch_snapshot(version)
    digest = hashlib.sha256(payload).hexdigest()

    rows: list[dict[str, Any]] = []
    duplicate_ids: list[str] = []
    seen: set[str] = set()

    for concept in concepts:
        if not isinstance(concept, dict) or concept.get("type") not in TARGET_TYPES:
            continue
        cid = str(concept.get("id") or "")
        if not cid:
            continue
        if cid in seen:
            duplicate_ids.append(cid)
        seen.add(cid)

        label = str(concept.get("preferred_label") or "")
        definition = str(concept.get("definition") or "")
        short_description = str(concept.get("short_description") or "")
        alt = [str(v) for v in as_list(concept.get("alternative_labels")) if str(v).strip()]
        hidden = [str(v) for v in as_list(concept.get("hidden_labels")) if str(v).strip()]

        n_label = normalize(label)
        n_definition = normalize(definition)
        n_short = normalize(short_description)

        rows.append(
            {
                "taxonomy_version": version,
                "id": cid,
                "type": str(concept["type"]),
                "preferred_label": label,
                "definition": definition,
                "definition_nonempty": bool(n_definition),
                "definition_distinct_from_label": bool(n_definition and n_definition != n_label),
                "definition_same_as_label": bool(n_definition and n_definition == n_label),
                "definition_chars": len(definition.strip()),
                "short_description": short_description,
                "short_description_nonempty": bool(n_short),
                "short_description_distinct_from_label": bool(n_short and n_short != n_label),
                "short_description_chars": len(short_description.strip()),
                "alternative_labels": alt,
                "alternative_label_count": len(alt),
                "hidden_labels": hidden,
                "hidden_label_count": len(hidden),
            }
        )

    rows.sort(key=lambda r: (r["type"], normalize(r["preferred_label"]), r["id"]))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["type"]].append(row)

    aggregate: dict[str, Any] = {
        "schema_version": 2,
        "taxonomy_version": version,
        "generated_at": generated_at,
        "snapshot": {
            "url": url,
            "sha256": digest,
            "bytes": len(payload),
            "all_concepts": len(concepts),
            "target_concepts": len(rows),
            "duplicate_target_ids": duplicate_ids,
        },
        "by_type": {},
    }

    for ctype in TARGET_TYPES:
        items = grouped.get(ctype, [])
        total = len(items)
        aggregate["by_type"][ctype] = {
            "total": total,
            "definition_nonempty": sum(bool(r["definition_nonempty"]) for r in items),
            "definition_distinct_from_label": sum(bool(r["definition_distinct_from_label"]) for r in items),
            "definition_same_as_label": sum(bool(r["definition_same_as_label"]) for r in items),
            "short_description_nonempty": sum(bool(r["short_description_nonempty"]) for r in items),
            "short_description_distinct_from_label": sum(bool(r["short_description_distinct_from_label"]) for r in items),
            "with_alternative_labels": sum(int(r["alternative_label_count"]) > 0 for r in items),
            "alternative_label_edges": sum(int(r["alternative_label_count"]) for r in items),
            "with_hidden_labels": sum(int(r["hidden_label_count"]) > 0 for r in items),
            "hidden_label_edges": sum(int(r["hidden_label_count"]) for r in items),
        }

    with (output / "concepts.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    (output / "aggregate.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "source-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "taxonomy_version": version,
                "retrieved_at": generated_at,
                "dataset": "concepts-and-common-relations",
                "url": url,
                "sha256": digest,
                "bytes": len(payload),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    lines = [
        f"# Native text coverage — taxonomy v{version}",
        "",
        f"Snapshot SHA-256: `{digest}`",
        "",
        "A definition counts as descriptive only when its normalized text differs from the preferred label.",
        "",
        "| Type | concepts | distinct definition | label-copy definition | short description | alternative labels | hidden labels |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for ctype in TARGET_TYPES:
        stats = aggregate["by_type"][ctype]
        total = int(stats["total"])
        lines.append(
            "| `{}` | {:,} | {:,} ({}) | {:,} ({}) | {:,} ({}) | {:,} ({}) | {:,} ({}) |".format(
                ctype,
                total,
                stats["definition_distinct_from_label"],
                pct(stats["definition_distinct_from_label"], total),
                stats["definition_same_as_label"],
                pct(stats["definition_same_as_label"], total),
                stats["short_description_nonempty"],
                pct(stats["short_description_nonempty"], total),
                stats["with_alternative_labels"],
                pct(stats["with_alternative_labels"], total),
                stats["with_hidden_labels"],
                pct(stats["with_hidden_labels"], total),
            )
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- This script intentionally does not read `quality-level`; its semantics outside occupation-name are unresolved and it is not a semantic-text field.",
            "- It does not infer graph coverage. Graph relations are measured independently by `common_relations_coverage.py` from the same snapshot.",
            "- Missing specialised relations or external datasets are not represented as zeros here.",
            "",
        ]
    )
    summary = "\n".join(lines)
    (output / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
