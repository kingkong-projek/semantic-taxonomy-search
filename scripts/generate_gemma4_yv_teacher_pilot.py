#!/usr/bin/env python3
"""Generate Gemma 4 teacher-language for bounded YV experiments.

Only public taxonomy evidence is sent. Opened evaluation/stress text is never teacher
input. Generated language is synthetic evidence, not canonical truth.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TAXONOMY_URL = (
    "https://data.jobtechdev.se/taxonomy/version/31/query/"
    "concepts-and-common-relations/concepts-and-common-relations.json"
)
MODEL = "gemma-4-26b-a4b-it"
PROMPT_REVISION = "yv-source-entailment-v2"
TOKEN_RE = re.compile(r"[0-9A-Za-zÅÄÖåäöÉéÜü]+", re.UNICODE)
BANNED_COLLOQUIAL_STEMS = (
    "gubbe",
    "gubbar",
    "tjej",
    "tjejer",
    "pamp",
    "kärring",
    "snubbe",
    "snubbar",
)


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


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def tokens(value: Any) -> list[str]:
    return [m.group(0).casefold() for m in TOKEN_RE.finditer(str(value or ""))]


def phrase_present(text: str, surface: str) -> bool:
    haystack = tokens(text)
    needle = tokens(surface)
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(haystack[i : i + width] == needle for i in range(len(haystack) - width + 1))


def evidence_for(concept: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_label": str(concept.get("preferred_label") or "").strip(),
        "definition": str(concept.get("definition") or "").strip(),
        "alternative_labels": clean_list(concept.get("alternative_labels")),
    }


def prompt_for(concept: dict[str, Any]) -> str:
    evidence = evidence_for(concept)
    example = [
        "kort svensk arbetsbeskrivning ett",
        "kort svensk arbetsbeskrivning två",
        "vardaglig svensk arbetsbeskrivning tre",
        "vardaglig svensk arbetsbeskrivning fyra",
        "indirekt men särskiljande beskrivning fem",
        "telegramstil med konkreta arbetsord",
        "konkret metod eller ansvar sju",
        "försiktig särskiljande gränsvariant åtta",
    ]
    return f"""Du skapar syntetiskt sökspråk för en svensk offentlig yrkestaxonomi.

Målkonceptet är ett EXISTERANDE yrke. Du får ENDAST uttrycka sådant som stöds av innebörden i evidensen nedan. Om evidensen är tunn ska du skriva försiktiga omskrivningar av den, inte fylla i med egen yrkeskunskap.

EVIDENS:
{json.dumps(evidence, ensure_ascii=False, sort_keys=True)}

Skriv exakt 8 korta svenska beskrivningar som en vanlig person skulle kunna skriva när hen beskriver sitt arbete men inte känner till taxonomins titel:
- 2 tydliga arbetsuppgiftsbeskrivningar
- 2 naturligt vardagliga beskrivningar
- 1 indirekt men rimligt särskiljande beskrivning
- 1 telegram/noisy stil med minst tre ord
- 1 verktyg/metod/ansvar ENDAST om det uttryckligen stöds av evidensen, annars ytterligare arbetsuppgift
- 1 försiktig gränsvariant som fortfarande stöds av evidensen

Varje rad ska innehålla minst ett konkret och särskiljande arbetsmoment, objekt, metod, miljö eller ansvar som faktiskt stöds av evidensen. Vardaglig betyder naturligt sätt att beskriva arbete — INTE smeknamn eller etiketter på personen.

