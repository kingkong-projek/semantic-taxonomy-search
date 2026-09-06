#!/usr/bin/env python3
"""Measure simple-first Pareto priority envelopes for YV occupations and KV skills.

The source is Historical API's server-side taxonomy statistics. Occurrence counts are
used only as a demand/popularity proxy for prioritisation. They are not query intent,
semantic ground truth, canonical authority, or evidence that a skill is required.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

UA = "semantic-taxonomy-search-pareto-demand/0.3"
THRESHOLDS = (0.50, 0.80, 0.90, 0.95, 0.99)
PRIORITY_SET_THRESHOLDS = ("p80", "p90", "p95")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 3) if d else 0.0


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def expected_hash(registry: dict[str, Any], adapter_id: str) -> str:
    adapters = registry.get("adapters")
    if not isinstance(adapters, list):
        raise RuntimeError("source registry missing adapters list")
    matches = [a for a in adapters if isinstance(a, dict) and a.get("id") == adapter_id]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one adapter {adapter_id!r}, got {len(matches)}")
    digest = matches[0].get("source_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise RuntimeError(f"adapter {adapter_id!r} has no accepted source_sha256")
    return digest


def checked_fetch(url: str, expected_sha256: str) -> bytes:
    body = fetch(url)
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected_sha256:
        raise RuntimeError(f"source drift for {url}: expected {expected_sha256}, got {actual}")
    return body


def validate_historical_contract(swagger: dict[str, Any]) -> None:
    stats = swagger.get("paths", {}).get("/stats", {}).get("get")
    if not isinstance(stats, dict):
        raise RuntimeError("Historical API swagger has no GET /stats contract")
    params = {p.get("name"): p for p in stats.get("parameters", []) if isinstance(p, dict)}
    taxonomy_type = params.get("taxonomy-type")
    stats_by = params.get("stats-by")
    if not isinstance(taxonomy_type, dict):
        raise RuntimeError("Historical API /stats lacks taxonomy-type")
    description = str(taxonomy_type.get("description") or "")
    for required in ("occupation-name", "skill"):
        if required not in description:
            raise RuntimeError(f"Historical API /stats contract no longer documents {required!r}")
    enum = stats_by.get("enum") if isinstance(stats_by, dict) else None
    if not isinstance(enum, list) or "concept_id" not in enum:
        raise RuntimeError("Historical API /stats no longer supports stats-by=concept_id")


def parse_rows(doc: dict[str, Any], key: str) -> list[dict[str, Any]]:
    stats = doc.get("stats")
    if not isinstance(stats, dict) or not isinstance(stats.get(key), list):
        raise RuntimeError(f"Historical API stats response missing {key!r}")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in stats[key]:
        if not isinstance(raw, dict) or not raw.get("concept_id"):
            continue
        cid = str(raw["concept_id"])
        if cid in seen:
            raise RuntimeError(f"duplicate {key} concept_id in Historical API stats: {cid}")
        seen.add(cid)
        occurrences = int(raw.get("occurrences") or 0)
        if occurrences < 0:
            raise RuntimeError(f"negative occurrence count for {cid}")
        rows.append({
            "concept_id": cid,
            "label": str(raw.get("label") or ""),
            "legacy_ams_taxonomy_id": str(raw.get("legacy_ams_taxonomy_id") or ""),
            "occurrences": occurrences,
        })
    rows.sort(key=lambda r: (-r["occurrences"], r["concept_id"]))
    return rows


def pareto(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(r["occurrences"] for r in rows)
    thresholds: dict[str, Any] = {}
    cumulative = 0
    threshold_index = 0
    for index, row in enumerate(rows, 1):
        cumulative += row["occurrences"]
        while threshold_index < len(THRESHOLDS) and total and cumulative / total >= THRESHOLDS[threshold_index]:
            threshold = THRESHOLDS[threshold_index]
            thresholds[f"p{int(threshold * 100)}"] = {
                "concept_count": index,
                "cumulative_occurrences": cumulative,
                "actual_share_pct": pct(cumulative, total),
                "last_included_occurrences": row["occurrences"],
            }
            threshold_index += 1
    priority_sets = {
        key: rows[: int(thresholds[key]["concept_count"])]
        for key in PRIORITY_SET_THRESHOLDS
        if key in thresholds
    }
    return {
        "observed_occurrence_total": total,
        "thresholds": thresholds,
        "priority_sets": priority_sets,
        "top_100": rows[:100],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--output-dir", default="artifacts/pareto-demand-v31")
    args = ap.parse_args()

    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    if str(registry.get("target_taxonomy_version")) != version:
        raise RuntimeError("source registry taxonomy version mismatch")

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    taxonomy_body = checked_fetch(taxonomy_url, expected_hash(registry, "taxonomy-common-relations"))
    taxonomy = json.loads(taxonomy_body)
    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy snapshot missing data.concepts")
    by_id = {
        str(c["id"]): c
        for c in concepts
        if isinstance(c, dict) and c.get("id")
    }
    active_occupations = {cid for cid, c in by_id.items() if c.get("type") == "occupation-name"}
    active_skills = {cid for cid, c in by_id.items() if c.get("type") == "skill"}

    swagger_url = "https://historical.api.jobtechdev.se/swagger.json"
    swagger_body = fetch(swagger_url)
    swagger = json.loads(swagger_body)
    validate_historical_contract(swagger)

    stats_base = "https://historical.api.jobtechdev.se/stats"
    params = [
        ("taxonomy-type", "occupation-name"),
        ("taxonomy-type", "skill"),
        ("stats-by", "concept_id"),
        ("limit", "10000"),
    ]
    stats_url = stats_base + "?" + urllib.parse.urlencode(params)
    stats_body = fetch(stats_url, timeout=300)
    stats_doc = json.loads(stats_body)
    stats_payload = stats_doc.get("stats")
    if not isinstance(stats_payload, dict):
        raise RuntimeError("Historical API stats response has no stats object")
    canonical_stats_sha256 = canonical_json_sha256(stats_payload)

    occupation_rows = parse_rows(stats_doc, "occupation-name")
    skill_rows = parse_rows(stats_doc, "skill")
    active_occ_rows = [r for r in occupation_rows if r["concept_id"] in active_occupations]
    active_skill_rows = [r for r in skill_rows if r["concept_id"] in active_skills]

    def summarize(all_rows: list[dict[str, Any]], active_rows: list[dict[str, Any]], universe: set[str]) -> dict[str, Any]:
        all_occurrences = sum(r["occurrences"] for r in all_rows)
        active_occurrences = sum(r["occurrences"] for r in active_rows)
        return {
            "historical_stat_rows": len(all_rows),
            "active_v31_rows": len(active_rows),
            "active_v31_target_universe": len(universe),
            "active_v31_targets_with_observed_occurrence_pct": pct(len(active_rows), len(universe)),
            "all_historical_occurrences": all_occurrences,
            "active_v31_occurrences": active_occurrences,
            "active_v31_share_of_returned_occurrences_pct": pct(active_occurrences, all_occurrences),
            "pareto_within_active_v31_observed_occurrence_mass": pareto(active_rows),
        }

    aggregate = {
        "schema_version": 3,
        "taxonomy_version": version,
        "measured_at": now_utc(),
        "semantics": {
            "source": "Historical API server-side taxonomy statistics",
            "use": "population/demand proxy for simple-first prioritisation",
            "not": [
                "user query intent",
                "semantic destination ground truth",
                "canonical authority",
                "proof that a listed skill is required rather than merely present in the source taxonomy fields",
            ],
            "pareto_denominator": "occurrence mass belonging to currently active v31 concepts that appear in the Historical API response",
            "priority_membership": "P80/P90/P95 memberships are persisted exactly so benchmark/runtime research can reproduce the same envelope without hand-written lists",
        },
        "sources": {
            "taxonomy": {"url": taxonomy_url, "sha256": hashlib.sha256(taxonomy_body).hexdigest()},
            "historical_api_swagger": {"url": swagger_url, "sha256": hashlib.sha256(swagger_body).hexdigest()},
            "historical_stats": {
                "url": stats_url,
                "sha256": canonical_stats_sha256,
                "hash_semantics": "SHA-256 of canonical JSON stats object only; request timing/metadata fields are excluded",
                "raw_response_sha256": hashlib.sha256(stats_body).hexdigest(),
            },
        },
        "occupation_name": summarize(occupation_rows, active_occ_rows, active_occupations),
        "skill": summarize(skill_rows, active_skill_rows, active_skills),
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "aggregate.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    o = aggregate["occupation_name"]
    s = aggregate["skill"]
    lines = [
        f"# Pareto demand proxy — taxonomy v{version}",
        "",
        "Historical API taxonomy occurrence statistics are used only to decide what to make good first.",
        "They are not semantic truth and do not change canonical/product identity.",
        "",
        "| active-v31 observed occurrence share | occupation-name concepts | skill concepts |",
        "|---:|---:|---:|",
    ]
    for key in ("p50", "p80", "p90", "p95", "p99"):
        op = o["pareto_within_active_v31_observed_occurrence_mass"]["thresholds"][key]
        sp = s["pareto_within_active_v31_observed_occurrence_mass"]["thresholds"][key]
        lines.append(f"| {key[1:]}% | {op['concept_count']:,} | {sp['concept_count']:,} |")
    lines += [
        "",
        f"- Active occupations represented in stats: **{o['active_v31_rows']:,}/{o['active_v31_target_universe']:,} = {o['active_v31_targets_with_observed_occurrence_pct']}%**.",
        f"- Active skills represented in stats: **{s['active_v31_rows']:,}/{s['active_v31_target_universe']:,} = {s['active_v31_targets_with_observed_occurrence_pct']}%**.",
        f"- Active-v31 occupation occurrence mass: **{o['active_v31_occurrences']:,}**.",
        f"- Active-v31 skill occurrence mass: **{s['active_v31_occurrences']:,}**.",
        f"- Canonical Historical `stats` SHA-256: `{canonical_stats_sha256}`.",
        "",
        "Simple-first implication: use P80 as the first candidate semantic confidence envelope, keep P90/P95 as measured expansion tiers, and preserve lexical fallback for the entire taxonomy.",
        "",
    ]
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
