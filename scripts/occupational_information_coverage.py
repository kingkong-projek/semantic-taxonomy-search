#!/usr/bin/env python3
"""Measure Yrkesinformation interim source coverage and canonical joinability.

The source is a legacy Hitta yrken export. Its metadata exposes legacy numeric IDs,
labels and slugs, while semantic search needs exact v31 taxonomy identities. This
extractor separates source-content coverage from identity joinability.

No normalized/fuzzy label match is accepted as a canonical identity join. Exact
text matches are reported only as candidate evidence unless an explicit shared ID
is found in the source itself.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any, Iterable

UA = "semantic-taxonomy-search-occupational-info/0.1"
SOURCE_URL = "https://data.arbetsformedlingen.se/yrke/yrkesinformation/yrkesinformation-interimslosning.json"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str, timeout: int = 180) -> tuple[bytes, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
    return body, json.loads(body)


def norm_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def walk(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, path + (str(key),))
    elif isinstance(value, list):
        for child in value:
            yield from walk(child, path + ("[]",))
    else:
        yield path, value


def record_map(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        return {str(k): v for k, v in data.items()}
    if isinstance(data, list):
        result: dict[str, Any] = {}
        for index, item in enumerate(data):
            if not isinstance(item, dict):
                result[f"#{index}"] = item
                continue
            key = str(item.get("slug") or item.get("id") or f"#{index}")
            result[key] = item
        return result
    raise RuntimeError(f"unsupported data type: {type(data).__name__}")


def concept_list(document: Any) -> list[dict[str, Any]]:
    concepts = document.get("data", {}).get("concepts") if isinstance(document, dict) else None
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy snapshot missing data.concepts")
    return [item for item in concepts if isinstance(item, dict)]


def extract_labels(concept: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    preferred = concept.get("preferred_label")
    if isinstance(preferred, str) and preferred.strip():
        values.add(norm_text(preferred))
    for field in ("alternative_labels", "hidden_labels"):
        labels = concept.get(field) or []
        if isinstance(labels, list):
            for label in labels:
                if isinstance(label, str) and label.strip():
                    values.add(norm_text(label))
                elif isinstance(label, dict):
                    for key in ("label", "value", "preferred_label"):
                        candidate = label.get(key)
                        if isinstance(candidate, str) and candidate.strip():
                            values.add(norm_text(candidate))
    return values


def find_explicit_taxonomy_ids(record: Any, active_ids: set[str]) -> set[str]:
    found: set[str] = set()
    for path, value in walk(record):
        if not isinstance(value, str):
            continue
        if value in active_ids:
            found.add(value)
        if any(token in ".".join(path).casefold() for token in ("taxonomy", "concept", "occupation")):
            for token in re.findall(r"[A-Za-z0-9_-]{7,40}", value):
                if token in active_ids:
                    found.add(token)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31")
    parser.add_argument("--output-dir", default="artifacts/occupational-information-v31")
    args = parser.parse_args()

    version = str(args.version)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )

    source_body, source_doc = fetch_json(SOURCE_URL)
    taxonomy_body, taxonomy_doc = fetch_json(taxonomy_url)

    if not isinstance(source_doc, dict):
        raise RuntimeError("Yrkesinformation source is not an object")
    metadata = source_doc.get("metadata")
    data = source_doc.get("data")
    if not isinstance(metadata, dict):
        raise RuntimeError("Yrkesinformation missing metadata object")
    occupations = metadata.get("occupations")
    if not isinstance(occupations, list):
        raise RuntimeError("Yrkesinformation missing metadata.occupations list")

    records = record_map(data)
    concepts = concept_list(taxonomy_doc)
    active_occupation = [c for c in concepts if c.get("type") == "occupation-name" and c.get("id")]
    active_occ_ids = {str(c["id"]) for c in active_occupation}
    active_all_ids = {str(c.get("id")) for c in concepts if c.get("id")}

    preferred_index: dict[str, set[str]] = collections.defaultdict(set)
    all_label_index: dict[str, set[str]] = collections.defaultdict(set)
    for concept in active_occupation:
        cid = str(concept["id"])
        preferred = concept.get("preferred_label")
        if isinstance(preferred, str) and preferred.strip():
            preferred_index[norm_text(preferred)].add(cid)
        for label in extract_labels(concept):
            all_label_index[label].add(cid)

    metadata_rows: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    seen_legacy_ids: set[str] = set()
    exact_preferred_unique = 0
    exact_preferred_ambiguous = 0
    exact_any_unique = 0
    exact_any_ambiguous = 0
    explicit_id_unique = 0
    explicit_id_ambiguous = 0
    no_text_candidate = 0
    missing_record = 0

    field_presence = collections.Counter()
    string_path_presence = collections.Counter()
    total_text_chars = 0
    rich_record_count = 0
    record_explicit_ids: dict[str, list[str]] = {}
    identifier_paths = collections.Counter()
    ssyk_paths = collections.Counter()

    for slug, record in records.items():
        record_paths: set[str] = set()
        string_paths: set[str] = set()
        record_chars = 0
        for path, value in walk(record):
            dotted = ".".join(path)
            if path:
                record_paths.add(dotted)
            if isinstance(value, str) and value.strip():
                string_paths.add(dotted)
                if not value.lstrip().lower().startswith(("http://", "https://")):
                    record_chars += len(value.strip())
            if "ssyk" in dotted.casefold():
                ssyk_paths[dotted] += 1
            if any(x in dotted.casefold() for x in ("legacy", "occupation_id", "occupationid", "taxonomy", "concept")):
                if isinstance(value, (str, int)):
                    identifier_paths[dotted] += 1
        for p in record_paths:
            field_presence[p] += 1
        for p in string_paths:
            string_path_presence[p] += 1
        total_text_chars += record_chars
        if record_chars >= 200:
            rich_record_count += 1
        explicit = find_explicit_taxonomy_ids(record, active_all_ids)
        if explicit:
            record_explicit_ids[slug] = sorted(explicit)

    for item in occupations:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        slug = str(item.get("slug") or "").strip()
        legacy_id = str(item.get("id") or "").strip()
        if slug:
            seen_slugs.add(slug)
        if legacy_id:
            seen_legacy_ids.add(legacy_id)
        normalized = norm_text(name) if name else ""
        preferred = preferred_index.get(normalized, set()) if normalized else set()
        any_label = all_label_index.get(normalized, set()) if normalized else set()
        explicit = set(record_explicit_ids.get(slug, [])) & active_occ_ids

        if len(preferred) == 1:
            exact_preferred_unique += 1
        elif len(preferred) > 1:
            exact_preferred_ambiguous += 1
        if len(any_label) == 1:
            exact_any_unique += 1
        elif len(any_label) > 1:
            exact_any_ambiguous += 1
        if len(explicit) == 1:
            explicit_id_unique += 1
        elif len(explicit) > 1:
            explicit_id_ambiguous += 1
        if not any_label:
            no_text_candidate += 1
        if slug and slug not in records:
            missing_record += 1

        metadata_rows.append({
            "legacy_id": legacy_id,
            "name": name,
            "slug": slug,
            "record_present": slug in records,
            "exact_preferred_occupation_ids": sorted(preferred),
            "exact_any_label_occupation_ids": sorted(any_label),
            "explicit_active_occupation_ids_in_record": sorted(explicit),
        })

    aggregate = {
        "schema_version": 1,
        "taxonomy_version": version,
        "generated_at": now_utc(),
        "sources": {
            "occupational_information": {
                "url": SOURCE_URL,
                "bytes": len(source_body),
                "sha256": hashlib.sha256(source_body).hexdigest(),
                "metadata": {
                    key: metadata.get(key)
                    for key in ("title", "version", "created_at", "source_date", "data_expires")
                    if key in metadata
                },
            },
            "taxonomy_snapshot": {
                "url": taxonomy_url,
                "bytes": len(taxonomy_body),
                "sha256": hashlib.sha256(taxonomy_body).hexdigest(),
            },
        },
        "source_shape": {
            "metadata_occupations": len(metadata_rows),
            "data_records": len(records),
            "metadata_slugs_unique": len(seen_slugs),
            "metadata_legacy_ids_unique": len(seen_legacy_ids),
            "metadata_rows_missing_data_record": missing_record,
            "rich_records_ge_200_text_chars": rich_record_count,
            "total_non_url_string_chars": total_text_chars,
            "top_field_paths": field_presence.most_common(80),
            "top_string_paths": string_path_presence.most_common(80),
            "ssyk_like_paths": ssyk_paths.most_common(30),
            "identifier_like_paths": identifier_paths.most_common(30),
        },
        "canonical_joinability": {
            "active_occupation_universe": len(active_occupation),
            "explicit_active_occupation_id_unique": explicit_id_unique,
            "explicit_active_occupation_id_ambiguous": explicit_id_ambiguous,
            "exact_preferred_label_unique_candidate": exact_preferred_unique,
            "exact_preferred_label_ambiguous_candidate": exact_preferred_ambiguous,
            "exact_any_taxonomy_label_unique_candidate": exact_any_unique,
            "exact_any_taxonomy_label_ambiguous_candidate": exact_any_ambiguous,
            "no_exact_taxonomy_label_candidate": no_text_candidate,
            "authority_boundary": (
                "Only explicit active taxonomy IDs embedded in a source record are authoritative joins. "
                "Exact label matches are candidate mappings and require independent validation before semantic text can inherit canonical identity."
            ),
        },
    }

    (out / "aggregate.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "join-candidates.json").write_text(
        json.dumps(metadata_rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = [
        f"# Yrkesinformation interim coverage — taxonomy v{version}",
        "",
        f"Source SHA-256: `{aggregate['sources']['occupational_information']['sha256']}`.",
        f"Metadata occupations: **{len(metadata_rows):,}**; data records: **{len(records):,}**.",
        f"Rich records (>=200 non-URL string chars): **{rich_record_count:,}**.",
        "",
        "## Canonical joinability",
        "",
        f"Explicit active occupation IDs embedded in source records, unique: **{explicit_id_unique:,}**.",
        f"Exact preferred-label unique candidates: **{exact_preferred_unique:,} / {len(metadata_rows):,}**.",
        f"Exact any-taxonomy-label unique candidates: **{exact_any_unique:,} / {len(metadata_rows):,}**.",
        f"No exact taxonomy-label candidate: **{no_text_candidate:,}**.",
        "",
        "Exact label equality is candidate evidence only; it is not promoted to an identity join without an independent canonical key.",
        "",
        "SSYK-like paths:",
        "```json",
        json.dumps(ssyk_paths.most_common(15), ensure_ascii=False, indent=2),
        "```",
        "Identifier-like paths:",
        "```json",
        json.dumps(identifier_paths.most_common(15), ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
