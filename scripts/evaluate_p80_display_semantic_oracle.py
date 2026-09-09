#!/usr/bin/env python3
"""One-shot semantic Top-5 relevance oracle for the active YV display-precision residual.

This does NOT change retrieval or ranking and is NOT a runtime proposal. It asks whether
additional semantic information is sufficient to separate a useful lower-ranked target
from an obviously irrelevant visible candidate.

Protocol frozen before outcomes:
- current P80 A-family ranker; all 2,105 occupations still compete;
- natural historical 2024 Platsbanken task snippets only;
- 22 source-thin rescue target identities excluded from primary proxy evaluation;
- semantic teacher never sees rank, structured target, SSYK4, or opened stress rows;
- candidate order is deterministically shuffled per query;
- candidate facts are source-bound: canonical taxonomy evidence + already-frozen
  source-bound teacher phrases;
- verdicts are keep / uncertain / drop; insufficient evidence => uncertain;
- rank 1 is always retained; ranks 2-5 are removed only on a confident drop;
- safe precision proxy counts only different-SSYK4 non-targets;
- opened user-style stress may be replayed only after a prefrozen primary pass.

The teacher is research/oracle evidence only. A pass licenses investigation of a compact
runtime-compatible student; it never licenses runtime LLM/API use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import generate_a593_language_diversity_falsifier as gemma
from evaluate_a593_language_diversity_falsifier import load_diverse_training, load_teacher
from evaluate_gemma_a149 import build_ranker
from evaluate_p80_display_lane_calibration import add_teacher
from evaluate_p80_display_natural_task_calibration import EVAL_YEAR, EXPECTED_UNIVERSE, TAXONOMY_URL, fetch_year_concept, wilson
from evaluate_p80_display_ssyk_phrase_gate import SSYK_HIERARCHY_URL, build_ssyk4_map
from evaluate_p80_lexical_ablation import as_list, expected_hash, fetch, norm
from evaluate_pareto_c1 import rank_c1

def _tolerant_extract_json(payload: dict[str, Any]) -> dict[str, Any]:
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
    value = json.loads(text)
    if isinstance(value, list):
        return {"items": value}
    if isinstance(value, dict):
        return value
    raise RuntimeError("response JSON must be object or array")


gemma.extract_json = _tolerant_extract_json


MODEL = gemma.MODEL
PROMPT_VERSION = "yv-p80-semantic-display-oracle-v0"
VERDICTS = {"keep", "uncertain", "drop"}
MAX_TASK_PHRASES = 2
EVIDENCE_VERSION = "label-alt3-definition50-task2x24-v0"

INSTRUCTIONS = """Du är en KONSERVATIV semantisk relevansdomare för svensk yrkessökning.

För varje CASE får du en användares fria beskrivning av arbete och fem yrkeskandidater.
Bedöm VARJE kandidat självständigt. Du får inte anta att någon kandidat måste vara rätt.
Kandidaternas ordning är slumpad och betyder ingenting.

Använd endast kandidatfakta som finns i EVIDENS. Fyll inte luckor med allmän yrkeskunskap.
Canonical_label och alternative_labels är giltiga identitetsytor; definition och task_evidence
är källbunden beskrivande evidens.

Verdikt:
- keep: användarbeskrivningen kan rimligen beskriva detta yrke enligt evidensen;
- uncertain: evidensen räcker inte för säker keep eller drop, eller beskrivningen är tvetydig;
- drop: kandidaten är tydligt semantiskt irrelevant för det arbete användaren beskriver.

VIKTIGT: drop ska vara konservativt. Några gemensamma generiska ord räcker inte för keep,
men avsaknad av detaljevidens räcker inte heller för drop. Bevara plausibla närliggande roller.
Bedöm semantisk koherens mellan arbetsuppgifter/ansvar/objekt/metoder och kandidatens evidens.

