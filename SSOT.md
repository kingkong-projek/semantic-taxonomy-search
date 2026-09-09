# Single source of truth

This file is the canonical entrypoint for current project state.

## Authority order

1. `docs/research-plan.md` — product scope, research architecture, evidence rules, gates and experiment order.
2. `docs/findings/*` and `research/*` — evidence supporting or falsifying the plan. They do not silently override it.
3. `docs/findings/field-feedback-findability-2026-09-07.md` + `research/evaluation/v31/field-feedback-findability-2026-09-07.json` — current real-user field-feedback evidence and frozen derived corpus.

## Current amendment — 2026-09-09: P80-first Track-2 feedback loop

<!-- P80-FIRST-TRACK2-2026-09-09 -->

Occupation Track 2 now optimizes and evaluates **P80 first: 159 occupations covering 80% of the frozen historical occurrence proxy**. This is a quality-priority stratum only; all **2,105** active v31 `occupation-name` identities remain eligible retrieval destinations.

Current frozen diversified-language overlap is **41/159 P80 occupations**; this does not authorize generating the same synthetic policy for the remaining 118. Broad synthetic scaling remains paused after the mixed full-universe opened replay. The next decision-bearing loop is fresh independent human/user description evidence sampled primarily from P80 under the existing frozen human-study contract. P90/P95/full-tail optimization is deferred until P80 evidence warrants expansion.

Evidence: `docs/findings/p80-track2-priority-2026-09-09.md` and `research/evaluation/v31/p80-track2-priority-coverage.json`.

## Current amendment — 2026-09-09: A593 language-diversity gate complete

The bounded training-language-distribution falsifier is complete. **Do not scale the current synthetic Gemma diversification policy to A593/A2105 yet.**

With the A-family ranker held fixed, 466 accepted source-bound diversified phrases across 133 A593 concepts produced a strong separately generated synthetic holdout gain: Top1 `286/446 -> 323/446` (**+8.30 pp**), Hit@5 `380/446 -> 406/446` (**+5.83 pp**), MRR `0.734509 -> 0.806519`; synthetic `shift_story` Top1 improved **+15.57 pp**. The prefrozen materiality gate therefore passed.

However the correctly replayed full-2,105 opened diagnostic is mixed rather than confirmatory: targetable40 Top1 `15 -> 16`, Hit@5 `26 -> 24`; strict17 remains `5` Top1 / `10` Hit@5 while MRR moves `0.424510 -> 0.418237`. The two targetable Hit@5 losses are colloquial and indirect cases, while a visible Top1 gain is noisy/directly lexical. Thus the large synthetic narrative-language gain does not reproduce on the opened colloquial/indirect residual.

The earlier file `research/evaluation/v31/a593-language-diversity-opened-replay.json` is **superseded for interpretation** because it accidentally ranked only the 593 teacher-expanded identities. The corrected file `research/evaluation/v31/a593-language-diversity-opened-replay-full-universe.json` hard-asserts parity with the original full-universe A593 checkpoint before comparison.

Active Track-2 decision:

- **A — teacher-expanded sparse retrieval — remains the surviving simple architecture family;**
- keep A2105/full Gemma identity generation paused;
- keep broad synthetic language scaling paused;
- do not tune prompts/phrases from opened 17/88 rows;
- do not revive B/C/E or activate D merely because the synthetic language gate did not transfer cleanly;
- next decision-bearing evidence should be **fresh independent human/user descriptions under the existing frozen human-study contract**;
- use that fresh evidence to measure both current-A quality and any incremental value of source-bound diversified training language;
- preserve the simplicity target: exact/canonical lexical route + one semantic description ranker/index.

Detailed evidence and interpretation:

- `docs/findings/a593-language-diversity-2026-09-09.md`
- `research/evaluation/v31/a593-language-diversity-result-v0.json`
- `research/evaluation/v31/a593-language-diversity-opened-replay-full-universe.json`

## Current amendment — 2026-09-09: Track-2 architecture breadth complete

The short Track-2 architecture breadth phase is complete. **A — teacher-expanded sparse retrieval — is the surviving simple architecture family.**

The breadth comparison deliberately avoided rescue sweeps and hybrid composition:

- **B supervised sparse** loses to its same-feature centroid control on the fixed 593 teacher holdouts and also trails A on the frozen 66-case hard-confusion gate;
- **C task/activity representation** reaches only `46/66` Top1 and `50/66` correct confusion-pair side versus A `62/66` and `63/66`;
- **E rank-64 latent student** fits the frontend-size budget (~0.84 MB gzip estimate) but also reaches only `46/66` Top1 versus A `62/66`, and strongly regresses on the fixed 593 construction holdout;
- the deferred two-stage **D coarse retrieval -> local discriminator is NOT activated** because the dedicated hard-confusion evidence does not demonstrate a need for another semantic stage.

Therefore the active Track-2 execution order is now superseded by the language-diversity amendment above. Historical breadth closeout order was:

- freeze A593 ranker architecture and keep A2105/full Gemma generation paused;
- do not resume stemming/hub/hard-negative/pair-rule micro-tuning;
- test training-language distribution inside A as the next bounded falsifier;
- opened 17/88 remains replay-only and may not choose new language/prompt;
- do not build a B/C/E/D hybrid stack merely to chase benchmark gains.

The simplicity contract remains: **exact/canonical lexical route + one semantic description ranker/index**. A second semantic stage remains disallowed absent new evidence that clears the stronger complexity bar.

Detailed closeout evidence:

- `docs/findings/compile-time-architecture-breadth-result-2026-09-09.md`
- `research/evaluation/v31/compile-time-semantic-architecture-breadth-result.json`

The previous breadth-opening decision is retained as history:

- `docs/findings/compile-time-architecture-breadth-gate-2026-09-08.md`
- `research/evaluation/v31/compile-time-semantic-architecture-breadth-gate.json`

## Current amendment — 2026-09-07: bounded Track-1 field-feedback replay

The field-feedback finding is new independent user evidence of the exact class that `docs/research-plan.md` names as a trigger for renewed product investigation.

Therefore the older sentence in section 2.1.1 that says Track 1 is simply `PARKED` is stale in one narrow respect:

- broad Track-1 expansion remains parked;
- **a bounded Track-1 field-feedback replay is ACTIVE**;
- its purpose is only to classify the 2026-09-07 real-user failures against exact current YV/KV behaviour and promote reproduced product-native defects to the owning repository;
- Track 2 remains active and is not replaced by this replay;
- consumer-service investigation is out of scope; that team has been informed separately.

The detailed evidence and action order are in `docs/findings/field-feedback-findability-2026-09-07.md`.

At the next safe consolidation of the large living research plan, current amendments should be folded into the relevant sections and reduced to pointers. Until then, this root file resolves status precedence explicitly so no future session needs conversation memory to recover the active execution order.

## Cross-repository boundary

`kingkong-projek/semantic-taxonomy-search` owns evidence, classification, semantic-retrieval research and the decision about whether a residual justifies Track 2.

`kingkong-projek/yrkesvaljaren` owns reproducible YV/KV product behaviour, fixes and regression tests. Its feedback-specific product SSOT is `docs/findability-feedback-ssot.md`.
