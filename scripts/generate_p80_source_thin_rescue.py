#!/usr/bin/env python3
"""Generate a source-enriched language-diversity rescue for the 22 canonical-thin P80 occupations.

Uses only prefrozen direct AF evidence from p80-source-thin-evidence-audit.json:
Relevanta kompetenser + ad-keyword corpus. Typed job-title labels are validation-only
forbidden surfaces. Opened 17/88 and retrieval outcomes are never loaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import generate_a593_language_diversity_falsifier as g

EXPECTED = 22
TRAIN_KEYS = g.TRAIN_KEYS
HOLDOUT_KEYS = g.HOLDOUT_KEYS


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tolerant_extract_json(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("no candidates")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
    if not text:
        raise RuntimeError("no response text")
    value = json.loads(text)
    if isinstance(value, list):
        return {"items": value}
    if isinstance(value, dict):
        return value
    raise RuntimeError("response JSON must be object or array")


g.extract_json = tolerant_extract_json


def compact_evidence(audit_row: dict[str, Any], canonical: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_label": canonical["canonical_label"],
        "definition": canonical["definition"],
        "alternative_labels": canonical["alternative_labels"],
        "relevant_skills": [x["label"] for x in audit_row.get("top_relevant_skills") or [] if x.get("label")][:10],
        "ad_keywords": [x["term"] for x in audit_row.get("top_ad_keywords_bm25") or [] if x.get("term")][:12],
    }


def training_prompt(batch: list[dict[str, Any]]) -> str:
    payload = [{"concept_id": x["concept_id"], "evidence": x["evidence"]} for x in batch]
    return f"""Du skapar syntetiskt träningsspråk för svensk yrkessökning. Varje yrke har tunn kanonisk definition, därför får du två DIREKTA KÄLLSIGNALER: relevanta kompetenser och annonsnyckelord som är bundna till exakt samma yrkes-id.

HÅRD EVIDENSGRÄNS: använd bara det som uttryckligen stöds av dessa signaler. En kompetens/ett nyckelord visar association till yrket men ger inte rätt att hitta på arbetsmiljö, verktyg, ansvar, kunder eller arbetsflöden som inte uttrycks. Hellre null än inferens.

Skapa fyra korta svenska beskrivningar utan yrkestitel:
- colloquial_first_person: vardaglig jag-form, 7–22 ord
- indirect_narrative: indirekt situation/ansvar/resultat, 8–28 ord
- elliptical_noisy: fragmentarisk söktext, 4–16 ord
- concrete_work: konkreta moment/begrepp endast där källsignalerna faktiskt stödjer dem, 6–24 ord

Regler:
- använd inte canonical_label eller alternative_labels;
- lägg inte till typiska yrkeskunskaper från allmän kunskap;
- variera ordval mellan formuleringarna;
- returnera endast JSON.

Format: {{"items":[{{"concept_id":"...","phrases":{{"colloquial_first_person":"... eller null","indirect_narrative":"... eller null","elliptical_noisy":"... eller null","concrete_work":"... eller null"}}}}]}}

EVIDENSBATCH:
{json.dumps(payload, ensure_ascii=False, sort_keys=True)}
"""


def holdout_prompt(batch: list[dict[str, Any]]) -> str:
    payload = [{"concept_id": x["concept_id"], "evidence": x["evidence"]} for x in batch]
    return f"""Du skriver FRISTÅENDE syntetiska testfrågor för svensk yrkessökning från direkt källbunden yrkesevidens. Dessa testfrågor skapas i ett separat anrop från träningsspråket.

HÅRD EVIDENSGRÄNS: använd bara explicit information i relevanta kompetenser och annonsnyckelord. Lägg inte till allmän yrkeskunskap. Hellre null än inferens. Personen vet inte vad yrket heter.

Skapa fyra frågor:
- shift_story: kort vardaglig sekvens i jag-form, 10–30 ord
- plain_search: spontan fritext om vad personen gör, 6–20 ord
- compressed_note: kort ofullständig anteckning, 4–14 ord
- outcome_context: ansvar/resultat endast om källsignalerna faktiskt uttrycker det, 8–24 ord

Regler:
- använd inte canonical_label eller alternative_labels;
- ingen markdown eller förklaring;
- returnera endast JSON.

Format: {{"items":[{{"concept_id":"...","queries":{{"shift_story":"... eller null","plain_search":"... eller null","compressed_note":"... eller null","outcome_context":"... eller null"}}}}]}}

