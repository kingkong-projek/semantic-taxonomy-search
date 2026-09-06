#!/usr/bin/env python3
"""Measure a minimal exact job-title->occupation routing lane on frozen real queries.

This is a candidate-generation diagnostic, not relevance ground truth. Job-title text
may generate canonical occupation-name candidates through typed taxonomy/YV context,
but the job-title itself is not a core occupation destination.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

UA = "semantic-taxonomy-search-exact-job-title-router/0.1"


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def fetch(url: str, timeout: int = 240) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def expected_hash(registry: dict[str, Any], adapter_id: str) -> str:
    adapters = registry.get("adapters")
    if not isinstance(adapters, list):
        raise RuntimeError("source registry missing adapters")
    matches = [a for a in adapters if isinstance(a, dict) and a.get("id") == adapter_id]
    if len(matches) != 1:
        raise RuntimeError(f"expected one adapter {adapter_id!r}, got {len(matches)}")
    digest = matches[0].get("source_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise RuntimeError(f"adapter {adapter_id!r} has no accepted source hash")
    return digest


def checked_json(url: str, expected: str) -> tuple[bytes, Any]:
    body = fetch(url)
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected:
        raise RuntimeError(f"source drift: {url}: expected {expected}, got {actual}")
    return body, json.loads(body)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def tier_sets(pareto: dict[str, Any]) -> dict[str, set[str]]:
    section = pareto["occupation_name"]
    thresholds = section["thresholds"]
    ranked = section["ranked_p95"]
    result = {}
    for key in ("p80", "p90", "p95"):
        count = int(thresholds[key]["concept_count"])
        result[key] = {str(r["concept_id"]) for r in ranked[:count]}
    if [len(result[k]) for k in ("p80", "p90", "p95")] != [159, 302, 455]:
        raise RuntimeError("Pareto occupation tier drift")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--review", default="research/benchmark/v31/yv-real-query-review/review-packet.jsonl")
    ap.add_argument("--output", default="artifacts/exact-job-title-router-v31.json")
    args = ap.parse_args()

    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    tiers = tier_sets(pareto)
    review = read_jsonl(Path(args.review))
    if len(review) != 50:
        raise RuntimeError(f"expected frozen 50-query review slice, got {len(review)}")

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    yv_url = f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{version}.json"
    taxonomy_body, taxonomy = checked_json(taxonomy_url, expected_hash(registry, "taxonomy-common-relations"))
    yv_body, yv = checked_json(yv_url, expected_hash(registry, "yrkesvaljaren"))

    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active_jobs = {cid for cid, c in by_id.items() if c.get("type") == "job-title"}

    label_to_job_ids: dict[str, set[str]] = defaultdict(set)
    job_to_parents: dict[str, set[str]] = defaultdict(set)
    for cid in active_jobs:
        c = by_id[cid]
        label = norm(c.get("preferred_label"))
        if label:
            label_to_job_ids[label].add(cid)
        related = c.get("related")
        if isinstance(related, list):
            for rel in related:
                rid = str(rel.get("id") if isinstance(rel, dict) else rel)
                if by_id.get(rid, {}).get("type") == "occupation-name":
                    job_to_parents[cid].add(rid)

    yv_rows = yv.get("data")
    if not isinstance(yv_rows, list):
        raise RuntimeError("YV missing data")
    admitted_job_ids: set[str] = set()
    admitted_parents: dict[str, set[str]] = defaultdict(set)
    for row in yv_rows:
        if not isinstance(row, dict) or row.get("type") != "job-title" or not row.get("id"):
            continue
        cid = str(row["id"])
        parent = str(row.get("occupation_name_id") or "")
        admitted_job_ids.add(cid)
        if parent:
            admitted_parents[cid].add(parent)

    results: list[dict[str, Any]] = []
    matched_count = matched_volume = 0
    zero_count = zero_volume = 0
    zero_matched_count = zero_matched_volume = 0
    matched_all_p80_count = 0
    matched_require_p90_count = 0
    matched_require_p95_count = 0
    matched_outside_p95_count = 0

    for row in review:
        query = str(row["query"])
        count = int(row["observed_count"])
        c0_zero = bool(row.get("candidate_context", {}).get("simple_configuration_would_abstain"))
        if c0_zero:
            zero_count += 1
            zero_volume += count
        job_ids = sorted(label_to_job_ids.get(norm(query), set()))
        candidate_ids = sorted({pid for jid in job_ids for pid in job_to_parents.get(jid, set())})
        admitted_ids = sorted(jid for jid in job_ids if jid in admitted_job_ids)
        excluded_ids = sorted(jid for jid in job_ids if jid not in admitted_job_ids)
        if candidate_ids:
            matched_count += 1
            matched_volume += count
            if c0_zero:
                zero_matched_count += 1
                zero_matched_volume += count
            s = set(candidate_ids)
            if s <= tiers["p80"]:
                matched_all_p80_count += 1
            elif s <= tiers["p90"]:
                matched_require_p90_count += 1
            elif s <= tiers["p95"]:
                matched_require_p95_count += 1
            else:
                matched_outside_p95_count += 1
        results.append({
            "query": query,
            "observed_count": count,
            "c0_would_abstain": c0_zero,
            "exact_job_title_match": bool(job_ids),
            "matched_job_title_ids": job_ids,
            "admitted_yv_job_title_ids": admitted_ids,
            "excluded_yv_job_title_ids": excluded_ids,
            "candidate_occupations": [
                {
                    "concept_id": cid,
                    "label": str(by_id[cid].get("preferred_label") or ""),
                    "p80": cid in tiers["p80"],
                    "p90": cid in tiers["p90"],
                    "p95": cid in tiers["p95"],
                }
                for cid in candidate_ids
            ],
            "authority_boundary": "exact job-title wording generates typed occupation candidates only; it is not destination ground truth and does not make a YV-excluded job title selectable",
        })

    top_matched = [r for r in results if r["candidate_occupations"]]
    top_matched.sort(key=lambda r: (-r["observed_count"], norm(r["query"])))
    zero_matched = [r for r in top_matched if r["c0_would_abstain"]]

    total_volume = sum(int(r["observed_count"]) for r in review)
    output = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "semantics": "candidate-generation diagnostic on pending real-query slice; no relevance labels are inferred",
        "lane": "exact normalized active job-title preferred label -> typed occupation-name parents",
        "review_slice": {
            "queries": len(review),
            "observed_volume": total_volume,
            "c0_zero_evidence_queries": zero_count,
            "c0_zero_evidence_volume": zero_volume,
        },
        "router": {
            "queries_with_exact_job_title_route": matched_count,
            "matched_query_volume": matched_volume,
            "matched_share_of_review_volume_pct": round(100 * matched_volume / total_volume, 3),
            "c0_zero_evidence_queries_rescued_as_candidate_generation": zero_matched_count,
            "c0_zero_evidence_volume_rescued_as_candidate_generation": zero_matched_volume,
            "c0_zero_evidence_volume_candidate_generation_share_pct": round(100 * zero_matched_volume / zero_volume, 3) if zero_volume else 0.0,
            "candidate_sets_entirely_within_p80": matched_all_p80_count,
            "candidate_sets_requiring_p90_but_not_beyond": matched_require_p90_count,
            "candidate_sets_requiring_p95_but_not_beyond": matched_require_p95_count,
            "candidate_sets_with_any_target_outside_p95": matched_outside_p95_count,
        },
        "top_matched_queries": top_matched[:20],
        "c0_zero_evidence_exact_router_matches": zero_matched,
        "sources": {
            "taxonomy_sha256": hashlib.sha256(taxonomy_body).hexdigest(),
            "yrkesvaljaren_sha256": hashlib.sha256(yv_body).hexdigest(),
            "review_file": args.review,
            "pareto_file": args.pareto,
        },
        "interpretation_guardrail": "A route proves that the wording is an active job-title label with typed occupation relations. It does not prove which candidate the user intends. Human-judged relevance is still required before scoring quality.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
