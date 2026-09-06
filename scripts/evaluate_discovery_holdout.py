#!/usr/bin/env python3
"""Discovery-oriented evaluation for the frozen C0/C1 Pareto holdout.

Primary product semantics are discovery, not exact top-1 classification:
- positive intent succeeds when at least one judged relevant occupation is visible in
  the small result set;
- NO_MATCH succeeds when the system abstains;
- top-1 remains secondary diagnostics only.

The benchmark's judged-positive sets are not exhaustive for broad natural language, so
we report hit/success metrics as primary and judged-positive density/coverage only as
secondary diagnostics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from evaluate_p80_lexical_ablation import as_list, expected_hash, fetch, norm, tokens, BM25
from evaluate_pareto_model_slice import observed_count, positive_rank
from evaluate_pareto_c1 import BOUNDARY_IDS, p80_ids, rank_c1


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def pct(n: float, d: float) -> float:
    return round(100.0 * n / d, 3) if d else 0.0


def build_index(by_id: dict[str, dict[str, Any]], ids: list[str]):
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


def score(name: str, cases: list[dict[str, Any]], rank_fn: Callable[[str], list[str]]) -> dict[str, Any]:
    stats = defaultdict(float)
    rows = []
    for case in cases:
        count = observed_count(case)
        intent = str(case["expected_intent"])
        positive = {str(x["concept_id"]) for x in case["must"] + case["acceptable"]}
        ranked = rank_fn(str(case["query"]))
        abstained = not ranked
        top1 = ranked[:1]
        top5 = ranked[:5]
        top10 = ranked[:10]

        if intent == "NO_MATCH":
            success1 = success5 = success10 = abstained
            positive_recall5 = None
            judged_density5 = None
        else:
            success1 = any(cid in positive for cid in top1)
            success5 = any(cid in positive for cid in top5)
            success10 = any(cid in positive for cid in top10)
            positive_recall5 = (len(set(top5) & positive) / len(positive)) if positive else 0.0
            judged_density5 = (len(set(top5) & positive) / len(top5)) if top5 else 0.0

        for k, ok in ((1, success1), (5, success5), (10, success10)):
            stats[f"success{k}_cases"] += int(ok)
            stats[f"success{k}_volume"] += count * int(ok)
        stats["cases"] += 1
        stats["volume"] += count
        stats["positive_cases"] += int(intent != "NO_MATCH")
        stats["positive_volume"] += count * int(intent != "NO_MATCH")
        stats["no_match_cases"] += int(intent == "NO_MATCH")
        stats["no_match_volume"] += count * int(intent == "NO_MATCH")
        stats["no_match_abstain_cases"] += int(intent == "NO_MATCH" and abstained)
        stats["no_match_abstain_volume"] += count * int(intent == "NO_MATCH" and abstained)
        if positive_recall5 is not None:
            stats["positive_recall5_sum"] += positive_recall5
            stats["positive_recall5_volume_sum"] += positive_recall5 * count
            stats["judged_density5_sum"] += judged_density5
            stats["judged_density5_volume_sum"] += judged_density5 * count

        rows.append({
            "id": case["id"],
            "query": case["query"],
            "intent": intent,
            "observed_count": count,
            "discovery_success_at_1": bool(success1),
            "discovery_success_at_5": bool(success5),
            "discovery_success_at_10": bool(success10),
            "abstained": abstained,
            "judged_positive_count": len(positive),
            "judged_positive_hits_at_5": len(set(top5) & positive),
            "top5_ids": top5,
        })

    positive_cases = stats["positive_cases"]
    positive_volume = stats["positive_volume"]
    return {
        "name": name,
        "primary": {
            "discovery_success_at_5_pct": pct(stats["success5_cases"], stats["cases"]),
            "volume_weighted_discovery_success_at_5_pct": pct(stats["success5_volume"], stats["volume"]),
            "discovery_success_at_10_pct": pct(stats["success10_cases"], stats["cases"]),
            "volume_weighted_discovery_success_at_10_pct": pct(stats["success10_volume"], stats["volume"]),
            "no_match_abstention_pct": pct(stats["no_match_abstain_cases"], stats["no_match_cases"]),
            "volume_weighted_no_match_abstention_pct": pct(stats["no_match_abstain_volume"], stats["no_match_volume"]),
        },
        "secondary": {
            "top1_success_pct": pct(stats["success1_cases"], stats["cases"]),
            "volume_weighted_top1_success_pct": pct(stats["success1_volume"], stats["volume"]),
            "mean_judged_positive_recall_at_5_pct": pct(stats["positive_recall5_sum"], positive_cases),
            "volume_weighted_judged_positive_recall_at_5_pct": pct(stats["positive_recall5_volume_sum"], positive_volume),
            "mean_judged_positive_density_at_5_pct": pct(stats["judged_density5_sum"], positive_cases),
            "volume_weighted_judged_positive_density_at_5_pct": pct(stats["judged_density5_volume_sum"], positive_volume),
            "note": "judged-positive sets are not exhaustive for broad queries, so density/coverage are diagnostics rather than true precision/recall",
        },
        "counts": {
            "cases": int(stats["cases"]),
            "observed_volume": int(stats["volume"]),
            "positive_cases": int(stats["positive_cases"]),
            "no_match_cases": int(stats["no_match_cases"]),
        },
        "cases": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--benchmark", default="research/benchmark/v31/pareto-model-holdout/benchmark.jsonl")
    ap.add_argument("--output", default="artifacts/pareto-holdout-discovery-v31.json")
    args = ap.parse_args()

    cases = read_jsonl(Path(args.benchmark))
    if len(cases) != 36:
        raise RuntimeError(f"expected frozen 36-case holdout, got {len(cases)}")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    p80 = p80_ids(pareto)
    c1_ids = sorted(set(p80) | BOUNDARY_IDS)

    version = str(args.version)
    url = f"https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    body = fetch(url)
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(body).get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    c0_ranker, c0_exact, _ = build_index(by_id, p80)
    c1_ranker, c1_exact, c1_surface = build_index(by_id, c1_ids)

    c0 = score("C0", cases, lambda q: [cid for cid, _ in positive_rank(c0_ranker, q, c0_exact)])
    c1 = score("C1", cases, lambda q: [cid for cid, _, _ in rank_c1(c1_ranker, q, c1_exact, c1_surface)])

    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "taxonomy_sha256": actual,
        "objective": "discovery: show a small useful candidate set containing what the user seeks; top-1 exactness is secondary",
        "primary_k": 5,
        "C0": c0,
        "C1": c1,
        "delta": {
            "volume_weighted_discovery_success_at_5_points": round(c1["primary"]["volume_weighted_discovery_success_at_5_pct"] - c0["primary"]["volume_weighted_discovery_success_at_5_pct"], 3),
            "volume_weighted_discovery_success_at_10_points": round(c1["primary"]["volume_weighted_discovery_success_at_10_pct"] - c0["primary"]["volume_weighted_discovery_success_at_10_pct"], 3),
            "volume_weighted_top1_success_points": round(c1["secondary"]["volume_weighted_top1_success_pct"] - c0["secondary"]["volume_weighted_top1_success_pct"], 3),
        },
    }
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"C0": c0["primary"], "C1": c1["primary"], "delta": result["delta"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
