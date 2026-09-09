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

For occupation Track 2, the retrieval architecture is provisionally settled. Keep the simple A-family boundary: privileged exact/canonical lexical routing plus one teacher-expanded sparse/BM25 description ranker. Do not revive B/C/E or add a general retrieval reranker merely to chase benchmark gains.

All **2,105 active v31 occupation-name identities** remain valid retrieval destinations. P80 is a demand-priority evaluation stratum: **159 occupations covering about 80% of the frozen historical occurrence proxy**.

The current deployed YV boundary remains **A593**. P80 enrichment and every display discriminator remain research-only. No runtime LLM/provider API is permitted.

The P80 language experiment remains strong source-bound retrieval evidence: over full 2,105-candidate competition, Top1 moved **53.99% -> 65.02% (+11.03 pp)** and Hit@5 **77.70% -> 83.57% (+5.87 pp)**. This is not human accuracy.

The primary active product-quality residual is **display precision**: a useful occupation can sit at rank 2–5 while Top-5 also contains professionally implausible alternatives. A fixed Top-N cutoff is therefore not acceptable.

## Display precision: lexical family is closed

Do **not** deploy or retune from opened stress rows any of:

- merged BM25 score thresholds / score gaps;
- lexical/query coverage thresholds;
- lane-aware phrase support;
- Top-5-local lexical contrast;
- SSYK4 + phrase heuristics;
- coherent single-evidence-unit TF-IDF similarity;
- the linear Top-5 relevance classifier over lexical/SSYK-derived features.

The linear classifier demonstrated the proxy trap: on untouched 2024 historical task-text proxy data it retained **167/167 Hit@5** and **87/87 rank-2–5 targets**, but exact frozen user-style replay degraded to **28 -> 24 Hit@5** and **13 -> 9 rank-2–5 targets**. Conclusion: the lexical/BM25-derived feature family does not encode the required semantic distinction reliably enough. Stop threshold rescue work.

## Separate semantic candidate relevance — v0 result

The research-only semantic oracle answers a narrower question: after the existing ranker has produced its candidates, is additional semantic information sufficient to decide which visible candidates are plausible?

Frozen v0 contract:

- retrieval and rank order unchanged;
- teacher sees no retrieval rank, structured target or SSYK;
- candidate order is deterministically shuffled;
- source-bound evidence only: `label-alt3-definition50-task2x24-v0`;
- verdicts `keep | uncertain | drop`; insufficient evidence => `uncertain`;
- rank 1 is retained; ranks 2–5 are removed only on confident `drop`;
- no runtime LLM/API implication.

Exact preregistration: `research/evaluation/v31/p80-display-semantic-oracle-preregistration-v0.json`.

### Primary 2024 proxy: STRONG PASS

Frozen result: `research/evaluation/v31/p80-display-semantic-oracle-v0.json`.

Over natural 2024 Platsbanken task text with full 2,105-candidate retrieval competition:

- Hit@5 target retention: **167/167 = 100%**;
- rank-2–5 target retention: **87/87 = 100%**;
- rank-specific retention: **80/80, 37/37, 18/18, 19/19, 13/13** for ranks 1–5;
- safe different-SSYK4 rank-2–5 negatives: **2,469 -> 908**, **63.22% removed**;
- mean visible list: **5.00 -> 2.67**.

The preregistered strong gate passed. The source contains 674 evaluation rows but 672 unique case keys because two rows are exact duplicate ad/query cases; report this as a sampling detail, not 674 independent cases. The conclusion is unchanged by those duplicates.

Interpretation: **semantic information has now shown a large capability advantage over the lexical display filters.** This is sufficient to keep semantic candidate relevance as the main research direction, but it is not sufficient for distillation or production.

### Exact opened user-style replay: FORMAL FAIL

Frozen result: `research/evaluation/v31/p80-display-semantic-oracle-opened-replay-v0.json`.

The unchanged oracle performed strongly overall:

- targetable Hit@5: **28/28 -> 28/28**;
- genuine rank-2–5 hits: **13/13 -> 13/13**;
- mean visible list: **4.593 -> 2.519**;
- full five-result lists: **49 -> 5**;
- electrician sanity (`yv02`): **passed**.

But the preregistered opened acceptance **failed** because nursing sanity (`yv01`) failed. The oracle dropped `Sjukhusvaktmästare` but kept `Apotekare` and `Receptarie` as `uncertain`; the frozen gate required at least two of those three to be removed while retaining a nursing-family result.

