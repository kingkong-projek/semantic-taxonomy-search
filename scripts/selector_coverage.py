#!/usr/bin/env python3
"""Measure published Yrkesväljaren and Kompetensväljaren coverage for taxonomy v31.

The selectors are evidence sources for two separate canonical search spaces:
  * YV semantic search returns occupation/job-title identities used by YV.
  * KV semantic search returns skill identities used by KV.

KV's published read model is also useful as contextual evidence: its records may
be keyed by occupation-name OR SSYK4. These context types must never be collapsed.
Likewise, one YV job-title identity may be emitted once per related occupation;
that ambiguity is measured explicitly rather than deduplicated away.
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

USER_AGENT = "semantic-taxonomy-search-selector-coverage/0.2"
KV_LAYERS = ("regulated_skills", "essential_skills", "optional_skills", "calculated_skills")
KV_CONTEXT_TYPES = ("occupation-name", "ssyk-level-4")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str, timeout: int = 180) -> tuple[bytes, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
    return body, json.loads(body)


def pct(n: int, d: int) -> float | None:
    return None if not d else round(100.0 * n / d, 3)


def distribution(values: list[int]) -> dict[str, float | int | None]:
    if not values:
        return {"min": None, "median": None, "mean": None, "max": None}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": round(statistics.fmean(values), 3),
        "max": max(values),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="31")
    parser.add_argument("--output-dir", default="artifacts/selector-coverage-v31")
    args = parser.parse_args()

    version = str(args.version)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    generated_at = now_utc()

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    yv_url = f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{version}.json"
    kv_url = f"https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t{version}.json"

    taxonomy_body, taxonomy_doc = fetch_json(taxonomy_url)
    yv_body, yv_doc = fetch_json(yv_url)
    kv_body, kv_doc = fetch_json(kv_url)

    concepts = taxonomy_doc.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy snapshot missing data.concepts")

    concept_by_id: dict[str, dict[str, Any]] = {}
    ids_by_type: dict[str, set[str]] = defaultdict(set)
    for concept in concepts:
        if not isinstance(concept, dict):
            continue
        cid = str(concept.get("id") or "")
        ctype = str(concept.get("type") or "")
        if cid:
            concept_by_id[cid] = concept
            ids_by_type[ctype].add(cid)

    # ------------------------------------------------------------------ YV
    yv_rows = yv_doc.get("data")
    if not isinstance(yv_rows, list):
        raise RuntimeError("Yrkesväljaren missing data list")
    yv_declared_version = str(yv_doc.get("metadata", {}).get("labour_market_taxonomy_version") or "")
    if version not in yv_declared_version:
        raise RuntimeError(f"Yrkesväljaren taxonomy version mismatch: {yv_declared_version!r}")

    yv_type_counts = Counter()
    yv_ids_by_type: dict[str, set[str]] = defaultdict(set)
    yv_weights: dict[str, list[float]] = defaultdict(list)
    yv_unknown_ids: set[str] = set()
    yv_wrong_types: list[dict[str, str]] = []
    yv_bad_parent_ids: list[dict[str, str]] = []
    yv_job_title_parents: dict[str, set[str]] = defaultdict(set)
    yv_job_title_labels: dict[str, str] = {}
    yv_label_to_id_parent_pairs: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for row in yv_rows:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id") or "")
        ctype = str(row.get("type") or "")
        label = str(row.get("preferred_label") or "").strip()
        parent = str(row.get("occupation_name_id") or "")
        yv_type_counts[ctype] += 1

        if cid:
            yv_ids_by_type[ctype].add(cid)
            canonical = concept_by_id.get(cid)
            if canonical is None:
                yv_unknown_ids.add(cid)
            elif str(canonical.get("type") or "") != ctype:
                yv_wrong_types.append({"id": cid, "selector_type": ctype, "taxonomy_type": str(canonical.get("type"))})

        try:
            yv_weights[ctype].append(float(row.get("weight")))
        except (TypeError, ValueError):
            pass

        if parent:
            target = concept_by_id.get(parent)
            if target is None or target.get("type") != "occupation-name":
                yv_bad_parent_ids.append({"row_id": cid, "occupation_name_id": parent})

        if ctype == "job-title" and cid:
            if parent:
                yv_job_title_parents[cid].add(parent)
            yv_job_title_labels[cid] = label
            yv_label_to_id_parent_pairs[label.casefold()].add((cid, parent))

    yv_coverage: dict[str, Any] = {}
    for ctype in ("occupation-name", "job-title"):
        universe = ids_by_type.get(ctype, set())
        observed = yv_ids_by_type.get(ctype, set())
        weights = yv_weights.get(ctype, [])
        yv_coverage[ctype] = {
            "taxonomy_active": len(universe),
            "selector_unique_ids": len(observed),
            "coverage_pct": pct(len(observed & universe), len(universe)),
            "missing_active_ids": len(universe - observed),
            "unknown_selector_ids": len(observed - universe),
            "row_occurrences": yv_type_counts.get(ctype, 0),
            "weights": {
                "count": len(weights),
                "min": min(weights) if weights else None,
                "median": statistics.median(weights) if weights else None,
                "mean": round(statistics.fmean(weights), 9) if weights else None,
                "max": max(weights) if weights else None,
                "zero_count": sum(x == 0 for x in weights),
            },
        }

    multi_parent_titles = {
        tid: {"preferred_label": yv_job_title_labels.get(tid, ""), "occupation_name_ids": sorted(parents)}
        for tid, parents in yv_job_title_parents.items()
        if len(parents) > 1
    }
    ambiguous_labels = {
        label: sorted({f"{cid}|{parent}" for cid, parent in pairs})
        for label, pairs in yv_label_to_id_parent_pairs.items()
        if len(pairs) > 1
    }

    # ------------------------------------------------------------------ KV
    kv_data = kv_doc.get("data")
    if not isinstance(kv_data, dict):
        raise RuntimeError("Kompetensväljaren missing data object")
    kv_declared_version = str(kv_doc.get("metadata", {}).get("labour_market_taxonomy_version") or "")
    if version not in kv_declared_version:
        raise RuntimeError(f"Kompetensväljaren taxonomy version mismatch: {kv_declared_version!r}")

    active_skills = ids_by_type.get("skill", set())
    kv_context_ids_by_type: dict[str, set[str]] = defaultdict(set)
    kv_unknown_context_ids: list[dict[str, str]] = []
    kv_wrong_context_types: list[dict[str, str]] = []
    kv_bad_ssyk: list[dict[str, str]] = []
    kv_unknown_skill_refs: list[dict[str, str]] = []
    kv_wrong_skill_types: list[dict[str, str]] = []

    layer_skill_ids: dict[str, set[str]] = {layer: set() for layer in KV_LAYERS}
    layer_edges = Counter()
    layer_edges_by_context: dict[str, Counter[str]] = {layer: Counter() for layer in KV_LAYERS}
    layer_nonempty_by_context: dict[str, Counter[str]] = {layer: Counter() for layer in KV_LAYERS}
    layer_counts_by_context: dict[str, dict[str, list[int]]] = {layer: defaultdict(list) for layer in KV_LAYERS}
    context_rows: list[dict[str, Any]] = []

    for context_id, record in kv_data.items():
        if not isinstance(record, dict):
            continue
        context_type = str(record.get("type") or "")
        kv_context_ids_by_type[context_type].add(context_id)

        canonical_context = concept_by_id.get(context_id)
        if canonical_context is None:
            kv_unknown_context_ids.append({"id": context_id, "record_type": context_type})
        elif str(canonical_context.get("type") or "") != context_type:
            kv_wrong_context_types.append({
                "id": context_id,
                "record_type": context_type,
                "taxonomy_type": str(canonical_context.get("type") or ""),
            })

        ssyk_id = str(record.get("ssyk-level-4-id") or "")
        if ssyk_id:
            ssyk = concept_by_id.get(ssyk_id)
            if ssyk is None or ssyk.get("type") != "ssyk-level-4":
                kv_bad_ssyk.append({"context_id": context_id, "context_type": context_type, "ssyk_level_4_id": ssyk_id})

        row: dict[str, Any] = {
            "context_id": context_id,
            "context_type": context_type,
            "preferred_label": record.get("preferred_label"),
            "ssyk_level_4_id": ssyk_id,
        }
        for layer in KV_LAYERS:
            mapping = record.get(layer) or {}
            if not isinstance(mapping, dict):
                raise RuntimeError(f"KV layer {layer} for {context_id} is not an object")
            count = len(mapping)
            row[f"{layer}_count"] = count
            layer_counts_by_context[layer][context_type].append(count)
            layer_edges[layer] += count
            layer_edges_by_context[layer][context_type] += count
            if count:
                layer_nonempty_by_context[layer][context_type] += 1
            for label, skill_id_value in mapping.items():
                skill_id = str(skill_id_value or "")
                if not skill_id:
                    continue
                layer_skill_ids[layer].add(skill_id)
                canonical_skill = concept_by_id.get(skill_id)
                if canonical_skill is None:
                    kv_unknown_skill_refs.append({"context_id": context_id, "context_type": context_type, "layer": layer, "skill_id": skill_id, "label": str(label)})
                elif canonical_skill.get("type") != "skill":
                    kv_wrong_skill_types.append({"context_id": context_id, "context_type": context_type, "layer": layer, "skill_id": skill_id, "taxonomy_type": str(canonical_skill.get("type"))})
        context_rows.append(row)

    context_coverage: dict[str, Any] = {}
    for ctype in sorted(set(KV_CONTEXT_TYPES) | set(kv_context_ids_by_type)):
        observed = kv_context_ids_by_type.get(ctype, set())
        universe = ids_by_type.get(ctype, set())
        context_coverage[ctype] = {
            "records": len(observed),
            "active_taxonomy": len(universe),
            "coverage_pct": pct(len(observed & universe), len(universe)),
            "missing_active_ids": len(universe - observed),
            "unknown_ids": len(observed - universe),
        }

    layer_coverage: dict[str, Any] = {}
    for layer in KV_LAYERS:
        skill_ids = layer_skill_ids[layer]
        by_context: dict[str, Any] = {}
        for ctype, observed_context_ids in kv_context_ids_by_type.items():
            by_context[ctype] = {
                "contexts_nonempty": layer_nonempty_by_context[layer].get(ctype, 0),
                "context_coverage_pct": pct(layer_nonempty_by_context[layer].get(ctype, 0), len(observed_context_ids)),
                "edges": layer_edges_by_context[layer].get(ctype, 0),
                "skills_per_context": distribution(layer_counts_by_context[layer].get(ctype, [])),
            }
        layer_coverage[layer] = {
            "edges": layer_edges[layer],
            "unique_skill_ids": len(skill_ids),
            "active_skill_coverage_pct": pct(len(skill_ids & active_skills), len(active_skills)),
            "unknown_skill_ids": len(skill_ids - active_skills),
            "by_context_type": by_context,
        }

    union_skill_ids = set().union(*(layer_skill_ids[layer] for layer in KV_LAYERS))
    overlaps: dict[str, int] = {}
    for i, left in enumerate(KV_LAYERS):
        for right in KV_LAYERS[i + 1:]:
            overlaps[f"{left}__{right}"] = len(layer_skill_ids[left] & layer_skill_ids[right])

    aggregate = {
        "schema_version": 2,
        "taxonomy_version": version,
        "generated_at": generated_at,
        "sources": {
            "taxonomy": {"url": taxonomy_url, "bytes": len(taxonomy_body), "sha256": hashlib.sha256(taxonomy_body).hexdigest()},
            "yrkesvaljaren": {"url": yv_url, "bytes": len(yv_body), "sha256": hashlib.sha256(yv_body).hexdigest(), "declared_taxonomy_version": yv_declared_version},
            "kompetensvaljaren": {"url": kv_url, "bytes": len(kv_body), "sha256": hashlib.sha256(kv_body).hexdigest(), "declared_taxonomy_version": kv_declared_version},
        },
        "yrkesvaljaren": {
            "rows": len(yv_rows),
            "coverage": yv_coverage,
            "unknown_ids": len(yv_unknown_ids),
            "wrong_type_occurrences": len(yv_wrong_types),
            "bad_occupation_parent_occurrences": len(yv_bad_parent_ids),
            "multi_parent_job_title_ids": len(multi_parent_titles),
            "max_occupation_parents_per_job_title": max((len(v["occupation_name_ids"]) for v in multi_parent_titles.values()), default=1),
            "ambiguous_job_title_labels": len(ambiguous_labels),
        },
        "kompetensvaljaren": {
            "records": len(kv_data),
            "context_coverage": context_coverage,
            "layers": layer_coverage,
            "union_unique_skill_ids": len(union_skill_ids),
            "union_active_skill_coverage_pct": pct(len(union_skill_ids & active_skills), len(active_skills)),
            "union_unknown_skill_ids": len(union_skill_ids - active_skills),
            "layer_unique_skill_overlap": overlaps,
            "unknown_context_id_occurrences": len(kv_unknown_context_ids),
            "wrong_context_type_occurrences": len(kv_wrong_context_types),
            "unknown_skill_ref_occurrences": len(kv_unknown_skill_refs),
            "wrong_skill_type_occurrences": len(kv_wrong_skill_types),
            "bad_ssyk_occurrences": len(kv_bad_ssyk),
        },
    }

    (out / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "kv-context-coverage.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in sorted(context_rows, key=lambda r: (r["context_type"], r["context_id"]))),
        encoding="utf-8",
    )
    (out / "yv-multi-parent-job-titles.json").write_text(json.dumps(multi_parent_titles, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "yv-ambiguous-labels.json").write_text(json.dumps(ambiguous_labels, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "anomalies.json").write_text(json.dumps({
        "yv_unknown_ids": sorted(yv_unknown_ids),
        "yv_wrong_types": yv_wrong_types,
        "yv_bad_occupation_parent_ids": yv_bad_parent_ids,
        "kv_unknown_context_ids": kv_unknown_context_ids,
        "kv_wrong_context_types": kv_wrong_context_types,
        "kv_unknown_skill_refs": kv_unknown_skill_refs,
        "kv_wrong_skill_types": kv_wrong_skill_types,
        "kv_bad_ssyk": kv_bad_ssyk,
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"# Selector coverage — taxonomy v{version}",
        "",
        "## Yrkesväljaren",
        "",
        f"Rows: **{len(yv_rows):,}**",
        "",
        "| Type | active taxonomy | unique selector IDs | row occurrences | coverage | missing active |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for ctype in ("occupation-name", "job-title"):
        c = yv_coverage[ctype]
        lines.append(f"| `{ctype}` | {c['taxonomy_active']:,} | {c['selector_unique_ids']:,} | {c['row_occurrences']:,} | {c['coverage_pct']}% | {c['missing_active_ids']:,} |")
    lines += [
        "",
        f"Job-title identities related to multiple occupations: **{len(multi_parent_titles):,}** (max parents: **{aggregate['yrkesvaljaren']['max_occupation_parents_per_job_title']}**).",
        f"Ambiguous job-title display labels when identity+occupation context is preserved: **{len(ambiguous_labels):,}**.",
        "",
        "## Kompetensväljaren context records",
        "",
        "| Context type | records | active taxonomy | coverage | missing active | unknown IDs |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for ctype, c in sorted(context_coverage.items()):
        lines.append(f"| `{ctype}` | {c['records']:,} | {c['active_taxonomy']:,} | {c['coverage_pct']}% | {c['missing_active_ids']:,} | {c['unknown_ids']:,} |")
    lines += [
        "",
        "## Kompetensväljaren skill layers",
        "",
        "| Layer | edges | unique skills | active skill coverage | occupation contexts non-empty | SSYK4 contexts non-empty |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for layer in KV_LAYERS:
        c = layer_coverage[layer]
        occ = c["by_context_type"].get("occupation-name", {})
        ssyk = c["by_context_type"].get("ssyk-level-4", {})
        lines.append(
            f"| `{layer}` | {c['edges']:,} | {c['unique_skill_ids']:,} | {c['active_skill_coverage_pct']}% | "
            f"{occ.get('contexts_nonempty', 0):,} | {ssyk.get('contexts_nonempty', 0):,} |"
        )
    lines += [
        "",
        f"Union of all KV layers: **{len(union_skill_ids):,}** unique skill IDs, covering **{pct(len(union_skill_ids & active_skills), len(active_skills))}%** of active v{version} skills.",
        "",
        "## Guardrails",
        "",
        "- YV weights are behavioural priors, not semantic truth.",
        "- A YV job-title row is scoped by its related occupation; duplicate job-title IDs across parents are intentional evidence of ambiguity, not duplicate noise.",
        "- KV context types remain separate: an SSYK4 context is not an occupation-name identity.",
        "- KV layer names remain separate. `regulated`, `essential`, `optional`, and `calculated` must not collapse into one authority level.",
        "- All referenced IDs are validated against the same immutable taxonomy snapshot before coverage is accepted.",
        "",
    ]
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
