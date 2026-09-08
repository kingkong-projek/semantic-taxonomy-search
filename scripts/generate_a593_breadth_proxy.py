#!/usr/bin/env python3
"""Generate a small prefrozen source-bound cross-style breadth proxy.

The proxy is intentionally architecture-selection evidence, not human accuracy.
It selects concepts from the frozen A593 universe without consulting opened 17/88
outcomes, then makes two independent Gemma calls per concept:

1) task/activity atoms for entrant C;
2) held-out user-style descriptions for common A/B/C evaluation.

Only public v31 taxonomy evidence is sent to the teacher. The old A593 teacher
phrases are used only to define membership in the frozen A593 universe and are
never included in either prompt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import generate_gemma4_yv_teacher_pilot as pilot

DEFAULT_CASES = 32
WS_RE = re.compile(r"\s+")


def norm(text: str) -> str:
    return WS_RE.sub(" ", text.casefold()).strip()


def evidence_for(concept: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_label": str(concept.get("preferred_label") or "").strip(),
        "definition": str(concept.get("definition") or "").strip(),
        "alternative_labels": pilot.clean_list(concept.get("alternative_labels")),
    }


def task_prompt(evidence: dict[str, Any]) -> str:
    return f"""Du extraherar source-bound arbetsaktiviteter ur en svensk offentlig yrkestaxonomi.

Använd ENDAST explicit information i EVIDENS. Använd inte allmän yrkeskunskap för att fylla luckor. Om evidensen inte räcker för konkreta aktiviteter ska `usable` vara false och `task_atoms` vara tom.

EVIDENS:
{json.dumps(evidence, ensure_ascii=False, sort_keys=True)}

Returnera endast ett JSON-objekt med exakt denna form:
{{"usable": true, "task_atoms": ["...", "...", "...", "..."]}}

Regler när usable=true:
- exakt 4 korta svenska task/activity-atomer;
- varje atom ska uttrycka ett arbetsmoment, objekt, metod, miljö eller ansvar som faktiskt stöds av evidensen;
- skriv inte yrkestiteln eller alternativa yrkestitlar;
- undvik generiskt språk som passar nästan alla yrken;
- hitta inte på verktyg, ansvar eller arbetsuppgifter som evidensen inte säger.
"""


def query_prompt(evidence: dict[str, Any]) -> str:
    return f"""Du skapar ett HELT SEPARAT held-out test för svensk yrkessökning.

Använd ENDAST explicit information i EVIDENS. Använd inte allmän yrkeskunskap för att fylla luckor. Om evidensen inte räcker för en rimlig arbetsbeskrivning ska `usable` vara false och `queries` vara tom.

EVIDENS:
{json.dumps(evidence, ensure_ascii=False, sort_keys=True)}

Returnera endast ett JSON-objekt med exakt denna form:
{{"usable": true, "queries": {{"direct_task": "...", "colloquial_first_person": "...", "indirect_narrative": "...", "noisy_telegraphic": "..."}}}}

