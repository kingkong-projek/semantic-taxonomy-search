#!/usr/bin/env python3
"""Execution-only duplicate-case adapter for semantic-display hard-confusion v2.

The frozen v2 method is unchanged. Historical retrieval can yield exact duplicate rows
with the same semantic case key. Durable checkpoints are keyed by that case key, so the
existing raw-case fingerprint is retained for checkpoint reuse while decision metrics
count each unique semantic case once.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from typing import Any

import evaluate_semantic_display_hard_confusion_v2 as v2


def unique_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for case in cases:
        key = v2.oracle.case_key(case)
        signature = {
            "pair_id": str(case["pair_id"]),
            "target": str(case["concept_id"]),
            "negative": str(case["negative_concept_id"]),
            "query_sha256": str(case["query_sha256"]),
            "candidates": [str(c["concept_id"]) for c in case["candidates"]],
        }
        previous = seen.get(key)
        if previous is None:
            seen[key] = signature
            out.append(case)
        elif previous != signature:
            raise RuntimeError(f"duplicate case_key has conflicting semantics: {key}")
    return out


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

    prereg = v2.load_prereg()
    contrast, contrast_raw, contrast_sha = v2.load_contrast()
    pairs = v2.load_pairs()
    by_id, _ids, _ssyk4, _ranker, _exact, _surfaces, phrase_map, _primary = v2.oracle.load_system()

    # Keep raw_cases unchanged when talking to durable.run_arm so the already-frozen
    # control checkpoint fingerprint remains valid. Only decision accounting is deduped.
    raw_cases = v2.fetch_cases(
        by_id, pairs, search_limit=args.search_limit, accepted=args.ads_per_concept
    )
    cases = unique_cases(raw_cases)
    duplicate_rows = len(raw_cases) - len(cases)
    print(
        f"v2 case accounting: raw_rows={len(raw_cases)} unique_cases={len(cases)} "
        f"duplicate_rows={duplicate_rows}",
        flush=True,
    )

    pair_coverage = len({c["pair_id"] for c in cases})
    sample_valid = (
        len(cases) >= int(prereg["query_evaluation"]["minimum_total_cases_for_decision"])
        and pair_coverage
        >= int(prereg["query_evaluation"]["minimum_pairs_with_at_least_one_case"])
    )
    sample_sha = hashlib.sha256(
        json.dumps(
            [
                {
                    "case_key": v2.oracle.case_key(c),
                    "pair_id": c["pair_id"],
                    "target": c["concept_id"],
                    "negative": c["negative_concept_id"],
                }
                for c in cases
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    if not sample_valid:
        v2.durable.atomic_json(
            v2.RESULT,
            {
                "id": "YV-semantic-display-hard-confusion-v2-result",
                "status": "inconclusive: preregistered 2021 sample floor not met",
                "sample": {
                    "raw_rows": len(raw_cases),
                    "cases": len(cases),
                    "duplicate_case_rows": duplicate_rows,
                    "pairs": pair_coverage,
                    "sha256": sample_sha,
                },
                "opened_17_88_loaded": False,
                "decision_gate": {"passed": False, "sample_valid": False},
            },
        )
        return 0

    control = v2.run_arm(
        "control",
        raw_cases,
        by_id,
        phrase_map,
        contrast,
        v2.CONTROL_CP,
        v2.CONTROL_STATUS,
        api_key=api_key,
        batch_size=args.batch_size,
        rpm=args.requests_per_minute,
        attempts=args.single_case_attempts,
    )
    if len(control["judgments"]) != len(cases):
        print(
            f"control incomplete by unique case key: {len(control['judgments'])}/{len(cases)}",
            flush=True,
        )
        return 0
    v2.durable.write_checkpoint(
        v2.CONTROL_CP,
        v2.CONTROL_STATUS,
        control,
        raw_cases,
        phase="control-complete-unique-case-key",
    )

    challenger = v2.run_arm(
        "challenger",
        raw_cases,
        by_id,
        phrase_map,
        contrast,
        v2.CHALLENGER_CP,
        v2.CHALLENGER_STATUS,
        api_key=api_key,
        batch_size=args.batch_size,
        rpm=args.requests_per_minute,
        attempts=args.single_case_attempts,
    )
    if len(challenger["judgments"]) != len(cases):
        print(
            f"challenger incomplete by unique case key: {len(challenger['judgments'])}/{len(cases)}",
            flush=True,
        )
        return 0
    v2.durable.write_checkpoint(
        v2.CHALLENGER_CP,
        v2.CHALLENGER_STATUS,
        challenger,
        raw_cases,
        phase="challenger-complete-unique-case-key",
    )

    cm = v2.v1.arm_metrics(cases, control["judgments"])
    vm = v2.v1.arm_metrics(cases, challenger["judgments"])
    improvement = round(
        vm["hard_negative_drop_rate"] - cm["hard_negative_drop_rate"], 6
    )
    evaluated_pairs = list(vm["by_pair"].values())
    breadth_success = sum(
        float(x["hard_negative_drop_rate"]) >= 0.50 for x in evaluated_pairs
    )
    breadth_rate = round(breadth_success / max(1, len(evaluated_pairs)), 6)

    safety = (
        vm["target_non_drop_rate"] >= 0.98
        and vm["target_drop"] <= cm["target_drop"] + 1
    )
    absolute = vm["hard_negative_drop_rate"] >= 0.70
    material = improvement >= 0.20
    breadth = breadth_rate >= 0.60
    contrast_coverage = int(contrast_raw["pairs_with_bilateral_contrast"]) >= int(
        contrast_raw["coverage_gate_minimum"]
    )
    passed = bool(
        sample_valid and contrast_coverage and safety and absolute and material and breadth
    )

    result = {
        "id": "YV-semantic-display-hard-confusion-v2-result",
        "status": "complete independent 2021 pairwise-contrast evidence",
        "preregistration": str(v2.PREREG),
        "opened_17_88_loaded": False,
        "query_year": v2.YEAR,
        "raw_query_text_committed": False,
        "model": v2.oracle.MODEL,
        "prompt_version": v2.PROMPT_VERSION,
        "prompt_sha256": v2.PROMPT_SHA256,
        "contrast_artifact": str(v2.CONTRAST),
        "contrast_artifact_sha256": contrast_sha,
        "contrast_pairs_with_bilateral_evidence": int(
            contrast_raw["pairs_with_bilateral_contrast"]
        ),
        "sample": {
            "raw_rows": len(raw_cases),
            "cases": len(cases),
            "duplicate_case_rows": duplicate_rows,
            "pairs_with_cases": pair_coverage,
            "sha256": sample_sha,
        },
        "control": {"evidence_version": v2.CONTROL_EVIDENCE, "metrics": cm},
        "challenger": {"evidence_version": v2.CHALLENGER_EVIDENCE, "metrics": vm},
        "hard_negative_drop_improvement": improvement,
        "pair_breadth": {
            "successful_pairs": breadth_success,
            "evaluated_pairs": len(evaluated_pairs),
            "rate": breadth_rate,
        },
        "decision_gate": {
            "sample_valid": sample_valid,
            "contrast_coverage_passed": contrast_coverage,
            "target_safety_passed": safety,
            "hard_negative_absolute_passed": absolute,
            "hard_negative_materiality_passed": material,
            "pair_breadth_passed": breadth,
            "passed": passed,
            "if_pass": "freeze exact v2 contrast artifact and oracle contract; only then replay unchanged opened stress as falsifier",
            "if_fail": "do not replay opened and do not distill; reassess richer independent source domains or human relevance evidence",
        },
        "interpretation_boundary": (
            "Historical structured occupation is a proxy target. Pairwise contrast spans "
            "are verbatim canonical evidence selected semantically, not human relevance truth. "
            "Exact duplicate semantic case keys are counted once."
        ),
    }
    v2.durable.atomic_json(v2.RESULT, result)
    print(
        json.dumps(
            {
                "sample": result["sample"],
                "control": cm,
                "challenger": vm,
                "improvement": improvement,
                "breadth": result["pair_breadth"],
                "gate": result["decision_gate"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