EVIDENSBATCH:
{json.dumps(payload, ensure_ascii=False, sort_keys=True)}
"""


def validate(row: dict[str, Any], generated: dict[str, str | None], *, training_texts: list[str] | None = None) -> tuple[dict[str, str | None], dict[str, int]]:
    canonical = row["canonical"]
    accepted, base = g.validate_texts({"evidence": canonical}, generated, training_texts=training_texts)
    forbidden = [x.get("label") or "" for x in row.get("typed_job_titles") or []]
    title_reject = 0
    for key, text in list(accepted.items()):
        if text and g.phrase_has_surface(text, forbidden):
            accepted[key] = None
            title_reject += 1
    rejected = dict(base.get("rejected") or {})
    rejected["typed_job_title_surface"] = title_reject
    return accepted, rejected


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", default="research/evaluation/v31/p80-source-thin-evidence-audit.json")
    ap.add_argument("--training-output", default="research/training/v31/p80-source-thin-rescue-training-v0.jsonl")
    ap.add_argument("--holdout-output", default="research/evaluation/v31/p80-source-thin-rescue-holdout-v0.jsonl")
    ap.add_argument("--summary-output", default="research/evaluation/v31/p80-source-thin-rescue-generation-v0.json")
    ap.add_argument("--batch-size", type=int, default=11)
    ap.add_argument("--requests-per-minute", type=float, default=6.0)
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required")
    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    if audit.get("source_thin_concepts") != EXPECTED or audit.get("candidate_for_source_bound_rescue") != EXPECTED:
        raise RuntimeError("source-thin audit drift")
    if "no retrieval outcomes" not in str(audit.get("evidence_class", "")):
        raise RuntimeError("audit evidence boundary drift")

    taxonomy_wire = g.fetch_bytes(g.TAXONOMY_URL)
    taxonomy_sha = hashlib.sha256(taxonomy_wire).hexdigest()
    if taxonomy_sha != g.expected_taxonomy_hash() or taxonomy_sha != audit.get("taxonomy_sha256"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(taxonomy_wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    selected = []
    for index, audit_row in enumerate(audit["rows"]):
        cid = str(audit_row["concept_id"])
        canonical = g.source_evidence(by_id[cid])
        selected.append({
            "concept_id": cid,
            "selection_index": index,
            "canonical": canonical,
            "typed_job_titles": audit_row.get("typed_job_titles") or [],
            "evidence": compact_evidence(audit_row, canonical),
        })

    usage = {"training": [], "holdout": []}
    train_by_id: dict[str, Any] = {}
    hold_by_id: dict[str, Any] = {}
    min_interval = 60.0 / max(args.requests_per_minute, 0.1)
    last_call = 0.0

    def wait_rate() -> None:
        nonlocal last_call
        elapsed = time.monotonic() - last_call
        if last_call and elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        last_call = time.monotonic()

    for start in range(0, len(selected), args.batch_size):
        batch = selected[start:start + args.batch_size]
        wait_rate()
        raw, meta = g.call_json(api_key, training_prompt(batch), temperature=0.55)
        usage["training"].append(meta)
        parsed = g.parse_batch(raw, batch, "phrases", TRAIN_KEYS)
        training_texts: dict[str, list[str]] = {}
        for row in batch:
            cid = row["concept_id"]
            accepted, rejected = validate(row, parsed[cid])
            usable_count = sum(isinstance(v, str) and bool(v.strip()) for v in accepted.values())
            training_texts[cid] = [v for v in accepted.values() if isinstance(v, str) and v.strip()]
            train_by_id[cid] = {
                "concept_id": cid, "label": row["canonical"]["canonical_label"], "model": g.MODEL,
                "phrases": accepted, "source_evidence": row["evidence"], "usable": usable_count >= 3,
                "validation": {"rejected": rejected, "usable_count": usable_count},
                "provenance": "P80 canonical-thin rescue from direct relevant-skills + ad-keyword evidence; no opened outcomes",
            }

        wait_rate()
        raw, meta = g.call_json(api_key, holdout_prompt(batch), temperature=0.7)
        usage["holdout"].append(meta)
        parsed = g.parse_batch(raw, batch, "queries", HOLDOUT_KEYS)
        for row in batch:
            cid = row["concept_id"]
            accepted, rejected = validate(row, parsed[cid], training_texts=training_texts[cid])
            usable_count = sum(isinstance(v, str) and bool(v.strip()) for v in accepted.values())
            hold_by_id[cid] = {
                "concept_id": cid, "label": row["canonical"]["canonical_label"], "model": g.MODEL,
                "queries": accepted, "source_evidence": row["evidence"], "usable": usable_count >= 3,
                "validation": {"rejected": rejected, "usable_count": usable_count},
                "provenance": "separate P80 canonical-thin rescue holdout call; direct source evidence; no opened outcomes",
            }

    training_rows = [train_by_id[row["concept_id"]] for row in selected]
    holdout_rows = [hold_by_id[row["concept_id"]] for row in selected]
    write_jsonl(Path(args.training_output), training_rows)
    write_jsonl(Path(args.holdout_output), holdout_rows)
    jointly = sum(t["usable"] and h["usable"] for t, h in zip(training_rows, holdout_rows, strict=True))
    summary = {
        "id": "YV-P80-source-thin-rescue-generation-v0",
        "model": g.MODEL,
        "taxonomy_sha256": taxonomy_sha,
        "requested_concepts": EXPECTED,
        "jointly_usable_concepts": jointly,
        "evidence_sources": ["relevant-skills", "ad-keyword-corpus"],
        "typed_job_titles_role": "validation-only forbidden surfaces; not generation evidence",
        "opened_17_88_loaded": False,
        "retrieval_outcomes_used": False,
        "training_temperature": 0.55,
        "holdout_temperature": 0.7,
        "training_sha256": file_sha(Path(args.training_output)),
        "holdout_sha256": file_sha(Path(args.holdout_output)),
        "usage_metadata": usage,
        "warning": "model-authored source-bound mechanism evidence; not human accuracy",
    }
    out = Path(args.summary_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"requested": EXPECTED, "jointly_usable": jointly}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
