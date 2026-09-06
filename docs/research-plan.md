# Semantic Taxonomy Search — living research plan

**Status:** active research  
**Target taxonomy snapshot:** v31 unless an experiment explicitly says otherwise  
**Last updated:** 2026-09-06  
**Authority:** this file is the single source of truth for product scope, current conclusions, research gates and experiment order. Findings and generated inventories provide evidence; when evidence changes a conclusion, this file must change too.

## 1. Product problem

We are building a **reusable semantic retrieval capability for occupations and skills/competences** in services where a user must identify or select taxonomy concepts without knowing the taxonomy's exact wording.

Yrkesväljaren (YV) and Kompetensväljaren (KV) are current **reference profiles**, not the scope boundary of the retrieval core. JobSearch/Platsbanken and other AF datasets are evidence sources, not the target product.

The core target spaces are intentionally simple:

- **occupation:** canonical active `occupation-name` identities;
- **skill:** canonical active `skill` identities.

A consuming service applies its own admission/profile rules after or around retrieval. YV may therefore admit published occupation/job-title identities with exact occupation context, while another service may admit a different occupation subset. KV is one concrete skill-selection profile.

Occupation context, job titles, SSYK, skill-headline, keyword, ESCO and other concepts may be used as evidence/routing/context. They are not interchangeable with the returned core identity.

Hard shared rule:

> Semantic retrieval may discover, expand, route, rank and explain candidates. It may never invent, merge or mutate canonical taxonomy identities, and it may never bypass the consuming service's explicit admission policy.

## 2. Product UX hypothesis

Do not replace ordinary selectors with a chatbot.

Keep fast lexical selection as the privileged path where a consuming service already has it. Add semantic description search when ordinary lookup is insufficient. YV/KV remain useful reference UX examples:

```text
YV: Hittar du inte det du söker? [Beskriv yrket]
KV: Hittar du inte kompetensen? [Beskriv kompetensen / vad du kan göra]
```

The core result remains an exact canonical occupation/skill identity with provenance; the consumer then enforces its admission profile. `Inget av dessa` / abstention is a first-class successful outcome. A nearest neighbour is not proof that a valid match exists.

### 2.1 Pareto / simple-first delivery principle

The semantic feature is **not required to solve the full taxonomy long tail in v0**. The existing lexical picker remains the complete deterministic fallback over the product's canonical destination universe. Semantic retrieval may start with a narrower confidence envelope and abstain outside it.

Product/research priority is therefore:

```text
high-demand + high-confidence + cheap-to-explain cases
→ measure real incremental value
→ add the smallest next capability that fixes a material residual
→ defer rare/weakly evidenced tail until data shows it matters
```

Where real demand data exists, optimise the first release for cumulative user value rather than equal concept coverage. Platsbanken/YV provides one measured source of real occupation-query language for sampling; it is evidence about that usage context, not the scope of the engine. For concept-level prioritisation across occupation and skill target spaces, Historical API taxonomy occurrence counts are now measured as one simple shared corpus/popularity proxy. They are **not user traffic** and are never mislabeled as query→selection evidence.

This creates two benchmark views:

1. **Pareto/product-value view** — weighted toward common/high-confidence use where demand evidence exists;
2. **safety/regression view** — small explicit slices for ambiguity, excluded routes, hard negatives and abstention so weighted metrics cannot hide dangerous failures.

Long-tail recall remains measurable but is not a v0 launch gate. A rare concept failing semantic retrieval is acceptable when lexical retrieval still works and semantic search abstains safely.

Complexity has a burden of proof. A new source, retrieval lane, model, reranker or deployment component is admitted only if it produces a material measured gain on the Pareto view or fixes a defined safety/regression failure. If two configurations perform similarly, prefer the one with fewer sources, rules, models and moving parts.

## 3. Architectural hypothesis

The feature is larger than "put embeddings on autocomplete".

```text
user text
  ↓
query interpretation
  ├─ lexical retrieval
  ├─ curated semantic text
  ├─ typed taxonomy graph/context
  ├─ AF-derived context
  ├─ corpus / observed language
  └─ optional vector retrieval
          ↓
      candidate union
          ↓
 constrained deterministic fusion
          ↓
 optional reranking
          ↓
 typed product-valid canonical candidates + provenance
```

Each core request has an explicit semantic target space independent of the consuming service:

```text
occupation -> active canonical occupation-name candidates
skill      -> active canonical skill candidates
```

A separate consumer/admission profile constrains what a specific service may present or select. YV and KV are the first measured profiles; they are not hard-coded engine target spaces. Cross-entity bridges generate evidence; they do not convert identity.

Current strongest data principle:

> **Use existing semantics before manufacturing semantics.**

Current deployment principle:

> **Compile semantics when practical; serve semantics where central iteration materially improves the product.**

Local/static versus API remains a deployment experiment, not a relevance-architecture decision.

## 4. Provenance classes

Every signal that affects retrieval must keep provenance:

```text
canonical
curated_relation
derived_af
behavioral
corpus_derived
synthetic
```

For ad-derived material we additionally preserve field origin inside `corpus_derived`:

```text
raw employer text
employer/recruiter structured taxonomy input
system-derived taxonomy context
model-derived enrichment
```

This is an authority boundary, not a simple ranking order. A generated phrase, calculated similarity, search frequency or model-extracted ad term can be useful retrieval evidence without becoming a canonical synonym, requirement or definition.

Canonical registry: `research/coverage/source-adapters.json`.

## 5. Current measured state — taxonomy v31

### 5.1 Canonical/native text

| Type | Concepts | real definition distinct from label | label-copy definition | with alternative labels |
|---|---:|---:|---:|---:|
| `occupation-name` | 2,105 | **1,636 (77.7%)** | 469 | 197 |
| `skill` | 6,752 | **1,654 (24.5%)** | 5,098 | 819 |
| `job-title` | 9,785 | **6 (0.1%)** | 9,779 | 0 |
| `keyword` | 1,484 | 0 | 1,484 | 1 |

Implication: occupation-name already has useful curated text, while skill and especially job-title need more context/evidence.

Evidence: `docs/findings/native-text-coverage-v31.md`.

