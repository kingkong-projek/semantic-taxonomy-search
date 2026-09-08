# Compile-time semantic architecture breadth gate — 2026-09-08

## Decision

Stop local micro-optimisation of the current A593 sparse/contrast lane and enter a short **architecture breadth phase**.

The purpose is not to build a hybrid stack. It is to cheaply falsify a few materially different simple representations, then return to one winner and optimise only that winner.

The desired end state remains simple: **one semantic description ranker/index plus the already-privileged exact/canonical lexical path**. Ensembles, query classifiers, pair-specific rule banks and multi-stage rerank stacks are not the default destination.

## Why the decision changed

The latest A593 explicit pair-contrast experiment is locally real but globally small:

- frozen 4,744 teacher holdouts: Top1 `1576 -> 1586` (**+10**, +0.2108 percentage points), Hit@5 `2957 -> 2965` (**+8**, +0.1686 pp), MRR `0.464618 -> 0.466288`;
- on the 176 holdouts belonging to the 11 distinguishable targeted confusion pairs: **+10 Top1**, **+8 Hit@5**, MRR **+0.045016**;
- on the subsequent frozen opened replay versus the relation-aware base: **0 delta** on targetable40 Top1, targetable40 Hit@5, strict17 Top1, strict17 Hit@5 and strict17 MRR.

This means the source-bound contrast notes can solve the exact distinction they encode, but the current compile form does not improve the measured user-like/source-attested transfer residual. Together with the prior stemming, char-centroid and hard-negative results, this is enough evidence to stop treating another A593 weighting tweak as the highest-value next experiment.

Evidence:

- `research/evaluation/v31/compile-time-semantic-a593-explicit-contrast-layer.json`
- `research/evaluation/v31/compile-time-semantic-a593-explicit-contrast-opened-replay.json`

## Constraints carried unchanged

- Build-time semantic intelligence; no runtime LLM.
- No general transformer inference in the browser.
- Teacher/build marginal API spend for this tournament remains `<= 10 SEK`, with zero-cost hosted access preferred.
- Generated evidence must be source-bound to public/canonical taxonomy evidence. No evidence means no invented occupational distinction.
- Canonical identities are immutable output targets.
- Opened 17/88 cases are replay-only and must not drive feature, threshold or architecture tuning.
- Preferred compressed incremental frontend artifact `<= 3 MB`; `> 5 MB` is a frontend-track failure absent a new explicit decision.
- Ordinary YV/KV lookup stays privileged; this research concerns the description fallback.

## Simplicity contract

Research may temporarily compare several lanes, but the product target must not become an architecture collage.

Default admissible final form:

```text
exact/canonical lexical route
        +
one semantic description ranker/index
```

A semantic entrant should therefore be independently useful. Do not combine two weak entrants merely to manufacture a stronger score.

A second semantic stage (for example retrieval -> local discriminator) is allowed only as a later escape experiment and must earn a **much larger** quality gain than a single-stage alternative. Pair-specific rules, hand-authored confusion maps and query-type classifiers are rejected as default production architecture regardless of small benchmark gains.

## Breadth tournament

### Baseline A — frozen expanded sparse lane

Keep the best existing A593 evidence as the reference family. Do not perform more local weighting, stemming, hub, hard-negative or pair-rule tuning during breadth selection.

This lane answers: how far does `teacher language -> sparse retrieval` already get us?

### Challenger B — supervised sparse classifier

Test the smallest genuinely discriminative single-stage model:

```text
query word/character n-grams -> learned concept weights -> top occupations
```

Requirements:

- one model, no reranker;
- prefer hashed word/character n-grams and a linear objective;
- train against positive concepts plus corpus-internal hard negatives;
- quantise/prune only after the uncompressed diagnostic establishes whether the architecture has a better quality ceiling;
- report both transfer quality and the projected/actual compiled sparse weight size.

This specifically tests whether the current plateau is caused by centroid/BM25-style representation rather than by the available language itself.

### Challenger C — task/activity representation

Test a single-stage task-mediated representation rather than direct occupation-document matching:

