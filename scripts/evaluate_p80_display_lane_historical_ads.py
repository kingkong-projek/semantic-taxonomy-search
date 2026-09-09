#!/usr/bin/env python3
"""Validate the frozen P80 lane display rule on natural historical job-ad language.

This is an independent-language proxy, not human self-description truth. The lane rule
is fixed before this corpus is fetched: ratio_mean_support >= 0.12. No threshold or
formula selection occurs here and opened 17/88 is never loaded.

Primary evidence excludes the 22 canonical-thin rescue identities because their
training source included ad-derived keywords. Historical 2025 Platsbanken ads are
queried by their structured occupation-name concept id. Sentences containing the
target occupation title/variants are removed before ranking to avoid trivial title
leakage. Raw ad text is never written to the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from evaluate_a593_language_diversity_falsifier import load_diverse_training, load_teacher
from evaluate_gemma_a149 import build_ranker
from evaluate_p80_display_lane_calibration import add_teacher, best_phrase_support, confidence
from evaluate_p80_display_relevance_calibration import candidate_features
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm
from evaluate_pareto_c1 import rank_c1

TAXONOMY_URL = (
    "https://data.jobtechdev.se/taxonomy/version/31/query/"
    "concepts-and-common-relations/concepts-and-common-relations.json"
)
HISTORICAL_SEARCH = "https://historical.api.jobtechdev.se/search"
YEAR_START = "2025-01-01T00:00:00"
YEAR_END = "2026-01-01T00:00:00"
FORMULA = "ratio_mean_support"
THRESHOLD = 0.12
EXPECTED_UNIVERSE = 2105


def fetch_json(url: str, retries: int = 4) -> Any:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "semantic-taxonomy-search-research/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read())
        except Exception as exc:  # network retry only; corpus is frozen after success
            last = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last}")


def text_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def alt_labels(concept: dict[str, Any]) -> list[str]:
    raw = concept.get("alternative_labels") or concept.get("alternative-labels") or []
    out: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                value = item.get("label") or item.get("value") or item.get("preferred_label")
                if isinstance(value, str):
                    out.append(value)
    return out


def title_surfaces(concept: dict[str, Any]) -> list[str]:
    values = [text_value(concept.get("preferred_label")), *alt_labels(concept)]
    surfaces: set[str] = set()
    for value in values:
        n = norm(value)
        if len(n) >= 4:
            surfaces.add(n)
        # Common taxonomy qualifiers must not make title-leak detection too weak.
        for part in re.split(r"[,/()]+", value):
            p = norm(part)
            if len(p) >= 4:
                surfaces.add(p)
    return sorted(surfaces, key=len, reverse=True)


def strip_markup(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def make_query(text: str, forbidden: list[str], max_words: int = 80) -> tuple[str | None, int]:
    clean = strip_markup(text)
    if not clean:
        return None, 0
    sentences = re.split(r"(?<=[.!?])\s+|\s*[\r\n]+\s*", clean)
    kept: list[str] = []
    removed = 0
    for sentence in sentences:
        n = norm(sentence)
        if any(surface and surface in n for surface in forbidden):
            removed += 1
            continue
        if sentence.strip():
            kept.append(sentence.strip())
    words = " ".join(kept).split()
    if len(words) < 25:
        return None, removed
    return " ".join(words[:max_words]), removed


def ad_id(hit: dict[str, Any]) -> str:
    return str(hit.get("id") or hit.get("external_id") or hit.get("original_id") or "")


def ad_description(hit: dict[str, Any]) -> str:
    desc = hit.get("description") or {}
    if isinstance(desc, dict):
        return text_value(desc.get("text")) or text_value(desc.get("text_formatted"))
    return ""


def occupation_id(hit: dict[str, Any]) -> str:
    occ = hit.get("occupation") or {}
    if isinstance(occ, dict):
        return str(occ.get("concept_id") or occ.get("conceptId") or "")
    return ""


def publication_date(hit: dict[str, Any]) -> str:
    return text_value(hit.get("publication_date")) or text_value(hit.get("published"))


def fetch_concept_ads(cid: str, concept: dict[str, Any], *, limit: int, accepted: int) -> dict[str, Any]:
    params = {
        "published-after": YEAR_START,
        "published-before": YEAR_END,
        "occupation-name": cid,
        "offset": 0,
        "limit": limit,
        "request-timeout": 60,
    }
    payload = fetch_json(HISTORICAL_SEARCH + "?" + urllib.parse.urlencode(params))
    hits = payload.get("hits") if isinstance(payload, dict) else None
    if not isinstance(hits, list):
        raise RuntimeError(f"unexpected historical search schema for {cid}: no hits[]")
    forbidden = title_surfaces(concept)
    rows: list[dict[str, Any]] = []
    rejected = {"wrong_structured_target": 0, "too_short_after_title_removal": 0, "missing_description": 0}
    for hit in sorted((h for h in hits if isinstance(h, dict)), key=ad_id):
        aid = ad_id(hit)
        if not aid:
            continue
        structured = occupation_id(hit)
        if structured and structured != cid:
            rejected["wrong_structured_target"] += 1
            continue
        body = ad_description(hit)
        if not body:
            rejected["missing_description"] += 1
            continue
        query, removed = make_query(body, forbidden)
        if not query:
            rejected["too_short_after_title_removal"] += 1
            continue
        rows.append({
            "concept_id": cid,
            "ad_id": aid,
            "publication_date": publication_date(hit),
            "query": query,
            "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
            "query_word_count": len(query.split()),
            "title_sentences_removed": removed,
        })
        if len(rows) >= accepted:
            break
    return {"concept_id": cid, "hits_returned": len(hits), "accepted": rows, "rejected": rejected}


def wilson(success: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total <= 0:
        return None
    p = success / total
    d = 1 + z * z / total
    center = (p + z * z / (2 * total)) / d
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / d
    return [round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6)]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    baseline_hits = retained_hits = baseline_tail = retained_tail = 0
    shown_before = shown_after = neg_before = neg_after = zero_after = 0
    by_rank = {i: [0, 0] for i in range(1, 6)}
    top1 = 0
    for row in rows:
        target = row["concept_id"]
        candidates = row["candidates"]
        shown_before += len(candidates)
        neg_before += sum(c["concept_id"] != target for c in candidates)
        target_row = next((c for c in candidates if c["concept_id"] == target), None)
        if target_row:
            baseline_hits += 1
            rank = int(target_row["rank"])
            top1 += int(rank == 1)
            by_rank[rank][0] += 1
            if rank >= 2:
                baseline_tail += 1
        kept = [c for c in candidates if confidence(c, FORMULA) >= THRESHOLD]
        shown_after += len(kept)
        neg_after += sum(c["concept_id"] != target for c in kept)
        zero_after += int(not kept)
        if target_row and target_row in kept:
            retained_hits += 1
            rank = int(target_row["rank"])
            by_rank[rank][1] += 1
            if rank >= 2:
                retained_tail += 1
    n = len(rows)
    neg_reduction = 1 - neg_after / max(1, neg_before)
    return {
        "queries": n,
        "concepts": len({r["concept_id"] for r in rows}),
        "baseline_top1": top1,
        "baseline_hit5": baseline_hits,
        "baseline_tail_hits_rank2_5": baseline_tail,
        "retained_hit5": retained_hits,
        "retained_tail_hits_rank2_5": retained_tail,
        "hit5_retention": round(retained_hits / max(1, baseline_hits), 6),
        "hit5_retention_wilson95": wilson(retained_hits, baseline_hits),
        "tail_hit_retention": round(retained_tail / max(1, baseline_tail), 6),
        "tail_hit_retention_wilson95": wilson(retained_tail, baseline_tail),
        "mean_displayed_before": round(shown_before / max(1, n), 6),
        "mean_displayed_after": round(shown_after / max(1, n), 6),
        "exact_target_negative_reduction": round(neg_reduction, 6),
        "zero_result_rate_after": round(zero_after / max(1, n), 6),
        "rank_retention": {
            str(rank): {
                "baseline": values[0],
                "retained": values[1],
                "rate": round(values[1] / max(1, values[0]), 6),
                "wilson95": wilson(values[1], values[0]),
            }
            for rank, values in by_rank.items()
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--teacher", default="research/enrichment/v31/gemma4-yv-a593/phrases.jsonl")
    ap.add_argument("--priority", default="research/evaluation/v31/p80-track2-priority-coverage.json")
    ap.add_argument("--a593-train", default="research/training/v31/a593-language-diversity-training-v0.jsonl")
    ap.add_argument("--p80-train", default="research/training/v31/p80-language-diversity-training-v0.jsonl")
    ap.add_argument("--rescue-train", default="research/training/v31/p80-source-thin-rescue-training-v0.jsonl")
    ap.add_argument("--output", default="research/evaluation/v31/p80-display-lane-historical-ads-v0.json")
    ap.add_argument("--search-limit", type=int, default=15)
    ap.add_argument("--ads-per-concept", type=int, default=6)
    args = ap.parse_args()

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    wire = fetch(TAXONOMY_URL)
    if hashlib.sha256(wire).hexdigest() != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != EXPECTED_UNIVERSE:
        raise RuntimeError("candidate universe drift")

    priority = json.loads(Path(args.priority).read_text(encoding="utf-8"))
    existing_ids = {str(r["concept_id"]) for r in priority.get("existing_diversified_v0") or []}
    missing_ids = {str(r["concept_id"]) for r in priority.get("missing_diversified_v0") or []}
    p80_ids = existing_ids | missing_ids
    if len(p80_ids) != 159:
        raise RuntimeError("P80 membership drift")

    _teacher_ids, base_teacher = load_teacher(Path(args.teacher))
    a593_train, _ = load_diverse_training(Path(args.a593_train))
    p80_train, _ = load_diverse_training(Path(args.p80_train))
    rescue_train, rescue_meta = load_diverse_training(Path(args.rescue_train))
    rescue_ids = {str(r.get("concept_id")) for r in rescue_meta if r.get("concept_id")}
    if len(rescue_ids) != 22:
        raise RuntimeError("rescue identity set drift")

    merged_teacher = {cid: list(v) for cid, v in base_teacher.items()}
    add_teacher(merged_teacher, a593_train, existing_ids)
    add_teacher(merged_teacher, p80_train, missing_ids)
    add_teacher(merged_teacher, rescue_train, p80_ids)
    ranker, exact, surfaces = build_ranker(by_id, ids, merged_teacher)

    phrase_map: dict[str, list[str]] = {cid: list(v) for cid, v in base_teacher.items()}
    add_teacher(phrase_map, a593_train, existing_ids)
    add_teacher(phrase_map, p80_train, missing_ids)
    add_teacher(phrase_map, rescue_train, p80_ids)

    primary_ids = sorted(p80_ids - rescue_ids)
    fetched: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(fetch_concept_ads, cid, by_id[cid], limit=args.search_limit, accepted=args.ads_per_concept): cid
            for cid in primary_ids
        }
        for fut in as_completed(futures):
            fetched.append(fut.result())
    fetched.sort(key=lambda x: x["concept_id"])

    cases = [row for group in fetched for row in group["accepted"]]
    rows: list[dict[str, Any]] = []
    for case in cases:
        scored = rank_c1(ranker, case["query"], exact, surfaces)
        candidates = candidate_features(ranker, case["query"], scored)
        for c in candidates:
            c.update(best_phrase_support(ranker, case["query"], phrase_map.get(c["concept_id"], [])))
        rows.append({**case, "candidates": candidates})

    metrics = summarize(rows)
    word_counts = [r["query_word_count"] for r in rows]
    manifest = [
        {
            "concept_id": r["concept_id"],
            "ad_id": r["ad_id"],
            "publication_date": r["publication_date"],
            "query_sha256": r["query_sha256"],
            "query_word_count": r["query_word_count"],
            "title_sentences_removed": r["title_sentences_removed"],
        }
        for r in rows
    ]
    result = {
        "id": "YV-P80-display-lane-historical-ads-v0",
        "evidence_class": "natural historical Platsbanken ad-language proxy with structured occupation-name target; not human self-description or human relevance judgment",
        "candidate_universe": 2105,
        "opened_17_88_loaded": False,
        "ranker_changed": False,
        "lane_rule_changed": False,
        "frozen_lane_rule": {"formula": FORMULA, "threshold": THRESHOLD},
        "source": {
            "api": HISTORICAL_SEARCH,
            "published_after": YEAR_START,
            "published_before": YEAR_END,
            "structured_filter": "occupation-name=<P80 concept id>",
            "license": "CC0",
            "raw_text_committed": False,
        },
        "primary_independence_boundary": {
            "p80_total": 159,
            "excluded_source_family_overlap_rescue_ids": len(rescue_ids),
            "eligible_primary_concepts": len(primary_ids),
            "reason": "source-thin rescue training used ad-derived keyword evidence; exclude all 22 rescue identities from this primary ad-language proxy",
        },
        "query_construction": {
            "body_only": True,
            "headline_used": False,
            "target_title_sentence_removal": True,
            "max_words": 80,
            "min_words": 25,
            "selection": "first accepted body text after deterministic title-sentence removal; up to six ads per concept; no ranker-dependent selection",
        },
        "sample": {
            "queries": len(rows),
            "concepts": len({r["concept_id"] for r in rows}),
            "mean_query_words": round(sum(word_counts) / max(1, len(word_counts)), 3),
            "concepts_with_no_accepted_ad": sum(not g["accepted"] for g in fetched),
            "api_hits_returned": sum(g["hits_returned"] for g in fetched),
            "rejected": {
                key: sum(g["rejected"][key] for g in fetched)
                for key in ("wrong_structured_target", "too_short_after_title_removal", "missing_description")
            },
        },
        "metrics": metrics,
        "interpretation_contract": {
            "no_threshold_selection": True,
            "no_binary_promotion_gate_added_after_result": True,
            "purpose": "estimate whether the already-frozen lane rule retains real-language rank2-5 targets while reducing visible exact-target negatives on a larger independent proxy",
            "human_evidence_still_required": True,
        },
        "manifest": manifest,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"sample": result["sample"], "metrics": metrics}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
