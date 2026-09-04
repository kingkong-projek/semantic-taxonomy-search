#!/usr/bin/env python3
"""Measure published Yrkesväljaren and Kompetensväljaren coverage for taxonomy v31.

The script treats the two selectors as evidence sources for two separate canonical
search spaces:
  * Yrkesväljaren -> occupation-name / job-title evidence
  * Kompetensväljaren -> occupation-contextual evidence about skill concepts

It validates all referenced concept IDs against the same immutable taxonomy
snapshot used by the native-text/common-relations inventories. It never converts
missing data or failed joins into zero semantic coverage.
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

USER_AGENT = "semantic-taxonomy-search-selector-coverage/0.1"
TARGET_TYPES = {"occupation-name", "job-title", "skill"}
KV_LAYERS = ("regulated_skills", "essential_skills", "optional_skills", "calculated_skills")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str, timeout: int = 180) -> tuple[bytes, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read()
    return body, json.loads(body)


def pct(n: int, d: int) -> float | None:
    return None if not d else round(100.0 * n / d, 3)


def stats(values: list[int]) -> dict[str, float | int | None]:
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

    # --- Yrkesväljaren ---
    yv_rows = yv_doc.get("data")
    if not isinstance(yv_rows, list):
        raise RuntimeError("Yrkesväljaren v31 missing data list")
    yv_declared_version = str(yv_doc.get("metadata", {}).get("labour_market_taxonomy_version") or "")
    if version not in yv_declared_version:
        raise RuntimeError(f"Yrkesväljaren taxonomy version mismatch: {yv_declared_version!r}")

    yv_type_counts = Counter()
    yv_ids_by_type: dict[str, set[str]] = defaultdict(set)
    yv_unknown_ids: list[str] = []
    yv_wrong_types: list[dict[str, str]] = []
    yv_bad_parent_ids: list[dict[str, str]] = []
    yv_weights: dict[str, list[float]] = defaultdict(list)
    yv_label_to_ids: dict[str, set[str]] = defaultdict(set)

    for row in yv_rows:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id") or "")
        ctype = str(row.get("type") or "")
        yv_type_counts[ctype] += 1
        if cid:
            yv_ids_by_type[ctype].add(cid)
            canonical = concept_by_id.get(cid)
            if canonical is None:
                yv_unknown_ids.append(cid)
            elif str(canonical.get("type") or "") != ctype:
                yv_wrong_types.append({"id": cid, "selector_type": ctype, "taxonomy_type": str(canonical.get("type"))})
        label = str(row.get("preferred_label") or "").strip().casefold()
        if label and cid:
            yv_label_to_ids[label].add(cid)
        try:
            yv_weights[ctype].append(float(row.get("weight")))
        except (TypeError, ValueError):
            pass

        occupation_id = str(row.get("occupation_name_id") or "")
        if occupation_id:
            target = concept_by_id.get(occupation_id)
            if target is None or target.get("type") != "occupation-name":
                yv_bad_parent_ids.append({"row_id": cid, "occupation_name_id": occupation_id})

    yv_coverage = {}
    for ctype in ("occupation-name", "job-title"):
        universe = ids_by_type.get(ctype, set())
        observed = yv_ids_by_type.get(ctype, set())
        w = yv_weights.get(ctype, [])
        yv_coverage[ctype] = {
            "taxonomy_active": len(universe),
            "selector_unique_ids": len(observed),
            "coverage_pct": pct(len(observed & universe), len(universe)),
            "missing_active_ids": len(universe - observed),
            "unknown_selector_ids": len(observed - universe),
            "weights": {
                "count": len(w),
                "min": min(w) if w else None,
                "median": statistics.median(w) if w else None,
                "mean": round(statistics.fmean(w), 9) if w else None,
                "max": max(w) if w else None,
                "zero_count": sum(x == 0 for x in w),
            },
        }

    ambiguous_yv_labels = {label: sorted(ids) for label, ids in yv_label_to_ids.items() if len(ids) > 1}

    # --- Kompetensväljaren ---
    kv_data = kv_doc.get("data")
    if not isinstance(kv_data, dict):
        raise RuntimeError("Kompetensväljaren v31 missing data object")
    kv_declared_version = str(kv_doc.get("metadata", {}).get("labour_market_taxonomy_version") or "")
    if version not in kv_declared_version:
        raise RuntimeError(f"Kompetensväljaren taxonomy version mismatch: {kv_declared_version!r}")

    kv_occupation_ids = set(kv_data.keys())
    active_occupations = ids_by_type.get("occupation-name", set())
    active_skills = ids_by_type.get("skill", set())
    kv_unknown_occupations = sorted(kv_occupation_ids - active_occupations)
    kv_missing_occupations = sorted(active_occupations - kv_occupation_ids)

    layer_skill_ids: dict[str, set[str]] = {layer: set() for layer in KV_LAYERS}
    layer_edges: Counter[str] = Counter()
    layer_nonempty_occupations: Counter[str] = Counter()
    layer_counts_per_occupation: dict[str, list[int]] = {layer: [] for layer in KV_LAYERS}
    kv_unknown_skill_refs: list[dict[str, str]] = []
    kv_wrong_skill_types: list[dict[str, str]] = []
    kv_bad_ssyk: list[dict[str, str]] = []
    occupation_rows: list[dict[str, Any]] = []

    for occupation_id, record in kv_data.items():
        if not isinstance(record, dict):
            continue
        ssyk_id = str(record.get("ssyk-level-4-id") or "")
        if ssyk_id:
            ssyk = concept_by_id.get(ssyk_id)
            if ssyk is None or ssyk.get("type") != "ssyk-level-4":
                kv_bad_ssyk.append({"occupation_id": occupation_id, "ssyk_level_4_id": ssyk_id})

        row: dict[str, Any] = {"occupation_id": occupation_id, "preferred_label": record.get("preferred_label"), "ssyk_level_4_id": ssyk_id}
        for layer in KV_LAYERS:
            mapping = record.get(layer) or {}
            if not isinstance(mapping, dict):
                raise RuntimeError(f"KV layer {layer} for {occupation_id} is not an object")
            count = len(mapping)
            row[f"{layer}_count"] = count
            layer_counts_per_occupation[layer].append(count)
            if count:
                layer_nonempty_occupations[layer] += 1
            layer_edges[layer] += count
            for label, skill_id_value in mapping.items():
                skill_id = str(skill_id_value or "")
                if not skill_id:
                    continue
                layer_skill_ids[layer].add(skill_id)
                canonical = concept_by_id.get(skill_id)
                if canonical is None:
                    kv_unknown_skill_refs.append({"occupation_id": occupation_id, "layer": layer, "skill_id": skill_id, "label": str(label)})
                elif canonical.get("type") != "skill":
                    kv_wrong_skill_types.append({"occupation_id": occupation_id, "layer": layer, "skill_id": skill_id, "taxonomy_type": str(canonical.get("type"))})
        occupation_rows.append(row)

    union_skill_ids = set().union(*(layer_skill_ids[layer] for layer in KV_LAYERS))
    layer_coverage = {}
    for layer in KV_LAYERS:
        ids = layer_skill_ids[layer]
        layer_coverage[layer] = {
            "occupations_nonempty": layer_nonempty_occupations[layer],
            "occupation_coverage_pct": pct(layer_nonempty_occupations[layer], len(kv_occupation_ids)),
            "edges": layer_edges[layer],
            "unique_skill_ids": len(ids),
            "active_skill_coverage_pct": pct(len(ids & active_skills), len(active_skills)),
            "unknown_skill_ids": len(ids - active_skills),
            "skills_per_occupation": stats(layer_counts_per_occupation[layer]),
        }

    overlaps: dict[str, int] = {}
    for i, left in enumerate(KV_LAYERS):
        for right in KV_LAYERS[i + 1 :]:
            overlaps[f"{left}__{right}"] = len(layer_skill_ids[left] & layer_skill_ids[right])

    aggregate = {
        "schema_version": 1,
        "taxonomy_version": version,
        "generated_at": generated_at,
        "sources": {
            "taxonomy": {"url": taxonomy_url, "bytes": len(taxonomy_body), "sha256": hashlib.sha256(taxonomy_body).hexdigest()},
            "yrkesvaljaren": {"url": yv_url, "bytes": len(yv_body), "sha256": hashlib.sha256(yv_body).hexdigest(), "declared_taxonomy_version": yv_declared_version},
            "kompetensvaljaren": {"url": kv_url, "bytes": len(kv_body), "sha256": hashlib.sha256(kv_body).hexdigest(), "declared_taxonomy_version": kv_declared_version},
        },
        "yrkesvaljaren": {
            "rows": len(yv_rows),
            "row_type_counts": dict(yv_type_counts),
            "coverage": yv_coverage,
            "unknown_id_occurrences": len(yv_unknown_ids),
            "wrong_type_occurrences": len(yv_wrong_types),
            "bad_occupation_parent_occurrences": len(yv_bad_parent_ids),
            "ambiguous_preferred_labels": len(ambiguous_yv_labels),
        },
        "kompetensvaljaren": {
            "occupation_records": len(kv_occupation_ids),
            "active_occupation_coverage_pct": pct(len(kv_occupation_ids & active_occupations), len(active_occupations)),
            "missing_active_occupations": len(kv_missing_occupations),
            "unknown_occupation_ids": len(kv_unknown_occupations),
            "layers": layer_coverage,
            "union_unique_skill_ids": len(union_skill_ids),
            "union_active_skill_coverage_pct": pct(len(union_skill_ids & active_skills), len(active_skills)),
            "union_unknown_skill_ids": len(union_skill_ids - active_skills),
            "layer_unique_skill_overlap": overlaps,
            "unknown_skill_ref_occurrences": len(kv_unknown_skill_refs),
            "wrong_skill_type_occurrences": len(kv_wrong_skill_types),
            "bad_ssyk_occurrences": len(kv_bad_ssyk),
        },
    }

    (out / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "kv-occupation-coverage.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in sorted(occupation_rows, key=lambda r: r["occupation_id"])), encoding="utf-8")
    (out / "yv-ambiguous-labels.json").write_text(json.dumps(ambiguous_yv_labels, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "anomalies.json").write_text(json.dumps({
        "yv_unknown_ids": sorted(set(yv_unknown_ids)),
        "yv_wrong_types": yv_wrong_types,
        "yv_bad_occupation_parent_ids": yv_bad_parent_ids,
        "kv_unknown_occupations": kv_unknown_occupations,
        "kv_missing_active_occupations": kv_missing_occupations,
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
        "| Type | active taxonomy | selector IDs | coverage | missing active |",
        "|---|---:|---:|---:|---:|",
    ]
    for ctype in ("occupation-name", "job-title"):
        c = yv_coverage[ctype]
        lines.append(f"| `{ctype}` | {c['taxonomy_active']:,} | {c['selector_unique_ids']:,} | {c['coverage_pct']}% | {c['missing_active_ids']:,} |")
    lines += [
        "",
        f"Ambiguous preferred labels inside YV rows: **{len(ambiguous_yv_labels):,}**.",
        "",
        "## Kompetensväljaren",
        "",
        f"Occupation records: **{len(kv_occupation_ids):,}** / **{len(active_occupations):,}** active occupation-name concepts ({pct(len(kv_occupation_ids & active_occupations), len(active_occupations))}%).",
        "",
        "| Layer | occupations non-empty | occupation coverage | edges | unique skills | active skill coverage |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for layer in KV_LAYERS:
        c = layer_coverage[layer]
        lines.append(f"| `{layer}` | {c['occupations_nonempty']:,} | {c['occupation_coverage_pct']}% | {c['edges']:,} | {c['unique_skill_ids']:,} | {c['active_skill_coverage_pct']}% |")
    lines += [
        "",
        f"Union of all KV layers: **{len(union_skill_ids):,}** unique skill IDs, covering **{pct(len(union_skill_ids & active_skills), len(active_skills))}%** of active v{version} skills.",
        "",
        "## Guardrails",
        "",
        "- YV weights are behavioural priors, not semantic truth.",
        "- KV layer names remain separate. `regulated`, `essential`, `optional`, and `calculated` must not be collapsed into one authority level.",
        "- A missing selector row is measured absence from that published selector dataset, not absence from taxonomy.",
        "- All selector concept IDs are validated against the same immutable taxonomy snapshot before coverage is accepted.",
        "",
    ]
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
