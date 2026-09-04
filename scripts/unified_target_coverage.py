#!/usr/bin/env python3
"""Compose a per-target semantic coverage matrix for YV and KV.

The matrix is diagnostic, not a ranking score. It preserves direct vs contextual
support and source provenance, and it fails closed if an accepted v31 source hash
has drifted from research/coverage/source-adapters.json.
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

import zstandard as zstd

UA = "semantic-taxonomy-search-unified-coverage/0.1"
KV_LAYERS = ("regulated_skills", "essential_skills", "optional_skills", "calculated_skills")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def fetch(url: str, timeout: int = 300) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "*/*", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def load_json_bytes(wire: bytes, compressed: bool = False) -> tuple[bytes, Any]:
    raw = zstd.ZstdDecompressor().decompress(wire) if compressed else wire
    return raw, json.loads(raw)


def relation_ids(concept: dict[str, Any], field: str) -> list[str]:
    value = concept.get(field)
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, dict) and item.get("id"):
            result.append(str(item["id"]))
        elif isinstance(item, str) and item:
            result.append(item)
    return result


def as_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            label = item.get("label") or item.get("value") or item.get("preferred_label")
            if isinstance(label, str) and label.strip():
                result.append(label.strip())
    return result


def real_definition(concept: dict[str, Any]) -> bool:
    definition = norm(concept.get("definition"))
    return bool(definition and definition != norm(concept.get("preferred_label")))


def expected_hash(registry: dict[str, Any], adapter_id: str) -> str:
    adapters = registry.get("adapters")
    if not isinstance(adapters, list):
        raise RuntimeError("source adapter registry missing adapters list")
    matches = [item for item in adapters if isinstance(item, dict) and item.get("id") == adapter_id]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one adapter {adapter_id!r}, got {len(matches)}")
    digest = matches[0].get("source_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise RuntimeError(f"adapter {adapter_id!r} has no accepted source_sha256")
    return digest


def checked_fetch(url: str, expected: str) -> bytes:
    wire = fetch(url)
    actual = hashlib.sha256(wire).hexdigest()
    if actual != expected:
        raise RuntimeError(f"source drift for {url}: expected {expected}, got {actual}")
    return wire


def typed_relation_count(
    concept: dict[str, Any], field: str, target_type: str, by_id: dict[str, dict[str, Any]]
) -> int:
    return sum(1 for rid in relation_ids(concept, field) if by_id.get(rid, {}).get("type") == target_type)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31")
    parser.add_argument("--registry", default="research/coverage/source-adapters.json")
    parser.add_argument("--output-dir", default="artifacts/unified-target-coverage-v31")
    args = parser.parse_args()

    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    if str(registry.get("target_taxonomy_version")) != version:
        raise RuntimeError("source registry taxonomy version does not match requested matrix version")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    urls = {
        "taxonomy-common-relations": (
            "https://data.jobtechdev.se/taxonomy/version/"
            f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
        ),
        "yrkesvaljaren": f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{version}.json",
        "skill-selector": f"https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t{version}.json",
        "relevant-skills": f"https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/v1/relevanta-kompetenser-t{version}.json.zst",
        "ad-keyword-corpus": f"https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t{version}/relevans-nyckelord.json.zst",
        "nearby-occupations": f"https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t{version}/narliggande-yrken.json",
    }

    wires = {
        adapter_id: checked_fetch(url, expected_hash(registry, adapter_id))
        for adapter_id, url in urls.items()
    }
    _, taxonomy_doc = load_json_bytes(wires["taxonomy-common-relations"])
    _, yv_doc = load_json_bytes(wires["yrkesvaljaren"])
    _, kv_doc = load_json_bytes(wires["skill-selector"])
    _, relevant_doc = load_json_bytes(wires["relevant-skills"], compressed=True)
    _, ad_doc = load_json_bytes(wires["ad-keyword-corpus"], compressed=True)
    _, nearby_doc = load_json_bytes(wires["nearby-occupations"])

    concepts = taxonomy_doc.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy snapshot missing data.concepts")
    by_id = {
        str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")
    }
    ids_by_type: dict[str, set[str]] = collections.defaultdict(set)
    for cid, concept in by_id.items():
        ids_by_type[str(concept.get("type") or "")].add(cid)

    active_occupations = ids_by_type["occupation-name"]
    active_jobs = ids_by_type["job-title"]
    active_skills = ids_by_type["skill"]

    # ------------------------------------------------------------ YV identity universe
    yv_rows = yv_doc.get("data")
    if not isinstance(yv_rows, list):
        raise RuntimeError("YV missing data list")
    yv_occ_weight: dict[str, float | None] = {}
    yv_job_rows: list[dict[str, Any]] = []
    published_job_ids: set[str] = set()
    title_context_count = collections.Counter()
    for row in yv_rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        cid = str(row["id"])
        ctype = str(row.get("type") or "")
        try:
            weight: float | None = float(row.get("weight"))
        except (TypeError, ValueError):
            weight = None
        if ctype == "occupation-name":
            yv_occ_weight[cid] = weight
        elif ctype == "job-title":
            parent = str(row.get("occupation_name_id") or "")
            if parent not in active_occupations:
                raise RuntimeError(f"YV job-title {cid} has invalid occupation parent {parent!r}")
            published_job_ids.add(cid)
            title_context_count[cid] += 1
            yv_job_rows.append({"id": cid, "parent": parent, "weight": weight})

    if set(yv_occ_weight) != active_occupations:
        raise RuntimeError("YV occupation universe is not exactly active occupation-name universe")

    # ---------------------------------------------------------- KV inverted context counts
    kv_data = kv_doc.get("data")
    if not isinstance(kv_data, dict):
        raise RuntimeError("KV missing data object")
    kv_counts: dict[str, dict[str, collections.Counter[str]]] = {
        layer: {
            "occupation-name": collections.Counter(),
            "ssyk-level-4": collections.Counter(),
        }
        for layer in KV_LAYERS
    }
    transferable_ids: set[str] = set()
    transferable = kv_data.get("transferable_skills")
    if isinstance(transferable, dict):
        transferable_ids = {str(v) for v in transferable.values() if str(v) in active_skills}

    for context_id, record in kv_data.items():
        if context_id == "transferable_skills" or not isinstance(record, dict):
            continue
        context_type = str(record.get("type") or "")
        if context_type not in {"occupation-name", "ssyk-level-4"}:
            continue
        for layer in KV_LAYERS:
            mapping = record.get(layer) or {}
            if not isinstance(mapping, dict):
                raise RuntimeError(f"KV {layer} for {context_id} is not an object")
            for skill_id in mapping.values():
                sid = str(skill_id)
                if sid not in active_skills:
                    raise RuntimeError(f"KV references non-active skill {sid}")
                kv_counts[layer][context_type][sid] += 1

    # ----------------------------------------------------- Relevanta skill context inversion
    relevant_data = relevant_doc.get("data")
    if not isinstance(relevant_data, dict):
        raise RuntimeError("Relevanta kompetenser missing data object")
    relevant_by_occ_count: dict[str, int] = {}
    relevant_occurrences = collections.Counter()
    for occ_id, record in relevant_data.items():
        if occ_id not in active_occupations:
            raise RuntimeError(f"Relevanta contains unknown occupation {occ_id}")
        items = record.get("relevant_skills") if isinstance(record, dict) else None
        if not isinstance(items, list):
            raise RuntimeError(f"Relevanta skills for {occ_id} is not a list")
        relevant_by_occ_count[occ_id] = len(items)
        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            sid = str(item["id"])
            if sid not in active_skills:
                raise RuntimeError(f"Relevanta references non-active skill {sid}")
            relevant_occurrences[sid] += 1

    # ----------------------------------------------------- observed ad language by occupation
    ad_data = ad_doc.get("data")
    if not isinstance(ad_data, dict) or not isinstance(ad_data.get("occupation_name"), dict):
        raise RuntimeError("ad keyword corpus missing occupation_name map")
    ad_keywords: dict[str, int] = {}
    for occ_id, record in ad_data["occupation_name"].items():
        if occ_id not in active_occupations:
            raise RuntimeError(f"ad keyword corpus contains unknown occupation {occ_id}")
        keywords = record.get("keywords") if isinstance(record, dict) else None
        if not isinstance(keywords, dict):
            raise RuntimeError(f"ad keyword record {occ_id} has invalid keywords")
        ad_keywords[occ_id] = len(keywords)

    # ---------------------------------------------------------- nearby by source occupation
    nearby_data = nearby_doc.get("data")
    if not isinstance(nearby_data, dict):
        raise RuntimeError("nearby occupations missing data object")
    nearby_count: dict[str, int] = {}
    for occ_id, record in nearby_data.items():
        if occ_id not in active_occupations:
            raise RuntimeError(f"nearby source is not active occupation {occ_id}")
        similar = record.get("similar") if isinstance(record, dict) else None
        if not isinstance(similar, list):
            raise RuntimeError(f"nearby record {occ_id} has invalid similar list")
        nearby_count[occ_id] = len(similar)

    # ------------------------------------------------------- occupation reusable dimensions
    occupation_support: dict[str, dict[str, Any]] = {}
    for occ_id in sorted(active_occupations):
        concept = by_id[occ_id]
        occupation_support[occ_id] = {
            "real_definition": real_definition(concept),
            "alternative_labels": len(as_labels(concept.get("alternative_labels"))),
            "job_title_relations": typed_relation_count(concept, "related", "job-title", by_id),
            "keyword_relations": typed_relation_count(concept, "related", "keyword", by_id),
            "esco_mappings": sum(
                typed_relation_count(concept, field, "esco-occupation", by_id)
                for field in ("exact_match", "broad_match", "narrow_match", "close_match")
            ),
            "substitutability_relations": (
                typed_relation_count(concept, "substitutes", "occupation-name", by_id)
                + typed_relation_count(concept, "substituted_by", "occupation-name", by_id)
            ),
            "relevant_skill_count": relevant_by_occ_count.get(occ_id, 0),
            "kv_calculated_skill_count": 0,
            "ad_keyword_count": ad_keywords.get(occ_id, 0),
            "nearby_occupation_count": nearby_count.get(occ_id, 0),
        }
        record = kv_data.get(occ_id)
        if isinstance(record, dict):
            mapping = record.get("calculated_skills") or {}
            if isinstance(mapping, dict):
                occupation_support[occ_id]["kv_calculated_skill_count"] = len(mapping)

    # ------------------------------------------------------------- YV occupation rows
    yv_occupations: list[dict[str, Any]] = []
    strata: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    for occ_id in sorted(active_occupations, key=lambda cid: (norm(by_id[cid].get("preferred_label")), cid)):
        concept = by_id[occ_id]
        support = occupation_support[occ_id]
        canonical_text_poor = not support["real_definition"] and support["alternative_labels"] == 0
        no_observed_language = support["ad_keyword_count"] == 0
        no_skill_context = support["relevant_skill_count"] == 0 and support["kv_calculated_skill_count"] == 0
        sparse_graph = (
            support["job_title_relations"] == 0
            and support["nearby_occupation_count"] == 0
            and support["substitutability_relations"] == 0
        )
        tags = []
        if canonical_text_poor:
            tags.append("canonical_text_poor")
        if no_observed_language:
            tags.append("no_observed_ad_language")
        if no_skill_context:
            tags.append("no_skill_context")
        if sparse_graph:
            tags.append("sparse_occupation_context")
        if canonical_text_poor and no_observed_language:
            tags.append("text_poor_without_observed_language")
        row = {
            "target_key": f"occupation-name:{occ_id}",
            "product": "YV",
            "kind": "occupation-name",
            "concept_id": occ_id,
            "preferred_label": concept.get("preferred_label"),
            "weight": yv_occ_weight[occ_id],
            "direct": {
                "canonical_preferred_label": True,
                "canonical_real_definition": support["real_definition"],
                "canonical_alternative_label_count": support["alternative_labels"],
                "taxonomy_job_title_relation_count": support["job_title_relations"],
                "taxonomy_keyword_relation_count": support["keyword_relations"],
                "taxonomy_esco_mapping_count": support["esco_mappings"],
                "taxonomy_substitutability_relation_count": support["substitutability_relations"],
            },
            "contextual": {
                "relevanta_skill_count": support["relevant_skill_count"],
                "kv_calculated_skill_count": support["kv_calculated_skill_count"],
                "ad_keyword_count": support["ad_keyword_count"],
                "nearby_occupation_count": support["nearby_occupation_count"],
            },
            "gap_tags": tags,
        }
        yv_occupations.append(row)
        for tag in tags:
            strata[tag].append({"target_key": row["target_key"], "preferred_label": str(row["preferred_label"] or "")})

    # -------------------------------------------------------------- YV job-title rows
    yv_jobs: list[dict[str, Any]] = []
    for item in sorted(
        yv_job_rows,
        key=lambda r: (norm(by_id[r["id"]].get("preferred_label")), norm(by_id[r["parent"]].get("preferred_label")), r["id"], r["parent"]),
    ):
        job = by_id[item["id"]]
        parent = by_id[item["parent"]]
        parent_support = occupation_support[item["parent"]]
        own_text_poor = not real_definition(job) and len(as_labels(job.get("alternative_labels"))) == 0
        parent_context_thin = (
            not parent_support["real_definition"]
            and parent_support["ad_keyword_count"] == 0
            and parent_support["relevant_skill_count"] == 0
            and parent_support["kv_calculated_skill_count"] == 0
        )
        tags = []
        if own_text_poor:
            tags.append("job_title_no_own_semantic_text")
        if title_context_count[item["id"]] > 1:
            tags.append("job_title_multi_parent")
        if parent_context_thin:
            tags.append("job_title_thin_parent_context")
        target_key = f"job-title:{item['id']}@occupation-name:{item['parent']}"
        row = {
            "target_key": target_key,
            "product": "YV",
            "kind": "job-title",
            "concept_id": item["id"],
            "occupation_name_id": item["parent"],
            "preferred_label": job.get("preferred_label"),
            "occupation_name_preferred_label": parent.get("preferred_label"),
            "weight": item["weight"],
            "title_context_count": title_context_count[item["id"]],
            "direct": {
                "canonical_preferred_label": True,
                "canonical_real_definition": real_definition(job),
                "canonical_alternative_label_count": len(as_labels(job.get("alternative_labels"))),
            },
            "contextual_from_exact_occupation": parent_support,
            "gap_tags": tags,
        }
        yv_jobs.append(row)
        for tag in tags:
            strata[tag].append({"target_key": target_key, "preferred_label": str(job.get("preferred_label") or "")})

    # ---------------------------------------------------- retrieval-only excluded YV titles
    excluded_titles: list[dict[str, Any]] = []
    missing_job_ids = active_jobs - published_job_ids
    for job_id in sorted(missing_job_ids, key=lambda cid: (norm(by_id[cid].get("preferred_label")), cid)):
        concept = by_id[job_id]
        parents = [rid for rid in relation_ids(concept, "related") if by_id.get(rid, {}).get("type") == "occupation-name"]
        label = str(concept.get("preferred_label") or "")
        if len(parents) > 3:
            reason = "too_many_parents"
        elif parents and all(norm(label) in norm(by_id[parent].get("preferred_label")) for parent in parents):
            reason = "redundant_label"
        else:
            raise RuntimeError(f"active YV-excluded title {job_id} is not explained by measured generator policy")
        excluded_titles.append({
            "kind": "job-title",
            "concept_id": job_id,
            "preferred_label": label,
            "retrieval_only": True,
            "yv_exclusion_reason": reason,
            "occupation_name_ids": sorted(parents),
        })
    if len(excluded_titles) != 205:
        raise RuntimeError(f"expected 205 generator-excluded active job titles, got {len(excluded_titles)}")

    # ---------------------------------------------------------------------- KV rows
    kv_skills: list[dict[str, Any]] = []
    for sid in sorted(active_skills, key=lambda cid: (norm(by_id[cid].get("preferred_label")), cid)):
        concept = by_id[sid]
        real_def = real_definition(concept)
        alt_count = len(as_labels(concept.get("alternative_labels")))
        hidden_count = len(as_labels(concept.get("hidden_labels")))
        layer_occ = {layer: kv_counts[layer]["occupation-name"][sid] for layer in KV_LAYERS}
        layer_ssyk = {layer: kv_counts[layer]["ssyk-level-4"][sid] for layer in KV_LAYERS}
        relevant_count = relevant_occurrences[sid]
        curated_context = layer_occ["regulated_skills"] + layer_occ["essential_skills"] + layer_occ["optional_skills"]
        derived_context = layer_occ["calculated_skills"] + relevant_count
        all_product_context = curated_context + derived_context
        canonical_text_poor = not real_def and alt_count == 0 and hidden_count == 0
        ssyk_relations = typed_relation_count(concept, "related", "ssyk-level-4", by_id)
        tags = []
        if canonical_text_poor:
            tags.append("skill_canonical_text_poor")
        if all_product_context == 0:
            tags.append("skill_no_yvkv_relevance_context")
        if canonical_text_poor and all_product_context == 0:
            tags.append("skill_critical_sparse")
        if canonical_text_poor and curated_context == 0 and derived_context > 0:
            tags.append("skill_text_poor_derived_only")
        if ssyk_relations == 0:
            tags.append("skill_no_ssyk_context")
        if sid in transferable_ids:
            tags.append("skill_transferable")
        row = {
            "target_key": f"skill:{sid}",
            "product": "KV",
            "kind": "skill",
            "concept_id": sid,
            "preferred_label": concept.get("preferred_label"),
            "direct": {
                "canonical_preferred_label": True,
                "canonical_real_definition": real_def,
                "canonical_alternative_label_count": alt_count,
                "canonical_hidden_label_count": hidden_count,
                "skill_headline_parent_count": typed_relation_count(concept, "broader", "skill-headline", by_id),
                "ssyk4_relation_count": ssyk_relations,
                "esco_mapping_count": sum(
                    typed_relation_count(concept, field, "esco-skill", by_id)
                    for field in ("exact_match", "broad_match", "narrow_match", "close_match")
                ),
            },
            "product_context": {
                "kv_occupation_context_occurrences": layer_occ,
                "kv_ssyk4_context_occurrences": layer_ssyk,
                "relevanta_occupation_occurrences": relevant_count,
                "transferable": sid in transferable_ids,
            },
            "gap_tags": tags,
        }
        kv_skills.append(row)
        for tag in tags:
            strata[tag].append({"target_key": row["target_key"], "preferred_label": str(row["preferred_label"] or "")})

    # --------------------------------------------------------------------- outputs
    for name, rows in (
        ("yv-occupations.jsonl", yv_occupations),
        ("yv-job-title-contexts.jsonl", yv_jobs),
        ("kv-skills.jsonl", kv_skills),
        ("yv-retrieval-only-excluded-titles.jsonl", excluded_titles),
    ):
        with (out / name).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    stratum_summary = {
        tag: {
            "count": len(items),
            "examples": sorted(items, key=lambda item: (norm(item["preferred_label"]), item["target_key"]))[:30],
        }
        for tag, items in sorted(strata.items())
    }
    aggregate = {
        "schema_version": 1,
        "taxonomy_version": version,
        "generated_at": now_utc(),
        "matrix_semantics": "diagnostic dimensions and explicit gap strata; no composite semantic score",
        "source_hashes": {
            adapter_id: hashlib.sha256(wire).hexdigest() for adapter_id, wire in wires.items()
        },
        "target_counts": {
            "yv_occupation_name": len(yv_occupations),
            "yv_job_title_context_rows": len(yv_jobs),
            "yv_unique_published_job_title_ids": len(published_job_ids),
            "yv_retrieval_only_excluded_active_job_titles": len(excluded_titles),
            "kv_active_skills": len(kv_skills),
        },
        "gap_strata": stratum_summary,
        "pending_not_composed": [
            "Yrkesinformation legacy-to-v31 semantic text attachment until canonical join is resolved",
            "deprecated historical vocabulary until replacement-graph measurement succeeds",
            "observed YV query frequency as a per-target signal except where separately and safely joined",
        ],
    }
    (out / "aggregate.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    summary = [
        f"# Unified target semantic coverage — taxonomy v{version}",
        "",
        "This is a diagnostic matrix, not a ranking score.",
        "",
        f"- YV occupation identities: **{len(yv_occupations):,}**",
        f"- YV job-title-in-occupation-context identities: **{len(yv_jobs):,}**",
        f"- Retrieval-only active YV-excluded titles: **{len(excluded_titles):,}**",
        f"- KV skill identities: **{len(kv_skills):,}**",
        "",
        "## Gap strata",
        "",
        "| stratum | targets |",
        "|---|---:|",
    ]
    for tag, info in stratum_summary.items():
        summary.append(f"| `{tag}` | {info['count']:,} |")
    summary += [
        "",
        "## Authority boundary",
        "",
        "- Direct canonical text is kept separate from occupation/context-inherited evidence.",
        "- KV native/selector layers remain separate from calculated/Relevanta evidence.",
        "- YV excluded active titles are retrieval-only vocabulary, never destination rows.",
        "- No opaque aggregate score is emitted.",
        "- Accepted source hashes are checked before composition; drift fails closed.",
        "",
    ]
    (out / "summary.md").write_text("\n".join(summary), encoding="utf-8")
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
