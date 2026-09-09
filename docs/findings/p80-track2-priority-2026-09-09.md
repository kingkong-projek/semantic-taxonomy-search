# P80-first Track-2 priority — 2026-09-09

<!-- P80-FIRST-TRACK2-2026-09-09 -->

## Decision

Track 2 now uses **P80-first optimization and evaluation** for occupations while preserving the full **2,105** active-v31 occupation candidate universe.

The frozen demand proxy puts **159 occupations at 80% of observed active-v31 historical occurrence mass**. These occupations are therefore the primary short-feedback-loop population. P90/P95/full-tail quality work is deferred until P80 evidence justifies expansion.

This is a prioritization rule, not an eligibility rule: a valid non-P80 occupation must remain retrievable and must never be coerced to a P80 identity.

## Current language-diversity overlap

Of the 159 P80 occupations, **41** already have usable phrases in the frozen `a593-language-diversity-training-v0` corpus and **118** do not.

The already-diversified subset represents **26.7%** of P80 historical occurrence mass.

This overlap is planning metadata only. The existing synthetic Gemma diversification policy is **not promoted for mass generation** because its large synthetic holdout gain did not reproduce on the corrected opened full-universe residual.

## Next short loop

1. Keep architecture A and all 2,105 occupation identities eligible.
2. Collect fresh independent human/user descriptions with **P80 as the primary recruitment/evaluation stratum** under the existing frozen human-study contract.
3. Report P80 separately, plus a small long-tail safety slice when evidence exists; do not use the tail to delay the P80 decision.
4. Compare current A against any language-enriched challenger only on evidence frozen before retrieval.
5. Expand quality work to P90 (302 occupations), then P95 (455), only after a material P80 result warrants it.

Machine-readable coverage: `research/evaluation/v31/p80-track2-priority-coverage.json`.
Human-study priority population: `research/human/description-fallback-v1/p80-occupation-priority-population.json`.
