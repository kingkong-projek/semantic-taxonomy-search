#!/usr/bin/env python3
"""Execution-only transport adapter for semantic-display contrast v2.

Gemini JSON mode sometimes serializes a requested single JSON object as a one-item
array. V2's research prompt, evidence, model and gates are unchanged; this adapter
normalizes only that wire shape before the frozen parser sees the response.
"""
from __future__ import annotations

import json
from typing import Any

import generate_a593_language_diversity_falsifier as gemma
import generate_semantic_display_contrast_v2 as v2


def extract_object_or_singleton(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("no candidates")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(
        str(part.get("text") or "")
        for part in parts
        if isinstance(part, dict) and not part.get("thought")
    ).strip()
    if not text:
        raise RuntimeError("no response text")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON response: {text[:500]!r}") from exc

    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        value = value[0]
    if not isinstance(value, dict):
        raise RuntimeError(
            "response JSON must be object or singleton-object list; "
            f"got {type(value).__name__}: {text[:240]!r}"
        )
    return value


def _payload(text: str) -> dict[str, Any]:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def self_test() -> None:
    assert extract_object_or_singleton(_payload('{"x":1}')) == {"x": 1}
    assert extract_object_or_singleton(_payload('[{"x":1}]')) == {"x": 1}
    for bad in ("[]", '[{"x":1},{"x":2}]', "[1]", '"x"'):
        try:
            extract_object_or_singleton(_payload(bad))
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"accepted malformed transport: {bad}")


def main() -> int:
    self_test()
    gemma.extract_json = extract_object_or_singleton
    return v2.main()


if __name__ == "__main__":
    raise SystemExit(main())
