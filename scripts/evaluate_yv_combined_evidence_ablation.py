#!/usr/bin/env python3
"""Opened YV description ablation for the smallest single-ranker evidence combination.

The decision question is whether one plain BM25 document per active occupation can use
already accepted provenance-separated evidence without requiring runtime lane fusion.
The representations are:
  C   canonical occupation text only;
  CA  C + AF occupation-linked ad keyword strings;
  CS  C + labels/real definitions of AF Relevanta kompetenser;
  CAS C + both observed ad language and relevant-skill context.

Source authority is not flattened by this experiment: the input fields remain typed and
separate in source/provenance. Only the lexical index document is concatenated. Published
ad/relevance scores are deliberately ignored in this first pass. Yrkesinformation
`work_task` is evaluation-only and target/title surface leakage is excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import zstandard as zstd

from evaluate_c2_job_title_router import build_c1_index, relation_parent_ids
from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, norm, tokens
from evaluate_pareto_c1 import rank_c1
from occupational_information_coverage import find_explicit_taxonomy_ids, record_map

OCC_INFO_URL = (
    "https://data.arbetsformedlingen.se/yrke/yrkesinformation/"
    "yrkesinformation-interimslosning.json"
)


def phrase_present(text: str, surface: str) -> bool:
    haystack = tokens(text)
    needle = tokens(surface)
    if not needle or len(needle) > len(haystack):
        return False
    n = len(needle)
    return any(haystack[i:i+n] == needle for i in range(len(haystack)-n+1))


def metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    n = len(rows)
    hit = sum(isinstance(r[key]["rank"], int) and r[key]["rank"] <= 5 for r in rows)
    top1 = sum(r[key]["rank"] == 1 for r in rows)
    rr = sum(0.0 if r[key]["rank"] is None else 1.0 / int(r[key]["rank"]) for r in rows)
    return {
        "cases": n,
        "top1": round(top1 / n, 6) if n else None,
        "hit_at_5": round(hit / n, 6) if n else None,
        "mrr": round(rr / n, 6) if n else None,
        "nonempty": round(sum(bool(r[key]["top5"]) for r in rows) / n, 6) if n else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--output", default="artifacts/yv-combined-evidence-ablation-v31.json")
    args = ap.parse_args()
    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    ad_url = (
        "https://data.arbetsformedlingen.se/yrke/narliggande-yrken/"
        f"v1/t{version}/relevans-nyckelord.json.zst"
    )
    relevant_url = (
        "https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/"
        f"v1/relevanta-kompetenser-t{version}.json.zst"
    )

    taxonomy_wire = fetch(taxonomy_url)
    occ_wire = fetch(OCC_INFO_URL)
    ad_wire = fetch(ad_url)
    relevant_wire = fetch(relevant_url)
    hashes = {
        "taxonomy": hashlib.sha256(taxonomy_wire).hexdigest(),
        "occupational_information": hashlib.sha256(occ_wire).hexdigest(),
        "ad_keywords": hashlib.sha256(ad_wire).hexdigest(),
        "relevant_skills": hashlib.sha256(relevant_wire).hexdigest(),
    }
    checks = {
        "taxonomy": expected_hash(registry, "taxonomy-common-relations"),
        "occupational_information": expected_hash(registry, "occupational-information"),
        "ad_keywords": expected_hash(registry, "ad-keyword-corpus"),
        "relevant_skills": expected_hash(registry, "relevant-skills"),
    }
    for name, actual in hashes.items():
        if actual != checks[name]:
            raise RuntimeError(f"{name} source drift: {actual}")

    taxonomy = json.loads(taxonomy_wire)
    occ_info = json.loads(occ_wire)
    ad_doc = json.loads(zstd.ZstdDecompressor().decompress(ad_wire))
    relevant_doc = json.loads(zstd.ZstdDecompressor().decompress(relevant_wire))

    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active_occ = {cid for cid,c in by_id.items() if c.get("type") == "occupation-name"}
    active_skills = {cid for cid,c in by_id.items() if c.get("type") == "skill"}
    if len(active_occ) != 2105 or len(active_skills) != 6752:
        raise RuntimeError("active target universe drift")
    ids = sorted(active_occ)

    canonical_ranker, exact, surface_tokens = build_c1_index(by_id, ids)
    canonical_docs = {cid: list(canonical_ranker.documents[cid]) for cid in ids}

    ad_occ = ad_doc.get("data", {}).get("occupation_name")
    if not isinstance(ad_occ, dict) or set(ad_occ) - active_occ:
        raise RuntimeError("invalid ad occupation universe")
    ad_tokens: dict[str, list[str]] = {cid: [] for cid in ids}
    distinct_ad_terms: set[str] = set()
    for cid, rec in ad_occ.items():
        kws = rec.get("keywords") if isinstance(rec, dict) else None
        if not isinstance(kws, dict):
            raise RuntimeError(f"invalid ad keywords: {cid}")
        terms = [str(x) for x in kws]
        distinct_ad_terms.update(terms)
        ad_tokens[cid] = tokens(" ".join(terms))
    if len(ad_occ) != 1051 or len(distinct_ad_terms) != 11085:
        raise RuntimeError("ad coverage drift")

    relevant = relevant_doc.get("data")
    if not isinstance(relevant, dict) or set(relevant) != active_occ:
        raise RuntimeError("invalid Relevanta occupation universe")
    skill_tokens: dict[str, list[str]] = {}
    unique_skill_ids: set[str] = set()
    for cid in ids:
        rec = relevant[cid]
        items = rec.get("relevant_skills") if isinstance(rec, dict) else None
        if not isinstance(items, list):
            raise RuntimeError(f"invalid relevant skills: {cid}")
        parts: list[str] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            sid = str(item["id"])
            if sid not in active_skills:
                raise RuntimeError(f"non-active relevant skill: {sid}")
            if sid in seen:
                continue
            seen.add(sid)
            unique_skill_ids.add(sid)
            skill = by_id[sid]
            label = str(skill.get("preferred_label") or "").strip()
            definition = str(skill.get("definition") or "").strip()
            if label:
                parts.append(label)
            if definition and norm(definition) != norm(label):
                parts.append(definition)
        skill_tokens[cid] = tokens(" ".join(parts))
    if len(unique_skill_ids) != 4685:
        raise RuntimeError("relevant skill coverage drift")

    no_exact = {cid: set(exact[cid]) for cid in ids}
    docs = {
        "canonical_2105": canonical_docs,
        "canonical_plus_ad": {cid: canonical_docs[cid] + ad_tokens[cid] for cid in ids},
        "canonical_plus_skills": {cid: canonical_docs[cid] + skill_tokens[cid] for cid in ids},
        "canonical_plus_ad_plus_skills": {
            cid: canonical_docs[cid] + ad_tokens[cid] + skill_tokens[cid] for cid in ids
        },
    }
    rankers = {name: BM25(doc, no_exact) for name, doc in docs.items()}

    all_ids = set(by_id)
    records = record_map(occ_info.get("data"))
    meta = occ_info.get("metadata")
    occupations_meta = meta.get("occupations") if isinstance(meta, dict) else None
    if not isinstance(occupations_meta, list):
        raise RuntimeError("Yrkesinformation missing metadata.occupations")

    job_title_surfaces: dict[str, set[str]] = defaultdict(set)
    for concept in by_id.values():
        if concept.get("type") != "job-title":
            continue
        label = str(concept.get("preferred_label") or "").strip()
        if not label:
            continue
        for parent in relation_parent_ids(concept, by_id):
            job_title_surfaces[parent].add(label)

    rows: list[dict[str, Any]] = []
    excluded: dict[str, int] = defaultdict(int)
    for m in occupations_meta:
        if not isinstance(m, dict):
            continue
        slug = str(m.get("slug") or "")
        record = records.get(slug)
        if not isinstance(record, dict):
            excluded["missing_record"] += 1
            continue
        explicit = find_explicit_taxonomy_ids(record, all_ids) & active_occ
        if len(explicit) != 1:
            excluded["not_unique_explicit_active_occupation"] += 1
            continue
        target = next(iter(explicit))
        query = str(record.get("work_task") or "").strip()
        if len(query) < 40:
            excluded["work_task_too_short"] += 1
            continue
        concept = by_id[target]
        surfaces = {
            str(concept.get("preferred_label") or ""),
            *as_list(concept.get("alternative_labels")),
            *job_title_surfaces.get(target, set()),
        }
        if any(s and phrase_present(query, s) for s in surfaces):
            excluded["contains_target_or_job_title_surface"] += 1
            continue

        row: dict[str, Any] = {
            "source_slug": slug,
            "target_id": target,
            "target_label": concept.get("preferred_label"),
            "target_has_real_definition": (
                bool(norm(concept.get("definition")))
                and norm(concept.get("definition")) != norm(concept.get("preferred_label"))
            ),
            "target_has_ad_language": target in ad_occ,
            "target_relevant_skill_count": len(relevant[target].get("relevant_skills", [])),
            "query": query,
        }
        for name, ranker in rankers.items():
            scored = rank_c1(ranker, query, exact, surface_tokens)
            ranked = [cid for cid,_,_ in scored]
            row[name] = {
                "rank": ranked.index(target)+1 if target in ranked else None,
                "top5": ranked[:5],
            }
        rows.append(row)

    if not rows:
        raise RuntimeError("no leak-free cases")
    text_poor = [r for r in rows if not r["target_has_real_definition"]]
    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "status": "opened_source_attested_development_ablation_not_human_validation",
        "decision_question": "can one unweighted BM25 evidence document avoid runtime lane fusion while retaining complementary recall",
        "representations": {
            "canonical_2105": "canonical occupation label + real definition + canonical alternatives",
            "canonical_plus_ad": "canonical + one textual occurrence of each AF occupation-linked ad keyword",
            "canonical_plus_skills": "canonical + labels/real definitions of AF Relevanta kompetenser",
            "canonical_plus_ad_plus_skills": "canonical + both provenance-separated evidence families concatenated at index build time",
        },
        "non_claims": [
            "concatenated evidence becomes canonical definition or synonymy",
            "published ad/relevance scores are calibrated retrieval weights",
            "opened Yrkesinformation cases are independent human validation",
        ],
        "source_sha256": hashes,
        "case_count": len(rows),
        "metrics": {
            "all": {name: metrics(rows, name) for name in rankers},
            "targets_without_real_canonical_definition": {
                "cases": len(text_poor),
                **{name: metrics(text_poor, name) for name in rankers},
            },
        },
        "excluded": dict(sorted(excluded.items())),
        "cases": rows,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({"cases": len(rows), "metrics": result["metrics"], "output": str(out)}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
