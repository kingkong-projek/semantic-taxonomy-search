#!/usr/bin/env python3
"""Bounded qualitative capability probe for explicit Gemma hard-negative reasoning.

Selects four high-frequency A593 confusion pairs from the frozen corpus-internal hard-
negative inventory, excluding relation-aware protected near-indistinguishable pairs.
The model sees only public canonical taxonomy evidence for the pair. No A593 teacher
phrases and no opened 17/88 queries are sent.

This probe answers a narrow question: can the cheap Gemma teacher itself identify
shared non-discriminating language, decisive A-vs-B cues, adversarial hard negatives,
and genuinely ambiguous text when explicitly asked to reason contrastively?
"""
from __future__ import annotations

import argparse
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
import generate_gemma4_yv_sniper_contrasts as sniper

MODEL = pilot.MODEL


def prompt_for(a: dict[str, Any], b: dict[str, Any]) -> str:
    evidence = {"A": sniper.evidence(a), "B": sniper.evidence(b)}
    shape = {
        "distinguishable_from_free_text": True,
        "why_confusable": "kort förklaring",
        "shared_not_negative": ["gemensam signal 1", "gemensam signal 2", "gemensam signal 3", "gemensam signal 4"],
        "a_decisive_cues": ["A-signal 1", "A-signal 2", "A-signal 3", "A-signal 4", "A-signal 5"],
        "b_decisive_cues": ["B-signal 1", "B-signal 2", "B-signal 3", "B-signal 4", "B-signal 5"],
        "hard_negatives_for_a": ["A-beskrivning som lätt kan misstas för B 1", "A-beskrivning som lätt kan misstas för B 2", "A-beskrivning som lätt kan misstas för B 3", "A-beskrivning som lätt kan misstas för B 4"],
        "hard_negatives_for_b": ["B-beskrivning som lätt kan misstas för A 1", "B-beskrivning som lätt kan misstas för A 2", "B-beskrivning som lätt kan misstas för A 3", "B-beskrivning som lätt kan misstas för A 4"],
        "ambiguous_do_not_force": ["formulering där A/B inte går att avgöra 1", "formulering där A/B inte går att avgöra 2", "formulering där A/B inte går att avgöra 3"],
        "anti_overfit_rules": ["kort regel 1", "kort regel 2", "kort regel 3"],
    }
    return f"""Du är en mycket noggrann forskare som bygger hard-negative-träningsdata för semantisk yrkessökning.

Två EXISTERANDE yrkesidentiteter A och B förväxlas ofta av en lexical/sparse sökmotor. Din uppgift är INTE att beskriva yrkena generellt, utan att analysera exakt vilka språkliga signaler som får och inte får användas för att skilja dem.

OFFENTLIG TAXONOMIEVIDENS:
{json.dumps(evidence, ensure_ascii=False, sort_keys=True)}

Tänk enligt följande principer:
1. Gemensamma arbetsord, miljöer eller verb som rimligen gäller båda är INTE negativa signaler. Skriv dem i shared_not_negative.
2. En decisive cue måste faktiskt stödjas av evidensen och innebära något som skiljer A från B. Hitta inte på skillnader.
3. Ett hard negative för A är en NATURLIG användarbeskrivning som verkligen avser A men innehåller mycket språk som skulle kunna lura en sökmotor mot B. Den måste samtidigt innehålla minst en legitim A-specifik signal.
4. Motsvarande för B.
5. Om en formulering saknar särskiljande information ska korrekt beteende vara 'kan inte avgöra A/B', inte att tvinga fram en etikett. Skriv sådana fall i ambiguous_do_not_force.
6. Om den offentliga evidensen inte räcker för robust fri-text-diskrimination: sätt distinguishable_from_free_text=false. Då ska decisive-cues och hard-negatives vara tomma; fyll fortfarande shared_not_negative och ambiguous_do_not_force.
7. anti_overfit_rules ska uttrycka tre konkreta saker en studentmodell INTE bör lära sig från just detta par.
8. Använd inte kanoniska yrkestitlar i hard-negative- eller ambiguous-beskrivningarna.
9. Endast offentlig/syntetisk text, ingen persondata.

Returnera endast JSON med exakt dessa nycklar och antal element enligt formen:
{json.dumps(shape, ensure_ascii=False, sort_keys=True)}
"""


