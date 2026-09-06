#!/usr/bin/env python3
"""Compare unchanged C0 and C1 on the independently adjudicated 36-row holdout.

The holdout consists of Pareto ranks 35-70 from the same frozen 70-row review pool and
was not used to design C1. This evaluator does not mutate rules, labels or target sets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, norm, tokens
from evaluate_pareto_model_slice import observed_count, positive_rank
from evaluate_pareto_c1 import BOUNDARY_IDS, p80_ids, rank_c1


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def pct(n: float, d: float) -> float:
    return round(100.0 * n / d, 3) if d else 0.0


def build_index(by_id: dict[str, dict[str, Any]], target_ids: list[str]) -> tuple[BM25, dict[str, set[str]], dict[str, set[str]]]:
    documents: dict[str, list[str]] = {}
    exact: dict[str, set[str]] = {}
    surface_tokens: dict[str, set[str]] = {}
    for cid in target_ids:
        c = by_id.get(cid)
        if not isinstance(c, dict) or c.get("type") != "occupation-name":
            raise RuntimeError(f"invalid occupation target {cid}")
        label = str(c.get("preferred_label") or "").strip()
        definition = str(c.get("definition") or "").strip()
        real_definition = definition if definition and norm(definition) != norm(label) else ""
        alternatives = [x for x in as_list(c.get("alternative_labels")) if norm(x) != norm(label)]
        surfaces = [label, *alternatives]
        documents[cid] = tokens(" ".join([label, real_definition, *alternatives]))
        exact[cid] = {norm(x) for x in surfaces if norm(x)}
        surface_tokens[cid] = {t for x in surfaces for t in tokens(x)}
    return BM25(documents, exact), exact, surface_tokens


def evaluate_config(
    name: str,
    cases: list[dict[str, Any]],
    target_ids: set[str],
    rank_fn: Callable[[str], list[str]],
) -> dict[str, Any]:
    stats = defaultdict(float)
    intent_stats: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    rows: list[dict[str, Any]] = []
    for case in cases:
        count = observed_count(case)
        intent = str(case["expected_intent"])
        positive = {str(x["concept_id"]) for x in case["must"] + case["acceptable"]}
        positive_in_envelope = positive & target_ids
        forbidden = {str(x["concept_id"]) for x in case["must_not"]} & target_ids
        ranked = rank_fn(str(case["query"]))
        top1 = ranked[0] if ranked else None
        abstained = not ranked
        top10 = ranked[:10]
        if intent == "NO_MATCH":
            success = abstained
            top10_hit = abstained
        else:
            success = bool(top1 and top1 in positive_in_envelope)
            top10_hit = any(cid in positive_in_envelope for cid in top10)
        false_confident = intent == "NO_MATCH" and not abstained
        hard_negative = any(cid in forbidden for cid in top10)
        unsatisfiable = intent != "NO_MATCH" and not positive_in_envelope

        stats["cases"] += 1; stats["volume"] += count
        stats["success_cases"] += int(success); stats["success_volume"] += count * int(success)
        stats["top10_cases"] += int(top10_hit); stats["top10_volume"] += count * int(top10_hit)
        stats["false_confident_cases"] += int(false_confident); stats["false_confident_volume"] += count * int(false_confident)
        stats["hard_negative_cases"] += int(hard_negative); stats["hard_negative_volume"] += count * int(hard_negative)
        stats["unsatisfiable_cases"] += int(unsatisfiable); stats["unsatisfiable_volume"] += count * int(unsatisfiable)

        s = intent_stats[intent]
        s["cases"] += 1; s["volume"] += count
        s["success_cases"] += int(success); s["success_volume"] += count * int(success)
        s["abstain_cases"] += int(abstained); s["abstain_volume"] += count * int(abstained)
        rows.append({
            "id": case["id"], "query": case["query"], "intent": intent, "observed_count": count,
            "decision_success": success, "top10_success": top10_hit, "abstained": abstained,
            "positive_in_envelope": len(positive_in_envelope), "top5_ids": ranked[:5],
        })

    overall = {
        "cases": int(stats["cases"]),
        "observed_volume": int(stats["volume"]),
        "decision_accuracy_pct": pct(stats["success_cases"], stats["cases"]),
        "volume_weighted_decision_accuracy_pct": pct(stats["success_volume"], stats["volume"]),
        "top10_success_pct": pct(stats["top10_cases"], stats["cases"]),
        "volume_weighted_top10_success_pct": pct(stats["top10_volume"], stats["volume"]),
        "false_confident_no_match_cases": int(stats["false_confident_cases"]),
        "false_confident_no_match_volume": int(stats["false_confident_volume"]),
        "hard_negative_violation_cases": int(stats["hard_negative_cases"]),
        "hard_negative_violation_volume": int(stats["hard_negative_volume"]),
        "positive_cases_unsatisfiable_inside_envelope": int(stats["unsatisfiable_cases"]),
        "positive_volume_unsatisfiable_inside_envelope": int(stats["unsatisfiable_volume"]),
    }
    by_intent = {
        intent: {
            "cases": int(s["cases"]), "observed_volume": int(s["volume"]),
            "decision_accuracy_pct": pct(s["success_cases"], s["cases"]),
            "volume_weighted_decision_accuracy_pct": pct(s["success_volume"], s["volume"]),
            "abstention_rate_pct": pct(s["abstain_cases"], s["cases"]),
            "volume_weighted_abstention_rate_pct": pct(s["abstain_volume"], s["volume"]),
        }
        for intent, s in sorted(intent_stats.items())
    }
    return {"name": name, "overall": overall, "by_intent": by_intent, "cases": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--output", default="artifacts/pareto-holdout-c0-c1-v31.json")
    args = ap.parse_args()

    cases = read_jsonl(Path(args.benchmark))
    if len(cases) != 36:
        raise RuntimeError(f"expected 36 holdout cases, got {len(cases)}")
    if any(c.get("adjudication", {}).get("status") != "MODEL_ADJUDICATED" for c in cases):
        raise RuntimeError("holdout contains non-model-adjudicated rows")
    ranks = sorted(int(str(c.get("notes")).split("Pareto rank: ")[1].split(".")[0]) for c in cases)
    if ranks != list(range(35, 71)):
        raise RuntimeError("holdout Pareto ranks drift")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    p80 = p80_ids(pareto)
    c1_ids = sorted(set(p80) | BOUNDARY_IDS)
    if len(p80) != 159 or len(c1_ids) != 165:
        raise RuntimeError("target-envelope drift")

    version = str(args.version)
    taxonomy_url = f"https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    body = fetch(taxonomy_url)
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(body).get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    c0_ranker, c0_exact, _ = build_index(by_id, p80)
    c1_ranker, c1_exact, c1_surface_tokens = build_index(by_id, c1_ids)

    def c0_rank(query: str) -> list[str]:
        return [cid for cid, _ in positive_rank(c0_ranker, query, c0_exact)]

    def c1_rank(query: str) -> list[str]:
        return [cid for cid, _, _ in rank_c1(c1_ranker, query, c1_exact, c1_surface_tokens)]

    c0 = evaluate_config("C0", cases, set(p80), c0_rank)
    c1 = evaluate_config("C1", cases, set(c1_ids), c1_rank)
    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "taxonomy_sha256": actual,
        "holdout_semantics": "Pareto ranks 35-70; independently model-adjudicated before retrieval evaluation and untouched by C1 design",
        "configurations": {
            "C0": "159 P80 targets; canonical label+definition+alternative label BM25; zero score abstains",
            "C1": "C0 representation over 165 targets; six predeclared boundary identities; short-query surface/component/fuzzy gate; long descriptions retain C0 ranking",
        },
        "C0": c0,
        "C1": c1,
        "delta": {
            "volume_weighted_decision_accuracy_points": round(c1["overall"]["volume_weighted_decision_accuracy_pct"] - c0["overall"]["volume_weighted_decision_accuracy_pct"], 3),
            "volume_weighted_top10_success_points": round(c1["overall"]["volume_weighted_top10_success_pct"] - c0["overall"]["volume_weighted_top10_success_pct"], 3),
            "false_confident_no_match_cases": c1["overall"]["false_confident_no_match_cases"] - c0["overall"]["false_confident_no_match_cases"],
            "unsatisfiable_positive_cases": c1["overall"]["positive_cases_unsatisfiable_inside_envelope"] - c0["overall"]["positive_cases_unsatisfiable_inside_envelope"],
        },
    }
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"C0": c0["overall"], "C1": c1["overall"], "delta": result["delta"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
