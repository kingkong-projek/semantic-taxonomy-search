#!/usr/bin/env python3
"""Regression-check exact job-title routing after expanding YV canonical candidates to 2,105.

The frozen excluded-title ranks 21-50 sentinel was the independent C2 router capability
check. This script keeps the same typed-parent route and parent ordering, but replaces
the old 165-target C1 base with every active v31 occupation-name. It measures whether
new full-universe exact canonical surfaces can crowd source-attested routed parents out
of the visible top 5.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_c2_job_title_router import build_c1_index, relation_parent_ids
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm
from evaluate_pareto_c1 import rank_c1


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def pct(n: float, d: float) -> float:
    return round(100.0 * n / d, 3) if d else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--excluded-sentinel", required=True)
    ap.add_argument("--output", default="artifacts/yv-full-job-title-router-regression-v31.json")
    args = ap.parse_args()

    sentinel = read_jsonl(Path(args.excluded_sentinel))
    if len(sentinel) != 30:
        raise RuntimeError(f"sentinel count drift: {len(sentinel)}")
    expected_ids = [f"yv.safety.excluded-review.{i:03d}" for i in range(21, 51)]
    if [r.get("id") for r in sentinel] != expected_ids:
        raise RuntimeError("sentinel must be frozen excluded-title ranks 21-50")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    version = str(args.version)
    url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    body = fetch(url)
    taxonomy_sha = hashlib.sha256(body).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError(f"taxonomy source drift: {taxonomy_sha}")
    concepts = json.loads(body).get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    full_ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(full_ids) != 2105:
        raise RuntimeError(f"active occupation universe drift: {len(full_ids)}")
    ranker, exact_surfaces, surface_tokens = build_c1_index(by_id, full_ids)

    occurrence = {
        str(r["concept_id"]): int(r["occurrences"])
        for r in pareto["occupation_name"]["ranked_p95"]
    }
    label_to_parent_ids: dict[str, set[str]] = defaultdict(set)
    label_to_job_ids: dict[str, set[str]] = defaultdict(set)
    for cid, concept in by_id.items():
        if concept.get("type") != "job-title":
            continue
        label = norm(concept.get("preferred_label"))
        if not label:
            continue
        parents = relation_parent_ids(concept, by_id)
        if parents:
            label_to_parent_ids[label].update(parents)
            label_to_job_ids[label].add(cid)

    def parent_sort_key(cid: str):
        return (-occurrence.get(cid, 0), norm(by_id[cid].get("preferred_label")), cid)

    def rank_full_router(query: str):
        scored = rank_c1(ranker, query, exact_surfaces, surface_tokens)
        canonical = [cid for cid, _, _ in scored]
        nq = norm(query)
        exact_canonical = [cid for cid in canonical if nq and nq in exact_surfaces[cid]]
        routed = sorted(label_to_parent_ids.get(nq, set()), key=parent_sort_key)
        merged: list[str] = []
        for cid in [*exact_canonical, *routed, *canonical]:
            if cid not in merged:
                merged.append(cid)
        return merged, exact_canonical, routed

    total_volume = 0
    any_hit_rows = any_hit_volume = 0
    all_visible_rows = all_visible_volume = 0
    recall_sum = recall_volume_sum = 0.0
    collision_rows = 0
    route_set_drift_rows = 0
    rows = []
    for row in sentinel:
        expected_parents = {
            str(x["concept_id"]) for x in row.get("candidate_occupation_identities", [])
        }
        if not expected_parents:
            raise RuntimeError(f"sentinel row missing typed parents: {row['id']}")
        ranked, exact_canonical, routed_list = rank_full_router(str(row["query"]))
        routed = set(routed_list)
        route_set_ok = routed == expected_parents
        route_set_drift_rows += int(not route_set_ok)
        if not route_set_ok:
            raise RuntimeError(
                f"taxonomy/generator parent drift for {row['query']!r}: {routed} != {expected_parents}"
            )
        foreign_exact = [cid for cid in exact_canonical if cid not in expected_parents]
        collision_rows += int(bool(foreign_exact))
        top5 = ranked[:5]
        hits = len(set(top5) & expected_parents)
        any_hit = hits > 0
        all_visible = hits == len(expected_parents)
        recall5 = hits / len(expected_parents)
        count = int(row["observed_count"])
        total_volume += count
        any_hit_rows += int(any_hit); any_hit_volume += count * int(any_hit)
        all_visible_rows += int(all_visible); all_visible_volume += count * int(all_visible)
        recall_sum += recall5; recall_volume_sum += count * recall5
        rows.append({
            "id": row["id"],
            "query": row["query"],
            "observed_count": count,
            "typed_parent_ids": routed_list,
            "foreign_exact_canonical_ids_before_route": foreign_exact,
            "top5_ids": top5,
            "any_parent_hit_at_5": any_hit,
            "all_typed_parents_visible_at_5": all_visible,
            "typed_parent_recall_at_5": round(recall5, 6),
        })

    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "status": "frozen_router_regression_on_existing_unseen_c2_sentinel",
        "configuration": {
            "canonical_candidate_count": len(full_ids),
            "exact_route_surface_count": len(label_to_parent_ids),
            "fusion": (
                "full-universe exact canonical occupation surfaces first; then exact active job-title typed parents "
                "ordered by frozen occupation occurrence proxy; then remaining full canonical ranking"
            ),
        },
        "source": {"taxonomy_url": url, "taxonomy_sha256": taxonomy_sha},
        "sentinel": {
            "rows": len(rows),
            "observed_volume": total_volume,
            "route_set_drift_rows": route_set_drift_rows,
            "foreign_exact_canonical_collision_rows": collision_rows,
            "any_parent_hit_at_5_pct": pct(any_hit_rows, len(rows)),
            "volume_weighted_any_parent_hit_at_5_pct": pct(any_hit_volume, total_volume),
            "all_typed_parents_visible_at_5_pct": pct(all_visible_rows, len(rows)),
            "volume_weighted_all_typed_parents_visible_at_5_pct": pct(all_visible_volume, total_volume),
            "mean_typed_parent_recall_at_5_pct": pct(recall_sum, len(rows)),
            "volume_weighted_typed_parent_recall_at_5_pct": pct(recall_volume_sum, total_volume),
            "cases": rows,
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "configuration": result["configuration"],
        "sentinel": {k:v for k,v in result["sentinel"].items() if k != "cases"},
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
