#!/usr/bin/env python3
"""Build the complete pinned 205-title YV generator-exclusion population."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

EXPECTED_GENERATOR_COMMIT = "6dd9e4737d7db3cb2709f8082808b88e5c89ed6e"
EXPECTED_QUERY_SHA256 = "01a2550473091b06fdaaf450015eeea13b301471f1c78f5fb0dc8d3499645ae2"


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generator-dir", required=True)
    ap.add_argument("--output", default="artifacts/yv-excluded-title-population-v31.json")
    args = ap.parse_args()

    root = Path(args.generator_dir)
    commit = (root / "SOURCE_COMMIT.txt").read_text(encoding="utf-8").strip()
    if commit != EXPECTED_GENERATOR_COMMIT:
        raise RuntimeError(f"unexpected generator commit {commit}")

    many = json.loads((root / "data/jobbtitlar-mappad-till-för-många-yb-t31.json").read_text(encoding="utf-8"))
    redundant = json.loads((root / "data/jobbtitlar-del-av-yb-t31.json").read_text(encoding="utf-8"))
    if len(many) != 104 or len(redundant) != 101:
        raise RuntimeError(f"generator diagnostics drifted: too_many={len(many)} redundant={len(redundant)}")

    zip_path = root / "data/sokningar-platsbanken.json.zip"
    body = zip_path.read_bytes()
    actual_sha = hashlib.sha256(body).hexdigest()
    if actual_sha != EXPECTED_QUERY_SHA256:
        raise RuntimeError(f"query corpus drift: {actual_sha}")
    with zipfile.ZipFile(zip_path) as zf:
        names = [name for name in zf.namelist() if name.endswith(".json")]
        if len(names) != 1:
            raise RuntimeError(f"expected one JSON in query archive, got {names}")
        query_doc = json.load(zf.open(names[0]))
    terms = query_doc.get("search_terms")
    if not isinstance(terms, dict):
        raise RuntimeError("query corpus missing search_terms")
    counts = {norm(k): int(v) for k, v in terms.items()}

    cases = []
    seen = set()
    for reason, mapping in (("redundant_label", redundant), ("too_many_parents", many)):
        for label, parents in mapping.items():
            key = norm(label)
            if key in seen:
                raise RuntimeError(f"duplicate excluded title across diagnostics: {label}")
            seen.add(key)
            parent_labels = sorted({str(x).strip() for x in parents if str(x).strip()}, key=str.casefold)
            if not parent_labels:
                raise RuntimeError(f"excluded title has no mapped parents: {label}")
            cases.append({
                "query": str(label),
                "reason": reason,
                "observed_count": counts.get(key, 0),
                "target_parent_labels": parent_labels,
            })

    if len(cases) != 205:
        raise RuntimeError(f"expected 205 excluded title cases, got {len(cases)}")
    cases.sort(key=lambda x: (-x["observed_count"], norm(x["query"])))

    result = {
        "schema_version": 1,
        "taxonomy_version": 31,
        "generator_commit": commit,
        "query_corpus_sha256": actual_sha,
        "query_corpus_start_date": query_doc.get("start_date"),
        "query_corpus_end_date": query_doc.get("end_date"),
        "cases": cases,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "cases": len(cases),
        "redundant_label": sum(1 for x in cases if x["reason"] == "redundant_label"),
        "too_many_parents": sum(1 for x in cases if x["reason"] == "too_many_parents"),
        "observed_exact_volume": sum(x["observed_count"] for x in cases),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
