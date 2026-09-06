# Discovery-oriented evaluation objective — taxonomy v31

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
| volume-weighted Discovery Success@5 | 59.765% | **84.788%** |
| volume-weighted Discovery Success@10 | 59.765% | **84.788%** |
| NO_MATCH abstention | 75.0% | **100.0%** |
| volume-weighted NO_MATCH abstention | 71.881% | **100.0%** |

C1 gains **+25.023 percentage points** of volume-weighted Discovery Success@5 over C0.

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

Evaluation SHA-256: `49e21687ea7eeb627d84e3af60bc59474435ead2715f649bfbf2d490b5ecfad2`
