#!/usr/bin/env python3
"""Failure-isolated/resumable executor for the prefrozen P80 semantic oracle.

This module changes execution durability only. It imports the frozen semantic prompt,
evidence contract, verdicts, ranking and gates from evaluate_p80_display_semantic_oracle.
No transport failure is converted into a semantic verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import evaluate_p80_display_semantic_oracle as oracle

CHECKPOINT_VERSION = "yv-p80-semantic-oracle-checkpoint-v1"
DEFAULT_CHECKPOINT = "research/evaluation/v31/p80-display-semantic-oracle-checkpoint-v0.json"
DEFAULT_STATUS = "research/evaluation/v31/p80-display-semantic-oracle-run-status-v0.json"


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def protocol_contract() -> dict[str, Any]:
    return {
        "checkpoint_version": CHECKPOINT_VERSION,
        "model": oracle.MODEL,
        "prompt_version": oracle.PROMPT_VERSION,
        "prompt_sha256": oracle.PROMPT_SHA256,
        "evidence_version": oracle.EVIDENCE_VERSION,
        "verdicts": sorted(oracle.VERDICTS),
    }


def case_fingerprint(cases: list[dict[str, Any]]) -> str:
    rows = []
    for case in cases:
        rows.append({
            "case_key": oracle.case_key(case),
            "query_sha256": str(case["query_sha256"]),
            "candidates": [
                {"rank": int(c["rank"]), "concept_id": str(c["concept_id"])}
                for c in case["candidates"]
            ],
        })
    wire = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(wire.encode("utf-8")).hexdigest()


def blank_state(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "protocol": protocol_contract(),
        "case_set_sha256": case_fingerprint(cases),
        "expected_cases": len(cases),
        "judgments": {},
        "transport_failures": {},
        "usage_metadata": [],
    }


def load_state(path: Path, cases: list[dict[str, Any]]) -> dict[str, Any]:
    expected = blank_state(cases)
    if not path.exists():
        return expected
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("protocol") != expected["protocol"]:
        raise RuntimeError("checkpoint protocol drift; refusing to mix semantic contracts")
    if state.get("case_set_sha256") != expected["case_set_sha256"]:
        raise RuntimeError("checkpoint case-set drift; refusing to mix retrieval outcomes")
    if int(state.get("expected_cases", -1)) != len(cases):
        raise RuntimeError("checkpoint expected-case count drift")

    by_key = {oracle.case_key(case): case for case in cases}
    clean: dict[str, dict[str, str]] = {}
    for key, verdicts in (state.get("judgments") or {}).items():
        if key not in by_key or not isinstance(verdicts, dict):
            continue
        expected_ids = {str(c["concept_id"]) for c in by_key[key]["candidates"]}
        normalized = {str(cid): str(v).casefold() for cid, v in verdicts.items()}
        if set(normalized) == expected_ids and all(v in oracle.VERDICTS for v in normalized.values()):
            clean[key] = normalized
    state["judgments"] = clean
    state.setdefault("transport_failures", {})
    state.setdefault("usage_metadata", [])
    return state


def build_cases(args: argparse.Namespace):
    by_id, ids, ssyk4, ranker, exact, surfaces, phrase_map, primary_ids = oracle.load_system()
    groups: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(
                oracle.fetch_year_concept,
                cid,
                by_id[cid],
                oracle.EVAL_YEAR,
                search_limit=args.search_limit,
                accepted=args.ads_per_concept,
            ): cid
            for cid in primary_ids
        }
        for future in as_completed(futures):
            groups.append(future.result())
    groups.sort(key=lambda x: x["concept_id"])
    cases = [row for group in groups for row in group["accepted"]]
    cases.sort(key=lambda x: (str(x["concept_id"]), str(x["ad_id"])))
    if len(cases) < 600:
        raise RuntimeError(f"unexpectedly small 2024 natural-task set: {len(cases)}")
    for case in cases:
        scored = oracle.rank_c1(ranker, case["query"], exact, surfaces)
        case["candidates"] = [
            {"rank": i, "concept_id": cid, "score": float(score), "signal": signal}
            for i, (cid, score, signal) in enumerate(scored[:5], 1)
        ]
        if len(case["candidates"]) != 5:
            raise RuntimeError(f"Top5 underflow for {oracle.case_key(case)}")
    return by_id, ids, ssyk4, phrase_map, cases


def status_payload(state: dict[str, Any], cases: list[dict[str, Any]], *, phase: str) -> dict[str, Any]:
    expected = {oracle.case_key(c) for c in cases}
    completed = set(state["judgments"])
    missing = sorted(expected - completed)
    return {
        "id": "YV-P80-display-semantic-oracle-v0-run-status",
        "phase": phase,
        "complete": not missing,
        "expected_cases": len(expected),
        "completed_cases": len(completed),
        "missing_cases": len(missing),
        "missing_case_keys": missing[:50],
        "transport_failure_cases": len(state.get("transport_failures") or {}),
        "protocol": state["protocol"],
        "case_set_sha256": state["case_set_sha256"],
        "decision_gate_evaluable": not missing,
    }


def write_checkpoint(checkpoint: Path, status: Path, state: dict[str, Any], cases: list[dict[str, Any]], *, phase: str) -> None:
    atomic_json(checkpoint, state)
    atomic_json(status, status_payload(state, cases, phase=phase))


def semantic_calls(
    cases: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    phrase_map: dict[str, list[str]],
    state: dict[str, Any],
    checkpoint: Path,
    status: Path,
    *,
    api_key: str,
    batch_size: int,
    requests_per_minute: float,
    single_case_attempts: int,
) -> None:
    min_interval = 60.0 / max(0.1, requests_per_minute)
    last_call = 0.0

    def call(batch: list[dict[str, Any]]):
        nonlocal last_call
        elapsed = time.monotonic() - last_call
        if last_call and elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        raw, meta = oracle.call_semantic_with_quota_retry(api_key, oracle.prompt(batch, by_id, phrase_map))
        last_call = time.monotonic()
        return raw, meta

    by_key = {oracle.case_key(case): case for case in cases}
    unresolved = [case for case in cases if oracle.case_key(case) not in state["judgments"]]
    print(f"semantic oracle resume: {len(cases) - len(unresolved)}/{len(cases)} already checkpointed", flush=True)

    for start in range(0, len(unresolved), batch_size):
        batch = unresolved[start : start + batch_size]
        pending = [case for case in batch if oracle.case_key(case) not in state["judgments"]]
        if not pending:
            continue

        try:
            raw, meta = call(pending)
            partial = oracle.parse_response(raw, pending, require_all=False)
            state["usage_metadata"].append(meta)
            for key, verdicts in partial.items():
                state["judgments"][key] = verdicts
                state["transport_failures"].pop(key, None)
            write_checkpoint(checkpoint, status, state, cases, phase="running")
            pending = [case for case in pending if oracle.case_key(case) not in state["judgments"]]
        except Exception as exc:  # transport/batch failure must not discard other cases
            message = f"{type(exc).__name__}: {exc}"[:600]
            print(f"semantic oracle batch transport failure; isolate {len(pending)} case(s): {message}", flush=True)

        # Isolate only missing cases. A permanently malformed response becomes a
        # transport failure record, never a keep/uncertain/drop verdict.
        for case in pending:
            key = oracle.case_key(case)
            last_error = "response omitted case"
            for attempt in range(1, single_case_attempts + 1):
                try:
                    raw, meta = call([case])
                    partial = oracle.parse_response(raw, [case], require_all=False)
                    state["usage_metadata"].append(meta)
                    if key in partial:
                        state["judgments"][key] = partial[key]
                        state["transport_failures"].pop(key, None)
                        write_checkpoint(checkpoint, status, state, cases, phase="running")
                        break
                    last_error = "single-case response omitted case"
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"[:600]
                print(f"semantic oracle isolated retry {attempt}/{single_case_attempts} for {key}: {last_error}", flush=True)
                time.sleep(5.0)
            if key not in state["judgments"]:
                previous = state["transport_failures"].get(key) or {}
                state["transport_failures"][key] = {
                    "attempts_this_run": single_case_attempts,
                    "runs_failed": int(previous.get("runs_failed", 0)) + 1,
                    "last_error": last_error,
                }
                write_checkpoint(checkpoint, status, state, cases, phase="running-with-transport-failures")
                print(f"semantic oracle parked transport failure {key}; continuing", flush=True)

        done = len(state["judgments"])
        print(f"semantic oracle durable progress {done}/{len(cases)}", flush=True)


def build_rows(cases: list[dict[str, Any]], judgments: dict[str, dict[str, str]], ssyk4: dict[str, str]) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        key = oracle.case_key(case)
        if key not in judgments:
            continue
        verdicts = judgments[key]
        candidates = []
        for c in case["candidates"]:
            cid = str(c["concept_id"])
            candidates.append({
                "rank": int(c["rank"]),
                "concept_id": cid,
                "ssyk4": ssyk4[cid],
                "verdict": verdicts[cid],
            })
        rows.append({
            "case_key": key,
            "ad_id": str(case["ad_id"]),
            "query_sha256": str(case["query_sha256"]),
            "query_word_count": int(case["query_word_count"]),
            "concept_id": str(case["concept_id"]),
            "candidates": candidates,
        })
    return rows


def final_result(rows: list[dict[str, Any]], ids: list[str], ssyk4: dict[str, str], usage: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = oracle.summarize(rows, ssyk4)
    strong = (
        metrics["hit5_retention"] >= 0.99
        and metrics["tail_hit_retention"] >= 0.98
        and metrics["safe_cross_ssyk_tail_negative_reduction"] >= 0.60
    )
    promising = (
        metrics["hit5_retention"] >= 0.98
        and metrics["tail_hit_retention"] >= 0.98
        and metrics["safe_cross_ssyk_tail_negative_reduction"] >= 0.50
    )
    return {
        "id": "YV-P80-display-semantic-oracle-v0",
        "status": "complete research semantic sufficiency test; never a runtime LLM proposal",
        "complete": True,
        "model": oracle.MODEL,
        "prompt_version": oracle.PROMPT_VERSION,
        "prompt_sha256": oracle.PROMPT_SHA256,
        "candidate_universe": len(ids),
        "ranker_changed": False,
        "rank_order_changed": False,
        "opened_17_88_loaded": False,
        "teacher_blinding": {
            "rank_hidden": True,
            "candidate_order_deterministically_shuffled": True,
            "structured_target_hidden": True,
            "ssyk_hidden": True,
        },
        "display_contract": "rank1 always retained; ranks2-5 retained for keep/uncertain and removed only for drop",
        "evidence_contract": "fixed compact source-bound payload: canonical label, <=3 alternative labels, definition <=50 words, <=2 already-frozen task phrases <=24 words each; no candidate facts may be invented",
        "evidence_version": oracle.EVIDENCE_VERSION,
        "sample": {
            "year": oracle.EVAL_YEAR,
            "queries": len(rows),
            "concepts": len({r["concept_id"] for r in rows}),
            "rescue_target_ids_excluded": 22,
            "raw_query_text_committed": False,
        },
        "evaluation": metrics,
        "decision_gate": {
            "strong": "overall baseline-Hit@5 target retention >=99%, rank2-5 target retention >=98%, safe cross-SSYK tail-negative reduction >=60%",
            "promising": "overall baseline-Hit@5 target retention >=98%, rank2-5 target retention >=98%, safe cross-SSYK tail-negative reduction >=50%",
            "strong_passed": strong,
            "promising_passed": promising,
            "if_strong_or_promising": "freeze exact prompt/model/rule and replay opened user-style stress unchanged; no retuning",
            "if_neither": "do not build a student; reassess semantic evidence/product interaction rather than adding another heuristic stack",
        },
        "opened_replay_prefrozen_falsifier": {
            "minimum_targetable_hit5_retention": "27/28",
            "minimum_rank2_5_target_retention": "12/13",
            "maximum_mean_visible_list": 3.5,
            "yv01_product_sanity": "must remove at least two of Apotekare, Receptarie, Sjukhusvaktmastare while retaining a sjukskoterska-family result",
            "yv02_product_sanity": "must remove both Vaxeltelefonist and Affarskonsult, IT while retaining an elektriker-family result",
            "purpose": "opened diagnostic acceptance for whether semantic sufficiency is worth distillation; never an accuracy estimate or tuning set",
        },
        "usage_metadata": usage,
        "interpretation_boundary": "Structured ad target and different-SSYK4 negatives are proxy labels, not human relevance judgments. A pass proves semantic information is promising enough to test transfer, not production accuracy.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=6)
    ap.add_argument("--requests-per-minute", type=float, default=3.0)
    ap.add_argument("--single-case-attempts", type=int, default=8)
    ap.add_argument("--search-limit", type=int, default=25)
    ap.add_argument("--ads-per-concept", type=int, default=5)
    ap.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    ap.add_argument("--status-output", default=DEFAULT_STATUS)
    ap.add_argument("--judgments-output", default="research/evaluation/v31/p80-display-semantic-oracle-judgments-v0.jsonl")
    ap.add_argument("--output", default="research/evaluation/v31/p80-display-semantic-oracle-v0.json")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required")

    by_id, ids, ssyk4, phrase_map, cases = build_cases(args)
    checkpoint = Path(args.checkpoint)
    status = Path(args.status_output)
    state = load_state(checkpoint, cases)
    write_checkpoint(checkpoint, status, state, cases, phase="initialized")

    semantic_calls(
        cases,
        by_id,
        phrase_map,
        state,
        checkpoint,
        status,
        api_key=api_key,
        batch_size=args.batch_size,
        requests_per_minute=args.requests_per_minute,
        single_case_attempts=args.single_case_attempts,
    )

    rows = build_rows(cases, state["judgments"], ssyk4)
    complete = len(rows) == len(cases)
    write_checkpoint(checkpoint, status, state, cases, phase="complete" if complete else "incomplete-transport")

    if not complete:
        print(json.dumps(status_payload(state, cases, phase="incomplete-transport"), indent=2, sort_keys=True))
        # Deliberately return success: transport incompleteness is persisted and
        # the workflow gate will refuse evaluation. This avoids losing progress.
        return 0

    judgment_path = Path(args.judgments_output)
    atomic_text(judgment_path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))
    result = final_result(rows, ids, ssyk4, state["usage_metadata"])
    atomic_json(Path(args.output), result)
    print(json.dumps({"evaluation": result["evaluation"], "decision_gate": result["decision_gate"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
