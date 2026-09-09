#!/usr/bin/env python3
"""Audit source-bound evidence available for the 22 P80 occupations that were too thin for canonical-only language diversification.

No opened 17/88 queries or retrieval outcomes are loaded. This is a source-coverage audit only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import zstandard as zstd

import generate_a593_language_diversity_falsifier as g
from derived_af_coverage import load_json
from evaluate_c2_job_title_router import relation_parent_ids

RELEVANT_URL = "https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/v1/relevanta-kompetenser-t31.json.zst"
CORPUS_URL = "https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t31/relevans-nyckelord.json.zst"
NEARBY_URL = "https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t31/narliggande-yrken.json"
EXPECTED_THIN = 22


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def metric(item: dict[str, Any], key: str) -> float:
    try:
        return float(item.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--training", default="research/training/v31/p80-language-diversity-training-v0.jsonl")
    ap.add_argument("--aggregate", default="research/coverage/v31/derived-af-aggregate.json")
    ap.add_argument("--output", default="research/evaluation/v31/p80-source-thin-evidence-audit.json")
    args = ap.parse_args()

    rows = load_jsonl(Path(args.training))
    thin_rows = [row for row in rows if not g.evidence_rich(row.get("source_evidence") or {})]
    if len(thin_rows) != EXPECTED_THIN:
        raise RuntimeError(f"source-thin P80 drift: {len(thin_rows)} != {EXPECTED_THIN}")
    thin_ids = {str(row["concept_id"]) for row in thin_rows}

    taxonomy_wire = g.fetch_bytes(g.TAXONOMY_URL)
    taxonomy_sha = hashlib.sha256(taxonomy_wire).hexdigest()
    if taxonomy_sha != g.expected_taxonomy_hash():
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(taxonomy_wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    aggregate = json.loads(Path(args.aggregate).read_text(encoding="utf-8"))
    relevant_wire, relevant_raw, relevant_doc = load_json(RELEVANT_URL, compressed=True)
    corpus_wire, corpus_raw, corpus_doc = load_json(CORPUS_URL, compressed=True)
    nearby_wire, nearby_raw, nearby_doc = load_json(NEARBY_URL)
    if hashlib.sha256(relevant_wire).hexdigest() != aggregate["relevant_skills"]["source_wire_sha256"]:
        raise RuntimeError("Relevanta kompetenser source drift")
    if hashlib.sha256(corpus_wire).hexdigest() != aggregate["ad_keyword_corpus"]["source_wire_sha256"]:
        raise RuntimeError("ad keyword source drift")
    if hashlib.sha256(nearby_raw).hexdigest() != aggregate["nearby_occupations"]["source_sha256"]:
        raise RuntimeError("nearby occupation source drift")

    relevant_data = relevant_doc.get("data") or {}
    corpus_occ = (corpus_doc.get("data") or {}).get("occupation_name") or {}
    nearby_data = nearby_doc.get("data") or {}

    job_titles_by_parent: dict[str, list[dict[str, str]]] = {cid: [] for cid in thin_ids}
    for jid, concept in by_id.items():
        if concept.get("type") != "job-title":
            continue
        parents = relation_parent_ids(concept, by_id)
        for parent in parents & thin_ids:
            job_titles_by_parent[parent].append({
                "id": jid,
                "label": str(concept.get("preferred_label") or "").strip(),
            })

    result_rows: list[dict[str, Any]] = []
    for source_row in thin_rows:
        cid = str(source_row["concept_id"])
        evidence = source_row.get("source_evidence") or {}

        rel_record = relevant_data.get(cid) or {}
        rel_items = rel_record.get("relevant_skills") or []
        skills = []
        for item in rel_items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            sid = str(item["id"])
            skills.append({
                "id": sid,
                "label": str(by_id.get(sid, {}).get("preferred_label") or "").strip(),
                "relevance_points": metric(item, "relevance_points"),
            })
        skills.sort(key=lambda x: (-x["relevance_points"], x["label"].casefold(), x["id"]))

        corpus_record = corpus_occ.get(cid) or {}
        kw_map = corpus_record.get("keywords") or {}
        keywords = []
        if isinstance(kw_map, dict):
            for term, metrics in kw_map.items():
                metrics = metrics if isinstance(metrics, dict) else {}
                keywords.append({
                    "term": str(term),
                    "BM25": metric(metrics, "BM25"),
                    "RCA": metric(metrics, "RCA"),
                    "TFIDF": metric(metrics, "TFIDF"),
                    "weighted_frequency": metric(metrics, "weighted_frequency"),
                })
        keywords.sort(key=lambda x: (-x["BM25"], -x["RCA"], x["term"].casefold()))

        titles = sorted(job_titles_by_parent[cid], key=lambda x: (x["label"].casefold(), x["id"]))

        nearby = []
        nrec = nearby_data.get(cid) or {}
        for item in nrec.get("similar") or []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            nid = str(item["id"])
            nearby.append({"id": nid, "label": str(by_id.get(nid, {}).get("preferred_label") or "").strip()})

        direct_signal_count = len(skills) + len(keywords) + len(titles)
        result_rows.append({
            "concept_id": cid,
            "label": source_row.get("label"),
            "p80_rank": source_row.get("p80_rank"),
            "occurrences": source_row.get("occurrences"),
            "canonical_definition_tokens": len(g.tokens(evidence.get("definition"))),
            "direct_source_counts": {
                "relevant_skills": len(skills),
                "ad_keywords": len(keywords),
                "typed_job_titles": len(titles),
                "total": direct_signal_count,
            },
            "top_relevant_skills": skills[:15],
            "top_ad_keywords_bm25": keywords[:20],
            "typed_job_titles": titles[:30],
            "nearby_occupations_diagnostic_only": nearby[:10],
            "candidate_for_source_bound_rescue": bool(len(skills) >= 5 or len(keywords) >= 10 or len(titles) >= 5),
        })

    rescueable = [row for row in result_rows if row["candidate_for_source_bound_rescue"]]
    result = {
        "id": "YV-P80-source-thin-evidence-audit-v0",
        "evidence_class": "source coverage audit; no retrieval outcomes and no opened 17/88",
        "taxonomy_sha256": taxonomy_sha,
        "source_hashes": {
            "relevant_skills_wire_sha256": hashlib.sha256(relevant_wire).hexdigest(),
            "ad_keywords_wire_sha256": hashlib.sha256(corpus_wire).hexdigest(),
            "nearby_occupations_sha256": hashlib.sha256(nearby_raw).hexdigest(),
        },
        "source_thin_concepts": len(result_rows),
        "with_relevant_skills": sum(bool(row["direct_source_counts"]["relevant_skills"]) for row in result_rows),
        "with_ad_keywords": sum(bool(row["direct_source_counts"]["ad_keywords"]) for row in result_rows),
        "with_typed_job_titles": sum(bool(row["direct_source_counts"]["typed_job_titles"]) for row in result_rows),
        "candidate_for_source_bound_rescue": len(rescueable),
        "rescue_rule": ">=5 relevant skills OR >=10 ad keywords OR >=5 typed job-title labels; frozen before retrieval evaluation",
        "rows": result_rows,
        "note": "Nearby occupations are reported only as diagnostic context and are not direct target facts for generation.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("source_thin_concepts", "with_relevant_skills", "with_ad_keywords", "with_typed_job_titles", "candidate_for_source_bound_rescue")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
