#!/usr/bin/env python3
"""Post-result diagnostic: query-length sensitivity of the frozen lane rule.

The 80-word historical-ad proxy showed severe retention failure. This diagnostic reruns
the identical source/sampling/ranker/lane rule at fixed 20- and 40-word truncations.
Because these lengths were chosen after observing the 80-word result, they are NOT
promotion evidence and MUST NOT be used to retune the threshold.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import evaluate_p80_display_lane_historical_ads as experiment

_original_load = experiment.load_diverse_training
_original_make_query = experiment.make_query


def _load(path: Path):
    training, meta = _original_load(path)
    if isinstance(meta, dict):
        meta = [{"concept_id": cid} for cid in meta]
    return training, meta


experiment.load_diverse_training = _load

summaries = {}
for words in (20, 40):
    def _make_query(text: str, forbidden: list[str], max_words: int = 80, *, _words=words):
        return _original_make_query(text, forbidden, max_words=_words)

    experiment.make_query = _make_query
    output = f"research/evaluation/v31/p80-display-lane-historical-ads-{words}w-diagnostic-v0.json"
    sys.argv = [sys.argv[0], "--output", output]
    rc = experiment.main()
    if rc:
        raise SystemExit(rc)
    result = json.loads(Path(output).read_text(encoding="utf-8"))
    result["evidence_class"] = (
        "POST-RESULT query-length diagnostic on the same historical-ad source; "
        "NOT independent promotion evidence"
    )
    result["post_result_diagnostic"] = True
    result["query_construction"]["max_words"] = words
    result["interpretation_contract"]["must_not_retune_lane_rule_from_this"] = True
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summaries[str(words)] = result["metrics"]

print(json.dumps(summaries, ensure_ascii=False, indent=2, sort_keys=True))
