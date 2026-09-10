#!/usr/bin/env python3
"""Evaluate preregistered pairwise contrast evidence on untouched 2021 hard-confusion text.

The contrast artifact must already be committed and pass its independent source-coverage
gate. Opened rows are never loaded. Retrieval/rank are not part of this pairwise mechanism
test. The oracle remains conservative: uncertain is retained and only clear semantic
irrelevance is a drop.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import evaluate_p80_display_semantic_oracle as oracle
import evaluate_semantic_display_hard_confusion_v1 as v1
import run_p80_display_semantic_oracle_resumable as durable

PREREG = Path("research/evaluation/v31/semantic-display-hard-confusion-v2-preregistration.json")
CONTRAST = Path("research/evaluation/v31/semantic-display-hard-confusion-v2-contrast-evidence.json")
RESULT = Path("research/evaluation/v31/semantic-display-hard-confusion-v2-result.json")
CONTROL_CP = Path("research/evaluation/v31/semantic-display-hard-confusion-v2-control-checkpoint.json")
CONTROL_STATUS = Path("research/evaluation/v31/semantic-display-hard-confusion-v2-control-status.json")
CHALLENGER_CP = Path("research/evaluation/v31/semantic-display-hard-confusion-v2-challenger-checkpoint.json")
CHALLENGER_STATUS = Path("research/evaluation/v31/semantic-display-hard-confusion-v2-challenger-status.json")
YEAR = 2021
PROMPT_VERSION = "yv-semantic-display-hard-confusion-v2"
CONTROL_EVIDENCE = "v0-compact-plus-empty-pair-contrast-v2"
CHALLENGER_EVIDENCE = "v0-compact-plus-source-grounded-pair-contrast-v2"

INSTRUCTIONS = """Du är en KONSERVATIV semantisk relevansdomare för svensk yrkessökning.

För varje CASE får du en användares fria arbetsbeskrivning och två närliggande yrkeskandidater. Bedöm VARJE kandidat självständigt. Du får inte anta att någon kandidat måste vara rätt. Kandidaternas ordning är slumpad och betyder ingenting.

Använd endast fakta i kandidatens EVIDENS. canonical_label och alternative_labels identifierar rollen. definition och task_evidence är källbunden positiv beskrivning. contrast_evidence, när den finns, består av ORAGRANNA källspann som i ett separat query-blint steg valts ut därför att de är särskilt användbara för att skilja kandidaten från den andra rollen i detta par.

VIKTIGT OM KONTRAST: contrast_evidence är positiv evidens för den kandidat där den står. Att en uppgift inte finns i den andra kandidatens evidens betyder INTE att den andra rollen aldrig eller inte får utföra den. Gör inga negativa yrkesfakta av frånvaro i källtext.

Verdikt:
- keep: arbetsbeskrivningen kan rimligen beskriva kandidaten enligt evidensen;
- uncertain: evidensen räcker inte för säker keep eller drop, eller rollerna kan inte särskiljas säkert;
- drop: kandidaten är tydligt semantiskt irrelevant för det arbete användaren beskriver enligt den levererade evidensen.

Några gemensamma generiska ord räcker inte för keep. Avsaknad av detaljevidens räcker inte för drop. Bevara plausibla närliggande roller, men använd uttryckliga särskiljande arbetsuppgifter/ansvar/objekt/metoder när källan ger stöd.

