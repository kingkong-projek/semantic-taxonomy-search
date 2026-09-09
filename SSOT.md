# Single source of truth

This file is the canonical entrypoint for current project state.

## Authority order

1. `docs/research-plan.md` — product scope, research architecture, evidence rules, gates and experiment order.
2. `docs/findings/*` and `research/*` — evidence supporting or falsifying the plan. They do not silently override it.
3. `docs/findings/field-feedback-findability-2026-09-07.md` + `research/evaluation/v31/field-feedback-findability-2026-09-07.json` — current real-user field-feedback evidence and frozen derived corpus.

## Current amendment — 2026-09-09: P80-first Track-2 feedback loop

<!-- P80-FIRST-TRACK2-2026-09-09 -->

Occupation Track 2 now optimizes and evaluates **P80 first: 159 occupations covering 80% of the frozen historical occurrence proxy**. This is a quality-priority stratum only; all **2,105** active v31 `occupation-name` identities remain eligible retrieval destinations.

The bounded P80 language expansion is now complete. The same frozen language-diversity policy was attempted for the **118 P80 occupations** previously missing coverage, with no ranker change and all **2,105** active occupations still competing. Source evidence supported generation for 96/118; 22 source-thin identities were initially left unmanufactured. The full-universe P80 holdout covers **117 concepts / 426 queries** and improves A593 **Top1 53.99% -> 65.02% (+11.03 pp)** and **Hit@5 77.70% -> 83.57% (+5.87 pp)**; demand-weighted Top1 is also **+11.03 pp**.

A subsequent source-thin rescue found direct source evidence for all 22 canonical-thin P80 identities in AF relevant-skills, ad-keyword and typed-job-title sources. The frozen rescue produced usable train+holdout data for 20/22. On its separate 72-query mechanism holdout Top1 moved **5.6% -> 80.6%** and Hit@5 **18.1% -> 95.8%**, while the existing P80 safety holdout moved only about **-0.47 pp Top1 / -0.23 pp Hit@5**, canonical 333 was unchanged, and exact-label P80 remained **159/159 Top1**. Keep this rescue in the frozen P80 candidate; it is still source-bound synthetic evidence, not human accuracy.

The preregistered P80 language-diversity strict gate is recorded as failed because canonical source-truth Top1 moved `331/333 -> 330/333` with Hit@5 unchanged at `333/333`. Deterministic diagnosis shows only three long `canonical_definition` rows changed: two `rank 1 -> 2`, one `2 -> 1`; **no exact preferred-label case regressed**. Do not retroactively relabel the strict gate as passed, but do advance the P80 challenger to the already-planned **small independent human confirmation**. The deployed YV candidate remains A593 until that human gate clears. P90/P95/full-tail expansion remains deferred.

Evidence: `docs/findings/p80-language-diversity-result-2026-09-09.md`, `research/evaluation/v31/p80-language-diversity-result-v0.json`, `research/evaluation/v31/p80-language-diversity-canonical-guard-diagnosis-v0.json`, and `research/evaluation/v31/p80-source-thin-rescue-result-v0.json`.

## Current amendment — 2026-09-09: irrelevant Top-5 suggestions are the primary active display residual

The current A-family ranker has a material **display precision / fail-open** problem: a useful target may sit at rank 2–5 while other visible candidates are professionally implausible. Therefore fixed top-N truncation is invalid. The active question is specifically whether a real lower-ranked target can be distinguished from junk at the same visible rank while leaving retrieval/order unchanged.

The threshold/coverage family is now sufficiently falsified. A merged-signal gate reduced opened targetable Hit@5 `28 -> 22`; the lane-aware synthetic result (`29/30` rank-2–5 retained with ~43% proxy-negative reduction) failed badly on natural historical task text; and a later length-robust rule retained `167/167` Hit@5 and `87/87` rank-2–5 targets on untouched 2024 natural task text but again fell to `28 -> 22` Hit@5 and `13 -> 10` lower-rank hits on the opened user-style replay. Do not continue threshold tuning on these feature families.

A Top-5-local lexical contrast signal was safe but useless: on untouched 2024 it retained `167/167` Hit@5 and `87/87` rank-2–5 targets but removed effectively **0%** of the negative proxy. A first SSYK+phrase experiment (`v0`) is superseded because it incorrectly looked for `ssyk_code_2012` directly on `occupation-name` objects; the feature was absent. The corrected `v1` maps all 2,105 occupations through the dedicated v31 SSYK hierarchy.

Corrected **SSYK4 + best-single-teacher-phrase** discrimination is the strongest hand-built heuristic so far on natural proxy data: untouched 2024 retained **166/167 Hit@5** and **86/87 rank-2–5** targets while reducing cross-SSYK non-targets **44.09%** and mean visible list size `5.00 -> 2.97`. However the exact frozen rule failed the opened user-style replay: targetable Hit@5 `28 -> 23`, rank-2–5 hits `13 -> 8`. It removes `Apotekare`/`Receptarie` from the nursing example and `Affärskonsult, IT` from the electrician example, but still leaves `Sjukhusvaktmästare` and `Växeltelefonist`. **Do not deploy or retune it from opened rows.**

A subsequent symmetric coherent-evidence-unit test (same SSYK4 as rank 1 OR TF-IDF similarity to one canonical definition/teacher phrase) was safer but too weak: untouched 2024 retained **166/167 Hit@5** and **86/87 rank-2–5**, but removed only **20.52%** of cross-SSYK non-targets and shortened the list only `5.00 -> 4.06`. It failed the prefrozen >=25% materiality gate, so it is not replayed/tuned on opened data.

Active decision: **stop hand-authored display-threshold/feature iteration.** Run one bounded tiny linear candidate-level relevance classifier on the already retrieved Top-5, with no rank feature and no rank-order change. Fit on a deterministic 2023 concept split; calibrate visibility on a disjoint 2023 concept split with zero baseline-target loss; evaluate untouched on 2024. Positive label is the structured target; only different-SSYK4 non-targets are safe negatives; same-SSYK4 alternatives are unlabeled rather than taught as irrelevant. Candidates sharing rank-1 SSYK4 remain automatically visible. The preregistered strong gate is 2024 overall Hit@5 retention >=98%, rank-2–5 retention >=98%, and >=35% safe cross-SSYK negative reduction. Only if that gate or the preregistered promising gate passes may the frozen rule be replayed on opened user-style rows. If it also fails, stop simple display discrimination and reassess whether additional semantic evidence is required; do not build a general reranker stack by default.

Evidence: `research/evaluation/v31/p80-display-precision-opened-audit-v0.json`, `research/evaluation/v31/p80-display-relevance-opened-replay-v0.json`, `research/evaluation/v31/p80-display-lane-calibration-v0.json`, `research/evaluation/v31/p80-display-lane-historical-ads-v0.json`, `research/evaluation/v31/p80-display-natural-task-calibration-v0.json`, `research/evaluation/v31/p80-display-natural-rule-opened-replay-v0.json`, `research/evaluation/v31/p80-display-local-contrast-v0.json`, `research/evaluation/v31/p80-display-ssyk-phrase-gate-v1.json`, `research/evaluation/v31/p80-display-ssyk-phrase-opened-replay-v1.json`, and `research/evaluation/v31/p80-display-ssyk-unit-similarity-v0.json`.

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
