#!/usr/bin/env python3
"""Development diagnostic for the full-universe YV canonical description baseline.

The query source is Yrkesinformation `work_task` text from records with exactly one
explicit active v31 occupation-name ID. That source is NOT ingested into the candidate.
Cases containing the target's canonical or related job-title surface are excluded so
this does not collapse into a title lookup benchmark.

This is source-attested development evidence, not human validation and not a tuning set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_c2_job_title_router import build_c1_index, relation_parent_ids
from evaluate_p80_lexical_ablation import as_list, expected_hash, fetch, norm, tokens
from evaluate_pareto_c1 import BOUNDARY_IDS, p80_ids, rank_c1
from occupational_information_coverage import find_explicit_taxonomy_ids, record_map

SOURCE_URL = (
    "https://data.arbetsformedlingen.se/yrke/yrkesinformation/"
    "yrkesinformation-interimslosning.json"
)


def phrase_present(text: str, surface: str) -> bool:
    """Match a complete token sequence, insensitive to punctuation/case."""
    haystack = tokens(text)
    needle = tokens(surface)
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(haystack[index:index + width] == needle for index in range(len(haystack) - width + 1))


def metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--output", default="artifacts/yv-full-description-canonical-diagnostic-v31.json")
    args = ap.parse_args()

    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    taxonomy_wire = fetch(taxonomy_url)
    taxonomy_sha = hashlib.sha256(taxonomy_wire).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")

    source_wire = fetch(SOURCE_URL)
    source_sha = hashlib.sha256(source_wire).hexdigest()
    if source_sha != expected_hash(registry, "occupational-information"):
        raise RuntimeError(f"occupational-information source drift: {source_sha}")

    taxonomy = json.loads(taxonomy_wire)
    source = json.loads(source_wire)
    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active_occ = {
        cid for cid, concept in by_id.items() if concept.get("type") == "occupation-name"
    }
    if len(active_occ) != 2105:
        raise RuntimeError(f"active occupation universe drift: {len(active_occ)}")

    all_ids = set(by_id)
    records = record_map(source.get("data"))
    metadata = source.get("metadata")
    occupations_meta = metadata.get("occupations") if isinstance(metadata, dict) else None
    if not isinstance(occupations_meta, list):
        raise RuntimeError("Yrkesinformation missing metadata.occupations")

    current_ids = sorted(set(p80_ids(pareto)) | BOUNDARY_IDS)
    if len(current_ids) != 165:
        raise RuntimeError(f"current C2 description envelope drift: {len(current_ids)}")
    current_ranker, current_exact, current_surface_tokens = build_c1_index(by_id, current_ids)

    full_ids = sorted(active_occ)
    full_ranker, full_exact, full_surface_tokens = build_c1_index(by_id, full_ids)

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
    seen_targets = set()

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
        leaking = sorted(
            {surface for surface in target_surfaces if surface and phrase_present(query, surface)},
            key=norm,
        )
        if leaking:
            exclusions["contains_target_or_job_title_surface"] += 1
            continue

        current_scored = rank_c1(current_ranker, query, current_exact, current_surface_tokens)
        full_scored = rank_c1(full_ranker, query, full_exact, full_surface_tokens)
        current_ranked = [cid for cid, _, _ in current_scored]
        full_ranked = [cid for cid, _, _ in full_scored]

        current_rank = current_ranked.index(target) + 1 if target in current_ranked else None
        full_rank = full_ranked.index(target) + 1 if target in full_ranked else None

        rows.append(
            {
                "source_slug": slug,
                "target_id": target,
                "target_label": concept.get("preferred_label"),
                "target_in_current_165": target in current_ids,
                "query": query,
                "current_c1_165": {
                    "rank": current_rank,
                    "top5": current_ranked[:5],
                },
                "full_canonical_2105": {
                    "rank": full_rank,
                    "top5": full_ranked[:5],
                },
            }
        )
        seen_targets.add(target)

    if not rows:
        raise RuntimeError("no leak-free source-attested work_task cases")

    in_165 = [row for row in rows if row["target_in_current_165"]]
    outside_165 = [row for row in rows if not row["target_in_current_165"]]

    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "status": "opened_source_attested_development_diagnostic_not_human_validation",
        "query_source": (
            "Yrkesinformation work_task text; only records with exactly one explicit "
            "active v31 occupation-name ID; source text is not ingested into either candidate"
        ),
        "anti_leakage": (
            "exclude a case when normalized token sequences reveal the target preferred/alternative "
            "label or any active related job-title preferred-label surface, including next to punctuation"
        ),
        "source_sha256": source_sha,
        "taxonomy_sha256": taxonomy_sha,
        "case_count": len(rows),
        "unique_target_count": len(seen_targets),
        "excluded": dict(sorted(exclusions.items())),
        "current_165_membership": {
            "inside_cases": len(in_165),
            "outside_cases": len(outside_165),
        },
        "metrics": {
            "all": {
                "current_c1_165": metrics(rows, "current_c1_165"),
                "full_canonical_2105": metrics(rows, "full_canonical_2105"),
            },
            "inside_current_165": {
                "current_c1_165": metrics(in_165, "current_c1_165"),
                "full_canonical_2105": metrics(in_165, "full_canonical_2105"),
            },
            "outside_current_165": {
                "current_c1_165": metrics(outside_165, "current_c1_165"),
                "full_canonical_2105": metrics(outside_165, "full_canonical_2105"),
            },
        },
        "cases": rows,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "cases": len(rows),
                "unique_targets": len(seen_targets),
                "inside_current_165": len(in_165),
                "outside_current_165": len(outside_165),
                "metrics": result["metrics"],
                "output": str(out),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
