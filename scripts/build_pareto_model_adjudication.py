#!/usr/bin/env python3
"""Create the first model-adjudicated Pareto occupation benchmark slice.

The source populations and their observed frequencies are already frozen. This script
adds explicit model judgment only where source truth cannot decide user intent. The
judgment remains a separate provenance class and can later be audited by a domain
expert without changing the underlying observations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

UA = "semantic-taxonomy-search-pareto-model-adjudication/0.1"
MODEL_JUDGMENT_SOURCE = "GPT-5.6 Sol model adjudication 2026-09-06"

GEO_QUERIES = {
    "stockholms län", "göteborg", "stockholm", "umeå", "skåne län", "malmö",
    "örebro", "västra götalands län", "västerås", "jönköping", "karlstad",
    "luleå", "sundsvall", "linköping", "uppsala", "norrköping", "skövde",
    "skellefteå",
}

SINGLE_OBSERVED = {
    "lagerarbetare": "DLEi_bTh_oLA",
    "systemutvecklare": "fg7B_yov_smw",
    "sjuksköterskor": "bXNH_MNX_dUR",
    "programmerare": "fg7B_yov_smw",
}

TEACHER_QUERY = "lärare"
CIVIL_ENGINEER_QUERY = "civilingenjör"
ASSISTANT_QUERY = "assistent"
SUBJECT_TEACHER_QUERY = "ämneslärare"
SELLER_QUERY = "försäljare"


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def fetch(url: str, timeout: int = 240) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def expected_hash(registry: dict[str, Any], adapter_id: str) -> str:
    adapters = registry.get("adapters")
    if not isinstance(adapters, list):
        raise RuntimeError("source registry missing adapters")
    matches = [a for a in adapters if isinstance(a, dict) and a.get("id") == adapter_id]
    if len(matches) != 1:
        raise RuntimeError(f"expected one adapter {adapter_id!r}, got {len(matches)}")
    digest = matches[0].get("source_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise RuntimeError(f"adapter {adapter_id!r} has no accepted source hash")
    return digest


def checked_json(url: str, expected: str) -> tuple[bytes, Any]:
    body = fetch(url)
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected:
        raise RuntimeError(f"source drift for {url}: expected {expected}, got {actual}")
    return body, json.loads(body)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def select_batch(real: list[dict[str, Any]], excluded: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for row in real:
        merged.append({"source_pool": "observed_unbound_query", "row": row, "observed_count": int(row["observed_count"])})
    for row in excluded:
        merged.append({"source_pool": "yv_excluded_title_routing", "row": row, "observed_count": int(row["observed_count"])})
    merged.sort(key=lambda x: (-x["observed_count"], x["source_pool"], norm(x["row"]["query"]), str(x["row"]["id"])))
    total = sum(x["observed_count"] for x in merged)
    selected = []
    cumulative = 0
    for item in merged:
        selected.append(item)
        cumulative += item["observed_count"]
        if cumulative / total >= 0.80:
            break
    if len(selected) != 34:
        raise RuntimeError(f"frozen Pareto batch shape drift: expected 34, got {len(selected)}")
    if round(100 * cumulative / total, 3) != 80.738:
        raise RuntimeError("frozen Pareto batch volume share drift")
    return selected


def identity(by_id: dict[str, dict[str, Any]], cid: str) -> dict[str, str]:
    concept = by_id.get(cid)
    if not isinstance(concept, dict) or concept.get("type") != "occupation-name":
        raise RuntimeError(f"invalid occupation identity {cid}")
    return {"kind": "occupation-name", "concept_id": cid, "label": str(concept.get("preferred_label") or "")}


def identities(by_id: dict[str, dict[str, Any]], ids: list[str] | set[str]) -> list[dict[str, str]]:
    unique = sorted(set(ids), key=lambda cid: (norm(by_id[cid].get("preferred_label")), cid))
    return [identity(by_id, cid) for cid in unique]


def evidence_observed(model_note: str, *, positive: bool) -> list[dict[str, str]]:
    evidence = [
        {
            "source": "Pinned Yrkesväljaren/Platsbanken observed-query corpus",
            "provenance": "behavioral",
            "role": "query_origin",
            "ref": "research/benchmark/v31/yv-real-query-review/review-packet.jsonl",
            "note": "Observed query string and aggregate frequency only; no selected-ID ground truth.",
        },
        {
            "source": MODEL_JUDGMENT_SOURCE,
            "provenance": "model_judgment",
            "role": "destination_ground_truth",
            "note": model_note,
        },
    ]
    if positive:
        evidence.extend([
            {
                "source": "JobTech Taxonomy v31",
                "provenance": "canonical",
                "role": "context_only",
                "note": "Selected judgment identities are validated active occupation-name concepts.",
            },
            {
                "source": "Published Yrkesväljaren v31",
                "provenance": "behavioral",
                "role": "product_admission",
                "note": "All occupation-name identities are admitted by the YV reference profile; YV does not define generic-engine scope.",
            },
        ])
    return evidence


def evidence_excluded(model_note: str) -> list[dict[str, str]]:
    return [
        {
            "source": "JobTech Taxonomy v31 job-title label",
            "provenance": "canonical",
            "role": "query_origin",
            "note": "The query is an exact active job-title preferred label that is retrieval vocabulary, not a core occupation destination.",
        },
        {
            "source": "JobTech Taxonomy v31 typed job-title→occupation relations",
            "provenance": "curated_relation",
            "role": "context_only",
            "note": "Candidate occupation contexts constrain the judgment but do not themselves prove user intent.",
        },
        {
            "source": MODEL_JUDGMENT_SOURCE,
            "provenance": "model_judgment",
            "role": "destination_ground_truth",
            "note": model_note,
        },
        {
            "source": "Published Yrkesväljaren v31",
            "provenance": "behavioral",
            "role": "product_admission",
            "note": "Positive occupation-name identities are admitted by the YV reference profile; the excluded job-title itself remains non-selectable there.",
        },
    ]


def case_common(index: int, query: str, query_origin: str, strata: list[str], intent: str,
                must: list[dict[str, Any]], acceptable: list[dict[str, Any]], must_not: list[dict[str, Any]],
                evidence: list[dict[str, str]], confidence: str, rationale: str, observed_count: int) -> dict[str, Any]:
    return {
        "id": f"yv.model-pareto.{index:03d}",
        "taxonomy_version": 31,
        "product": "YV",
        "query": query,
        "query_language": "sv",
        "query_origin": query_origin,
        "strata": sorted(set(strata)),
        "expected_intent": intent,
        "must": must,
        "acceptable": acceptable,
        "must_not": must_not,
        "top_k": 10,
        "allow_abstention": intent == "NO_MATCH",
        "source_evidence": evidence,
        "rationale": rationale,
        "notes": f"Observed count in source review pool: {observed_count}. Model-judgment confidence: {confidence}.",
        "adjudication": {
            "status": "MODEL_ADJUDICATED",
            "reviewer_count": 0,
            "agreement": "UNREVIEWED",
            "review_note": f"confidence={confidence}; {rationale}",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--real-query", default="research/benchmark/v31/yv-real-query-review/review-packet.jsonl")
    ap.add_argument("--excluded-routing", default="research/benchmark/v31/yv-profile-safety/excluded-routing-review.jsonl")
    ap.add_argument("--output-dir", default="artifacts/pareto-model-adjudicated-v31")
    args = ap.parse_args()

    real = read_jsonl(Path(args.real_query))
    excluded = read_jsonl(Path(args.excluded_routing))
    if len(real) != 50 or len(excluded) != 20:
        raise RuntimeError("frozen review population count drift")
    selected = select_batch(real, excluded)

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    taxonomy_url = "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json"
    taxonomy_body, taxonomy = checked_json(taxonomy_url, expected_hash(registry, "taxonomy-common-relations"))
    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    # Cross-reference the generic excluded Säljare route for the observed synonym Försäljare.
    excluded_by_query = {norm(r["query"]): r for r in excluded}
    seller_route = excluded_by_query.get("säljare")
    if not seller_route:
        raise RuntimeError("missing frozen Säljare routing context")
    seller_parent_ids = [str(x["concept_id"]) for x in seller_route["candidate_occupation_identities"]]

    teacher_ids = {
        str(c["id"]) for c in concepts
        if isinstance(c, dict) and c.get("type") == "occupation-name" and "lärare" in norm(c.get("preferred_label"))
    }
    if len(teacher_ids) != 25:
        # Yogainstruktör has alternative label Yogalärare and is deliberately not included by preferred-label family.
        raise RuntimeError(f"teacher preferred-label family drift: {len(teacher_ids)}")
    civil_ids = {
        str(c["id"]) for c in concepts
        if isinstance(c, dict) and c.get("type") == "occupation-name" and norm(c.get("preferred_label")).startswith("civilingenjör")
    }
    if len(civil_ids) != 20:
        raise RuntimeError(f"civil-engineer family drift: {len(civil_ids)}")
    assistant_ids = {
        str(c["id"]) for c in concepts
        if isinstance(c, dict) and c.get("type") == "occupation-name" and "assistent" in norm(c.get("preferred_label"))
    }
    if len(assistant_ids) != 51:
        # One surface-context hit is Flight Data Operator via alternative label; preferred-label family stays narrower.
        raise RuntimeError(f"assistant preferred-label family drift: {len(assistant_ids)}")

    subject_teacher_ids = {"wypk_7S7_snv", "86sy_hBf_exW"}

    out_cases: list[dict[str, Any]] = []
    source_pool_counts = {"observed_unbound_query": 0, "yv_excluded_title_routing": 0}
    no_match_count = single_count = ambiguous_count = 0

    for index, item in enumerate(selected, 1):
        pool = item["source_pool"]
        row = item["row"]
        query = str(row["query"])
        q = norm(query)
        count = int(row["observed_count"])
        source_pool_counts[pool] += 1

        if pool == "observed_unbound_query":
            if q in GEO_QUERIES:
                must_not = [
                    identity(by_id, str(x["concept_id"]))
                    for x in row.get("candidate_context", {}).get("top5", [])
                    if str(x.get("concept_id") or "") in by_id
                ]
                rationale = "The query is geographic rather than an occupation expression; occupation retrieval should abstain. Any incidental C0 occupation overlap is a hard negative."
                case = case_common(
                    index, query, "observed_query", ["yv_unbound_observed_query", "no_valid_match", "hard_negative"],
                    "NO_MATCH", [], [], must_not,
                    evidence_observed("Model judgment: geographic/place intent has no valid occupation destination.", positive=False),
                    "HIGH", rationale, count,
                )
                no_match_count += 1
            elif q in SINGLE_OBSERVED:
                cid = SINGLE_OBSERVED[q]
                rationale = {
                    "lagerarbetare": "Common singular wording maps directly to the canonical occupation Lagerarbetare/Terminalarbetare.",
                    "systemutvecklare": "Systemutvecklare is an exact canonical alternative label of Systemutvecklare/Programmerare.",
                    "sjuksköterskor": "Generic plural wording refers to the base occupation Sjuksköterska, grundutbildad rather than a specific specialist-nurse subtype.",
                    "programmerare": "Programmerare is an exact canonical alternative label of Systemutvecklare/Programmerare.",
                }[q]
                strata = ["yv_unbound_observed_query"]
                if q in {"systemutvecklare", "programmerare"}:
                    strata.append("alternative_label")
                else:
                    strata.append("colloquial")
                case = case_common(
                    index, query, "observed_query", strata, "SINGLE",
                    [identity(by_id, cid)], [], [],
                    evidence_observed(f"Model judgment: {rationale}", positive=True),
                    "HIGH", rationale, count,
                )
                single_count += 1
            else:
                if q == TEACHER_QUERY:
                    ids = teacher_ids
                    rationale = "The bare word 'lärare' is an underspecified occupation family; multiple canonical teacher occupations are valid without further context."
                elif q == CIVIL_ENGINEER_QUERY:
                    ids = civil_ids
                    rationale = "The bare civil-engineer title omits engineering specialisation; all canonical Civilingenjör specialisations remain plausible."
                elif q == ASSISTANT_QUERY:
                    ids = assistant_ids
                    rationale = "The bare word 'assistent' is too broad to identify one assistant occupation; multiple canonical assistant occupations are plausible."
                elif q == SUBJECT_TEACHER_QUERY:
                    ids = subject_teacher_ids
                    rationale = "Ämneslärare is underspecified between the canonical 7–9 and gymnasieskolan occupation identities."
                elif q == SELLER_QUERY:
                    ids = set(seller_parent_ids)
                    rationale = "Försäljare is a generic synonym of Säljare and is underspecified across the occupation contexts attached to the generic Säljare title."
                else:
                    raise RuntimeError(f"unadjudicated observed query in Pareto batch: {query!r}")
                case = case_common(
                    index, query, "observed_query", ["yv_unbound_observed_query", "broad_or_underspecified"],
                    "AMBIGUOUS", [], identities(by_id, ids), [],
                    evidence_observed(f"Model judgment: {rationale}", positive=True),
                    "MEDIUM", rationale, count,
                )
                ambiguous_count += 1

        elif pool == "yv_excluded_title_routing":
            candidates = row.get("candidate_occupation_identities")
            if not isinstance(candidates, list) or not candidates:
                raise RuntimeError(f"excluded routing row has no candidate contexts: {query}")
            candidate_ids = [str(x["concept_id"]) for x in candidates]
            for cid in candidate_ids:
                identity(by_id, cid)

            must_not: list[dict[str, str]] = []
            if q == "sjuksköterska":
                if len(candidate_ids) != 1:
                    raise RuntimeError("Sjuksköterska routing shape drift")
                intent = "SINGLE"
                must = [identity(by_id, candidate_ids[0])]
                acceptable: list[dict[str, str]] = []
                rationale = "The generic excluded title Sjuksköterska has one typed occupation context: Sjuksköterska, grundutbildad."
                confidence = "HIGH"
                single_count += 1
            else:
                accepted_ids = list(candidate_ids)
                if q == "grundlärare":
                    rejected = "wypk_7S7_snv"  # Ämneslärare, 7–9 is a distinct certification/occupation family.
                    if rejected not in accepted_ids:
                        raise RuntimeError("Grundlärare expected 7–9 context disappeared")
                    accepted_ids.remove(rejected)
                    must_not = [identity(by_id, rejected)]
                    rationale = "Grundlärare is broad across primary-school teacher identities, but Ämneslärare, 7–9 is a distinct teacher category and is rejected despite the generic title relation."
                else:
                    rationale = f"The generic excluded title {query} is underspecified across its typed occupation contexts; without additional context the related occupation identities remain plausible routing outcomes."
                intent = "AMBIGUOUS"
                must = []
                acceptable = identities(by_id, accepted_ids)
                confidence = "MEDIUM"
                ambiguous_count += 1

            case = case_common(
                index, query, "canonical_label", ["yv_excluded_title_router", "broad_or_underspecified"] if intent == "AMBIGUOUS" else ["yv_excluded_title_router"],
                intent, must, acceptable, must_not,
                evidence_excluded(f"Model judgment: {rationale}"), confidence, rationale, count,
            )
        else:
            raise RuntimeError(f"unknown pool {pool}")

        out_cases.append(case)

    if source_pool_counts != {"observed_unbound_query": 27, "yv_excluded_title_routing": 7}:
        raise RuntimeError(f"selected pool counts drifted: {source_pool_counts}")
    if (no_match_count, single_count, ambiguous_count) != (18, 5, 11):
        raise RuntimeError(f"adjudication intent counts drifted: no_match={no_match_count} single={single_count} ambiguous={ambiguous_count}")

    selected_volume = sum(int(x["observed_count"]) for x in selected)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "benchmark.jsonl").open("w", encoding="utf-8") as handle:
        for case in out_cases:
            handle.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")

    manifest = {
        "schema_version": 1,
        "taxonomy_version": 31,
        "status": "MODEL_ADJUDICATED",
        "model_judgment_source": MODEL_JUDGMENT_SOURCE,
        "cases": len(out_cases),
        "observed_volume": selected_volume,
        "selected_share_of_70_row_review_pool_pct": 80.738,
        "source_pool_counts": source_pool_counts,
        "intent_counts": {"NO_MATCH": no_match_count, "SINGLE": single_count, "AMBIGUOUS": ambiguous_count},
        "authority_boundary": "model_judgment is evaluation truth for this initial decision slice only; it is not canonical taxonomy authority, source truth, or human review and may later be audited/revised independently",
        "taxonomy_sha256": hashlib.sha256(taxonomy_body).hexdigest(),
        "source_files": [args.real_query, args.excluded_routing],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