### 5.2 Immutable common graph

Accepted snapshot SHA-256:

`634fd9d848a172747e54e3e487160a912ae6c0fcb8219c50998767c8c9aacbcc`

Important measured coverage:

- occupation-name → job-title: 1,583 / 2,105 occupations, 11,198 edges;
- occupation-name → keyword: 130 / 2,105;
- occupation-name → SSYK4 and ISCO4 broader relations: 100%;
- skill → skill-headline broader relation: 100%;
- skill → SSYK4: 6,734 / 6,752, 17,884 edges;
- all 9,785 job-title concepts have at least one occupation-name relation;
- ESCO mappings are substantial and must remain split by exact/broad/narrow/close semantics.

Evidence: `docs/findings/common-relations-coverage-v31.md`.

### 5.3 Published Yrkesväljaren v31

Source SHA-256:

`1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49`

- 2,105 / 2,105 occupation-name IDs: **100%**;
- 9,580 / 9,785 active job-title IDs: **97.905%**;
- 12,330 row occurrences total;
- **541 job-title IDs occur in multiple occupation-name contexts**, max 3 in the published YV read model;
- no unknown IDs, wrong types or invalid occupation parent references were observed.

YV weights are behavioural/search-frequency priors, not concept meaning.

Evidence: `docs/findings/selector-coverage-v31.md`.

### 5.4 YV's 205 omitted active titles are fully explained

The earlier residual gap is closed against the public generator itself.

Accepted generator source commit:

`6dd9e4737d7db3cb2709f8082808b88e5c89ed6e`

Its committed v31 output is byte-identical to published YV.

The 205 omitted active job-title IDs are exactly partitioned by generator policy:

- **104**: title has more than three mapped occupation-name contexts;
- **101**: title label is contained in every mapped occupation-name label and is treated as redundant;
- union = **205 / 205**, no residual.

The sole active title present in YV v30 but absent in v31 is `Präst` (`c57D_hnj_zGv`). Its v30 YV parent was `Stiftsadjunkt`; in v31 its mapped occupation is `Präst, Svenska kyrkan`, so the title now triggers the redundancy rule.

Product conclusion:

> **Retrieval vocabulary is allowed to be larger than YV destination space.**

An excluded title may be a high-value route/disambiguation term, but it cannot silently become a selectable YV title.

Evidence: `docs/findings/yv-generator-exclusion-policy-v31.md` and `research/coverage/v31/yv-generator-policy-aggregate.json`.

### 5.5 Observed YV query language — generator-bound cumulative snapshot

The generator-bound cumulative Platsbanken query snapshot contains:

- **115,553 distinct terms**;
- **3,136,136,606 aggregate searches**;
- date range **2022-05-04 through 2026-08-16**.

It contains query strings + frequency, **not query → selected canonical ID ground truth**.

Exact textual partition:

| class | distinct terms | query volume | volume share |
|---|---:|---:|---:|
| admitted YV labels | 4,181 | 673,338,841 | 21.470% |
| excluded >3-context titles | 58 | 84,249,412 | 2.686% |
| excluded redundant titles | 83 | 265,510,870 | 8.466% |
| unbound language | 111,231 | 2,113,037,483 | 67.377% |

Thus **141 observed excluded-title labels account for 349,760,282 searches = 11.153% of all volume**.

This is not an edge case. High-volume examples include `undersköterska`, `butikssäljare`, `sjuksköterska`, `kock`, `projektledare` and `säljare`.

Design implication:

```text
observed query
  ├─ admitted YV identity -> lexical/product-valid result
  ├─ excluded title -> route/disambiguate to allowed YV destination
  └─ unbound language -> semantic retrieval -> allowed YV destination
```

The 67.377% unbound volume is excellent language/evaluation material but cannot be auto-labelled without additional evidence.

Evidence: `docs/findings/yv-observed-query-language-v31.md` and `research/coverage/v31/yv-query-language-aggregate.json`.

### 5.5.1 Raw public JobSearch Trends

The complete Yrkesväljaren source and its upstream `job-ads/search-trends` generator are now audited end-to-end.

The committed `data/sokningar-platsbanken.json.zip` is **not the raw public search source**. `update_search_terms.py` reads only `q_approved` from public daily JobSearch Trends files, retains terms with at least 10 searches on a day, sums over time, performs small whitespace/hyphen normalization and then removes cumulative terms below 100.

The public source is materially richer:

- **1,256 dated ZIP files** were present in the current listing, from **2022-05-04 through 2026-09-04**;
- that interval contains 1,585 calendar days, so **329 dates currently have no published ZIP**; absence is `UNKNOWN`, not zero;
- the first sampled daily file contains **15,425** distinct `q_approved` values;
- the 2026-09-04 sample contains **100,342** distinct `q_approved` values;
- public files also contain independent daily counters for several structured JobSearch parameters such as occupation group/field/name and geography.

Upstream source semantics are decisive: JobSearch Trends summarizes `/search` request logs by parameter and explicitly does **not** publish complete parameter combinations. `q_approved` is free text that passed a whitelist/stemming privacy filter intended to remove PII. It does **not** mean semantically approved, taxonomy-mapped or selected by a user.

Therefore:

```text
raw daily JobSearch Trends
  = behavioral language + time/frequency + independent parameter marginals
  != query -> selected canonical identity ground truth
```

The current public field whitelist does not expose structured `skill` counts. Same-day free text and taxonomy-ID counters may never be paired as if they came from the same request.

Raw JobSearch Trends is now a first-class Gate-2 source for recency, trend, long-tail and benchmark sampling. The cumulative generator snapshot remains the reproducible evidence source for current YV weighting/admission analysis.

Evidence: `docs/findings/yrkesvaljaren-jobsearch-trends-source-audit-2026-09-06.md` and `research/coverage/jobsearch-trends-source-probe-2026-09-06.json`.

### 5.6 Published Kompetensväljaren v31

Source SHA-256:

`da83f26bf316971caa407364d8feae6f791203bff5758e674cace3d919e4b524`

Context coverage:

- 2,105 / 2,105 occupation-name contexts;
- 400 / 400 SSYK4 contexts.

