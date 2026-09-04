# Semantic retrieval study — Yrkesväljaren + Kompetensväljaren

**Study performed:** 2026-09-04  
**Committed:** 2026-09-05  
**Repository state reviewed:** `main` through `6b4578d5efa214139f56bad0d131d077cf20f1b8`  
**Scope:** architecture and research synthesis for shared semantic retrieval across Yrkesväljaren (YV) and Kompetensväljaren (KV).

> This document is a synthesis and architecture recommendation. `docs/research-plan.md` remains the single source of truth for active research status, gates and experiment order. When the two disagree because newer evidence has landed, the research plan wins.

## 1. Executive conclusion

The right abstraction is **one shared retrieval kernel with two different product contracts**, not one shared destination space and not two unrelated search implementations.

```text
                         shared retrieval kernel
user text ------------------------------------------------------+
  |                                                             |
  +-> lexical evidence                                          |
  +-> canonical/curated semantic text                           |
  +-> typed taxonomy graph                                      |
  +-> AF-derived context                                        |
  +-> observed query / employer language                        |
  +-> optional dense retrieval                                  |
                         |                                       |
                         v                                       |
                  candidate evidence                             |
                         |                                       |
                  constrained fusion                             |
                         |                                       |
                  optional reranking                             |
                         |                                       |
          +--------------+---------------+                       |
          |                              |                       |
          v                              v                       |
 YV product contract              KV product contract            |
 occupation-name or               active skill ID                |
 job-title + exact                                                |
 occupation context                                               |
```

The main design rule is:

> **Retrieval vocabulary may be much broader than selectable product identity. Evidence may help discover and rank an identity without becoming that identity.**

That distinction resolves several otherwise conflicting facts in the data: YV deliberately excludes valid taxonomy titles; job titles can belong to multiple occupations; KV uses occupation and SSYK context while returning skills; derived AF relations are useful without being canonical truth; and observed search/ad language is valuable despite lacking destination ground truth.

The study does **not** support starting with a chatbot, a large LLM-generated synonym bank, a monolithic vector index over flattened text, or a seven-million-ad ETL platform. The evidence supports a typed, provenance-preserving hybrid retrieval system measured by a judged benchmark before model complexity is added.

## 2. What the data already tells us

### 2.1 YV has a strict product identity boundary

Taxonomy v31 contains 2,105 active `occupation-name` concepts and 9,785 active `job-title` concepts. Published YV contains all 2,105 occupations but only 9,580 active job-title IDs.

The 205 omitted titles are not unexplained missing data. They are exactly explained by the public YV generator policy:

- 104 titles map to more than three occupation contexts;
- 101 are redundant because the title label is contained in every mapped occupation label.

This means an active taxonomy concept is not automatically a selectable YV result.

It also means those 205 titles should not be thrown away. They can be excellent **routing vocabulary**. A query such as a common excluded title can lead to valid YV destinations without the excluded title itself becoming selectable.

YV also has 541 admitted job-title IDs that occur in multiple occupation contexts. Therefore the stable YV identity for a title result is not just the job-title ID. It is the pair:

```text
(job-title ID, occupation-name ID)
```

Flattening this to a bare title destroys real product semantics.

### 2.2 Real query language is large and useful, but mostly unlabeled

The generator-bound Platsbanken query snapshot contains:

- 115,553 distinct query strings;
- 3,136,136,606 aggregate searches;
- data from 2022-05-04 through 2026-08-16.

Only 21.470% of query volume is an exact admitted YV label. Excluded-title labels account for 11.153% of all volume. The remaining 67.377% is unbound language.

This is strong evidence that retrieval vocabulary must be wider than canonical labels. It is **not** evidence that the 111,231 unbound strings can be auto-labelled by nearest string/vector similarity. The snapshot contains query text and frequency, not query → selected canonical destination truth.

So search frequency is a ranking/coverage signal, not a semantic label.

### 2.3 KV is text-sparse but not semantics-sparse

KV's destination space is the 6,752 active skill identities.

Canonical text alone looks weak: 5,098 skills have a definition equal to their preferred label. But the graph and product context are much richer:

- all active skills have skill-headline context in the measured common graph;
- only 18 lack SSYK4 context;
- 784 lack ESCO mapping;
- only one skill is simultaneously poor in canonical text, SSYK4 context and ESCO mapping, and even that skill is known in KV's typed transferable-skills container.

This matters architecturally: **missing prose is not equivalent to missing semantics**. Generating N synthetic descriptions for every skill would solve the wrong problem and erase useful distinctions between evidence types.

Published KV ordinary layers cover 4,647 / 6,752 active skills. Relevanta kompetenser covers 4,685 unique active skills and adds 404 skills beyond the ordinary KV union, bringing that combined union to 5,051 / 6,752.

Native taxonomy occupation→skill relations also prove an important non-independence:

