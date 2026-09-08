#!/usr/bin/env python3
"""Replay the frozen A593 evaluator with Swedish Snowball token stemming.

Candidate choice is based only on the frozen A593 corpus-internal 8-fold phrase-slot
holdout diagnostic. This script is committed before any opened 17/88 replay.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import evaluate_gemma_a149 as base
import evaluate_pareto_c1 as c1
from evaluate_gemma_a593_phrase_representation import stemmed_tokens

EXPECTED_TEACHER_ROWS = 593
EXPECTED_TEACHER_PHRASES = EXPECTED_TEACHER_ROWS * 8
CANDIDATE_ID = "YV-A593-Gemma4-26B-sequence-expansion-snowball-v0"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--source-truth", default="research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl")
    ap.add_argument("--output", default="artifacts/gemma-a593-snowball-tournament.json")
    args = ap.parse_args()

    base.EXPECTED_TEACHER_ROWS = EXPECTED_TEACHER_ROWS
    base.EXPECTED_TEACHER_PHRASES = EXPECTED_TEACHER_PHRASES

    # Freeze the lexical representation change before the opened replay. BM25 documents,
    # query tokens and canonical surface-token checks use the same deterministic stemmer;
    # exact full-string canonical surfaces remain unchanged through norm().
    base.tokens = stemmed_tokens
    c1.tokens = stemmed_tokens

    tmp = Path(args.output).with_suffix(".a149-tmp.json")
    old_argv = sys.argv
    try:
        sys.argv = [
            "evaluate_gemma_a149.py",
            "--teacher", args.teacher,
            "--registry", args.registry,
            "--stress", args.stress,
            "--source-truth", args.source_truth,
            "--output", str(tmp),
        ]
        rc = base.main()
    finally:
        sys.argv = old_argv
    if rc != 0:
        return rc

    result = json.loads(tmp.read_text(encoding="utf-8"))
    tmp.unlink()

    candidate = result["candidate"]
    candidate["id"] = CANDIDATE_ID
    candidate["representation"] = (
        "full canonical YV BM25 + eight Gemma phrases for 593 concepts, with deterministic "
        "Swedish Snowball stemming for lexical tokens; teacher phrases are not exact surfaces"
    )
    candidate["selection_basis"] = (
        "frozen A593 corpus-internal 8-fold phrase-slot holdout only; opened 17/88 outcomes "
        "were not used to select or tune this candidate"
    )

    for section in (
        "strict_source_attested_17",
        "opened_stress_54",
        "canonical_source_truth_333",
    ):
        values = result[section]
        values["gemma_a593_snowball"] = values.pop("gemma_a149")

    result["status"] = "opened replay of prefrozen A593-Snowball architecture candidate; no runtime promotion"
    result["evidence_warning"] = (
        "The Snowball variant was selected using only corpus-internal teacher holdouts. "
        "The 17-case and 54-case suites are already-opened development evidence and may only "
        "replay/falsify the prefrozen candidate, not tune it or establish independent user accuracy."
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    compact = {
        "candidate": result["candidate"],
        "coverage": result["coverage"],
        "size": result["size"],
        "strict_source_attested_17": {
            key: {k: v for k, v in value.items() if k != "rows"}
            for key, value in result["strict_source_attested_17"].items()
        },
        "opened_stress_categories": {
            key: value["categories"] for key, value in result["opened_stress_54"].items()
        },
        "canonical_source_truth_333": result["canonical_source_truth_333"],
        "output": str(out),
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
