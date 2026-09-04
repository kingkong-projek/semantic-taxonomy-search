#!/usr/bin/env python3
"""Measure observed Platsbanken query language against YV v31 destination policy.

Uses the version-bound search-term corpus committed in the public YV generator.
The corpus is query string + frequency only: this script never treats it as a
query->selected-taxonomy-ID label set. Exact textual joins are reported separately
for admitted YV labels and generator-excluded job-title labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any


def pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 3) if d else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-dir", required=True)
    ap.add_argument("--version", default="31")
    ap.add_argument("--output-dir", default="artifacts/yv-query-language-v31")
    args = ap.parse_args()
    src = Path(args.source_dir)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    version = str(args.version)

    source_commit = (src / "SOURCE_COMMIT.txt").read_text(encoding="utf-8").strip()
    zip_path = src / "data/sokningar-platsbanken.json.zip"
    zip_bytes = zip_path.read_bytes()
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".json")]
        if len(names) != 1:
            raise RuntimeError(f"expected one JSON in query corpus ZIP, got {names}")
        corpus = json.load(zf.open(names[0]))

    terms = corpus.get("search_terms")
    if not isinstance(terms, dict):
        raise RuntimeError("query corpus missing search_terms object")
    terms = {str(k): int(v) for k, v in terms.items()}
    total_volume = sum(terms.values())
    if total_volume != int(corpus.get("total_search_terms") or -1):
        raise RuntimeError("query corpus total_search_terms does not equal summed frequencies")

    yv = json.loads((src / f"output/v1/yrkesvaljaren-t{version}.json").read_text(encoding="utf-8"))
    rows = yv.get("data")
    if not isinstance(rows, list):
        raise RuntimeError("YV output missing data list")
    admitted_by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if isinstance(row, dict) and row.get("preferred_label"):
            admitted_by_label[str(row["preferred_label"]).casefold()].append(row)

    many = json.loads((src / f"data/jobbtitlar-mappad-till-för-många-yb-t{version}.json").read_text(encoding="utf-8"))
    redundant = json.loads((src / f"data/jobbtitlar-del-av-yb-t{version}.json").read_text(encoding="utf-8"))
    many_labels = {str(x).casefold() for x in many}
    redundant_labels = {str(x).casefold() for x in redundant}
    if many_labels & redundant_labels:
        raise RuntimeError("excluded YV title families overlap")

    buckets: dict[str, dict[str, Any]] = {
        "admitted_exact": {"terms": [], "volume": 0},
        "excluded_too_many_exact": {"terms": [], "volume": 0},
        "excluded_redundant_exact": {"terms": [], "volume": 0},
        "unbound": {"terms": [], "volume": 0},
    }
    multi_context_exact: list[tuple[str, int, int, int]] = []
    for query, count in terms.items():
        key = query.casefold()
        admitted = admitted_by_label.get(key)
        if admitted:
            bucket = "admitted_exact"
            if len(admitted) > 1:
                multi_context_exact.append((query, count, len(admitted), len({str(r.get('id')) for r in admitted})))
        elif key in many_labels:
            bucket = "excluded_too_many_exact"
        elif key in redundant_labels:
            bucket = "excluded_redundant_exact"
        else:
            bucket = "unbound"
        buckets[bucket]["terms"].append((query, count))
        buckets[bucket]["volume"] += count

    bucket_summary = {}
    for name, data in buckets.items():
        top = sorted(data["terms"], key=lambda x: (-x[1], x[0]))[:100]
        bucket_summary[name] = {
            "distinct_terms": len(data["terms"]),
            "distinct_term_share_pct": pct(len(data["terms"]), len(terms)),
            "query_volume": data["volume"],
            "query_volume_share_pct": pct(data["volume"], total_volume),
            "top_terms": [{"query": q, "count": c} for q, c in top],
        }

    excluded_terms = bucket_summary["excluded_too_many_exact"]["distinct_terms"] + bucket_summary["excluded_redundant_exact"]["distinct_terms"]
    excluded_volume = bucket_summary["excluded_too_many_exact"]["query_volume"] + bucket_summary["excluded_redundant_exact"]["query_volume"]
    admitted_volume = bucket_summary["admitted_exact"]["query_volume"]
    multi_context_volume = sum(x[1] for x in multi_context_exact)

    aggregate = {
        "schema_version": 1,
        "taxonomy_version": version,
        "generator_source_commit": source_commit,
        "query_corpus": {
            "zip_sha256": hashlib.sha256(zip_bytes).hexdigest(),
            "start_date": corpus.get("start_date"),
            "end_date": corpus.get("end_date"),
            "distinct_terms": len(terms),
            "total_query_volume": total_volume,
            "semantics": "query string plus aggregated frequency; no selected canonical taxonomy ID",
        },
        "exact_text_binding": bucket_summary,
        "excluded_yv_title_vocabulary": {
            "distinct_observed_excluded_labels": excluded_terms,
            "query_volume": excluded_volume,
            "query_volume_share_pct": pct(excluded_volume, total_volume),
            "share_of_all_exact_yv_or_excluded_label_volume_pct": pct(excluded_volume, admitted_volume + excluded_volume),
        },
        "admitted_exact_multi_context": {
            "distinct_queries": len(multi_context_exact),
            "query_volume": multi_context_volume,
            "query_volume_share_pct": pct(multi_context_volume, total_volume),
            "share_of_admitted_exact_volume_pct": pct(multi_context_volume, admitted_volume),
            "all_multirow_matches_same_job_title_id": all(x[3] == 1 for x in multi_context_exact),
            "top_queries": [
                {"query": q, "count": c, "yv_rows": row_count, "unique_ids": id_count}
                for q, c, row_count, id_count in sorted(multi_context_exact, key=lambda x: (-x[1], x[0]))[:100]
            ],
        },
    }
    (out / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"# YV observed query-language coverage — taxonomy v{version}", "",
        f"Source generator commit: `{source_commit}`.",
        f"Corpus: **{len(terms):,} distinct terms**, **{total_volume:,} aggregate searches**, {corpus.get('start_date')} → {corpus.get('end_date')}.", "",
        "The corpus contains query strings and counts only. It is not query→selected-ID ground truth.", "",
        "| Exact textual class | distinct terms | term share | query volume | volume share |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in ("admitted_exact", "excluded_too_many_exact", "excluded_redundant_exact", "unbound"):
        r = bucket_summary[name]
        lines.append(f"| `{name}` | {r['distinct_terms']:,} | {r['distinct_term_share_pct']}% | {r['query_volume']:,} | {r['query_volume_share_pct']}% |")
    lines += [
        "",
        f"Observed exact queries using generator-excluded job-title labels: **{excluded_terms:,} terms**, **{excluded_volume:,} searches = {pct(excluded_volume,total_volume)}%** of all corpus volume.",
        f"These excluded-title queries account for **{pct(excluded_volume, admitted_volume + excluded_volume)}%** of the volume that exactly matches either an admitted YV label or an excluded YV title label.",
        "",
        f"Admitted exact labels with multiple YV context rows: **{len(multi_context_exact):,} query strings**, **{multi_context_volume:,} searches = {pct(multi_context_volume,total_volume)}%** of all volume.",
        "",
        "## Guardrail", "",
        "Exact textual binding is the only labelled association claimed here. Unbound query strings remain observed language, not inferred taxonomy labels.", "",
    ]
    summary = "\n".join(lines)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
