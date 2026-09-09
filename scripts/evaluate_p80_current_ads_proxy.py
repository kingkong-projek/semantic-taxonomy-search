#!/usr/bin/env python3
"""Evaluate A593 vs P80 language expansion on current human-written job-ad task text.

Purpose: obtain a real-language proxy while independent human YV descriptions are not
available. This is NOT equivalent to user self-description accuracy.

Leakage controls:
- targets touched by source-thin ad-keyword rescue are excluded;
- headline is never used;
- description slices containing preferred/alternative/job-title surfaces for the
  target occupation are rejected;
- opened 17/88 outcomes are never loaded;
- P80 challenger evaluated here excludes rescue phrases.

The selected query slices and ad ids are frozen in the output so the benchmark does
not depend on future JobSearch state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_a593_language_diversity_falsifier import load_diverse_training, load_teacher
from evaluate_c2_job_title_router import relation_parent_ids
from evaluate_gemma_a149 import build_ranker, rank_ids
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm

TAXONOMY_URL = (
    "https://data.jobtechdev.se/taxonomy/version/31/query/"
    "concepts-and-common-relations/concepts-and-common-relations.json"
)
JOBSEARCH_URL = "https://jobsearch.api.jobtechdev.se/search"
MARKERS = (
    "arbetsuppgifter", "dina arbetsuppgifter", "arbetsuppgifterna", "om rollen",
    "i rollen", "rollen innebär", "arbetsbeskrivning", "ditt uppdrag", "uppdraget innebär",
)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
PHONE_RE = re.compile(r"(?<!\w)(?:\+46|0)[0-9][0-9 ()/-]{6,}[0-9]")
WS_RE = re.compile(r"\s+")


def as_list(value: Any) -> list[str]:
    return [str(x).strip() for x in value] if isinstance(value, list) else []


def jobsearch(cid: str, limit: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"occupation-name": cid, "limit": limit})
    req = urllib.request.Request(
        f"{JOBSEARCH_URL}?{query}",
        headers={"Accept": "application/json", "User-Agent": "semantic-taxonomy-search-real-ad-proxy/0.1"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = json.load(response)
    hits = payload.get("hits") if isinstance(payload, dict) else None
    return hits if isinstance(hits, list) else []


def clean_text(value: str) -> str:
    text = EMAIL_RE.sub(" ", value)
    text = URL_RE.sub(" ", text)
    text = PHONE_RE.sub(" ", text)
    return WS_RE.sub(" ", text).strip()


def work_slice(text: str) -> str:
    text = clean_text(text)
    lower = text.casefold()
    starts = [lower.find(marker) for marker in MARKERS if lower.find(marker) >= 0]
    start = min(starts) if starts else 0
    slice_ = text[start:start + 1200].strip()
    return slice_


def contains_surface(text: str, surfaces: set[str]) -> bool:
    nt = norm(text)
    for surface in surfaces:
        ns = norm(surface)
        if len(ns) >= 4 and ns in nt:
            return True
    return False


def metrics(rows: list[dict[str, Any]], rank_key: str) -> dict[str, Any]:
    n = len(rows)
    ranks = [int(r[rank_key]) for r in rows]
    return {
        "cases": n,
        "top1": sum(r == 1 for r in ranks),
        "top1_rate": round(sum(r == 1 for r in ranks) / max(1, n), 6),
        "hit5": sum(r <= 5 for r in ranks),
        "hit5_rate": round(sum(r <= 5 for r in ranks) / max(1, n), 6),
        "mrr": round(sum(1 / r for r in ranks) / max(1, n), 6),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--teacher", default="research/enrichment/v31/gemma4-yv-a593/phrases.jsonl")
    ap.add_argument("--priority", default="research/evaluation/v31/p80-track2-priority-coverage.json")
    ap.add_argument("--a593-diverse", default="research/training/v31/a593-language-diversity-training-v0.jsonl")
    ap.add_argument("--p80-diverse", default="research/training/v31/p80-language-diversity-training-v0.jsonl")
    ap.add_argument("--rescue", default="research/training/v31/p80-source-thin-rescue-training-v0.jsonl")
    ap.add_argument("--ads-per-concept", type=int, default=3)
    ap.add_argument("--fetch-limit", type=int, default=20)
    ap.add_argument("--output", default="research/evaluation/v31/p80-current-ads-proxy-v0.json")
    args = ap.parse_args()

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    wire = fetch(TAXONOMY_URL)
    tax_sha = hashlib.sha256(wire).hexdigest()
    if tax_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != 2105:
        raise RuntimeError("candidate universe drift")

    priority = json.loads(Path(args.priority).read_text(encoding="utf-8"))
    p80_rows = [*(priority.get("existing_diversified_v0") or []), *(priority.get("missing_diversified_v0") or [])]
    p80_ids = {str(r["concept_id"]) for r in p80_rows}
    if len(p80_ids) != 159:
        raise RuntimeError("P80 membership drift")
    p80_rank = {str(r["concept_id"]): int(r.get("p80_rank") or 9999) for r in p80_rows}

    _teacher_ids, base_teacher = load_teacher(Path(args.teacher))
    a593_diverse, _ = load_diverse_training(Path(args.a593_diverse))
    p80_diverse, _ = load_diverse_training(Path(args.p80_diverse))
    _rescue_train, rescue_meta = load_diverse_training(Path(args.rescue))
    rescue_ids = set(rescue_meta)
    eligible_targets = sorted(p80_ids - rescue_ids, key=lambda cid: (p80_rank.get(cid, 9999), cid))

    existing_ids = {str(r["concept_id"]) for r in priority.get("existing_diversified_v0") or []}
    missing_ids = {str(r["concept_id"]) for r in priority.get("missing_diversified_v0") or []}
    control_teacher = {cid: list(v) for cid, v in base_teacher.items()}
    challenger_teacher = {cid: list(v) for cid, v in base_teacher.items()}
    for cid, values in a593_diverse.items():
        if cid in existing_ids:
            challenger_teacher.setdefault(cid, []).extend(values)
    for cid, values in p80_diverse.items():
        if cid in missing_ids:
            challenger_teacher.setdefault(cid, []).extend(values)

    control_ranker, control_exact, control_surfaces = build_ranker(by_id, ids, control_teacher)
    challenger_ranker, challenger_exact, challenger_surfaces = build_ranker(by_id, ids, challenger_teacher)

    job_titles_by_parent: dict[str, set[str]] = defaultdict(set)
    for concept in by_id.values():
        if concept.get("type") != "job-title":
            continue
        label = str(concept.get("preferred_label") or "").strip()
        if not label:
            continue
        for parent in relation_parent_ids(concept, by_id):
            job_titles_by_parent[parent].add(label)

    cases: list[dict[str, Any]] = []
    concept_stats = []
    for cid in eligible_targets:
        concept = by_id[cid]
        label = str(concept.get("preferred_label") or cid)
        surfaces = {label, *as_list(concept.get("alternative_labels")), *job_titles_by_parent.get(cid, set())}
        try:
            hits = jobsearch(cid, args.fetch_limit)
        except Exception as exc:
            concept_stats.append({"concept_id": cid, "label": label, "status": "fetch_error", "error": str(exc)[:200]})
            continue
        accepted = []
        reject_surface = reject_short = 0
        for hit in hits:
            desc = hit.get("description") if isinstance(hit, dict) else None
            text = str(desc.get("text") or "") if isinstance(desc, dict) else ""
            query = work_slice(text)
            if len(query) < 120:
                reject_short += 1
                continue
            if contains_surface(query, surfaces):
                reject_surface += 1
                continue
            ad_id = str(hit.get("id") or hit.get("external_id") or "")
            accepted.append((ad_id, query))
            if len(accepted) >= args.ads_per_concept:
                break
        concept_stats.append({
            "concept_id": cid,
            "label": label,
            "fetched": len(hits),
            "accepted": len(accepted),
            "rejected_target_surface": reject_surface,
            "rejected_short": reject_short,
        })
        for ad_id, query in accepted:
            cr = rank_ids(control_ranker, control_exact, control_surfaces, query)
            hr = rank_ids(challenger_ranker, challenger_exact, challenger_surfaces, query)
            control_rank = cr.index(cid) + 1 if cid in cr else len(cr) + 1
            challenger_rank = hr.index(cid) + 1 if cid in hr else len(hr) + 1
            cases.append({
                "ad_id": ad_id,
                "concept_id": cid,
                "label": label,
                "p80_rank": p80_rank.get(cid),
                "query": query,
                "control_rank": control_rank,
                "challenger_rank": challenger_rank,
                "control_top5": cr[:5],
                "challenger_top5": hr[:5],
            })

    if len(cases) < 80 or len({r["concept_id"] for r in cases}) < 35:
        raise RuntimeError(f"real-ad proxy too small: cases={len(cases)}, concepts={len({r['concept_id'] for r in cases})}")

    control = metrics(cases, "control_rank")
    challenger = metrics(cases, "challenger_rank")
    result = {
        "id": "YV-P80-current-ads-proxy-v0",
        "evidence_class": "current human-written job-ad language proxy with registered occupation filter; not user self-description accuracy",
        "frozen_at_source": "JobSearch current open ads at workflow execution time; selected ad ids/query slices frozen below",
        "taxonomy_sha256": tax_sha,
        "candidate_universe": 2105,
        "opened_17_88_loaded": False,
        "leakage_controls": {
            "source_thin_rescue_target_ids_excluded": len(rescue_ids),
            "headline_used": False,
            "target_preferred_alternative_and_job_title_surfaces_rejected": True,
            "challenger_excludes_source_thin_rescue_phrases": True,
            "contact_urls_emails_phones_removed": True,
        },
        "selection": {
            "eligible_p80_targets": len(eligible_targets),
            "ads_per_concept_max": args.ads_per_concept,
            "fetch_limit_per_concept": args.fetch_limit,
            "minimum_query_chars": 120,
            "maximum_query_chars": 1200,
            "concepts_with_cases": len({r["concept_id"] for r in cases}),
            "cases": len(cases),
        },
        "control": {"name": "A593", **control},
        "challenger": {"name": "A593 + P80 diversified canonical-source language; no rescue", **challenger},
        "delta": {
            "top1_pp": round(100 * (challenger["top1_rate"] - control["top1_rate"]), 4),
            "hit5_pp": round(100 * (challenger["hit5_rate"] - control["hit5_rate"]), 4),
            "mrr": round(challenger["mrr"] - control["mrr"], 6),
            "rank_improved": sum(r["challenger_rank"] < r["control_rank"] for r in cases),
            "rank_worsened": sum(r["challenger_rank"] > r["control_rank"] for r in cases),
            "rank_unchanged": sum(r["challenger_rank"] == r["control_rank"] for r in cases),
        },
        "interpretation_boundary": "Real employer language and registered occupation metadata materially reduce synthetic-language dependence, but job ads are longer and differently authored than end-user work descriptions. Use as a strong proxy, not final promotion truth.",
        "concept_fetch_stats": concept_stats,
        "cases": cases,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("selection", "control", "challenger", "delta")}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