Ordinary occupation-context skill layers:

| Layer | edges | unique active skills | active skill coverage | occupation contexts non-empty |
|---|---:|---:|---:|---:|
| regulated | 137 | 33 | 0.489% | 109 |
| essential | 151 | 55 | 0.815% | 132 |
| optional | 2,727 | 1,463 | 21.668% | 796 |
| calculated | 31,637 | 4,104 | 60.782% | 2,097 |

Union: **4,647 / 6,752 active skills = 68.824%**.

All referenced IDs resolve to active skills. Layer semantics/provenance must remain separate.

`transferable_skills` is measured separately:

- 27 labels → 27 active skill IDs;
- 14 already occur in ordinary KV layers;
- 13 are additional to the ordinary union;
- unresolved ID-like values: 0.

Its intended ranking/UI semantics remain a methodology question. It is not merged into another layer merely because IDs overlap.

Evidence: `docs/findings/selector-coverage-v31.md` and `docs/findings/selector-residual-gaps-v31.md`.

### 5.7 Native occupation→skill semantics vs KV

The specialised native taxonomy relations are now independently measured against KV.

Native taxonomy:

- `optional`: **2,727 directed pairs**;
- `essential`: **288 directed pairs**.

Exact pair equality proves:

```text
Taxonomy native optional
= KV optional_skills                         2,727 / 2,727

Taxonomy native essential
= KV essential_skills                       151
  ∪ KV regulated_skills                     137
                                             ---
                                             288 / 288
```

The 137 regulated pairs are exactly the native essential pairs whose skill belongs to canonical skill collection `Reglerande behörigheter` (`4P8B_LtK_JgE`, 33 active skills).

Implication: native and KV projections are **not independent evidence** and must not be double-counted. `calculated_skills` and `transferable_skills` remain separate KV provenance.

Evidence: `docs/findings/native-occupation-skill-relations-v31.md` and `research/coverage/v31/native-occupation-skill-aggregate.json`.

### 5.8 Relevanta kompetenser v31

Measured:

- occupation coverage: **2,105 / 2,105 = 100%**;
- 41,096 occupation→skill edge occurrences;
- **4,685 unique active skill IDs = 69.387%**;
- 724 occupations return the apparent cap of 30 skills;
- 4,281 skills overlap ordinary KV layers;
- **404 skills are added beyond ordinary KV**;
- Relevanta + ordinary KV union: **5,051 / 6,752 = 74.807%**.

`relevance_points` is a source-specific derived score. It is not numerically interchangeable with KV fields and does not mean required/essential skill.

Evidence: `docs/findings/derived-af-semantic-coverage-v31.md`.

### 5.9 Employer-language keywords and nearby occupations

The v31 Närliggande-yrken publication contains both similarity and corpus-derived keyword material.

Employer-language keyword dataset:

- occupation records: **1,051 = 49.929%** of active occupations;
- SSYK4 records: **384 = 96.0%**;
- **11,085 distinct keyword strings**;
- source metadata: 7,367,297 ads, 6,937,543 enriched ads;
- **198 / 469 occupation-name concepts with label-copy definitions gain ad-derived keyword material = 42.217%**.

Nearby occupation dataset:

- source occupation records: **1,050 = 49.881%**;
- 10,218 similarity edges;
- 934 unique target occupation IDs.

These are high-value discovery/observed-language signals. They are not synonymy or career-suitability authority.

Evidence: `docs/findings/derived-af-semantic-coverage-v31.md`.

### 5.10 Dedicated keyword/search-concept view

The versioned `keyword-concepts-with-relations` dataset contains all 1,484 active keyword concepts, but is **not a broad YV/KV synonym bank**:

- 34 keywords point directly to occupation-name;
- 151 such edges reach 130 unique occupations = 6.176% occupation coverage;
- 5 keywords point to skills;
- 8 such edges reach 7 unique skills = 0.104% skill coverage;
- 1,443 relation edges instead target `sun-education-field-4`.

Keep it as typed supporting evidence; reduce its priority for direct YV/KV semantic retrieval.

Evidence: `docs/findings/taxonomy-special-relations-v31.md`.

### 5.11 Curated occupation substitutability

The versioned substitutability distribution covers all 2,105 occupation-name concepts.

Measured directional edges:

- `substituted_by`: 4,394 edges, 993 non-empty sources;
- `substitutes`: 4,394 edges, 968 non-empty sources;
- per direction: 1,977 edges at 25 and 2,417 at 75.

Direction and 25/75 semantics must be preserved. Neither value means canonical equivalence.

Evidence: `docs/findings/taxonomy-special-relations-v31.md`.

### 5.12 Yrkesinformation interimslösning

The previous distribution anomaly is resolved.

The portal exposes the download through a custom web-component `af-href`, which is why an ordinary anchor/JSON-LD probe incorrectly found no distribution.

Actual distribution:

`https://data.arbetsformedlingen.se/yrke/yrkesinformation/yrkesinformation-interimslosning.json`

Measured source facts:

- HTTP 200, application/json;
- 9,942,357 bytes;
- SHA-256 `3d52bfec15041898786460374736eba31c5d79ef205182265288b60cf2819c51`;
- title `Yrkesinformation interimslösning`;
- version `1.0`;
- created `2026-04-15`;
- source date `2026-02-24`;
- expiry metadata `2026-12-31`;
- metadata describes legacy Hitta yrken occupations using numeric IDs, names and slugs.

Canonical joinability is now measured across all 324 records:

- **85** records contain exactly one explicit active v31 `occupation-name` ID and may attach their semantic text to that identity;
- **34** contain multiple explicit active occupation IDs and remain ambiguous;
- **205** contain no explicit active occupation ID and remain blocked from canonical attachment.

Exact preferred/alternative-label equality is retrieval candidate evidence only. It does not resolve the 239 ambiguous/unkeyed records. We therefore use the safe 85-record subset and fail closed for the rest rather than manufacture a legacy-ID/slug mapping.

Evidence: `docs/findings/occupational-information-join-v31.md` and `research/coverage/v31/occupational-information-aggregate.json`.

Extractor: `scripts/occupational_information_coverage.py`.

