#!/usr/bin/env python3
"""Generate bounded pair-specific contrast training data for A593 confusions.

Pair selection is derived only from the already-frozen A593 corpus-internal hard-negative
inventory. Pairs that the frozen relation-aware diagnostic marks as near-indistinguishable
are excluded. The Gemma prompt receives only public canonical taxonomy evidence for the
two concepts (label, definition, alternative labels) -- never opened 17/88 queries and
never the frozen eight teacher phrases.

This is TRAINING data, not evaluation data.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import generate_gemma4_yv_teacher_pilot as pilot

MODEL = pilot.MODEL


def evidence(concept: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_label": str(concept.get("preferred_label") or "").strip(),
        "definition": str(concept.get("definition") or "").strip(),
        "alternative_labels": pilot.clean_list(concept.get("alternative_labels")),
    }


def prompt_for(a: dict[str, Any], b: dict[str, Any]) -> str:
    payload = {"A": evidence(a), "B": evidence(b)}
    example = {
        "distinguishable": True,
        "a_cues": ["särskiljande signal A1", "särskiljande signal A2", "särskiljande signal A3", "särskiljande signal A4", "särskiljande signal A5", "särskiljande signal A6"],
        "b_cues": ["särskiljande signal B1", "särskiljande signal B2", "särskiljande signal B3", "särskiljande signal B4", "särskiljande signal B5", "särskiljande signal B6"],
        "a_descriptions": ["kort naturlig A-beskrivning 1", "kort naturlig A-beskrivning 2", "kort naturlig A-beskrivning 3"],
        "b_descriptions": ["kort naturlig B-beskrivning 1", "kort naturlig B-beskrivning 2", "kort naturlig B-beskrivning 3"],
        "shared_ambiguous": ["beskrivning som rimligen passar båda 1", "beskrivning som rimligen passar båda 2"],
    }
    return f"""Du skapar PRICKSKYTTE-KONTRASTDATA för två existerande yrken i en svensk offentlig taxonomi.

Målet är INTE att beskriva yrkena generellt. Målet är att skriva ned den minsta språkliga evidens som faktiskt hjälper en sökmotor att skilja A från B när användaren beskriver arbetsuppgifter, ansvar, verktyg, miljö eller arbetssätt.

Använd ENDAST innebörden i den offentliga evidensen nedan. Hitta inte på certifikat, ansvar, arbetsuppgifter eller organisationsnivå som evidensen inte stödjer.

EVIDENS:
{json.dumps(payload, ensure_ascii=False, sort_keys=True)}