```text
native optional = KV optional
native essential = KV essential + KV regulated
```

Those signals must not be counted twice simply because they arrive through two files/products.

### 2.4 Employer language fills real gaps

The v31 Närliggande-yrken material provides:

- 11,085 distinct employer-language keyword strings;
- source metadata covering 7,367,297 ads, of which 6,937,543 were enriched;
- keyword records for 1,051 occupations;
- 10,218 nearby-occupation similarity edges from 1,050 source occupations.

For occupations with poor canonical definitions, this corpus-derived material supplies substantial additional language. It is therefore valuable for discovery and benchmark construction.

But statistical similarity and ad-derived keyword association are not synonymy, identity or career-suitability authority.

## 3. The epistemic model is part of the architecture

The most important architectural requirement is not the embedding model. It is preserving **what each piece of evidence is allowed to mean**.

The current provenance classes are a good basis:

```text
canonical
curated_relation
derived_af
behavioral
corpus_derived
synthetic
```

For ad-derived data, field origin should remain distinguishable between raw employer text, employer-entered structured fields, system-derived taxonomy context and model-derived enrichment.

These classes are not merely ranking tiers. They are authority boundaries.

Examples:

- a canonical alternative label may support identity semantics;
- a job-title relation may support routing but does not make the title a synonym of the occupation;
- YV weight may be a strong prior without defining concept meaning;
- `relevance_points` may rank useful skills without proving they are required;
- an ad keyword may be excellent retrieval language without being canonical terminology;
- an LLM-generated phrase may improve recall without becoming benchmark truth.

This implies the retrieval representation should retain typed evidence/provenance instead of irreversibly concatenating all source material into one undifferentiated description.

## 4. Recommended retrieval architecture

### 4.1 Shared kernel, explicit target-space parameter

YV and KV should share infrastructure for normalization, lexical retrieval, semantic retrieval, evidence joining, candidate fusion, diagnostics and evaluation.

Every request must nevertheless declare its destination contract:

```text
YV -> published occupation-name
   | published job-title in exact occupation-name context

KV -> active skill
```

Cross-entity concepts — SSYK, occupation, skill headline, keyword, ESCO, excluded YV title, nearby occupation — can produce evidence and routes. They cannot silently change the destination type.

### 4.2 Hybrid candidate generation before sophisticated reranking

A robust baseline should union candidates from several channels rather than asking one representation to do everything:

1. exact and normalized lexical matches;
2. canonical preferred/alternative/hidden text where semantically permitted;
3. curated typed graph relations;
4. product-specific YV/KV context;
5. documented AF-derived relations;
6. observed employer/query language;
7. dense/vector retrieval over trusted representations where it adds measured recall.

Candidate fusion should remain deterministic and inspectable. A reranker can be added later, but only after the benchmark shows what it fixes.

The ordinary lexical path should remain privileged for exact/simple searches. Semantic search is primarily for descriptions, vocabulary mismatch, ambiguity and recovery when ordinary lookup is insufficient.

### 4.3 Keep evidence units typed

Do not build a single synthetic "perfect description" for each concept and discard provenance.

A better internal unit is concept identity plus typed evidence fragments, for example:

```text
candidate identity
  canonical text
  curated aliases
  job-title / occupation context
  SSYK / hierarchy context
  ESCO mapping context + mapping type
  KV relation context + layer type
  Relevanta context
  employer-language evidence
  observed-query evidence
```

The implementation can still precompile these into efficient local indexes or embeddings. The important point is that the original evidence type and relation semantics remain recoverable for ranking rules, debugging, ablation and explanations.

### 4.4 Product guard after retrieval

A high semantic score cannot override product admission.

Before returning results:

- YV candidates must resolve to an admitted occupation or an admitted job-title+occupation-context row;
- KV candidates must resolve to an active skill;
- ambiguous YV title contexts must stay distinct;
- retrieval-only vocabulary must route, not leak into the destination space;
- no valid result must remain an allowed outcome.

This guard should be deterministic.

### 4.5 Abstention is a normal result

Semantic nearest-neighbour search always has a nearest item. The product does not always have a valid answer.

Therefore confidence/relevance logic must support abstention and the benchmark must contain genuine `NO_MATCH` cases. Otherwise model tuning will reward confident false mappings.

## 5. Deployment: do not confuse serving topology with relevance architecture

The research does not justify choosing an API merely because the retrieval is semantic, nor local/static delivery merely because taxonomy releases are versioned.

The relevance architecture above works with either.

A sensible initial bias is to **compile stable semantic artifacts at taxonomy-version build time where practical**, because canonical/product data is versioned and reproducibility matters. Central serving becomes valuable when it materially improves iteration, model size, cross-product consistency, observability or update cadence.

Therefore local/static vs API should be evaluated as a deployment and operations trade-off after retrieval quality is understood, not baked into the semantic model.