### 5.13 Job-ad provenance boundary

Current source documentation establishes four distinct ad signals:

```text
raw ad text
employer/recruiter structured occupation/requirements
system-derived taxonomy context
model-derived JobAd Enrichments
```

The Historical Ads API states that ads from 2016 onward are enriched with competencies. Downloadable enriched files are currently published through 2026-Q2. JobAd Enrichments explicitly extracts labour-market information automatically from ad text.

Therefore an enriched skill annotation is not automatically human ground truth.

Gate-1 decision:

> Do not build a seven-million-ad normalization/ETL platform before the relevance benchmark.

The already measured occupation-bound `relevans-nyckelord` publication represents broad observed employer-language coverage for Gate 1. Raw/enriched ad-level data moves to **bounded Gate-2 sampling**, where each example records taxonomy version and field provenance.

Evidence: `docs/findings/job-ad-source-boundaries-2026-09-04.md`.

### 5.14 Deprecated → active compatibility v31

The replacement graph is now measured for **3,031** deprecated concepts in YV/KV-relevant types:

- **1,845** resolve to exactly one active same-type target;
- **277** resolve to multiple active targets and must disambiguate/fail closed;
- **909** have no active target;
- direct target type mismatches: **0**;
- unknown direct replacement targets: **0**.

For unique routes, YV still rejects 8 active job-title targets under its measured product policy. `replaced_by` therefore remains a separate migration/history signal, not synonymy and not a bypass around product admission.

Evidence: `docs/findings/deprecated-compatibility-coverage-v31.md` and `research/coverage/v31/deprecated-compatibility-aggregate.json`.

### 5.15 Unified per-target coverage v31

The complete hash-verified target matrix is now measured against current accepted v31 sources:

- YV occupation-name identities: **2,105**;
- selectable YV job-title-in-occupation-context rows: **10,225** from 9,580 unique job-title IDs;
- YV excluded active retrieval-only titles: **205**;
- KV active skills: **6,752**.

Important overlapping weak strata include **244** YV occupations that are canonical-text-poor and lack observed ad language, **1,410** critical-sparse KV skills, **1,701** skills without YV/KV relevance context, and the identity-risk populations of 1,186 multi-parent YV context rows plus 205 excluded-title routes.

This replaces the earlier partial offline matrix as the Gate-1 coverage result. The offline reconstruction remains useful provenance for the post-transfer outage, but `UNKNOWN` derived layers are no longer the current state.

Evidence: `docs/findings/unified-target-coverage-v31.md` and `research/coverage/v31/unified-target-coverage-aggregate.json`.

### 5.16 Pareto demand priority

Historical API server-side taxonomy occurrence statistics provide a cheap concept-level popularity proxy for both occupations and skills. After intersecting with active v31 identities:

| cumulative share of observed active-v31 occurrence mass | occupation-name | skill |
|---:|---:|---:|
| 50% | 33 | 63 |
| 80% | **159** | **316** |
| 90% | 302 | 614 |
| 95% | 455 | 976 |
| 99% | 834 | 1,848 |

The first semantic priority envelope is therefore **P80 = 159 occupations + 316 skills = 475 canonical targets**. YV/KV are the measured reference profiles used to validate this envelope, not the definition of the core target spaces. P90/P95 are explicit expansion tiers. The exact ranked P95 memberships are frozen in repo, so P80/P90 are reproducible prefixes rather than hand-maintained lists.

This is a `corpus_derived` popularity proxy, not user intent or destination ground truth. Existing lexical search continues to cover the full product-valid taxonomy.

**v0 semantic-lane simplification:** YV semantic description search is required initially to emit only the P80 `occupation-name` set. Published job titles remain fully available in the existing lexical picker and may be semantic routing/context vocabulary, but direct semantic `job-title` destinations are deferred until benchmark/telemetry shows material value. KV semantic description search starts with the P80 skill set.

Evidence: `docs/findings/pareto-demand-priority-v31.md` and `research/coverage/v31/pareto-demand-aggregate.json`.

## 6. Semantic boundaries

### 6.1 YV retrieval vocabulary vs destination identity

This is now a first-class distinction.

A `job-title` may be:

1. a published/selectable YV identity in one or more occupation contexts; or
2. an active taxonomy title intentionally excluded by YV generator policy but still valuable as retrieval language.

An excluded title may route to one/many product-valid YV destinations. It is not itself admitted merely because the query matches it exactly.

### 6.2 YV occupation-name vs job-title

`job-title` is a separate identity, not an alternative label. A title can belong to multiple occupations. Exact duplicate/ambiguous identities remain separately scoped until context/user choice disambiguates them.

### 6.3 KV skill vs context

KV returns skills. Occupation-name and SSYK may retrieve/rank skills but can never masquerade as the result identity.

### 6.4 Relation type matters

Never flatten:

- exact/broad/narrow/close ESCO mappings;
- native essential/optional vs KV calculated/transferable signals;
- regulated partition semantics;
- job-title→occupation relations;
- keyword relations;
- substitutability 25/75 and direction;
- statistical similarity;
- ad-derived language/co-occurrence;
- observed query frequency;
- model-derived ad enrichment.

### 6.5 UNKNOWN is not zero

Failed adapters, missing sources and unresolved schemas are `UNKNOWN`. No source may silently produce zero semantic coverage because extraction failed.

## 7. Data priority after current measurements

Current evidence order for experiments:

```text
canonical taxonomy text/identity
→ typed curated taxonomy relations
→ YV/KV product read models and admission semantics
→ Relevanta kompetenser
→ real employer/ad language + measured AF similarity
→ raw + cumulative real query/search language with date/source provenance and explicit non-join semantics
→ embeddings/reranking over trusted representations
→ synthetic LLM text only for measured residual gaps
```

The ad-language, YV query-language and Relevanta measurements materially reduce the justification for early synthetic phrase generation.

## 8. Synthetic data policy

Do **not** generate N phrases per concept as the baseline.

Synthetic phrases are allowed only after ablation shows a concrete residual gap that real/curated/observed sources do not solve. If used they must be generated, provenance-tagged, validated, deduplicated, adversarially tested and versioned. They never become canonical synonyms merely because retrieval metrics improve.

