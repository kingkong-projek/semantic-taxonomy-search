#!/usr/bin/env python3
"""Bind excluded-title benchmark review candidates to the pinned YV generator diagnostics.

The benchmark seed builder can derive the omitted 205 active job-title IDs from
published YV admission, but the exclusion *reason* is product-generator
provenance. This verifier therefore replaces any heuristic reason with the
exact, version-bound diagnostic family from the accepted generator snapshot.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_COMMIT = "6dd9e4737d7db3cb2709f8082808b88e5c89ed6e"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise RuntimeError(f"{path}:{line_number}: expected JSON object")
            rows.append(value)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--version", default="31")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    version = str(args.version)
    source_dir = Path(args.source_dir)
    source_commit = (source_dir / "SOURCE_COMMIT.txt").read_text(encoding="utf-8").strip()
    if source_commit != EXPECTED_SOURCE_COMMIT:
        raise RuntimeError(
            f"unexpected YV generator commit: expected {EXPECTED_SOURCE_COMMIT}, got {source_commit}"
        )

    many = load_json(source_dir / f"data/jobbtitlar-mappad-till-för-många-yb-t{version}.json")
    redundant = load_json(source_dir / f"data/jobbtitlar-del-av-yb-t{version}.json")
    if not isinstance(many, dict) or not isinstance(redundant, dict):
        raise RuntimeError("generator diagnostics must be JSON objects")
    if len(many) != 104 or len(redundant) != 101:
        raise RuntimeError(
            f"accepted v{version} policy counts drifted: too_many={len(many)} redundant={len(redundant)}"
        )
    if set(many) & set(redundant):
        raise RuntimeError("generator diagnostic label families unexpectedly overlap")

    rows = read_jsonl(Path(args.input))
    if len(rows) != 205:
        raise RuntimeError(f"expected 205 excluded-title review rows, got {len(rows)}")

    expected_labels = set(many) | set(redundant)
    actual_labels: set[str] = set()
    reason_counts = {"too_many_parents": 0, "redundant_label": 0}

    for row in rows:
        label = str(row.get("query") or "")
        if not label:
            raise RuntimeError("review row missing query label")
        if label in actual_labels:
            raise RuntimeError(f"duplicate excluded-title label in review rows: {label!r}")
        actual_labels.add(label)

        if label in many:
            reason = "too_many_parents"
            expected_parent_labels = {str(v) for v in many[label]}
        elif label in redundant:
            reason = "redundant_label"
            expected_parent_labels = {str(v) for v in redundant[label]}
        else:
            raise RuntimeError(f"excluded title {label!r} absent from pinned generator diagnostics")

        candidate_parent_labels = {
            str(item.get("label") or "")
            for item in row.get("candidate_occupation_identities", [])
            if isinstance(item, dict)
        }
        if candidate_parent_labels != expected_parent_labels:
            raise RuntimeError(
                f"parent-set drift for {label!r}: taxonomy={sorted(candidate_parent_labels)!r} "
                f"generator={sorted(expected_parent_labels)!r}"
            )

        row["yv_exclusion_reason"] = reason
        row["generator_policy_evidence"] = {
            "source_commit": source_commit,
            "diagnostic_family": reason,
            "taxonomy_version": int(version),
        }
        reason_counts[reason] += 1

    if actual_labels != expected_labels:
        raise RuntimeError(
            f"review population != generator diagnostic population: "
            f"missing={len(expected_labels-actual_labels)} extra={len(actual_labels-expected_labels)}"
        )
    if reason_counts != {"too_many_parents": 104, "redundant_label": 101}:
        raise RuntimeError(f"unexpected final reason counts: {reason_counts}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    manifest = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "generator_source_commit": source_commit,
        "review_candidates": len(rows),
        "reason_counts": reason_counts,
        "authority_boundary": (
            "exclusion reason comes from the pinned product generator diagnostics; "
            "candidate occupation parents remain routing/context evidence and are not auto-scored destination truth"
        ),
    }
    manifest_path = Path(args.manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
