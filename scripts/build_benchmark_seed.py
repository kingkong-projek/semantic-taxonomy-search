#!/usr/bin/env python3
"""Build provenance-safe Gate-2 benchmark seed cases.

Only canonical preferred/alternative-label cases become AUTO_HIGH_CONFIDENCE.
YV generator-excluded titles are emitted to a separate review-candidate file and
are never auto-promoted to benchmark truth.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

UA = "semantic-taxonomy-search-benchmark-seed/0.2"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def fetch(url: str, timeout: int = 240) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def relation_ids(concept: dict[str, Any], field: str) -> list[str]:
    value = concept.get(field)
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        if isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
        elif isinstance(item, str) and item:
            ids.append(item)
    return ids


def labels(value: Any) -> list[str]:
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


def expected_hash(registry: dict[str, Any], adapter_id: str) -> str:
    adapters = registry.get("adapters")
    if not isinstance(adapters, list):
        raise RuntimeError("source registry missing adapters")
    found = [item for item in adapters if isinstance(item, dict) and item.get("id") == adapter_id]
    if len(found) != 1:
        raise RuntimeError(f"expected one adapter {adapter_id!r}, got {len(found)}")
    digest = found[0].get("source_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise RuntimeError(f"adapter {adapter_id!r} has no accepted source_sha256")
    return digest


def checked_json(url: str, expected: str) -> tuple[bytes, Any]:
    body = fetch(url)
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected:
        raise RuntimeError(f"source drift for {url}: expected {expected}, got {actual}")
    return body, json.loads(body)


def identity_key(identity: dict[str, Any]) -> tuple[str, ...]:
    if identity["kind"] == "job-title":
        return identity["kind"], identity["concept_id"], identity["occupation_name_id"]
    return identity["kind"], identity["concept_id"]


def canonical_evidence(version: str, role: str = "destination_ground_truth", note: str | None = None) -> dict[str, str]:
    result = {
        "source": f"JobTech Taxonomy v{version}",
        "provenance": "canonical",
        "role": role,
    }
    if note:
        result["note"] = note
    return result


def curated_evidence(version: str, note: str) -> dict[str, str]:
    return {
        "source": f"JobTech Taxonomy v{version} typed relations",
        "provenance": "curated_relation",
        "role": "destination_ground_truth",
        "note": note,
    }


def yv_admission_evidence(version: str) -> dict[str, str]:
    return {
        "source": f"Published Yrkesväljaren v{version}",
        "provenance": "behavioral",
        "role": "product_admission",
        "note": "Exact row/context is admitted by the published YV read model; weight is not semantic ground truth.",
    }


def make_case(
    *, case_id: str, version: int, product: str, query: str, query_origin: str,
    strata: list[str], identities: list[dict[str, Any]], evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    unique = {identity_key(identity): identity for identity in identities}
    ordered = [unique[key] for key in sorted(unique)]
    if not ordered:
        raise RuntimeError(f"cannot auto-build benchmark case {case_id}: no destination identities")
    if len(ordered) > 100:
        raise RuntimeError(
            f"cannot auto-build benchmark case {case_id}: {len(ordered)} exact identities exceed benchmark top_k limit; send to review instead"
        )
    intent = "SINGLE" if len(ordered) == 1 else "AMBIGUOUS"
    return {
        "id": case_id,
        "taxonomy_version": version,
        "product": product,
        "query": query,
        "query_language": "sv",
        "query_origin": query_origin,
        "strata": sorted(set(strata)),
        "expected_intent": intent,
        "must": ordered,
        "acceptable": [],
        "must_not": [],
        "top_k": max(10, len(ordered)),
        "allow_abstention": False,
        "source_evidence": evidence,
        "adjudication": {
            "status": "AUTO_HIGH_CONFIDENCE",
            "reviewer_count": 0,
            "agreement": "UNREVIEWED",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31")
    parser.add_argument("--registry", default="research/coverage/source-adapters.json")
    parser.add_argument("--output-dir", default="artifacts/benchmark-seed-v31")
    args = parser.parse_args()

    version_str = str(args.version)
    version = int(version_str)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    if str(registry.get("target_taxonomy_version")) != version_str:
        raise RuntimeError("registry taxonomy version mismatch")

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version_str}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    yv_url = f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{version_str}.json"

    taxonomy_body, taxonomy_doc = checked_json(
        taxonomy_url, expected_hash(registry, "taxonomy-common-relations")
    )
    yv_body, yv_doc = checked_json(yv_url, expected_hash(registry, "yrkesvaljaren"))

    concepts = taxonomy_doc.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy snapshot missing data.concepts")
    by_id = {
        str(concept["id"]): concept
        for concept in concepts
        if isinstance(concept, dict) and concept.get("id")
    }
    active_jobs = {
        cid for cid, concept in by_id.items() if concept.get("type") == "job-title"
    }
    active_skills = {
        cid for cid, concept in by_id.items() if concept.get("type") == "skill"
    }

    # ---------------------------------------------------------------- YV exact labels
    yv_rows = yv_doc.get("data")
    if not isinstance(yv_rows, list):
        raise RuntimeError("YV missing data list")

    yv_by_query: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    yv_query_surface: dict[str, set[str]] = collections.defaultdict(set)
    published_job_ids: set[str] = set()
    job_parents_by_id: dict[str, set[str]] = collections.defaultdict(set)

    for row in yv_rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        cid = str(row["id"])
        ctype = str(row.get("type") or "")
        label = str(row.get("preferred_label") or "").strip()
        if not label:
            continue
        canonical = by_id.get(cid)
        if canonical is None or canonical.get("type") != ctype:
            raise RuntimeError(f"YV row {cid} fails canonical identity validation")
        if norm(canonical.get("preferred_label")) != norm(label):
            raise RuntimeError(f"YV row {cid} label drift vs canonical taxonomy")

        if ctype == "occupation-name":
            identity = {"kind": "occupation-name", "concept_id": cid, "label": label}
        elif ctype == "job-title":
            parent = str(row.get("occupation_name_id") or "")
            parent_concept = by_id.get(parent)
            if parent_concept is None or parent_concept.get("type") != "occupation-name":
                raise RuntimeError(f"YV job-title {cid} has invalid occupation parent")
            published_job_ids.add(cid)
            job_parents_by_id[cid].add(parent)
            identity = {
                "kind": "job-title",
                "concept_id": cid,
                "occupation_name_id": parent,
                "label": label,
                "occupation_name_label": str(parent_concept.get("preferred_label") or ""),
            }
        else:
            continue
        key = norm(label)
        yv_by_query[key].append(identity)
        yv_query_surface[key].add(label)

    yv_cases: list[dict[str, Any]] = []
    for index, key in enumerate(sorted(yv_by_query), 1):
        identities = yv_by_query[key]
        query = sorted(yv_query_surface[key], key=lambda value: (len(value), value))[0]
        strata = ["exact_preferred_label"]
        job_ids = {identity["concept_id"] for identity in identities if identity["kind"] == "job-title"}
        if job_ids:
            strata.append("yv_exact_job_title")
        if any(len(job_parents_by_id[job_id]) > 1 for job_id in job_ids):
            strata.append("yv_multi_parent_title")
        evidence = [canonical_evidence(version_str), yv_admission_evidence(version_str)]
        if job_ids:
            evidence.append(curated_evidence(version_str, "job-title identity retains exact occupation-name context"))
        yv_cases.append(make_case(
            case_id=f"yv.exact.{index:05d}",
            version=version,
            product="YV",
            query=query,
            query_origin="canonical_label",
            strata=strata,
            identities=identities,
            evidence=evidence,
        ))

    # ---------------------------------------------------------- KV canonical label vocabulary
    skill_by_query: dict[str, set[str]] = collections.defaultdict(set)
    preferred_surfaces: dict[str, set[str]] = collections.defaultdict(set)
    alternative_surfaces: dict[str, set[str]] = collections.defaultdict(set)

    for sid in active_skills:
        concept = by_id[sid]
        preferred = str(concept.get("preferred_label") or "").strip()
        if preferred:
            key = norm(preferred)
            skill_by_query[key].add(sid)
            preferred_surfaces[key].add(preferred)
        for alternative in labels(concept.get("alternative_labels")):
            key = norm(alternative)
            skill_by_query[key].add(sid)
            alternative_surfaces[key].add(alternative)

    kv_cases: list[dict[str, Any]] = []
    for index, key in enumerate(sorted(skill_by_query), 1):
        ids = sorted(skill_by_query[key])
        if preferred_surfaces[key]:
            query_origin = "canonical_label"
            query = sorted(preferred_surfaces[key], key=lambda value: (len(value), value))[0]
            strata = ["exact_preferred_label"]
        else:
            query_origin = "alternative_label"
            query = sorted(alternative_surfaces[key], key=lambda value: (len(value), value))[0]
            strata = ["alternative_label"]
        identities = [
            {"kind": "skill", "concept_id": sid, "label": str(by_id[sid].get("preferred_label") or "")}
            for sid in ids
        ]
        kv_cases.append(make_case(
            case_id=f"kv.canonical.{index:05d}",
            version=version,
            product="KV",
            query=query,
            query_origin=query_origin,
            strata=strata,
            identities=identities,
            evidence=[canonical_evidence(version_str)],
        ))

    # --------------------------------------------- excluded-title review population, not truth
    excluded_review: list[dict[str, Any]] = []
    for job_id in sorted(active_jobs - published_job_ids, key=lambda cid: (norm(by_id[cid].get("preferred_label")), cid)):
        concept = by_id[job_id]
        label = str(concept.get("preferred_label") or "")
        parents = [
            rid for rid in relation_ids(concept, "related")
            if by_id.get(rid, {}).get("type") == "occupation-name"
        ]
        if len(parents) > 3:
            reason = "too_many_parents"
        elif parents and all(norm(label) in norm(by_id[parent].get("preferred_label")) for parent in parents):
            reason = "redundant_label"
        else:
            raise RuntimeError(f"excluded title {job_id} is not explained by measured YV policy")
        excluded_review.append({
            "taxonomy_version": version,
            "query": label,
            "query_origin": "canonical_label",
            "stratum": "yv_excluded_title_router",
            "job_title_id": job_id,
            "yv_exclusion_reason": reason,
            "candidate_occupation_identities": [
                {
                    "kind": "occupation-name",
                    "concept_id": parent,
                    "label": str(by_id[parent].get("preferred_label") or ""),
                }
                for parent in sorted(parents)
            ],
            "adjudication": "PENDING_HUMAN_REVIEW",
            "note": "Candidate parents are taxonomy relation evidence, not benchmark destination truth.",
        })

    if len(excluded_review) != 205:
        raise RuntimeError(f"expected 205 excluded YV titles, got {len(excluded_review)}")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for filename, rows in (
        ("yv-exact-labels.jsonl", yv_cases),
        ("kv-canonical-labels.jsonl", kv_cases),
        ("yv-excluded-title-review-candidates.jsonl", excluded_review),
    ):
        with (out / filename).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    manifest = {
        "schema_version": 2,
        "taxonomy_version": version,
        "generated_at": now_utc(),
        "sources": {
            "taxonomy": {"url": taxonomy_url, "sha256": hashlib.sha256(taxonomy_body).hexdigest()},
            "yrkesvaljaren": {"url": yv_url, "sha256": hashlib.sha256(yv_body).hexdigest()},
        },
        "scored_seed_cases": {
            "yv_exact_label_queries": len(yv_cases),
            "kv_canonical_or_alternative_label_queries": len(kv_cases),
            "total": len(yv_cases) + len(kv_cases),
        },
        "pending_review_populations": {
            "yv_generator_excluded_titles": len(excluded_review),
        },
        "authority_boundary": (
            "only canonical preferred/alternative-label cases are auto-scored; YV scored identities additionally require explicit published-YV product admission; YV excluded titles remain a separate human-review candidate population"
        ),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