## 9. Research Gate 1 — Semantic Coverage Inventory

Goal: know which semantic material exists for every canonical YV/KV target and relevant context concept in v31, and establish enough source boundaries to build a fair benchmark.

### Completed / measured / explicitly bounded

- [x] active canonical text for occupation-name, skill, job-title, keyword
- [x] immutable common typed relation graph
- [x] SSYK/ISCO hierarchy coverage
- [x] ESCO mapping coverage split by mapping type
- [x] YV per-concept weights and active coverage
- [x] YV job-title parent multiplicity / ambiguity
- [x] exact generator policy for all 205 active titles omitted from YV
- [x] v30→v31 YV dropout identified (`Präst`)
- [x] generator-bound observed YV query-language inventory and exact join semantics
- [x] KV occupation-name and SSYK4 context coverage
- [x] KV regulated/essential/optional/calculated layer coverage
- [x] KV `transferable_skills` inventory
- [x] native occupation→skill essential/optional semantics and exact relationship to KV
- [x] Relevanta kompetenser v31 schema and per-ID coverage
- [x] dedicated keyword/search-concept v31 distribution
- [x] curated occupation substitutability distribution and 25/75 semantics
- [x] Närliggande yrken current v31 distribution and basic coverage
- [x] published employer-language keyword coverage from Närliggande yrken
- [x] Yrkesinformation distribution identity resolved
- [x] job-ad / JobAd-Enrichments provenance boundary established
- [x] full raw-ad ETL explicitly scoped out of Gate 1; bounded sampling moves to Gate 2
- [x] source adapter registry and immutable hashes for accepted sources

### Gate 1 closure — 2026-09-06

- [x] Yrkesinformation legacy→v31 joinability measured: 85 records have one explicit active occupation identity; 34 are ambiguous and 205 unkeyed records fail closed
- [x] deprecated→active compatibility policy and full measurement completed
- [x] unified hash-verified per-target coverage matrix completed and lowest-coverage strata identified

Raw public JobSearch Trends lineage is now audited end-to-end. It does not reopen Gate 1 because it does not change the canonical target universe or provide query→selection ground truth, but it is a first-class Gate-2 behavioral source and must be sampled with date/source provenance.

**Gate 1 is closed.** Every originally required item is measured, explicitly bounded or deliberately blocked with an authority-preserving rationale. Work now moves to Gate 2; new source discoveries do not reopen Gate 1 unless they invalidate an accepted source boundary or target universe.

## 10. Research Gate 2 — judged relevance benchmark

Build structurally compatible **occupation** and **skill** suites. YV/KV-labelled cases remain reference-profile fixtures where product admission semantics matter; they do not define the core engine API.

The current benchmark schema keeps `product: YV | KV` for frozen-fixture compatibility. Treat that field as an **admission/reference-profile label**, not as the semantic engine's `target_space`. A future schema revision should change it only when doing so buys concrete value; do not migrate the 950 frozen cases merely for naming purity.

Start with a **compact 500–1,000 case decision benchmark**, intentionally biased toward source-truth, common/high-value and easy-to-adjudicate cases. Expand toward 1,000–3,000 only when measured residuals, uncertainty or safety slices justify it. Do not spend early benchmark budget trying to make every rare target equally represented.

The initial benchmark should be sufficient to choose between simple baselines. It is not a census of the taxonomy.

The frozen source-truth core currently contains **950 cases**: 333 YV and 617 KV over all 475 P80 targets. It includes 475 preferred-label cases, 330 real canonical-definition cases and 145 alternative-label cases. This is deliberately a source-attested benchmark; it must be complemented by a small manually judged real-query slice before making claims about natural paraphrase performance.

Evidence: `docs/findings/p80-decision-benchmark-v31.md` and `research/benchmark/v31/p80-source-truth/manifest.json`.

Shared strata:

- exact preferred label;
- alternative wording/synonym;
- spelling error;
- Swedish compounds;
- abbreviation;
- English/international wording;
- colloquial language;
- task descriptions;
- tools/method descriptions;
- long descriptions;
- rare/long-tail concepts (small sentinel slice initially; expand only if value/risk warrants);
- hard negatives/confusable siblings;
- broad/underspecified intent;
- deliberate no-valid-match / abstention.

Initial YV benchmark priority:

- the **159 P80 occupation-name identities** are the core semantic destination population;
- exact/prefix lexical behavior remains a full-universe regression baseline, not something semantic v0 must reimplement;
- high-volume admitted/excluded job-title wording is sampled as router language into product-valid occupations;
- a **small** multi-parent-title safety slice is retained; the full 541-title population is not an initial benchmark requirement;
- a **small** excluded-title routing safety slice is retained; the full 205-title population is reproducible but not all must be manually judged now;
- a small high-volume unbound observed-query sample receives human judgments;
- task/skill description→occupation and hard-negative/no-match cases focus primarily on P80;
- P90/P95/tail contribute only small boundary/sentinel samples initially.

Initial KV benchmark priority:

- the **316 P80 active skill identities** are the core semantic destination population;
- exact/alternative labels plus description-style cases focus on that core;
- occupation→skill bridge, transferable/calculated/Relevanta and subtype cases are sampled where they materially exercise the P80 core;
- nearby/confusable skills and no-match/abstention remain explicit safety cases;
- P90/P95/tail contribute only small boundary/sentinel samples initially.

Bounded ad-derived benchmark samples must record field provenance and taxonomy version. Model-derived JobAd Enrichments output cannot serve as ground truth for evaluating the same semantic mapping.

Judged cases must allow genuine ambiguity:

```text
query
MUST
ACCEPTABLE
MUST_NOT
expected_intent: SINGLE | AMBIGUOUS | NO_MATCH
```

## 11. Research Gate 3 — controlled ablation

Evaluate occupation and skill retrieval separately; do not force source symmetry. Keep YV/KV reference-profile slices separate where their admission/routing semantics materially differ.

