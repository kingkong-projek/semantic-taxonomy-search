#!/usr/bin/env python3
"""Adjudicate the untouched 36-row Pareto holdout without using C0/C1 output.

Judgments use only the frozen behavioral row, canonical taxonomy context and pinned
YV routing relations. They are explicitly MODEL_ADJUDICATED/model_judgment, not source
truth or human review. The script must run before any holdout retrieval evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

UA = "semantic-taxonomy-search-holdout-adjudication/0.1"
MODEL_SOURCE = "GPT-5.6 Sol holdout model adjudication 2026-09-06"

GEO = {
    "halmstad", "kalmar", "eskilstuna", "örebro län", "kristianstad", "helsingborg",
    "gävle", "borås", "jönköpings län", "växjö", "östersund", "skåne",
    "örnsköldsvik", "trollhättan", "uddevalla", "nyköping", "karlskrona", "varberg", "piteå",
}

SINGLE_EXCLUDED = {
    "lagermedarbetare": "DLEi_bTh_oLA",
    "adjunkt": "YfCD_kUE_kck",
}


def norm(x: Any) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip().casefold()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=240) as r:
        return r.read()


def expected_hash(registry: dict[str, Any], adapter_id: str) -> str:
    xs = [a for a in registry["adapters"] if a.get("id") == adapter_id]
    if len(xs) != 1:
        raise RuntimeError(f"adapter lookup drift: {adapter_id}")
    return str(xs[0]["source_sha256"])


def identity(by_id: dict[str, dict[str, Any]], cid: str) -> dict[str, str]:
    c = by_id.get(cid)
    if not isinstance(c, dict) or c.get("type") != "occupation-name":
        raise RuntimeError(f"invalid occupation identity {cid}")
    return {"kind": "occupation-name", "concept_id": cid, "label": str(c.get("preferred_label") or "")}


def ids_to_identities(by_id: dict[str, dict[str, Any]], ids: set[str] | list[str]) -> list[dict[str, str]]:
    return [identity(by_id, cid) for cid in sorted(set(ids), key=lambda x: (norm(by_id[x].get("preferred_label")), x))]


def evidence(query_source: str, model_note: str, *, positive: bool, excluded: bool) -> list[dict[str, str]]:
    out = [
        {
            "source": query_source,
            "provenance": "canonical" if excluded else "behavioral",
            "role": "query_origin",
            "note": "Exact active job-title wording used only as retrieval vocabulary." if excluded else "Observed free-text plus aggregate frequency; no selected-ID ground truth.",
        },
    ]
    if excluded:
        out.append({
            "source": "JobTech Taxonomy v31 typed job-title→occupation relations",
            "provenance": "curated_relation",
            "role": "context_only",
            "note": "Typed parent occupations constrain plausible routing but do not prove user intent.",
        })
    out.append({
        "source": MODEL_SOURCE,
        "provenance": "model_judgment",
        "role": "destination_ground_truth",
        "note": model_note,
    })
    if positive:
        out.extend([
            {
                "source": "JobTech Taxonomy v31",
                "provenance": "canonical",
                "role": "context_only",
                "note": "Judged identities are validated active occupation-name concepts.",
            },
            {
                "source": "Published Yrkesväljaren v31",
                "provenance": "behavioral",
                "role": "product_admission",
                "note": "Occupation-name identities are admitted by the YV reference profile; YV does not define generic-engine scope.",
            },
        ])
    return out


def make_case(index: int, row: dict[str, Any], intent: str, must: list[dict[str, Any]], acceptable: list[dict[str, Any]],
              must_not: list[dict[str, Any]], strata: list[str], rationale: str, confidence: str) -> dict[str, Any]:
    excluded = row["source_pool"] == "yv_excluded_title_routing"
    return {
        "id": f"yv.model-holdout.{index:03d}",
        "taxonomy_version": 31,
        "product": "YV",
        "query": row["query"],
        "query_language": "sv",
        "query_origin": "canonical_label" if excluded else "observed_query",
        "strata": sorted(set(strata)),
        "expected_intent": intent,
        "must": must,
        "acceptable": acceptable,
        "must_not": must_not,
        "top_k": 10,
        "allow_abstention": intent == "NO_MATCH",
        "source_evidence": evidence(
            "JobTech Taxonomy v31 job-title preferred label" if excluded else "Pinned Yrkesväljaren/Platsbanken observed-query corpus",
            rationale,
            positive=intent != "NO_MATCH",
            excluded=excluded,
        ),
        "rationale": rationale,
        "notes": f"Observed count in source review pool: {int(row['observed_count'])}. Pareto rank: {int(row['pareto_rank'])}. Model-judgment confidence: {confidence}.",
        "adjudication": {
            "status": "MODEL_ADJUDICATED",
            "reviewer_count": 0,
            "agreement": "UNREVIEWED",
            "review_note": f"confidence={confidence}; holdout judgment made without C0/C1 output",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout", required=True)
    ap.add_argument("--context", required=True)
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--output-dir", default="artifacts/pareto-holdout-adjudicated-v31")
    args = ap.parse_args()

    rows = read_jsonl(Path(args.holdout))
    ctx = json.loads(Path(args.context).read_text(encoding="utf-8"))
    if len(rows) != 36 or rows[0].get("pareto_rank") != 35 or rows[-1].get("pareto_rank") != 70:
        raise RuntimeError("holdout split drift")
    if ctx.get("authority_boundary") != "context only; no relevance labels inferred":
        raise RuntimeError("adjudication context authority boundary drift")
    ctx_by_source = {str(r["source_id"]): r for r in ctx["rows"]}

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    taxonomy_url = "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json"
    body = fetch(taxonomy_url)
    actual = hashlib.sha256(body).hexdigest()
    expected = expected_hash(registry, "taxonomy-common-relations")
    if actual != expected or actual != ctx.get("taxonomy_sha256"):
        raise RuntimeError("taxonomy/context source drift")
    concepts = json.loads(body).get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    cases: list[dict[str, Any]] = []
    intent_counts = {"SINGLE": 0, "AMBIGUOUS": 0, "NO_MATCH": 0}
    pool_counts = {"observed_unbound_query": 0, "yv_excluded_title_routing": 0}

    for index, row in enumerate(rows, 1):
        q = norm(row["query"])
        pool = str(row["source_pool"])
        pool_counts[pool] += 1

        if pool == "observed_unbound_query":
            context = ctx_by_source.get(str(row["source_id"]), {})
            if q in GEO:
                must_not = [
                    identity(by_id, str(x["concept_id"]))
                    for x in row.get("candidate_context", {}).get("top5", [])
                    if str(x.get("concept_id") or "") in by_id
                ]
                case = make_case(index, row, "NO_MATCH", [], [], must_not,
                                 ["yv_unbound_observed_query", "no_valid_match", "hard_negative"],
                                 "The query is a Swedish place/region name, not an occupation expression; occupation retrieval should abstain.", "HIGH")
            elif q == "sommarjobb":
                case = make_case(index, row, "NO_MATCH", [], [], [],
                                 ["yv_unbound_observed_query", "no_valid_match"],
                                 "Sommarjobb describes employment timing/type rather than an occupation identity; occupation retrieval should abstain without occupational context.", "HIGH")
            elif q == "lager":
                ids = {str(x["concept_id"]) for x in context.get("occupation_surface_hits", [])}
                if ids != {"ebKB_MDe_9pQ", "GLp9_DyP_gHJ", "zXv9_zv2_VUs", "DLEi_bTh_oLA", "c4S8_tmV_fJW"}:
                    raise RuntimeError(f"lager context drift: {ids}")
                case = make_case(index, row, "AMBIGUOUS", [], ids_to_identities(by_id, ids), [],
                                 ["yv_unbound_observed_query", "broad_or_underspecified"],
                                 "The bare domain word 'lager' can reasonably denote warehouse work, planning, administration, supervision or management; no single occupation is justified.", "HIGH")
            elif q == "handläggare":
                ids = {str(x["concept_id"]) for x in context.get("occupation_surface_hits", [])}
                if len(ids) < 20 or "YG1s_tUg_jWJ" not in ids:
                    raise RuntimeError(f"handläggare context drift: {len(ids)}")
                case = make_case(index, row, "AMBIGUOUS", [], ids_to_identities(by_id, ids), [],
                                 ["yv_unbound_observed_query", "broad_or_underspecified"],
                                 "The unspecialised title 'handläggare' spans many canonical handläggare occupations; further domain context is required.", "HIGH")
            elif q == "administration":
                case = make_case(index, row, "SINGLE", [identity(by_id, "soBq_ia8_xcx")], [], [],
                                 ["yv_unbound_observed_query", "colloquial"],
                                 "When an occupation selector receives the generic work-area noun 'administration', the direct canonical occupation Administratör is the strongest justified destination; managerial/specialist variants require extra wording.", "MEDIUM")
            else:
                raise RuntimeError(f"unhandled observed holdout query: {row['query']!r}")
        else:
            parents = {str(x["concept_id"]) for x in row.get("candidate_occupation_identities", [])}
            if not parents:
                raise RuntimeError(f"excluded row has no typed parents: {row['query']}")
            if q in SINGLE_EXCLUDED:
                cid = SINGLE_EXCLUDED[q]
                if cid not in parents:
                    raise RuntimeError(f"single excluded target absent from parent context: {row['query']}")
                rationale = (
                    "Lagermedarbetare most directly denotes the canonical Lagerarbetare/Terminalarbetare; planning/administrative parent relations are contextual alternatives rather than the ordinary title meaning."
                    if q == "lagermedarbetare" else
                    "Adjunkt has one typed occupation parent in the pinned taxonomy context: Universitets- och högskoleadjunkt."
                )
                case = make_case(index, row, "SINGLE", [identity(by_id, cid)], [], [],
                                 ["yv_excluded_title_router"], rationale, "HIGH")
            else:
                case = make_case(index, row, "AMBIGUOUS", [], ids_to_identities(by_id, parents), [],
                                 ["yv_excluded_title_router", "broad_or_underspecified"],
                                 f"The generic excluded job-title wording {row['query']!r} has multiple typed occupation contexts and lacks enough information to select one safely.", "HIGH")

        intent_counts[case["expected_intent"]] += 1
        cases.append(case)

    if intent_counts != {"SINGLE": 3, "AMBIGUOUS": 13, "NO_MATCH": 20}:
        raise RuntimeError(f"unexpected holdout intent counts: {intent_counts}")

    observed_volume = sum(int(r["observed_count"]) for r in rows)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "benchmark.jsonl").open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
    manifest = {
        "schema_version": 1,
        "taxonomy_version": 31,
        "status": "MODEL_ADJUDICATED_HOLDOUT",
        "cases": len(cases),
        "observed_volume": observed_volume,
        "intent_counts": intent_counts,
        "source_pool_counts": pool_counts,
        "pareto_ranks": [35, 70],
        "judgment_source": MODEL_SOURCE,
        "taxonomy_sha256": actual,
        "leakage_boundary": "judgments use frozen query/routing rows plus taxonomy-only context; no C0/C1 retrieval output was consulted before adjudication",
        "authority_boundary": "model_judgment is benchmark evaluation provenance only; it is neither canonical taxonomy authority nor human review",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
