#!/usr/bin/env python3
"""Evaluate the smallest C1 residual fix on frozen occupation benchmarks.

C1 deliberately stays classical and deterministic:
- P80 occupation targets + six high-volume boundary identities found by the first Pareto slice;
- preferred labels + real canonical definitions + canonical alternative labels;
- label/alternative-label surface evidence dominates definition-only overlap;
- conservative component/fuzzy surface matching for ordinary inflection/compound wording;
- queries of <=3 tokens require surface evidence and otherwise abstain.

This is a development iteration on the same 34-case Pareto slice, so improvement there is
not holdout/generalisation evidence. A frozen 333-case source-truth regression is also run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, norm, tokens
from evaluate_pareto_model_slice import observed_count

BOUNDARY_IDS = {
    "DLEi_bTh_oLA",
    "wypk_7S7_snv",
    "86sy_hBf_exW",
    "743P_CSD_tF8",
    "PecC_mHt_1Cj",
    "VZoJ_4oe_xyR",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def p80_ids(pareto: dict[str, Any]) -> list[str]:
    section = pareto["occupation_name"]
    count = int(section["thresholds"]["p80"]["concept_count"])
    ranked = section["ranked_p95"]
    ids = [str(row["concept_id"]) for row in ranked[:count]]
    if count != 159 or len(ids) != 159 or len(set(ids)) != 159:
        raise RuntimeError("P80 occupation membership drift")
    return ids


def bounded_levenshtein(a: str, b: str, limit: int) -> int:
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            value = min(
                current[j - 1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ca != cb),
            )
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1]


def fuzzy_limit(token: str) -> int:
    if len(token) >= 9:
        return 2
    if len(token) >= 6:
        return 1
    return 0


def surface_signal(
    query: str,
    exact_surfaces: set[str],
    surface_tokens: set[str],
) -> tuple[int, str]:
    nq = norm(query)
    if nq and nq in exact_surfaces:
        return 4, "exact_surface"

    qtokens = set(tokens(query))
    if qtokens & surface_tokens:
        return 3, "exact_label_token"

    for qt in qtokens:
        if len(qt) < 6:
            continue
        for st in surface_tokens:
            if len(st) < 6:
                continue
            if qt in st or st in qt:
                return 2, "component_surface"

    for qt in qtokens:
        limit = fuzzy_limit(qt)
        if not limit:
            continue
        for st in surface_tokens:
            if len(st) < 6:
                continue
            effective = min(limit, fuzzy_limit(st))
            if effective and bounded_levenshtein(qt, st, effective) <= effective:
                return 1, "fuzzy_surface"

    return 0, "none"


def rank_c1(
    ranker: BM25,
    query: str,
    exact_surfaces: dict[str, set[str]],
    surface_tokens: dict[str, set[str]],
) -> list[tuple[str, float, str]]:
    qtokens = tokens(query)
    short_query = len(qtokens) <= 3
    boosts = {4: 1_000_000.0, 3: 10_000.0, 2: 5_000.0, 1: 2_500.0, 0: 0.0}
    scored: list[tuple[str, float, str]] = []
    nq = norm(query)
    for cid in ranker.documents:
        lexical = ranker.score(qtokens, cid)

        if short_query:
            # Short picker-style queries are where lexical surface evidence is useful
            # and where definition-only overlap caused false confident geography hits.
            signal, signal_name = surface_signal(query, exact_surfaces[cid], surface_tokens[cid])
            if signal == 0:
                continue
            score = lexical + boosts[signal]
        else:
            # Description-style queries keep C0 semantics. Token/component/fuzzy
            # surface boosts on long text caused incidental words to overpower the
            # concept's own definition in the frozen source-truth regression.
            signal_name = "exact_surface" if nq and nq in exact_surfaces[cid] else "definition_bm25"
            score = lexical + (1_000_000.0 if signal_name == "exact_surface" else 0.0)
            if score <= 0.0:
                continue

        scored.append((cid, score, signal_name))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored


def pct(n: float, d: float) -> float:
    return round(100.0 * n / d, 3) if d else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--benchmark", default="research/benchmark/v31/pareto-model-adjudicated/benchmark.jsonl")
    ap.add_argument("--source-truth", default="research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl")
    ap.add_argument("--output", default="artifacts/pareto-c1-eval-v31.json")
    args = ap.parse_args()

    cases = read_jsonl(Path(args.benchmark))
    if len(cases) != 34 or any(c.get("adjudication", {}).get("status") != "MODEL_ADJUDICATED" for c in cases):
        raise RuntimeError("unexpected frozen Pareto decision benchmark")
    source_truth = read_jsonl(Path(args.source_truth))
    if len(source_truth) != 333:
        raise RuntimeError(f"unexpected YV P80 source-truth count: {len(source_truth)}")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    base_p80 = p80_ids(pareto)
    if BOUNDARY_IDS & set(base_p80):
        raise RuntimeError("C1 boundary IDs unexpectedly already inside P80")
    targets = sorted(set(base_p80) | BOUNDARY_IDS)
    if len(targets) != 165:
        raise RuntimeError(f"C1 target envelope drift: {len(targets)}")

    version = str(args.version)
    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    body = fetch(taxonomy_url)
    actual = hashlib.sha256(body).hexdigest()
    expected = expected_hash(registry, "taxonomy-common-relations")
    if actual != expected:
        raise RuntimeError(f"taxonomy source drift: expected {expected}, got {actual}")
    taxonomy = json.loads(body)
    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    documents: dict[str, list[str]] = {}
    exact_surfaces: dict[str, set[str]] = {}
    surface_tokens_by_id: dict[str, set[str]] = {}
    for cid in targets:
        c = by_id.get(cid)
        if not isinstance(c, dict) or c.get("type") != "occupation-name":
            raise RuntimeError(f"invalid C1 occupation target {cid}")
        label = str(c.get("preferred_label") or "").strip()
        definition = str(c.get("definition") or "").strip()
        real_definition = definition if definition and norm(definition) != norm(label) else ""
        alternatives = [x for x in as_list(c.get("alternative_labels")) if norm(x) != norm(label)]
        surfaces = [label, *alternatives]
        documents[cid] = tokens(" ".join([label, real_definition, *alternatives]))
        exact_surfaces[cid] = {norm(x) for x in surfaces if norm(x)}
        surface_tokens_by_id[cid] = {t for x in surfaces for t in tokens(x)}

    ranker = BM25(documents, exact_surfaces)
    target_set = set(targets)
    total_volume = sum(observed_count(c) for c in cases)
    stats = defaultdict(float)
    by_intent: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    rows: list[dict[str, Any]] = []

    for case in cases:
        count = observed_count(case)
        intent = str(case["expected_intent"])
        positive = {str(x["concept_id"]) for x in case["must"] + case["acceptable"]}
        positive_in_envelope = positive & target_set
        forbidden = {str(x["concept_id"]) for x in case["must_not"]} & target_set
        scored = rank_c1(ranker, str(case["query"]), exact_surfaces, surface_tokens_by_id)
        ranked = [cid for cid, _, _ in scored]
        top1 = ranked[0] if ranked else None
        top10 = ranked[:10]
        abstained = not ranked

        if intent == "NO_MATCH":
            success = abstained
            top10_hit = abstained
        else:
            success = bool(top1 and top1 in positive_in_envelope)
            top10_hit = any(cid in positive_in_envelope for cid in top10)

        hard_negative_violation = any(cid in forbidden for cid in top10)
        false_confident = intent == "NO_MATCH" and not abstained
        unsatisfiable = intent != "NO_MATCH" and not positive_in_envelope

        stats["cases"] += 1
        stats["volume"] += count
        stats["success_cases"] += int(success)
        stats["success_volume"] += count * int(success)
        stats["top10_cases"] += int(top10_hit)
        stats["top10_volume"] += count * int(top10_hit)
        stats["false_confident_cases"] += int(false_confident)
        stats["false_confident_volume"] += count * int(false_confident)
        stats["hard_negative_cases"] += int(hard_negative_violation)
        stats["hard_negative_volume"] += count * int(hard_negative_violation)
        stats["unsatisfiable_cases"] += int(unsatisfiable)
        stats["unsatisfiable_volume"] += count * int(unsatisfiable)

        ist = by_intent[intent]
        ist["cases"] += 1
        ist["volume"] += count
        ist["success_cases"] += int(success)
        ist["success_volume"] += count * int(success)
        ist["abstain_cases"] += int(abstained)
        ist["abstain_volume"] += count * int(abstained)

        rows.append({
            "id": case["id"],
            "query": case["query"],
            "intent": intent,
            "observed_count": count,
            "abstained": abstained,
            "decision_success": success,
            "top10_success": top10_hit,
            "hard_negative_violation": hard_negative_violation,
            "positive_in_c1_envelope": len(positive_in_envelope),
            "top5": [
                {
                    "concept_id": cid,
                    "label": str(by_id[cid].get("preferred_label") or ""),
                    "score": round(score, 6),
                    "surface_signal": signal,
                }
                for cid, score, signal in scored[:5]
            ],
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
        "positive_cases_unsatisfiable_inside_c1": int(stats["unsatisfiable_cases"]),
        "positive_volume_unsatisfiable_inside_c1": int(stats["unsatisfiable_volume"]),
    }

    by_intent_out = {}
    for intent, s in sorted(by_intent.items()):
        by_intent_out[intent] = {
            "cases": int(s["cases"]),
            "observed_volume": int(s["volume"]),
            "decision_accuracy_pct": pct(s["success_cases"], s["cases"]),
            "volume_weighted_decision_accuracy_pct": pct(s["success_volume"], s["volume"]),
            "abstention_rate_pct": pct(s["abstain_cases"], s["cases"]),
            "volume_weighted_abstention_rate_pct": pct(s["abstain_volume"], s["volume"]),
        }

    # Source-truth regression: all original 159 targets must remain first-class despite six extra candidates.
    regression_success = 0
    regression_top10 = 0
    regression_misses: list[dict[str, Any]] = []
    for case in source_truth:
        positive = {str(x["concept_id"]) for x in case["must"]}
        scored = rank_c1(ranker, str(case["query"]), exact_surfaces, surface_tokens_by_id)
        ranked = [cid for cid, _, _ in scored]
        top1_ok = bool(ranked and ranked[0] in positive)
        top10_ok = any(cid in positive for cid in ranked[:10])
        regression_success += int(top1_ok)
        regression_top10 += int(top10_ok)
        if not top1_ok:
            regression_misses.append({
                "id": case["id"],
                "query": case["query"],
                "expected": sorted(positive),
                "top5": ranked[:5],
            })

    regression = {
        "cases": len(source_truth),
        "top1_pct": pct(regression_success, len(source_truth)),
        "recall_at_10_case_success_pct": pct(regression_top10, len(source_truth)),
        "top1_miss_count": len(regression_misses),
        "top1_misses_first_20": regression_misses[:20],
    }

    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "taxonomy_sha256": actual,
        "benchmark_semantics": "development evaluation on the same frozen 34-case model-adjudicated Pareto slice used to identify C0 residuals; improvement is not holdout evidence",
        "retrieval": {
            "name": "C1",
            "target_envelope": "159 P80 occupation-name + six measured high-volume boundary identities = 165 targets",
            "boundary_ids": sorted(BOUNDARY_IDS),
            "representation": "preferred label + real canonical definition + canonical alternative labels",
            "ranking": "short queries: deterministic label-surface dominance (exact > token > component > bounded fuzzy); long descriptions: unchanged C0 BM25 with exact-full-surface dominance only",
            "abstention": "queries of <=3 tokens require label/alternative-label surface evidence; longer descriptions retain C0 definition-BM25 behavior",
            "complexity_boundary": "no ESCO, embeddings, ad ETL, synthetic text, ML model or place-name list",
        },
        "overall": overall,
        "by_intent": by_intent_out,
        "source_truth_regression": regression,
        "cases": rows,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": overall, "by_intent": by_intent_out, "source_truth_regression": regression}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