This failure must not be relabeled as a pass merely because aggregate metrics were excellent.

## Current decision

1. **Do not distill semantic-oracle v0.**
2. **Do not retune v0 on `yv01`, `yv02`, or any opened 17/88 row.** Opened data remains replay/falsification only.
3. Keep the existing retrieval ranker unchanged while investigating semantic candidate relevance.
4. The next decision-bearing evidence must be **independent** of the opened stress set.
5. The specific residual to explain is now narrower: semantic v0 can remove broad irrelevant tails without losing real lower-rank hits, but its compact candidate evidence is sometimes insufficient to reject plausible adjacent-domain roles and therefore returns `uncertain`.
6. Any v1 evidence/prompt/evidence-contract change must be motivated and developed from independent source-bound data, preregistered before evaluation, and then tested on untouched independent data. It may not be justified by tuning to the known nursing failure.
7. Runtime target remains a small deterministic browser-compatible student only **after** an oracle/evidence contract earns that step. No runtime LLM/provider API.

## Next research step

Use independent source-bound hard-confusion evidence to test whether **richer candidate-specific discriminative evidence** resolves near-role ambiguity without harming target retention. Existing compile-time confusion work is admissible as mechanism evidence because it was generated without opened rows; for example `research/evaluation/v31/compile-time-semantic-a593-confusion-task-atoms-v0.json` contains 11 frozen confusion pairs / 22 concepts and explicitly records that contrast cues/descriptions were not supplied to its generator.

The next experiment must therefore be contrastive in **evidence**, not another score threshold:

- derive candidate-specific task/responsibility evidence from independent source-bound material;
- never encode `yv01`/`yv02` labels or known desired outcomes;
- preregister a hard-confusion development/evaluation split before oracle outcomes;
- require preservation of useful candidates as well as removal of independently defined safe negatives;
- only if that independent v1 evidence passes may the unchanged opened set be replayed again as a falsifier.

Do not build the compact student before this step passes.

## Human validation

Fresh independent human/user descriptions and relevance judgments remain the decisive evidence when available. Proxy and teacher judgments are not human accuracy.

Use the existing frozen human-study boundary when data becomes available:

- `docs/findings/description-fallback-human-validation-protocol-v31.md`
- `research/human/description-fallback-v1/README.md`
- `research/human/description-fallback-v1/participant-instructions-sv.md`
- `research/human/description-fallback-v1/preregistration-template.json`

Do not promote the P80 challenger or a display discriminator solely from synthetic/historical/teacher evidence.

## Skills / KV

KV is not the active residual in this display investigation. Keep **KV-G1+T3** unless new independent evidence reopens it.

## Track 1 boundary

Broad YV/KV selector-audit expansion remains parked. Feedback-specific product defects are owned by `kingkong-projek/yrkesvaljaren`; this repository owns semantic-search evidence and architecture decisions.

## Key evidence

Retrieval/language:

- `docs/findings/p80-language-diversity-result-2026-09-09.md`
- `research/evaluation/v31/p80-language-diversity-result-v0.json`
- `research/evaluation/v31/p80-source-thin-rescue-result-v0.json`
- `docs/findings/compile-time-architecture-breadth-result-2026-09-09.md`

Display precision / semantic relevance:

- `research/evaluation/v31/p80-display-precision-opened-audit-v0.json`
- `research/evaluation/v31/p80-display-linear-relevance-v0.json`
- `research/evaluation/v31/p80-display-linear-relevance-opened-replay-v0.json`
- `research/evaluation/v31/p80-display-semantic-oracle-preregistration-v0.json`
- `research/evaluation/v31/p80-display-semantic-oracle-v0.json`
- `research/evaluation/v31/p80-display-semantic-oracle-opened-replay-v0.json`
- `research/evaluation/v31/compile-time-semantic-a593-confusion-task-atoms-v0.json`

## Cross-repository boundary

`kingkong-projek/semantic-taxonomy-search` owns evidence, classification, semantic-retrieval research and the decision whether a residual justifies additional semantic machinery.

`kingkong-projek/yrkesvaljaren` owns reproducible YV/KV product behavior, fixes and regression tests. Its feedback-specific product SSOT is `docs/findability-feedback-ssot.md`.
