#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

GENERATOR_COMMIT = "6dd9e4737d7db3cb2709f8082808b88e5c89ed6e"
YV_URL = "https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t31.json"
YV_SHA256 = "1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49"
QUERY_ZIP_SHA256 = "01a2550473091b06fdaaf450015eeea13b301471f1c78f5fb0dc8d3499645ae2"
CASES = ["projektledare", "projektkoordinator", "kock", "säljare"]


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "semantic-taxonomy-search-persona-adjudication/0.1"})
    with urllib.request.urlopen(req, timeout=240) as response:
        return response.read()


def direct_score(label: str, query: str) -> float | None:
    label_n = norm(label)
    query_n = norm(query)
    tokens = [token for token in query_n.split(" ") if token]
    if label_n == query_n:
        return 1.0
    if len(tokens) > 1:
        return 0.98 if all(token in label_n for token in tokens) else None
    if label_n.startswith(query_n):
        return 0.99
    if query_n in label_n:
        return 0.95
    return None


def display(row: dict[str, Any]) -> str:
    parent = str(row.get("occupation_name_preferred_label") or "")
    return f"{row.get('preferred_label', '')} ({parent})" if parent else str(row.get("preferred_label") or "")


def direct_results(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    hits = []
    for row in rows:
        score = direct_score(str(row.get("preferred_label") or ""), query)
        if score is None:
            continue
        copy = dict(row)
        copy["score"] = score
        copy["display"] = display(row)
        hits.append(copy)
    hits.sort(key=lambda row: (-float(row["score"]), -float(row.get("weight") or 0), str(row["display"]).casefold()))
    return hits


def load_query_counts(generator: Path) -> dict[str, int]:
    path = generator / "data/sokningar-platsbanken.json.zip"
    body = path.read_bytes()
    actual = sha256(body)
    if actual != QUERY_ZIP_SHA256:
        raise RuntimeError(f"query corpus hash drift: {actual}")
    with zipfile.ZipFile(path) as zf:
        names = [name for name in zf.namelist() if name.endswith('.json')]
        if len(names) != 1:
            raise RuntimeError(f"unexpected query corpus members: {names}")
        doc = json.load(zf.open(names[0]))
    return {norm(k): int(v) for k, v in doc["search_terms"].items()}


def normalized_lookup(mapping: dict[str, Any], query: str) -> tuple[str, Any] | None:
    q = norm(query)
    for key, value in mapping.items():
        if norm(key) == q:
            return str(key), value
    return None


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": row.get("type"),
        "id": row.get("id"),
        "preferred_label": row.get("preferred_label"),
        "occupation_name_id": row.get("occupation_name_id"),
        "occupation_name_preferred_label": row.get("occupation_name_preferred_label"),
        "display": row.get("display") or display(row),
        "weight": row.get("weight"),
        "score": row.get("score"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generator-dir", required=True)
    ap.add_argument("--output", default="artifacts/yv-persona-title-adjudication-v31.json")
    args = ap.parse_args()
    generator = Path(args.generator_dir)

    source_commit = (generator / "SOURCE_COMMIT.txt").read_text().strip()
    if source_commit != GENERATOR_COMMIT:
        raise RuntimeError(f"generator commit drift: {source_commit}")

    many = json.loads((generator / "data/jobbtitlar-mappad-till-för-många-yb-t31.json").read_text())
    redundant = json.loads((generator / "data/jobbtitlar-del-av-yb-t31.json").read_text())
    query_counts = load_query_counts(generator)

    body = fetch(YV_URL)
    actual_yv_sha = sha256(body)
    if actual_yv_sha != YV_SHA256:
        raise RuntimeError(f"YV source drift: {actual_yv_sha}")
    yv = json.loads(body)
    rows = yv["data"]

    output_cases = []
    for query in CASES:
        many_hit = normalized_lookup(many, query)
        redundant_hit = normalized_lookup(redundant, query)
        if many_hit and redundant_hit:
            raise RuntimeError(f"case in both exclusion diagnostics: {query}")
        exclusion_reason = "too_many_parents" if many_hit else "redundant_label" if redundant_hit else None
        mapped_parents = list(many_hit[1] if many_hit else redundant_hit[1] if redundant_hit else [])

        exact_rows = [row for row in rows if norm(row.get("preferred_label")) == norm(query)]
        direct = direct_results(rows, query)
        mapped_parent_positions = []
        mapped_norm = {norm(label) for label in mapped_parents}
        for idx, row in enumerate(direct, start=1):
            if row.get("type") == "occupation-name" and norm(row.get("preferred_label")) in mapped_norm:
                mapped_parent_positions.append({"rank": idx, "label": row.get("preferred_label"), "id": row.get("id")})

        output_cases.append({
            "query": query,
            "observed_exact_query_count": query_counts.get(norm(query), 0),
            "generator_exclusion_reason": exclusion_reason,
            "generator_mapped_parent_count": len(mapped_parents),
            "generator_mapped_parent_labels": mapped_parents,
            "published_exact_row_count": len(exact_rows),
            "published_exact_rows": [compact_row(row) for row in exact_rows],
            "current_direct_result_count": len(direct),
            "current_direct_top10": [compact_row(row) for row in direct[:10]],
            "mapped_parent_positions_in_direct_results": mapped_parent_positions,
            "mapped_parent_in_direct_top5": any(item["rank"] <= 5 for item in mapped_parent_positions),
            "mapped_parent_in_direct_top10": any(item["rank"] <= 10 for item in mapped_parent_positions),
        })

    result = {
        "schema_version": 1,
        "taxonomy_version": 31,
        "classification": "source-adjudication of frozen synthetic persona title queries; observed query counts are real corpus counts, persona intent remains synthetic",
        "sources": {
            "generator_commit": GENERATOR_COMMIT,
            "yv_sha256": YV_SHA256,
            "query_corpus_sha256": QUERY_ZIP_SHA256,
        },
        "cases": output_cases,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
