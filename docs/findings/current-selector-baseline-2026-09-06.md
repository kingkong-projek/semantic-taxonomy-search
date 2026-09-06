# Current YV/KV selector baseline — 2026-09-06

**Status:** code-audited  
**Reference implementation:** `kingkong-projek/yrkesvaljaren`  
**Pinned main commit:** `0eba98e3a91079a43c1eaf6da09dfabe11e5bc8b`

## Why this matters

The semantic-search project is primarily intended to add a **description/natural-language fallback** when the ordinary selector cannot help the user find the taxonomy concept they need. The current YV/KV implementations are therefore the product baseline. Research-only BM25 configurations such as occupation/skill C0 are ablation instruments; they are not substitutes for measuring the actual selectors.

A second, optional research question remains open: if one simple retrieval engine eventually preserves or improves the current selector behaviour *and* solves description search, it may become attractive to unify the implementation. Replacement is a bonus hypothesis, not the v0 requirement.

## Current Yrkesväljaren search

Source: `src/components/job-selector/search.utils.ts` at the pinned commit.

The ordinary YV search is local lexical/fuzzy retrieval over product data, not semantic description search.

Direct matching precedence/score:

- exact preferred label: `1.00`;
- single-token prefix: `0.99`;
- multi-token query: every query token must occur in the label, `0.98`;
- substring/contains: `0.95`.

If **any direct match exists**, YV returns the sorted direct matches and does not mix in Fuse candidates. Results sort by match score, then YV behavioural `weight`, then Swedish label order.

Only when there are no direct results does Fuse.js become the fallback. The fuzzy path has minimum/maximum score guards, a best-result gap guard, extra support for likely word/compound-root matches, and deliberately small result limits (up to 5 for strong-root fuzzy; otherwise at most 3).

Consequences:

1. exact/prefix/substring/ordinary misspelling queries are already a relatively strong baseline;
2. a semantic-fallback benchmark should not claim value merely by solving these cases again;
3. semantic occupation research should focus on descriptions, tasks, tools/methods, colloquial paraphrases and other queries for which the ordinary selector has insufficient lexical evidence;
4. the current YV implementation itself must be included as the baseline when estimating incremental fallback value.

## Current Kompetensväljaren search

Sources:

- `packages/kompetensvaljaren/src/components/kompetensvaljaren/logic/search.engine.ts`;
- `docs/kv_sokfilosofi_och_refaktoreringsplan.md`.

KV is also not a semantic description engine today, but it has more domain-aware ranking than a plain label search.

At non-empty query:

- candidate generation is global across skills;
- direct text matching distinguishes exact, prefix, word-boundary and contains;
- Fuse is a conservative typo candidate generator;
- occupation/SSYK context, context-list category and precomputed `weightedSkills` may influence ordering/domain score **only among candidates that text/fuzzy already matched**;
- context is not allowed to manufacture unrelated text candidates.

At empty query:

- with context, KV shows a prioritised context list (`regulated -> essential -> optional -> calculated -> related` plus prepared weighted ordering);
- without context, it shows `most_common_skills`.

The documented invariant is that all skills remain globally reachable by text even under an unrelated occupation context; fuzzy should return nothing for nonsense rather than always invent a nearest candidate.

Consequences:

1. the current KV `HybridSearchEngine` is the real lexical/context baseline;
2. description-style skill benchmarks should compare it directly against any semantic fallback, not merely against research BM25 C0;
3. the already frozen manual labour-market-training text benchmark is relevant to the fallback use case because it contains specialised descriptions mapped by humans to skills, but its next decision-bearing evaluation must include the current KV engine;
4. occupation/context-derived lanes may already be partially represented in ordinary KV ranking, so semantic experiments must not count duplicating current product behaviour as incremental gain.

## Two evaluation questions

### A. Fallback value — primary v0 question

```text
ordinary YV/KV selector does not provide an adequate discovery result
                         ↓
user chooses/enters description mode
                         ↓
natural description / tasks / tools / methods / colloquial wording
                         ↓
semantic fallback
                         ↓
small product-valid candidate list containing the intended identity
```

Primary measures:

- incremental Discovery Success@5 **over the current selector** on fallback-eligible queries;
- correct abstention/noise;
- product-valid identity/admission preservation;
- latency/payload/browser cost.

### B. Full-replacement potential — secondary bonus question

Run the same candidate engine against the current selectors' ordinary exact/prefix/substring/fuzzy/context regression suites.

A replacement is interesting only if it simultaneously:

- preserves current ordinary lookup behaviour and product identity semantics;
- matches/exceeds current latency and client footprint sufficiently;
- handles description fallback materially better;
- does not add operational complexity merely to remove a working lexical lane.

Until that is demonstrated, the default architecture remains **ordinary selector first + semantic description fallback**. A future unified implementation may still contain an explicit privileged lexical lane internally; “one engine” does not imply “semantic similarity for every query”.

## Benchmark consequence

The research benchmark now needs an explicit `fallback_eligible`/baseline-outcome view:

- canonical preferred/alternative-label cases remain regression tests, not evidence of semantic fallback value;
- typo/prefix/substring cases primarily measure replacement compatibility;
- description/task/tool/method/colloquial cases measure fallback value;
- every decision-bearing fallback evaluation should record what the pinned current selector returned at K for the same query;
- semantic gain is the **increment over the current selector**, not the semantic candidate's absolute score in isolation.