## 6. Synthetic language and LLMs

The measured real sources materially weaken the case for generating large synthetic phrase sets up front.

Use this order:

```text
canonical taxonomy semantics
-> curated typed relations
-> YV/KV product context
-> Relevanta kompetenser
-> employer/ad language and measured similarity
-> observed query language with explicit join semantics
-> embeddings/reranking
-> synthetic language only for measured residual gaps
```

Synthetic data should enter only after an ablation demonstrates a specific gap. It must remain provenance-tagged and must never become canonical truth merely because it improves a metric.

Likewise, there is currently no evidence that an LLM belongs in the online serving path. A deterministic hybrid retrieval system plus optional learned/vector reranking is the lower-risk baseline. Add an LLM only if the benchmark exposes a class of failures it solves better enough to justify latency, cost and nondeterminism.

## 7. Evaluation must precede architecture optimization

The benchmark contract in `research/benchmark/` is not auxiliary test data; it is what makes architecture choices measurable.

YV and KV should have structurally compatible but separately scored suites. Important slices include:

- exact-label preservation;
- spelling, compounds, abbreviations and English/international wording;
- task/tool/long-description queries;
- rare and long-tail concepts;
- YV multi-context titles;
- YV's 205 excluded titles as routing vocabulary;
- unbound observed queries with human judgments;
- KV occupation→skill bridging;
- native/derived/calculated/transferable evidence differences;
- confusable siblings and explicit hard negatives;
- true no-match/abstention.

Do not optimize one global score. Recall gains that collapse YV context identity, promote excluded titles, double-count correlated evidence or increase confident no-match errors are regressions even if average nDCG improves.

The most useful experiments are controlled ablations: start with canonical lexical retrieval, then add one evidence family at a time and measure which strata actually improve.

## 8. What not to build yet

The current evidence argues against these early moves:

1. **One flat synonym bank.** It destroys relation type, identity and authority boundaries.
2. **One shared YV/KV destination index without target typing.** Shared infrastructure is correct; shared identity space is not.
3. **Automatic labels for the 111k unbound observed queries.** Their frequency does not provide destination ground truth.
4. **Synthetic descriptions for every concept as baseline.** Most apparent text gaps have real graph/context evidence already.
5. **A seven-million-ad normalization platform before the benchmark.** Bounded samples and already aggregated employer language are enough for the next research gate.
6. **A mandatory online LLM.** It introduces complexity before a measured need exists.
7. **A single semantic score that erases provenance.** Source correlation and authority differ materially.
8. **Treating deprecated replacements as synonyms.** Historical compatibility can route queries while preserving current identity and relation semantics.

## 9. Current state and next decisions

At the time of the original study, Gate 1 still required a unified per-target coverage matrix in addition to the unresolved Yrkesinformation join and deprecated compatibility semantics.

The repository has since advanced: `scripts/unified_target_coverage.py` now implements a fail-closed v31 matrix builder over accepted source hashes. `docs/findings/offline-target-coverage-v31.md` also provides a conservative artifact-reconstructed matrix where unavailable per-ID facts remain `UNKNOWN` rather than being inferred from aggregates.

That strengthens, rather than changes, the architecture conclusion: semantic coverage is multi-dimensional and provenance-sensitive.

Recommended continuation:

1. complete/validate Gate 1 rather than adding new semantic sources opportunistically;
2. freeze deterministic YV/KV benchmark populations and obtain human judgments for ambiguous/unbound/no-match cases;
3. establish lexical and simple hybrid baselines;
4. run evidence-layer and model ablations;
5. choose vector model, fusion/reranking strategy and deployment topology from measured failures rather than intuition;
6. only then decide whether synthetic data or an LLM adds enough marginal value.

## 10. Files that substantiate this study

Primary living contracts:

- `docs/research-plan.md`
- `docs/source-inventory.md`
- `research/benchmark/README.md`
- `research/coverage/source-adapters.json`

Key measured findings:

- `docs/findings/native-text-coverage-v31.md`
- `docs/findings/common-relations-coverage-v31.md`
- `docs/findings/selector-coverage-v31.md`
- `docs/findings/selector-residual-gaps-v31.md`
- `docs/findings/native-occupation-skill-relations-v31.md`
- `docs/findings/derived-af-semantic-coverage-v31.md`
- `docs/findings/yv-generator-exclusion-policy-v31.md`
- `docs/findings/yv-observed-query-language-v31.md`
- `docs/findings/job-ad-source-boundaries-2026-09-04.md`
- `docs/findings/deprecated-compatibility-policy-v31.md`
- `docs/findings/offline-target-coverage-v31.md`

Executable contracts and research machinery live under:

- `scripts/`
- `research/coverage/v31/`
- `research/benchmark/schema/`
- `.github/workflows/`

The study should be challenged against those sources, not treated as a substitute for them.