Returnera ENDAST JSON, ingen markdown eller förklaring:
{"items":[{"case_key":"...","judgments":[{"concept_id":"...","verdict":"keep|uncertain|drop"}]}]}
"""
PROMPT_SHA256 = hashlib.sha256(INSTRUCTIONS.encode("utf-8")).hexdigest()
_CURRENT_CONTRAST: dict[str, dict[str, list[str]]] = {}


def load_prereg() -> dict[str, Any]:
    p = json.loads(PREREG.read_text(encoding="utf-8"))
    if p.get("status") != "frozen before v2 contrast generation and oracle outcomes":
        raise RuntimeError("v2 preregistration drift")
    if int(p["query_evaluation"]["year"]) != YEAR:
        raise RuntimeError("v2 year drift")
    if p["opened_data_policy"].get("opened_17_88_loaded_for_generation_design_or_execution") is not False:
        raise RuntimeError("opened-data policy drift")
    return p


def load_contrast() -> tuple[dict[str, dict[str, list[str]]], dict[str, Any], str]:
    wire = CONTRAST.read_bytes()
    raw = json.loads(wire)
    if raw.get("opened_17_88_loaded") is not False or raw.get("historical_query_or_ad_text_loaded") is not False:
        raise RuntimeError("contrast artifact independence drift")
    if int(raw.get("pairs", -1)) != 11:
        raise RuntimeError("contrast pair-count drift")
    if not raw.get("coverage_gate_passed"):
        raise RuntimeError("contrast source-coverage gate failed; 2021 evaluation forbidden")
    out: dict[str, dict[str, list[str]]] = {}
    for row in raw.get("rows") or []:
        pid = str(row["pair_id"])
        a, b = str(row["a_concept_id"]), str(row["b_concept_id"])
        out[pid] = {a: [str(x) for x in row.get("a_spans") or []], b: [str(x) for x in row.get("b_spans") or []]}
    if len(out) != 11:
        raise RuntimeError("contrast rows incomplete")
    return out, raw, hashlib.sha256(wire).hexdigest()


def load_pairs() -> list[dict[str, str]]:
    pairs, _atoms = v1.load_atoms()
    return [{"pair_id": p["pair_id"], "a": p["a"], "b": p["b"]} for p in pairs]


def fetch_cases(by_id: dict[str, dict[str, Any]], pairs: list[dict[str, str]], *, search_limit: int, accepted: int) -> list[dict[str, Any]]:
    concept_to_pair: dict[str, tuple[str, str]] = {}
    for p in pairs:
        concept_to_pair[p["a"]] = (p["pair_id"], p["b"])
        concept_to_pair[p["b"]] = (p["pair_id"], p["a"])
    groups: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(oracle.fetch_year_concept, cid, by_id[cid], YEAR, search_limit=search_limit, accepted=accepted): cid
            for cid in sorted(concept_to_pair)
        }
        for future in as_completed(futures):
            groups.append(future.result())
    groups.sort(key=lambda x: x["concept_id"])
    cases: list[dict[str, Any]] = []
    for group in groups:
        cid = str(group["concept_id"])
        pair_id, negative = concept_to_pair[cid]
        for row in group.get("accepted") or []:
            ordered = sorted((cid, negative))
            cases.append({
                "ad_id": f"hc-v2-{pair_id}-{cid}-{row['ad_id']}",
                "query": str(row["query"]),
                "query_sha256": str(row["query_sha256"]),
                "query_word_count": int(row["query_word_count"]),
                "concept_id": cid,
                "negative_concept_id": negative,
                "pair_id": pair_id,
                "candidates": [
                    {"rank": i + 1, "concept_id": x, "score": 0.0, "signal": "fixed-hard-confusion-pair"}
                    for i, x in enumerate(ordered)
                ],
            })
    cases.sort(key=lambda c: (c["pair_id"], c["concept_id"], c["ad_id"], c["query_sha256"]))
    return cases


def wire_key(case: dict[str, Any]) -> str:
    return "c" + hashlib.sha256(oracle.case_key(case).encode()).hexdigest()[:15]


def v2_prompt(batch: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], phrase_map: dict[str, list[str]]) -> str:
    payload = []
    for case in batch:
        candidates = []
        pid = str(case["pair_id"])
        for c in case["candidates"]:
            cid = str(c["concept_id"])
            base = oracle.candidate_evidence(by_id[cid], phrase_map.get(cid, []))
            base["contrast_evidence"] = list(_CURRENT_CONTRAST.get(pid, {}).get(cid, []))
            candidates.append({"concept_id": cid, "evidence": base})
        candidates.sort(key=lambda x: hashlib.sha256(f"{PROMPT_VERSION}:{oracle.case_key(case)}:{x['concept_id']}".encode()).hexdigest())
        payload.append({"case_key": wire_key(case), "query": case["query"], "candidates": candidates})
    return INSTRUCTIONS + "\nCASES:\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def v2_parse(value: dict[str, Any], batch: list[dict[str, Any]], *, require_all: bool = True) -> dict[str, dict[str, str]]:
    by_wire = {wire_key(case): case for case in batch}
    expected = {
        key: {str(c["concept_id"]) for c in case["candidates"]}
        for key, case in by_wire.items()
    }
    items = value.get("items")
    if not isinstance(items, list):
        raise RuntimeError("v2 response missing items")
    out: dict[str, dict[str, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        wk = str(item.get("case_key") or "")
        if wk not in expected:
            continue
        current: dict[str, str] = {}
        judgments = item.get("judgments")
        if not isinstance(judgments, list):
            continue
        for j in judgments:
            if not isinstance(j, dict):
                continue
            cid = str(j.get("concept_id") or "")
            verdict = str(j.get("verdict") or "").strip().casefold()
            if cid in expected[wk] and verdict in oracle.VERDICTS:
                current[cid] = verdict
        if set(current) == expected[wk]:
            out[oracle.case_key(by_wire[wk])] = current
    expected_original = {oracle.case_key(c) for c in batch}
    if require_all and set(out) != expected_original:
        missing = sorted(expected_original - set(out))
        raise RuntimeError(f"v2 response omitted cases: {missing[:3]}")
    return out


def run_arm(
    arm: str,
    cases: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    phrase_map: dict[str, list[str]],
    contrast: dict[str, dict[str, list[str]]],
    checkpoint: Path,
    status: Path,
    *,
    api_key: str,
    batch_size: int,
    rpm: float,
    attempts: int,
) -> dict[str, Any]:
    global _CURRENT_CONTRAST
    original = {
        "prompt": oracle.prompt,
        "parse": oracle.parse_response,
        "prompt_version": oracle.PROMPT_VERSION,
        "prompt_sha": oracle.PROMPT_SHA256,
        "evidence_version": oracle.EVIDENCE_VERSION,
        "max_task_phrases": oracle.MAX_TASK_PHRASES,
    }
    try:
        oracle.prompt = v2_prompt
        oracle.parse_response = v2_parse
        oracle.PROMPT_VERSION = PROMPT_VERSION
        oracle.PROMPT_SHA256 = PROMPT_SHA256
        oracle.MAX_TASK_PHRASES = 2
        if arm == "control":
            oracle.EVIDENCE_VERSION = CONTROL_EVIDENCE
            _CURRENT_CONTRAST = {}
        elif arm == "challenger":
            oracle.EVIDENCE_VERSION = CHALLENGER_EVIDENCE
            _CURRENT_CONTRAST = contrast
        else:
            raise ValueError(arm)
        state = durable.load_state(checkpoint, cases)
        durable.write_checkpoint(checkpoint, status, state, cases, phase=f"{arm}-initialized")
        durable.semantic_calls(
            cases, by_id, phrase_map, state, checkpoint, status,
            api_key=api_key, batch_size=batch_size, requests_per_minute=rpm, single_case_attempts=attempts,
        )
        complete = len(state["judgments"]) == len(cases)
        durable.write_checkpoint(checkpoint, status, state, cases, phase=f"{arm}-complete" if complete else f"{arm}-incomplete")
        return state
    finally:
        oracle.prompt = original["prompt"]
        oracle.parse_response = original["parse"]
        oracle.PROMPT_VERSION = original["prompt_version"]
        oracle.PROMPT_SHA256 = original["prompt_sha"]
        oracle.EVIDENCE_VERSION = original["evidence_version"]
        oracle.MAX_TASK_PHRASES = original["max_task_phrases"]
        _CURRENT_CONTRAST = {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=6)
    ap.add_argument("--requests-per-minute", type=float, default=3.0)
    ap.add_argument("--single-case-attempts", type=int, default=8)
    ap.add_argument("--search-limit", type=int, default=25)
    ap.add_argument("--ads-per-concept", type=int, default=5)
    args = ap.parse_args()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY required")
    prereg = load_prereg()
    contrast, contrast_raw, contrast_sha = load_contrast()
    pairs = load_pairs()
    by_id, _ids, _ssyk4, _ranker, _exact, _surfaces, phrase_map, _primary = oracle.load_system()
    cases = fetch_cases(by_id, pairs, search_limit=args.search_limit, accepted=args.ads_per_concept)
    pair_coverage = len({c["pair_id"] for c in cases})
    sample_valid = len(cases) >= int(prereg["query_evaluation"]["minimum_total_cases_for_decision"]) and pair_coverage >= int(prereg["query_evaluation"]["minimum_pairs_with_at_least_one_case"])
    sample_sha = hashlib.sha256(json.dumps([
        {"case_key": oracle.case_key(c), "pair_id": c["pair_id"], "target": c["concept_id"], "negative": c["negative_concept_id"]}
        for c in cases
    ], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if not sample_valid:
        durable.atomic_json(RESULT, {
            "id": "YV-semantic-display-hard-confusion-v2-result",
            "status": "inconclusive: preregistered 2021 sample floor not met",
            "sample": {"cases": len(cases), "pairs": pair_coverage, "sha256": sample_sha},
            "opened_17_88_loaded": False,
            "decision_gate": {"passed": False, "sample_valid": False},
        })
        return 0

    control = run_arm(
        "control", cases, by_id, phrase_map, contrast, CONTROL_CP, CONTROL_STATUS,
        api_key=api_key, batch_size=args.batch_size, rpm=args.requests_per_minute, attempts=args.single_case_attempts,
    )
    if len(control["judgments"]) != len(cases):
        return 0
    challenger = run_arm(
        "challenger", cases, by_id, phrase_map, contrast, CHALLENGER_CP, CHALLENGER_STATUS,
        api_key=api_key, batch_size=args.batch_size, rpm=args.requests_per_minute, attempts=args.single_case_attempts,
    )
    if len(challenger["judgments"]) != len(cases):
        return 0

    cm = v1.arm_metrics(cases, control["judgments"])
    vm = v1.arm_metrics(cases, challenger["judgments"])
    improvement = round(vm["hard_negative_drop_rate"] - cm["hard_negative_drop_rate"], 6)
    evaluated_pairs = list(vm["by_pair"].values())
    breadth_success = sum(float(x["hard_negative_drop_rate"]) >= 0.50 for x in evaluated_pairs)
    breadth_rate = round(breadth_success / max(1, len(evaluated_pairs)), 6)
    safety = vm["target_non_drop_rate"] >= 0.98 and vm["target_drop"] <= cm["target_drop"] + 1
    absolute = vm["hard_negative_drop_rate"] >= 0.70
    material = improvement >= 0.20
    breadth = breadth_rate >= 0.60
    contrast_coverage = int(contrast_raw["pairs_with_bilateral_contrast"]) >= int(contrast_raw["coverage_gate_minimum"])
    passed = bool(sample_valid and contrast_coverage and safety and absolute and material and breadth)

    result = {
        "id": "YV-semantic-display-hard-confusion-v2-result",
        "status": "complete independent 2021 pairwise-contrast evidence",
        "preregistration": str(PREREG),
        "opened_17_88_loaded": False,
        "query_year": YEAR,
        "raw_query_text_committed": False,
        "model": oracle.MODEL,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": PROMPT_SHA256,
        "contrast_artifact": str(CONTRAST),
        "contrast_artifact_sha256": contrast_sha,
        "contrast_pairs_with_bilateral_evidence": int(contrast_raw["pairs_with_bilateral_contrast"]),
        "sample": {"cases": len(cases), "pairs_with_cases": pair_coverage, "sha256": sample_sha},
        "control": {"evidence_version": CONTROL_EVIDENCE, "metrics": cm},
        "challenger": {"evidence_version": CHALLENGER_EVIDENCE, "metrics": vm},
        "hard_negative_drop_improvement": improvement,
        "pair_breadth": {"successful_pairs": breadth_success, "evaluated_pairs": len(evaluated_pairs), "rate": breadth_rate},
        "decision_gate": {
            "sample_valid": sample_valid,
            "contrast_coverage_passed": contrast_coverage,
            "target_safety_passed": safety,
            "hard_negative_absolute_passed": absolute,
            "hard_negative_materiality_passed": material,
            "pair_breadth_passed": breadth,
            "passed": passed,
            "if_pass": "freeze exact v2 contrast artifact and oracle contract; only then replay unchanged opened stress as falsifier",
            "if_fail": "do not replay opened and do not distill; reassess richer independent source domains or human relevance evidence",
        },
        "interpretation_boundary": "Historical structured occupation is a proxy target. Pairwise contrast spans are verbatim canonical evidence selected semantically, not human relevance truth."
    }
    durable.atomic_json(RESULT, result)
    print(json.dumps({"sample": result["sample"], "control": cm, "challenger": vm, "improvement": improvement, "breadth": result["pair_breadth"], "gate": result["decision_gate"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
