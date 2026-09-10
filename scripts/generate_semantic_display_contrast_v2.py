#!/usr/bin/env python3
"""Generate preregistered pairwise source-grounded contrast evidence for semantic display v2.

No query/ad/opened data are loaded. For each already-frozen hard-confusion pair, Gemma
selects verbatim spans from each candidate's own canonical definition that are most
useful for distinguishing that candidate from its peer. Absence from peer evidence is
never turned into a negative occupational fact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import generate_a593_language_diversity_falsifier as gemma

PREREG = Path("research/evaluation/v31/semantic-display-hard-confusion-v2-preregistration.json")
PAIRS = Path("research/evaluation/v31/compile-time-semantic-a593-confusion-task-atoms-v0.json")
CHECKPOINT = Path("research/evaluation/v31/semantic-display-hard-confusion-v2-contrast-checkpoint.json")
STATUS = Path("research/evaluation/v31/semantic-display-hard-confusion-v2-contrast-status.json")
OUTPUT = Path("research/evaluation/v31/semantic-display-hard-confusion-v2-contrast-evidence.json")

INSTRUCTIONS = """Du väljer KÄLLCITAT som hjälper en senare semantisk relevansdomare att skilja två närliggande svenska yrkesroller.

Du får två yrkeskandidater och deras kanoniska källevidens. För VARJE kandidat: välj 0–4 KONTIGUA, ORAGRANNA textspann ur just den kandidatens DEFINITION som är särskilt användbara för att skilja kandidaten från den andra rollen.

Regler:
- varje span måste vara ordagrant kopierad från kandidatens egen definition, högst 24 ord;
- välj positiv evidens om kandidatens aktiviteter, ansvar, objekt, metoder eller arbetskontext;
- prioritera sådant som är mer särskiljande än generiskt gemensamt innehåll;
- påstå ALDRIG att den andra rollen inte/kan inte gör något bara för att det saknas i dess text;
- använd ingen allmän yrkeskunskap och hitta inte på fakta;
- om definitionen inte ger en meningsfull särskiljande span: returnera tom lista;
- yrkestiteln ensam är inte en giltig span;
- ingen förklaring och ingen markdown.

