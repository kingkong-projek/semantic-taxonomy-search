#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

bench_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/holdout-adjudicated")
eval_path = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/pareto-holdout-c0-c1.json")

manifest = json.loads((bench_dir / "manifest.json").read_text(encoding="utf-8"))
eval_doc = json.loads(eval_path.read_text(encoding="utf-8"))
if manifest.get("cases") != 36 or manifest.get("observed_volume") != 208583095:
    raise RuntimeError("holdout manifest drift")
if manifest.get("intent_counts") != {"AMBIGUOUS": 13, "NO_MATCH": 20, "SINGLE": 3}:
    raise RuntimeError("holdout intent drift")
if manifest.get("pareto_ranks") != [35, 70]:
    raise RuntimeError("holdout rank drift")

c0 = eval_doc["C0"]["overall"]
c1 = eval_doc["C1"]["overall"]
expected_c0 = {
    "volume_weighted_decision_accuracy_pct": 59.765,
    "volume_weighted_top10_success_pct": 59.765,
    "false_confident_no_match_cases": 5,
    "false_confident_no_match_volume": 46133124,
    "positive_cases_unsatisfiable_inside_envelope": 9,
}
expected_c1 = {
    "volume_weighted_decision_accuracy_pct": 83.173,
    "volume_weighted_top10_success_pct": 84.788,
    "false_confident_no_match_cases": 0,
    "false_confident_no_match_volume": 0,
    "positive_cases_unsatisfiable_inside_envelope": 4,
    "positive_volume_unsatisfiable_inside_envelope": 17117662,
}
for key, value in expected_c0.items():
    if c0.get(key) != value: raise RuntimeError(f"C0 holdout drift {key}: {c0.get(key)}")
for key, value in expected_c1.items():
    if c1.get(key) != value: raise RuntimeError(f"C1 holdout drift {key}: {c1.get(key)}")
if eval_doc.get("delta", {}).get("volume_weighted_decision_accuracy_points") != 23.408:
    raise RuntimeError("C1 delta drift")

