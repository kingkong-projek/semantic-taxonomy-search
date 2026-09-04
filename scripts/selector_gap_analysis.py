#!/usr/bin/env python3
"""Analyse two residual gaps discovered by selector_coverage.py.

1. Why are 205 active v31 job-title IDs absent from published Yrkesväljaren?
2. What exactly is Kompetensväljaren's special `transferable_skills` container?

The script is descriptive and fail-closed. It validates IDs against immutable
v31/v30 taxonomy snapshots and never treats an unresolved string as a skill ID.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

USER_AGENT = "semantic-taxonomy-search-selector-gaps/0.1"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str, timeout: int = 180) -> tuple[bytes, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
    return body, json.loads(body)


def taxonomy_url(version: str) -> str:
    return (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )


def walk_strings(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk_strings(child, path + (str(key),))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk_strings(child, path + (str(i),))
    elif isinstance(value, str):
        yield path, value


def shape(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        if isinstance(value, dict):
            return f"object[{len(value)}]"
        if isinstance(value, list):
            return f"list[{len(value)}]"
        return type(value).__name__
    if isinstance(value, dict):
        return {str(k): shape(v, depth + 1) for k, v in list(value.items())[:30]}
    if isinstance(value, list):
        return [] if not value else [shape(value[0], depth + 1), f"count={len(value)}"]
    return type(value).__name__


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31")
    parser.add_argument("--previous-version", default="30")
    parser.add_argument("--output-dir", default="artifacts/selector-gaps-v31")
    args = parser.parse_args()

    version = str(args.version)
    previous = str(args.previous_version)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    t31_body, t31_doc = fetch_json(taxonomy_url(version))
    t30_body, t30_doc = fetch_json(taxonomy_url(previous))
    yv_url = f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{version}.json"
    kv_url = f"https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t{version}.json"
    yv_body, yv_doc = fetch_json(yv_url)
    kv_body, kv_doc = fetch_json(kv_url)

    c31 = t31_doc.get("data", {}).get("concepts")
    c30 = t30_doc.get("data", {}).get("concepts")
    if not isinstance(c31, list) or not isinstance(c30, list):
        raise RuntimeError("taxonomy snapshot missing concepts")

    by31 = {str(c.get("id")): c for c in c31 if isinstance(c, dict) and c.get("id")}
    by30 = {str(c.get("id")): c for c in c30 if isinstance(c, dict) and c.get("id")}
    active31_by_type: dict[str, set[str]] = defaultdict(set)
    for cid, concept in by31.items():
        active31_by_type[str(concept.get("type") or "")].add(cid)

    # ------------------------------- YV missing active job titles
    yv_rows = yv_doc.get("data")
    if not isinstance(yv_rows, list):
        raise RuntimeError("YV data is not a list")
    yv_job_ids = {str(r.get("id")) for r in yv_rows if isinstance(r, dict) and r.get("type") == "job-title" and r.get("id")}
    active_jobs = active31_by_type.get("job-title", set())
    missing = sorted(active_jobs - yv_job_ids)

    missing_rows: list[dict[str, Any]] = []
    parent_count = Counter()
    for cid in missing:
        concept = by31[cid]
        related_ids = [str(v) for v in (concept.get("related") or [])]
        occupation_parents = [rid for rid in related_ids if by31.get(rid, {}).get("type") == "occupation-name"]
        parent_count[len(occupation_parents)] += 1
        missing_rows.append({
            "id": cid,
            "preferred_label": concept.get("preferred_label"),
            "existed_in_v30": cid in by30,
            "occupation_parent_count": len(occupation_parents),
            "occupation_parent_ids": occupation_parents,
            "definition_distinct_from_label": str(concept.get("definition") or "").strip().casefold() != str(concept.get("preferred_label") or "").strip().casefold(),
        })

    new_in_v31 = [r for r in missing_rows if not r["existed_in_v30"]]
    existed_v30 = [r for r in missing_rows if r["existed_in_v30"]]

    # Compare previous YV publication when available to distinguish taxonomy-new
    # from long-standing titles that remain excluded by selector methodology.
    yv30_url = f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{previous}.json"
    yv30_body, yv30_doc = fetch_json(yv30_url)
    yv30_rows = yv30_doc.get("data")
    yv30_job_ids = {
        str(r.get("id")) for r in yv30_rows
        if isinstance(yv30_rows, list) and isinstance(r, dict) and r.get("type") == "job-title" and r.get("id")
    } if isinstance(yv30_rows, list) else set()
    existed_v30_but_absent_yv30 = [r for r in existed_v30 if r["id"] not in yv30_job_ids]
    existed_v30_and_present_yv30 = [r for r in existed_v30 if r["id"] in yv30_job_ids]

    # ------------------------------- KV transferable_skills
    kv_data = kv_doc.get("data")
    if not isinstance(kv_data, dict):
        raise RuntimeError("KV data is not an object")
    transferable = kv_data.get("transferable_skills")
    if transferable is None:
        raise RuntimeError("KV v31 has no data.transferable_skills")

    active_skills = active31_by_type.get("skill", set())
    referenced_active_skills: set[str] = set()
    unknown_id_like_strings: set[str] = set()
    string_paths: list[dict[str, Any]] = []
    for path, value in walk_strings(transferable):
        if value in active_skills:
            referenced_active_skills.add(value)
            classification = "active_skill_id"
        elif value in by31:
            classification = f"taxonomy_id:{by31[value].get('type')}"
        else:
            classification = "text_or_other"
            if len(value) == 11 and value.count("_") == 2:
                unknown_id_like_strings.add(value)
        if len(string_paths) < 100:
            string_paths.append({"path": list(path), "value": value, "classification": classification})

    # Skill ids already used by ordinary KV layers.
    ordinary_kv_skill_ids: set[str] = set()
    for key, record in kv_data.items():
        if key == "transferable_skills" or not isinstance(record, dict):
            continue
        for layer in ("regulated_skills", "essential_skills", "optional_skills", "calculated_skills"):
            mapping = record.get(layer) or {}
            if isinstance(mapping, dict):
                ordinary_kv_skill_ids.update(str(v) for v in mapping.values() if str(v) in active_skills)

    transferable_only = referenced_active_skills - ordinary_kv_skill_ids

    aggregate = {
        "schema_version": 1,
        "taxonomy_version": version,
        "generated_at": now_utc(),
        "sources": {
            "taxonomy_v31": {"url": taxonomy_url(version), "sha256": hashlib.sha256(t31_body).hexdigest()},
            "taxonomy_v30": {"url": taxonomy_url(previous), "sha256": hashlib.sha256(t30_body).hexdigest()},
            "yv_v31": {"url": yv_url, "sha256": hashlib.sha256(yv_body).hexdigest()},
            "yv_v30": {"url": yv30_url, "sha256": hashlib.sha256(yv30_body).hexdigest()},
            "kv_v31": {"url": kv_url, "sha256": hashlib.sha256(kv_body).hexdigest()},
        },
        "yv_missing_job_titles": {
            "count": len(missing_rows),
            "new_in_v31": len(new_in_v31),
            "existed_in_v30": len(existed_v30),
            "existed_in_v30_but_absent_from_yv30": len(existed_v30_but_absent_yv30),
            "existed_in_v30_and_present_in_yv30": len(existed_v30_and_present_yv30),
            "occupation_parent_count_distribution": {str(k): v for k, v in sorted(parent_count.items())},
        },
        "kv_transferable_skills": {
            "python_type": type(transferable).__name__,
            "container_size": len(transferable) if isinstance(transferable, (dict, list)) else None,
            "shape": shape(transferable),
            "active_skill_ids_referenced": len(referenced_active_skills),
            "active_skill_ids_already_in_ordinary_layers": len(referenced_active_skills & ordinary_kv_skill_ids),
            "active_skill_ids_unique_to_transferable": len(transferable_only),
            "unknown_id_like_strings": sorted(unknown_id_like_strings),
        },
    }

    (out / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "yv-missing-job-titles.json").write_text(json.dumps(missing_rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "kv-transferable-skill-ids.json").write_text(json.dumps({
        "referenced_active_skill_ids": sorted(referenced_active_skills),
        "unique_to_transferable": sorted(transferable_only),
        "sample_string_paths": string_paths,
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"# Selector residual-gap analysis — v{version}",
        "",
        "## YV missing active job titles",
        "",
        f"Missing active v{version} job-title IDs: **{len(missing_rows):,}**.",
        f"New in v{version}: **{len(new_in_v31):,}**.",
        f"Already existed in v{previous}: **{len(existed_v30):,}**.",
        f"Of the long-standing IDs, absent from YV v{previous} too: **{len(existed_v30_but_absent_yv30):,}**.",
        f"Of the long-standing IDs, present in YV v{previous} but absent now: **{len(existed_v30_and_present_yv30):,}**.",
        "",
        "Occupation-parent count distribution for missing titles: " + json.dumps(aggregate["yv_missing_job_titles"]["occupation_parent_count_distribution"], ensure_ascii=False),
        "",
        "## KV transferable_skills",
        "",
        f"Container type: **{type(transferable).__name__}**; size: **{aggregate['kv_transferable_skills']['container_size']}**.",
        f"Active skill IDs referenced: **{len(referenced_active_skills):,}**.",
        f"Already present in ordinary KV layers: **{len(referenced_active_skills & ordinary_kv_skill_ids):,}**.",
        f"Unique additional active skill IDs: **{len(transferable_only):,}**.",
        "",
        "## Guardrails",
        "",
        "- Missing YV titles are not called errors until release/history and methodology evidence explains the omission.",
        "- `transferable_skills` remains a separate provenance class/container even if it references the same skill IDs as ordinary KV layers.",
        "",
    ]
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    print("TRANSFERABLE_SHAPE", json.dumps(shape(transferable), ensure_ascii=False)[:12000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
