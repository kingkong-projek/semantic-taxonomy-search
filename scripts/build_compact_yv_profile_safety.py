#!/usr/bin/env python3
"""Build compact, demand-prioritised YV reference-profile safety slices.

This is deliberately profile-specific evidence on top of the reusable occupation core:
- admitted multi-parent job-title labels are source-truth ambiguity regressions;
- generator-excluded title labels are pending routing review, never auto-labeled.

Selection is Pareto/simple-first: highest observed exact-query frequency first, not a
census of all 541 multi-context titles or all 205 excluded titles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

UA = "semantic-taxonomy-search-compact-yv-safety/0.1"
EXPECTED_GENERATOR_COMMIT = "6dd9e4737d7db3cb2709f8082808b88e5c89ed6e"


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
        raise RuntimeError(f"adapter {adapter_id!r} has no accepted source_sha256")
    return digest


def checked_json(url: str, expected: str) -> tuple[bytes, Any]:
    body = fetch(url)
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected:
        raise RuntimeError(f"source drift for {url}: expected {expected}, got {actual}")
    return body, json.loads(body)


def load_query_counts(source_dir: Path, expected_sha: str) -> tuple[dict[str, int], dict[str, Any]]:
    zip_path = source_dir / "data/sokningar-platsbanken.json.zip"
    body = zip_path.read_bytes()
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected_sha:
        raise RuntimeError(f"query corpus hash drift: expected {expected_sha}, got {actual}")
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".json")]
        if len(names) != 1:
            raise RuntimeError(f"expected one JSON in query ZIP, got {names}")
        doc = json.load(zf.open(names[0]))
    terms = doc.get("search_terms")
    if not isinstance(terms, dict):
        raise RuntimeError("query corpus missing search_terms")
    counts = {norm(k): int(v) for k, v in terms.items()}
    if sum(int(v) for v in terms.values()) != int(doc.get("total_search_terms") or -1):
        raise RuntimeError("query corpus total mismatch")
    return counts, {
        "sha256": actual,
        "start_date": doc.get("start_date"),
        "end_date": doc.get("end_date"),
        "total_query_volume": int(doc.get("total_search_terms") or 0),
    }


def canonical_evidence(version: str) -> dict[str, str]:
    return {
        "source": f"JobTech Taxonomy v{version}",
        "provenance": "canonical",
        "role": "destination_ground_truth",
    }


def curated_evidence(version: str) -> dict[str, str]:
    return {
        "source": f"JobTech Taxonomy v{version} typed relations",
        "provenance": "curated_relation",
        "role": "destination_ground_truth",
        "note": "job-title identity retains exact occupation-name context",
    }


def admission_evidence(version: str) -> dict[str, str]:
    return {
        "source": f"Published Yrkesväljaren v{version}",
        "provenance": "behavioral",
        "role": "product_admission",
        "note": "Reference-profile admission only; YV is not the generic engine target space.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--source-dir", required=True)
    ap.add_argument("--multi-parent-limit", type=int, default=20)
    ap.add_argument("--excluded-limit", type=int, default=20)
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--query-aggregate", default="research/coverage/v31/yv-query-language-aggregate.json")
    ap.add_argument("--output-dir", default="artifacts/compact-yv-profile-safety-v31")
    args = ap.parse_args()

    if not 5 <= args.multi_parent_limit <= 50 or not 5 <= args.excluded_limit <= 50:
        raise RuntimeError("compact safety limits must stay in [5,50]")

    version = str(args.version)
    version_int = int(version)
    source_dir = Path(args.source_dir)
    source_commit = (source_dir / "SOURCE_COMMIT.txt").read_text(encoding="utf-8").strip()
    if source_commit != EXPECTED_GENERATOR_COMMIT:
        raise RuntimeError(f"unexpected generator commit {source_commit}")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    query_agg = json.loads(Path(args.query_aggregate).read_text(encoding="utf-8"))
    if query_agg.get("generator_source_commit") != source_commit:
        raise RuntimeError("query aggregate/generator commit mismatch")

    query_counts, query_meta = load_query_counts(
        source_dir, str(query_agg["query_corpus"]["zip_sha256"])
    )
    if query_meta["total_query_volume"] != int(query_agg["query_corpus"]["total_query_volume"]):
        raise RuntimeError("query-volume drift vs frozen aggregate")

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    yv_url = f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{version}.json"
    taxonomy_body, taxonomy = checked_json(taxonomy_url, expected_hash(registry, "taxonomy-common-relations"))
    yv_body, yv = checked_json(yv_url, expected_hash(registry, "yrkesvaljaren"))

    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active_job_ids = {cid for cid, c in by_id.items() if c.get("type") == "job-title"}

    rows = yv.get("data")
    if not isinstance(rows, list):
        raise RuntimeError("YV missing data")
    job_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    published_job_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("type") != "job-title" or not row.get("id"):
            continue
        cid = str(row["id"])
        parent = str(row.get("occupation_name_id") or "")
        if by_id.get(cid, {}).get("type") != "job-title" or by_id.get(parent, {}).get("type") != "occupation-name":
            raise RuntimeError(f"invalid YV job row {cid}/{parent}")
        published_job_ids.add(cid)
        job_rows[cid].append(row)

    multi_population: list[dict[str, Any]] = []
    for cid, members in job_rows.items():
        parents = {str(r.get("occupation_name_id") or "") for r in members}
        if len(parents) <= 1:
            continue
        label = str(by_id[cid].get("preferred_label") or "").strip()
        multi_population.append({
            "job_title_id": cid,
            "label": label,
            "observed_count": query_counts.get(norm(label), 0),
            "rows": members,
        })
    if len(multi_population) != 541:
        raise RuntimeError(f"expected 541 multi-parent title IDs, got {len(multi_population)}")
    multi_population.sort(key=lambda x: (-x["observed_count"], norm(x["label"]), x["job_title_id"]))
    selected_multi = multi_population[: args.multi_parent_limit]

    multi_cases: list[dict[str, Any]] = []
    for rank, item in enumerate(selected_multi, 1):
        identities = []
        seen: set[tuple[str, str]] = set()
        for row in item["rows"]:
            parent = str(row["occupation_name_id"])
            key = (item["job_title_id"], parent)
            if key in seen:
                continue
            seen.add(key)
            identities.append({
                "kind": "job-title",
                "concept_id": item["job_title_id"],
                "occupation_name_id": parent,
                "label": item["label"],
                "occupation_name_label": str(by_id[parent].get("preferred_label") or ""),
            })
        identities.sort(key=lambda x: (x["occupation_name_id"], x["concept_id"]))
        if len(identities) < 2:
            raise RuntimeError("multi-parent case lost ambiguity")
        multi_cases.append({
            "id": f"yv.safety.multi-parent.{rank:03d}",
            "taxonomy_version": version_int,
            "product": "YV",
            "query": item["label"],
            "query_language": "sv",
            "query_origin": "canonical_label",
            "strata": ["exact_preferred_label", "yv_exact_job_title", "yv_multi_parent_title"],
            "expected_intent": "AMBIGUOUS",
            "must": identities,
            "acceptable": [],
            "must_not": [],
            "top_k": max(10, len(identities)),
            "allow_abstention": False,
            "source_evidence": [canonical_evidence(version), curated_evidence(version), admission_evidence(version)],
            "rationale": f"Exact admitted job-title label occurs in {len(identities)} YV occupation contexts; context identities must not collapse.",
            "notes": f"Observed exact-query count in pinned YV corpus: {item['observed_count']}",
            "adjudication": {"status": "AUTO_HIGH_CONFIDENCE", "reviewer_count": 0, "agreement": "UNREVIEWED"},
        })

    many = json.loads((source_dir / f"data/jobbtitlar-mappad-till-för-många-yb-t{version}.json").read_text(encoding="utf-8"))
    redundant = json.loads((source_dir / f"data/jobbtitlar-del-av-yb-t{version}.json").read_text(encoding="utf-8"))
    if not isinstance(many, dict) or not isinstance(redundant, dict) or len(many) != 104 or len(redundant) != 101:
        raise RuntimeError("pinned generator diagnostic counts drifted")
    if set(many) & set(redundant):
        raise RuntimeError("generator diagnostic families overlap")

    label_to_job_ids: dict[str, list[str]] = defaultdict(list)
    for cid in active_job_ids:
        label_to_job_ids[str(by_id[cid].get("preferred_label") or "")].append(cid)

    excluded_population: list[dict[str, Any]] = []
    for reason, diagnostic in (("too_many_parents", many), ("redundant_label", redundant)):
        for label, parent_labels in diagnostic.items():
            ids = label_to_job_ids.get(str(label), [])
            if len(ids) != 1:
                raise RuntimeError(f"diagnostic label does not map uniquely: {label!r} -> {ids}")
            job_id = ids[0]
            if job_id in published_job_ids:
                raise RuntimeError(f"diagnostic title unexpectedly admitted: {label!r}")
            related = by_id[job_id].get("related")
            parent_ids = []
            if isinstance(related, list):
                for rel in related:
                    rid = str(rel.get("id") if isinstance(rel, dict) else rel)
                    if by_id.get(rid, {}).get("type") == "occupation-name":
                        parent_ids.append(rid)
            parent_ids = sorted(set(parent_ids))
            actual_parent_labels = {str(by_id[pid].get("preferred_label") or "") for pid in parent_ids}
            if actual_parent_labels != {str(x) for x in parent_labels}:
                raise RuntimeError(f"taxonomy/generator parent drift for {label!r}")
            excluded_population.append({
                "job_title_id": job_id,
                "query": str(label),
                "observed_count": query_counts.get(norm(label), 0),
                "yv_exclusion_reason": reason,
                "candidate_occupation_identities": [
                    {"kind": "occupation-name", "concept_id": pid, "label": str(by_id[pid].get("preferred_label") or "")}
                    for pid in parent_ids
                ],
            })
    if len(excluded_population) != 205:
        raise RuntimeError(f"expected 205 excluded titles, got {len(excluded_population)}")
    excluded_population.sort(key=lambda x: (-x["observed_count"], norm(x["query"]), x["job_title_id"]))
    selected_excluded = excluded_population[: args.excluded_limit]

    excluded_review: list[dict[str, Any]] = []
    for rank, item in enumerate(selected_excluded, 1):
        excluded_review.append({
            "id": f"yv.safety.excluded-review.{rank:03d}",
            "taxonomy_version": version_int,
            "reference_profile": "YV",
            "query": item["query"],
            "observed_count": item["observed_count"],
            "job_title_id": item["job_title_id"],
            "yv_exclusion_reason": item["yv_exclusion_reason"],
            "candidate_occupation_identities": item["candidate_occupation_identities"],
            "source": {
                "generator_commit": source_commit,
                "query_corpus_sha256": query_meta["sha256"],
                "semantics": "high-volume canonical job-title wording excluded from YV admission; parent occupations are routing/context evidence only",
            },
            "adjudication": {
                "status": "PENDING_HUMAN_REVIEW",
                "expected_intent": None,
                "must": [],
                "acceptable": [],
                "must_not": [],
                "review_note": "",
            },
        })

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "multi-parent-auto.jsonl").open("w", encoding="utf-8") as f:
        for row in multi_cases:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with (out / "excluded-routing-review.jsonl").open("w", encoding="utf-8") as f:
        for row in excluded_review:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    manifest = {
        "schema_version": 1,
        "taxonomy_version": version_int,
        "semantics": "compact YV reference-profile safety slices; not generic-engine scope",
        "multi_parent": {
            "population": len(multi_population),
            "selected": len(multi_cases),
            "selection": "highest exact observed query count first",
            "selected_query_volume": sum(x["observed_count"] for x in selected_multi),
            "top_queries": [{"query": x["label"], "count": x["observed_count"], "contexts": len(x["rows"])} for x in selected_multi[:10]],
            "truth": "AUTO_HIGH_CONFIDENCE exact admitted context identities",
        },
        "excluded_routing": {
            "population": len(excluded_population),
            "selected": len(excluded_review),
            "selection": "highest exact observed query count first",
            "selected_query_volume": sum(x["observed_count"] for x in selected_excluded),
            "reason_counts": dict(Counter(x["yv_exclusion_reason"] for x in selected_excluded)),
            "top_queries": [{"query": x["query"], "count": x["observed_count"], "reason": x["yv_exclusion_reason"]} for x in selected_excluded[:10]],
            "truth": "PENDING_HUMAN_REVIEW; generator reason is source truth, candidate parent occupations are not destination labels",
        },
        "sources": {
            "taxonomy_sha256": hashlib.sha256(taxonomy_body).hexdigest(),
            "yrkesvaljaren_sha256": hashlib.sha256(yv_body).hexdigest(),
            "generator_commit": source_commit,
            "query_corpus": query_meta,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
