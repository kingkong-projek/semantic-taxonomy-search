#!/usr/bin/env python3
"""Evaluate simple C0 on the first model-adjudicated, volume-weighted Pareto slice.

C0 = P80 occupation preferred labels + real canonical definitions + canonical
alternative labels, deterministic BM25, with exact indexed-surface dominance.
Crucially, zero positive lexical evidence abstains instead of returning a zero-score
nearest neighbour.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, norm, tokens

COUNT_RE = re.compile(r"Observed count in source review pool: ([0-9]+)\.")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def observed_count(case: dict[str, Any]) -> int:
    m = COUNT_RE.search(str(case.get("notes") or ""))
    if not m:
        raise RuntimeError(f"case {case.get('id')} missing frozen observed count")
    return int(m.group(1))


def p80_ids(pareto: dict[str, Any]) -> list[str]:
    section = pareto["occupation_name"]
    count = int(section["thresholds"]["p80"]["concept_count"])
    ranked = section["ranked_p95"]
    ids = [str(row["concept_id"]) for row in ranked[:count]]
    if count != 159 or len(ids) != 159 or len(set(ids)) != 159:
        raise RuntimeError("P80 occupation membership drift")
    return ids


def positive_rank(ranker: BM25, query: str, exact_surfaces: dict[str, set[str]]) -> list[tuple[str, float]]:
    qtokens = tokens(query)
    nq = norm(query)
    scored: list[tuple[str, float]] = []
    for cid in ranker.documents:
        score = ranker.score(qtokens, cid)
        if nq and nq in exact_surfaces[cid]:
            score += 1_000_000.0
        if score > 0.0:
            scored.append((cid, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--output", default="artifacts/pareto-model-c0-eval-v31.json")
    args = ap.parse_args()

    cases = read_jsonl(Path(args.benchmark))
    if len(cases) != 34:
        raise RuntimeError(f"expected 34 adjudicated cases, got {len(cases)}")
    if any(c.get("adjudication", {}).get("status") != "MODEL_ADJUDICATED" for c in cases):
        raise RuntimeError("benchmark contains non-model-adjudicated rows")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    targets = p80_ids(pareto)

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
    for cid in targets:
        c = by_id.get(cid)
        if not isinstance(c, dict) or c.get("type") != "occupation-name":
            raise RuntimeError(f"invalid P80 occupation {cid}")
        label = str(c.get("preferred_label") or "")
        definition = str(c.get("definition") or "").strip()
        real_definition = definition if definition and norm(definition) != norm(label) else ""
        alternatives = [x for x in as_list(c.get("alternative_labels")) if norm(x) != norm(label)]
        documents[cid] = tokens(" ".join([label, real_definition, *alternatives]))
        exact_surfaces[cid] = {norm(label), *[norm(x) for x in alternatives if norm(x)]}

    ranker = BM25(documents, exact_surfaces)
    p80 = set(targets)
    total_volume = sum(observed_count(c) for c in cases)

    stats = defaultdict(float)
    intent_stats: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    rows = []
    for case in cases:
        count = observed_count(case)
        intent = str(case["expected_intent"])
        positive = {str(x["concept_id"]) for x in case["must"] + case["acceptable"]}
        positive_p80 = positive & p80
        forbidden = {str(x["concept_id"]) for x in case["must_not"]} & p80
        scored = positive_rank(ranker, str(case["query"]), exact_surfaces)
        ranked = [cid for cid, _ in scored]
        top1 = ranked[0] if ranked else None
        top10 = ranked[:10]
        abstained = not ranked
        satisfiable = intent == "NO_MATCH" or bool(positive_p80)

        if intent == "NO_MATCH":
            success = abstained
            top10_hit = abstained
        else:
            success = bool(top1 and top1 in positive_p80)
            top10_hit = any(cid in positive_p80 for cid in top10)

        hard_negative_violation = any(cid in forbidden for cid in top10)
        false_confident = intent == "NO_MATCH" and not abstained

        stats["cases"] += 1
        stats["volume"] += count
        stats["decision_success_cases"] += int(success)
        stats["decision_success_volume"] += count * int(success)
        stats["top10_success_cases"] += int(top10_hit)
        stats["top10_success_volume"] += count * int(top10_hit)
        stats["abstention_cases"] += int(abstained)
        stats["abstention_volume"] += count * int(abstained)
        stats["false_confident_cases"] += int(false_confident)
        stats["false_confident_volume"] += count * int(false_confident)
        stats["hard_negative_violation_cases"] += int(hard_negative_violation)
        stats["hard_negative_violation_volume"] += count * int(hard_negative_violation)
        stats["unsatisfiable_positive_cases"] += int(intent != "NO_MATCH" and not positive_p80)
        stats["unsatisfiable_positive_volume"] += count * int(intent != "NO_MATCH" and not positive_p80)

        ist = intent_stats[intent]
        ist["cases"] += 1
        ist["volume"] += count
        ist["success_cases"] += int(success)
        ist["success_volume"] += count * int(success)
        ist["abstain_cases"] += int(abstained)
        ist["abstain_volume"] += count * int(abstained)

        rows.append({
            "id": case["id"],
            "query": case["query"],
            "observed_count": count,
            "intent": intent,
            "positive_total": len(positive),
            "positive_in_p80": len(positive_p80),
            "p80_satisfiable": satisfiable,
            "abstained": abstained,
            "decision_success": success,
            "top10_success": top10_hit,
            "hard_negative_violation": hard_negative_violation,
            "top5": [
                {"concept_id": cid, "label": str(by_id[cid].get("preferred_label") or ""), "score": round(score, 6)}
                for cid, score in scored[:5]
            ],
        })

    def pct(n: float, d: float) -> float:
        return round(100.0 * n / d, 3) if d else 0.0

    overall = {
        "cases": int(stats["cases"]),
        "observed_volume": int(stats["volume"]),
        "decision_accuracy_pct": pct(stats["decision_success_cases"], stats["cases"]),
        "volume_weighted_decision_accuracy_pct": pct(stats["decision_success_volume"], stats["volume"]),
        "top10_success_pct": pct(stats["top10_success_cases"], stats["cases"]),
        "volume_weighted_top10_success_pct": pct(stats["top10_success_volume"], stats["volume"]),
        "false_confident_no_match_cases": int(stats["false_confident_cases"]),
        "false_confident_no_match_volume": int(stats["false_confident_volume"]),
        "hard_negative_violation_cases": int(stats["hard_negative_violation_cases"]),
        "hard_negative_violation_volume": int(stats["hard_negative_violation_volume"]),
        "positive_cases_unsatisfiable_inside_p80": int(stats["unsatisfiable_positive_cases"]),
        "positive_volume_unsatisfiable_inside_p80": int(stats["unsatisfiable_positive_volume"]),
    }

    by_intent = {}
    for intent, s in sorted(intent_stats.items()):
        by_intent[intent] = {
            "cases": int(s["cases"]),
            "observed_volume": int(s["volume"]),
            "decision_accuracy_pct": pct(s["success_cases"], s["cases"]),
            "volume_weighted_decision_accuracy_pct": pct(s["success_volume"], s["volume"]),
            "abstention_rate_pct": pct(s["abstain_cases"], s["cases"]),
            "volume_weighted_abstention_rate_pct": pct(s["abstain_volume"], s["volume"]),
        }

    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "benchmark_semantics": "model-adjudicated first Pareto decision slice; 34 rows cover 80.738% of the frozen 70-row review-pool observed volume",
        "retrieval": {
            "name": "C0",
            "target_envelope": "P80 occupation-name only (159 targets)",
            "representation": "preferred label + real canonical definition + canonical alternative labels",
            "ranking": "deterministic BM25 with exact indexed-surface dominance",
            "abstention": "zero positive lexical evidence => abstain",
        },
        "taxonomy_sha256": actual,
        "overall": overall,
        "by_intent": by_intent,
        "cases": rows,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": overall, "by_intent": by_intent}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
