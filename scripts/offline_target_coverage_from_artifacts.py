#!/usr/bin/env python3
"""Compose a fail-closed tri-state target matrix from accepted v31 artifacts.

This is an offline recovery path for already accepted pre-transfer measurement
artifacts. It deliberately does not replace unified_target_coverage.py. Missing
per-ID dimensions remain UNKNOWN; aggregate coverage is never imputed to IDs.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, Iterable

KNOWN_TRUE = "KNOWN_TRUE"
KNOWN_FALSE = "KNOWN_FALSE"
UNKNOWN = "UNKNOWN"

EXPECTED = {
    "taxonomy_version": "31",
    "taxonomy_common_sha256": "634fd9d848a172747e54e3e487160a912ae6c0fcb8219c50998767c8c9aacbcc",
    "yv_sha256": "1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49",
    "kv_sha256": "da83f26bf316971caa407364d8feae6f791203bff5758e674cace3d919e4b524",
}

ARTIFACTS = {
    "native_text": {"run_id": 33860719240, "artifact_id": 9932067713, "name": "semantic-coverage-v31"},
    "common_relations": {"run_id": 33861288432, "artifact_id": 9932211469, "name": "common-relations-v31"},
    "selector": {"run_id": 33863555154, "artifact_id": 9933045595, "name": "selector-coverage-v31"},
    "selector_gaps": {"run_id": 33864077660, "artifact_id": 9933248443, "name": "selector-gaps-v31"},
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def state(value: bool) -> str:
    return KNOWN_TRUE if value else KNOWN_FALSE


def archive_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_zip_json(path: Path, member: str) -> Any:
    with zipfile.ZipFile(path) as zf:
        with zf.open(member) as fh:
            return json.load(fh)


def iter_zip_jsonl(path: Path, member: str) -> Iterable[dict[str, Any]]:
    with zipfile.ZipFile(path) as zf:
        with zf.open(member) as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                row = json.loads(raw)
                if not isinstance(row, dict):
                    raise RuntimeError(f"{path}:{member} contains a non-object row")
                yield row


def load_rows(path: Path, member: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in iter_zip_jsonl(path, member):
        cid = str(row.get("id") or "")
        require(bool(cid), f"{path}:{member} row missing id")
        require(cid not in rows, f"duplicate id {cid} in {path}:{member}")
        rows[cid] = row
    return rows


def count(row: dict[str, Any], key: str) -> int:
    value = row.get(key, 0)
    return int(value) if isinstance(value, (int, float)) else 0


def esco_count(row: dict[str, Any], target: str) -> int:
    return sum(
        count(row, f"{relation}__{target}")
        for relation in ("exact_match", "broad_match", "narrow_match", "close_match")
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-text-artifact", type=Path, required=True)
    parser.add_argument("--common-relations-artifact", type=Path, required=True)
    parser.add_argument("--selector-artifact", type=Path, required=True)
    parser.add_argument("--selector-gaps-artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/offline-target-coverage-v31"))
    args = parser.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    native_manifest = read_zip_json(args.native_text_artifact, "source-manifest.json")
    common_aggregate = read_zip_json(args.common_relations_artifact, "aggregate.json")
    selector_aggregate = read_zip_json(args.selector_artifact, "aggregate.json")
    gaps_aggregate = read_zip_json(args.selector_gaps_artifact, "aggregate.json")

    require(str(native_manifest.get("taxonomy_version")) == EXPECTED["taxonomy_version"], "native-text taxonomy version mismatch")
    warnings = native_manifest.get("warnings") or []
    require(
        any("GraphQL relation extraction failed" in str(warning) for warning in warnings),
        "native-text artifact is not the known text-only artifact with invalid GraphQL relations",
    )
    require(common_aggregate.get("snapshot", {}).get("sha256") == EXPECTED["taxonomy_common_sha256"], "common-relations snapshot hash mismatch")
    require(str(common_aggregate.get("taxonomy_version")) == EXPECTED["taxonomy_version"], "common-relations taxonomy version mismatch")
    require(selector_aggregate.get("sources", {}).get("taxonomy", {}).get("sha256") == EXPECTED["taxonomy_common_sha256"], "selector taxonomy hash mismatch")
    require(selector_aggregate.get("sources", {}).get("yrkesvaljaren", {}).get("sha256") == EXPECTED["yv_sha256"], "selector YV hash mismatch")
    require(selector_aggregate.get("sources", {}).get("kompetensvaljaren", {}).get("sha256") == EXPECTED["kv_sha256"], "selector KV hash mismatch")
    require(gaps_aggregate.get("sources", {}).get("taxonomy_v31", {}).get("sha256") == EXPECTED["taxonomy_common_sha256"], "gap taxonomy hash mismatch")
    require(gaps_aggregate.get("sources", {}).get("yv_v31", {}).get("sha256") == EXPECTED["yv_sha256"], "gap YV hash mismatch")
    require(gaps_aggregate.get("sources", {}).get("kv_v31", {}).get("sha256") == EXPECTED["kv_sha256"], "gap KV hash mismatch")

    native = load_rows(args.native_text_artifact, "concepts.jsonl")
    common = load_rows(args.common_relations_artifact, "concepts.jsonl")
    require(set(native) == set(common), "native-text and common-relations concept universes differ")
    for cid in native:
        require(native[cid].get("type") == common[cid].get("type"), f"type mismatch for {cid}")
        require(native[cid].get("preferred_label") == common[cid].get("preferred_label"), f"label mismatch for {cid}")

    ids_by_type: dict[str, set[str]] = collections.defaultdict(set)
    for cid, row in common.items():
        ids_by_type[str(row.get("type") or "")].add(cid)
    occupations = ids_by_type["occupation-name"]
    jobs = ids_by_type["job-title"]
    skills = ids_by_type["skill"]
    require(len(occupations) == 2105, f"unexpected occupation count {len(occupations)}")
    require(len(jobs) == 9785, f"unexpected job-title count {len(jobs)}")
    require(len(skills) == 6752, f"unexpected skill count {len(skills)}")

    missing_jobs = read_zip_json(args.selector_gaps_artifact, "yv-missing-job-titles.json")
    require(isinstance(missing_jobs, list), "missing-title artifact is not a list")
    excluded = {str(row["id"]): row for row in missing_jobs}
    require(len(excluded) == 205, f"unexpected excluded title count {len(excluded)}")
    require(set(excluded) <= jobs, "excluded titles contain non-active IDs")
    admitted_jobs = jobs - set(excluded)
    require(len(admitted_jobs) == 9580, f"unexpected admitted title count {len(admitted_jobs)}")

    multi_parent = read_zip_json(args.selector_artifact, "yv-multi-parent-job-titles.json")
    require(isinstance(multi_parent, dict) and len(multi_parent) == 541, "unexpected multi-parent title population")
    require(set(multi_parent) <= admitted_jobs, "multi-parent selector title is not admitted")
    for cid, item in multi_parent.items():
        parents = item.get("occupation_name_ids") if isinstance(item, dict) else None
        require(isinstance(parents, list) and 2 <= len(parents) <= 3, f"invalid multi-parent context list for {cid}")
        require(set(map(str, parents)) <= occupations, f"invalid YV occupation context for {cid}")

    transferable = read_zip_json(args.selector_gaps_artifact, "kv-transferable-skill-ids.json")
    transferable_ids = set(map(str, transferable.get("referenced_active_skill_ids") or []))
    require(len(transferable_ids) == 27 and transferable_ids <= skills, "invalid transferable-skill population")

    occupation_rows: list[dict[str, Any]] = []
    occupation_strata = collections.Counter()
    for cid in sorted(occupations, key=lambda item: (str(native[item].get("preferred_label") or "").casefold(), item)):
        text = native[cid]
        graph = common[cid]
        real_definition = bool(text.get("definition_distinct_from_label"))
        alternative_labels = int(text.get("alternative_label_count") or 0)
        job_titles = count(graph, "related__job-title")
        keywords = count(graph, "related__keyword")
        esco = esco_count(graph, "esco-occupation")
        substitutability = count(graph, "substitutes__occupation-name") + count(graph, "substituted_by__occupation-name")
        tags: list[str] = []
        if not real_definition and alternative_labels == 0:
            tags.append("canonical_text_poor")
        if job_titles == 0 and keywords == 0 and esco == 0 and substitutability == 0:
            tags.append("common_graph_retrieval_sparse")
        if not real_definition:
            tags.append("needs_derived_language_resolution")
        occupation_strata.update(tags)
        occupation_rows.append({
            "target_key": f"occupation-name:{cid}",
            "product": "YV",
            "kind": "occupation-name",
            "concept_id": cid,
            "preferred_label": text.get("preferred_label"),
            "product_admission": KNOWN_TRUE,
            "canonical": {
                "real_definition": state(real_definition),
                "alternative_label_count": alternative_labels,
                "hidden_label_count": int(text.get("hidden_label_count") or 0),
                "quality_level": text.get("quality_level"),
            },
            "common_graph": {
                "ssyk4_parent_count": count(graph, "broader__ssyk-level-4"),
                "job_title_relation_count": job_titles,
                "keyword_relation_count": keywords,
                "esco_mapping_count": esco,
                "substitutability_relation_count": substitutability,
            },
            "per_target_knownness": {
                "relevant_skills": UNKNOWN,
                "kv_calculated_skills": UNKNOWN,
                "ad_keyword_corpus": UNKNOWN,
                "nearby_occupations": UNKNOWN,
            },
            "diagnostic_strata": tags,
        })

    skill_rows: list[dict[str, Any]] = []
    skill_strata = collections.Counter()
    for cid in sorted(skills, key=lambda item: (str(native[item].get("preferred_label") or "").casefold(), item)):
        text = native[cid]
        graph = common[cid]
        real_definition = bool(text.get("definition_distinct_from_label"))
        alternative_labels = int(text.get("alternative_label_count") or 0)
        ssyk = count(graph, "related__ssyk-level-4")
        esco = esco_count(graph, "esco-skill")
        tags: list[str] = []
        if not real_definition and alternative_labels == 0:
            tags.append("canonical_text_poor")
        if ssyk == 0:
            tags.append("no_ssyk4_context")
        if esco == 0:
            tags.append("no_esco_mapping")
        if not real_definition and ssyk == 0 and esco == 0:
            tags.append("canonical_and_common_context_poor")
        skill_strata.update(tags)
        skill_rows.append({
            "target_key": f"skill:{cid}",
            "product": "KV",
            "kind": "skill",
            "concept_id": cid,
            "preferred_label": text.get("preferred_label"),
            "product_admission": KNOWN_TRUE,
            "canonical": {
                "real_definition": state(real_definition),
                "alternative_label_count": alternative_labels,
                "hidden_label_count": int(text.get("hidden_label_count") or 0),
                "quality_level": text.get("quality_level"),
            },
            "common_graph": {
                "skill_headline_parent_count": count(graph, "broader__skill-headline"),
                "ssyk4_relation_count": ssyk,
                "esco_mapping_count": esco,
                "skill_collection_relation_count": count(graph, "related__skill-collection"),
            },
            "selector_artifact": {
                "transferable_skill_membership": state(cid in transferable_ids),
                "ordinary_kv_layer_membership": UNKNOWN,
                "relevant_skills_membership": UNKNOWN,
            },
            "diagnostic_strata": tags,
        })

    job_rows: list[dict[str, Any]] = []
    admitted_context_rows: list[dict[str, Any]] = []
    excluded_route_rows: list[dict[str, Any]] = []
    job_strata = collections.Counter()
    for cid in sorted(jobs, key=lambda item: (str(native[item].get("preferred_label") or "").casefold(), item)):
        text = native[cid]
        graph = common[cid]
        is_excluded = cid in excluded
        admitted = not is_excluded
        parent_count = count(graph, "related__occupation-name")
        if is_excluded:
            parent_ids = list(map(str, excluded[cid].get("occupation_parent_ids") or []))
            require(len(parent_ids) == parent_count, f"excluded parent count mismatch for {cid}")
            contexts_known = KNOWN_TRUE
            for parent in parent_ids:
                excluded_route_rows.append({
                    "job_title_id": cid,
                    "occupation_name_id": parent,
                    "preferred_label": text.get("preferred_label"),
                    "selectable": False,
                    "role": "retrieval_routing_context",
                })
        elif cid in multi_parent:
            parent_ids = list(map(str, multi_parent[cid]["occupation_name_ids"]))
            require(len(parent_ids) == parent_count, f"multi-parent context count mismatch for {cid}")
            contexts_known = KNOWN_TRUE
            for parent in parent_ids:
                admitted_context_rows.append({
                    "job_title_id": cid,
                    "occupation_name_id": parent,
                    "preferred_label": text.get("preferred_label"),
                    "selectable": True,
                    "role": "yv_product_identity",
                })
        else:
            parent_ids = []
            contexts_known = UNKNOWN
            require(parent_count == 1, f"admitted non-multi title {cid} has {parent_count} parents")

        tags: list[str] = []
        if is_excluded:
            tags.append("retrieval_only_excluded_by_yv")
        elif cid in multi_parent:
            tags.append("admitted_multi_context")
        else:
            tags.append("admitted_single_context_id_missing_from_offline_artifacts")
        if not bool(text.get("definition_distinct_from_label")):
            tags.append("definition_is_label_copy")
        job_strata.update(tags)
        job_rows.append({
            "target_key": f"job-title:{cid}",
            "product": "YV",
            "kind": "job-title-concept",
            "concept_id": cid,
            "preferred_label": text.get("preferred_label"),
            "product_admission": state(admitted),
            "taxonomy_occupation_parent_count": parent_count,
            "occupation_context_ids_known": contexts_known,
            "known_occupation_context_ids": parent_ids,
            "canonical_real_definition": state(bool(text.get("definition_distinct_from_label"))),
            "diagnostic_strata": tags,
        })

    write_jsonl(out / "yv-occupation.jsonl", occupation_rows)
    write_jsonl(out / "kv-skill.jsonl", skill_rows)
    write_jsonl(out / "yv-job-title-concepts.jsonl", job_rows)
    write_jsonl(out / "yv-known-admitted-job-title-contexts.jsonl", admitted_context_rows)
    write_jsonl(out / "yv-excluded-title-routing-contexts.jsonl", excluded_route_rows)

    require(len(admitted_context_rows) == sum(len(value["occupation_name_ids"]) for value in multi_parent.values()), "known admitted context count mismatch")
    require(len(excluded_route_rows) == sum(int(value.get("occupation_parent_count") or 0) for value in excluded.values()), "excluded routing context count mismatch")
    require(selector_aggregate.get("yrkesvaljaren", {}).get("multi_parent_job_title_ids") == len(multi_parent), "selector aggregate multi-parent mismatch")
    require(selector_aggregate.get("yrkesvaljaren", {}).get("coverage", {}).get("job-title", {}).get("selector_unique_ids") == len(admitted_jobs), "selector admitted-title count mismatch")

    paths = {
        "native_text": args.native_text_artifact,
        "common_relations": args.common_relations_artifact,
        "selector": args.selector_artifact,
        "selector_gaps": args.selector_gaps_artifact,
    }
    artifact_provenance = {
        key: {**ARTIFACTS[key], "archive_sha256": archive_sha256(path)}
        for key, path in paths.items()
    }
    aggregate = {
        "schema_version": 1,
        "taxonomy_version": EXPECTED["taxonomy_version"],
        "generated_at": now_utc(),
        "semantics": {
            "matrix_kind": "offline partial per-target diagnostic coverage",
            "tri_state": [KNOWN_TRUE, KNOWN_FALSE, UNKNOWN],
            "ranking_score": False,
            "aggregate_to_per_id_imputation": False,
            "invalid_native_text_graphql_relations_used": False,
        },
        "universes": {
            "yv_occupation_targets": len(occupation_rows),
            "kv_skill_targets": len(skill_rows),
            "active_job_title_concepts": len(job_rows),
            "yv_admitted_job_title_ids": len(admitted_jobs),
            "yv_excluded_job_title_ids": len(excluded),
            "yv_admitted_multi_context_ids_with_contexts_preserved": len(multi_parent),
            "yv_known_admitted_job_title_context_rows": len(admitted_context_rows),
            "yv_admitted_single_context_ids_with_parent_id_unknown_offline": len(admitted_jobs) - len(multi_parent),
            "yv_excluded_retrieval_routing_context_rows": len(excluded_route_rows),
        },
        "yv_occupation_strata": dict(sorted(occupation_strata.items())),
        "kv_skill_strata": dict(sorted(skill_strata.items())),
        "yv_job_title_strata": dict(sorted(job_strata.items())),
        "known_source_boundaries": {
            "native_text": "canonical text only; GraphQL relation columns in this historical artifact are invalid and ignored",
            "common_relations": "authoritative per-ID typed common-relation counts from immutable v31 snapshot",
            "selector": "per-context aggregate/count evidence plus explicit admitted multi-parent job-title contexts",
            "selector_gaps": "explicit 205 excluded job-title IDs/parents and 27 transferable skill IDs",
            "derived_af_per_target": UNKNOWN,
            "reason_derived_af_unknown": "accepted historical derived-AF artifact retained aggregate coverage only; absence must not become false per-ID",
        },
        "artifact_provenance": artifact_provenance,
        "accepted_source_hashes": EXPECTED,
    }
    (out / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "source-manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "generated_at": aggregate["generated_at"],
        "artifacts": artifact_provenance,
        "accepted_source_hashes": EXPECTED,
        "warnings": [
            "Historical native-text GraphQL relation extraction failed; only native text fields are consumed from that artifact.",
            "Derived-AF aggregate coverage is not materialized per ID in this offline matrix.",
            "Admitted single-context YV job-title parent IDs are not present in accepted offline artifacts and remain UNKNOWN here.",
        ],
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
