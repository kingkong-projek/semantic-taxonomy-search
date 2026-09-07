#!/usr/bin/env python3
"""Generate a tiny Gemma 4 teacher-language pilot for YV.

This is deliberately a small API plumbing/quality probe, not a promoted corpus build.
Only public taxonomy evidence is sent. The opened semantic stress suite is never used
as teacher input. Requests are sequential and conservatively throttled.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TAXONOMY_URL = (
    "https://data.jobtechdev.se/taxonomy/version/31/query/"
    "concepts-and-common-relations/concepts-and-common-relations.json"
)
INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL = "gemma-4-26b-a4b-it"


def fetch_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            for key in ("label", "name", "value"):
                text = item.get(key)
                if isinstance(text, str) and text.strip():
                    out.append(text.strip())
                    break
    return out


def prompt_for(concept: dict[str, Any]) -> str:
    label = str(concept.get("preferred_label") or "").strip()
    definition = str(concept.get("definition") or "").strip()
    alternatives = clean_list(concept.get("alternative_labels"))
    evidence = {
        "canonical_label": label,
        "definition": definition,
        "alternative_labels": alternatives,
    }
    return f"""Du skapar träningsspråk för en svensk offentlig yrkestaxonomi.

Målkonceptet är ett EXISTERANDE yrke. Använd endast innebörden i evidensen nedan. Hitta inte på nya arbetsuppgifter som inte rimligen hör till yrket.

EVIDENS:
{json.dumps(evidence, ensure_ascii=False, sort_keys=True)}

Skriv exakt 8 korta svenska förstapersonsbeskrivningar som en vanlig person skulle kunna skriva när hen inte känner till taxonomins yrkestitel. Variera språket:
- 2 tydliga arbetsuppgiftsbeskrivningar
- 2 vardagliga/kolloquiala
- 1 indirekt men fortfarande rimligt särskiljande
- 1 telegram/noisy stil
- 1 verktyg/metod/ansvar om evidensen faktiskt stödjer det; annars ytterligare arbetsuppgiftsbeskrivning
- 1 försiktig gränsvariant som fortfarande bör kunna leda till detta yrke men inte kopierar titeln

Regler:
- skriv INTE den kanoniska yrkestiteln eller dess uppenbara böjningsform
- undvik generiska fraser som skulle passa hundratals yrken
- ingen persondata
- endast offentlig/syntetisk text
"""


def extract_interaction_text(payload: dict[str, Any]) -> str:
    for step in reversed(payload.get("steps") or []):
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        texts = [
            str(part.get("text") or "")
            for part in (step.get("content") or [])
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        text = "".join(texts).strip()
        if text:
            return text
    raise RuntimeError(f"Gemma interaction has no model text output: {json.dumps(payload, ensure_ascii=False)[:1200]}")


def validate_phrases(text: str) -> list[str]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"structured output was not valid JSON: {text[:500]!r}") from exc
    if not isinstance(value, list) or len(value) != 8:
        raise RuntimeError(
            f"structured output violated 8-string contract: {type(value).__name__}/"
            f"{len(value) if isinstance(value, list) else 'n/a'}"
        )
    phrases = [str(x).strip() for x in value]
    if any(not x for x in phrases):
        raise RuntimeError("structured output contained a blank phrase")
    return phrases


def call_gemma(api_key: str, prompt: str, *, max_attempts: int = 5) -> tuple[list[str], dict[str, Any]]:
    body = json.dumps(
        {
            "model": MODEL,
            "input": prompt,
            "response_format": [
                {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "description": "En kort svensk förstapersonsbeskrivning av arbetet utan yrkestiteln.",
                        },
                        "minItems": 8,
                        "maxItems": 8,
                    },
                }
            ],
            "generation_config": {
                "max_output_tokens": 1000,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")

    for attempt in range(max_attempts):
        request = urllib.request.Request(
            INTERACTIONS_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.load(response)
            if payload.get("status") == "failed":
                raise RuntimeError(f"Gemma interaction failed: {json.dumps(payload.get('errors') or [], ensure_ascii=False)[:1200]}")
            return validate_phrases(extract_interaction_text(payload)), payload.get("usage") or {}
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            detail = exc.read().decode("utf-8", errors="replace")[:1200]
            if status != 429 and not (500 <= status < 600):
                raise RuntimeError(f"Gemma API HTTP {status}: {detail}") from exc
            if attempt + 1 >= max_attempts:
                raise RuntimeError(f"Gemma API still failing after retries, HTTP {status}: {detail}") from exc
            delay = min(60.0, 2.0 ** attempt) + random.uniform(0.0, 1.0)
            print(f"transient Gemma HTTP {status}; retrying in {delay:.1f}s", flush=True)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 >= max_attempts:
                raise
            delay = min(60.0, 2.0 ** attempt) + random.uniform(0.0, 1.0)
            print(f"transient Gemma network error; retrying in {delay:.1f}s: {exc}", flush=True)
            time.sleep(delay)
    raise AssertionError("unreachable")


def usage_tokens(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, int):
            return value
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--output", default="artifacts/gemma4-yv-teacher-pilot.jsonl")
    ap.add_argument("--cases", type=int, default=8)
    ap.add_argument("--requests-per-minute", type=float, default=3.0)
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    if not (1 <= args.cases <= 20):
        raise RuntimeError("pilot --cases must be between 1 and 20")
    if not (0.2 <= args.requests_per_minute <= 6.0):
        raise RuntimeError("pilot RPM must stay between 0.2 and 6.0")

    taxonomy = fetch_json(TAXONOMY_URL)
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    ranked = pareto.get("occupation_name", {}).get("ranked_p95") or []
    selected: list[dict[str, Any]] = []
    for row in ranked:
        cid = str(row.get("concept_id") or "")
        concept = by_id.get(cid)
        if concept and concept.get("type") == "occupation-name":
            selected.append(concept)
        if len(selected) == args.cases:
            break
    if len(selected) != args.cases:
        raise RuntimeError(f"could only select {len(selected)} pilot occupations")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    interval = 60.0 / args.requests_per_minute
    rows: list[dict[str, Any]] = []
    for index, concept in enumerate(selected):
        if index:
            time.sleep(interval)
        label = str(concept.get("preferred_label") or "").strip()
        print(f"Gemma pilot {index + 1}/{len(selected)}: {label}", flush=True)
        phrases, usage = call_gemma(api_key, prompt_for(concept))
        rows.append(
            {
                "concept_id": str(concept["id"]),
                "label": label,
                "model": MODEL,
                "phrases": phrases,
                "usage": usage,
                "provenance": "Gemma 4 structured-output teacher; public taxonomy input only; exploratory pilot",
            }
        )
        out.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    total_input = sum(usage_tokens(r["usage"], "input_tokens", "prompt_tokens", "promptTokenCount") for r in rows)
    total_output = sum(usage_tokens(r["usage"], "output_tokens", "completion_tokens", "candidatesTokenCount") for r in rows)
    print(json.dumps({
        "status": "exploratory teacher pilot only",
        "model": MODEL,
        "api": "Interactions API with JSON Schema structured output",
        "cases": len(rows),
        "requests_per_minute_cap": args.requests_per_minute,
        "input_tokens_reported": total_input,
        "output_tokens_reported": total_output,
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
