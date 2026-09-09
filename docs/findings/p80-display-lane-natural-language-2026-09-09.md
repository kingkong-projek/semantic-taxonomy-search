# P80 lane display rule on natural ad language — 2026-09-09

## Result

The previously frozen lane rule `ratio_mean_support >= 0.12` is **not deployable**.

A primary proxy used historical 2025 Platsbanken ad bodies with a structured `occupation-name` target. The 22 source-thin rescue identities were excluded because rescue training had consumed ad-derived keywords. Target-title sentences were removed, raw ad text was not committed, all 2,105 occupations remained retrieval candidates, and the lane rule was not changed or selected on this corpus.

Primary 80-word proxy:

- 822 queries across all 137 eligible P80 concepts;
- baseline target Hit@5: 139;
- baseline rank-2–5 target hits: 76;
- lane retained only 10/139 Hit@5 targets (7.19%);
- lane retained only 1/76 rank-2–5 targets (1.32%);
- exact-target-negative proxy reduction: 99.57%, which here is simply over-filtering, not useful precision.

This strongly falsifies transfer of the synthetic lane operating point to long natural ad language.

## Post-result query-length diagnosis

To determine whether the failure was merely caused by 80-word queries, the same source and unchanged lane rule were replayed at fixed 20- and 40-word truncations. Because those lengths were selected after observing the 80-word result, these are mechanism diagnostics, not independent promotion evidence.

At 20 words:

- baseline Hit@5 65; rank-2–5 hits 45;
- retained Hit@5 28/65 = 43.08%;
- retained rank-2–5 12/45 = 26.67%.

At 40 words:

- baseline Hit@5 86; rank-2–5 hits 53;
- retained Hit@5 30/86 = 34.88%;
- retained rank-2–5 9/53 = 16.98%.

Therefore query length alone does not rescue the frozen rule. The synthetic success was distribution-specific.

## Decision

- Keep the original preregistered synthetic result as historical evidence; do not rewrite it as if it had failed there.
- **Reject `ratio_mean_support >= 0.12` for deployment.**
- Do not tune that threshold on 2025 or the opened 17/88 rows.
- Keep visible-result relevance as an active product residual.
- Next bounded experiment: extract natural task-oriented snippets from an earlier historical-ad year, calibrate only a simple **query-length-robust candidate confidence** while keeping retrieval unchanged, then evaluate the frozen rule on a separate untouched year.
- Prefer candidate-local/relative evidence (for example score ratio and absolute local phrase/IDF support) over coverage divided by the whole query.
- Human relevance judgments remain the eventual decision-bearing evidence; historical ads are a proxy.
- Do not introduce a runtime semantic reranker unless this simpler calibration family is falsified.

Evidence:

- `research/evaluation/v31/p80-display-lane-historical-ads-v0.json`
- `research/evaluation/v31/p80-display-lane-historical-ads-20w-diagnostic-v0.json`
- `research/evaluation/v31/p80-display-lane-historical-ads-40w-diagnostic-v0.json`
