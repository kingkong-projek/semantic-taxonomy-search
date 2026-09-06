#!/usr/bin/env python3
"""Build the compact source-truth benchmark around the frozen P80 priority core.

The suite deliberately uses only source-attested query text:
- canonical preferred labels for every P80 target;
- canonical definitions that are non-empty and not label copies;
- canonical alternative labels.

No synthetic wording, inferred query->target joins, or corpus popularity signal becomes
destination ground truth. Historical occurrence counts select the priority population
only; JobTech Taxonomy v31 supplies semantic truth; published YV supplies YV product
admission.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

UA = "semantic-taxonomy-search-p80-benchmark/0.1"


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
        raise RuntimeError(f"adapter {adapter_id!r} has no accepted source_sha256")
    return digest


def checked_json(url: str, expected_sha256: str) -> tuple[bytes, dict[str, Any]]:
    body = fetch(url)
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected_sha256:
        raise RuntimeError(f"source drift for {url}: expected {expected_sha256}, got {actual}")
    doc = json.loads(body)
    if not isinstance(doc, dict):
        raise RuntimeError(f"expected JSON object from {url}")
    return body, doc


def as_labels(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if value in (None, ""):
        return []
    text = str(value).strip()
    return [text] if text else []


def p80_ids(section: dict[str, Any], expected_count: int) -> list[str]:
    count = int(section.get("thresholds", {}).get("p80", {}).get("concept_count") or -1)
    ranked = section.get("ranked_p95")
    if count != expected_count:
        raise RuntimeError(f"unexpected frozen P80 count: expected {expected_count}, got {count}")
    if not isinstance(ranked, list) or len(ranked) < count:
        raise RuntimeError("frozen Pareto aggregate has incomplete ranked_p95 membership")
    result = [str(row.get("concept_id") or "") for row in ranked[:count] if isinstance(row, dict)]
    if len(result) != count or len(set(result)) != count or any(not cid for cid in result):
        raise RuntimeError("invalid or duplicate P80 concept membership")
    return result


def identity(kind: str, concept: dict[str, Any]) -> dict[str, str]:
    return {
        "kind": kind,
        "concept_id": str(concept["id"]),
        "label": str(concept.get("preferred_label") or ""),
    }


def canonical_evidence(version: str, role: str, note: str) -> dict[str, str]:
    return {
        "source": f"JobTech Taxonomy v{version}",
        "provenance": "canonical",
        "role": role,
        "note": note,
    }


def yv_admission_evidence(version: str) -> dict[str, str]:
    return {
        "source": f"Published Yrkesväljaren v{version}",
        "provenance": "behavioral",
        "role": "product_admission",
        "note": "P80 occupation identity is explicitly admitted by the published YV read model.",
    }


def add_surface(
    groups: dict[str, dict[str, Any]],
    *,
    query: str,
    origin: str,
    stratum: str,
    target: dict[str, str],
) -> None:
    key = norm(query)
    if not key:
        return
    group = groups.setdefault(key, {"surfaces": set(), "origins": set(), "strata": set(), "targets": {}})
    group["surfaces"].add(query.strip())
    group["origins"].add(origin)
    group["strata"].add(stratum)
    group["targets"][(target["kind"], target["concept_id"])] = target


def choose_origin(origins: set[str]) -> str:
    for value in ("canonical_label", "canonical_definition", "alternative_label"):
        if value in origins:
            return value
    raise RuntimeError(f"unsupported source-truth origins: {origins}")


def materialize(
    product: str,
    groups: dict[str, dict[str, Any]],
    version: int,
    version_str: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, key in enumerate(sorted(groups), 1):
        group = groups[key]
        targets = [group["targets"][k] for k in sorted(group["targets"])]
        origin = choose_origin(group["origins"])
        query = sorted(group["surfaces"], key=lambda s: (len(s), s))[0]
        evidence = [
            canonical_evidence(version_str, "query_origin", f"Source-attested {origin} text."),
            canonical_evidence(version_str, "destination_ground_truth", "Query text is attached directly to the scored canonical identity in the accepted v31 taxonomy snapshot."),
        ]
        if product == "YV":
            evidence.append(yv_admission_evidence(version_str))
        rows.append({
            "id": f"{product.lower()}.p80.{index:04d}",
            "taxonomy_version": version,
            "product": product,
            "query": query,
            "query_language": "sv",
            "query_origin": origin,
            "strata": sorted(group["strata"]),
            "expected_intent": "SINGLE" if len(targets) == 1 else "AMBIGUOUS",
            "must": targets,
            "acceptable": [],
            "must_not": [],
            "top_k": max(10, len(targets)),
            "allow_abstention": False,
            "source_evidence": evidence,
            "adjudication": {
                "status": "AUTO_HIGH_CONFIDENCE",
                "reviewer_count": 0,
                "agreement": "UNREVIEWED",
            },
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--output-dir", default="artifacts/p80-benchmark-v31")
    args = ap.parse_args()

    version_str = str(args.version)
    version = int(version_str)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    if str(registry.get("target_taxonomy_version")) != version_str:
        raise RuntimeError("registry taxonomy version mismatch")
    if str(pareto.get("taxonomy_version")) != version_str:
        raise RuntimeError("Pareto taxonomy version mismatch")

    p80_occ = p80_ids(pareto["occupation_name"], 159)
    p80_skills = p80_ids(pareto["skill"], 316)

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version_str}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    yv_url = f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{version_str}.json"
    taxonomy_body, taxonomy_doc = checked_json(taxonomy_url, expected_hash(registry, "taxonomy-common-relations"))
    yv_body, yv_doc = checked_json(yv_url, expected_hash(registry, "yrkesvaljaren"))

    concepts = taxonomy_doc.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy snapshot missing data.concepts")
    by_id = {
        str(c["id"]): c
        for c in concepts
        if isinstance(c, dict) and c.get("id")
    }

    for cid in p80_occ:
        if by_id.get(cid, {}).get("type") != "occupation-name":
            raise RuntimeError(f"P80 occupation {cid} is not active occupation-name in taxonomy")
    for cid in p80_skills:
        if by_id.get(cid, {}).get("type") != "skill":
            raise RuntimeError(f"P80 skill {cid} is not active skill in taxonomy")

    yv_rows = yv_doc.get("data")
    if not isinstance(yv_rows, list):
        raise RuntimeError("published YV missing data list")
    published_occ = {
        str(row.get("id"))
        for row in yv_rows
        if isinstance(row, dict) and row.get("type") == "occupation-name" and row.get("id")
    }
    missing_yv = sorted(set(p80_occ) - published_occ)
    if missing_yv:
        raise RuntimeError(f"P80 occupation identities not admitted by published YV: {missing_yv}")

    yv_groups: dict[str, dict[str, Any]] = {}
    kv_groups: dict[str, dict[str, Any]] = {}
    target_surface_stats = collections.Counter()

    def add_target(groups: dict[str, dict[str, Any]], cid: str, kind: str, product: str) -> None:
        concept = by_id[cid]
        target = identity(kind, concept)
        label = str(concept.get("preferred_label") or "").strip()
        if not label:
            raise RuntimeError(f"P80 target {cid} has no preferred label")
        add_surface(groups, query=label, origin="canonical_label", stratum="exact_preferred_label", target=target)
        target_surface_stats[f"{product}.preferred"] += 1

        definition = str(concept.get("definition") or "").strip()
        if definition and norm(definition) != norm(label):
            strata = ["long_description"]
            if product == "KV" and norm(label) not in norm(definition):
                strata.append("kv_description_without_canonical_term")
            for stratum in strata:
                add_surface(groups, query=definition, origin="canonical_definition", stratum=stratum, target=target)
            target_surface_stats[f"{product}.definition"] += 1

        for alternative in as_labels(concept.get("alternative_labels")):
            if norm(alternative) == norm(label):
                continue
            add_surface(groups, query=alternative, origin="alternative_label", stratum="alternative_label", target=target)
            target_surface_stats[f"{product}.alternative"] += 1

    for cid in p80_occ:
        add_target(yv_groups, cid, "occupation-name", "YV")
    for cid in p80_skills:
        add_target(kv_groups, cid, "skill", "KV")

    yv_cases = materialize("YV", yv_groups, version, version_str)
    kv_cases = materialize("KV", kv_groups, version, version_str)
    total = len(yv_cases) + len(kv_cases)
    if total < 500 or total > 1000:
        raise RuntimeError(f"P80 source-truth suite should stay compact in [500,1000], got {total}")

    represented_yv = {x["concept_id"] for case in yv_cases for x in case["must"]}
    represented_kv = {x["concept_id"] for case in kv_cases for x in case["must"]}
    if represented_yv != set(p80_occ):
        raise RuntimeError("not every P80 YV identity is represented in benchmark truth")
    if represented_kv != set(p80_skills):
        raise RuntimeError("not every P80 KV identity is represented in benchmark truth")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for filename, rows in (("yv-p80-source-truth.jsonl", yv_cases), ("kv-p80-source-truth.jsonl", kv_cases)):
        with (out / filename).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def origin_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
        return dict(sorted(collections.Counter(row["query_origin"] for row in rows).items()))

    manifest = {
        "schema_version": 1,
        "taxonomy_version": version,
        "selection": {
            "yv_p80_occupation_targets": len(p80_occ),
            "kv_p80_skill_targets": len(p80_skills),
            "total_p80_targets": len(p80_occ) + len(p80_skills),
            "rule": "Frozen Historical-API P80 popularity envelope selects targets; accepted taxonomy/YV sources alone supply benchmark truth.",
        },
        "cases": {
            "YV": len(yv_cases),
            "KV": len(kv_cases),
            "total": total,
            "origin_counts": {"YV": origin_counts(yv_cases), "KV": origin_counts(kv_cases)},
        },
        "source_attested_target_surfaces": dict(sorted(target_surface_stats.items())),
        "sources": {
            "pareto_frozen_repo_file": str(args.pareto),
            "taxonomy": {"url": taxonomy_url, "sha256": hashlib.sha256(taxonomy_body).hexdigest()},
            "yrkesvaljaren": {"url": yv_url, "sha256": hashlib.sha256(yv_body).hexdigest()},
        },
        "authority_boundary": "No observed-query, ad-derived, historical popularity, model-derived or synthetic signal is used as destination ground truth. Canonical definitions/labels bind only to their own canonical identities; YV positives also require published product admission.",
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
