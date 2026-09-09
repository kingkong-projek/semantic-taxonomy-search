#!/usr/bin/env python3
"""Syntax-only adapter for the frozen historical-ad lane validation.

`load_diverse_training` returns metadata keyed by concept id. The v0 driver expected
row-shaped metadata only when deriving the 22 rescue ids. Normalize that shape here;
no corpus, ranking, lane formula, threshold, sampling policy or metric changes.
"""
from pathlib import Path

import evaluate_p80_display_lane_historical_ads as experiment

_original = experiment.load_diverse_training


def _load(path: Path):
    training, meta = _original(path)
    if isinstance(meta, dict):
        meta = [{"concept_id": cid} for cid in meta]
    return training, meta


experiment.load_diverse_training = _load
raise SystemExit(experiment.main())
