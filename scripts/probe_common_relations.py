#!/usr/bin/env python3
"""Probe the versioned concepts-and-common-relations distribution schema.

This is deliberately tiny and diagnostic. It verifies the immutable v31 URL,
records the root shape, counts target concept types and prints relation item
shapes before the main coverage extractor relies on them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request

USER_AGENT = "semantic-taxonomy-search-common-relations-probe/0.1"
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31")
    args = parser.parse_args()

    url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{args.version}/query/concepts-and-common-relations/"
        "concepts-and-common-relations.json"
    )
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
        print("http_status", response.status)
        print("content_type", response.headers.get("content-type"))
        print("content_length_header", response.headers.get("content-length"))

    print("url", url)
    print("sha256", hashlib.sha256(payload).hexdigest())
    print("bytes", len(payload))

    document = json.loads(payload)
    print("root_type", type(document).__name__)
    print("root_keys", sorted(document.keys()) if isinstance(document, dict) else None)
    data = document.get("data", document) if isinstance(document, dict) else document
    print("data_type", type(data).__name__)
    print("data_keys", sorted(data.keys()) if isinstance(data, dict) else None)

    concepts = data.get("concepts", []) if isinstance(data, dict) else []
    print("concept_count", len(concepts))

    counts = {t: 0 for t in sorted(TARGET_TYPES)}
    field_presence = {t: {f: 0 for f in ("definition", "short_description", "alternative_labels", "hidden_labels")} for t in sorted(TARGET_TYPES)}
    relation_presence = {t: {f: 0 for f in RELATION_FIELDS} for t in sorted(TARGET_TYPES)}
    relation_sample: dict[str, object] = {}

    target_example = None
    for concept in concepts:
        if not isinstance(concept, dict):
            continue
        ctype = concept.get("type")
        if ctype not in TARGET_TYPES:
            continue
        counts[ctype] += 1
        for field in field_presence[ctype]:
            if field in concept and concept.get(field) not in (None, "", []):
                field_presence[ctype][field] += 1
        for field in RELATION_FIELDS:
            value = concept.get(field)
            if isinstance(value, list) and value:
                relation_presence[ctype][field] += 1
                relation_sample.setdefault(field, value[0])
        if concept.get("id") == "xbZT_DjD_aWc":
            target_example = concept

    print("target_type_counts", json.dumps(counts, ensure_ascii=False, sort_keys=True))
    print("field_presence", json.dumps(field_presence, ensure_ascii=False, sort_keys=True))
    print("relation_presence", json.dumps(relation_presence, ensure_ascii=False, sort_keys=True))
    print("relation_item_samples", json.dumps(relation_sample, ensure_ascii=False, sort_keys=True)[:10000])

    if target_example:
        reduced = {
            key: target_example.get(key)
            for key in (
                "id",
                "type",
                "preferred_label",
                "definition",
                "short_description",
                "alternative_labels",
                "hidden_labels",
                *RELATION_FIELDS,
            )
            if key in target_example
        }
        print("kammarrattspresident", json.dumps(reduced, ensure_ascii=False, sort_keys=True)[:30000])
    else:
        print("kammarrattspresident", "NOT_FOUND")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
