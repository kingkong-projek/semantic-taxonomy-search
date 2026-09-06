# First model-adjudicated Pareto decision slice — taxonomy v31

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

- unweighted decision accuracy: **61.765%**;
- **volume-weighted decision accuracy: 63.786%**;
- volume-weighted top-10 success: **68.481%**;
- false-confident `NO_MATCH`: **7 / 18 cases**, representing **112,995,083** observed searches;
- positive cases impossible inside the P80 envelope: **3**, representing **95,330,535** searches.

Among positive-intent volume in this slice, P80 itself can represent **84.737%**. The entire currently measured envelope miss is explained by only **six additional occupation identities**:

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

- benchmark SHA-256: `e3497a8d0f0f9cc9725d9c194f26be880d922ce9a07d318a2d037a76e6bd637d`
- manifest SHA-256: `ca7ce26cde2c5902dc25ea04704b842e04c069a7195f633a8c0f38856c0fa1c8`
- C0 evaluation SHA-256: `4d27b5b50cad179785308cbfd02b098760aab833ba28ebe49cc12ce754f6608b`
- taxonomy SHA-256: `634fd9d848a172747e54e3e487160a912ae6c0fcb8219c50998767c8c9aacbcc`