Regler när usable=true:
- exakt en beskrivning per namngiven stil;
- beskriv vad personen gör, inte vad yrket heter;
- skriv inte den kanoniska yrkestiteln eller alternativa yrkestitlar;
- direkt_task: konkret arbetsbeskrivning;
- colloquial_first_person: vardaglig svensk jag-form;
- indirect_narrative: rimlig indirekt beskrivning utan titeln;
- noisy_telegraphic: kort telegramstil, gärna bortfall av småord men fortfarande begriplig;
- hitta inte på verktyg, ansvar eller arbetsuppgifter som evidensen inte säger.
"""


def call_json(api_key: str, prompt: str, *, max_attempts: int = 5) -> tuple[dict[str, Any], dict[str, Any]]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{pilot.MODEL}:generateContent"
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "thinkingConfig": {"thinkingLevel": "minimal"},
                "responseMimeType": "application/json",
                "temperature": 0.0,
                "maxOutputTokens": 1200,
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
            text = pilot.extract_text(payload)
            value = json.loads(text)
            if not isinstance(value, dict):
                raise RuntimeError("response is not a JSON object")
            return value, payload.get("usageMetadata") or {}
        except (json.JSONDecodeError, RuntimeError) as exc:
            if attempt + 1 >= max_attempts:
                raise RuntimeError(f"invalid Gemma JSON object after retries: {exc}") from exc
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            if status != 429 and not (500 <= status < 600):
                raise RuntimeError(f"Gemma API HTTP {status}: {detail}") from exc
            if attempt + 1 >= max_attempts:
                raise RuntimeError(f"Gemma API still failing after retries, HTTP {status}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 >= max_attempts:
                raise RuntimeError(f"Gemma network error after retries: {exc}") from exc
        delay = min(60.0, 2.0 ** attempt) + random.uniform(0.0, 1.0)
        time.sleep(delay)
    raise AssertionError("unreachable")


def forbidden_titles(evidence: dict[str, Any]) -> list[str]:
    values = [evidence["canonical_label"], *evidence["alternative_labels"]]
    return [norm(x) for x in values if len(norm(x)) >= 4]


def contains_forbidden(text: str, forbidden: list[str]) -> bool:
    value = norm(text)
    return any(title in value for title in forbidden)


def validate_tasks(value: dict[str, Any], evidence: dict[str, Any]) -> tuple[bool, list[str]]:
    usable = value.get("usable") is True
    atoms = value.get("task_atoms")
    if not usable:
        return False, []
    if not isinstance(atoms, list) or len(atoms) != 4:
        raise RuntimeError("task response must contain exactly 4 task_atoms")
    atoms = [str(x).strip() for x in atoms]
    if any(not x for x in atoms):
        raise RuntimeError("blank task atom")
    forbidden = forbidden_titles(evidence)
    if any(contains_forbidden(x, forbidden) for x in atoms):
        raise RuntimeError("task atom leaked a canonical/alternative title")
    return True, atoms


def validate_queries(value: dict[str, Any], evidence: dict[str, Any]) -> tuple[bool, dict[str, str]]:
    usable = value.get("usable") is True
    queries = value.get("queries")
    if not usable:
        return False, {}
    keys = ["direct_task", "colloquial_first_person", "indirect_narrative", "noisy_telegraphic"]
    if not isinstance(queries, dict) or set(queries) != set(keys):
        raise RuntimeError("query response must contain exactly four named styles")
    out = {key: str(queries[key]).strip() for key in keys}
    if any(not text for text in out.values()):
        raise RuntimeError("blank held-out query")
    forbidden = forbidden_titles(evidence)
    if any(contains_forbidden(text, forbidden) for text in out.values()):
        raise RuntimeError("held-out query leaked a canonical/alternative title")
    return True, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True, help="frozen A593 teacher JSONL; membership only")
    ap.add_argument("--cases", type=int, default=DEFAULT_CASES)
    ap.add_argument("--requests-per-minute", type=float, default=6.0)
    ap.add_argument("--output", default="artifacts/a593-breadth-proxy-v0.json")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    if not (8 <= args.cases <= 64):
        raise RuntimeError("--cases must be between 8 and 64")
    if not (0.2 <= args.requests_per_minute <= 6.0):
        raise RuntimeError("RPM must stay between 0.2 and 6.0")

    teacher_rows = [json.loads(line) for line in Path(args.teacher).read_text(encoding="utf-8").splitlines() if line.strip()]
    a593_ids = {str(row.get("concept_id") or "") for row in teacher_rows}
    if len(a593_ids) != 593:
        raise RuntimeError(f"A593 membership drift: {len(a593_ids)}")

    taxonomy = pilot.fetch_json(pilot.TAXONOMY_URL)
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    eligible = []
    for cid in sorted(a593_ids):
        concept = by_id.get(cid)
        if not concept or concept.get("type") != "occupation-name":
            continue
        evidence = evidence_for(concept)
        if len(evidence["definition"]) < 60:
            continue
        key = hashlib.sha256(f"a593-breadth-proxy-v0:{cid}".encode("utf-8")).hexdigest()
        eligible.append((key, cid, concept, evidence))
    eligible.sort(key=lambda row: row[0])
    selected = eligible[: args.cases]
    if len(selected) != args.cases:
        raise RuntimeError(f"only {len(selected)} eligible concepts")

    interval = 60.0 / args.requests_per_minute
    rows = []
    failures = []
    request_count = 0
    for index, (_key, cid, concept, evidence) in enumerate(selected):
        label = str(concept.get("preferred_label") or "").strip()
        print(f"breadth proxy {index + 1}/{len(selected)}: {label}", flush=True)
        try:
            if request_count:
                time.sleep(interval)
            task_value, task_usage = call_json(api_key, task_prompt(evidence))
            request_count += 1
            task_usable, atoms = validate_tasks(task_value, evidence)

            time.sleep(interval)
            query_value, query_usage = call_json(api_key, query_prompt(evidence))
            request_count += 1
            query_usable, queries = validate_queries(query_value, evidence)
        except RuntimeError as exc:
            failures.append({"concept_id": cid, "label": label, "error": str(exc)})
            continue

        rows.append(
            {
                "concept_id": cid,
                "label": label,
                "source_evidence": evidence,
                "task_usable": task_usable,
                "task_atoms": atoms,
                "query_usable": query_usable,
                "heldout_queries": queries,
                "task_usage_metadata": task_usage,
                "query_usage_metadata": query_usage,
            }
        )

    payload = {
        "id": "YV-A593-breadth-proxy-v0",
        "status": "prefrozen synthetic architecture-selection evidence",
        "model": pilot.MODEL,
        "opened_17_88_used_for_selection_or_prompting": False,
        "old_a593_teacher_phrases_sent_to_generator": False,
        "selection": {
            "universe": "frozen A593 concept membership",
            "eligibility": "v31 occupation-name with canonical definition length >= 60 characters",
            "ordering": "sha256('a593-breadth-proxy-v0:' + concept_id)",
            "requested_cases": args.cases,
            "successful_rows": len(rows),
            "failures": failures,
        },
        "generation": {
            "independent_calls_per_concept": 2,
            "task_call": "source evidence -> 4 task/activity atoms",
            "query_call": "source evidence -> four held-out styles",
            "temperature": 0.0,
            "requests_per_minute_cap": args.requests_per_minute,
        },
        "rows": rows,
        "evidence_warning": "Synthetic/model-authored architecture evidence only. It may select between coarse architecture families but is not a human/user accuracy estimate.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), "rows": len(rows), "failures": len(failures)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
