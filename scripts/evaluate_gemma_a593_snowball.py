#!/usr/bin/env python3
"""Replay the frozen A593 evaluator with Swedish Snowball lexical stemming.

Candidate choice is based only on the frozen A593 corpus-internal 8-fold phrase-slot
holdout diagnostic. This script is committed before any opened 17/88 replay.

Important boundary: the existing raw baseline and canonical/surface logic remain
unchanged. Only the lexical BM25 token representation for the A593 candidate is
stemmed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import evaluate_gemma_a149 as base
import evaluate_pareto_c1 as c1
from evaluate_gemma_a593_phrase_representation import raw_tokens, stemmed_tokens

EXPECTED_TEACHER_ROWS = 593
EXPECTED_TEACHER_PHRASES = EXPECTED_TEACHER_ROWS * 8
CANDIDATE_ID = "YV-A593-Gemma4-26B-sequence-expansion-snowball-v0"


def build_ranker(
    by_id: dict[str, dict[str, Any]],
    ids: list[str],
    teacher: dict[str, list[str]] | None = None,
):
    teacher = teacher or {}
    # Baseline stays byte-for-byte equivalent to the frozen raw-token evaluator.
    tokenizer = stemmed_tokens if teacher else raw_tokens
    docs: dict[str, list[str]] = {}
    exact: dict[str, set[str]] = {}
    surface_tokens: dict[str, set[str]] = {}
    for cid in ids:
        concept = by_id[cid]
        label = str(concept.get("preferred_label") or "").strip()
        definition = str(concept.get("definition") or "").strip()
        real_definition = definition if definition and base.norm(definition) != base.norm(label) else ""
        alternatives = [x for x in base.as_list(concept.get("alternative_labels")) if base.norm(x) != base.norm(label)]
        canonical_surfaces = [label, *alternatives]
        extra = teacher.get(cid, [])
        docs[cid] = tokenizer(" ".join([label, real_definition, *alternatives, *extra]))
        exact[cid] = {base.norm(x) for x in canonical_surfaces if base.norm(x)}
        # Surface evidence deliberately stays raw so the only tested intervention is
        # lexical BM25 stemming in the description representation.
        surface_tokens[cid] = {t for x in canonical_surfaces for t in raw_tokens(x)}
    ranker = base.BM25(docs, exact)
    ranker.query_tokenizer = tokenizer
    return ranker, exact, surface_tokens


def rank_ids(
    ranker: base.BM25,
    exact: dict[str, set[str]],
    surface_tokens: dict[str, set[str]],
    query: str,
) -> list[str]:
    tokenizer = getattr(ranker, "query_tokenizer", raw_tokens)
    qtokens = tokenizer(query)
    short_query = len(raw_tokens(query)) <= 3
    boosts = {4: 1_000_000.0, 3: 10_000.0, 2: 5_000.0, 1: 2_500.0, 0: 0.0}
    nq = base.norm(query)
    scored: list[tuple[str, float]] = []
    for cid in ranker.documents:
        lexical = ranker.score(qtokens, cid)
        if short_query:
            signal, _ = c1.surface_signal(query, exact[cid], surface_tokens[cid])
            if signal == 0:
                continue
            score = lexical + boosts[signal]
        else:
            exact_surface = bool(nq and nq in exact[cid])
            score = lexical + (1_000_000.0 if exact_surface else 0.0)
            if score <= 0.0:
                continue
        scored.append((cid, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [cid for cid, _ in scored]


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
    base.build_ranker = build_ranker
    base.rank_ids = rank_ids

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
        "full canonical YV BM25 + eight Gemma phrases for 593 concepts; only candidate lexical "
        "BM25 tokens use deterministic Swedish Snowball stemming; canonical exact/surface logic stays raw"
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