```text
A  canonical labels only
B  A + real canonical definitions
C  B + alternative labels + product title/retrieval vocabulary
D  C + typed taxonomy graph + ESCO context
E  D + YV/KV selector evidence
F  E + Relevanta kompetenser + curated substitutability + other AF-derived data
G  F + measured real ad/query language
H  G + vector retrieval / neural reranking over trusted representations
I  H + synthetic LLM enrichment only for measured residual gaps
```

Embeddings are intentionally tested **before** synthetic text. Every layer reports incremental gain and regressions per stratum.

## 12. Evaluation metrics

Primary product objective is **discovery**, not exact top-1 classification. A small visible candidate list succeeds when it contains what the user meant; broad/ambiguous queries may correctly expose several plausible canonical candidates. Use **Discovery Success@5** as the primary positive-intent metric and correct abstention as the primary NO_MATCH metric. Top-1 remains secondary ranking diagnostics.

At minimum:

- **Discovery Success@5**, including volume-weighted and per-stratum views;
- abstention precision/recall for `NO_MATCH`;
- hard-negative violation rate;
- Recall@K;
- MRR / nDCG@K;
- top-1 precision where one answer is justified, as a secondary ordering metric;
- exact-label preservation;
- YV ambiguous-title recall/context preservation;
- YV excluded-title routing correctness;
- KV exact skill-identity precision;
- hard-negative violation rate;
- false-confident mapping rate;
- abstention precision/recall;
- no-result rate;
- long-tail recall;
- per-stratum metrics;
- incremental gain by evidence layer;
- explanation/provenance coverage;
- latency/cold-start;
- payload/model/index size;
- browser/server memory where relevant;
- diversity for broad queries.

## 13. Retrieval lanes to test

Do not make one opaque `semantic_score`.

Candidate lanes:

0. exact product-valid labels
1. prefix/token/fuzzy
2. retrieval-only vocabulary/router terms, including excluded YV titles
3. curated semantic text
4. typed graph/context expansion
5. AF-derived evidence
6. corpus-derived observed language
7. vector similarity
8. optional cross-encoder reranker

Heterogeneous rankings require constrained deterministic fusion/rank fusion. Exact lexical evidence gets explicit dominance guarantees where appropriate, but an exact retrieval-only term does not bypass product admission policy.

## 14. Embeddings hypothesis

Embeddings remain plausible for description-style queries, but are an experiment rather than the architecture.

Test:

- small multilingual encoders first;
- one-vector vs multi-view representations;
- label, definition/tasks, graph context, occupation context and observed-language views;
- hard-negative mining from taxonomy neighbours/substitutability/confusables;
- precomputed vectors per taxonomy release;
- optional top-K cross-encoder only if measured value justifies latency/cost.

Do not fabricate descriptions merely to make sparse concepts look symmetrical.

## 15. Cross-entity bridge

YV example:

```text
"svetsa rostfria rör"
  -> TIG/rörsvetsning skill evidence
  -> typed occupation contexts
  -> product-valid YV occupation candidates
```

KV example:

```text
"undersköterska"
  -> occupation/retrieval context
  -> KV/Relevanta skill evidence
  -> exact KV skill candidates
```

The bridge is evidence generation, not identity conversion.

## 16. Hard invariants

- semantic retrieval never invents taxonomy IDs;
- occupation and skill core target spaces never collapse;
- consumer admission profiles never silently expand because retrieval found extra vocabulary;
- YV retrieval vocabulary cannot silently expand selectable YV identities;
- job-title identity retains occupation context;
- exact ambiguous YV identities remain available until disambiguated;
- active taxonomy job-title outside published YV is not automatically a valid YV output;
- occupation/SSYK context cannot masquerade as a KV skill;
- native/KV duplicate projections are not double-counted as independent evidence;
- provenance survives candidate generation/fusion;
- observed query frequency is not query→selection ground truth;
- JobSearch Trends `q_approved` means privacy-filtered public free text, not semantic approval or a selected target;
- public JobSearch Trends fields are independent daily aggregate marginals and must never be interpreted as same-request co-occurrence;
- model-derived ad enrichment is not human ground truth;
- generated text never becomes canonical authority;
- failed/unmeasured source = UNKNOWN, not zero;
- wrong taxonomy version fails closed;
- same taxonomy version + matcher version + query is reproducible;
- semantic-service failure must not corrupt lexical baseline;
- duplicate enrichment is idempotent;
- explanations may cite only retrieval-trace evidence;
- low confidence may and should abstain.

These become property/metamorphic tests when implementation starts.

## 17. Deployment research — local-first vs API

The static/local baseline has strong availability, privacy and version determinism. A central semantic API can ship ranking/index/model/calibration improvements immediately.

Current deployment hypothesis:

```text
existing local lexical picker
        ↓
strong lexical result? -> return locally
        ↓ no / explicit description search
optional semantic service or local semantic module
        ↓
versioned canonical candidates + provenance
        ↓
client validates product-valid taxonomy identities
```

Possible shared core request contract:

```json
{
  "taxonomy_version": 31,
  "target_space": "occupation | skill",
  "query": "...",
  "limit": 10,
  "admission_profile": "optional consumer-defined profile/version"
}
```

The engine must not require a named AF product to retrieve canonical candidates. A profile may constrain the candidate set before/after ranking when a consuming service needs stricter admission semantics. Response must preserve taxonomy version, matcher version, target space, canonical candidate identity, profile/admission provenance when used, and retrieval provenance. API outage should degrade semantic enhancement, not make the selectors unusable.

No deployment choice is final before relevance, latency, privacy, availability, payload and iteration speed are measured.

### Research execution status

After the repository transfer, GitHub-hosted jobs were failing before their first step. Active research workflows now use the available self-hosted `Linux/X64` runner (`garderob` operationally). Benchmark contract, deprecated compatibility, resolved Gate-1 coverage and unified target coverage have all completed successfully on this path; this is execution infrastructure, not a product deployment decision.

## 18. Work sequence

### Gate 1 — closed 2026-09-06

