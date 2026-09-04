#!/usr/bin/env python3
"""Validate the published YV v31 exclusion policy against its open generator.

Input is a checked-out/snapshotted public Yrkesväljaren generator repository.
The script compares its committed v31 output with the published file, resolves
its diagnostic exclusion files against the active immutable taxonomy snapshot,
and identifies active v31 titles that moved from YV v30 to exclusion in v31.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

USER_AGENT = "semantic-taxonomy-search-yv-generator-policy/0.1"


def fetch(url: str) -> tuple[bytes, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=180) as r:
        body = r.read()
    return body, json.loads(body)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-dir", required=True)
    ap.add_argument("--version", default="31")
    ap.add_argument("--previous-version", default="30")
    ap.add_argument("--output-dir", default="artifacts/yv-generator-policy-v31")
    args = ap.parse_args()

    src = Path(args.source_dir)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    version = str(args.version)
    previous = str(args.previous_version)

    source_commit = (src / "SOURCE_COMMIT.txt").read_text(encoding="utf-8").strip()
    generator_file = src / "utils/create_weighted_occupational_data.py"
    generator_text = generator_file.read_text(encoding="utf-8")

    required_code_fragments = {
        "redundancy_predicate": "return all(title.lower() in o.lower() for o in occupations)",
        "single_parent_redundancy_gate": "if check_if_job_title_in_all_occupations(i[\"preferred_label\"], mappedOccupationNames):",
        "max_three_parent_gate": "if len(related) <= 3:",
        "too_many_diagnostic": "jobTitlesMappedToManyOccupations[i[\"preferred_label\"]] = mappedOccupationNames",
    }
    missing_fragments = [name for name, fragment in required_code_fragments.items() if fragment not in generator_text]
    if missing_fragments:
        raise RuntimeError(f"generator policy source changed; missing expected fragments: {missing_fragments}")

    repo_output_path = src / f"output/v1/yrkesvaljaren-t{version}.json"
    repo_output_bytes = repo_output_path.read_bytes()
    repo_output = json.loads(repo_output_bytes)
    published_url = f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{version}.json"
    published_bytes, published = fetch(published_url)
    if repo_output_bytes != published_bytes:
        raise RuntimeError(
            f"generator committed output differs from published v{version}: repo={sha(repo_output_bytes)} published={sha(published_bytes)}"
        )

    taxonomy_url = (
        f"https://data.jobtechdev.se/taxonomy/version/{version}/query/"
        "concepts-and-common-relations/concepts-and-common-relations.json"
    )
    taxonomy_bytes, taxonomy = fetch(taxonomy_url)
    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy snapshot missing data.concepts")
    active_titles = [c for c in concepts if isinstance(c, dict) and c.get("type") == "job-title"]
    active_title_ids = {str(c["id"]) for c in active_titles if c.get("id")}
    label_to_ids: dict[str, set[str]] = defaultdict(set)
    id_to_label: dict[str, str] = {}
    for c in active_titles:
        cid = str(c.get("id") or "")
        label = str(c.get("preferred_label") or "")
        if cid:
            id_to_label[cid] = label
            label_to_ids[label].add(cid)

    current_rows = published.get("data")
    if not isinstance(current_rows, list):
        raise RuntimeError("published YV data not list")
    current_title_ids = {str(r["id"]) for r in current_rows if isinstance(r, dict) and r.get("type") == "job-title"}
    missing_active_ids = active_title_ids - current_title_ids

    many = load(src / f"data/jobbtitlar-mappad-till-för-många-yb-t{version}.json")
    redundant = load(src / f"data/jobbtitlar-del-av-yb-t{version}.json")
    if not isinstance(many, dict) or not isinstance(redundant, dict):
        raise RuntimeError("YV diagnostic files are not objects")
    if set(many) & set(redundant):
        raise RuntimeError("YV diagnostic exclusion families overlap by label")

    diagnostic_ids: dict[str, str] = {}
    ambiguous_diagnostic_labels: dict[str, list[str]] = {}
    unknown_diagnostic_labels: list[str] = []
    for reason, doc in (("too_many_parents", many), ("redundant_label", redundant)):
        for label in doc:
            ids = sorted(label_to_ids.get(label, set()))
            if len(ids) == 1:
                diagnostic_ids[ids[0]] = reason
            elif len(ids) == 0:
                unknown_diagnostic_labels.append(label)
            else:
                ambiguous_diagnostic_labels[label] = ids

    if unknown_diagnostic_labels or ambiguous_diagnostic_labels:
        raise RuntimeError(
            f"cannot map diagnostics uniquely: unknown={len(unknown_diagnostic_labels)} ambiguous={len(ambiguous_diagnostic_labels)}"
        )
    if set(diagnostic_ids) != missing_active_ids:
        raise RuntimeError(
            f"diagnostics do not exactly explain active YV omissions: missing={len(missing_active_ids)} diagnostics={len(diagnostic_ids)} "
            f"only_missing={len(missing_active_ids-set(diagnostic_ids))} only_diagnostic={len(set(diagnostic_ids)-missing_active_ids)}"
        )

    previous_url = f"https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t{previous}.json"
    previous_bytes, previous_doc = fetch(previous_url)
    previous_rows = previous_doc.get("data")
    if not isinstance(previous_rows, list):
        raise RuntimeError("previous YV data not list")
    previous_by_id = {
        str(r["id"]): r for r in previous_rows
        if isinstance(r, dict) and r.get("type") == "job-title" and r.get("id")
    }
    active_dropouts = sorted((set(previous_by_id) - current_title_ids) & active_title_ids)
    dropout_details = []
    for cid in active_dropouts:
        old = previous_by_id[cid]
        label = id_to_label[cid]
        reason = diagnostic_ids.get(cid)
        parents = many.get(label) if reason == "too_many_parents" else redundant.get(label)
        dropout_details.append({
            "id": cid,
            "preferred_label": label,
            "previous_occupation_name_id": old.get("occupation_name_id"),
            "previous_occupation_name_preferred_label": old.get("occupation_name_preferred_label"),
            "v31_exclusion_reason": reason,
            "v31_mapped_occupation_labels": parents,
        })

    aggregate = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "taxonomy_version": version,
        "previous_taxonomy_version": previous,
        "generator_source": {
            "remote": "https://gitlab.com/arbetsformedlingen/taxonomy-dev/backend/yrkesvaljaren.git",
            "commit": source_commit,
            "policy_file": "utils/create_weighted_occupational_data.py",
            "policy_file_sha256": sha(generator_file.read_bytes()),
            "required_policy_fragments_present": True,
        },
        "published_output": {
            "url": published_url,
            "sha256": sha(published_bytes),
            "bytes": len(published_bytes),
            "generator_repo_output_exact_byte_match": True,
            "active_job_title_universe": len(active_title_ids),
            "published_unique_job_title_ids": len(current_title_ids),
            "missing_active_job_title_ids": len(missing_active_ids),
        },
        "exclusion_policy": {
            "too_many_parents": {
                "threshold": ">3 occupation-name relations",
                "titles": len(many),
                "parent_count_distribution": dict(sorted(Counter(len(v) for v in many.values()).items())),
            },
            "redundant_label": {
                "predicate": "job-title preferred label is a case-insensitive substring of every mapped occupation-name preferred label",
                "titles": len(redundant),
                "parent_count_distribution": dict(sorted(Counter(len(v) for v in redundant.values()).items())),
            },
            "total_diagnostic_titles": len(diagnostic_ids),
            "exactly_equals_missing_active_population": True,
        },
        "v30_to_v31": {
            "previous_url": previous_url,
            "previous_sha256": sha(previous_bytes),
            "active_v31_titles_present_in_v30_but_absent_v31": len(active_dropouts),
            "dropouts": dropout_details,
        },
        "taxonomy_snapshot": {"url": taxonomy_url, "sha256": sha(taxonomy_bytes)},
    }

    (out / "aggregate.json").write_text(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = f"""# YV generator exclusion policy — taxonomy v{version}

Generator source commit: `{source_commit}`.
Generator-committed v{version} output is byte-identical to published YV: `{sha(published_bytes)}`.

Active job-title universe: **{len(active_title_ids):,}**.
Published unique YV job-title IDs: **{len(current_title_ids):,}**.
Missing active titles: **{len(missing_active_ids):,}**.

Exclusion diagnostics explain the missing population exactly:

- more than three mapped occupation-names: **{len(many):,}**;
- job-title label contained in every mapped occupation label: **{len(redundant):,}**;
- total: **{len(diagnostic_ids):,}**;
- diagnostic IDs exactly equal missing active IDs: **true**.

Active v31 titles present in YV v{previous} but absent in v{version}: **{len(active_dropouts)}**.

```json
{json.dumps(dropout_details, ensure_ascii=False, indent=2)}
```
"""
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
