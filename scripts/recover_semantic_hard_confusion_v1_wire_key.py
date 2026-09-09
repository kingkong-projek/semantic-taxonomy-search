#!/usr/bin/env python3
"""Execution-only recovery for a persistently malformed opaque case key in hard-confusion v1.

The frozen semantic payload is built first with its original case key, preserving query,
candidate evidence, candidate membership, and deterministic candidate order. Only the
opaque response identifier is then shortened on the wire and mapped back after strict
candidate/verdict validation. No semantic evidence, prompt instruction, model, or gate is
changed.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

import evaluate_p80_display_semantic_oracle as oracle
import evaluate_semantic_display_hard_confusion_v1 as v1
import run_p80_display_semantic_oracle_resumable as durable


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY required")

    v1.load_prereg()
    pairs, atom_map = v1.load_atoms()
    by_id, _ids, _ssyk4, _ranker, _exact, _surfaces, _v0_phrases, _primary = oracle.load_system()
    cases = v1.fetch_cases(by_id, pairs, search_limit=25, accepted=5)

    original_version = oracle.EVIDENCE_VERSION
    original_max = oracle.MAX_TASK_PHRASES
    original_evidence = oracle.candidate_evidence
    try:
        oracle.EVIDENCE_VERSION = v1.CHALLENGER_EVIDENCE
        oracle.MAX_TASK_PHRASES = 6

        def rich_evidence(concept, phrases):
            base = original_evidence(concept, [])
            base["task_evidence"] = [oracle.clip_words(x, 24) for x in list(phrases)[:6]]
            return base

        oracle.candidate_evidence = rich_evidence
        state = durable.load_state(v1.CHALLENGER_CP, cases)
        missing = [case for case in cases if oracle.case_key(case) not in state["judgments"]]
        if not missing:
            print("challenger already complete; no wire-key recovery needed")
            return 0
        if len(missing) != 1:
            raise RuntimeError(f"wire-key recovery is intentionally single-case only; missing={len(missing)}")

        case = missing[0]
        key = oracle.case_key(case)
        prompt_text = oracle.prompt([case], by_id, atom_map)
        shadow = dict(case)
        shadow["ad_id"] = "wire-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        short_key = oracle.case_key(shadow)
        old_wire = json.dumps(key, ensure_ascii=False)
        new_wire = json.dumps(short_key, ensure_ascii=False)
        if prompt_text.count(old_wire) != 1:
            raise RuntimeError("could not isolate original case key in frozen prompt payload")
        wire_prompt = prompt_text.replace(old_wire, new_wire, 1)

        last_error = "no attempt"
        for attempt in range(1, 4):
            raw, meta = oracle.call_semantic_with_quota_retry(api_key, wire_prompt)
            partial = oracle.parse_response(raw, [shadow], require_all=False)
            state["usage_metadata"].append(meta)
            if short_key in partial:
                state["judgments"][key] = partial[short_key]
                state["transport_failures"].pop(key, None)
                durable.write_checkpoint(
                    v1.CHALLENGER_CP,
                    v1.CHALLENGER_STATUS,
                    state,
                    cases,
                    phase="challenger-complete-after-short-wire-key-recovery",
                )
                print(f"recovered one opaque case key on attempt {attempt}; challenger={len(state['judgments'])}/{len(cases)}")
                return 0
            last_error = "short-wire-key response omitted case"
            time.sleep(5)
        raise RuntimeError(last_error)
    finally:
        oracle.EVIDENCE_VERSION = original_version
        oracle.MAX_TASK_PHRASES = original_max
        oracle.candidate_evidence = original_evidence


if __name__ == "__main__":
    raise SystemExit(main())