- [x] native text + common graph
- [x] YV/KV selector inventories
- [x] YV ambiguity + exact generator admission/exclusion policy
- [x] YV observed query-language measurement
- [x] KV transferable skills
- [x] native occupation→skill / KV exact relationship
- [x] Relevanta kompetenser
- [x] dedicated keyword/search concepts
- [x] curated substitutability
- [x] Närliggande yrken + employer-language keyword coverage
- [x] Yrkesinformation distribution + fail-closed legacy→v31 join decision
- [x] deprecated→active compatibility policy + measurement
- [x] unified coverage matrix + lowest-coverage strata
- [x] ad / enrichment provenance boundary; raw full-corpus ETL scoped to Gate 2

### Now — Gate 2

- [x] benchmark schema and semantic validator contract
- [x] define the compact Pareto decision slice: **P80 = 159 occupation-name + 316 skill targets**, using Historical API occurrence counts as an explicit corpus/popularity proxy; exact P95 membership frozen in repo
- [x] freeze the **950-case P80 source-truth core benchmark**: 333 YV + 617 KV cases over all 475 P80 targets; preferred labels + 330 real canonical-definition cases + 145 alternative-label cases; validator-clean and frozen in repo
- [x] automatic source-truth strata construction for preferred labels, real canonical definitions and alternative labels; no corpus/model/synthetic signal is auto-promoted to destination truth
- [x] compact high-volume **YV reference-profile multi-parent ambiguity** slice: 20 source-truth exact-title cases selected by observed frequency from the 541-ID population; all admitted context identities are required
- [x] compact high-volume **excluded-YV routing review** slice: 20 highest-volume excluded title queries selected from the 205-ID population; generator reason is verified, destination judgment remains `PENDING_HUMAN_REVIEW`
- [x] compact **model-adjudicated hard-negative + no-match/abstention slice** embedded in the first 34-case Pareto decision benchmark: 18 real high-volume `NO_MATCH` cases, primarily geography; no synthetic negatives required

Evidence: `docs/findings/compact-yv-profile-safety-v31.md` and `research/benchmark/v31/yv-profile-safety/`.
- [x] prepare deterministic **top-50 high-volume Platsbanken/YV occupation-language review packet** from the pinned real query corpus: 742.0M searches = 23.661% of all volume / 35.117% of unbound volume; remains fully `PENDING_HUMAN_REVIEW`; this is one behavioral evidence slice, not the engine's product scope
- [x] adjudicate the **first Pareto batch** rather than all review rows: 34 highest-volume rows across the 50 real unbound queries + 20 excluded-title routing rows cover **80.738%** of combined review-pool volume; 27 are observed unbound queries and 7 excluded-title routes; judgments are explicitly `MODEL_ADJUDICATED`, not source/human truth
- [x] independently adjudicate the **remaining 36 lower-volume rows (Pareto ranks 35–70)** as an untouched holdout before evaluating C1; 208.6M observed searches, 20 NO_MATCH / 13 AMBIGUOUS / 3 SINGLE
- [ ] **defer** full raw JobSearch Trends date-range/long-tail adapter until the first simple baseline shows that recency/long-tail materially changes decisions
- [ ] **defer** broad source-gap enrichment (ESCO text, AF catalog, Sveriges dataportal discovery, ad-language expansion) until benchmark residuals identify which gaps are worth paying complexity for
- [ ] bounded provenance-safe ad-language sample only if needed by the first measured residuals

### Then — Gate 3

First decision: run the **smallest useful baseline** on the compact Pareto benchmark before adding more data engineering.

Preliminary source-truth result: A/B/C0 is complete on the 950-case P80 core. C0 (`preferred labels + real canonical definitions + canonical alternative labels`) reaches **100% top-1 and Recall@10 for both YV and KV** on this source-attested suite. C0 intentionally does **not** yet include the planned C layer's product-title/retrieval vocabulary. This is an ingestion/retrieval result, not natural-paraphrase proof. The next decision-bearing step is the small manually judged real-query + safety slice before adding D/ESCO or neural retrieval.

Evidence: `docs/findings/p80-lexical-ablation-v31.md` and `research/evaluation/v31/p80-lexical-ablation.json`.

First real-language/Pareto result: the frozen 34-case `MODEL_ADJUDICATED` occupation slice covers **80.738%** of the combined review-pool observed volume. C0 reaches **63.786% volume-weighted decision accuracy** and **68.481% volume-weighted top-10 success**. Seven of 18 `NO_MATCH` rows are false-confident because short geography strings overlap definition text. Three positive rows fall outside P80; all are covered by only six additional occupation identities. P80 can represent **84.737%** of positive-intent volume in this slice.

Decision: test a minimal **C1** (P80 + six measured boundary identities + stronger label-surface evidence + conservative short-query abstention) before D/ESCO, neural retrieval or new source engineering.

Evidence: `docs/findings/pareto-model-decision-v31.md`, `research/benchmark/v31/pareto-model-adjudicated/` and `research/evaluation/v31/pareto-model-c0-eval.json`.

C1 holdout result: on independently adjudicated Pareto ranks 35–70 (**36 untouched cases / 208.6M observed searches**), C1 improves volume-weighted decision accuracy from **59.765% to 83.173%** and top-10 success from **59.765% to 84.788%**. It eliminates all five C0 false-confident `NO_MATCH` holdout failures; all 20 NO_MATCH cases abstain. The 333-case source-truth regression remains 100%. Of C1's 12 remaining holdout top-1 failures, **10 are exact active job-title retrieval/routing terms**, so the next justified complexity is the planned deterministic typed job-title router, not D/ESCO or neural retrieval.

Evidence: `docs/findings/pareto-holdout-c1-v31.md`, `research/benchmark/v31/pareto-model-holdout/` and `research/evaluation/v31/pareto-holdout-c0-c1.json`.

Discovery framing: because the product goal is to help a user **find** the intended identity in a small result list rather than classify every query to rank 1, the primary holdout metric is now Discovery Success@5. On the same untouched holdout, C1 reaches **84.788% volume-weighted Discovery Success@5** versus C0 59.765%; C1 @5 equals @10, so no additional judged-positive cases require positions 6–10 in this slice. Top-1 remains secondary diagnostics.

Evidence: `docs/findings/discovery-objective-v31.md` and `research/evaluation/v31/pareto-holdout-discovery.json`.

