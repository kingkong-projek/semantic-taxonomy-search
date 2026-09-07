#!/usr/bin/env python3
"""Measure occupation-contextual skill language as an independent YV description lane.

This is an opened development diagnostic, not a promoted retrieval configuration.
It exists because unified v31 coverage shows that Relevanta kompetenser supplies skill
context for almost every occupation that lacks both canonical descriptive text and
observed ad language.

Queries come from Yrkesinformation `work_task` text for records with exactly one explicit
active v31 occupation-name ID. Yrkesinformation text is evaluation-only and is never
ingested into a retrieval document. Target occupation/job-title surface leakage is
excluded before ranking.

Two deliberately simple representations are compared independently:
- skill labels only;
- skill labels + distinct canonical skill definitions.

Published `relevance_points` are not used as weights in this first pass. No lane fusion,
embeddings, generated teacher text or learned ranking is introduced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import zstandard as zstd

from evaluate_c2_job_title_router import build_c1_index, relation_parent_ids
from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, norm, tokens
from evaluate_pareto_c1 import rank_c1
from occupational_information_coverage import find_explicit_taxonomy_ids, record_map

OCC_INFO_URL = (
    "https://data.arbetsformedlingen.se/yrke/yrkesinformation/"
    "yrkesinformation-interimslosning.json"
)


def phrase_present(text: str, surface: str) -> bool:
    haystack = tokens(text)
    needle = tokens(surface)
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(haystack[i:i + width] == needle for i in range(len(haystack) - width + 1))


def positive_bm25_rank(ranker: BM25, query: str) -> list[str]:
    qtokens = tokens(query)
    scored = [(cid, ranker.score(qtokens, cid)) for cid in ranker.documents]
    scored = [(cid, score) for cid, score in scored if score > 0.0]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [cid for cid, _ in scored]


def lane_metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"cases": 0, "top1": None, "hit_at_5": None, "mrr": None, "nonempty": None}
    top1 = sum(row[key]["rank"] == 1 for row in rows)
    hit5 = sum(
        isinstance(row[key]["rank"], int) and row[key]["rank"] <= 5
        for row in rows
    )
    nonempty = sum(bool(row[key]["top5"]) for row in rows)
    rr = sum(
        0.0 if row[key]["rank"] is None else 1.0 / int(row[key]["rank"])
        for row in rows
    )
    return {
        "cases": n,
        "top1": round(top1 / n, 6),
        "hit_at_5": round(hit5 / n, 6),
        "mrr": round(rr / n, 6),
        "nonempty": round(nonempty / n, 6),
    }


def hit5_ids(rows: list[dict[str, Any]], key: str) -> set[str]:
    return {
        row["source_slug"]
        for row in rows
        if isinstance(row[key]["rank"], int) and row[key]["rank"] <= 5
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--output", default="artifacts/yv-relevant-skill-lane-diagnostic-v31.json")
    args = ap.parse_args()

    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    relevant_url = (
        "https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/"
        f"v1/relevanta-kompetenser-t{version}.json.zst"
    )

    taxonomy_wire = fetch(taxonomy_url)
    taxonomy_sha = hashlib.sha256(taxonomy_wire).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")

    occ_info_wire = fetch(OCC_INFO_URL)
    occ_info_sha = hashlib.sha256(occ_info_wire).hexdigest()
    if occ_info_sha != expected_hash(registry, "occupational-information"):
        raise RuntimeError(f"occupational-information source drift: {occ_info_sha}")

    relevant_wire = fetch(relevant_url)
    relevant_sha = hashlib.sha256(relevant_wire).hexdigest()
    if relevant_sha != expected_hash(registry, "relevant-skills"):
        raise RuntimeError(f"relevant-skills source drift: {relevant_sha}")

    taxonomy = json.loads(taxonomy_wire)
    occ_info = json.loads(occ_info_wire)
    relevant_doc = json.loads(zstd.ZstdDecompressor().decompress(relevant_wire))

    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active_occ = {
        cid for cid, concept in by_id.items() if concept.get("type") == "occupation-name"
    }
    active_skills = {
        cid for cid, concept in by_id.items() if concept.get("type") == "skill"
    }
    if len(active_occ) != 2105 or len(active_skills) != 6752:
        raise RuntimeError(
            f"active target universe drift: occupations={len(active_occ)} skills={len(active_skills)}"
        )

    full_ids = sorted(active_occ)
    canonical_ranker, canonical_exact, canonical_surface_tokens = build_c1_index(by_id, full_ids)

    relevant_data = relevant_doc.get("data")
    if not isinstance(relevant_data, dict):
        raise RuntimeError("Relevanta kompetenser missing data object")
    if set(relevant_data) != active_occ:
        raise RuntimeError(
            "Relevanta kompetenser occupation universe must equal active occupation-name universe"
        )

    label_docs: dict[str, list[str]] = {}
    definition_docs: dict[str, list[str]] = {}
    exact_none: dict[str, set[str]] = {}
    occupation_skill_counts: dict[str, int] = {}
    unique_skill_ids: set[str] = set()

    for occ_id in full_ids:
        record = relevant_data[occ_id]
        items = record.get("relevant_skills") if isinstance(record, dict) else None
        if not isinstance(items, list):
            raise RuntimeError(f"Relevanta skills for {occ_id} is not a list")

        labels: list[str] = []
        label_plus_definitions: list[str] = []
        local_seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            skill_id = str(item["id"])
            if skill_id not in active_skills:
                raise RuntimeError(f"Relevanta references non-active skill {skill_id}")
            if skill_id in local_seen:
                continue
            local_seen.add(skill_id)
            unique_skill_ids.add(skill_id)
            skill = by_id[skill_id]
            label = str(skill.get("preferred_label") or "").strip()
            definition = str(skill.get("definition") or "").strip()
            real_definition = definition if definition and norm(definition) != norm(label) else ""
            if label:
                labels.append(label)
                label_plus_definitions.append(label)
            if real_definition:
                label_plus_definitions.append(real_definition)

        occupation_skill_counts[occ_id] = len(local_seen)
        label_docs[occ_id] = tokens(" ".join(labels))
        definition_docs[occ_id] = tokens(" ".join(label_plus_definitions))
        exact_none[occ_id] = set()

    if len(unique_skill_ids) != 4685:
        raise RuntimeError(f"Relevanta unique skill universe drift: {len(unique_skill_ids)}")

    label_ranker = BM25(label_docs, exact_none)
    definition_ranker = BM25(definition_docs, exact_none)

    all_ids = set(by_id)
    records = record_map(occ_info.get("data"))
    metadata = occ_info.get("metadata")
    occupations_meta = metadata.get("occupations") if isinstance(metadata, dict) else None
    if not isinstance(occupations_meta, list):
        raise RuntimeError("Yrkesinformation missing metadata.occupations")

    job_title_surfaces_by_parent: dict[str, set[str]] = defaultdict(set)
    for concept in by_id.values():
        if concept.get("type") != "job-title":
            continue
        label = str(concept.get("preferred_label") or "").strip()
        if not label:
            continue
        for parent in relation_parent_ids(concept, by_id):
            job_title_surfaces_by_parent[parent].add(label)

    rows: list[dict[str, Any]] = []
    exclusions: dict[str, int] = defaultdict(int)
    for meta in occupations_meta:
        if not isinstance(meta, dict):
            continue
        slug = str(meta.get("slug") or "")
        record = records.get(slug)
        if not isinstance(record, dict):
            exclusions["missing_record"] += 1
            continue
        explicit = find_explicit_taxonomy_ids(record, all_ids) & active_occ
        if len(explicit) != 1:
            exclusions["not_unique_explicit_active_occupation"] += 1
            continue
        target = next(iter(explicit))
        query = str(record.get("work_task") or "").strip()
        if len(query) < 40:
            exclusions["work_task_too_short"] += 1
            continue

        concept = by_id[target]
        target_surfaces = {
            str(concept.get("preferred_label") or ""),
            *as_list(concept.get("alternative_labels")),
            *job_title_surfaces_by_parent.get(target, set()),
        }
        if any(surface and phrase_present(query, surface) for surface in target_surfaces):
            exclusions["contains_target_or_job_title_surface"] += 1
            continue

        canonical_scored = rank_c1(
            canonical_ranker, query, canonical_exact, canonical_surface_tokens
        )
        canonical_ranked = [cid for cid, _, _ in canonical_scored]
        labels_ranked = positive_bm25_rank(label_ranker, query)
        defs_ranked = positive_bm25_rank(definition_ranker, query)

        def rank_of(ranked: list[str]) -> int | None:
            return ranked.index(target) + 1 if target in ranked else None

        rows.append({
            "source_slug": slug,
            "target_id": target,
            "target_label": concept.get("preferred_label"),
            "target_relevant_skill_count": occupation_skill_counts[target],
            "target_has_real_canonical_definition": (
                bool(norm(concept.get("definition")))
                and norm(concept.get("definition")) != norm(concept.get("preferred_label"))
            ),
            "query": query,
            "full_canonical_2105": {
                "rank": rank_of(canonical_ranked),
                "top5": canonical_ranked[:5],
            },
            "relevant_skill_labels_bm25": {
                "rank": rank_of(labels_ranked),
                "top5": labels_ranked[:5],
            },
            "relevant_skill_labels_plus_definitions_bm25": {
                "rank": rank_of(defs_ranked),
                "top5": defs_ranked[:5],
            },
        })

    if not rows:
        raise RuntimeError("no leak-free source-attested work_task cases")

    canonical_hit = hit5_ids(rows, "full_canonical_2105")
    labels_hit = hit5_ids(rows, "relevant_skill_labels_bm25")
    defs_hit = hit5_ids(rows, "relevant_skill_labels_plus_definitions_bm25")
    text_poor = [row for row in rows if not row["target_has_real_canonical_definition"]]

    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "status": "prepared_opened_source_attested_development_diagnostic_not_human_validation",
        "decision_question": (
            "does existing occupation-linked skill context add lexical description recall beyond the full canonical occupation lane"
        ),
        "lane_semantics": {
            "full_canonical_2105": (
                "all active occupation-name identities; preferred label + distinct canonical definition + canonical alternatives"
            ),
            "relevant_skill_labels_bm25": (
                "one document per occupation containing preferred labels of its AF Relevanta kompetenser skills; no relevance weighting"
            ),
            "relevant_skill_labels_plus_definitions_bm25": (
                "same occupation-skill relation set plus distinct canonical definitions of those skills; no relevance weighting"
            ),
        },
        "non_claims": [
            "Relevanta skill context is canonical occupation definition text",
            "relevance_points are calibrated retrieval weights",
            "Yrkesinformation work_task is independent human query language",
            "either skill lane should be fused into product retrieval before a separate decision-bearing comparison",
        ],
        "anti_leakage": (
            "Yrkesinformation work_task is evaluation-only; normalized token-sequence matching excludes target occupation preferred/alternative labels and related active job-title surfaces"
        ),
        "source_sha256": {
            "taxonomy": taxonomy_sha,
            "occupational_information": occ_info_sha,
            "relevant_skills": relevant_sha,
        },
        "coverage": {
            "occupation_records": len(relevant_data),
            "unique_active_skills_referenced": len(unique_skill_ids),
            "occupations_with_zero_relevant_skills": sum(count == 0 for count in occupation_skill_counts.values()),
        },
        "case_count": len(rows),
        "metrics": {
            "all": {
                "full_canonical_2105": lane_metrics(rows, "full_canonical_2105"),
                "relevant_skill_labels_bm25": lane_metrics(rows, "relevant_skill_labels_bm25"),
                "relevant_skill_labels_plus_definitions_bm25": lane_metrics(
                    rows, "relevant_skill_labels_plus_definitions_bm25"
                ),
            },
            "targets_without_real_canonical_definition": {
                "cases": len(text_poor),
                "full_canonical_2105": lane_metrics(text_poor, "full_canonical_2105"),
                "relevant_skill_labels_bm25": lane_metrics(text_poor, "relevant_skill_labels_bm25"),
                "relevant_skill_labels_plus_definitions_bm25": lane_metrics(
                    text_poor, "relevant_skill_labels_plus_definitions_bm25"
                ),
            },
        },
        "complementarity_at_5": {
            "canonical_hit_cases": len(canonical_hit),
            "skill_labels_hit_cases": len(labels_hit),
            "skill_labels_plus_definitions_hit_cases": len(defs_hit),
            "skill_labels_rescue_canonical_miss_cases": len(labels_hit - canonical_hit),
            "skill_labels_plus_definitions_rescue_canonical_miss_cases": len(defs_hit - canonical_hit),
            "hit_in_canonical_or_labels_cases": len(canonical_hit | labels_hit),
            "hit_in_canonical_or_labels_plus_definitions_cases": len(canonical_hit | defs_hit),
        },
        "excluded": dict(sorted(exclusions.items())),
        "cases": rows,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "cases": len(rows),
        "coverage": result["coverage"],
        "metrics": result["metrics"],
        "complementarity_at_5": result["complementarity_at_5"],
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
