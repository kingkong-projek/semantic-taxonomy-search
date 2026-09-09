#!/usr/bin/env python3
"""Diagnose fail-open / irrelevant-tail behaviour of the frozen P80 YV candidate.

This is deliberately an OPENED diagnostic replay. It may establish mechanism and
product risk, but MUST NOT choose/tune a confidence threshold. The opened 17/88
stress rows are never promotion evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from evaluate_a593_language_diversity_falsifier import load_diverse_training, load_teacher
from evaluate_gemma_a149 import build_ranker
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm, tokens
from evaluate_pareto_c1 import rank_c1

TAXONOMY_URL = (
    "https://data.jobtechdev.se/taxonomy/version/31/query/"
    "concepts-and-common-relations/concepts-and-common-relations.json"
)
EXPECTED_UNIVERSE = 2105


def add_teacher(dst: dict[str, list[str]], src: dict[str, list[str]], allowed: set[str] | None = None) -> None:
    for cid, values in src.items():
        if allowed is not None and cid not in allowed:
            continue
        dst.setdefault(cid, []).extend(values)


def family_rank(scored: list[tuple[str, float, str]], by_id: dict[str, dict[str, Any]], expected: list[str]) -> int | None:
    needles = [norm(x) for x in expected if norm(x)]
    if not needles:
        return None
    for i, (cid, _score, _signal) in enumerate(scored, 1):
        label = norm(by_id[cid].get("preferred_label"))
        if any(needle in label for needle in needles):
            return i
    return None


def shared_terms(ranker, cid: str, query: str) -> list[str]:
    q = set(tokens(query))
    return sorted(t for t in q if ranker.tf[cid].get(t, 0))


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)
    return {
        "cases": len(rows),
        "nonempty": sum(bool(r["result_count"]) for r in rows),
        "full_five": sum(r["displayed_count"] == 5 for r in rows),
        "mean_displayed": round(sum(r["displayed_count"] for r in rows) / max(1, len(rows)), 3),
        "by_category": {
            cat: {
                "cases": len(subset),
                "nonempty": sum(bool(r["result_count"]) for r in subset),
                "full_five": sum(r["displayed_count"] == 5 for r in subset),
                "top1_family_hit": sum(r["expected_family_rank"] == 1 for r in subset if r["expected"]),
                "top5_family_hit": sum(
                    r["expected_family_rank"] is not None and r["expected_family_rank"] <= 5
                    for r in subset if r["expected"]
                ),
                "targetable_cases": sum(bool(r["expected"]) for r in subset),
            }
            for cat, subset in sorted(by_category.items())
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--teacher", default="research/enrichment/v31/gemma4-yv-a593/phrases.jsonl")
    ap.add_argument("--priority", default="research/evaluation/v31/p80-track2-priority-coverage.json")
    ap.add_argument("--a593-diverse", default="research/training/v31/a593-language-diversity-training-v0.jsonl")
    ap.add_argument("--p80-diverse", default="research/training/v31/p80-language-diversity-training-v0.jsonl")
    ap.add_argument("--rescue", default="research/training/v31/p80-source-thin-rescue-training-v0.jsonl")
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--output", default="research/evaluation/v31/p80-display-precision-opened-audit-v0.json")
    args = ap.parse_args()

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    wire = fetch(TAXONOMY_URL)
    sha = hashlib.sha256(wire).hexdigest()
    if sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != EXPECTED_UNIVERSE:
        raise RuntimeError("candidate universe drift")

    priority = json.loads(Path(args.priority).read_text(encoding="utf-8"))
    existing_ids = {str(r["concept_id"]) for r in priority.get("existing_diversified_v0") or []}
    missing_ids = {str(r["concept_id"]) for r in priority.get("missing_diversified_v0") or []}
    p80_ids = existing_ids | missing_ids
    if len(p80_ids) != 159:
        raise RuntimeError("P80 membership drift")

    _teacher_ids, base_teacher = load_teacher(Path(args.teacher))
    a593, _ = load_diverse_training(Path(args.a593_diverse))
    p80, _ = load_diverse_training(Path(args.p80_diverse))
    rescue, rescue_meta = load_diverse_training(Path(args.rescue))
    if len(rescue_meta) != 22:
        raise RuntimeError("rescue metadata drift")

    teacher = {cid: list(values) for cid, values in base_teacher.items()}
    add_teacher(teacher, a593, existing_ids)
    add_teacher(teacher, p80, missing_ids)
    add_teacher(teacher, rescue, p80_ids)
    ranker, exact, surfaces = build_ranker(by_id, ids, teacher)

    stress = json.loads(Path(args.stress).read_text(encoding="utf-8"))
    cases = stress.get("yv") or []
    rows: list[dict[str, Any]] = []
    token_support_hist = Counter()
    for case in cases:
        query = str(case["query"])
        scored = rank_c1(ranker, query, exact, surfaces)
        top = scored[:5]
        expected = [str(x) for x in case.get("expect") or []]
        erank = family_rank(scored, by_id, expected)
        top_rows = []
        for i, (cid, score, signal) in enumerate(top, 1):
            support = shared_terms(ranker, cid, query)
            token_support_hist[len(support)] += 1
            top_rows.append({
                "rank": i,
                "concept_id": cid,
                "label": str(by_id[cid].get("preferred_label") or cid),
                "score": round(float(score), 6),
                "score_ratio_to_top": round(float(score / top[0][1]), 6) if top and top[0][1] > 0 else 0.0,
                "signal": signal,
                "shared_terms": support,
                "shared_term_count": len(support),
            })
        rows.append({
            "id": case["id"],
            "category": case["category"],
            "query": query,
            "expected": expected,
            "should_abstain": bool(case.get("should_abstain")),
            "should_clarify": bool(case.get("should_clarify")),
            "result_count": len(scored),
            "displayed_count": len(top),
            "expected_family_rank": erank,
            "top5": top_rows,
        })

    abstain = [r for r in rows if r["should_abstain"]]
    clarify = [r for r in rows if r["should_clarify"]]
    targetable = [r for r in rows if r["expected"] and not r["should_abstain"]]
    result = {
        "id": "YV-P80-display-precision-opened-audit-v0",
        "status": "opened diagnostic only; MUST NOT tune a confidence/display threshold from these rows",
        "candidate": "frozen P80 A-family + source-thin rescue; same 2,105 occupation universe",
        "mechanism": {
            "long_query_admission": "rank_c1 admits every occupation with BM25 score > 0; there is no confidence threshold, score-gap requirement, or result-set precision gate",
            "presentation": "consumer demo takes first five admitted candidates; therefore weak lexical overlap can fill the visible tail",
        },
        "overall": summarize(rows),
        "explicit_abstention": {
            "cases": len(abstain),
            "correct_empty": sum(r["result_count"] == 0 for r in abstain),
            "failed_open": sum(r["result_count"] > 0 for r in abstain),
            "full_five": sum(r["displayed_count"] == 5 for r in abstain),
        },
        "clarification_cases": {
            "cases": len(clarify),
            "nonempty": sum(r["result_count"] > 0 for r in clarify),
            "full_five": sum(r["displayed_count"] == 5 for r in clarify),
        },
        "targetable": {
            "cases": len(targetable),
            "top1_family_hit": sum(r["expected_family_rank"] == 1 for r in targetable),
            "top5_family_hit": sum(r["expected_family_rank"] is not None and r["expected_family_rank"] <= 5 for r in targetable),
        },
        "visible_result_shared_term_count_histogram": {str(k): v for k, v in sorted(token_support_hist.items())},
        "rows": rows,
        "interpretation_boundary": "This replay can confirm fail-open mechanism and show examples. A display-confidence rule must be selected on separate prefrozen calibration evidence, then only replayed here diagnostically.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "overall": result["overall"],
        "explicit_abstention": result["explicit_abstention"],
        "clarification_cases": result["clarification_cases"],
        "targetable": result["targetable"],
        "visible_result_shared_term_count_histogram": result["visible_result_shared_term_count_histogram"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