JSON exakt:
{"pair_id":"...","a_spans":["..."],"b_spans":["..."]}
"""
PROMPT_SHA256 = hashlib.sha256(INSTRUCTIONS.encode("utf-8")).hexdigest()
SPACE = re.compile(r"\s+")


def norm(text: Any) -> str:
    return SPACE.sub(" ", str(text or "")).strip().casefold()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def load_prereg() -> dict[str, Any]:
    p = json.loads(PREREG.read_text(encoding="utf-8"))
    if p.get("status") != "frozen before v2 contrast generation and oracle outcomes":
        raise RuntimeError("v2 preregistration is not frozen")
    if p["opened_data_policy"].get("opened_17_88_loaded_for_generation_design_or_execution") is not False:
        raise RuntimeError("opened-data policy drift")
    if int(p["query_evaluation"]["year"]) != 2021:
        raise RuntimeError("evaluation-year drift")
    return p


def load_pairs(prereg: dict[str, Any]) -> list[dict[str, str]]:
    raw = json.loads(PAIRS.read_text(encoding="utf-8"))
    if int(raw.get("pairs", -1)) != 11 or int(raw.get("concepts", -1)) != 22:
        raise RuntimeError("hard-confusion population drift")
    if raw.get("opened_17_88_loaded") is not False:
        raise RuntimeError("hard-confusion artifact opened-data drift")
    rows = []
    for i, r in enumerate(raw.get("rows") or []):
        rows.append({
            "pair_id": f"pair-{i+1:02d}",
            "a_concept_id": str(r["a_concept_id"]),
            "b_concept_id": str(r["b_concept_id"]),
        })
    if len(rows) != 11 or len({x for r in rows for x in (r['a_concept_id'], r['b_concept_id'])}) != 22:
        raise RuntimeError("pair parsing drift")
    return rows


def taxonomy() -> tuple[dict[str, dict[str, Any]], str]:
    wire = gemma.fetch_bytes(gemma.TAXONOMY_URL)
    actual = hashlib.sha256(wire).hexdigest()
    expected = gemma.expected_taxonomy_hash()
    if actual != expected:
        raise RuntimeError(f"taxonomy source drift: {actual} != {expected}")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active = [cid for cid, c in by_id.items() if c.get("type") == "occupation-name"]
    if len(active) != 2105:
        raise RuntimeError(f"active occupation universe drift: {len(active)}")
    return by_id, actual


def evidence(c: dict[str, Any]) -> dict[str, Any]:
    e = gemma.source_evidence(c)
    return {
        "canonical_label": str(e.get("canonical_label") or ""),
        "alternative_labels": list(e.get("alternative_labels") or [])[:8],
        "definition": str(e.get("definition") or ""),
    }


def prompt(pair: dict[str, str], by_id: dict[str, dict[str, Any]]) -> str:
    payload = {
        "pair_id": pair["pair_id"],
        "a": {"concept_id": pair["a_concept_id"], "evidence": evidence(by_id[pair["a_concept_id"]])},
        "b": {"concept_id": pair["b_concept_id"], "evidence": evidence(by_id[pair["b_concept_id"]])},
    }
    return INSTRUCTIONS + "\nPAIR:\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def parse(value: dict[str, Any], pair: dict[str, str], by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if str(value.get("pair_id") or "") != pair["pair_id"]:
        raise RuntimeError("pair_id mismatch")
    out: dict[str, Any] = {
        "pair_id": pair["pair_id"],
        "a_concept_id": pair["a_concept_id"],
        "b_concept_id": pair["b_concept_id"],
    }
    for side, cid_key in (("a", "a_concept_id"), ("b", "b_concept_id")):
        raw = value.get(f"{side}_spans")
        if not isinstance(raw, list) or len(raw) > 4:
            raise RuntimeError(f"invalid {side}_spans")
        cid = pair[cid_key]
        definition = str(by_id[cid].get("definition") or "")
        source = norm(definition)
        label = norm(by_id[cid].get("preferred_label"))
        accepted: list[str] = []
        seen: set[str] = set()
        for item in raw:
            span = SPACE.sub(" ", str(item or "")).strip()
            key = norm(span)
            if not key:
                continue
            if len(span.split()) > 24:
                raise RuntimeError(f"{side} span exceeds 24 words")
            if key == label:
                raise RuntimeError(f"{side} span is title only")
            if key not in source:
                raise RuntimeError(f"{side} span is not verbatim definition evidence: {span!r}")
            if key not in seen:
                seen.add(key)
                accepted.append(span)
        out[f"{side}_spans"] = accepted
        out[f"{side}_definition_sha256"] = hashlib.sha256(definition.encode("utf-8")).hexdigest()
    return out


def state_contract(pair_rows: list[dict[str, str]], taxonomy_sha: str) -> dict[str, Any]:
    population_sha = hashlib.sha256(json.dumps(pair_rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "version": "semantic-display-contrast-v2-checkpoint-v0",
        "model": gemma.MODEL,
        "prompt_sha256": PROMPT_SHA256,
        "taxonomy_sha256": taxonomy_sha,
        "pair_population_sha256": population_sha,
        "expected_pairs": 11,
    }


def load_state(contract: dict[str, Any]) -> dict[str, Any]:
    if not CHECKPOINT.exists():
        return {"contract": contract, "rows": {}, "transport_failures": {}, "usage_metadata": []}
    s = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    if s.get("contract") != contract:
        raise RuntimeError("contrast checkpoint contract drift")
    s.setdefault("rows", {})
    s.setdefault("transport_failures", {})
    s.setdefault("usage_metadata", [])
    return s


def write_state(state: dict[str, Any], *, phase: str) -> None:
    atomic_json(CHECKPOINT, state)
    atomic_json(STATUS, {
        "id": "YV-semantic-display-hard-confusion-v2-contrast-status",
        "phase": phase,
        "complete": len(state["rows"]) == int(state["contract"]["expected_pairs"]),
        "completed_pairs": len(state["rows"]),
        "expected_pairs": int(state["contract"]["expected_pairs"]),
        "transport_failure_pairs": len(state.get("transport_failures") or {}),
        "contract": state["contract"],
    })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests-per-minute", type=float, default=3.0)
    ap.add_argument("--attempts-per-pair", type=int, default=6)
    args = ap.parse_args()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY required")
    prereg = load_prereg()
    pairs = load_pairs(prereg)
    by_id, taxonomy_sha = taxonomy()
    if any(cid not in by_id for p in pairs for cid in (p["a_concept_id"], p["b_concept_id"])):
        raise RuntimeError("hard-confusion concept missing from taxonomy")
    contract = state_contract(pairs, taxonomy_sha)
    state = load_state(contract)
    write_state(state, phase="initialized")

    interval = 60.0 / max(0.2, args.requests_per_minute)
    last_call = 0.0
    for pair in pairs:
        pid = pair["pair_id"]
        if pid in state["rows"]:
            continue
        last_error = "not attempted"
        for attempt in range(1, args.attempts_per_pair + 1):
            elapsed = time.monotonic() - last_call
            if last_call and elapsed < interval:
                time.sleep(interval - elapsed)
            try:
                raw, usage = gemma.call_json(api_key, prompt(pair, by_id), temperature=0.0, max_attempts=3)
                last_call = time.monotonic()
                row = parse(raw, pair, by_id)
                state["rows"][pid] = row
                state["usage_metadata"].append(usage)
                state["transport_failures"].pop(pid, None)
                write_state(state, phase="running")
                print(f"contrast durable progress {len(state['rows'])}/11", flush=True)
                break
            except Exception as exc:
                last_call = time.monotonic()
                last_error = f"{type(exc).__name__}: {exc}"[:600]
                print(f"contrast retry {attempt}/{args.attempts_per_pair} {pid}: {last_error}", flush=True)
                time.sleep(5)
        if pid not in state["rows"]:
            old = state["transport_failures"].get(pid) or {}
            state["transport_failures"][pid] = {"runs_failed": int(old.get("runs_failed", 0)) + 1, "last_error": last_error}
            write_state(state, phase="running-with-transport-failures")

    complete = len(state["rows"]) == 11
    write_state(state, phase="complete" if complete else "incomplete")
    if not complete:
        print("contrast generation incomplete; durable checkpoint retained", flush=True)
        return 0

    rows = [state["rows"][p["pair_id"]] for p in pairs]
    covered = sum(bool(r["a_spans"]) and bool(r["b_spans"]) for r in rows)
    result = {
        "id": "YV-semantic-display-hard-confusion-v2-contrast-evidence",
        "status": "complete preregistered source-grounded pairwise contrast artifact",
        "preregistration": str(PREREG),
        "model": gemma.MODEL,
        "prompt_sha256": PROMPT_SHA256,
        "opened_17_88_loaded": False,
        "historical_query_or_ad_text_loaded": False,
        "source": "v31 canonical preferred label, alternative labels and definition; emitted spans validate verbatim against own definition",
        "negative_fact_policy": "absence from peer source evidence is never encoded as inability/non-applicability",
        "taxonomy_sha256": taxonomy_sha,
        "pairs": 11,
        "pairs_with_bilateral_contrast": covered,
        "coverage_gate_minimum": 8,
        "coverage_gate_passed": covered >= 8,
        "rows": rows,
        "usage_metadata": state["usage_metadata"],
    }
    atomic_json(OUTPUT, result)
    print(json.dumps({"pairs": 11, "bilateral_contrast": covered, "coverage_gate_passed": covered >= 8}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
