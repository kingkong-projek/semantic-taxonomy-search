#!/usr/bin/env python3
"""Evaluate C2: C1 plus exact active job-title -> typed occupation-parent routing.

The objective is discovery, not top-1 classification. Exact active job-title preferred
labels are retrieval vocabulary. Their typed occupation-name parents are source-attested
candidate destinations and are unioned ahead of ordinary C1 results. Existing exact
occupation surfaces retain dominance so C1 source-truth behavior cannot regress.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import as_list, expected_hash, fetch, norm, tokens, BM25
from evaluate_pareto_c1 import BOUNDARY_IDS, p80_ids, rank_c1
from evaluate_pareto_model_slice import observed_count


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def pct(n: float, d: float) -> float:
    return round(100.0 * n / d, 3) if d else 0.0


def relation_parent_ids(c: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    rel = c.get("related")
    if isinstance(rel, list):
        for x in rel:
            rid = str(x.get("id") if isinstance(x, dict) else x)
            if by_id.get(rid, {}).get("type") == "occupation-name":
                out.add(rid)
    return out


def build_c1_index(by_id: dict[str, dict[str, Any]], ids: list[str]):
    docs: dict[str, list[str]] = {}
    exact: dict[str, set[str]] = {}
    surface_tokens: dict[str, set[str]] = {}
    for cid in ids:
        c = by_id[cid]
        label = str(c.get("preferred_label") or "").strip()
        definition = str(c.get("definition") or "").strip()
        real_definition = definition if definition and norm(definition) != norm(label) else ""
        alternatives = [x for x in as_list(c.get("alternative_labels")) if norm(x) != norm(label)]
        surfaces = [label, *alternatives]
        docs[cid] = tokens(" ".join([label, real_definition, *alternatives]))
        exact[cid] = {norm(x) for x in surfaces if norm(x)}
        surface_tokens[cid] = {t for x in surfaces for t in tokens(x)}
    return BM25(docs, exact), exact, surface_tokens


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--holdout", default="research/benchmark/v31/pareto-model-holdout/benchmark.jsonl")
    ap.add_argument("--source-truth", default="research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl")
    ap.add_argument("--excluded-sentinel", required=True)
    ap.add_argument("--output", default="artifacts/c2-job-title-router-v31.json")
    args = ap.parse_args()

    holdout = read_jsonl(Path(args.holdout))
    source_truth = read_jsonl(Path(args.source_truth))
    sentinel = read_jsonl(Path(args.excluded_sentinel))
    if len(holdout) != 36 or len(source_truth) != 333 or len(sentinel) != 30:
        raise RuntimeError(f"benchmark/sentinel count drift: {len(holdout)}/{len(source_truth)}/{len(sentinel)}")
    expected_sentinel_ids = [f"yv.safety.excluded-review.{i:03d}" for i in range(21, 51)]
    if [r["id"] for r in sentinel] != expected_sentinel_ids:
        raise RuntimeError("excluded-title sentinel must be frozen ranks 21-50")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    version = str(args.version)
    url = f"https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    body = fetch(url)
    taxonomy_sha = hashlib.sha256(body).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(body).get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    p80 = p80_ids(pareto)
    c1_ids = sorted(set(p80) | BOUNDARY_IDS)
    ranker, exact_surfaces, surface_tokens = build_c1_index(by_id, c1_ids)

    occurrence = {str(r["concept_id"]): int(r["occurrences"]) for r in pareto["occupation_name"]["ranked_p95"]}
    label_to_parent_ids: dict[str, set[str]] = defaultdict(set)
    label_to_job_ids: dict[str, set[str]] = defaultdict(set)
    for cid, c in by_id.items():
        if c.get("type") != "job-title":
            continue
        label = norm(c.get("preferred_label"))
        if not label:
            continue
        parents = relation_parent_ids(c, by_id)
        if parents:
            label_to_parent_ids[label].update(parents)
            label_to_job_ids[label].add(cid)

    def parent_sort_key(cid: str):
        return (-occurrence.get(cid, 0), norm(by_id[cid].get("preferred_label")), cid)

    def rank_c2(query: str) -> tuple[list[str], dict[str, Any]]:
        c1_scored = rank_c1(ranker, query, exact_surfaces, surface_tokens)
        c1_ranked = [cid for cid, _, _ in c1_scored]
        nq = norm(query)
        exact_canonical = [cid for cid in c1_ranked if nq and nq in exact_surfaces[cid]]
        routed = sorted(label_to_parent_ids.get(nq, set()), key=parent_sort_key)
        merged: list[str] = []
        for cid in [*exact_canonical, *routed, *c1_ranked]:
            if cid not in merged:
                merged.append(cid)
        return merged, {
            "exact_active_job_title": bool(routed),
            "matching_job_title_ids": sorted(label_to_job_ids.get(nq, set())),
            "typed_parent_ids": routed,
        }

    # 1) Previously unseen excluded-title ranks 21-50: source-attested routing coverage.
    sent_stats = defaultdict(float)
    sent_rows = []
    parent_count_distribution: dict[int, int] = defaultdict(int)
    for row in sentinel:
        expected_parents = {str(x["concept_id"]) for x in row.get("candidate_occupation_identities", [])}
        if not expected_parents:
            raise RuntimeError(f"sentinel row missing typed parents: {row['id']}")
        ranked, meta = rank_c2(str(row["query"]))
        routed = set(meta["typed_parent_ids"])
        if routed != expected_parents:
            raise RuntimeError(f"taxonomy/generator parent drift for {row['query']!r}: {routed} != {expected_parents}")
        top5 = ranked[:5]
        hits = len(set(top5) & expected_parents)
        any_hit = hits > 0
        all_visible = hits == len(expected_parents)
        recall5 = hits / len(expected_parents)
        count = int(row["observed_count"])
        parent_count_distribution[len(expected_parents)] += 1
        sent_stats["rows"] += 1; sent_stats["volume"] += count
        sent_stats["any_hit_rows"] += int(any_hit); sent_stats["any_hit_volume"] += count * int(any_hit)
        sent_stats["all_visible_rows"] += int(all_visible); sent_stats["all_visible_volume"] += count * int(all_visible)
        sent_stats["parent_recall5_sum"] += recall5; sent_stats["parent_recall5_volume_sum"] += count * recall5
        sent_rows.append({
            "id": row["id"], "query": row["query"], "observed_count": count,
            "typed_parent_count": len(expected_parents), "any_parent_hit_at_5": any_hit,
            "all_typed_parents_visible_at_5": all_visible, "typed_parent_recall_at_5": round(recall5, 6),
            "top5_ids": top5,
        })
    sentinel_result = {
        "rows": int(sent_stats["rows"]),
        "observed_volume": int(sent_stats["volume"]),
        "any_parent_hit_at_5_pct": pct(sent_stats["any_hit_rows"], sent_stats["rows"]),
        "volume_weighted_any_parent_hit_at_5_pct": pct(sent_stats["any_hit_volume"], sent_stats["volume"]),
        "all_typed_parents_visible_at_5_pct": pct(sent_stats["all_visible_rows"], sent_stats["rows"]),
        "volume_weighted_all_typed_parents_visible_at_5_pct": pct(sent_stats["all_visible_volume"], sent_stats["volume"]),
        "mean_typed_parent_recall_at_5_pct": pct(sent_stats["parent_recall5_sum"], sent_stats["rows"]),
        "volume_weighted_typed_parent_recall_at_5_pct": pct(sent_stats["parent_recall5_volume_sum"], sent_stats["volume"]),
        "typed_parent_count_distribution": {str(k): v for k, v in sorted(parent_count_distribution.items())},
    }

    # 2) Previously opened natural-language holdout: development impact only.
    h_stats = defaultdict(float)
    h_rows = []
    for case in holdout:
        count = observed_count(case)
        intent = str(case["expected_intent"])
        positive = {str(x["concept_id"]) for x in case["must"] + case["acceptable"]}
        ranked, meta = rank_c2(str(case["query"]))
        if intent == "NO_MATCH":
            success5 = not ranked
        else:
            success5 = any(cid in positive for cid in ranked[:5])
        h_stats["cases"] += 1; h_stats["volume"] += count
        h_stats["success5_cases"] += int(success5); h_stats["success5_volume"] += count * int(success5)
        h_stats["no_match_cases"] += int(intent == "NO_MATCH")
        h_stats["no_match_abstain_cases"] += int(intent == "NO_MATCH" and not ranked)
        h_rows.append({
            "id": case["id"], "query": case["query"], "intent": intent,
            "observed_count": count, "discovery_success_at_5": success5,
            "exact_job_title_route": meta["exact_active_job_title"], "top5_ids": ranked[:5],
        })
    holdout_result = {
        "cases": int(h_stats["cases"]),
        "observed_volume": int(h_stats["volume"]),
        "discovery_success_at_5_pct": pct(h_stats["success5_cases"], h_stats["cases"]),
        "volume_weighted_discovery_success_at_5_pct": pct(h_stats["success5_volume"], h_stats["volume"]),
        "no_match_abstention_pct": pct(h_stats["no_match_abstain_cases"], h_stats["no_match_cases"]),
        "interpretation": "development-only because this holdout was already opened before C2 design",
    }

    # 3) Frozen source-truth regression: exact occupation surfaces must not regress.
    st_top1 = st_hit5 = 0
    st_misses = []
    for case in source_truth:
        positive = {str(x["concept_id"]) for x in case["must"]}
        ranked, _ = rank_c2(str(case["query"]))
        top1_ok = bool(ranked and ranked[0] in positive)
        hit5 = any(cid in positive for cid in ranked[:5])
        st_top1 += int(top1_ok); st_hit5 += int(hit5)
        if not top1_ok:
            st_misses.append({"id": case["id"], "query": case["query"], "top5": ranked[:5]})
    source_truth_result = {
        "cases": len(source_truth),
        "top1_pct": pct(st_top1, len(source_truth)),
        "discovery_hit_at_5_pct": pct(st_hit5, len(source_truth)),
        "top1_miss_count": len(st_misses),
        "top1_misses_first_20": st_misses[:20],
    }

    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "taxonomy_sha256": taxonomy_sha,
        "configuration": {
            "name": "C2",
            "base": "C1",
            "new_lane": "exact active job-title preferred label -> union of typed related occupation-name parents",
            "fusion": "existing exact canonical occupation surfaces first; then typed job-title parents ordered by frozen occupation occurrence proxy; then remaining C1 candidates",
            "destination_boundary": "job-title is retrieval vocabulary only; emitted candidates are canonical occupation-name identities",
            "primary_metric": "Discovery Success@5 / typed-parent coverage@5",
        },
        "unseen_excluded_title_sentinel_ranks_21_50": {**sentinel_result, "cases": sent_rows},
        "opened_holdout_development_view": {**holdout_result, "cases_detail": h_rows},
        "source_truth_regression": source_truth_result,
    }
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "sentinel": sentinel_result,
        "opened_holdout": holdout_result,
        "source_truth_regression": source_truth_result,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
