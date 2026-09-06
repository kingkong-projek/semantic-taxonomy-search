#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

bench_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pareto-model-adjudicated-v31")
eval_path = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/pareto-model-c0-eval-v31.json")

manifest = json.loads((bench_dir / "manifest.json").read_text(encoding="utf-8"))
evaluation = json.loads(eval_path.read_text(encoding="utf-8"))

if manifest.get("taxonomy_version") != 31 or manifest.get("cases") != 34:
    raise RuntimeError("unexpected Pareto adjudication manifest shape")
if manifest.get("intent_counts") != {"AMBIGUOUS": 11, "NO_MATCH": 18, "SINGLE": 5}:
    raise RuntimeError(f"intent-count drift: {manifest.get('intent_counts')}")
if manifest.get("observed_volume") != 874274239:
    raise RuntimeError("observed-volume drift")
if manifest.get("selected_share_of_70_row_review_pool_pct") != 80.738:
    raise RuntimeError("Pareto review-pool share drift")

ov = evaluation.get("overall", {})
expected = {
    "cases": 34,
    "observed_volume": 874274239,
    "volume_weighted_decision_accuracy_pct": 63.786,
    "volume_weighted_top10_success_pct": 68.481,
    "false_confident_no_match_cases": 7,
    "false_confident_no_match_volume": 112995083,
    "positive_cases_unsatisfiable_inside_p80": 3,
    "positive_volume_unsatisfiable_inside_p80": 95330535,
}
for key, value in expected.items():
    if ov.get(key) != value:
        raise RuntimeError(f"C0 evaluation drift for {key}: expected {value}, got {ov.get(key)}")

