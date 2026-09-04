#!/usr/bin/env python3
"""Measure semantic coverage from AF-derived v31 sources.

Sources kept distinct by provenance:
- Relevanta kompetenser: derived occupation→skill relevance with scores.
- Kompetensväljaren: published typed occupation→skill context used only for
  overlap/delta analysis; its layer semantics remain separate.
- Närliggande yrken relevans-nyckelord: corpus-derived employer language from
  historical ads, tied to occupation-name/SSYK4 contexts.
- Närliggande yrken: filtered occupation similarity, measured as a separate
  contextual/discovery signal rather than synonymy.

No source is promoted to canonical truth. All taxonomy IDs are validated against
the same immutable active v31 snapshot.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import statistics
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import zstandard as zstd

USER_AGENT = "semantic-taxonomy-search-derived-af-coverage/0.1"
KV_LAYERS = ("regulated_skills", "essential_skills", "optional_skills", "calculated_skills")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch(url: str, timeout: int = 240) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "*/*", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def load_json(url: str, compressed: bool = False) -> tuple[bytes, bytes, Any]:
    wire = fetch(url)
    raw = zstd.ZstdDecompressor().decompress(wire) if compressed else wire
    return wire, raw, json.loads(raw)


def pct(n: int, d: int) -> float | None:
    return None if not d else round(100.0 * n / d, 3)


def number_stats(values: list[float | int]) -> dict[str, float | int | None]:
    if not values:
        return {"min": None, "median": None, "mean": None, "max": None}
    numeric = [float(v) for v in values]
    return {
        "min": min(numeric),
        "median": statistics.median(numeric),
        "mean": round(statistics.fmean(numeric), 3),
        "max": max(numeric),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31")
    parser.add_argument("--output-dir", default="artifacts/derived-af-coverage-v31")
    args = parser.parse_args()

    version = str(args.version)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    relevant_url = f"https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/v1/relevanta-kompetenser-t{version}.json.zst"
    kv_url = f"https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t{version}.json"
    corpus_url = f"https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t{version}/relevans-nyckelord.json.zst"
    nearby_url = f"https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t{version}/narliggande-yrken.json"

    taxonomy_wire, taxonomy_raw, taxonomy_doc = load_json(taxonomy_url)
    relevant_wire, relevant_raw, relevant_doc = load_json(relevant_url, compressed=True)
    kv_wire, kv_raw, kv_doc = load_json(kv_url)
    corpus_wire, corpus_raw, corpus_doc = load_json(corpus_url, compressed=True)
    nearby_wire, nearby_raw, nearby_doc = load_json(nearby_url)

    concepts = taxonomy_doc.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy snapshot missing data.concepts")
    by_id = {str(c.get("id")): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids_by_type: dict[str, set[str]] = defaultdict(set)
    for cid, concept in by_id.items():
        ids_by_type[str(concept.get("type") or "")].add(cid)
    active_occupations = ids_by_type.get("occupation-name", set())
    active_skills = ids_by_type.get("skill", set())
    active_ssyk4 = ids_by_type.get("ssyk-level-4", set())

    # -------------------------------------------------- Relevanta kompetenser
    relevant_data = relevant_doc.get("data")
    if not isinstance(relevant_data, dict):
        raise RuntimeError("Relevanta kompetenser missing data object")

    relevant_occ_ids = set(relevant_data.keys())
    relevant_skill_ids: set[str] = set()
    relevant_edges = 0
    relevant_count_per_occ: list[int] = []
    relevance_points: list[float] = []
    capped_30 = 0
    relevant_unknown_occ: list[str] = []
    relevant_unknown_skills: list[dict[str, str]] = []
    relevant_wrong_skill_types: list[dict[str, str]] = []
    relevant_by_occ: dict[str, set[str]] = {}

    for occ_id, record in relevant_data.items():
        if occ_id not in active_occupations:
            relevant_unknown_occ.append(occ_id)
        if not isinstance(record, dict):
            raise RuntimeError(f"Relevanta kompetenser record {occ_id} is not an object")
        items = record.get("relevant_skills") or []
        if not isinstance(items, list):
            raise RuntimeError(f"Relevanta kompetenser relevant_skills for {occ_id} is not a list")
        relevant_count_per_occ.append(len(items))
        if len(items) == 30:
            capped_30 += 1
        local: set[str] = set()
        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            sid = str(item["id"])
            local.add(sid)
            relevant_skill_ids.add(sid)
            relevant_edges += 1
            try:
                relevance_points.append(float(item.get("relevance_points")))
            except (TypeError, ValueError):
                pass
            canonical = by_id.get(sid)
            if canonical is None:
                relevant_unknown_skills.append({"occupation_id": occ_id, "skill_id": sid})
            elif canonical.get("type") != "skill":
                relevant_wrong_skill_types.append({"occupation_id": occ_id, "skill_id": sid, "type": str(canonical.get("type"))})
        relevant_by_occ[occ_id] = local

    # -------------------------------------------------------------- KV overlap
    kv_data = kv_doc.get("data")
    if not isinstance(kv_data, dict):
        raise RuntimeError("KV missing data object")
    kv_layer_ids: dict[str, set[str]] = {layer: set() for layer in KV_LAYERS}
    kv_union: set[str] = set()
    kv_by_occ: dict[str, set[str]] = {}

    transferable = kv_data.get("transferable_skills") or {}
    transferable_ids = {
        str(v) for v in transferable.values()
        if isinstance(transferable, dict) and str(v) in active_skills
    }

    for key, record in kv_data.items():
        if key == "transferable_skills" or not isinstance(record, dict) or record.get("type") != "occupation-name":
            continue
        local: set[str] = set()
        for layer in KV_LAYERS:
            mapping = record.get(layer) or {}
            if not isinstance(mapping, dict):
                raise RuntimeError(f"KV {layer} for {key} is not an object")
            ids = {str(v) for v in mapping.values() if str(v) in active_skills}
            kv_layer_ids[layer].update(ids)
            kv_union.update(ids)
            local.update(ids)
        kv_by_occ[key] = local

    relevant_overlap_layers = {}
    for layer in KV_LAYERS:
        overlap = relevant_skill_ids & kv_layer_ids[layer]
        relevant_overlap_layers[layer] = {
            "kv_unique_skills": len(kv_layer_ids[layer]),
            "overlap_unique_skills": len(overlap),
            "relevant_skill_overlap_pct": pct(len(overlap), len(relevant_skill_ids)),
        }

    relevant_only_vs_kv = relevant_skill_ids - kv_union
    kv_only_vs_relevant = kv_union - relevant_skill_ids
    combined_relevant_kv = relevant_skill_ids | kv_union
    relevant_only_vs_kv_plus_transferable = relevant_skill_ids - (kv_union | transferable_ids)

    occ_overlap_counts: list[int] = []
    occ_relevant_only_counts: list[int] = []
    occ_jaccards: list[float] = []
    for occ_id in active_occupations:
        rset = relevant_by_occ.get(occ_id, set())
        kset = kv_by_occ.get(occ_id, set())
        overlap = rset & kset
        union = rset | kset
        occ_overlap_counts.append(len(overlap))
        occ_relevant_only_counts.append(len(rset - kset))
        if union:
            occ_jaccards.append(len(overlap) / len(union))

    # ---------------------------------------------- ad-derived keyword corpus
    corpus_data = corpus_doc.get("data")
    if not isinstance(corpus_data, dict):
        raise RuntimeError("relevans-nyckelord missing data object")
    corpus_occ = corpus_data.get("occupation_name") or {}
    corpus_ssyk = corpus_data.get("ssyk_level_4") or {}
    if not isinstance(corpus_occ, dict) or not isinstance(corpus_ssyk, dict):
        raise RuntimeError("relevans-nyckelord context spaces have unexpected schema")

    corpus_occ_ids = set(corpus_occ.keys())
    corpus_ssyk_ids = set(corpus_ssyk.keys())
    corpus_unknown_occ = sorted(corpus_occ_ids - active_occupations)
    corpus_unknown_ssyk = sorted(corpus_ssyk_ids - active_ssyk4)
    corpus_keyword_counts: list[int] = []
    corpus_ad_counts: list[int] = []
    distinct_terms: set[str] = set()
    terms_with_metrics = Counter()
    label_copy_occupations = {
        cid for cid in active_occupations
        if str(by_id[cid].get("definition") or "").strip().casefold()
        == str(by_id[cid].get("preferred_label") or "").strip().casefold()
    }
    label_copy_with_corpus = label_copy_occupations & corpus_occ_ids

    for occ_id, record in corpus_occ.items():
        if not isinstance(record, dict):
            continue
        keywords = record.get("keywords") or {}
        if not isinstance(keywords, dict):
            raise RuntimeError(f"corpus keywords for {occ_id} is not an object")
        corpus_keyword_counts.append(len(keywords))
        try:
            corpus_ad_counts.append(int(record.get("number_of_ads")))
        except (TypeError, ValueError):
            pass
        for term, metrics in keywords.items():
            distinct_terms.add(str(term))
            if isinstance(metrics, dict):
                for metric in ("weighted_frequency", "TFIDF", "BM25", "RCA"):
                    if metric in metrics:
                        terms_with_metrics[metric] += 1

    corpus_metadata = corpus_doc.get("metadata") or {}

    # -------------------------------------------------- nearby occupations view
    nearby_data = nearby_doc.get("data")
    if not isinstance(nearby_data, dict):
        raise RuntimeError("narliggande-yrken missing data object")
    nearby_source_ids = set(nearby_data.keys())
    nearby_unknown_sources = sorted(nearby_source_ids - active_occupations)
    nearby_edges = 0
    nearby_target_ids: set[str] = set()
    nearby_unknown_targets: list[dict[str, str]] = []
    nearby_counts: list[int] = []
    for source_id, record in nearby_data.items():
        if not isinstance(record, dict):
            continue
        similar = record.get("similar") or []
        if not isinstance(similar, list):
            raise RuntimeError(f"nearby similar for {source_id} is not a list")
        nearby_counts.append(len(similar))
        for item in similar:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            tid = str(item["id"])
            nearby_edges += 1
            nearby_target_ids.add(tid)
            if tid not in active_occupations:
                nearby_unknown_targets.append({"source_id": source_id, "target_id": tid})

    aggregate = {
        "schema_version": 1,
        "taxonomy_version": version,
        "generated_at": now_utc(),
        "sources": {
            "taxonomy": {"url": taxonomy_url, "wire_bytes": len(taxonomy_wire), "sha256": hashlib.sha256(taxonomy_raw).hexdigest()},
            "relevant_skills": {"url": relevant_url, "wire_bytes": len(relevant_wire), "wire_sha256": hashlib.sha256(relevant_wire).hexdigest(), "json_bytes": len(relevant_raw), "json_sha256": hashlib.sha256(relevant_raw).hexdigest()},
            "kompetensvaljaren": {"url": kv_url, "bytes": len(kv_raw), "sha256": hashlib.sha256(kv_raw).hexdigest()},
            "ad_keywords": {"url": corpus_url, "wire_bytes": len(corpus_wire), "wire_sha256": hashlib.sha256(corpus_wire).hexdigest(), "json_bytes": len(corpus_raw), "json_sha256": hashlib.sha256(corpus_raw).hexdigest()},
            "nearby_occupations": {"url": nearby_url, "bytes": len(nearby_raw), "sha256": hashlib.sha256(nearby_raw).hexdigest()},
        },
        "relevant_skills": {
            "occupation_records": len(relevant_occ_ids),
            "active_occupation_coverage_pct": pct(len(relevant_occ_ids & active_occupations), len(active_occupations)),
            "unknown_occupation_ids": len(relevant_unknown_occ),
            "edge_occurrences": relevant_edges,
            "unique_skill_ids": len(relevant_skill_ids),
            "active_skill_coverage_pct": pct(len(relevant_skill_ids & active_skills), len(active_skills)),
            "unknown_skill_ref_occurrences": len(relevant_unknown_skills),
            "wrong_skill_type_occurrences": len(relevant_wrong_skill_types),
            "skills_per_occupation": number_stats(relevant_count_per_occ),
            "occupations_with_exactly_30_skills": capped_30,
            "relevance_points": number_stats(relevance_points),
            "overlap_with_kv_layers": relevant_overlap_layers,
            "overlap_with_kv_union": len(relevant_skill_ids & kv_union),
            "unique_skills_not_in_kv_union": len(relevant_only_vs_kv),
            "unique_skills_not_in_kv_union_or_transferable": len(relevant_only_vs_kv_plus_transferable),
            "kv_unique_skills_not_in_relevant": len(kv_only_vs_relevant),
            "combined_unique_skills_relevant_plus_kv": len(combined_relevant_kv),
            "combined_active_skill_coverage_pct": pct(len(combined_relevant_kv & active_skills), len(active_skills)),
            "per_occupation_overlap_count": number_stats(occ_overlap_counts),
            "per_occupation_relevant_only_count": number_stats(occ_relevant_only_counts),
            "per_occupation_jaccard": number_stats(occ_jaccards),
        },
        "ad_keyword_corpus": {
            "occupation_records": len(corpus_occ_ids),
            "active_occupation_coverage_pct": pct(len(corpus_occ_ids & active_occupations), len(active_occupations)),
            "unknown_occupation_ids": len(corpus_unknown_occ),
            "ssyk4_records": len(corpus_ssyk_ids),
            "active_ssyk4_coverage_pct": pct(len(corpus_ssyk_ids & active_ssyk4), len(active_ssyk4)),
            "unknown_ssyk4_ids": len(corpus_unknown_ssyk),
            "keywords_per_occupation": number_stats(corpus_keyword_counts),
            "ads_per_occupation": number_stats(corpus_ad_counts),
            "distinct_keyword_strings": len(distinct_terms),
            "metric_occurrences": dict(terms_with_metrics),
            "label_copy_definition_occupations": len(label_copy_occupations),
            "label_copy_definition_with_ad_keywords": len(label_copy_with_corpus),
            "label_copy_definition_with_ad_keywords_pct": pct(len(label_copy_with_corpus), len(label_copy_occupations)),
            "metadata": {
                "years_added_historical_ads": corpus_metadata.get("years_added_historical_ads"),
                "total_number_of_ads": corpus_metadata.get("total_number_of_ads"),
                "total_number_of_enriched_ads": corpus_metadata.get("total_number_of_enriched_ads"),
                "data_created": corpus_metadata.get("data_created"),
            },
        },
        "nearby_occupations": {
            "source_records": len(nearby_source_ids),
            "active_occupation_source_coverage_pct": pct(len(nearby_source_ids & active_occupations), len(active_occupations)),
            "unknown_source_ids": len(nearby_unknown_sources),
            "edge_occurrences": nearby_edges,
            "unique_target_ids": len(nearby_target_ids),
            "unknown_target_occurrences": len(nearby_unknown_targets),
            "neighbours_per_source": number_stats(nearby_counts),
        },
    }

    (out / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "relevant-vs-kv-delta.json").write_text(json.dumps({
        "relevant_only_vs_kv": sorted(relevant_only_vs_kv),
        "relevant_only_vs_kv_plus_transferable": sorted(relevant_only_vs_kv_plus_transferable),
        "kv_only_vs_relevant": sorted(kv_only_vs_relevant),
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "anomalies.json").write_text(json.dumps({
        "relevant_unknown_occupations": sorted(relevant_unknown_occ),
        "relevant_unknown_skill_refs": relevant_unknown_skills,
        "relevant_wrong_skill_types": relevant_wrong_skill_types,
        "corpus_unknown_occupations": corpus_unknown_occ,
        "corpus_unknown_ssyk4": corpus_unknown_ssyk,
        "nearby_unknown_sources": nearby_unknown_sources,
        "nearby_unknown_targets": nearby_unknown_targets,
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rel = aggregate["relevant_skills"]
    corp = aggregate["ad_keyword_corpus"]
    near = aggregate["nearby_occupations"]
    lines = [
        f"# AF-derived semantic coverage — taxonomy v{version}",
        "",
        "## Relevanta kompetenser",
        "",
        f"Occupation coverage: **{rel['occupation_records']:,}** records / **{len(active_occupations):,}** active occupations = **{rel['active_occupation_coverage_pct']}%**.",
        f"Unique active skill IDs: **{rel['unique_skill_ids']:,}** = **{rel['active_skill_coverage_pct']}%** of active skills.",
        f"Edge occurrences: **{rel['edge_occurrences']:,}**.",
        f"Occupations with exactly 30 returned skills: **{rel['occupations_with_exactly_30_skills']:,}**.",
        "",
        "### Delta vs Kompetensväljaren",
        "",
        f"Unique Relevanta-kompetenser skills also in ordinary KV layers: **{rel['overlap_with_kv_union']:,}**.",
        f"Unique skills added beyond ordinary KV layers: **{rel['unique_skills_not_in_kv_union']:,}**.",
        f"Still added beyond KV ordinary + transferable: **{rel['unique_skills_not_in_kv_union_or_transferable']:,}**.",
        f"Combined Relevanta + ordinary KV union: **{rel['combined_unique_skills_relevant_plus_kv']:,}** active skills = **{rel['combined_active_skill_coverage_pct']}%**.",
        "",
        "## Ad-derived employer-language keywords",
        "",
        f"Occupation records: **{corp['occupation_records']:,}** = **{corp['active_occupation_coverage_pct']}%** of active occupations.",
        f"SSYK4 records: **{corp['ssyk4_records']:,}** = **{corp['active_ssyk4_coverage_pct']}%** of active SSYK4.",
        f"Distinct keyword strings: **{corp['distinct_keyword_strings']:,}**.",
        f"Label-copy-definition occupations rescued with ad keywords: **{corp['label_copy_definition_with_ad_keywords']:,} / {corp['label_copy_definition_occupations']:,} = {corp['label_copy_definition_with_ad_keywords_pct']}%**.",
        f"Source metadata total ads: **{corp['metadata']['total_number_of_ads']}**; enriched ads: **{corp['metadata']['total_number_of_enriched_ads']}**.",
        "",
        "## Nearby occupations",
        "",
        f"Source occupation records: **{near['source_records']:,}** = **{near['active_occupation_source_coverage_pct']}%** of active occupations.",
        f"Similarity edges: **{near['edge_occurrences']:,}** to **{near['unique_target_ids']:,}** unique occupation IDs.",
        "",
        "## Guardrails",
        "",
        "- Relevance points are source-specific derived scores, not requirement/essentiality truth.",
        "- KV layer scores/labels and Relevanta-kompetenser relevance points are not assumed numerically comparable.",
        "- Ad keywords are corpus-derived employer language and can contain generic/noisy terms; their presence is retrieval evidence, not a canonical definition.",
        "- Nearby occupations are discovery/similarity evidence, not synonymy or proof of career suitability.",
        "",
    ]
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
