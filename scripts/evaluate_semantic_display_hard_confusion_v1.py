#!/usr/bin/env python3
"""Independent hard-confusion test for richer semantic candidate evidence.

Preregistered in research/evaluation/v31/semantic-display-hard-confusion-v1-preregistration.json.
Opened stress rows are never loaded. The frozen v0 semantic verdict prompt is reused.
Execution is resumable through the existing per-case durable checkpoint machinery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import evaluate_p80_display_semantic_oracle as oracle
import run_p80_display_semantic_oracle_resumable as durable

PREREG = Path("research/evaluation/v31/semantic-display-hard-confusion-v1-preregistration.json")
ATOMS = Path("research/evaluation/v31/compile-time-semantic-a593-confusion-task-atoms-v0.json")
YEAR = 2022
CONTROL_EVIDENCE = "label-alt3-definition50-task2x24-v0"
CHALLENGER_EVIDENCE = "label-alt3-definition50-canonical-task6x24-v1"
RESULT = Path("research/evaluation/v31/semantic-display-hard-confusion-v1-result.json")
CONTROL_CP = Path("research/evaluation/v31/semantic-display-hard-confusion-v1-control-checkpoint.json")
CONTROL_STATUS = Path("research/evaluation/v31/semantic-display-hard-confusion-v1-control-status.json")
CHALLENGER_CP = Path("research/evaluation/v31/semantic-display-hard-confusion-v1-challenger-checkpoint.json")
CHALLENGER_STATUS = Path("research/evaluation/v31/semantic-display-hard-confusion-v1-challenger-status.json")


def load_prereg() -> dict[str, Any]:
    p = json.loads(PREREG.read_text(encoding="utf-8"))
    if p.get("status") != "frozen before v1 oracle outcomes":
        raise RuntimeError("v1 preregistration is not frozen")
    if int(p["query_evaluation"]["year"]) != YEAR:
        raise RuntimeError("v1 evaluation year drift")
    if p["opened_data_policy"].get("opened_17_88_loaded_for_design_or_execution") is not False:
        raise RuntimeError("opened-data policy drift")
    return p


def load_atoms() -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    raw = json.loads(ATOMS.read_text(encoding="utf-8"))
    if int(raw.get("pairs", -1)) != 11 or int(raw.get("concepts", -1)) != 22:
        raise RuntimeError("hard-confusion artifact drift")
    if raw.get("contrast_cues_or_descriptions_sent_to_generator") is not False:
        raise RuntimeError("hard-confusion evidence independence drift")
    rows = raw.get("rows") or []
    atom_map: dict[str, list[str]] = {}
    pairs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, row in enumerate(rows):
        a, b = str(row["a_concept_id"]), str(row["b_concept_id"])
        aa = [str(x) for x in row.get("a_atoms") or []]
        ba = [str(x) for x in row.get("b_atoms") or []]
        if len(aa) != 6 or len(ba) != 6:
            raise RuntimeError(f"expected six frozen task atoms for pair {i}")
        if a in seen or b in seen:
            raise RuntimeError("hard-confusion concepts must be unique across pairs")
        seen.update((a, b))
        atom_map[a] = aa
        atom_map[b] = ba
        pairs.append({"pair_id": f"pair-{i+1:02d}", "a": a, "b": b})
    if len(pairs) != 11 or len(seen) != 22:
        raise RuntimeError("hard-confusion pair parsing drift")
    return pairs, atom_map


def fetch_cases(by_id: dict[str, dict[str, Any]], pairs: list[dict[str, Any]], *, search_limit: int, accepted: int) -> list[dict[str, Any]]:
    concept_to_pair: dict[str, tuple[str, str]] = {}
    for p in pairs:
        concept_to_pair[p["a"]] = (p["pair_id"], p["b"])
        concept_to_pair[p["b"]] = (p["pair_id"], p["a"])
    groups: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(oracle.fetch_year_concept, cid, by_id[cid], YEAR, search_limit=search_limit, accepted=accepted): cid
            for cid in sorted(concept_to_pair)
        }
        for future in as_completed(futures):
            groups.append(future.result())
    groups.sort(key=lambda x: x["concept_id"])
    cases: list[dict[str, Any]] = []
    for group in groups:
        cid = str(group["concept_id"])
        pair_id, negative = concept_to_pair[cid]
        for row in group.get("accepted") or []:
            # rank here is only a stable case fingerprint field. Teacher never sees it.
            ordered = sorted((cid, negative))
            candidates = [
                {"rank": i + 1, "concept_id": x, "score": 0.0, "signal": "fixed-hard-confusion-pair"}
                for i, x in enumerate(ordered)
            ]
            cases.append({
                "ad_id": f"hc-{pair_id}-{cid}-{row["ad_id"]}",
                "query": str(row["query"]),
                "query_sha256": str(row["query_sha256"]),
                "query_word_count": int(row["query_word_count"]),
                "concept_id": cid,
                "negative_concept_id": negative,
                "pair_id": pair_id,
                "candidates": candidates,
            })
    cases.sort(key=lambda c: (c["pair_id"], c["concept_id"], c["ad_id"], c["query_sha256"]))
    return cases


def run_arm(
    arm: str,
    evidence_version: str,
    cases: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    phrase_map: dict[str, list[str]],
    checkpoint: Path,
    status: Path,
    *, api_key: str,
    batch_size: int,
    rpm: float,
    attempts: int,
) -> dict[str, Any]:
    original_version = oracle.EVIDENCE_VERSION
    original_max = oracle.MAX_TASK_PHRASES
    original_evidence = oracle.candidate_evidence
    try:
        oracle.EVIDENCE_VERSION = evidence_version
        if arm == "control":
            oracle.MAX_TASK_PHRASES = 2
        elif arm == "challenger":
            oracle.MAX_TASK_PHRASES = 6

            def rich_evidence(concept: dict[str, Any], phrases: list[str]) -> dict[str, Any]:
                base = original_evidence(concept, [])
                base["task_evidence"] = [oracle.clip_words(x, 24) for x in list(phrases)[:6]]
                return base

            oracle.candidate_evidence = rich_evidence
        else:
            raise ValueError(arm)

        state = durable.load_state(checkpoint, cases)
        durable.write_checkpoint(checkpoint, status, state, cases, phase=f"{arm}-initialized")
        durable.semantic_calls(
            cases,
            by_id,
            phrase_map,
            state,
            checkpoint,
            status,
            api_key=api_key,
            batch_size=batch_size,
            requests_per_minute=rpm,
            single_case_attempts=attempts,
        )
        complete = len(state["judgments"]) == len(cases)
        durable.write_checkpoint(checkpoint, status, state, cases, phase=f"{arm}-complete" if complete else f"{arm}-incomplete")
        return state
    finally:
        oracle.EVIDENCE_VERSION = original_version
        oracle.MAX_TASK_PHRASES = original_max
        oracle.candidate_evidence = original_evidence


def arm_metrics(cases: list[dict[str, Any]], judgments: dict[str, dict[str, str]]) -> dict[str, Any]:
    target_drop = target_keep = target_uncertain = 0
    negative_drop = negative_keep = negative_uncertain = 0
    by_pair: dict[str, dict[str, int]] = {}
    for case in cases:
        key = oracle.case_key(case)
        if key not in judgments:
            continue
        target = str(case["concept_id"])
        negative = str(case["negative_concept_id"])
        tv = judgments[key][target]
        nv = judgments[key][negative]
        target_drop += tv == "drop"
        target_keep += tv == "keep"
        target_uncertain += tv == "uncertain"
        negative_drop += nv == "drop"
        negative_keep += nv == "keep"
        negative_uncertain += nv == "uncertain"
        row = by_pair.setdefault(case["pair_id"], {"cases": 0, "target_drop": 0, "negative_drop": 0})
        row["cases"] += 1
        row["target_drop"] += tv == "drop"
        row["negative_drop"] += nv == "drop"
    n = len(cases)
    return {
        "cases": n,
        "target_non_drop": n - target_drop,
        "target_non_drop_rate": round((n - target_drop) / max(1, n), 6),
        "target_drop": target_drop,
        "target_keep": target_keep,
        "target_keep_rate": round(target_keep / max(1, n), 6),
        "target_uncertain": target_uncertain,
        "hard_negative_drop": negative_drop,
        "hard_negative_drop_rate": round(negative_drop / max(1, n), 6),
        "hard_negative_keep": negative_keep,
        "hard_negative_uncertain": negative_uncertain,
        "by_pair": {
            pair: {
                **counts,
                "target_non_drop_rate": round((counts["cases"] - counts["target_drop"]) / max(1, counts["cases"]), 6),
                "hard_negative_drop_rate": round(counts["negative_drop"] / max(1, counts["cases"]), 6),
            }
            for pair, counts in sorted(by_pair.items())
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=6)
    ap.add_argument("--requests-per-minute", type=float, default=3.0)
    ap.add_argument("--single-case-attempts", type=int, default=8)
    ap.add_argument("--search-limit", type=int, default=25)
    ap.add_argument("--ads-per-concept", type=int, default=5)
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY required")
    prereg = load_prereg()
    pairs, atom_map = load_atoms()
    by_id, _ids, _ssyk4, _ranker, _exact, _surfaces, v0_phrase_map, _primary_ids = oracle.load_system()
    if not set(atom_map).issubset(by_id):
        raise RuntimeError("hard-confusion concept missing from v31 taxonomy")
    cases = fetch_cases(by_id, pairs, search_limit=args.search_limit, accepted=args.ads_per_concept)
    pair_coverage = len({c["pair_id"] for c in cases})
    sample_valid = len(cases) >= int(prereg["query_evaluation"]["minimum_total_cases_for_decision"]) and pair_coverage >= int(prereg["query_evaluation"]["minimum_pairs_with_at_least_one_case"])
    sample_fingerprint = hashlib.sha256(json.dumps([
        {"case_key": oracle.case_key(c), "pair_id": c["pair_id"], "target": c["concept_id"], "negative": c["negative_concept_id"]}
        for c in cases
    ], sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    if not sample_valid:
        durable.atomic_json(RESULT, {
            "id": "YV-semantic-display-hard-confusion-v1-result",
            "status": "inconclusive: preregistered sample floor not met",
            "sample": {"cases": len(cases), "pairs": pair_coverage, "sha256": sample_fingerprint},
            "decision_gate_passed": False
        })
        return 0

    control = run_arm(
        "control", CONTROL_EVIDENCE, cases, by_id, v0_phrase_map, CONTROL_CP, CONTROL_STATUS,
        api_key=api_key, batch_size=args.batch_size, rpm=args.requests_per_minute, attempts=args.single_case_attempts,
    )
    if len(control["judgments"]) != len(cases):
        return 0

    challenger = run_arm(
        "challenger", CHALLENGER_EVIDENCE, cases, by_id, atom_map, CHALLENGER_CP, CHALLENGER_STATUS,
        api_key=api_key, batch_size=args.batch_size, rpm=args.requests_per_minute, attempts=args.single_case_attempts,
    )
    if len(challenger["judgments"]) != len(cases):
        return 0

    cm = arm_metrics(cases, control["judgments"])
    vm = arm_metrics(cases, challenger["judgments"])
    improvement = round(vm["hard_negative_drop_rate"] - cm["hard_negative_drop_rate"], 6)
    safety = vm["target_non_drop_rate"] >= 0.98 and vm["target_drop"] <= cm["target_drop"] + 1
    absolute = vm["hard_negative_drop_rate"] >= 0.70
    material = improvement >= 0.10
    passed = bool(sample_valid and safety and absolute and material)

    result = {
        "id": "YV-semantic-display-hard-confusion-v1-result",
        "status": "complete independent 2022 hard-confusion evidence",
        "preregistration": str(PREREG),
        "opened_17_88_loaded": false,
        "model": oracle.MODEL,
        "prompt_version": oracle.PROMPT_VERSION,
        "prompt_sha256": oracle.PROMPT_SHA256,
        "query_year": YEAR,
        "raw_query_text_committed": false,
        "sample": {
            "cases": len(cases),
            "pairs_with_cases": pair_coverage,
            "fixed_pairs_total": 11,
            "sha256": sample_fingerprint,
            "case_rows": [
                {"case_key": oracle.case_key(c), "query_sha256": c["query_sha256"], "pair_id": c["pair_id"], "target_concept_id": c["concept_id"], "paired_negative_concept_id": c["negative_concept_id"]}
                for c in cases
            ],
        },
        "control": {"evidence_version": CONTROL_EVIDENCE, "metrics": cm},
        "challenger": {"evidence_version": CHALLENGER_EVIDENCE, "metrics": vm},
        "hard_negative_drop_improvement": improvement,
        "decision_gate": {
            "sample_valid": sample_valid,
            "target_safety_passed": safety,
            "hard_negative_absolute_passed": absolute,
            "hard_negative_materiality_passed": material,
            "passed": passed,
            "if_pass": "freeze v1 evidence contract, then replay unchanged opened stress only as falsifier",
            "if_fail": "do not replay opened and do not distill; reassess independent evidence mechanism",
        },
        "interpretation_boundary": "Historical structured occupation is a proxy target and task atoms are canonical-derived model representations, not human relevance truth. Human validation remains required for promotion."
    }
    durable.atomic_json(RESULT, result)
    print(json.dumps({"sample": result["sample"], "control": cm, "challenger": vm, "improvement": improvement, "gate": result["decision_gate"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