Hårda regler:
- skriv INTE canonical_label, någon alternative_label eller en uppenbar böjningsform av dem
- använd INTE könade, stereotypa, nedsättande eller skämtsamma personetiketter som "-gubbe", "-tjej", "pamp" eller liknande
- hitta INTE på legitimationer, certifikat, verktyg, tekniker, arbetsmiljöer eller arbetsuppgifter som inte stöds av evidensen
- undvik generiska fraser som passar många yrken, till exempel bara "hjälper människor", "jobbar med kunder" eller "jobbar med datorer"
- varje sträng ska innehålla minst 3 token/ord
- de 8 strängarna ska vara sinsemellan olika i innehåll, inte bara små omskrivningar
- ingen persondata
- endast offentlig/syntetisk text
- returnera endast en JSON-array, ingen markdown, inget objekt och ingen förklaring
- arrayen ska innehålla exakt åtta strängar, som i detta formexempel:
{json.dumps(example, ensure_ascii=False)}
"""


def extract_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemma returned no candidates: {json.dumps(payload, ensure_ascii=False)[:1200]}")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(
        str(part.get("text") or "")
        for part in parts
        if isinstance(part, dict) and not part.get("thought")
    ).strip()
    if not text:
        raise RuntimeError(f"Gemma returned no non-thought text: {json.dumps(payload, ensure_ascii=False)[:1200]}")
    return text


def validate_phrases(text: str, *, forbidden_surfaces: list[str]) -> list[str]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemma JSON MIME response was not valid JSON: {text[:700]!r}") from exc
    if not isinstance(value, list) or len(value) != 8:
        raise RuntimeError(
            f"expected JSON array with 8 phrases, got {type(value).__name__}/"
            f"{len(value) if isinstance(value, list) else 'n/a'}: {str(value)[:500]}"
        )
    out = [str(x).strip() for x in value]
    if any(not x for x in out):
        raise RuntimeError("teacher returned blank phrase")
    normalized = [norm(x) for x in out]
    if len(set(normalized)) != len(normalized):
        raise RuntimeError("teacher returned duplicate phrases")
    too_short = [x for x in out if len(tokens(x)) < 3]
    if too_short:
        raise RuntimeError(f"teacher returned <3-token phrase: {too_short[:2]!r}")
    leaks = [
        phrase
        for phrase in out
        if any(surface and phrase_present(phrase, surface) for surface in forbidden_surfaces)
    ]
    if leaks:
        raise RuntimeError(f"teacher leaked canonical/alternative surface: {leaks[:2]!r}")
    stereotyped = [
        phrase
        for phrase in out
        if any(stem in token for token in tokens(phrase) for stem in BANNED_COLLOQUIAL_STEMS)
    ]
    if stereotyped:
        raise RuntimeError(f"teacher returned stereotyped colloquialism: {stereotyped[:2]!r}")
    return out


def retry_delay(attempt: int) -> float:
    return min(60.0, 2.0 ** attempt) + random.uniform(0.0, 1.0)


def call_gemma(
    api_key: str,
    prompt: str,
    *,
    forbidden_surfaces: list[str],
    max_attempts: int = 5,
) -> tuple[list[str], dict[str, Any]]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "thinkingConfig": {"thinkingLevel": "minimal"},
                "responseMimeType": "application/json",
                "temperature": 0.0,
                "maxOutputTokens": 1500,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")

    for attempt in range(max_attempts):
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.load(response)
            phrases = validate_phrases(
                extract_text(payload),
                forbidden_surfaces=forbidden_surfaces,
            )
            return phrases, payload.get("usageMetadata") or {}
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            detail = exc.read().decode("utf-8", errors="replace")[:1200]
            if status != 429 and not (500 <= status < 600):
                raise RuntimeError(f"Gemma API HTTP {status}: {detail}") from exc
            if attempt + 1 >= max_attempts:
                raise RuntimeError(f"Gemma API still failing after retries, HTTP {status}: {detail}") from exc
            delay = retry_delay(attempt)
            print(f"transient Gemma HTTP {status}; retrying in {delay:.1f}s", flush=True)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 >= max_attempts:
                raise RuntimeError(f"Gemma network error after retries: {exc}") from exc
            delay = retry_delay(attempt)
            print(f"transient Gemma network error; retrying in {delay:.1f}s: {exc}", flush=True)
            time.sleep(delay)
        except RuntimeError as exc:
            if attempt + 1 >= max_attempts:
                raise
            delay = retry_delay(attempt)
            print(f"invalid Gemma response; retrying in {delay:.1f}s: {exc}", flush=True)
            time.sleep(delay)
    raise AssertionError("unreachable")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--output", default="artifacts/gemma4-yv-teacher-pilot.jsonl")
    ap.add_argument("--start-rank", type=int, default=1, help="1-based occupation demand rank")
    ap.add_argument("--cases", type=int, default=8)
    ap.add_argument("--requests-per-minute", type=float, default=3.0)
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    if not (1 <= args.start_rank):
        raise RuntimeError("--start-rank must be >= 1")
    if not (1 <= args.cases <= 200):
        raise RuntimeError("--cases must be between 1 and 200")
    if not (0.2 <= args.requests_per_minute <= 6.0):
        raise RuntimeError("RPM must stay between 0.2 and 6.0")

    taxonomy = fetch_json(TAXONOMY_URL)
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    ranked = pareto.get("occupation_name", {}).get("ranked_p95") or []
    ranked_concepts: list[dict[str, Any]] = []
    for row in ranked:
        concept = by_id.get(str(row.get("concept_id") or ""))
        if concept and concept.get("type") == "occupation-name":
            ranked_concepts.append(concept)

    start = args.start_rank - 1
    selected = ranked_concepts[start : start + args.cases]
    if len(selected) != args.cases:
        raise RuntimeError(
            f"could only select {len(selected)} occupations from start rank {args.start_rank}; "
            f"ranked occupation count is {len(ranked_concepts)}"
        )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    interval = 60.0 / args.requests_per_minute
    rows: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for index, concept in enumerate(selected):
        if index:
            time.sleep(interval)
        label = str(concept.get("preferred_label") or "").strip()
        rank = args.start_rank + index
        print(f"Gemma teacher rank {rank} ({index + 1}/{len(selected)}): {label}", flush=True)
        evidence = evidence_for(concept)
        forbidden_surfaces = [
            evidence["canonical_label"],
            *[str(x) for x in evidence["alternative_labels"]],
        ]
        try:
            phrases, usage = call_gemma(
                api_key,
                prompt_for(concept),
                forbidden_surfaces=forbidden_surfaces,
            )
        except RuntimeError as exc:
            failed.append({"concept_id": str(concept["id"]), "label": label, "error": str(exc)})
            print(f"skipping {label} after retries: {exc}", flush=True)
            continue
        rows.append({
            "concept_id": str(concept["id"]),
            "label": label,
            "demand_rank": rank,
            "model": MODEL,
            "prompt_revision": PROMPT_REVISION,
            "phrases": phrases,
            "usage_metadata": usage,
            "provenance": "Gemma 4 generateContent JSON-MIME teacher; public taxonomy input only; exploratory build-time evidence",
        })
        out.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    print(json.dumps({
        "status": "exploratory teacher run only",
        "model": MODEL,
        "prompt_revision": PROMPT_REVISION,
        "api": "generateContent + thinkingLevel=minimal + responseMimeType=application/json",
        "start_rank": args.start_rank,
        "requested_cases": len(selected),
        "successful_cases": len(rows),
        "failed_cases": len(failed),
        "failures": failed,
        "requests_per_minute_cap": args.requests_per_minute,
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