benchmark_rows = [json.loads(x) for x in (bench_dir / "benchmark.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
if len(benchmark_rows) != 34:
    raise RuntimeError("benchmark row-count drift")
if any(r.get("adjudication", {}).get("status") != "MODEL_ADJUDICATED" for r in benchmark_rows):
    raise RuntimeError("benchmark contains non-model-adjudicated rows")

# Six exact occupation identities explain every positive case currently unsatisfiable inside P80.
residual_ids = sorted({
    str(x["concept_id"])
    for row in benchmark_rows
    if row["id"] in {"yv.model-pareto.005", "yv.model-pareto.013", "yv.model-pareto.014"}
    for x in row["must"] + row["acceptable"]
})
expected_residual_ids = sorted({
    "DLEi_bTh_oLA",  # Lagerarbetare/Terminalarbetare
    "wypk_7S7_snv", # Ämneslärare, 7–9
    "86sy_hBf_exW", # Ämneslärare, gymnasieskolan
    "743P_CSD_tF8", # Grundlärare, 4–6
    "PecC_mHt_1Cj", # Grundlärare, förskoleklass och 1–3
    "VZoJ_4oe_xyR", # Lärare i grundskolan, årskurs 1–6
})
if residual_ids != expected_residual_ids:
    raise RuntimeError(f"unexpected P80 residual identities: {residual_ids}")

frozen_bench = Path("research/benchmark/v31/pareto-model-adjudicated")
frozen_eval = Path("research/evaluation/v31")
frozen_bench.mkdir(parents=True, exist_ok=True)
frozen_eval.mkdir(parents=True, exist_ok=True)
for name in ("benchmark.jsonl", "manifest.json"):
    shutil.copyfile(bench_dir / name, frozen_bench / name)
shutil.copyfile(eval_path, frozen_eval / "pareto-model-c0-eval.json")

hashes = {
    "benchmark": hashlib.sha256((frozen_bench / "benchmark.jsonl").read_bytes()).hexdigest(),
    "manifest": hashlib.sha256((frozen_bench / "manifest.json").read_bytes()).hexdigest(),
    "evaluation": hashlib.sha256((frozen_eval / "pareto-model-c0-eval.json").read_bytes()).hexdigest(),
}

positive_volume = int(ov["observed_volume"]) - int(evaluation["by_intent"]["NO_MATCH"]["observed_volume"])
p80_satisfied_positive_volume = positive_volume - int(ov["positive_volume_unsatisfiable_inside_p80"])
p80_positive_volume_coverage_pct = round(100 * p80_satisfied_positive_volume / positive_volume, 3)
if p80_positive_volume_coverage_pct != 84.737:
    raise RuntimeError(f"unexpected P80 positive-volume coverage: {p80_positive_volume_coverage_pct}")

finding = f"""# First model-adjudicated Pareto decision slice — taxonomy v31

**Status:** frozen decision benchmark and measured C0 baseline  
**Measured:** 2026-09-06

This is the first relevance slice whose destination judgments are not merely copied from the same canonical source used by retrieval. It combines the highest-volume rows from the already frozen observed-query and excluded-title review populations until cumulative review-pool volume exceeds 80%.

## Benchmark

- **34 cases** covering **80.738%** of the frozen 70-row review-pool observed volume;
- observed volume represented: **874,274,239**;
- **5 SINGLE**, **11 AMBIGUOUS**, **18 NO_MATCH**;
- judgments are explicitly `MODEL_ADJUDICATED` with `model_judgment` provenance;
- they are evaluation truth for this development slice, not canonical taxonomy authority and not human review.

The 18 `NO_MATCH` cases are primarily real high-volume geography queries. They provide a non-synthetic abstention/hard-negative safety slice.

## C0 result

C0 is deliberately small:

```text
159 P80 occupation-name targets
+ preferred label
+ real canonical definition
+ canonical alternative labels
+ deterministic BM25
+ exact lexical-surface dominance
+ zero lexical evidence => abstain
```

Measured on the 34-case slice:

- unweighted decision accuracy: **{ov['decision_accuracy_pct']}%**;
- **volume-weighted decision accuracy: {ov['volume_weighted_decision_accuracy_pct']}%**;
- volume-weighted top-10 success: **{ov['volume_weighted_top10_success_pct']}%**;
- false-confident `NO_MATCH`: **{ov['false_confident_no_match_cases']} / 18 cases**, representing **{ov['false_confident_no_match_volume']:,}** observed searches;
- positive cases impossible inside the P80 envelope: **{ov['positive_cases_unsatisfiable_inside_p80']}**, representing **{ov['positive_volume_unsatisfiable_inside_p80']:,}** searches.

Among positive-intent volume in this slice, P80 itself can represent **{p80_positive_volume_coverage_pct}%**. The entire currently measured envelope miss is explained by only **six additional occupation identities**:

- `DLEi_bTh_oLA` — Lagerarbetare/Terminalarbetare;
- `wypk_7S7_snv` — Ämneslärare, 7–9;
- `86sy_hBf_exW` — Ämneslärare, gymnasieskolan;
- `743P_CSD_tF8` — Grundlärare, 4–6;
- `PecC_mHt_1Cj` — Grundlärare, förskoleklass och 1–3;
- `VZoJ_4oe_xyR` — Lärare i grundskolan, årskurs 1–6.

## Decision

The residual does **not** justify ESCO, embeddings, ad ETL or synthetic text yet. Test a minimal C1 first:

1. P80 + the six measured high-volume boundary identities;
2. make label/alternative-label evidence dominate definition-only overlap for short queries;
3. add conservative lexical component/fuzzy handling sufficient for ordinary inflection/compound wording;
4. short queries with definition-only evidence abstain rather than mapping confidently.

This is a development decision slice, so C1 improvements must later be checked on additional held-out/review rows before being treated as generalisation evidence.

## Reproducibility

- benchmark SHA-256: `{hashes['benchmark']}`
- manifest SHA-256: `{hashes['manifest']}`
- C0 evaluation SHA-256: `{hashes['evaluation']}`
- taxonomy SHA-256: `{evaluation['taxonomy_sha256']}`
"""
Path("docs/findings/pareto-model-decision-v31.md").write_text(finding, encoding="utf-8")

plan_path = Path("docs/research-plan.md")
plan = plan_path.read_text(encoding="utf-8")

old = "- [ ] compact hard-negative + no-match/abstention safety slice; keep it small and adjudicated rather than manufacturing negatives"
new = "- [x] compact **model-adjudicated hard-negative + no-match/abstention slice** embedded in the first 34-case Pareto decision benchmark: 18 real high-volume `NO_MATCH` cases, primarily geography; no synthetic negatives required"
if plan.count(old) != 1:
    raise RuntimeError(f"expected one hard-negative marker, got {plan.count(old)}")
plan = plan.replace(old, new, 1)

old = "- [ ] adjudicate the prepared top-50 real-query packet into occupation intent vs other/no-match and MUST/ACCEPTABLE/MUST_NOT identities; do not score it before review"
new = """- [x] adjudicate the **first Pareto batch** rather than all review rows: 34 highest-volume rows across the 50 real unbound queries + 20 excluded-title routing rows cover **80.738%** of combined review-pool volume; 27 are observed unbound queries and 7 excluded-title routes; judgments are explicitly `MODEL_ADJUDICATED`, not source/human truth
- [ ] adjudicate the remaining 36 lower-volume review rows only if C1/holdout evidence shows that doing so can change a decision"""
if plan.count(old) != 1:
    raise RuntimeError(f"expected one adjudication marker, got {plan.count(old)}")
plan = plan.replace(old, new, 1)

anchor = "Evidence: `docs/findings/p80-lexical-ablation-v31.md` and `research/evaluation/v31/p80-lexical-ablation.json`."
addition = anchor + f"""

First real-language/Pareto result: the frozen 34-case `MODEL_ADJUDICATED` occupation slice covers **80.738%** of the combined review-pool observed volume. C0 reaches **63.786% volume-weighted decision accuracy** and **68.481% volume-weighted top-10 success**. Seven of 18 `NO_MATCH` rows are false-confident because short geography strings overlap definition text. Three positive rows fall outside P80; all are covered by only six additional occupation identities. P80 can represent **{p80_positive_volume_coverage_pct}%** of positive-intent volume in this slice.

Decision: test a minimal **C1** (P80 + six measured boundary identities + stronger label-surface evidence + conservative short-query abstention) before D/ESCO, neural retrieval or new source engineering.

Evidence: `docs/findings/pareto-model-decision-v31.md`, `research/benchmark/v31/pareto-model-adjudicated/` and `research/evaluation/v31/pareto-model-c0-eval.json`."""
if plan.count(anchor) != 1:
    raise RuntimeError(f"expected one C0 evidence anchor, got {plan.count(anchor)}")
plan = plan.replace(anchor, addition, 1)

old = "- [ ] complete planned C's product-title/retrieval-vocabulary portion only where the real-query/safety slice demonstrates value; do not conflate C0 with full planned C"
new = "- [ ] **C1 first:** P80 + six measured high-volume boundary occupations + lexical surface/component/fuzzy evidence + conservative short-query definition-only abstention; evaluate before adding broader product-title vocabulary"
if plan.count(old) != 1:
    raise RuntimeError(f"expected one planned-C marker, got {plan.count(old)}")
plan = plan.replace(old, new, 1)

plan_path.write_text(plan, encoding="utf-8")
print(json.dumps({"hashes": hashes, "p80_positive_volume_coverage_pct": p80_positive_volume_coverage_pct, "overall": ov}, indent=2, sort_keys=True))
