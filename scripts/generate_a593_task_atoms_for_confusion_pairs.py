#!/usr/bin/env python3
"""Generate C-v0 task atoms for frozen A593 confusion pairs.

Pair membership comes from the already-frozen source-bound sniper contrast corpus,
but no contrast cues/descriptions are sent to the generator. Only public canonical
v31 evidence for the two concepts is sent. Opened 17/88 is never loaded.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import generate_a593_breadth_proxy as proxy
import generate_gemma4_yv_teacher_pilot as pilot


def prompt_for_pair(a: dict[str, Any], b: dict[str, Any]) -> str:
    return f"""Du extraherar source-bound arbetsaktiviteter ur en svensk offentlig yrkestaxonomi.

Du får två separata yrkeskoncept. För VARJE koncept: använd endast explicit information i dess egen EVIDENS. Använd inte allmän yrkeskunskap och använd inte information från det andra konceptet för att fylla luckor.

A_EVIDENS:
{json.dumps(a, ensure_ascii=False, sort_keys=True)}

B_EVIDENS:
{json.dumps(b, ensure_ascii=False, sort_keys=True)}

Returnera endast JSON med exakt formen:
{{"a_atoms": ["...", "...", "...", "...", "...", "..."], "b_atoms": ["...", "...", "...", "...", "...", "..."]}}

Regler:
- exakt 6 korta svenska task/activity-atomer per koncept;
- varje atom ska uttrycka ett konkret arbetsmoment, objekt, metod, miljö eller ansvar som explicit stöds av respektive evidens;
- skriv inte den kanoniska titeln eller alternativa titlar;
- undvik generiskt språk;
- hitta inte på verktyg, ansvar eller arbetsuppgifter;
- om evidensen är tunn: dela hellre upp det som faktiskt står än att lägga till ny kunskap.
"""


def validate_atoms(value: Any, evidence: dict[str, Any], key: str) -> list[str]:
    if not isinstance(value, dict):
        raise RuntimeError("response is not an object")
    atoms = value.get(key)
    if not isinstance(atoms, list) or len(atoms) != 6:
        raise RuntimeError(f"{key} must contain exactly 6 atoms")
    out = [str(x).strip() for x in atoms]
    if any(not x for x in out):
        raise RuntimeError(f"{key} contains blank atom")
    forbidden = proxy.forbidden_titles(evidence)
    if any(proxy.contains_forbidden(x, forbidden) for x in out):
        raise RuntimeError(f"{key} leaked canonical/alternative title")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contrasts", default="research/training/v31/a593-gemma4-sniper-contrasts-v0.jsonl")
    ap.add_argument("--requests-per-minute", type=float, default=6.0)
    ap.add_argument("--output", default="artifacts/a593-confusion-task-atoms-v0.json")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    contrast_rows = [json.loads(line) for line in Path(args.contrasts).read_text(encoding="utf-8").splitlines() if line.strip()]
    pairs = [row for row in contrast_rows if (row.get("contrast") or {}).get("distinguishable") is True]
    if len(pairs) != 11:
        raise RuntimeError(f"distinguishable pair drift: {len(pairs)} != 11")
    ids = [str(row[key]) for row in pairs for key in ("a_concept_id", "b_concept_id")]
    if len(set(ids)) != 22:
        raise RuntimeError("expected 22 unique concepts across 11 distinguishable pairs")

    taxonomy = pilot.fetch_json(pilot.TAXONOMY_URL)
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    interval = 60.0 / args.requests_per_minute
    generated = []
    for index, row in enumerate(pairs):
        if index:
            time.sleep(interval)
        a_id = str(row["a_concept_id"])
        b_id = str(row["b_concept_id"])
        a_evidence = proxy.evidence_for(by_id[a_id])
        b_evidence = proxy.evidence_for(by_id[b_id])
        value, usage = proxy.call_json(api_key, prompt_for_pair(a_evidence, b_evidence))
        a_atoms = validate_atoms(value, a_evidence, "a_atoms")
        b_atoms = validate_atoms(value, b_evidence, "b_atoms")
        generated.append({
            "a_concept_id": a_id,
            "b_concept_id": b_id,
            "a_atoms": a_atoms,
            "b_atoms": b_atoms,
            "usage_metadata": usage,
        })
        print(f"pair {index + 1}/{len(pairs)}: {a_id} vs {b_id}", flush=True)

    result = {
        "id": "YV-A593-confusion-task-atoms-v0",
        "model": pilot.MODEL,
        "pairs": len(generated),
        "concepts": len(set(ids)),
        "contrast_cues_or_descriptions_sent_to_generator": False,
        "opened_17_88_loaded": False,
        "source": "public canonical v31 label/definition/alternative labels only",
        "rows": generated,
        "evidence_warning": "Generated task representation for architecture diagnostic only; not taxonomy truth beyond its canonical source evidence.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
