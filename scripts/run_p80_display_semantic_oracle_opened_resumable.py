#!/usr/bin/env python3
"""Durable replay of the exact frozen semantic oracle on the 54 opened stress cases.

Execution durability only: this imports the already-frozen prompt/model/evidence/display
contract and the already-prefrozen opened acceptance rule. Transport failures are
checkpointed and never converted into semantic verdicts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import evaluate_p80_display_semantic_oracle as oracle
import replay_p80_display_semantic_oracle_opened as replay
import run_p80_display_semantic_oracle_resumable as durable

EXPECTED_PRIMARY_ID = "YV-P80-display-semantic-oracle-v0"
EXPECTED_STRESS_CASES = 54
DEFAULT_CHECKPOINT = "research/evaluation/v31/p80-display-semantic-oracle-opened-checkpoint-v0.json"
DEFAULT_STATUS = "research/evaluation/v31/p80-display-semantic-oracle-opened-run-status-v0.json"
DEFAULT_OUTPUT = "research/evaluation/v31/p80-display-semantic-oracle-opened-replay-v0.json"


def validate_primary(path: Path) -> dict[str, Any]:
    primary = json.loads(path.read_text(encoding="utf-8"))
    if primary.get("id") != EXPECTED_PRIMARY_ID or not primary.get("complete"):
        raise RuntimeError("complete primary semantic-oracle result is required")
    if (
        primary.get("model") != oracle.MODEL
        or primary.get("prompt_version") != oracle.PROMPT_VERSION
        or primary.get("prompt_sha256") != oracle.PROMPT_SHA256
    ):
        raise RuntimeError("semantic-oracle prompt/model drift")
    gate = primary.get("decision_gate") or {}
    if not (gate.get("strong_passed") or gate.get("promising_passed")):
        raise RuntimeError("primary semantic-oracle gate did not pass; opened replay forbidden")
    return primary


def build_cases() -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], list[dict[str, Any]]]:
    by_id, _ids, _ssyk4, ranker, exact, surfaces, phrase_map, _primary_ids = oracle.load_system()
    stress = json.loads(Path("research/evaluation/v31/opened-live-semantic-stress-v1.json").read_text(encoding="utf-8"))
    raw_cases = stress.get("yv") or []
    if len(raw_cases) != EXPECTED_STRESS_CASES:
        raise RuntimeError("opened stress drift")

    cases: list[dict[str, Any]] = []
    for source in raw_cases:
        query = str(source["query"])
        scored = oracle.rank_c1(ranker, query, exact, surfaces)
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
    return by_id, phrase_map, cases


def opened_status(state: dict[str, Any], cases: list[dict[str, Any]], *, phase: str) -> dict[str, Any]:
    expected = {oracle.case_key(case) for case in cases}
    completed = set(state["judgments"])
    missing = sorted(expected - completed)
    return {
        "id": "YV-P80-display-semantic-oracle-opened-v0-run-status",
        "phase": phase,
        "complete": not missing,
        "expected_cases": len(expected),
        "completed_cases": len(completed),
        "missing_cases": len(missing),
        "missing_case_keys": missing,
        "transport_failure_cases": len(state.get("transport_failures") or {}),
        "protocol": state["protocol"],
        "case_set_sha256": state["case_set_sha256"],
        "acceptance_evaluable": not missing,
    }


def build_result(cases: list[dict[str, Any]], judgments: dict[str, dict[str, str]], by_id: dict[str, dict[str, Any]], usage: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        source = case["opened_source"]
        key = oracle.case_key(case)
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
        kept = [c for c in candidates if oracle.display_keep(c)]
        expected = [str(x) for x in source.get("expect") or []]
        before_scored = [(str(c["concept_id"]), float(c["score"]), str(c["signal"])) for c in case["candidates"]]
        rank_before = replay.family_rank(before_scored, by_id, expected)
        display_after, original_after = replay.displayed_family_rank(kept, by_id, expected)
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

    overall = replay.summarize(rows)
    by_row = {row["id"]: row for row in rows}
    yv01 = by_row["yv01"]
    yv02 = by_row["yv02"]

    yv01_bad = {replay.norm("Apotekare"), replay.norm("Receptarie"), replay.norm("Sjukhusvaktmästare")}
    yv01_after = {replay.norm(c["label"]) for c in yv01["after"]}
    yv01_removed = len(yv01_bad - yv01_after)
    yv01_ok = yv01_removed >= 2 and yv01["family_display_rank_after"] is not None

    yv02_bad = {replay.norm("Växeltelefonist"), replay.norm("Affärskonsult, IT")}
    yv02_after = {replay.norm(c["label"]) for c in yv02["after"]}
    yv02_ok = not (yv02_bad & yv02_after) and yv02["family_display_rank_after"] is not None

    targetable = overall["targetable"]
    accepted = (
        int(targetable["hit5_after"]) >= 27
        and int(targetable["tail_hits_after"]) >= 12
        and float(overall["mean_displayed_after"]) <= 3.5
        and yv01_ok
        and yv02_ok
    )

    return {
        "id": "YV-P80-display-semantic-oracle-opened-replay-v0",
        "status": "opened diagnostic only; exact frozen semantic oracle replay; no tuning",
        "complete": True,
        "model": oracle.MODEL,
        "prompt_version": oracle.PROMPT_VERSION,
        "prompt_sha256": oracle.PROMPT_SHA256,
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--primary", default="research/evaluation/v31/p80-display-semantic-oracle-v0.json")
    ap.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    ap.add_argument("--status-output", default=DEFAULT_STATUS)
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--batch-size", type=int, default=6)
    ap.add_argument("--requests-per-minute", type=float, default=3.0)
    ap.add_argument("--single-case-attempts", type=int, default=8)
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required")
    validate_primary(Path(args.primary))
    by_id, phrase_map, cases = build_cases()

    checkpoint = Path(args.checkpoint)
    status_path = Path(args.status_output)
    state = durable.load_state(checkpoint, cases)
    durable.atomic_json(checkpoint, state)
    durable.atomic_json(status_path, opened_status(state, cases, phase="initialized"))

    # semantic_calls is execution-only and uses the same frozen oracle prompt/model.
    durable.semantic_calls(
        cases,
        by_id,
        phrase_map,
        state,
        checkpoint,
        status_path,
        api_key=api_key,
        batch_size=args.batch_size,
        requests_per_minute=args.requests_per_minute,
        single_case_attempts=args.single_case_attempts,
    )

    complete = len(state["judgments"]) == len(cases)
    durable.atomic_json(status_path, opened_status(state, cases, phase="complete" if complete else "incomplete-transport"))
    if not complete:
        print(json.dumps(opened_status(state, cases, phase="incomplete-transport"), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    result = build_result(cases, state["judgments"], by_id, state.get("usage_metadata") or [])
    durable.atomic_json(Path(args.output), result)
    print(json.dumps({
        "overall": result["overall"],
        "product_sanity": {k: v for k, v in result["product_sanity"].items() if k not in {"yv01", "yv02"}},
        "prefrozen_opened_acceptance_passed": result["prefrozen_opened_acceptance_passed"],
        "decision": result["decision"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
