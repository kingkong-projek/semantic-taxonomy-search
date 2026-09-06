# KV description fallback increment — taxonomy v31

**Status:** measured against the pinned current product on the same frozen blind holdout.  
**Target space:** P80 active `skill` identities.  
**Benchmark:** 35 source-attested labour-market-training descriptions frozen before either comparison result was inspected.  
**Benchmark SHA-256:** `79816eb2020b100bf8260b8f1807069288c30dbabd457bfffbfe3f49735c6675`.

## Product baseline

The current KV product baseline is pinned to `kingkong-projek/yrkesvaljaren@0eba98e3a91079a43c1eaf6da09dfabe11e5bc8b`, including Fuse.js `7.5.0` and the exact no-context path `HybridSearchEngine.search(query, '', [], 5)` over the pinned KV v31 skill catalog.

On the 35 blind natural-description cases the current selector returns **no result for 35/35 cases**:

| configuration | Discovery Hit@5 | weighted Discovery Hit@5 | no-result cases |
|---|---:|---:|---:|
| pinned current KV | **0.000%** | **0.000%** | **35/35** |
| KV-C0 semantic fallback | **31.429% (11/35)** | **34.734%** | — |

The weighted column uses the existing Historical-API occurrence proxy attached to the target identities. It is **not user traffic**.

## Incremental fallback value

Because the current selector misses every case, the contingency table is unambiguous:

- both product and semantic hit: **0**;
- product-only hit: **0**;
- semantic rescue: **11**;
- both miss: **24**.

Therefore KV-C0 adds **+31.429 percentage points Discovery@5** over the current product on this benchmark, or **+34.734 points occurrence-proxy weighted**. All 35 cases are fallback-eligible relative to the pinned product, and C0 rescues 11 of them.

This is the first direct evidence that the proposed description fallback adds material product capability rather than merely reproducing ordinary KV lookup.

## What this does not prove

This benchmark is source-attested but not a sample of production query traffic. It demonstrates capability on realistic learning-outcome/task descriptions, not a claim that 31.429% of real KV users would be rescued.

The 24 remaining misses are now an **opened development residual**. They may be used to diagnose what kind of evidence or retrieval capability is missing, but any configuration chosen after inspecting them must be validated on a new unopened holdout before being promoted as independent evidence.

The previously tested `KV-F1-close-one-slot` remains rejected: it gave no unweighted blind-holdout gain and reduced weighted Discovery@5. Do not add special-case rules simply to fit these 24 rows.

## Decision

Keep deterministic KV-C0 as the minimum semantic fallback baseline. The next evidence step is a separate `synthetic_query` stress suite covering first-person/task/tool/method phrasing, with no traffic weighting and no ingestion into retrieval documents. Use that suite plus the opened residual only to nominate the **smallest** next skill capability. Any promoted capability then needs a fresh source-attested unopened validation holdout.

Reproduction:

- product evaluator: `scripts/evaluate_pinned_kv_selector_description_baseline.mjs`;
- increment comparator: `scripts/compare_skill_fallback_increment.py`;
- workflow: `.github/workflows/pinned-kv-description-baseline.yml`;
- semantic baseline result: `research/evaluation/v31/skill-fresh-holdout.json`.
