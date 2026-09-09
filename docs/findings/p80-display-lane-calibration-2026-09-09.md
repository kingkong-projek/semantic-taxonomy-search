# P80 lane-aware display calibration — 2026-09-09

## Result

The generic merged-score display gate is still **not deployable**: its frozen opened replay reduced visible list size but lost too many previously observed Hit@5 targets under language shift.

A bounded follow-up preserved enrichment/phrase evidence separately while leaving the A-family ranker unchanged. The selected rule was frozen on the calibration split as `ratio_mean_support >= 0.12`; opened 17/88 rows were not loaded during selection.

On the untouched synthetic evaluation split (187 queries, full 2,105 candidate universe):

- overall Hit@5 retention: `158/159` = **99.37%**;
- targets originally at ranks 2–5: `29/30` = **96.67%** retained;
- rank 4: `3/3` retained;
- rank 5: `3/3` retained;
- mean displayed candidates: `4.984 -> 3.214`;
- exact-target-negative visible-candidate proxy: **-42.69%**.

The preregistered gate required >=98% rank-2–5 retention, so this experiment **formally failed**. Do not retroactively lower or relabel that gate after seeing the result.

## Interpretation

The formal fail does **not** justify killing the lane-aware idea. There were only 30 positive rank-2–5 cases in the untouched split: one lost rank-3 target changes retention from `30/30 = 100%` to `29/30 = 96.67%`. The observed trade-off — roughly 43% fewer visible negative candidates for one lost lower-ranked target — is materially promising but statistically too thin to promote or reject confidently.

Therefore:

1. freeze the selected rule exactly; no threshold retuning on these results;
2. do not deploy it yet;
3. validate the unchanged rule on a larger, more independent natural-language proxy, with human descriptions remaining the eventual decision-bearing evidence;
4. preserve rank-2–5 retention as a first-class metric rather than optimizing list length alone;
5. do not add a runtime reranker or multi-stage architecture merely to improve display appearance.

This is candidate-level mechanism evidence, not human relevance accuracy. Semantically acceptable sibling occupations are counted as negatives in the exact-target proxy, so the reported negative-removal metric is deliberately conservative but not a human precision estimate.

Evidence: `research/evaluation/v31/p80-display-lane-calibration-v0.json`.
