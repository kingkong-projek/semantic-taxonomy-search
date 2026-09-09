#!/usr/bin/env python3
"""Syntax-only adapter for the frozen A593 language-diversity evaluator.

The preregistered evaluator uses JSON's `false` token in three Python metadata fields.
Expose that name as False without changing any scoring, data, thresholds or experiment
logic, then execute the frozen evaluator unchanged.
"""
from __future__ import annotations

import builtins
import runpy

builtins.false = False
runpy.run_path("scripts/evaluate_a593_language_diversity_falsifier.py", run_name="__main__")
