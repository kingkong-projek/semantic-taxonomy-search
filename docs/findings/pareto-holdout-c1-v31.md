# C1 on untouched Pareto holdout — taxonomy v31

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
| volume-weighted decision accuracy | 59.765% | **83.173%** |
| volume-weighted top-10 success | 59.765% | **84.788%** |
| false-confident NO_MATCH cases | 5 | **0** |
| false-confident NO_MATCH volume | 46,133,124 | **0** |
| positive cases impossible inside envelope | 9 | **4** |

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

- benchmark SHA-256: `9cfc5acfd7dc9134aae43971d891053a218390c520dc43be46afbb29ce2259fb`
- manifest SHA-256: `a3427613b43b64964b2d3beaea1ff55338dd196b5b205da76cdea4438c070076`
- C0/C1 evaluation SHA-256: `c3bee5b708ffde2010c35976ea84a59edfa5712077a1d6b8727c4ccb1810ba7d`
- taxonomy SHA-256: `634fd9d848a172747e54e3e487160a912ae6c0fcb8219c50998767c8c9aacbcc`