- [x] preliminary **A/B/C0** source-truth lexical ablation on P80 core, where C0 = preferred labels + real canonical definitions + canonical alternative labels
- [x] **C1:** P80 + six measured high-volume boundary occupations + short-query lexical surface/component/fuzzy evidence + conservative definition-only abstention; 100% on the 34-row development slice, 100% on the frozen 333-case source-truth regression, and **83.173% volume-weighted decision accuracy on untouched 36-row holdout** vs C0 59.765%
- [ ] **complete planned C retrieval vocabulary next:** add exact active job-title preferred-label → typed occupation-name parent routing. Optimize/evaluate primarily for **Discovery Success@5**, not rank 1; the holdout shows exact job-title routing is the dominant remaining candidate-generation gap. Evaluate on a new next-volume sentinel before D/ESCO.
- [ ] D typed graph/ESCO only if the adjudicated real-query/safety residual justifies it; do not add D merely to complete an ablation ladder
- [ ] E–G evidence layers separately
- [ ] H vectors/reranking in shadow evaluation
- [ ] local compiled vs central API deployment benchmark
- [ ] I synthetic enrichment only if residual gaps justify it

### Prototype after evidence

- [ ] reusable core retrieval prototype with `target_space = occupation | skill` and explicit versioned provenance
- [ ] YV reference integration: `Beskriv yrket` with P80 occupation core plus YV admission/routing policy; lexical picker still supports full YV including job titles
- [ ] KV reference integration: `Beskriv kompetensen` with P80 skill core plus KV admission/context policy; lexical picker still supports full KV
- [ ] `Inget av dessa` + feedback flow
- [ ] privacy-reviewed query→candidate→selection telemetry if permitted
- [ ] canary/rollback/versioned semantic API if API wins deployment evaluation

## 19. Open research questions

Resolved answers remain listed when useful.

1. occupation-name real definition coverage? **77.7%**.
2. skill real definition coverage? **24.5%**.
3. job-title real definition coverage? **~0.1%**.
4. YV occupation-name coverage? **100%**.
5. YV job-title coverage? **97.905%; 205 active titles intentionally filtered by generator policy**.
6. Multi-context YV title identity? **541 IDs, max 3 published YV parents**.
7. Why 205 titles are absent? **104 >3-context + 101 redundant-label; exact 205/205 closure**.
8. v30→v31 dropout? **`Präst`, due changed context causing redundancy rule**.
9. Observed search data direct selected-ID labels? **No. The YV cumulative snapshot is query + frequency; raw daily JobSearch Trends adds time and independent structured-parameter counts, but explicitly omits complete request combinations and therefore still has no query→selected-ID join.**
10. Excluded-title search importance? **349.76M searches = 11.153% of measured query volume**.
11. Unbound observed query volume? **67.377%**.
12. KV ordinary four-layer union? **4,647 skills = 68.824%**.
13. KV transferable skills? **27 active skills; 13 additional beyond ordinary layers; ranking semantics still open**.
14. Native optional vs KV optional? **Exact 2,727-pair equality**.
15. Native essential vs KV essential+regulated? **Exact 288-pair equality = 151 + 137**.
16. Relevanta kompetenser coverage? **2,105 occupations, 4,685 skills; adds 404 beyond ordinary KV**.
17. Relevanta + ordinary KV union? **5,051 skills = 74.807%**.
18. Dedicated search concepts useful as broad synonym source? **No; direct YV/KV coverage is very small**.
19. Employer-language keyword coverage? **1,051 occupations, 11,085 terms; rescues 198/469 text-poor occupations**.
20. Curated substitutability? **4,394 directional edges per field with explicit 25/75 semantics**.
21. Yrkesinformation distribution/join? **Resolved: 85/324 records have one explicit active v31 occupation ID and may attach canonically; 34 are ambiguous and 205 have none, so 239 fail closed.**
22. Raw historical ads required before benchmark? **No; full ETL scoped out. Bounded provenance-safe samples move to Gate 2**.
23. JobAd Enrichments ground truth? **No; explicitly model-derived extraction**.
24. Deprecated concepts? **Separate legacy retrieval/migration layer: 1,845 unique active routes, 277 branching routes and 909 without active target; replacement is not synonymy and product admission still applies.**
25. Lowest combined coverage? **Measured overlapping strata include 244 YV text-poor occupations without observed ad language, 6 YV occupations without skill context, 1,410 critical-sparse KV skills and 1,701 KV skills without YV/KV relevance context.**
26. Which judged query strata actually need embeddings?
27. What abstention calibration is safe enough?
28. Does central API materially outperform compiled local semantics after operational costs?
29. What is the intended product role of KV transferable skills?
30. What does observed `quality-level` mean on non-occupation types, and does it affect retrieval enough to justify a Gate-1 adapter?
31. How much vocabulary and recency signal is lost by the YV `>=10/day` and `>=100 cumulative` filters, and which raw-date windows are most useful for Gate-2 sampling?
32. How much incremental Swedish semantic text do mapped ESCO v1.2.1 concepts add specifically to the 244 weak YV occupations and 1,410 critical-sparse KV skills?
33. How much of the critical-sparse KV population is covered by AF's manually mapped labour-market-training learning outcomes and other explicitly curated domain sources?
34. Concept-level Pareto priority? **Historical ad-taxonomy occurrence proxy gives P80 = 159 active occupations + 316 active skills; P90 = 302 + 614; P95 = 455 + 976. This is popularity, not query→selection truth.**
35. What cumulative share of real YV query demand does the P80 occupation envelope cover once high-volume observed wording is manually/safely mapped?
36. What is the smallest evidence/retrieval configuration whose Pareto performance is statistically/materially indistinguishable from more complex alternatives?

## 20. Research discipline

Every important statement is one of:

- **measured** — reproduced by an inventory/evaluation;
- **documented** — stated by an authoritative source;
- **inferred** — deduction from measured/documented facts;
- **hypothesis** — requires experiment.

Do not promote attractive hypotheses to architecture. Do not turn unavailable data into zero. Do not hide source semantics inside a generic score. Do not use model outputs as evaluation truth for the same task. Do not let retrieval vocabulary expand destination identity by accident.

When evidence changes a conclusion, update this file.
