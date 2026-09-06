#!/usr/bin/env python3
"""Bounded JobStream v2 probe for skill-field shape and provenance markers.

Reads at most N ads and at most a hard byte budget from the snapshot response. Supports
NDJSON as well as a compact top-level JSON array without reading the full response.
Does not persist ad text or ad IDs. Output is schema/coverage metadata only.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any, Iterator

URL = "https://jobstream.api.jobtechdev.se/v2/snapshot"
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


def iter_json_array(response: Any, max_bytes: int, state: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Incrementally decode objects from a compact top-level JSON array.

    Never calls response.read() for more than the remaining byte budget. The decoder keeps
    only the unconsumed suffix in memory. If the root is not an array, the probe is marked
    inconclusive rather than attempting to buffer the whole document.
    """
    decoder = json.JSONDecoder()
    buffer = ""
    root_seen = False
    ended = False
    while state["bytes_read"] < max_bytes and not ended:
        remaining = max_bytes - state["bytes_read"]
        chunk = response.read(min(65_536, remaining))
        if not chunk:
            state["eof"] = True
            break
        state["bytes_read"] += len(chunk)
        buffer += chunk.decode("utf-8")

        if not root_seen:
            stripped = buffer.lstrip()
            if not stripped:
                continue
            state["root_token"] = stripped[0]
            if stripped[0] != "[":
                state["parse_status"] = "unsupported_non_array_json_root"
                return
            buffer = stripped[1:]
            root_seen = True

        while True:
            buffer = buffer.lstrip()
            while buffer.startswith(","):
                buffer = buffer[1:].lstrip()
            if buffer.startswith("]"):
                ended = True
                state["parse_status"] = "complete_array"
                break
            if not buffer:
                break
            try:
                value, end = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                # Most commonly an object split across chunks. Keep the suffix and read more.
                break
            buffer = buffer[end:]
            if isinstance(value, dict):
                state["decoded_values"] += 1
                yield value
            else:
                state["non_object_values"] += 1

    if root_seen and not ended and state["bytes_read"] >= max_bytes:
        state["parse_status"] = "byte_budget_reached"


def iter_ndjson(response: Any, max_bytes: int, state: dict[str, Any]) -> Iterator[dict[str, Any]]:
    while state["bytes_read"] < max_bytes:
        remaining = max_bytes - state["bytes_read"]
        # readline(size) bounds a pathological single line as well.
        line = response.readline(remaining)
        if not line:
            state["eof"] = True
            break
        state["bytes_read"] += len(line)
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            state["invalid_lines"] += 1
            continue
        if isinstance(value, dict):
            state["decoded_values"] += 1
            yield value
        else:
            state["non_object_values"] += 1
    state["parse_status"] = "byte_budget_reached" if state["bytes_read"] >= max_bytes else "complete_ndjson"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-ads", type=int, default=500)
    ap.add_argument("--max-bytes", type=int, default=8_000_000)
    ap.add_argument("--output", default="artifacts/jobstream-skill-language-probe.json")
    args = ap.parse_args()

    req = urllib.request.Request(URL, headers={"User-Agent": "semantic-taxonomy-search-research/1.0", "Accept": "application/x-ndjson,application/json"})
    valid_ads = 0
    top_keys = collections.Counter()
    requirement_shapes = {"must_have": collections.Counter(), "nice_to_have": collections.Counter()}
    skill_shapes = {"must_have": collections.Counter(), "nice_to_have": collections.Counter()}
    skill_key_counts = {"must_have": collections.Counter(), "nice_to_have": collections.Counter()}
    provenance_keys = {"must_have": collections.Counter(), "nice_to_have": collections.Counter()}
    ads_with_skills = {"must_have": 0, "nice_to_have": 0}
    skill_items = {"must_have": 0, "nice_to_have": 0}
    examples = {"must_have": [], "nice_to_have": []}
    response_meta: dict[str, Any] = {}
    parse_state: dict[str, Any] = {
        "bytes_read": 0,
        "decoded_values": 0,
        "non_object_values": 0,
        "invalid_lines": 0,
        "root_token": None,
        "parse_status": "not_started",
        "eof": False,
    }

    with urllib.request.urlopen(req, timeout=45) as response:
        content_type = str(response.headers.get("Content-Type") or "").casefold()
        response_meta = {
            "status": getattr(response, "status", None),
            "content_type": response.headers.get("Content-Type"),
            "content_length": response.headers.get("Content-Length"),
            "content_encoding": response.headers.get("Content-Encoding"),
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        }
        iterator = iter_ndjson(response, args.max_bytes, parse_state) if "ndjson" in content_type else iter_json_array(response, args.max_bytes, parse_state)
        for ad in iterator:
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
            if valid_ads >= args.max_ads:
                parse_state["parse_status"] = "max_ads_reached"
                break

    explicit_provenance_markers = sorted(set(provenance_keys["must_have"]) | set(provenance_keys["nice_to_have"]))
    if valid_ads == 0:
        provenance_assessment = "inconclusive_no_valid_ads"
    elif skill_items["must_have"] + skill_items["nice_to_have"] == 0:
        provenance_assessment = "inconclusive_no_skill_items_in_sample"
    elif explicit_provenance_markers:
        provenance_assessment = "machine_visible_markers_present"
    else:
        provenance_assessment = "no_machine_visible_item_provenance_marker_in_sample"

    result = {
        "schema_version": 2,
        "role": "bounded schema/provenance probe only; no retrieval evidence admitted",
        "source_url": URL,
        "request_limits": {"max_ads": args.max_ads, "max_bytes": args.max_bytes},
        "response": response_meta,
        "parse": parse_state,
        "observed": {
            "valid_ads": valid_ads,
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
        "bytes_read": parse_state["bytes_read"],
        "parse_status": parse_state["parse_status"],
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