```text
source-bound work/task atoms -> occupation memberships/weights
query -> task evidence -> occupation score
```

This is not a two-model hybrid. The task layer is the representation being indexed.

Requirements:

- task/activity atoms must be derivable from public canonical/source evidence or strictly source-bound teacher rewrites;
- shared tasks may point to several occupations; weak evidence must not be forced into one identity;
- runtime should remain sparse deterministic scoring/aggregation;
- do not add an occupation reranker in the first falsification.

This tests the hypothesis that reusable work activities generalise better than 593 separate occupation-language documents.

### Deferred D — coarse retrieval -> local discriminator

Do **not** build this during the first breadth round. It is structurally more complex because it introduces a second semantic stage.

Only test it if both B and C fail to clear the single-stage materiality bar but diagnostics show strong candidate recall with systematic within-family confusion. It must then beat the best single-stage entrant by at least the stronger complexity bar below.

## Common prefrozen transfer proxy

Teacher self-retrieval is no longer sufficient for architecture selection. Before fitting B or C to a new proxy, freeze one common cross-style transfer set that none of the entrants sees during training.

Construct it without using wording from the opened 17/88 cases:

- select concepts deterministically from the frozen A593 universe using taxonomy/source properties and frozen corpus difficulty, not opened-query outcomes;
- cover several occupation families and difficulty strata;
- generate separate held-out formulations in generic styles already defined by the product problem: direct task description, colloquial first-person language, indirect narrative and noisy/telegraphic language;
- every formulation must be checked against the source-bound evidence contract;
- prefer an independent zero/very-low-cost teacher for the held-out wording when available; otherwise use a separately frozen prompt/revision and generation pass;
- freeze the proxy before comparing B versus C.

This proxy remains synthetic/model-authored architecture evidence, not a human accuracy estimate. Final promotion still requires fresh independent human/user evidence.

## Materiality / kill rules

The breadth phase is intentionally coarse. We are looking for a different ceiling, not benchmark crumbs.

For a **single-stage** challenger to survive:

1. it must preserve the exact/canonical regression guards;
2. on the prefrozen cross-style transfer proxy it should improve the frozen A-family baseline by at least **5 absolute percentage points** on a primary rank-sensitive metric (prefer Top1/first-acceptable-rank; Hit@5 remains secondary), without a material counter-regression in another major stratum;
3. the gain must include colloquial and/or indirect language, not only direct descriptions;
4. it must remain compatible with the `<=3 MB` preferred / `>5 MB` fail frontend boundary after plausible pruning/quantisation;
5. it must not require runtime teacher/model inference.

If the observed difference is below this bar, treat the entrant as the same practical quality tier and prefer the simpler implementation.

For a **two-stage** semantic architecture to survive later, require at least **10 absolute percentage points** improvement over the best surviving single-stage candidate on the prefrozen transfer proxy, plus a clear mechanistic reason for the extra stage. Otherwise reject the complexity.

Do not optimize thresholds to land exactly on these bars. They are decision thresholds, not tuning targets.

## Execution order

1. Freeze this decision and keep A593/A2105 generation paused.
2. Freeze the common cross-style transfer proxy.
3. Build the minimal supervised sparse B falsifier and measure it.
4. Build the minimal task/activity C falsifier and measure it.
5. Compare A/B/C on the same frozen evidence and bytes/runtime constraints.
6. Kill losing architecture families.
7. Optimise only the simplest surviving winner.
8. Consider deferred D only if the single-stage lanes fail and the failure mechanism specifically justifies it.
9. Resume A2105/full-universe generation only if the winning architecture requires broader identity coverage to answer a remaining measured question.

## Current interpretation

We have **not** established a ceiling for compile-time semantics. We have established enough of a plateau for the current `A593 + same teacher distribution + increasingly clever sparse discrimination` line that continued local tuning is lower-value than a bounded breadth comparison.

The next objective is therefore not `make A593 0.2 pp better`. It is: **find out whether a different simple representation buys a materially higher transfer ceiling.**