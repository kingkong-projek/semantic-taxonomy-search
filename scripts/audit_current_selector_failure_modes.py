#!/usr/bin/env python3
"""Audit current YV/KV product failure modes before adding semantic complexity.

The audit is deliberately product-first:
- reproduce the published YV v31 read model and its generator policy;
- verify the pinned frontend search/selection contracts from source;
- measure reachability of generator-excluded YV titles using the current direct-search lane;
- measure context identity/round-trip hazards for multi-parent job-title rows;
- quantify canonical taxonomy vocabulary that current preferred-label-only search does not index;
- verify the YV -> KV context hand-off contract and the repo demo implementation.

No benchmark labels are generated here and no retrieval architecture is changed.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

UA = "semantic-taxonomy-search-current-selector-failure-audit/0.1"
EXPECTED_GENERATOR_COMMIT = "6dd9e4737d7db3cb2709f8082808b88e5c89ed6e"
EXPECTED_FRONTEND_COMMIT = "0eba98e3a91079a43c1eaf6da09dfabe11e5bc8b"


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def as_labels(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if value in (None, ""):
        return []
    text = str(value).strip()
    return [text] if text else []


def fetch(url: str, timeout: int = 240) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expected_hash(registry: dict[str, Any], adapter_id: str) -> str:
    adapters = registry.get("adapters")
    if not isinstance(adapters, list):
        raise RuntimeError("source registry missing adapters")
    matches = [a for a in adapters if isinstance(a, dict) and a.get("id") == adapter_id]
    if len(matches) != 1:
        raise RuntimeError(f"expected one adapter {adapter_id!r}, got {len(matches)}")
    digest = matches[0].get("source_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise RuntimeError(f"adapter {adapter_id!r} missing accepted source hash")
    return digest


def checked_json(url: str, expected: str) -> tuple[bytes, dict[str, Any]]:
    body = fetch(url)
    actual = sha(body)
    if actual != expected:
        raise RuntimeError(f"source drift for {url}: expected {expected}, got {actual}")
    doc = json.loads(body)
    if not isinstance(doc, dict):
        raise RuntimeError(f"expected JSON object from {url}")
    return body, doc


def load_query_counts(source_dir: Path, expected_sha: str) -> tuple[dict[str, int], dict[str, Any]]:
    zip_path = source_dir / "data/sokningar-platsbanken.json.zip"
    body = zip_path.read_bytes()
    actual = sha(body)
    if actual != expected_sha:
        raise RuntimeError(f"query corpus hash drift: expected {expected_sha}, got {actual}")
    with zipfile.ZipFile(zip_path) as zf:
        names = [name for name in zf.namelist() if name.endswith(".json")]
        if len(names) != 1:
            raise RuntimeError(f"expected one JSON in query archive, got {names}")
        doc = json.load(zf.open(names[0]))
    terms = doc.get("search_terms")
    if not isinstance(terms, dict):
        raise RuntimeError("query corpus missing search_terms")
    counts = {norm(k): int(v) for k, v in terms.items()}
    return counts, {
        "sha256": actual,
        "start_date": doc.get("start_date"),
        "end_date": doc.get("end_date"),
        "total_query_volume": int(doc.get("total_search_terms") or 0),
    }


def yv_direct_score(label: str, query: str) -> float | None:
    normalized_label = norm(label)
    normalized_query = norm(query)
    tokens = [token for token in normalized_query.split(" ") if token]
    if normalized_label == normalized_query:
        return 1.0
    if len(tokens) > 1:
        return 0.98 if all(token in normalized_label for token in tokens) else None
    if normalized_label.startswith(normalized_query):
        return 0.99
    if normalized_query in normalized_label:
        return 0.95
    return None


def yv_direct_results(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for row in rows:
        score = yv_direct_score(str(row.get("preferred_label") or ""), query)
        if score is None:
            continue
        copy = dict(row)
        copy["_score"] = score
        parent_label = str(row.get("occupation_name_preferred_label") or "")
        copy["_display"] = (
            f"{row.get('preferred_label', '')} ({parent_label})" if parent_label else str(row.get("preferred_label") or "")
        )
        hits.append(copy)
    hits.sort(key=lambda row: (
        -float(row.get("_score") or 0),
        -float(row.get("weight") or 0),
        str(row.get("_display") or "").casefold(),
    ))
    return hits


def collect_kv_skill_labels(kv_doc: dict[str, Any]) -> dict[str, str]:
    categories = (
        "regulated_skills",
        "essential_skills",
        "optional_skills",
        "calculated_skills",
        "related_skills",
    )
    raw = kv_doc.get("data") or {}
    if not isinstance(raw, dict):
        raise RuntimeError("KV source missing data object")
    skills: dict[str, str] = {}
    for node in raw.values():
        if not isinstance(node, dict):
            continue
        for category in categories:
            value = node.get(category)
            if not isinstance(value, dict):
                continue
            for label, skill_id in value.items():
                if isinstance(label, str) and isinstance(skill_id, str):
                    skills[skill_id] = label
        if node.get("type") is None and not node.get("preferred_label"):
            for label, skill_id in node.items():
                if isinstance(label, str) and isinstance(skill_id, str):
                    skills[skill_id] = label
    return skills


def source_contract(frontend: Path) -> dict[str, Any]:
    files = {
        "yv_search": frontend / "src/components/job-selector/search.utils.ts",
        "yv_controller": frontend / "src/components/job-selector/job-selector-controller.ts",
        "yv_component": frontend / "src/components/job-selector/job-selector.tsx",
        "yv_constants": frontend / "src/components/job-selector/constants.ts",
        "kv_helpers": frontend / "packages/kompetensvaljaren/src/components/kompetensvaljaren/logic/search.engine.helpers.ts",
        "kv_engine": frontend / "packages/kompetensvaljaren/src/components/kompetensvaljaren/logic/search.engine.ts",
        "demo": frontend / "e2e-test-app/main.js",
    }
    text = {name: path.read_text(encoding="utf-8") for name, path in files.items()}
    expected_fragments = {
        "yv_search_only_preferred_label": ("yv_search", "const normalizedLabel = normalizeForComparison(item.preferred_label);"),
        "yv_fuse_preferred_label_key": ("yv_constants", "keys: ['preferred_label']"),
        "yv_rich_display_uses_parent": ("yv_controller", "`${item.preferred_label} (${item.occupation_name_preferred_label})`"),
        "yv_programmatic_lookup_by_id_only": ("yv_controller", "this.taxonomyData.find((taxonomy) => taxonomy.id === item.id)"),
        "yv_form_value_id_only": ("yv_component", "formData.append(this.name, item.id || item.rawLabel)"),
        "yv_edit_requeries_display_label": ("yv_controller", "const professionLabel = selectedItem.displayLabel;"),
        "kv_catalog_only_preferred_label": ("kv_helpers", "normalizedLabel: normalizeText(preferred_label)"),
        "kv_token_catalog_only_preferred_label": ("kv_helpers", "splitSearchTokens(preferred_label)"),
        "kv_candidates_before_context_ranking": ("kv_engine", "const candidateMatches = this.getCandidateMatches(normalizedQuery);"),
        "kv_context_accepts_occupation_or_ssyk4": ("kv_engine", "if (this.base.occupationToSsyk4[id]) return 'occupation-name';"),
        "demo_passes_yv_id_directly_to_kv": ("demo", "const idToUse = selection.id || '';"),
    }
    missing = [name for name, (file_name, fragment) in expected_fragments.items() if fragment not in text[file_name]]
    if missing:
        raise RuntimeError(f"frontend source contract drift; missing expected fragments: {missing}")
    return {
        "frontend_commit": EXPECTED_FRONTEND_COMMIT,
        "verified_fragments": sorted(expected_fragments),
        "interpretation": {
            "YV_query_fields": ["preferred_label"],
            "YV_display_context_field": "occupation_name_preferred_label",
            "KV_query_fields": ["skill preferred_label/tokenized preferred_label"],
            "KV_context_role": "ranking/filter signal after lexical candidate generation; not candidate-generation vocabulary",
            "KV_context_id_types": ["occupation-name", "ssyk-level-4"],
            "demo_handoff": "uses YV selection.id directly as KV af-occupation-id",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--generator-dir", required=True)
    ap.add_argument("--frontend-dir", required=True)
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--query-aggregate", default="research/coverage/v31/yv-query-language-aggregate.json")
    ap.add_argument("--output-dir", default="artifacts/current-selector-failure-audit-v31")
    args = ap.parse_args()

    version = str(args.version)
    generator = Path(args.generator_dir)
    frontend = Path(args.frontend_dir)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    query_agg = json.loads(Path(args.query_aggregate).read_text(encoding="utf-8"))

    generator_commit = (generator / "SOURCE_COMMIT.txt").read_text(encoding="utf-8").strip()
    frontend_commit = (frontend / "SOURCE_COMMIT.txt").read_text(encoding="utf-8").strip()
    if generator_commit != EXPECTED_GENERATOR_COMMIT:
        raise RuntimeError(f"unexpected generator commit {generator_commit}")
    if frontend_commit != EXPECTED_FRONTEND_COMMIT:
        raise RuntimeError(f"unexpected frontend commit {frontend_commit}")

    query_counts, query_meta = load_query_counts(generator, str(query_agg["query_corpus"]["zip_sha256"]))

    taxonomy_url = (
        f"https://data.jobtechdev.se/taxonomy/version/{version}/query/"
        "concepts-and-common-relations/concepts-and-common-relations.json"
    )
    yv_url = f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{version}.json"
    kv_url = f"https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t{version}.json"
    taxonomy_body, taxonomy_doc = checked_json(taxonomy_url, expected_hash(registry, "taxonomy-common-relations"))
    yv_body, yv_doc = checked_json(yv_url, expected_hash(registry, "yrkesvaljaren"))
    kv_body, kv_doc = checked_json(kv_url, expected_hash(registry, "skill-selector"))

    concepts = taxonomy_doc.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy source missing data.concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    yv_rows = yv_doc.get("data")
    if not isinstance(yv_rows, list):
        raise RuntimeError("YV source missing data list")
    occupation_rows = [r for r in yv_rows if isinstance(r, dict) and r.get("type") == "occupation-name"]
    job_rows = [r for r in yv_rows if isinstance(r, dict) and r.get("type") == "job-title"]
    job_by_id: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in job_rows:
        job_by_id[str(row["id"])].append(row)

    multi = {
        cid: members for cid, members in job_by_id.items()
        if len({str(row.get("occupation_name_id") or "") for row in members}) > 1
    }
    multi_rows = sum(len(members) for members in multi.values())
    if len(multi) != 541 or multi_rows != 1186:
        raise RuntimeError(f"expected 541 multi-parent IDs / 1186 rows, got {len(multi)} / {multi_rows}")

    multi_direct_all_top10 = 0
    multi_direct_volume = 0
    multi_total_volume = 0
    multi_fail_examples: list[dict[str, Any]] = []
    for cid, members in multi.items():
        label = str(members[0].get("preferred_label") or "")
        expected_pairs = {(cid, str(r.get("occupation_name_id") or "")) for r in members}
        top10 = yv_direct_results(yv_rows, label)[:10]
        got_pairs = {
            (str(r.get("id") or ""), str(r.get("occupation_name_id") or ""))
            for r in top10 if r.get("type") == "job-title"
        }
        count = query_counts.get(norm(label), 0)
        multi_total_volume += count
        if expected_pairs.issubset(got_pairs):
            multi_direct_all_top10 += 1
            multi_direct_volume += count
        elif len(multi_fail_examples) < 20:
            multi_fail_examples.append({
                "job_title_id": cid,
                "query": label,
                "observed_count": count,
                "expected_contexts": sorted(expected_pairs),
                "top10": [
                    {
                        "id": r.get("id"),
                        "type": r.get("type"),
                        "label": r.get("preferred_label"),
                        "occupation_name_id": r.get("occupation_name_id"),
                        "occupation_name_label": r.get("occupation_name_preferred_label"),
                        "score": r.get("_score"),
                    }
                    for r in top10
                ],
            })

    many = json.loads((generator / f"data/jobbtitlar-mappad-till-för-många-yb-t{version}.json").read_text(encoding="utf-8"))
    redundant = json.loads((generator / f"data/jobbtitlar-del-av-yb-t{version}.json").read_text(encoding="utf-8"))
    if len(many) != 104 or len(redundant) != 101:
        raise RuntimeError("generator exclusion diagnostics drifted")

    exclusion_stats: dict[str, Any] = {}
    exclusion_examples: list[dict[str, Any]] = []
    for reason, diagnostic in (("too_many_parents", many), ("redundant_label", redundant)):
        items = []
        for label, parent_labels in diagnostic.items():
            expected_parent_labels = {str(x) for x in parent_labels}
            hits = yv_direct_results(yv_rows, str(label))
            top10 = hits[:10]
            relevant_any = [r for r in hits if r.get("type") == "occupation-name" and str(r.get("preferred_label")) in expected_parent_labels]
            relevant_top10 = [r for r in top10 if r.get("type") == "occupation-name" and str(r.get("preferred_label")) in expected_parent_labels]
            count = query_counts.get(norm(label), 0)
            items.append({
                "query": str(label),
                "observed_count": count,
                "mapped_parent_count": len(expected_parent_labels),
                "direct_relevant_any": bool(relevant_any),
                "direct_relevant_top10": bool(relevant_top10),
                "direct_result_count": len(hits),
            })
            if not relevant_top10:
                exclusion_examples.append({
                    "reason": reason,
                    "query": str(label),
                    "observed_count": count,
                    "mapped_parent_labels": sorted(expected_parent_labels),
                    "direct_top10": [
                        {"type": r.get("type"), "label": r.get("preferred_label"), "id": r.get("id"), "score": r.get("_score")}
                        for r in top10
                    ],
                })
        exclusion_stats[reason] = {
            "titles": len(items),
            "with_observed_exact_query": sum(1 for x in items if x["observed_count"] > 0),
            "observed_query_volume": sum(x["observed_count"] for x in items),
            "direct_relevant_any": sum(1 for x in items if x["direct_relevant_any"]),
            "direct_relevant_top10": sum(1 for x in items if x["direct_relevant_top10"]),
            "volume_with_direct_relevant_top10": sum(x["observed_count"] for x in items if x["direct_relevant_top10"]),
            "volume_without_direct_relevant_top10": sum(x["observed_count"] for x in items if not x["direct_relevant_top10"]),
        }
    exclusion_examples.sort(key=lambda x: (-x["observed_count"], norm(x["query"])))

    admitted_yv_ids = {str(r.get("id")) for r in yv_rows if r.get("id")}
    yv_alt_queries: list[tuple[str, str, str]] = []
    for cid in admitted_yv_ids:
        concept = by_id.get(cid)
        if not concept:
            continue
        for alt in as_labels(concept.get("alternative_labels")):
            if norm(alt) and norm(alt) != norm(concept.get("preferred_label")):
                yv_alt_queries.append((cid, str(concept.get("type") or ""), alt))
    yv_alt_no_direct = [
        (cid, kind, alt) for cid, kind, alt in yv_alt_queries
        if not yv_direct_results(yv_rows, alt)
    ]

    kv_skill_labels = collect_kv_skill_labels(kv_doc)
    active_skill_ids = {cid for cid, c in by_id.items() if c.get("type") == "skill"}
    if set(kv_skill_labels) != active_skill_ids:
        missing = len(active_skill_ids - set(kv_skill_labels))
        extra = len(set(kv_skill_labels) - active_skill_ids)
        raise RuntimeError(f"KV runtime skill catalog differs from active skill universe: missing={missing}, extra={extra}")
    kv_norm_labels = [norm(label) for label in kv_skill_labels.values()]
    kv_alt_queries: list[tuple[str, str]] = []
    kv_distinct_definitions = 0
    for cid in active_skill_ids:
        concept = by_id[cid]
        label = str(concept.get("preferred_label") or "")
        definition = str(concept.get("definition") or "").strip()
        if definition and norm(definition) != norm(label):
            kv_distinct_definitions += 1
        for alt in as_labels(concept.get("alternative_labels")):
            if norm(alt) and norm(alt) != norm(label):
                kv_alt_queries.append((cid, alt))
    kv_alt_no_direct = [
        (cid, alt) for cid, alt in kv_alt_queries
        if not any(norm(alt) in canonical for canonical in kv_norm_labels)
    ]

    contract = source_contract(frontend)

    context_roundtrip = {
        "multi_parent_job_title_ids": len(multi),
        "multi_parent_context_rows": multi_rows,
        "extra_context_rows_beyond_first_id_match": multi_rows - len(multi),
        "programmatic_setSelection": "rich job-title input is validated but reduced to id; controller resolves first taxonomy row with that id",
        "affected_nonfirst_context_rows": multi_rows - len(multi),
        "form_submission": "standard form value serializes job-title id only, so parent occupation context is not preserved for any multi-parent job-title",
        "form_context_ambiguous_rows": multi_rows,
        "multi_select": "duplicate prevention compares id first, so two contexts of the same job-title id cannot coexist as selections",
    }

    handoff = {
        "KV_accepted_context_types": ["occupation-name", "ssyk-level-4"],
        "YV_job_title_event_shape": "job-title id + related occupation-name id",
        "required_handoff_for_job_title": "selection.related.id (or equivalent explicit occupation-name identity), not selection.id",
        "repo_demo_current_behavior": "passes selection.id directly to KV af-occupation-id",
        "consequence_for_job_title_selection": "KV does not recognize the job-title id as context and falls back to context-free/global behaviour",
        "classification": "integration-footgun demonstrated by repo demo; whether production consumers repeat it must be checked separately",
    }

    aggregate = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "taxonomy_version": int(version),
        "scope": "current YV/KV product failure-mode audit before semantic fallback design",
        "sources": {
            "generator_commit": generator_commit,
            "frontend_commit": frontend_commit,
            "taxonomy": {"url": taxonomy_url, "sha256": sha(taxonomy_body)},
            "yv": {"url": yv_url, "sha256": sha(yv_body)},
            "kv": {"url": kv_url, "sha256": sha(kv_body)},
            "query_corpus": query_meta,
        },
        "source_contract": contract,
        "YV": {
            "published_rows": {
                "total": len(yv_rows),
                "occupation_name_rows": len(occupation_rows),
                "job_title_context_rows": len(job_rows),
                "unique_job_title_ids": len(job_by_id),
            },
            "multi_parent_title_behavior": {
                "job_title_ids": len(multi),
                "context_rows": multi_rows,
                "all_contexts_present_in_direct_top10_for_exact_title_query": multi_direct_all_top10,
                "population_exact_query_volume": multi_total_volume,
                "volume_with_all_contexts_in_direct_top10": multi_direct_volume,
                "fail_examples": multi_fail_examples,
            },
            "context_identity_roundtrip": context_roundtrip,
            "excluded_title_direct_reachability": {
                "note": "Measures the deterministic direct lane only. Cases without a relevant direct parent may still receive fuzzy results, which are not treated as grounded routing evidence here.",
                "by_reason": exclusion_stats,
                "highest_volume_without_relevant_direct_top10": exclusion_examples[:25],
            },
            "unused_canonical_vocabulary": {
                "admitted_concepts_with_runtime_alternative_label_surfaces": len({cid for cid, _, _ in yv_alt_queries}),
                "distinct_alternative_label_surfaces": len({norm(alt) for _, _, alt in yv_alt_queries}),
                "alternative_surfaces_with_no_current_direct_result": len(yv_alt_no_direct),
                "note": "YV runtime indexes preferred_label only. This does not claim every alternative label should be enabled without product review.",
            },
        },
        "KV": {
            "runtime_skill_catalog": len(kv_skill_labels),
            "candidate_generation": "preferred skill label and tokens from preferred skill label only",
            "context_behavior": "occupation/SSYK context can rank/filter lexical candidates but does not add query vocabulary",
            "unused_canonical_vocabulary": {
                "skills_with_distinct_canonical_definition": kv_distinct_definitions,
                "skills_with_alternative_labels": len({cid for cid, _ in kv_alt_queries}),
                "distinct_alternative_label_surfaces": len({norm(alt) for _, alt in kv_alt_queries}),
                "alternative_surfaces_with_no_canonical_contains_match": len(kv_alt_no_direct),
                "note": "Fuzzy may rescue some surfaces; this count isolates vocabulary absent from the deterministic direct label lane.",
            },
        },
        "YV_to_KV_handoff": handoff,
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"# Current YV/KV failure-mode audit — taxonomy v{version}",
        "",
        f"Pinned YV generator: `{generator_commit}`  ",
        f"Pinned selector frontend: `{frontend_commit}`",
        "",
        "## YV",
        "",
        f"- Published rows: **{len(yv_rows):,}** = {len(occupation_rows):,} occupation-name + {len(job_rows):,} job-title context rows.",
        f"- Published unique job-title IDs: **{len(job_by_id):,}**.",
        f"- Multi-parent job-title IDs: **{len(multi):,}**, represented by **{multi_rows:,}** selectable context rows.",
        f"- Exact title query exposes all intended multi-parent contexts in direct top-10 for **{multi_direct_all_top10:,}/{len(multi):,}** title IDs.",
        f"- Programmatic roundtrip can collapse **{multi_rows-len(multi):,}** non-first contextual rows because `setSelection` resolves by job-title ID only.",
        f"- Standard form value cannot encode parent context for any of the **{multi_rows:,}** multi-parent context rows because it serializes only the job-title ID.",
        "",
        "### Generator-excluded active job titles",
        "",
    ]
    for reason in ("redundant_label", "too_many_parents"):
        s = exclusion_stats[reason]
        lines.append(
            f"- `{reason}`: {s['titles']} titles; relevant mapped occupation appears in current direct top-10 for "
            f"**{s['direct_relevant_top10']}/{s['titles']}**. Observed exact-query volume without such a direct top-10 route: "
            f"**{s['volume_without_direct_relevant_top10']:,}**."
        )
    lines += [
        "",
        "## Search vocabulary already owned by the taxonomy but not indexed by current product search",
        "",
        f"- YV: {len({cid for cid, _, _ in yv_alt_queries}):,} admitted concepts expose canonical alternative-label vocabulary; "
        f"{len(yv_alt_no_direct):,} alternative surfaces produce no deterministic direct YV result.",
        f"- KV: {len({cid for cid, _ in kv_alt_queries}):,} skills expose alternative labels and {kv_distinct_definitions:,} skills have a definition distinct from the preferred label. "
        f"Current KV candidate generation indexes preferred labels only; {len(kv_alt_no_direct):,} alternative surfaces have no canonical contains match.",
        "",
        "## YV → KV context hand-off",
        "",
        "- KV accepts occupation-name or SSYK4 IDs as context.",
        "- A YV job-title selection carries its occupation-name in `related.id`.",
        "- The repo's stepped YV→KV demo passes `selection.id` directly. For a job-title selection that is the job-title ID, so KV treats it as no context and falls back to global behaviour.",
        "- This is proven as an integration footgun in the demo; production consumers must be inspected separately before calling it a production incident.",
        "",
        "## Decision consequence",
        "",
        "Do not add semantic complexity until these product-native gaps are evaluated/fixed first: admission/reachability of excluded high-volume titles, context-preserving identity/roundtrip, canonical alternative-label vocabulary, and correct YV→KV context hand-off. Description fallback remains a separate incremental capability after the ordinary selector baseline is made honest.",
        "",
    ]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
