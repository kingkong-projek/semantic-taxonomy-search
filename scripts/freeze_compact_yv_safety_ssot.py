#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

src = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/compact-yv-profile-safety-v31")
manifest = json.loads((src / "manifest.json").read_text(encoding="utf-8"))

if manifest.get("taxonomy_version") != 31:
    raise RuntimeError("unexpected taxonomy version")
if manifest.get("multi_parent", {}).get("population") != 541:
    raise RuntimeError("multi-parent population drift")
if manifest.get("multi_parent", {}).get("selected") != 20:
    raise RuntimeError("multi-parent compact slice drift")
if manifest.get("excluded_routing", {}).get("population") != 205:
    raise RuntimeError("excluded population drift")
if manifest.get("excluded_routing", {}).get("selected") != 20:
    raise RuntimeError("excluded compact slice drift")
if manifest.get("excluded_routing", {}).get("reason_counts") != {"redundant_label": 10, "too_many_parents": 10}:
    raise RuntimeError(f"unexpected selected reason counts: {manifest.get('excluded_routing', {}).get('reason_counts')}")

multi_path = src / "multi-parent-auto.jsonl"
excluded_path = src / "excluded-routing-review.jsonl"
multi_rows = [json.loads(x) for x in multi_path.read_text(encoding="utf-8").splitlines() if x.strip()]
excluded_rows = [json.loads(x) for x in excluded_path.read_text(encoding="utf-8").splitlines() if x.strip()]
if len(multi_rows) != 20 or len(excluded_rows) != 20:
    raise RuntimeError("compact row count drift")
if not all(r.get("adjudication", {}).get("status") == "AUTO_HIGH_CONFIDENCE" for r in multi_rows):
    raise RuntimeError("multi-parent slice must remain source-truth auto-scored")
if not all(r.get("adjudication", {}).get("status") == "PENDING_HUMAN_REVIEW" for r in excluded_rows):
    raise RuntimeError("excluded routing slice must remain pending review")
if any(r.get("adjudication", {}).get("must") or r.get("adjudication", {}).get("acceptable") or r.get("adjudication", {}).get("must_not") for r in excluded_rows):
    raise RuntimeError("excluded routing review gained unreviewed destination labels")

out = Path("research/benchmark/v31/yv-profile-safety")
out.mkdir(parents=True, exist_ok=True)
for name in ("manifest.json", "multi-parent-auto.jsonl", "excluded-routing-review.jsonl"):
    shutil.copyfile(src / name, out / name)

hashes = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in ("manifest.json", "multi-parent-auto.jsonl", "excluded-routing-review.jsonl")}

mp = manifest["multi_parent"]
ex = manifest["excluded_routing"]
finding = f"""# Compact YV reference-profile safety slices — taxonomy v31

**Status:** measured/frozen where source truth permits; routing review remains pending  
**Measured:** 2026-09-06

These slices test YV-specific admission/routing semantics on top of the reusable `occupation` retrieval core. They are **not** the generic engine scope.

## Multi-parent ambiguity

Population: **{mp['population']}** admitted job-title IDs with multiple YV occupation contexts.

Simple-first selection: the **20 highest-volume exact title queries** from the pinned observed-query corpus, totaling **{mp['selected_query_volume']:,} searches**.

The 20 cases are `AUTO_HIGH_CONFIDENCE` because the exact canonical job-title identity, typed occupation contexts and published YV admission are all source-attested. Every case requires all admitted context-specific identities to remain available; the system may not collapse them prematurely.

Top examples:

""" + "\n".join(
    f"- `{row['query']}` — {row['count']:,} searches, {row['contexts']} contexts"
    for row in mp["top_queries"][:10]
) + f"""

## Excluded-title routing review

Population: **{ex['population']}** active job-title IDs excluded by the pinned YV generator policy.

Simple-first selection: the **20 highest-volume exact excluded-title queries**, totaling **{ex['selected_query_volume']:,} searches**. In this top-20 slice the generator reasons are exactly **10 `redundant_label` + 10 `too_many_parents`**.

These rows remain `PENDING_HUMAN_REVIEW`. The generator exclusion reason is source truth; related occupation identities are only routing/context candidates and are **not** auto-promoted to benchmark destination truth.

Top examples:

""" + "\n".join(
    f"- `{row['query']}` — {row['count']:,} searches — `{row['reason']}`"
    for row in ex["top_queries"][:10]
) + f"""

## Why this is enough for now

The initial safety budget follows the Pareto rule. We do not manually adjudicate all 541 multi-parent titles or all 205 excluded titles before the simple system has demonstrated that broader coverage changes a decision. The remaining small safety requirement is hard-negative/no-match/abstention judgment.

## Reproducibility

- generator commit: `{manifest['sources']['generator_commit']}`
- query corpus SHA-256: `{manifest['sources']['query_corpus']['sha256']}`
- taxonomy SHA-256: `{manifest['sources']['taxonomy_sha256']}`
- Yrkesväljaren SHA-256: `{manifest['sources']['yrkesvaljaren_sha256']}`
- frozen manifest SHA-256: `{hashes['manifest.json']}`
- multi-parent JSONL SHA-256: `{hashes['multi-parent-auto.jsonl']}`
- excluded-routing JSONL SHA-256: `{hashes['excluded-routing-review.jsonl']}`
"""
Path("docs/findings/compact-yv-profile-safety-v31.md").write_text(finding, encoding="utf-8")

plan_path = Path("docs/research-plan.md")
plan = plan_path.read_text(encoding="utf-8")
old = "- [ ] compact safety/regression slices: multi-parent ambiguity, excluded-YV routing, hard negatives and no-match/abstention"
new = """- [x] compact high-volume **YV reference-profile multi-parent ambiguity** slice: 20 source-truth exact-title cases selected by observed frequency from the 541-ID population; all admitted context identities are required
- [x] compact high-volume **excluded-YV routing review** slice: 20 highest-volume excluded title queries selected from the 205-ID population; generator reason is verified, destination judgment remains `PENDING_HUMAN_REVIEW`
- [ ] compact hard-negative + no-match/abstention safety slice; keep it small and adjudicated rather than manufacturing negatives

Evidence: `docs/findings/compact-yv-profile-safety-v31.md` and `research/benchmark/v31/yv-profile-safety/`."""
if plan.count(old) != 1:
    raise RuntimeError(f"expected one safety checklist marker, got {plan.count(old)}")
plan_path.write_text(plan.replace(old, new, 1), encoding="utf-8")

print(json.dumps({"hashes": hashes, "multi_parent": mp, "excluded_routing": ex}, ensure_ascii=False, indent=2, sort_keys=True))
