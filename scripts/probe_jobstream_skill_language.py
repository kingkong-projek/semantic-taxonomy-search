#!/usr/bin/env python3
"""Bounded JobStream v2 probe for skill-field shape and provenance markers.

Reads only the first N valid NDJSON ads (default 500) with a conservative byte cap.
Does not persist ad text or ad IDs. Output is schema/coverage metadata only.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

URL = "https://jobstream.api.jobtechdev.se/v2/snapshot"
SENSITIVE_TEXT_KEYS = {"description", "headline", "application_details", "workplace_address"}
PROVENANCE_KEYWORDS = ("source", "origin", "original", "enrich", "derived", "provider", "producer", "method", "model")


def shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


def shape_key(value: Any) -> str:
    return json.dumps(shape(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def find_requirement_container(ad: dict[str, Any], key: str) -> Any:
    if key in ad:
        return ad.get(key)
    requirements = ad.get("requirements")
    if isinstance(requirements, dict) and key in requirements:
        return requirements.get(key)
    return None


def skills_from(container: Any) -> list[Any]:
    if isinstance(container, dict):
        value = container.get("skills")
        return value if isinstance(value, list) else []
    return []


def safe_example(item: Any) -> Any:
    if not isinstance(item, dict):
        return shape(item)
    out = {}
    for k, v in sorted(item.items()):
        kl = k.casefold()
        if any(token in kl for token in PROVENANCE_KEYWORDS):
            out[k] = v
        elif k in {"concept_id", "label", "weight", "legacy_ams_taxonomy_id", "taxonomy_id", "id"}:
            out[k] = v
        else:
            out[k] = f"<{type(v).__name__}>"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-ads", type=int, default=500)
    ap.add_argument("--max-bytes", type=int, default=8_000_000)
    ap.add_argument("--output", default="artifacts/jobstream-skill-language-probe.json")
    args = ap.parse_args()

    req = urllib.request.Request(URL, headers={"User-Agent": "semantic-taxonomy-search-research/1.0", "Accept": "application/x-ndjson,application/json"})
    valid_ads = 0
    bytes_read = 0
    invalid_lines = 0
    top_keys = collections.Counter()
    requirement_shapes = {"must_have": collections.Counter(), "nice_to_have": collections.Counter()}
    skill_shapes = {"must_have": collections.Counter(), "nice_to_have": collections.Counter()}
    skill_key_counts = {"must_have": collections.Counter(), "nice_to_have": collections.Counter()}
    provenance_keys = {"must_have": collections.Counter(), "nice_to_have": collections.Counter()}
    ads_with_skills = {"must_have": 0, "nice_to_have": 0}
    skill_items = {"must_have": 0, "nice_to_have": 0}
    examples = {"must_have": [], "nice_to_have": []}
    response_meta: dict[str, Any] = {}

    with urllib.request.urlopen(req, timeout=45) as response:
        response_meta = {
            "status": getattr(response, "status", None),
            "content_type": response.headers.get("Content-Type"),
            "content_length": response.headers.get("Content-Length"),
            "content_encoding": response.headers.get("Content-Encoding"),
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        }
        while valid_ads < args.max_ads and bytes_read < args.max_bytes:
            line = response.readline()
            if not line:
                break
            bytes_read += len(line)
            if bytes_read > args.max_bytes:
                break
            try:
                ad = json.loads(line)
            except json.JSONDecodeError:
                invalid_lines += 1
                continue
            if not isinstance(ad, dict):
                invalid_lines += 1
                continue
            valid_ads += 1
            top_keys.update(ad.keys())
            for requirement in ("must_have", "nice_to_have"):
                container = find_requirement_container(ad, requirement)
                requirement_shapes[requirement][shape_key(container)] += 1
                items = skills_from(container)
                if items:
                    ads_with_skills[requirement] += 1
                for item in items:
                    skill_items[requirement] += 1
                    skill_shapes[requirement][shape_key(item)] += 1
                    if isinstance(item, dict):
                        skill_key_counts[requirement].update(item.keys())
                        for k in item:
                            if any(token in k.casefold() for token in PROVENANCE_KEYWORDS):
                                provenance_keys[requirement][k] += 1
                    if len(examples[requirement]) < 5:
                        examples[requirement].append(safe_example(item))

    explicit_provenance_markers = sorted(set(provenance_keys["must_have"]) | set(provenance_keys["nice_to_have"]))
    if explicit_provenance_markers:
        provenance_assessment = "machine_visible_markers_present"
    else:
        provenance_assessment = "no_machine_visible_item_provenance_marker_in_sample"

    result = {
        "schema_version": 1,
        "role": "bounded schema/provenance probe only; no retrieval evidence admitted",
        "source_url": URL,
        "request_limits": {"max_ads": args.max_ads, "max_bytes": args.max_bytes},
        "response": response_meta,
        "observed": {
            "valid_ads": valid_ads,
            "bytes_read": bytes_read,
            "invalid_lines": invalid_lines,
            "top_level_keys": dict(top_keys.most_common()),
            "ads_with_skills": ads_with_skills,
            "skill_item_counts": skill_items,
            "requirement_shapes": {k: dict(v.most_common(10)) for k, v in requirement_shapes.items()},
            "skill_item_shapes": {k: dict(v.most_common(10)) for k, v in skill_shapes.items()},
            "skill_item_key_counts": {k: dict(v.most_common()) for k, v in skill_key_counts.items()},
            "provenance_like_key_counts": {k: dict(v.most_common()) for k, v in provenance_keys.items()},
            "redacted_skill_item_examples": examples,
        },
        "provenance_assessment": provenance_assessment,
        "privacy_guard": "no ad id, headline, description or address text persisted",
        "source_snapshot_fingerprint": hashlib.sha256(json.dumps(response_meta, sort_keys=True).encode()).hexdigest(),
        "decision_rule": "Do not use JobStream skill-labelled text as retrieval evidence unless requirement-field lineage is sufficiently distinguishable/documented after this probe and source-code review.",
    }
    p = Path(args.output); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "valid_ads": valid_ads,
        "bytes_read": bytes_read,
        "content_type": response_meta.get("content_type"),
        "ads_with_skills": ads_with_skills,
        "skill_item_counts": skill_items,
        "skill_item_keys": {k: list(v.keys()) for k, v in skill_key_counts.items()},
        "provenance_like_keys": explicit_provenance_markers,
        "assessment": provenance_assessment,
    }, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
