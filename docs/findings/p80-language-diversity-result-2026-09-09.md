# P80 language-diversity result — 2026-09-09

## Decision

The bounded P80 expansion is successful enough to advance to independent human confirmation. It is **not yet promoted over deployed A593**.

Keep the ranker and full **2,105 occupation** candidate universe unchanged. Do not add a reranker, embeddings, a second semantic stage, or expand to P90/P95 yet.

## What changed

The frozen A593 language-diversity policy was reused without prompt/ranker tuning for the **118 P80 occupations** missing prior diversified-language coverage.

- 118 missing P80 identities requested.
- 96 had sufficiently rich canonical source evidence for generation.
- 22 remained source-thin and were not hallucinated into coverage.
- 87 new identities produced usable training enrichment.
- 79 new identities were jointly usable for both training and independent generated holdout.
- Together with the previous P80 subset, the full-universe evaluation had **117 P80 concepts / 426 holdout queries**.
- Opened 17/88 outcomes were not loaded for selection, generation, or evaluation.

## Full-universe result

Control is frozen A593. Challenger is the same A ranker and the same 2,105 candidates, with source-bound diversified P80 language added where valid.

| Metric | A593 control | P80 challenger | Delta |
|---|---:|---:|---:|
| Top1 | 53.99% | 65.02% | **+11.03 pp** |
| Hit@5 | 77.70% | 83.57% | **+5.87 pp** |
| MRR | 0.6482 | 0.7390 | **+0.0909** |
| Demand-weighted Top1 | 50.36% | 61.39% | **+11.03 pp** |
| Demand-weighted Hit@5 | 79.15% | 86.53% | **+7.38 pp** |

Style Top1 deltas:

- `shift_story`: **+14.78 pp**
- `compressed_note`: **+11.61 pp**
- `outcome_context`: **+8.60 pp**
- `plain_search`: **+8.49 pp**

Paired changes: 141 ranks improved, 27 worsened, 258 unchanged; 54 Top1 gains versus 7 losses; 31 Hit@5 gains versus 6 losses.

## Canonical guard

The strict preregistered materiality gate did not pass because canonical source-truth Top1 moved **331/333 -> 330/333** while Hit@5 remained **333/333**.

A separate deterministic diagnosis shows this is limited to three `canonical_definition` / `long_description` rows:

- two target ranks moved `1 -> 2`;
- one moved `2 -> 1`;
- no exact preferred-label case regressed;
- all three remain in Top5.

Therefore the failed strict no-regression clause remains recorded as a failed clause; it is not retroactively rewritten. The diagnosis does, however, remove the hypothesis that privileged exact/canonical identity lookup was broken by the P80 enrichment. This is sufficient to justify the next independent human confirmation, not production promotion.

## Next gate

Run a small, frozen, independent human occupation-description confirmation with P80 as the primary recruitment/reporting stratum and the full 2,105 occupation universe as valid retrieval destinations. Emphasize colloquial and indirect/task narrative language. Freeze elicitation and blind adjudication before retrieval.

Promotion requires human evidence that the P80 challenger materially improves description findability without a meaningful regression in direct/canonical behavior. Until then the deployed YV candidate remains frozen A593.

## Evidence

- `research/evaluation/v31/p80-language-diversity-generation-v0.json`
- `research/training/v31/p80-language-diversity-training-v0.jsonl`
- `research/evaluation/v31/p80-language-diversity-holdout-v0.jsonl`
- `research/evaluation/v31/p80-language-diversity-result-v0.json`
- `research/evaluation/v31/p80-language-diversity-canonical-guard-diagnosis-v0.json`
