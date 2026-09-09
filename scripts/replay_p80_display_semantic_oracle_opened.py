#!/usr/bin/env python3
"""Replay the exact frozen semantic relevance oracle on opened user-style stress.

This script may run only after the primary 2024 semantic-oracle gate passes. It imports
the exact prompt/model/display contract from evaluate_p80_display_semantic_oracle.py and
asserts them against the frozen primary result. Opened rows may falsify transfer but may
never tune prompt, model, evidence, verdict policy or thresholds.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from audit_p80_display_precision import family_rank
from evaluate_p80_lexical_ablation import norm
from evaluate_pareto_c1 import rank_c1
from evaluate_p80_display_semantic_oracle import (
    MODEL,
    PROMPT_SHA256,
    PROMPT_VERSION,
    display_keep,
    load_system,
    semantic_judge_batches,
)

EXPECTED_PRIMARY_ID = "YV-P80-display-semantic-oracle-v0"
EXPECTED_STRESS_CASES = 54


def displayed_family_rank(kept: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], expected: list[str]) -> tuple[int | None, int | None]:
    needles = [norm(x) for x in expected if norm(x)]
    if not needles:
        return None, None
    for display_rank, c in enumerate(kept, 1):
        label = norm(by_id[str(c["concept_id"])].get("preferred_label"))
        if any(needle in label for needle in needles):
            return display_rank, int(c["rank"])
    return None, None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    targetable = [r for r in rows if r["expected"] and not r["should_abstain"]]
    abstain = [r for r in rows if r["should_abstain"]]
    clarify = [r for r in rows if r["should_clarify"]]
    return {
        "cases": len(rows),
        "mean_displayed_before": round(sum(r["before_count"] for r in rows) / max(1, len(rows)), 3),
        "mean_displayed_after": round(sum(r["after_count"] for r in rows) / max(1, len(rows)), 3),
        "full_five_before": sum(r["before_count"] == 5 for r in rows),
        "full_five_after": sum(r["after_count"] == 5 for r in rows),
        "targetable": {
            "cases": len(targetable),
            "top1_before": sum(r["family_rank_before"] == 1 for r in targetable),
            "top1_after": sum(r["family_original_rank_after"] == 1 for r in targetable),
            "hit5_before": sum(r["family_rank_before"] is not None and r["family_rank_before"] <= 5 for r in targetable),
            "hit5_after": sum(r["family_display_rank_after"] is not None for r in targetable),
            "tail_hits_before": sum(r["family_rank_before"] is not None and 2 <= r["family_rank_before"] <= 5 for r in targetable),
            "tail_hits_after": sum(r["family_original_rank_after"] is not None and 2 <= r["family_original_rank_after"] <= 5 for r in targetable),
        },
        "explicit_abstention": {
            "cases": len(abstain),
            "empty_before": sum(r["before_count"] == 0 for r in abstain),
            "empty_after": sum(r["after_count"] == 0 for r in abstain),
            "full_five_before": sum(r["before_count"] == 5 for r in abstain),
            "full_five_after": sum(r["after_count"] == 5 for r in abstain),
        },
        "clarification": {
            "cases": len(clarify),
            "mean_displayed_before": round(sum(r["before_count"] for r in clarify) / max(1, len(clarify)), 3),
            "mean_displayed_after": round(sum(r["after_count"] for r in clarify) / max(1, len(clarify)), 3),
        },
    }


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required")

    primary = json.loads(Path("research/evaluation/v31/p80-display-semantic-oracle-v0.json").read_text(encoding="utf-8"))
    if primary.get("id") != EXPECTED_PRIMARY_ID:
        raise RuntimeError("primary semantic-oracle result id drift")
    if primary.get("model") != MODEL or primary.get("prompt_version") != PROMPT_VERSION or primary.get("prompt_sha256") != PROMPT_SHA256:
        raise RuntimeError("semantic-oracle prompt/model drift")
    gate = primary.get("decision_gate") or {}
    if not (gate.get("strong_passed") or gate.get("promising_passed")):
        raise RuntimeError("primary semantic-oracle gate did not pass; opened replay forbidden")

    by_id, _ids, _ssyk4, ranker, exact, surfaces, phrase_map, _primary_ids = load_system()
    stress = json.loads(Path("research/evaluation/v31/opened-live-semantic-stress-v1.json").read_text(encoding="utf-8"))
    raw_cases = stress.get("yv") or []
    if len(raw_cases) != EXPECTED_STRESS_CASES:
        raise RuntimeError("opened stress drift")

    cases: list[dict[str, Any]] = []
    for source in raw_cases:
        query = str(source["query"])
        scored = rank_c1(ranker, query, exact, surfaces)
        candidates = [
            {"rank": i, "concept_id": cid, "score": float(score), "signal": signal}
            for i, (cid, score, signal) in enumerate(scored[:5], 1)
        ]
        cases.append({
            "ad_id": f"opened-{source['id']}",
            "query": query,
            "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
            "query_word_count": len(query.split()),
            "concept_id": "",
            "candidates": candidates,
            "opened_source": source,
        })

    judgments, usage = semantic_judge_batches(
        cases, by_id, phrase_map,
        api_key=api_key,
        batch_size=6,
        requests_per_minute=3.0,
    )

    rows: list[dict[str, Any]] = []
    for case in cases:
        source = case["opened_source"]
        key = f"{case['ad_id']}:{case['query_sha256'][:16]}"
        verdicts = judgments[key]
        candidates = []
        for c in case["candidates"]:
            cid = str(c["concept_id"])
            candidates.append({
                "rank": int(c["rank"]),
                "concept_id": cid,
                "label": str(by_id[cid].get("preferred_label") or cid),
                "verdict": verdicts[cid],
            })
        kept = [c for c in candidates if display_keep(c)]
        expected = [str(x) for x in source.get("expect") or []]
        before_scored = [(str(c["concept_id"]), float(c["score"]), str(c["signal"])) for c in case["candidates"]]
        rank_before = family_rank(before_scored, by_id, expected)
        display_after, original_after = displayed_family_rank(kept, by_id, expected)
        rows.append({
            "id": str(source["id"]),
            "category": str(source["category"]),
            "query": str(source["query"]),
            "expected": expected,
            "should_abstain": bool(source.get("should_abstain")),
            "should_clarify": bool(source.get("should_clarify")),
            "family_rank_before": rank_before,
            "family_display_rank_after": display_after,
            "family_original_rank_after": original_after,
            "before_count": len(candidates),
            "after_count": len(kept),
            "before": candidates,
            "after": kept,
        })

    overall = summarize(rows)
    by_id_row = {r["id"]: r for r in rows}
    yv01 = by_id_row["yv01"]
    yv02 = by_id_row["yv02"]

    yv01_bad = {norm("Apotekare"), norm("Receptarie"), norm("Sjukhusvaktmästare")}
    yv01_after = {norm(c["label"]) for c in yv01["after"]}
    yv01_removed = len(yv01_bad - yv01_after)
    yv01_ok = yv01_removed >= 2 and yv01["family_display_rank_after"] is not None

    yv02_bad = {norm("Växeltelefonist"), norm("Affärskonsult, IT")}
    yv02_after = {norm(c["label"]) for c in yv02["after"]}
    yv02_ok = not (yv02_bad & yv02_after) and yv02["family_display_rank_after"] is not None

    targetable = overall["targetable"]
    accepted = (
        int(targetable["hit5_after"]) >= 27
        and int(targetable["tail_hits_after"]) >= 12
        and float(overall["mean_displayed_after"]) <= 3.5
        and yv01_ok
        and yv02_ok
    )

    result = {
        "id": "YV-P80-display-semantic-oracle-opened-replay-v0",
        "status": "opened diagnostic only; exact frozen semantic oracle replay; no tuning",
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": PROMPT_SHA256,
        "opened_rows_used_to_choose_prompt_model_or_rule": False,
        "overall": overall,
        "product_sanity": {
            "yv01_removed_known_bad_count": yv01_removed,
            "yv01_passed": yv01_ok,
            "yv02_passed": yv02_ok,
            "yv01": yv01,
            "yv02": yv02,
        },
        "prefrozen_opened_acceptance_passed": accepted,
        "decision": "semantic information is strong enough to justify a compact-student distillation experiment" if accepted else "semantic oracle did not transfer strongly enough; do not distill from this oracle without new independent evidence",
        "usage_metadata": usage,
        "rows": rows,
        "interpretation_boundary": "Opened diagnostic acceptance/falsification only. This is not a human relevance precision estimate and cannot tune the oracle.",
    }
    out = Path("research/evaluation/v31/p80-display-semantic-oracle-opened-replay-v0.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "overall": overall,
        "product_sanity": {k: v for k, v in result["product_sanity"].items() if k not in {"yv01", "yv02"}},
        "prefrozen_opened_acceptance_passed": accepted,
        "decision": result["decision"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
