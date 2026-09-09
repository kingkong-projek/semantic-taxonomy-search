# Single source of truth

Updated: 2026-09-09.

This file is the canonical entrypoint for **current execution state**. Historical experiments remain in `docs/findings/` and `research/`; they are evidence, not competing active plans.

## Authority

1. The newest explicit amendments at the top of `docs/research-plan.md` define scope, gates and experiment order.
2. This file states the current execution state in compact form.
3. `docs/findings/*` and `research/*` contain supporting/falsifying evidence.
4. Older sections remain historical when a newer dated amendment explicitly supersedes them.

## Current state in one screen

Product sequence remains:

`ordinary YV/KV lookup -> semantic description fallback -> Ge förslag only if no acceptable existing concept is found`.

For occupation Track 2, the **retrieval architecture question is provisionally settled**. Keep the simple A-family boundary: privileged exact/canonical lexical routing plus one teacher-expanded sparse/BM25 description ranker. Do not revive B/C/E or activate a general two-stage reranker merely to chase benchmark gains.

All **2,105 active v31 occupation-name identities** remain valid retrieval destinations. P80 is only the current demand-priority evaluation stratum: **159 occupations covering about 80% of the frozen historical occurrence proxy**.

The current deployed YV research/runtime boundary remains **A593**. The P80-enriched challenger is research-only until independent human/user confirmation is available. P90/P95/full-tail expansion remains deferred.

The P80 language experiment is strong source-bound mechanism evidence: over full 2,105-candidate competition, Top1 moved **53.99% -> 65.02% (+11.03 pp)** and Hit@5 **77.70% -> 83.57% (+5.87 pp)**. Source-thin rescue also showed that canonical-thin occupations can have useful AF evidence elsewhere. This is **not human accuracy**.

The primary active product-quality residual is now **display precision**: the ranker can put a genuinely useful occupation at rank 2–5 while also filling Top-5 with professionally implausible alternatives. A fixed Top-N cutoff is therefore not acceptable; Hit@5 is valuable precisely because many correct results are below rank 1.

## What is already falsified for display precision

Do **not** deploy or retune any of these from opened stress rows:

- merged BM25 score thresholds / score gaps;
- lexical/query coverage thresholds;
- lane-aware phrase support;
- Top-5-local lexical contrast;
- SSYK4 + phrase heuristics;
- coherent single-evidence-unit TF-IDF similarity;
- the tiny linear Top-5 relevance classifier over lexical/SSYK-derived features.

The linear classifier is the strongest warning against proxy overconfidence. On untouched 2024 historical task-text proxy data it retained **167/167 Hit@5** and **87/87 rank-2–5 targets** while reducing safe different-SSYK4 negatives **48.46%** and shortening the mean list `5.00 -> 2.79`. The exact frozen model then failed user-style replay: Hit@5 **28 -> 24**, rank-2–5 targets **13 -> 9**, and obvious junk often remained. For example, the nursing case still kept `Apotekare`, `Receptarie` and `Sjukhusvaktmästare`; the electrician case still kept `Växeltelefonist` and `Affärskonsult, IT`.

Conclusion: **the current lexical/BM25-derived feature family does not encode the semantic relevance distinction well enough.** Stop threshold rescue work.

## Active experiment: separate semantic candidate relevance

This is now the single primary parallel research question until human/domain-expert relevance data is available.

### V0 purpose

First prove that **additional semantic information is sufficient** before designing a production student/runtime mechanism.

Use the existing P80 A-family ranker only to retrieve Top-5. Then let a research-only semantic teacher judge each already-retrieved candidate independently as `keep`, `uncertain`, or `drop`.

Hard boundaries:

- retrieval candidate universe and rank order are unchanged;
- the semantic teacher is **not** a new retrieval ranker;
- rank/position is hidden from the teacher; candidate order in the prompt is deterministically shuffled;
- candidate evidence is source-bound: canonical label/definition plus already-frozen source-bound teacher phrases; insufficient evidence must yield `uncertain`, not invented facts;
- rank 1 is retained in v0; for ranks 2–5 only a confident `drop` removes a candidate;
- opened 17/88 user-style rows are never used to choose prompt, model, labels, threshold or decision rule;
- the teacher is research/oracle evidence only. **No runtime LLM/API is permitted by this experiment.**

### Primary evaluation

