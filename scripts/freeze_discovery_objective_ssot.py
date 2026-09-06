#!/usr/bin/env python3
from __future__ import annotations

import hashlib, json, shutil, sys
from pathlib import Path

src = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pareto-holdout-discovery-v31.json")
x = json.loads(src.read_text(encoding="utf-8"))
if x.get("primary_k") != 5 or not str(x.get("objective", "")).startswith("discovery:"):
    raise RuntimeError("discovery scorecard shape drift")
c0 = x["C0"]["primary"]; c1 = x["C1"]["primary"]
expected = {
    "c0_d5": 59.765,
    "c1_d5": 84.788,
    "c1_d10": 84.788,
    "c1_abstain": 100.0,
}
actual = {
    "c0_d5": c0["volume_weighted_discovery_success_at_5_pct"],
    "c1_d5": c1["volume_weighted_discovery_success_at_5_pct"],
    "c1_d10": c1["volume_weighted_discovery_success_at_10_pct"],
    "c1_abstain": c1["volume_weighted_no_match_abstention_pct"],
}
if actual != expected:
    raise RuntimeError(f"discovery metric drift: {actual}")

out = Path("research/evaluation/v31/pareto-holdout-discovery.json")
out.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(src, out)
digest = hashlib.sha256(out.read_bytes()).hexdigest()

finding = f"""# Discovery-oriented evaluation objective — taxonomy v31

**Status:** adopted as primary product evaluation objective  
**Measured:** 2026-09-06

The reusable engine is a **discovery system**, not a top-1 classifier. A consuming selector shows a small candidate list and succeeds when the user can find the occupation or skill they meant. Exact rank 1 is useful but secondary.

## Primary semantics

For positive `SINGLE` or `AMBIGUOUS` queries:

> **Discovery Success@5** = at least one judged relevant canonical destination appears among the first five visible candidates.

For `NO_MATCH`:

> success = abstain rather than fabricate a plausible occupation/skill.

Use **@5** as the primary small-list target. Keep @10 as a diagnostic/robustness view, together with MRR/top-1/nDCG for ordering quality.

For ambiguous/broad queries, several useful candidates are desirable. Do not punish a system merely because the ultimately selected identity is not rank 1 when it is already easy to discover in the visible list.

## Current holdout result

On the independently model-adjudicated 36-case Pareto holdout (208.6M observed searches):

| metric | C0 | C1 |
|---|---:|---:|
| volume-weighted Discovery Success@5 | {c0['volume_weighted_discovery_success_at_5_pct']}% | **{c1['volume_weighted_discovery_success_at_5_pct']}%** |
| volume-weighted Discovery Success@10 | {c0['volume_weighted_discovery_success_at_10_pct']}% | **{c1['volume_weighted_discovery_success_at_10_pct']}%** |
| NO_MATCH abstention | {c0['no_match_abstention_pct']}% | **{c1['no_match_abstention_pct']}%** |
| volume-weighted NO_MATCH abstention | {c0['volume_weighted_no_match_abstention_pct']}% | **{c1['volume_weighted_no_match_abstention_pct']}%** |

C1 gains **+{x['delta']['volume_weighted_discovery_success_at_5_points']} percentage points** of volume-weighted Discovery Success@5 over C0.

The identical C1 @5 and @10 score means every currently recoverable judged-positive holdout case is already found within the first five; expanding the UI list from five to ten does not recover additional cases in this slice.

## Metric hierarchy

Primary product metrics:

1. Discovery Success@5 / volume-weighted Discovery Success@5;
2. abstention correctness for NO_MATCH;
3. hard-negative violation rate;
4. per-stratum discovery success and coverage.

Secondary ranking diagnostics:

- top-1 success / precision where one answer is actually justified;
- Recall@10, MRR, nDCG;
- judged-positive density/coverage in the visible list, interpreted cautiously because broad-query judgments are not exhaustive.

This metric hierarchy applies to both occupation and skill discovery. Consumer UIs may choose a different visible K, but the research benchmark should keep K small and explicit rather than optimize an unbounded candidate list.

Evaluation SHA-256: `{digest}`
"""
Path("docs/findings/discovery-objective-v31.md").write_text(finding, encoding="utf-8")

p = Path("docs/research-plan.md")
plan = p.read_text(encoding="utf-8")
old = "At minimum:\n\n- Recall@K;\n- MRR / nDCG@K;\n- top-1 precision where one answer is justified;"
new = """Primary product objective is **discovery**, not exact top-1 classification. A small visible candidate list succeeds when it contains what the user meant; broad/ambiguous queries may correctly expose several plausible canonical candidates. Use **Discovery Success@5** as the primary positive-intent metric and correct abstention as the primary NO_MATCH metric. Top-1 remains secondary ranking diagnostics.\n\nAt minimum:\n\n- **Discovery Success@5**, including volume-weighted and per-stratum views;\n- abstention precision/recall for `NO_MATCH`;\n- hard-negative violation rate;\n- Recall@K;\n- MRR / nDCG@K;\n- top-1 precision where one answer is justified, as a secondary ordering metric;"""
if plan.count(old) != 1: raise RuntimeError(f"metrics anchor drift: {plan.count(old)}")
plan = plan.replace(old, new, 1)

anchor = "Evidence: `docs/findings/pareto-holdout-c1-v31.md`, `research/benchmark/v31/pareto-model-holdout/` and `research/evaluation/v31/pareto-holdout-c0-c1.json`."
addition = anchor + f"""\n\nDiscovery framing: because the product goal is to help a user **find** the intended identity in a small result list rather than classify every query to rank 1, the primary holdout metric is now Discovery Success@5. On the same untouched holdout, C1 reaches **{c1['volume_weighted_discovery_success_at_5_pct']}% volume-weighted Discovery Success@5** versus C0 {c0['volume_weighted_discovery_success_at_5_pct']}%; C1 @5 equals @10, so no additional judged-positive cases require positions 6–10 in this slice. Top-1 remains secondary diagnostics.\n\nEvidence: `docs/findings/discovery-objective-v31.md` and `research/evaluation/v31/pareto-holdout-discovery.json`."""
if plan.count(anchor) != 1: raise RuntimeError(f"holdout evidence anchor drift: {plan.count(anchor)}")
plan = plan.replace(anchor, addition, 1)

old = "- [ ] **complete planned C retrieval vocabulary next:** add exact active job-title preferred-label → typed occupation-name parent routing; 10/12 remaining C1 holdout top-1 failures are exact measured job-title routes. Evaluate on a new next-volume sentinel before D/ESCO."
new = "- [ ] **complete planned C retrieval vocabulary next:** add exact active job-title preferred-label → typed occupation-name parent routing. Optimize/evaluate primarily for **Discovery Success@5**, not rank 1; the holdout shows exact job-title routing is the dominant remaining candidate-generation gap. Evaluate on a new next-volume sentinel before D/ESCO."
if plan.count(old) != 1: raise RuntimeError(f"planned C anchor drift: {plan.count(old)}")
plan = plan.replace(old, new, 1)
p.write_text(plan, encoding="utf-8")
print(json.dumps({"sha256":digest,"C0":c0,"C1":c1},indent=2,sort_keys=True))
