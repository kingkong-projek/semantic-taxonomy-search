# P80 display relevance calibration — 2026-09-09

Status: **simple display gate is NOT promoted**.

## Problem

The YV ranker optimizes retrieval but long description queries admit every occupation with positive BM25 evidence. The demo then shows up to five results, so weakly supported tail candidates can look like confident recommendations.

This is a separate product-quality problem from Hit@5. A fixed top-N cutoff is not acceptable because a material share of useful YV retrieval lives at ranks 2–5.

## Prefrozen calibration experiment

The frozen P80 + source-thin-rescue A-family ranker and the full 2,105-candidate universe were left unchanged. Model-authored P80 holdout concepts were deterministically split by concept id into calibration and untouched evaluation partitions. Opened 17/88 rows were not loaded.

A small per-candidate rule family used only signals already available from the sparse ranker: score relative to top, query-token coverage, IDF-weighted query coverage and shared-term count. No rank cutoff was allowed. The calibration constraint required >=98% retention of both all baseline Hit@5 targets and targets originally at ranks 2–5.

Selected rule:

- score ratio >= 0.55
- token coverage >= 0.30
- IDF coverage >= 0.10
- at least 2 shared terms

On the untouched synthetic evaluation split (52 concepts / 187 queries):

- baseline Hit@5 targets: 159; retained: 158 (**99.37%**)
- baseline targets at ranks 2–5: 30; retained: 30 (**100%**)
- rank 4: 3/3 retained
- rank 5: 3/3 retained
- mean displayed candidates: **4.98 -> 3.40**
- exact-target-negative visible candidates: **-38.29%**

This proves that current ranker signals contain substantial candidate-relevance information under the same synthetic distribution.

## Opened transfer replay

Only after the rule was frozen, it was replayed on the pre-existing opened 54-case YV stress suite. Those rows did not choose the rule.

The visible list became shorter:

- mean displayed: **4.59 -> 3.30**
- full five-result lists: **49 -> 22**
- explicit abstention cases returning empty: **1/8 -> 3/8**

But target retention transferred poorly:

- targetable opened Hit@5: **28/41 -> 22/41**
- opened Top1: **15/41 -> 14/41**
- direct Hit@5: **12/12 -> 11/12**
- indirect Hit@5: **5/8 -> 3/8**
- noisy Hit@5: **7/8 -> 4/8**

Therefore the simple gate is **not deployable**. A cosmetic confidence threshold can remove visible junk but also removes useful low-ranked candidates under language shift.

## Decision

Do not add a fixed top-N cutoff and do not deploy the v0 display gate. Preserve Hit@5 as a hard safety metric.

Next bounded experiment: keep the A-family ranker unchanged and test whether candidate relevance is more stable when canonical evidence and teacher/diversified evidence are preserved as separate query-candidate signals instead of only using the final merged BM25 score. This is an experiment, not activation of a production reranker. If that also fails transfer, wait for independent human relevance data before adding further complexity.

Evidence:

- `research/evaluation/v31/p80-display-precision-opened-audit-v0.json`
- `research/evaluation/v31/p80-display-relevance-calibration-v0.json`
- `research/evaluation/v31/p80-display-relevance-opened-replay-v0.json`