Use natural historical **2024 Platsbanken task text** with the structured occupation as target, over the same full **2,105-candidate** retrieval universe. Exclude the 22 rescue identities from the primary proxy set to avoid source-overlap ambiguity, matching the previous natural-task safety protocol.

Evaluation labels:

- positive: structured target when present in Top-5;
- conservative safe negative: non-target candidate in a different SSYK4 from the structured target;
- same-SSYK4 non-target: unlabeled for precision accounting because it may be a legitimate neighboring occupation.

The semantic teacher receives neither the structured target nor SSYK4 labels.

Prefrozen gate for semantic-oracle v0:

- rank-1 target retention: **100%** by the display contract;
- overall baseline Hit@5 target retention: **>=99%**;
- rank-2–5 target retention: **>=98%**;
- safe different-SSYK4 negative reduction: **>=60%** for a strong pass;
- a bounded promising result is `>=98% / >=98% / >=50%` respectively.

Only a strong/promising pass permits an **unchanged diagnostic replay** on the opened user-style stress set. Opened replay may falsify transfer but may never retune the teacher or its rule.

### Decision after semantic-oracle v0

If the semantic teacher also transfers to user-style stress, then semantic information has earned its complexity. The next step is **distillation/compilation into a small deterministic runtime-compatible student**, still preserving the existing retrieval ranker initially. The production target remains no runtime LLM, no provider API, small browser artifact, deterministic behavior and measurable parity.

If the semantic teacher itself does **not** separate useful rank-2–5 candidates from obvious junk, do not build a student. Reassess candidate evidence and the product interaction instead of adding another heuristic stack.

## Human validation

Fresh independent human/user descriptions and relevance judgments remain the decisive evidence when available. We do not currently have access to them, so work continues in parallel without pretending proxy or teacher judgments are human accuracy.

Use the existing frozen human-study boundary when data becomes available:

- `docs/findings/description-fallback-human-validation-protocol-v31.md`
- `research/human/description-fallback-v1/README.md`
- `research/human/description-fallback-v1/participant-instructions-sv.md`
- `research/human/description-fallback-v1/preregistration-template.json`

Do not promote the P80 challenger or a display discriminator solely from synthetic/historical/teacher evidence.

## Skills / KV

KV is not the active residual in this display investigation. Keep the existing simple research/runtime boundary **KV-G1+T3** unless new independent evidence reopens it.

## Track 1 boundary

Broad YV/KV selector-audit expansion remains parked. The bounded field-feedback replay remains historical/actionable evidence for product-native defects, owned by `kingkong-projek/yrkesvaljaren`. This repository owns semantic-search evidence and architecture decisions, not YV/KV deployment.

## Key evidence

Retrieval/language:

- `docs/findings/p80-language-diversity-result-2026-09-09.md`
- `research/evaluation/v31/p80-language-diversity-result-v0.json`
- `research/evaluation/v31/p80-language-diversity-canonical-guard-diagnosis-v0.json`
- `research/evaluation/v31/p80-source-thin-rescue-result-v0.json`
- `docs/findings/compile-time-architecture-breadth-result-2026-09-09.md`
- `research/evaluation/v31/compile-time-semantic-architecture-breadth-result.json`

Display precision / falsifiers:

- `research/evaluation/v31/p80-display-precision-opened-audit-v0.json`
- `research/evaluation/v31/p80-display-natural-task-calibration-v0.json`
- `research/evaluation/v31/p80-display-natural-rule-opened-replay-v0.json`
- `research/evaluation/v31/p80-display-local-contrast-v0.json`
- `research/evaluation/v31/p80-display-ssyk-phrase-gate-v1.json`
- `research/evaluation/v31/p80-display-ssyk-phrase-opened-replay-v1.json`
- `research/evaluation/v31/p80-display-ssyk-unit-similarity-v0.json`
- `research/evaluation/v31/p80-display-linear-relevance-v0.json`
- `research/evaluation/v31/p80-display-linear-relevance-opened-replay-v0.json`

## Cross-repository boundary

`kingkong-projek/semantic-taxonomy-search` owns evidence, classification, semantic-retrieval research and the decision whether a residual justifies additional semantic machinery.

`kingkong-projek/yrkesvaljaren` owns reproducible YV/KV product behavior, fixes and regression tests. Its feedback-specific product SSOT is `docs/findability-feedback-ssot.md`.