Regler:
- Om evidensen inte räcker för att på ett robust sätt skilja yrkena i fri text: sätt distinguishable=false och lämna a_cues, b_cues, a_descriptions och b_descriptions tomma. shared_ambiguous får fortfarande innehålla två rimliga gemensamma beskrivningar.
- Om de går att skilja: ge exakt 6 korta A-signaler och 6 korta B-signaler. Signaler får vara ett ord eller en kort fras och ska vara diskriminerande, inte generiska ord som 'jobbar', 'hjälper', 'kollar'.
- Ge exakt 3 naturliga svenska användarbeskrivningar som innehåller A-specifik evidens och 3 som innehåller B-specifik evidens.
- Ge exakt 2 gemensamma/ambigua beskrivningar där det vore FEL att tvinga fram skillnaden A vs B.
- Skriv inte den kanoniska yrkestiteln eller en uppenbar böjning av den i descriptions.
- Cues får använda sakord från titeln endast om de beskriver en verklig särskiljande saklig signal.
- Ingen persondata. Endast offentlig/syntetisk text.
- Returnera endast ett JSON-objekt med exakt dessa nycklar:
{json.dumps(example, ensure_ascii=False, sort_keys=True)}
"""


def validate(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("expected JSON object")
    keys = {"distinguishable", "a_cues", "b_cues", "a_descriptions", "b_descriptions", "shared_ambiguous"}
    if set(value) != keys:
        raise RuntimeError(f"unexpected keys: {sorted(value)}")
    distinguishable = bool(value["distinguishable"])
    out: dict[str, Any] = {"distinguishable": distinguishable}
    for key in ("a_cues", "b_cues", "a_descriptions", "b_descriptions", "shared_ambiguous"):
        current = value[key]
        if not isinstance(current, list) or any(not isinstance(x, str) or not x.strip() for x in current):
            raise RuntimeError(f"invalid {key}")
        out[key] = [x.strip() for x in current]
    if distinguishable:
        expected = {"a_cues": 6, "b_cues": 6, "a_descriptions": 3, "b_descriptions": 3, "shared_ambiguous": 2}
    else:
        expected = {"a_cues": 0, "b_cues": 0, "a_descriptions": 0, "b_descriptions": 0, "shared_ambiguous": 2}
    for key, count in expected.items():
        if len(out[key]) != count:
            raise RuntimeError(f"expected {count} values for {key}, got {len(out[key])}")
    return out


def call_json(api_key: str, prompt: str, max_attempts: int = 5) -> tuple[dict[str, Any], dict[str, Any]]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "responseMimeType": "application/json",
            "temperature": 0.0,
            "maxOutputTokens": 1800,
        },
    }, ensure_ascii=False).encode("utf-8")
    for attempt in range(max_attempts):
        request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.load(response)
            text = pilot.extract_text(payload)
            return validate(json.loads(text)), payload.get("usageMetadata") or {}
        except (json.JSONDecodeError, RuntimeError) as exc:
            if attempt + 1 >= max_attempts:
                raise RuntimeError(f"invalid Gemma contrast response after retries: {exc}") from exc
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            detail = exc.read().decode("utf-8", errors="replace")[:900]
            if status != 429 and not (500 <= status < 600):
                raise RuntimeError(f"Gemma API HTTP {status}: {detail}") from exc
            if attempt + 1 >= max_attempts:
                raise RuntimeError(f"Gemma API HTTP {status} after retries: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 >= max_attempts:
                raise RuntimeError(f"Gemma network error after retries: {exc}") from exc
        delay = min(60.0, 2.0 ** attempt) + random.uniform(0.0, 1.0)
        time.sleep(delay)
    raise AssertionError("unreachable")


def select_pairs(hard: dict[str, Any], relation: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    protected = {
        frozenset((row["left_concept_id"], row["right_concept_id"]))
        for row in relation.get("full_corpus_protected_examples", [])
    }
    aggregate: dict[frozenset[str], dict[str, Any]] = {}
    for row in hard.get("top_directed_hard_negative_pairs", []):
        a, b = str(row["target_concept_id"]), str(row["wrong_concept_id"])
        key = frozenset((a, b))
        if len(key) != 2 or key in protected:
            continue
        current = aggregate.setdefault(key, {"ids": tuple(sorted(key)), "directed_count_sum": 0, "directed_count_max": 0})
        count = int(row["count"])
        current["directed_count_sum"] += count
        current["directed_count_max"] = max(current["directed_count_max"], count)
    ordered = sorted(aggregate.values(), key=lambda x: (-x["directed_count_sum"], -x["directed_count_max"], x["ids"]))
    if len(ordered) < limit:
        raise RuntimeError(f"only {len(ordered)} non-protected hard pairs available")
    return ordered[:limit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hard-negatives", default="research/evaluation/v31/compile-time-semantic-a593-hard-negative-distillation.json")
    ap.add_argument("--relation-aware", default="research/evaluation/v31/compile-time-semantic-a593-relation-aware-negatives.json")
    ap.add_argument("--pairs", type=int, default=16)
    ap.add_argument("--requests-per-minute", type=float, default=3.0)
    ap.add_argument("--output", default="research/training/v31/a593-gemma4-sniper-contrasts-v0.jsonl")
    ap.add_argument("--summary", default="research/training/v31/a593-gemma4-sniper-contrasts-v0-summary.json")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    if not (1 <= args.pairs <= 40):
        raise RuntimeError("--pairs must be 1..40")

    hard = json.loads(Path(args.hard_negatives).read_text(encoding="utf-8"))
    relation = json.loads(Path(args.relation_aware).read_text(encoding="utf-8"))
    selected = select_pairs(hard, relation, args.pairs)

    taxonomy = pilot.fetch_json(pilot.TAXONOMY_URL)
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    rows = []
    failures = []
    interval = 60.0 / args.requests_per_minute
    for index, pair in enumerate(selected):
        if index:
            time.sleep(interval)
        a_id, b_id = pair["ids"]
        a, b = by_id.get(a_id), by_id.get(b_id)
        if not a or not b:
            raise RuntimeError(f"taxonomy concept missing for {a_id}/{b_id}")
        print(f"sniper {index+1}/{len(selected)}: {a.get('preferred_label')} <> {b.get('preferred_label')}", flush=True)
        try:
            contrast, usage = call_json(api_key, prompt_for(a, b))
        except RuntimeError as exc:
            failures.append({"a_concept_id": a_id, "b_concept_id": b_id, "error": str(exc)})
            continue
        rows.append({
            "a_concept_id": a_id,
            "a_label": str(a.get("preferred_label") or ""),
            "b_concept_id": b_id,
            "b_label": str(b.get("preferred_label") or ""),
            "hard_negative_directed_count_sum": pair["directed_count_sum"],
            "hard_negative_directed_count_max": pair["directed_count_max"],
            "model": MODEL,
            "contrast": contrast,
            "usage_metadata": usage,
            "provenance": "pair selected from frozen A593 corpus-internal confusion inventory; Gemma prompt uses public canonical taxonomy evidence only; no A593 teacher phrases or opened 17/88 queries provided",
        })
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    out = Path(args.output)
    raw = out.read_bytes() if out.exists() else b""
    summary = {
        "status": "frozen synthetic training data; not evaluation evidence",
        "model": MODEL,
        "requested_pairs": len(selected),
        "successful_pairs": len(rows),
        "distinguishable_pairs": sum(bool(r["contrast"]["distinguishable"]) for r in rows),
        "indistinguishable_pairs": sum(not bool(r["contrast"]["distinguishable"]) for r in rows),
        "failed_pairs": len(failures),
        "failures": failures,
        "selection": "top unique unordered directed hard-negative pairs after excluding relation-aware protected pairs; no opened query used",
        "teacher_input": "public canonical label + definition + alternative labels for each pair only",
        "output_sha256": hashlib.sha256(raw).hexdigest(),
    }
    Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
