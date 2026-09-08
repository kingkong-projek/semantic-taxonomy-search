#!/usr/bin/env python3
"""Format-only adapter for the frozen A593 language-diversity generator.

The first run showed Gemma consistently returning the requested `items` array as the
JSON root instead of wrapping it in `{\"items\": ...}`. This adapter changes no prompt,
selection, temperature, evidence or validation rule; it only accepts both JSON shapes.
"""
from __future__ import annotations

import json
from typing import Any

import generate_a593_language_diversity_falsifier as g


def tolerant_extract_json(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("no candidates")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(
        str(p.get("text") or "")
        for p in parts
        if isinstance(p, dict) and not p.get("thought")
    ).strip()
    if not text:
        raise RuntimeError("no response text")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON response: {text[:500]!r}") from exc
    if isinstance(value, list):
        return {"items": value}
    if isinstance(value, dict):
        return value
    raise RuntimeError("response JSON must be object or array")


g.extract_json = tolerant_extract_json
raise SystemExit(g.main())
