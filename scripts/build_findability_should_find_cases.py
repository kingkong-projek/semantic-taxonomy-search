#!/usr/bin/env python3
"""Build source-attested findability probes for current YV/KV.

The goal is not to invent semantic benchmark truth. It is to reconstruct plausible
"I know this word, why can't I find it?" product experiences from evidence that
already has an authoritative target:

YV
- canonical alternative/hidden labels for active occupation-name concepts;
- legacy labels whose deprecated occupation/job-title concept has one canonical
  active replacement admitted by YV;
- real observed title+context queries for multi-context job titles when the extra
  query words uniquely identify one published occupation parent.

KV
- canonical alternative/hidden labels for active skills;
- legacy labels whose deprecated skill has one canonical active replacement.

YV probes retain real query frequency when the exact surface occurs in the pinned
Yrkesväljaren query corpus. KV has no equivalent query log, so target occurrence
is carried only as an explicit popularity proxy.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from audit_current_selector_failure_modes import checked_json, expected_hash, norm
from deprecated_compatibility_coverage import as_strings, graphql, relation_ids, resolve_route

EXPECTED_GENERATOR_COMMIT = "6dd9e4737d7db3cb2709f8082808b88e5c89ed6e"
TARGET_TYPES = ("occupation-name", "job-title", "skill")


def word_tokens(value: Any) -> tuple[str, ...]:
    return tuple(re.findall(r"[0-9a-zåäö+#]+", norm(value)))


def load_queries(generator: Path, expected_sha: str) -> tuple[dict[str, int], dict[str, Any]]:
    path = generator / "data/sokningar-platsbanken.json.zip"
    body = path.read_bytes()
    actual = hashlib.sha256(body).hexdigest()
    if actual != expected_sha:
        raise RuntimeError(f"query corpus drift: expected {expected_sha}, got {actual}")
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".json")]
        if len(names) != 1:
            raise RuntimeError(f"expected one JSON in query archive, got {names}")
        doc = json.load(zf.open(names[0]))
    raw = doc.get("search_terms")
    if not isinstance(raw, dict):
        raise RuntimeError("query corpus missing search_terms")
    counts: dict[str, int] = collections.defaultdict(int)
    for q, count in raw.items():
        counts[norm(q)] += int(count)
    return dict(counts), {
        "sha256": actual,
        "start_date": doc.get("start_date"),
        "end_date": doc.get("end_date"),
        "total_search_terms": int(doc.get("total_search_terms") or 0),
        "distinct_terms": len(raw),
    }


def fetch_graphql_concepts(version: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    all_concepts: dict[str, dict[str, Any]] = {}
    sources: list[dict[str, Any]] = []
    for ctype in TARGET_TYPES:
        query = f'''query FindabilityShouldFind {{
          concepts(type: "{ctype}", version: "{version}", include_deprecated: true, limit: 50000) {{
            id
            preferred_label
            type
            deprecated
            alternative_labels
            hidden_labels
            replaced_by {{ id preferred_label type deprecated }}
          }}
        }}'''
        body, doc, url = graphql(query)
        rows = (doc.get("data") or {}).get("concepts")
        if not isinstance(rows, list):
            raise RuntimeError(f"GraphQL missing concepts for {ctype}")
        for c in rows:
            if isinstance(c, dict) and c.get("id"):
                all_concepts[str(c["id"])] = c
        sources.append({
            "type": ctype,
            "url": url,
            "response_sha256": hashlib.sha256(body).hexdigest(),
            "returned_concepts": len(rows),
        })
    return all_concepts, sources


def surface_rows(
    all_concepts: dict[str, dict[str, Any]],
    active_by_id: dict[str, dict[str, Any]],
    yv_occ_ids: set[str],
    yv_job_ids: set[str],
    active_skill_ids: set[str],
) -> list[dict[str, Any]]:
    """Return authoritative query-surface -> target candidates before collision filtering."""
    out: list[dict[str, Any]] = []

    # Current canonical alternative/hidden vocabulary.
    for cid, c in active_by_id.items():
        ctype = str(c.get("type") or "")
        gql = all_concepts.get(cid, c)
        preferred = norm(c.get("preferred_label"))
        if ctype == "occupation-name" and cid in yv_occ_ids:
            product = "YV"
        elif ctype == "skill" and cid in active_skill_ids:
            product = "KV"
        else:
            continue
        for field, provenance in (("alternative_labels", "canonical_alternative_label"), ("hidden_labels", "canonical_hidden_label")):
            for surface in as_strings(gql.get(field)):
                if norm(surface) and norm(surface) != preferred:
                    out.append({
                        "product": product,
                        "query": surface,
                        "surface_provenance": provenance,
                        "source_concept_id": cid,
                        "source_concept_type": ctype,
                        "target_id": cid,
                        "target_type": ctype,
                        "target_label": c.get("preferred_label"),
                    })

    # Canonical migration/history vocabulary. Replacement is route evidence, not synonymy.
    type_by_id = {cid: str(c.get("type") or "") for cid, c in all_concepts.items()}
    for cid, c in active_by_id.items():
        type_by_id.setdefault(cid, str(c.get("type") or ""))
    deprecated_ids = {cid for cid, c in all_concepts.items() if c.get("deprecated") is True}
    active_ids = set(active_by_id)
    graph = {
        cid: tuple(sorted(set(relation_ids(all_concepts[cid].get("replaced_by")))))
        for cid in deprecated_ids
    }
    for cid in sorted(deprecated_ids):
        c = all_concepts[cid]
        ctype = str(c.get("type") or "")
        if ctype not in TARGET_TYPES:
            continue
        res = resolve_route(cid, ctype, graph, type_by_id, deprecated_ids, active_ids)
        if res.state != "UNIQUE_ACTIVE_TARGET" or len(res.active_targets) != 1:
            continue
        target = res.active_targets[0]
        if ctype == "occupation-name" and target in yv_occ_ids:
            product = "YV"
        elif ctype == "job-title" and target in yv_job_ids:
            product = "YV"
        elif ctype == "skill" and target in active_skill_ids:
            product = "KV"
        else:
            continue
        target_concept = active_by_id.get(target)
        if not target_concept:
            continue
        labels = [str(c.get("preferred_label") or "").strip()]
        labels += as_strings(c.get("alternative_labels"))
        labels += as_strings(c.get("hidden_labels"))
        for surface in sorted({x for x in labels if x}):
            if norm(surface) and norm(surface) != norm(target_concept.get("preferred_label")):
                out.append({
                    "product": product,
                    "query": surface,
                    "surface_provenance": "deprecated_unique_replacement_label",
                    "source_concept_id": cid,
                    "source_concept_type": ctype,
                    "target_id": target,
                    "target_type": ctype,
                    "target_label": target_concept.get("preferred_label"),
                    "replacement_path": list(res.paths[0]) if res.paths else [cid, target],
                })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--generator-dir", required=True)
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--query-aggregate", default="research/coverage/v31/yv-query-language-aggregate.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--output-dir", default="artifacts/findability-should-find-v31")
    args = ap.parse_args()

    version = str(args.version)
    generator = Path(args.generator_dir)
    commit = (generator / "SOURCE_COMMIT.txt").read_text(encoding="utf-8").strip()
    if commit != EXPECTED_GENERATOR_COMMIT:
        raise RuntimeError(f"unexpected generator commit {commit}")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    query_aggregate = json.loads(Path(args.query_aggregate).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    query_counts, query_meta = load_queries(generator, str(query_aggregate["query_corpus"]["zip_sha256"]))

    taxonomy_url = f"https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    yv_url = f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{version}.json"
    kv_url = f"https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t{version}.json"
    taxonomy_body, taxonomy_doc = checked_json(taxonomy_url, expected_hash(registry, "taxonomy-common-relations"))
    yv_body, yv_doc = checked_json(yv_url, expected_hash(registry, "yrkesvaljaren"))
    kv_body, _ = checked_json(kv_url, expected_hash(registry, "skill-selector"))

    active = taxonomy_doc.get("data", {}).get("concepts")
    if not isinstance(active, list):
        raise RuntimeError("active taxonomy concepts missing")
    active_by_id = {str(c["id"]): c for c in active if isinstance(c, dict) and c.get("id")}
    active_skill_ids = {cid for cid, c in active_by_id.items() if c.get("type") == "skill"}

    yv_rows = yv_doc.get("data")
    if not isinstance(yv_rows, list):
        raise RuntimeError("YV data missing")
    yv_occ_ids = {str(r["id"]) for r in yv_rows if isinstance(r, dict) and r.get("type") == "occupation-name" and r.get("id")}
    yv_job_ids = {str(r["id"]) for r in yv_rows if isinstance(r, dict) and r.get("type") == "job-title" and r.get("id")}
    current_yv_preferred: dict[str, set[tuple[str, str]]] = collections.defaultdict(set)
    for r in yv_rows:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        current_yv_preferred[norm(r.get("preferred_label"))].add((str(r.get("type") or ""), str(r["id"])))

    all_concepts, gql_sources = fetch_graphql_concepts(version)
    surfaces = surface_rows(all_concepts, active_by_id, yv_occ_ids, yv_job_ids, active_skill_ids)

    # Collision filter: a surface is decision-bearing only when all authoritative rows for
    # that product/surface route to the same target. Also do not call a current preferred
    # label a missing-vocabulary alias.
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in surfaces:
        grouped[(row["product"], norm(row["query"]))].append(row)

    canonical_alias_groups: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in surfaces:
        if row["surface_provenance"] in {"canonical_alternative_label", "canonical_hidden_label"}:
            canonical_alias_groups[(row["product"], norm(row["query"]))].append(row)
    canonical_alias_surface_collisions: dict[str, dict[str, int | float]] = {}
    for product in ("YV", "KV"):
        groups=[rows for (p,_),rows in canonical_alias_groups.items() if p==product]
        unique=[rows for rows in groups if len({(str(r["target_type"]),str(r["target_id"])) for r in rows})==1]
        ambiguous=[rows for rows in groups if len({(str(r["target_type"]),str(r["target_id"])) for r in rows})>1]
        canonical_alias_surface_collisions[product]={
            "distinct_normalized_surfaces":len(groups),
            "unique_target_surfaces":len(unique),
            "ambiguous_target_surfaces":len(ambiguous),
            "ambiguous_target_surface_pct":round(100.0*len(ambiguous)/len(groups),3) if groups else 0.0,
        }

    occurrence: dict[str, int] = {}
    for key in ("occupation_name", "skill"):
        for r in pareto.get(key, {}).get("ranked_p95", []):
            occurrence[str(r.get("concept_id"))] = int(r.get("occurrences") or 0)

    cases: list[dict[str, Any]] = []
    for (product, nq), rows in sorted(grouped.items()):
        targets = {(str(r["target_type"]), str(r["target_id"])) for r in rows}
        if len(targets) != 1 or not nq:
            continue
        target_type, target_id = next(iter(targets))
        if product == "YV":
            # If this exact surface is already a current preferred label for the intended
            # target, it is a control, not a missing-vocabulary probe.
            preferred_targets = current_yv_preferred.get(nq, set())
            if (target_type, target_id) in preferred_targets:
                continue
            observed = int(query_counts.get(nq, 0))
            weight = observed
        else:
            observed = None
            weight = int(occurrence.get(target_id, 0))
        exemplar = rows[0]
        cases.append({
            "id": f"{product.lower()}.should-find.{len(cases)+1:04d}",
            "product": product,
            "query": exemplar["query"],
            "normalized_query": nq,
            "surface_provenance": sorted({str(r["surface_provenance"]) for r in rows}),
            "target": {"concept_id": target_id, "kind": target_type, "label": exemplar.get("target_label")},
            "observed_yv_query_count": observed,
            "target_occurrence_proxy": int(occurrence.get(target_id, 0)),
            "decision_weight": weight,
            "source_rows": rows,
            "authority_boundary": "source-attested query surface/route; replay measures current selector reachability, not user selection intent",
        })

    # Real title + context queries: infer intended parent only where extra tokens uniquely
    # identify one published parent among that job title's own context rows.
    by_job: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in yv_rows:
        if isinstance(r, dict) and r.get("type") == "job-title" and r.get("id"):
            by_job[str(r["id"])].append(r)
    multi = [rows for rows in by_job.values() if len({str(r.get("occupation_name_id") or "") for r in rows}) > 1]
    query_items = [(q, count, set(word_tokens(q))) for q, count in query_counts.items()]
    context_cases: list[dict[str, Any]] = []
    for rows in multi:
        title = str(rows[0].get("preferred_label") or "")
        title_tokens = set(word_tokens(title))
        if not title_tokens:
            continue
        parent_tokens = {
            str(r.get("occupation_name_id") or ""): set(word_tokens(r.get("occupation_name_preferred_label")))
            for r in rows if r.get("occupation_name_id")
        }
        for q, count, qtokens in query_items:
            if count <= 0 or norm(q) == norm(title) or not title_tokens.issubset(qtokens):
                continue
            extra = qtokens - title_tokens
            if not extra:
                continue
            matches = [pid for pid, ptokens in parent_tokens.items() if extra.issubset(ptokens)]
            if len(matches) != 1:
                continue
            pid = matches[0]
            # Require at least one genuinely distinguishing token versus sibling parents.
            sibling_union = set().union(*(tokens for other, tokens in parent_tokens.items() if other != pid))
            if not any(t not in sibling_union for t in extra):
                continue
            parent_row = next(r for r in rows if str(r.get("occupation_name_id") or "") == pid)
            context_cases.append({
                "id": f"yv.context-qualified.{len(context_cases)+1:04d}",
                "product": "YV",
                "query": q,
                "normalized_query": norm(q),
                "surface_provenance": ["observed_multi_context_title_plus_unique_parent_tokens"],
                "job_title_id": str(rows[0]["id"]),
                "job_title_label": title,
                "target": {"concept_id": pid, "kind": "occupation-name", "label": parent_row.get("occupation_name_preferred_label")},
                "expected_context_row": {"job_title_id": str(rows[0]["id"]), "occupation_name_id": pid},
                "observed_yv_query_count": int(count),
                "decision_weight": int(count),
                "authority_boundary": "intent inferred from observed query tokens uniquely naming one published parent among this title's sibling contexts; not query->selection ground truth",
            })
    # Deduplicate same query/target inferred through equivalent rows and order by demand.
    unique_context: dict[tuple[str, str], dict[str, Any]] = {}
    for c in context_cases:
        key = (c["normalized_query"], c["target"]["concept_id"])
        prev = unique_context.get(key)
        if prev is None or int(c["observed_yv_query_count"]) > int(prev["observed_yv_query_count"]):
            unique_context[key] = c
    context_cases = sorted(unique_context.values(), key=lambda c: (-int(c["observed_yv_query_count"]), c["normalized_query"]))
    for i, c in enumerate(context_cases, 1):
        c["id"] = f"yv.context-qualified.{i:04d}"

    cases.extend(context_cases)
    cases.sort(key=lambda c: (c["product"], -int(c.get("decision_weight") or 0), c["normalized_query"], c["target"]["concept_id"]))

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "cases.jsonl").open("w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n")

    yv = [c for c in cases if c["product"] == "YV"]
    kv = [c for c in cases if c["product"] == "KV"]
    yv_observed = [c for c in yv if int(c.get("observed_yv_query_count") or 0) > 0]
    manifest = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "generator_commit": commit,
        "sources": {
            "taxonomy": {"url": taxonomy_url, "sha256": hashlib.sha256(taxonomy_body).hexdigest()},
            "yv": {"url": yv_url, "sha256": hashlib.sha256(yv_body).hexdigest()},
            "kv": {"url": kv_url, "sha256": hashlib.sha256(kv_body).hexdigest()},
            "query_corpus": query_meta,
            "graphql": gql_sources,
        },
        "canonical_alias_surface_collisions": canonical_alias_surface_collisions,
        "counts": {
            "all_cases": len(cases),
            "yv_cases": len(yv),
            "yv_cases_with_observed_exact_query": len(yv_observed),
            "yv_observed_query_volume": sum(int(c.get("observed_yv_query_count") or 0) for c in yv_observed),
            "yv_context_qualified_observed_cases": len(context_cases),
            "yv_context_qualified_observed_volume": sum(int(c["observed_yv_query_count"]) for c in context_cases),
            "kv_cases": len(kv),
        },
        "interpretation": "source-attested should-find probes plus narrowly inferred title-context traffic; evaluate against exact current selectors before proposing fixes",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