Returnera ENDAST JSON. Ingen markdown, inga förklaringar.
Format exakt:
{"items":[{"case_key":"...","judgments":[{"concept_id":"...","verdict":"keep|uncertain|drop"}]}]}
"""
PROMPT_SHA256 = hashlib.sha256(INSTRUCTIONS.encode("utf-8")).hexdigest()


def clean_strings(value: Any, limit: int | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in as_list(value):
        text = str(raw).strip()
        key = norm(text)
        if text and key and key not in seen:
            seen.add(key)
            out.append(text)
            if limit is not None and len(out) >= limit:
                break
    return out


def clip_words(text: Any, limit: int) -> str:
    return " ".join(str(text or "").split()[:limit])


def candidate_evidence(concept: dict[str, Any], phrases: list[str]) -> dict[str, Any]:
    label = str(concept.get("preferred_label") or "").strip()
    definition = str(concept.get("definition") or "").strip()
    if norm(definition) == norm(label):
        definition = ""
    return {
        "canonical_label": clip_words(label, 12),
        "alternative_labels": [clip_words(x, 12) for x in clean_strings(concept.get("alternative_labels"), limit=3)],
        "definition": clip_words(definition, 50),
        "task_evidence": [clip_words(x, 24) for x in clean_strings(phrases, limit=MAX_TASK_PHRASES)],
    }


def case_key(case: dict[str, Any]) -> str:
    return f"{case['ad_id']}:{case['query_sha256'][:16]}"


def shuffled_payload(case: dict[str, Any], by_id: dict[str, dict[str, Any]], phrase_map: dict[str, list[str]]) -> dict[str, Any]:
    key = case_key(case)
    candidates = []
    for c in case["candidates"]:
        cid = str(c["concept_id"])
        candidates.append({
            "concept_id": cid,
            "evidence": candidate_evidence(by_id[cid], phrase_map.get(cid, [])),
        })
    candidates.sort(key=lambda x: hashlib.sha256(f"{PROMPT_VERSION}:{key}:{x['concept_id']}".encode()).hexdigest())
    return {"case_key": key, "query": case["query"], "candidates": candidates}


def prompt(batch: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], phrase_map: dict[str, list[str]]) -> str:
    payload = [shuffled_payload(case, by_id, phrase_map) for case in batch]
    return INSTRUCTIONS + "\nCASES:\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def parse_response(value: dict[str, Any], batch: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    expected = {case_key(case): {str(c["concept_id"]) for c in case["candidates"]} for case in batch}
    items = value.get("items")
    if not isinstance(items, list):
        raise RuntimeError("semantic oracle response missing items")
    out: dict[str, dict[str, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("case_key") or "")
        if key not in expected or key in out:
            continue
        judgments = item.get("judgments")
        if not isinstance(judgments, list):
            continue
        current: dict[str, str] = {}
        for judgment in judgments:
            if not isinstance(judgment, dict):
                continue
            cid = str(judgment.get("concept_id") or "")
            verdict = str(judgment.get("verdict") or "").strip().casefold()
            if cid in expected[key] and cid not in current and verdict in VERDICTS:
                current[cid] = verdict
        if set(current) == expected[key]:
            out[key] = current
    if set(out) != set(expected):
        missing = sorted(set(expected) - set(out))
        raise RuntimeError(f"semantic oracle response case mismatch: {missing[:5]} count={len(missing)}")
    return out


def display_keep(candidate: dict[str, Any]) -> bool:
    return int(candidate["rank"]) == 1 or str(candidate["verdict"]) != "drop"


def summarize(rows: list[dict[str, Any]], ssyk4: dict[str, str]) -> dict[str, Any]:
    before = after = baseline_hits = retained_hits = baseline_tail = retained_tail = 0
    safe_before = safe_after = safe_tail_before = safe_tail_after = 0
    by_rank = {i: [0, 0] for i in range(1, 6)}
    verdict_counts = {v: 0 for v in sorted(VERDICTS)}
    for row in rows:
        target = str(row["concept_id"])
        target_code = ssyk4[target]
        cs = row["candidates"]
        before += len(cs)
        for c in cs:
            verdict_counts[str(c["verdict"])] += 1
        target_row = next((c for c in cs if str(c["concept_id"]) == target), None)
        if target_row:
            baseline_hits += 1
            rank = int(target_row["rank"])
            by_rank[rank][0] += 1
            baseline_tail += int(rank >= 2)
        kept = [c for c in cs if display_keep(c)]
        after += len(kept)
        if target_row and target_row in kept:
            retained_hits += 1
            rank = int(target_row["rank"])
            by_rank[rank][1] += 1
            retained_tail += int(rank >= 2)
        for c in cs:
            cid = str(c["concept_id"])
            if cid == target or ssyk4[cid] == target_code:
                continue
            safe_before += 1
            safe_tail_before += int(int(c["rank"]) >= 2)
            if c in kept:
                safe_after += 1
                safe_tail_after += int(int(c["rank"]) >= 2)
    n = len(rows)
    return {
        "queries": n,
        "concepts": len({str(r['concept_id']) for r in rows}),
        "baseline_hit5": baseline_hits,
        "retained_hit5": retained_hits,
        "hit5_retention": round(retained_hits / max(1, baseline_hits), 6),
        "hit5_retention_wilson95": wilson(retained_hits, baseline_hits),
        "baseline_tail_hits_rank2_5": baseline_tail,
        "retained_tail_hits_rank2_5": retained_tail,
        "tail_hit_retention": round(retained_tail / max(1, baseline_tail), 6),
        "tail_hit_retention_wilson95": wilson(retained_tail, baseline_tail),
        "mean_displayed_before": round(before / max(1, n), 6),
        "mean_displayed_after": round(after / max(1, n), 6),
        "safe_cross_ssyk_negative_before": safe_before,
        "safe_cross_ssyk_negative_after": safe_after,
        "safe_cross_ssyk_negative_reduction": round(1 - safe_after / max(1, safe_before), 6),
        "safe_cross_ssyk_tail_negative_before": safe_tail_before,
        "safe_cross_ssyk_tail_negative_after": safe_tail_after,
        "safe_cross_ssyk_tail_negative_reduction": round(1 - safe_tail_after / max(1, safe_tail_before), 6),
        "verdict_counts": verdict_counts,
        "rank_retention": {
            str(rank): {
                "baseline": values[0],
                "retained": values[1],
                "rate": round(values[1] / max(1, values[0]), 6),
            }
            for rank, values in by_rank.items()
        },
    }


def load_system() -> tuple[dict[str, dict[str, Any]], list[str], dict[str, str], Any, Any, Any, dict[str, list[str]], list[str]]:
    registry = json.loads(Path("research/coverage/source-adapters.json").read_text(encoding="utf-8"))
    wire = fetch(TAXONOMY_URL)
    if hashlib.sha256(wire).hexdigest() != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != EXPECTED_UNIVERSE:
        raise RuntimeError("candidate universe drift")

    ssyk_wire = fetch(SSYK_HIERARCHY_URL)
    ssyk4 = build_ssyk4_map(json.loads(ssyk_wire))
    if set(ssyk4) != set(ids):
        raise RuntimeError("SSYK4 hierarchy coverage drift")

    priority = json.loads(Path("research/evaluation/v31/p80-track2-priority-coverage.json").read_text(encoding="utf-8"))
    existing = {str(r["concept_id"]) for r in priority.get("existing_diversified_v0") or []}
    missing = {str(r["concept_id"]) for r in priority.get("missing_diversified_v0") or []}
    p80 = existing | missing
    if len(p80) != 159:
        raise RuntimeError("P80 membership drift")

    _teacher_ids, base = load_teacher(Path("research/enrichment/v31/gemma4-yv-a593/phrases.jsonl"))
    a593, _ = load_diverse_training(Path("research/training/v31/a593-language-diversity-training-v0.jsonl"))
    p80t, _ = load_diverse_training(Path("research/training/v31/p80-language-diversity-training-v0.jsonl"))
    rescue, rescue_meta = load_diverse_training(Path("research/training/v31/p80-source-thin-rescue-training-v0.jsonl"))
    rescue_ids = set(rescue_meta)
    if len(rescue_ids) != 22:
        raise RuntimeError("rescue identity drift")
    primary_ids = sorted(p80 - rescue_ids)

    teacher = {cid: list(v) for cid, v in base.items()}
    add_teacher(teacher, a593, existing)
    add_teacher(teacher, p80t, missing)
    add_teacher(teacher, rescue, p80)
    ranker, exact, surfaces = build_ranker(by_id, ids, teacher)

    phrase_map = {cid: list(v) for cid, v in base.items()}
    add_teacher(phrase_map, a593, existing)
    add_teacher(phrase_map, p80t, missing)
    add_teacher(phrase_map, rescue, p80)
    return by_id, ids, ssyk4, ranker, exact, surfaces, phrase_map, primary_ids


def call_semantic_with_quota_retry(api_key: str, prompt_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    # Execution-only handling for the free-tier input-token window. The first run
    # produced zero judgments and failed before outcomes, so this does not change
    # prompt/model/verdict/gates. It only waits for the quota window instead of
    # exhausting generic short retries.
    for attempt in range(12):
        try:
            return gemma.call_json(api_key, prompt_text, temperature=0.0, max_attempts=1)
        except RuntimeError as exc:
            message = str(exc)
            if "429" not in message and "RESOURCE_EXHAUSTED" not in message:
                raise
            match = re.search(r"retry in ([0-9.]+)s", message, re.IGNORECASE)
            wait = (float(match.group(1)) + 3.0) if match else 35.0
            wait = max(25.0, min(wait, 90.0))
            print(f"semantic oracle quota window; wait {wait:.1f}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("semantic oracle quota remained exhausted after 12 quota-aware retries")


def semantic_judge_batches(
    cases: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    phrase_map: dict[str, list[str]],
    *,
    api_key: str,
    batch_size: int,
    requests_per_minute: float,
) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    all_judgments: dict[str, dict[str, str]] = {}
    usage: list[dict[str, Any]] = []
    min_interval = 60.0 / max(0.1, requests_per_minute)
    last_call = 0.0
    for start in range(0, len(cases), batch_size):
        batch = cases[start : start + batch_size]
        elapsed = time.monotonic() - last_call
        if last_call and elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        raw, meta = call_semantic_with_quota_retry(api_key, prompt(batch, by_id, phrase_map))
        last_call = time.monotonic()
        parsed = parse_response(raw, batch)
        all_judgments.update(parsed)
        usage.append(meta)
        print(f"semantic oracle {min(start + len(batch), len(cases))}/{len(cases)}", flush=True)
    return all_judgments, usage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=6)
    ap.add_argument("--requests-per-minute", type=float, default=3.0)
    ap.add_argument("--search-limit", type=int, default=25)
    ap.add_argument("--ads-per-concept", type=int, default=5)
    ap.add_argument("--judgments-output", default="research/evaluation/v31/p80-display-semantic-oracle-judgments-v0.jsonl")
    ap.add_argument("--output", default="research/evaluation/v31/p80-display-semantic-oracle-v0.json")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required")

    by_id, ids, ssyk4, ranker, exact, surfaces, phrase_map, primary_ids = load_system()

    groups: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(fetch_year_concept, cid, by_id[cid], EVAL_YEAR, search_limit=args.search_limit, accepted=args.ads_per_concept): cid
            for cid in primary_ids
        }
        for future in as_completed(futures):
            groups.append(future.result())
    groups.sort(key=lambda x: x["concept_id"])

    cases = [row for group in groups for row in group["accepted"]]
    cases.sort(key=lambda x: (str(x["concept_id"]), str(x["ad_id"])))
    if len(cases) < 600:
        raise RuntimeError(f"unexpectedly small 2024 natural-task set: {len(cases)}")

    for case in cases:
        scored = rank_c1(ranker, case["query"], exact, surfaces)
        case["candidates"] = [
            {"rank": i, "concept_id": cid, "score": float(score), "signal": signal}
            for i, (cid, score, signal) in enumerate(scored[:5], 1)
        ]
        if len(case["candidates"]) != 5:
            raise RuntimeError(f"Top5 underflow for {case_key(case)}")

    judgments, usage = semantic_judge_batches(
        cases, by_id, phrase_map,
        api_key=api_key,
        batch_size=args.batch_size,
        requests_per_minute=args.requests_per_minute,
    )

    rows: list[dict[str, Any]] = []
    for case in cases:
        key = case_key(case)
        verdicts = judgments[key]
        candidates = []
        for c in case["candidates"]:
            cid = str(c["concept_id"])
            candidates.append({
                "rank": int(c["rank"]),
                "concept_id": cid,
                "ssyk4": ssyk4[cid],
                "verdict": verdicts[cid],
            })
        rows.append({
            "case_key": key,
            "ad_id": str(case["ad_id"]),
            "query_sha256": str(case["query_sha256"]),
            "query_word_count": int(case["query_word_count"]),
            "concept_id": str(case["concept_id"]),
            "candidates": candidates,
        })

    judgment_path = Path(args.judgments_output)
    judgment_path.parent.mkdir(parents=True, exist_ok=True)
    judgment_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    metrics = summarize(rows, ssyk4)
    strong = (
        metrics["hit5_retention"] >= 0.99
        and metrics["tail_hit_retention"] >= 0.98
        and metrics["safe_cross_ssyk_tail_negative_reduction"] >= 0.60
    )
    promising = (
        metrics["hit5_retention"] >= 0.98
        and metrics["tail_hit_retention"] >= 0.98
        and metrics["safe_cross_ssyk_tail_negative_reduction"] >= 0.50
    )

    result = {
        "id": "YV-P80-display-semantic-oracle-v0",
        "status": "research semantic sufficiency test; never a runtime LLM proposal",
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": PROMPT_SHA256,
        "candidate_universe": len(ids),
        "ranker_changed": False,
        "rank_order_changed": False,
        "opened_17_88_loaded": False,
        "teacher_blinding": {
            "rank_hidden": True,
            "candidate_order_deterministically_shuffled": True,
            "structured_target_hidden": True,
            "ssyk_hidden": True,
        },
        "display_contract": "rank1 always retained; ranks2-5 retained for keep/uncertain and removed only for drop",
        "evidence_contract": "fixed compact source-bound payload: canonical label, <=3 alternative labels, definition <=50 words, <=2 already-frozen task phrases <=24 words each; no candidate facts may be invented",
        "evidence_version": EVIDENCE_VERSION,
        "sample": {
            "year": EVAL_YEAR,
            "queries": len(rows),
            "concepts": len({r["concept_id"] for r in rows}),
            "rescue_target_ids_excluded": 22,
            "raw_query_text_committed": False,
        },
        "evaluation": metrics,
        "decision_gate": {
            "strong": "overall baseline-Hit@5 target retention >=99%, rank2-5 target retention >=98%, safe cross-SSYK tail-negative reduction >=60%",
            "promising": "overall baseline-Hit@5 target retention >=98%, rank2-5 target retention >=98%, safe cross-SSYK tail-negative reduction >=50%",
            "strong_passed": strong,
            "promising_passed": promising,
            "if_strong_or_promising": "freeze exact prompt/model/rule and replay opened user-style stress unchanged; no retuning",
            "if_neither": "do not build a student; reassess semantic evidence/product interaction rather than adding another heuristic stack",
        },
        "opened_replay_prefrozen_falsifier": {
            "minimum_targetable_hit5_retention": "27/28",
            "minimum_rank2_5_target_retention": "12/13",
            "maximum_mean_visible_list": 3.5,
            "yv01_product_sanity": "must remove at least two of Apotekare, Receptarie, Sjukhusvaktmästare while retaining a sjukskoterska-family result",
            "yv02_product_sanity": "must remove both Vaxeltelefonist and Affarskonsult, IT while retaining an elektriker-family result",
            "purpose": "opened diagnostic acceptance for whether semantic sufficiency is worth distillation; never an accuracy estimate or tuning set",
        },
        "usage_metadata": usage,
        "interpretation_boundary": "Structured ad target and different-SSYK4 negatives are proxy labels, not human relevance judgments. A pass proves semantic information is promising enough to test transfer, not production accuracy.",
    }
    out = Path(args.output)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"evaluation": metrics, "decision_gate": result["decision_gate"]}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