rows = [json.loads(x) for x in (bench_dir / "benchmark.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
c1_rows = {r["id"]: r for r in eval_doc["C1"]["cases"]}
failures = [r for r in rows if not c1_rows[r["id"]]["decision_success"]]
if len(failures) != 12:
    raise RuntimeError(f"expected 12 C1 holdout decision failures, got {len(failures)}")
exact_title_failures = [r for r in failures if r["query_origin"] == "canonical_label" and "yv_excluded_title_router" in r["strata"]]
if len(exact_title_failures) != 10:
    raise RuntimeError(f"expected 10 exact-title residual failures, got {len(exact_title_failures)}")

out_bench = Path("research/benchmark/v31/pareto-model-holdout")
out_eval = Path("research/evaluation/v31")
out_bench.mkdir(parents=True, exist_ok=True); out_eval.mkdir(parents=True, exist_ok=True)
for name in ("benchmark.jsonl", "manifest.json"):
    shutil.copyfile(bench_dir / name, out_bench / name)
shutil.copyfile(eval_path, out_eval / "pareto-holdout-c0-c1.json")
hashes = {
    "benchmark": hashlib.sha256((out_bench / "benchmark.jsonl").read_bytes()).hexdigest(),
    "manifest": hashlib.sha256((out_bench / "manifest.json").read_bytes()).hexdigest(),
    "evaluation": hashlib.sha256((out_eval / "pareto-holdout-c0-c1.json").read_bytes()).hexdigest(),
}

finding = f"""# C1 on untouched Pareto holdout — taxonomy v31

**Status:** measured/frozen; C1 materially improves unseen review-pool performance  
**Measured:** 2026-09-06

The first 34 Pareto rows were used to diagnose C0 and design C1. Rows **35–70** were kept untouched, then independently model-adjudicated from frozen query/routing evidence plus taxonomy-only context before any C0/C1 holdout evaluation.

## Holdout

- **36 cases**, **208,583,095** observed searches;
- 23 observed unbound queries + 13 excluded-title routing queries;
- **20 NO_MATCH**, **13 AMBIGUOUS**, **3 SINGLE**;
- judgments are explicitly `MODEL_ADJUDICATED`; they are development evaluation truth, not canonical or human authority.

## C0 → C1

| metric | C0 | C1 |
|---|---:|---:|
| volume-weighted decision accuracy | {c0['volume_weighted_decision_accuracy_pct']}% | **{c1['volume_weighted_decision_accuracy_pct']}%** |
| volume-weighted top-10 success | {c0['volume_weighted_top10_success_pct']}% | **{c1['volume_weighted_top10_success_pct']}%** |
| false-confident NO_MATCH cases | {c0['false_confident_no_match_cases']} | **{c1['false_confident_no_match_cases']}** |
| false-confident NO_MATCH volume | {c0['false_confident_no_match_volume']:,} | **{c1['false_confident_no_match_volume']:,}** |
| positive cases impossible inside envelope | {c0['positive_cases_unsatisfiable_inside_envelope']} | **{c1['positive_cases_unsatisfiable_inside_envelope']}** |

C1 gains **+23.408 percentage points** of volume-weighted decision accuracy on untouched rows. Its short-query surface gate also generalises cleanly to safety: all **20/20 NO_MATCH** holdout rows abstain, while the frozen 333-case YV source-truth regression remains **100% top-1 and Recall@10**.

## Residual

C1 still misses **12/36** holdout rows at top-1. Crucially, **10/12 are exact active job-title queries** from the already measured YV retrieval/routing vocabulary, including examples such as `Specialistläkare`, `Jurist`, `Vaktmästare`, `Lastbilsförare`, `Lagermedarbetare`, `Grundskollärare`, `Lastbilschaufför`, `Beteendevetare`, `Idrottslärare` and `Slöjdlärare`.

Only two residual top-1 failures in this holdout are not exact excluded-title routes: `lager` and `administration`.

## Decision

This is direct evidence for completing the planned **C retrieval-vocabulary lane** before adding D/ESCO or neural retrieval:

```text
exact active job-title preferred label
→ pinned typed job-title→occupation-name relations
→ deterministic occupation candidates
→ consumer admission policy still applies
```

The job title is retrieval vocabulary, never a generic core destination. Exact routing may generate canonical occupation parents outside the 165-document semantic BM25 envelope because that route is source-attested rather than inferred semantic similarity. Parent ordering must remain deterministic and should use an already measured simple prior rather than a new model.

After adding this lane, test it on a **new next-volume sentinel**, not by claiming the already-opened holdout as fresh generalisation evidence.

## Reproducibility

- benchmark SHA-256: `{hashes['benchmark']}`
- manifest SHA-256: `{hashes['manifest']}`
- C0/C1 evaluation SHA-256: `{hashes['evaluation']}`
- taxonomy SHA-256: `{eval_doc['taxonomy_sha256']}`
"""
Path("docs/findings/pareto-holdout-c1-v31.md").write_text(finding, encoding="utf-8")

plan_path = Path("docs/research-plan.md")
plan = plan_path.read_text(encoding="utf-8")
old = "- [ ] adjudicate the remaining 36 lower-volume review rows only if C1/holdout evidence shows that doing so can change a decision"
new = "- [x] independently adjudicate the **remaining 36 lower-volume rows (Pareto ranks 35–70)** as an untouched holdout before evaluating C1; 208.6M observed searches, 20 NO_MATCH / 13 AMBIGUOUS / 3 SINGLE"
if plan.count(old) != 1: raise RuntimeError(f"holdout checklist marker drift: {plan.count(old)}")
plan = plan.replace(old, new, 1)

old = "- [ ] **C1 first:** P80 + six measured high-volume boundary occupations + lexical surface/component/fuzzy evidence + conservative short-query definition-only abstention; evaluate before adding broader product-title vocabulary"
new = """- [x] **C1:** P80 + six measured high-volume boundary occupations + short-query lexical surface/component/fuzzy evidence + conservative definition-only abstention; 100% on the 34-row development slice, 100% on the frozen 333-case source-truth regression, and **83.173% volume-weighted decision accuracy on untouched 36-row holdout** vs C0 59.765%
- [ ] **complete planned C retrieval vocabulary next:** add exact active job-title preferred-label → typed occupation-name parent routing; 10/12 remaining C1 holdout top-1 failures are exact measured job-title routes. Evaluate on a new next-volume sentinel before D/ESCO."""
if plan.count(old) != 1: raise RuntimeError(f"C1 checklist marker drift: {plan.count(old)}")
plan = plan.replace(old, new, 1)

anchor = "Evidence: `docs/findings/pareto-model-decision-v31.md`, `research/benchmark/v31/pareto-model-adjudicated/` and `research/evaluation/v31/pareto-model-c0-eval.json`."
addition = anchor + """

C1 holdout result: on independently adjudicated Pareto ranks 35–70 (**36 untouched cases / 208.6M observed searches**), C1 improves volume-weighted decision accuracy from **59.765% to 83.173%** and top-10 success from **59.765% to 84.788%**. It eliminates all five C0 false-confident `NO_MATCH` holdout failures; all 20 NO_MATCH cases abstain. The 333-case source-truth regression remains 100%. Of C1's 12 remaining holdout top-1 failures, **10 are exact active job-title retrieval/routing terms**, so the next justified complexity is the planned deterministic typed job-title router, not D/ESCO or neural retrieval.

Evidence: `docs/findings/pareto-holdout-c1-v31.md`, `research/benchmark/v31/pareto-model-holdout/` and `research/evaluation/v31/pareto-holdout-c0-c1.json`."""
if plan.count(anchor) != 1: raise RuntimeError(f"evidence anchor drift: {plan.count(anchor)}")
plan = plan.replace(anchor, addition, 1)
plan_path.write_text(plan, encoding="utf-8")
print(json.dumps({"hashes": hashes, "C0": c0, "C1": c1, "exact_title_residual_failures": len(exact_title_failures)}, indent=2, sort_keys=True))