def validate(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("expected object")
    keys = {
        "distinguishable_from_free_text", "why_confusable", "shared_not_negative",
        "a_decisive_cues", "b_decisive_cues", "hard_negatives_for_a",
        "hard_negatives_for_b", "ambiguous_do_not_force", "anti_overfit_rules",
    }
    if set(value) != keys:
        raise RuntimeError(f"unexpected keys: {sorted(value)}")
    distinguishable = bool(value["distinguishable_from_free_text"])
    if not isinstance(value["why_confusable"], str) or not value["why_confusable"].strip():
        raise RuntimeError("invalid why_confusable")
    expected = {
        "shared_not_negative": 4,
        "ambiguous_do_not_force": 3,
        "anti_overfit_rules": 3,
        "a_decisive_cues": 5 if distinguishable else 0,
        "b_decisive_cues": 5 if distinguishable else 0,
        "hard_negatives_for_a": 4 if distinguishable else 0,
        "hard_negatives_for_b": 4 if distinguishable else 0,
    }
    out = {"distinguishable_from_free_text": distinguishable, "why_confusable": value["why_confusable"].strip()}
    for key, count in expected.items():
        items = value[key]
        if not isinstance(items, list) or len(items) != count or any(not isinstance(x, str) or not x.strip() for x in items):
            raise RuntimeError(f"expected {count} non-empty strings for {key}")
        out[key] = [x.strip() for x in items]
    return out


def call(api_key: str, prompt: str, attempts: int = 5):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "thinkingConfig": {"thinkingLevel": "minimal"},
            "responseMimeType": "application/json",
            "temperature": 0.0,
            "maxOutputTokens": 2400,
        },
    }, ensure_ascii=False).encode("utf-8")
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                payload = json.load(response)
            return validate(json.loads(pilot.extract_text(payload))), payload.get("usageMetadata") or {}
        except (json.JSONDecodeError, RuntimeError) as exc:
            if attempt + 1 >= attempts:
                raise RuntimeError(f"invalid response after retries: {exc}") from exc
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            detail = exc.read().decode("utf-8", errors="replace")[:900]
            if status != 429 and not (500 <= status < 600):
                raise RuntimeError(f"HTTP {status}: {detail}") from exc
            if attempt + 1 >= attempts:
                raise RuntimeError(f"HTTP {status} after retries: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 >= attempts:
                raise RuntimeError(f"network error after retries: {exc}") from exc
        time.sleep(min(60.0, 2.0 ** attempt) + random.uniform(0.0, 1.0))
    raise AssertionError("unreachable")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hard-negatives", default="research/evaluation/v31/compile-time-semantic-a593-hard-negative-distillation.json")
    ap.add_argument("--relation-aware", default="research/evaluation/v31/compile-time-semantic-a593-relation-aware-negatives.json")
    ap.add_argument("--pairs", type=int, default=4)
    ap.add_argument("--requests-per-minute", type=float, default=3.0)
    ap.add_argument("--output", default="research/evaluation/v31/gemma4-explicit-hard-negative-capability-v0.json")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing")
    hard = json.loads(Path(args.hard_negatives).read_text(encoding="utf-8"))
    relation = json.loads(Path(args.relation_aware).read_text(encoding="utf-8"))
    pairs = sniper.select_pairs(hard, relation, args.pairs)

    taxonomy = pilot.fetch_json(pilot.TAXONOMY_URL)
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    rows = []
    failures = []
    interval = 60.0 / args.requests_per_minute
    for index, pair in enumerate(pairs):
        if index:
            time.sleep(interval)
        a_id, b_id = pair["ids"]
        a, b = by_id[a_id], by_id[b_id]
        print(f"capability {index+1}/{len(pairs)}: {a.get('preferred_label')} <> {b.get('preferred_label')}", flush=True)
        try:
            analysis, usage = call(api_key, prompt_for(a, b))
        except RuntimeError as exc:
            failures.append({"a_concept_id": a_id, "b_concept_id": b_id, "error": str(exc)})
            continue
        rows.append({
            "a_concept_id": a_id,
            "a_label": str(a.get("preferred_label") or ""),
            "a_evidence": sniper.evidence(a),
            "b_concept_id": b_id,
            "b_label": str(b.get("preferred_label") or ""),
            "b_evidence": sniper.evidence(b),
            "confusion_count_sum": pair["directed_count_sum"],
            "analysis": analysis,
            "usage_metadata": usage,
        })

    result = {
        "schema_version": 1,
        "status": "qualitative capability probe; not accuracy evidence and not training data unless separately promoted",
        "model": MODEL,
        "thinking_level": "minimal",
        "pairs_requested": len(pairs),
        "pairs_successful": len(rows),
        "failures": failures,
        "selection": "top non-protected A593 corpus-internal hard-negative pairs",
        "input_guard": "public canonical label/definition/alternative labels only; no A593 teacher phrases; no opened 17/88 queries",
        "pairs": rows,
    }
    raw = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    result["content_sha256_without_self_hash"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"pairs_successful": len(rows), "failures": failures, "labels": [[r["a_label"], r["b_label"]] for r in rows]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
