# Blind natural-description skill holdout — taxonomy v31

**Status:** independent validation; frozen benchmark predates evaluator and candidate exposure.  
**Target space:** P80 active `skill` identities.  
**Benchmark:** 35 source-attested labour-market-training descriptions, one previously unused descriptive/non-leaky module per unique P80 skill.

## Result

| configuration | Discovery Hit@5 | weighted Discovery Hit@5 | Hit@10 | canonical regression |
|---|---:|---:|---:|---:|
| KV-C0 | 31.429% | 34.734% | 40.000% | 617/617 = 100% |
| KV-F1 close-match one-slot | 31.429% | 31.955% | 31.429% | 617/617 = 100% |

The preselected one-slot `close_match` ESCO lane therefore gives **0.000 percentage-point unweighted gain and -2.779 points weighted** on the blind holdout. Its small development gain did not generalize.

## Decision

Reject `KV-F1-close-one-slot` as the next skill configuration. Keep KV-C0 as the smallest benchmark baseline. Do not add this ESCO lane merely because it helped the opened development slice.

The holdout confirms the actual remaining problem: natural task/tool/method descriptions are materially harder than canonical label/definition regression. The next experiments must diagnose that gap without contaminating retrieval documents with benchmark text.

Synthetic **queries** may now be used as a separate provenance-tagged stress suite for realistic first-person/task/tool/method wording. They are evaluation probes, not traffic evidence, training data, canonical synonyms or retrieval enrichment. Synthetic retrieval/enrichment text remains deferred until a measured residual justifies it.

Evidence: `research/benchmark/v31/training-skill-fresh-holdout/` and `research/evaluation/v31/skill-fresh-holdout.json`.
