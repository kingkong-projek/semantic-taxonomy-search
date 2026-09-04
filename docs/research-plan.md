# Semantic Taxonomy Search — living research plan

**Status:** active research  
**Target taxonomy snapshot:** v31 unless an experiment explicitly says otherwise  
**Last updated:** 2026-09-04  
**Authority:** this file is the single source of truth for scope, current conclusions, research gates and experiment order. Findings and generated inventories provide evidence; when they change our conclusions, this file must be updated.

## 1. Problem

Yrkesväljaren and Kompetensväljaren need to let a person reach the correct canonical taxonomy concept even when the person does not know the canonical label.

Examples:

- exact title: `förskollärare`
- spelling/compound variation
- colloquial title or abbreviation
- English/international title
- task description: `jag leder projektering av större byggprojekt och samordnar konsulter`
- competence description: `programmera cnc-maskiner och skriva g-kod`
- long work description containing several tasks
- ambiguous labels where the same or similar wording points to different canonical identities

The output must remain exact taxonomy identities. Semantic retrieval is allowed to discover and rank candidates; it is not allowed to invent, merge or mutate canonical concepts.

## 2. Product hypothesis

Do **not** replace the fast existing picker with a chatbot.

Keep the current lexical picker as the privileged fast path. Add a second interaction when ordinary title search is insufficient:

```text
[Vad arbetar du som?                    ]

Förskollärare
Förskolechef
Lärare i förskola
...

────────────────────
Hittar du inte yrket?
Beskriv vad du arbetar med
```

A description returns a small set of canonical candidates:

```text
"Jag leder projektering av större
byggprojekt och samordnar konsulter"

Vi tror att du menar:

○ Projektledare, bygg och anläggning
○ Projekteringsledare
○ Byggprojektledare

[Inget av dessa]
```

`Inget av dessa` is a first-class outcome. Low confidence must not be disguised as certainty.

## 3. Architectural hypothesis

The retrieval problem is larger than "put embeddings on autocomplete".

Candidate architecture:

```text
user text
  ↓
query interpretation
  ├─ lexical retrieval
  ├─ curated semantic retrieval
  ├─ taxonomy graph retrieval
  ├─ empirical/corpus retrieval
  └─ optional vector retrieval
          ↓
      candidate union
          ↓
 deterministic/constrained fusion
          ↓
 optional reranking
          ↓
 exact taxonomy IDs + match evidence
```

The strongest current principle is:

> **Use existing semantics before manufacturing semantics.**

A related deployment principle remains valuable:

> **Compile semantics when possible; serve semantics only where central iteration is worth the operational boundary.**

The runtime form is not decided yet. A central Semantic Mapping API is a serious candidate because ranking/model/index improvements could then reach all consumers without republishing every web component. This must be compared against local/versioned assets for latency, availability, privacy, reproducibility and operational cost.

## 4. Current measured state — taxonomy v31

This section supersedes earlier assumptions based only on documentation or single API examples.

### 4.1 Native text coverage

Measured over the active concepts returned for v31:

| Type | Concepts | Definition distinct from preferred label | Label-copy definition | With alternative labels |
|---|---:|---:|---:|---:|
| `occupation-name` | 2,105 | 1,636 (77.7%) | 469 (22.3%) | 197 (9.4%) |
| `skill` | 6,752 | 1,654 (24.5%) | 5,098 (75.5%) | 819 (12.1%) |
| `job-title` | 9,785 | 6 (0.1%) | 9,779 (99.9%) | 0 |
| `keyword` | 1,484 | 0 | 1,484 (100%) | 1 |

Consequences:

1. **`occupation-name` has a surprisingly rich semantic text layer.** Roughly three quarters have a definition that is genuinely different from the preferred label.
2. **`job-title` is almost entirely vocabulary + graph, not descriptive text.** Even the six distinct rows are an upper bound on rich descriptions; some are spelling/normalisation corrections.
3. **`skill` is text-sparse relative to occupations.** Its retrieval representation must lean more heavily on graph/context/ESCO/derived data.
4. **`keyword` is not a description corpus.** Its value is its wording and typed relations.

Detailed measured finding: [`findings/native-text-coverage-v31.md`](findings/native-text-coverage-v31.md).

### 4.2 Common typed graph coverage

The immutable v31 `concepts-and-common-relations` snapshot has SHA-256:

`634fd9d848a172747e54e3e487160a912ae6c0fcb8219c50998767c8c9aacbcc`

It contains 43,695 unique active concept IDs and exactly the same target populations as the independently paged REST extraction.

High-value measured relations:

#### `occupation-name`

- `related → job-title`: 1,583 / 2,105 (75.2%), 11,198 edges
- `related → keyword`: 130 / 2,105 (6.2%), 151 edges
- `broader → ssyk-level-4`: 2,105 / 2,105 (100%), 2,105 edges
- `broader → isco-level-4`: 2,105 / 2,105 (100%), 2,107 edges
- `exact_match → esco-occupation`: 982 (46.7%)
- `broad_match → esco-occupation`: 595 (28.3%)
- `narrow_match → esco-occupation`: 487 (23.1%)
- `close_match → esco-occupation`: 553 (26.3%)

#### `skill`

- `broader → skill-headline`: 6,752 / 6,752 (100%)
- `related → ssyk-level-4`: 6,734 / 6,752 (99.7%), 17,884 edges
- `exact_match → esco-skill`: 1,251 (18.5%)
- `broad_match → esco-skill`: 4,017 (59.5%)
- `narrow_match → esco-skill`: 2,495 (37.0%)
- `close_match → esco-skill`: 1,283 (19.0%)

#### `job-title`

All 9,785 active job titles have at least one `related → occupation-name` edge; there are 11,198 such edges. This directly proves that a title can be related to more than one occupation and reinforces the identity-preservation requirement.

Detailed measured finding: [`findings/common-relations-coverage-v31.md`](findings/common-relations-coverage-v31.md).

### 4.3 Documentation/data drift is itself evidence

The current occupation-name documentation says most occupation-name concepts lack real definitions and that `definition` is generally the preferred label. The measured active v31 snapshot shows **77.7% distinct definitions**. Therefore documentation is useful for intended semantics/governance, but the immutable versioned dataset is the authority for actual coverage statistics.

Likewise, documentation says `quality-level` is unique to `occupation-name`, while the v31 REST representation exposes it on 611 skills, 148 job titles and 2 keywords as well. Until semantics are verified, `quality-level` outside occupation-name is recorded but **must not be used as a ranking/authority feature**.

### 4.4 Unknown must stay unknown

The first GraphQL relation experiment failed because the generated query passed taxonomy version as a string. Its printed relation zeros were invalid and have been superseded by the immutable common-relations extraction.

The common-relations distribution does **not** expose all specialised relations. In particular, documented `essential` / `optional` occupation→skill relations remain **unknown**, not zero, until a separate adapter measures them.

## 5. Important semantic distinctions

### 5.1 `occupation-name` vs `job-title`

A `job-title` is a separate concept with narrower/different scope; it is **not** merely an alternative label for the related `occupation-name`.

`alternative-labels` are intended for obvious synonyms/abbreviations. Keywords can be broader domains. These distinctions must survive retrieval and explanation.

Consequence: the matcher must never flatten all related strings into a synonym bag.

### 5.2 Ambiguous title identities

If an identical or near-identical title maps to multiple occupations, all exact canonical identities must remain distinct. Semantic context may rerank/disambiguate them, but may not arbitrarily collapse them.

A better invariant than "exact label is always one top-1 result" is:

> all exact canonical matches dominate non-exact semantic matches, while duplicate-title identities remain separately visible until disambiguated.

### 5.3 Skills and ESCO mappings

Taxonomy skill concepts are broader/fewer than ESCO skills. The taxonomy contains curated SKOS mapping relations to ESCO (`exact`, `broad`, `narrow`, `close`). These mappings are potentially strong semantic enrichment but must retain relation type; `broad-match` must never become synonymy.

The v31 measurements reinforce this: ESCO mappings are widespread, especially for skills, but mapping types overlap and must never be summed into a generic synonym score.

Sources:
- https://arbetsformedlingen.gitlab.io/taxonomy-dev/projects/jobtech-taxonomy/about/esco-skill.html
- https://arbetsformedlingen.gitlab.io/taxonomy-dev/projects/jobtech-taxonomy/about/esco-occupation.html

## 6. Evidence/provenance classes

Every semantic signal should have an explicit provenance class. Working vocabulary:

```text
canonical
curated_relation
derived_af
behavioral
corpus_derived
synthetic
```

Candidate generation may use all classes. Claims about taxonomy meaning require much stricter authority.

```text
                         TRUST / AUTHORITY
                                ▲
                                │
           canonical taxonomy + curated relations
                                │
                    derived AF datasets
                                │
              observed behaviour / corpora
                                │
                     synthetic model data
                                │
                                ▼
                           RECALL ONLY
```

Generated paraphrases, if they are ever used, are retrieval aids and never taxonomy facts.

## 7. Known data landscape

The current research has identified at least these useful sources:

| Source | What it says | Candidate use | Authority caveat |
|---|---|---|---|
| Taxonomy concepts | canonical identity, labels, real definitions where present | identity + retrieval | coverage varies strongly by type |
| Alternative labels | explicit synonym/abbreviation cases | lexical/semantic retrieval | stronger than generic related terms |
| Job-title relations | narrower/different job-title concepts | candidate expansion + disambiguation | not synonyms; 100% of job titles link to occupation-name in v31 |
| Keyword relations/search concepts | broader/common search language | recall | may be broader than occupation; common-edge coverage is sparse |
| SSYK hierarchy | occupational context | routing, disambiguation, graph evidence | group membership, not semantic equivalence |
| Curated occupation relations/substitutability | related occupations | candidate expansion/hard negatives | relation semantics must be preserved |
| Essential/optional skill relations | occupation↔skill | cross-entity bridge | not measured yet in v31 common snapshot |
| ESCO mappings | manually curated cross-taxonomy mappings | enrichment, hard negatives, descriptions later | exact/broad/narrow/close are different |
| Yrkesväljaren dataset | popularity weights for occupation-name/job-title | prior/ranking | not meaning |
| Platsbanken search history | real user search language/behaviour | evaluation, query corpus, ranking | not automatically labelled query→ID pairs |
| Historical ads | real employer language/tasks | corpus-derived retrieval | noisy; occupation fields can be missing/wrong |
| JobAd enrichments | extracted structured expressions | candidate enrichment | model-derived, not canonical truth |
| Relevanta kompetenser | occupation→skill suggestions derived through ESCO | candidate expansion | derived; documented noise/granularity limits |
| Kompetensväljaren | weighted skills in occupation context | ranking/context | derived/read-model semantics |
| Närliggande yrken | ad-derived occupational similarity | discovery/diversification | explicitly not proof of suitable career transition |
| Curated släktskap mellan yrkesbenämningar | editorial/curated occupational similarity | hard negatives/context | relation strength must retain source meaning |
| JobSearch Trends/current search signals | recent language/popularity | drift detection | popularity ≠ meaning |
| Yrkesinformation | descriptive occupational information | possible enrichment | source/version coverage must be measured |

Current Yrkesväljaren methodology reports 2,603,440,552 retained Platsbanken searches over the stated source interval after low-frequency filtering. The dataset assigns weights to `occupation-name` and `job-title`, and occupations inherit searches from related job titles. Treat this as very strong behavioural evidence, but not as two billion labelled semantic mappings.

Sources:
- https://gitlab.com/arbetsformedlingen/taxonomy-dev/backend/yrkesvaljaren
- https://gitlab.com/arbetsformedlingen/taxonomy-dev/backend/yrkesvaljaren/-/blob/main/Metodbeskrivning.md

Note: the current methodology page contains a date statement (`2026-12-15`) that is later than this document's update date. Treat that particular date as a source anomaly until verified; the source interval and reported count are still recorded as source claims, not inferred facts.

## 8. Why synthetic phrases are now late, not early

Previous idea: generate 50–200 realistic Swedish queries/paraphrases per concept with a strong LLM and compile them into static search assets.

Current position: **do not do this as the baseline**.

First use and measure:

1. canonical labels
2. real definitions where distinct from labels
3. alternative/hidden labels
4. job-title/keyword/search-term relations
5. taxonomy graph
6. ESCO mappings
7. AF-derived datasets
8. observed user/ad language

Only add synthetic language if a controlled ablation proves incremental recall on concrete misses.

This avoids semantic sludge, fabricated synonymy and a large unreviewable generated corpus.

The v31 inventory makes this ordering stronger, not weaker: occupation-name already has rich text for 77.7% of active concepts, and text-sparse skills are densely connected to SSYK/ESCO context.

## 9. Research Gate 1 — Semantic Coverage Inventory

**Goal:** establish exactly what semantic material exists for every target concept in taxonomy v31.

Primary entity spaces:

- `occupation-name`
- `skill`

Supporting spaces that must also be inventoried because they can carry retrieval language/context:

- `job-title`
- `keyword` / search concepts
- SSYK groups
- ESCO occupation/skill mappings
- deprecated concepts only in a separate compatibility/history layer

For each target concept capture at least:

```text
id
type
preferred_label
deprecated/current scope

text coverage:
  definition_nonempty
  definition_distinct_from_label
  definition_length
  alternative_label_count
  hidden_label_count
  quality_level_observed
  quality_level_semantics_verified

taxonomy graph coverage:
  job_title_count
  keyword/search_concept_count
  ssyk_parent_count
  essential_skill_count | UNKNOWN until adapter exists
  optional_skill_count | UNKNOWN until adapter exists
  curated_related_count
  esco_mapping_count by mapping relation

external/derived coverage:
  yrkesvaljaren_weight_present
  relevant_skills_present
  competence_selector_context_present
  curated_occupation_kinship_present
  historical_ad_count / usable corpus signal
  jobad_enrichment_signal
  occupational_information_present
  observed-search-language signal

research metadata:
  taxonomy_version
  source_snapshot/version/hash
  extraction_timestamp
  join_key
  provenance_class
  warnings
```

Do not compress these into one "coverage score" initially. Missing dimensions mean different things.

### Gate 1 measured so far

- [x] active v31 canonical text fields for occupation-name, skill, job-title and keyword
- [x] immutable v31 common relation graph, typed by target concept type
- [x] SSYK4/ISCO4 common hierarchy coverage
- [x] ESCO occupation/skill common mapping coverage split by exact/broad/narrow/close
- [x] active job-title → occupation-name and occupation-name → job-title coverage
- [ ] specialised native occupation→skill `essential` / `optional` relations
- [ ] separate search-concept distribution and its relation semantics
- [ ] Yrkesväljaren per-concept weight coverage
- [ ] Relevanta kompetenser per-concept coverage
- [ ] Kompetensväljaren per-concept/context coverage
- [ ] curated släktskap mellan yrkesbenämningar
- [ ] Yrkesinformation coverage
- [ ] historical/current advertisement corpus coverage by canonical identity
- [ ] JobAd enrichment signal and provenance
- [ ] JobSearch Trends / observed query-language coverage and usable join semantics
- [ ] deprecated/replaced concept compatibility layer, separate from active retrieval corpus

Canonical machine-readable adapter status lives in [`../research/coverage/source-adapters.json`](../research/coverage/source-adapters.json) once created/updated.

### Gate 1 outputs

- machine-readable per-concept JSONL/CSV
- aggregate JSON
- human-readable Markdown summaries
- lists of lowest-coverage concepts by entity type
- data-source coverage matrix
- explicit extraction errors/source anomalies
- immutable source URL/hash/version wherever possible

### Gate 1 decision

After the inventory we decide which evidence sources are actually worth integrating into retrieval experiments. We do not choose a model before this gate.

Gate 1 is **not complete** yet.

## 10. Research Gate 2 — evaluation set

Create a Swedish relevance benchmark before tuning retrieval.

Initial target: 1,000–3,000 judged queries, stratified rather than randomly averaged.

Required strata:

- exact preferred labels
- alternative labels
- job titles
- spelling errors
- Swedish compounds
- colloquial language
- abbreviations
- English/international titles
- task phrases
- tool/method phrases
- broad intent (`jobba med data`)
- long work descriptions
- rare/long-tail concepts
- ambiguous duplicate/near-duplicate titles
- hard negatives/confusable siblings
- competence descriptions
- heterogeneous skill subtypes (technology/software/certificate/qualification/etc.)
- cross-entity queries
- deliberate no-match/abstention cases

Potential sources for queries, in decreasing authority for "real language": observed product/search data where permitted, historical ads, expert-written cases, and synthetic queries only for gaps.

## 11. Research Gate 3 — A→H ablation

Run the same benchmark through increasingly enriched systems:

```text
A  labels only
B  A + real/distinct curated definitions
C  B + alternative/hidden labels + job-title/keyword/search relations
D  C + taxonomy graph + curated occupation/skill relations + ESCO mappings
E  D + Yrkesväljaren behavioural weights
F  E + historical ad vocabulary/enrichments
G  F + other useful AF-derived datasets
H  G + synthetic LLM-generated semantic data
```

The exact layers may be split further after Gate 1 if sources have materially different semantics. In particular, `job-title`, search concepts, ESCO and curated occupation similarity should be independently ablated rather than hidden inside a single opaque C/D result if they materially affect quality.

Measure incremental gain at every layer. If H adds negligible value or raises false-positive/confusion risk, do not ship H.

## 12. Evaluation metrics

At minimum:

- Recall@K: was the correct canonical identity retrieved?
- MRR / nDCG@K: was it ranked usefully?
- Top-1 precision where a single answer is justified
- exact-label preservation
- ambiguous-label recall: all relevant exact identities remain available
- hard-negative error rate
- false-confident mapping rate
- abstention quality
- no-result rate
- long-tail recall
- per-stratum metrics; never only overall average
- semantic lane incremental gain over lexical baseline
- latency, cold-start, payload and memory
- explanation/provenance coverage
- broad-query result diversity

## 13. Retrieval lanes to test

Do not make one undifferentiated `semantic_score`.

Candidate lanes:

0. exact/alternative label
1. prefix/token/fuzzy
2. curated semantic text (real definitions/search terms)
3. taxonomy graph bridge
4. corpus-derived text retrieval
5. vector semantic retrieval
6. optional cross-encoder reranker

Heterogeneous rankings should be fused with a deterministic method such as constrained rank fusion/RRF, with explicit lexical dominance rules where warranted. Do not sum incomparable raw scores blindly.

## 14. Embeddings hypothesis

Embeddings remain plausible, but are now an experiment rather than the architecture.

If tested:

- precompute concept/document vectors per taxonomy release
- compare one-vector-per-concept against multi-view representations
- possible views: label, definition/tasks, tools/methods, graph context, observed query language
- do not give text-sparse job-title/keyword concepts synthetic descriptions merely to make embedding input symmetrical
- query encoder may run centrally or locally; deployment decision is separate from relevance quality
- use hard-negative mining from taxonomy siblings/near-labels/ESCO mappings
- benchmark a small multilingual encoder before large models
- rerank only top-K if a cross-encoder adds measurable value

## 15. Cross-entity bridge

A strong non-traditional idea is to exploit the graph rather than only embed final labels.

Example occupation search:

```text
"svetsa rostfria rör"
  → skill candidates: TIG-svetsning, rörsvetsning
  → known occupation↔skill relations
  → occupation candidates
```

Example competence search:

```text
"undersköterska"
  → occupation candidate
  → known skill relations / Relevanta kompetenser
  → competence candidates
```

The bridge must preserve relation provenance. `related`, `optional`, `essential`, `broad-match` etc. are not interchangeable.

The measured v31 graph makes this hypothesis more plausible for skills: 99.7% have at least one SSYK4 relation and ESCO mapping coverage is substantial even where native definition text is sparse.

## 16. Semantic diversification

Broad queries should not return ten near-duplicates.

For a query such as `jobba med data`, test result diversification across meaningful interpretations, for example analysis, software development, databases and data science. Diversification may use taxonomy branches or retrieval clusters, but must not fabricate taxonomy categories.

## 17. Anti-search / disambiguation

Hard negatives can power a useful UX after retrieval:

> You selected Redovisning. Did you perhaps mean Bokföring, Revision or Ekonomistyrning?

This is valuable because the product goal is not merely high recall; it is selection of the right canonical identity.

## 18. Hard invariants

Regardless of model:

- semantic retrieval never invents taxonomy IDs
- entity spaces (`occupation-name`, `job-title`, `skill`, etc.) never collapse identities
- exact duplicate-title identities remain distinct
- all exact canonical matches dominate non-exact semantic candidates unless an explicit documented policy says otherwise
- semantic index unavailable/corrupt → lexical baseline still works
- stale/wrong taxonomy-version semantic artifacts fail closed
- same taxonomy version + matcher version + query → reproducible ranking
- generated phrases never become canonical synonyms
- graph relations keep their relation type/provenance
- absence in a source that was not successfully extracted is `UNKNOWN`, never zero
- unresolved/deprecated relation targets are not silently dropped into active semantic equivalence
- unrelated semantic artifact changes should not perturb unrelated exact matches
- duplicate enrichment data should be idempotent
- low-confidence description mapping supports abstention
- explanations may only claim evidence actually present in the retrieval trace

These are candidates for property-based/metamorphic tests as implementation matures.

## 19. Deployment research: local assets vs central API

Do not conflate relevance architecture with deployment architecture.

### Local/versioned assets advantages

- instant/no per-query network dependency
- privacy
- deterministic snapshot
- robust embedding in host products

### Central Semantic Mapping API advantages

- new index/ranking/model/calibration deployed once
- consumers improve without republishing component code
- easier observation/evaluation/rollback
- heavier models possible

### If central API is used

Return at least:

```json
{
  "taxonomy_version": 31,
  "matcher_version": "...",
  "candidates": []
}
```

Support canary, rollback, reproducibility and explicit failure behavior. Local lexical search should remain usable when the semantic service is unavailable unless a future product explicitly chooses otherwise.

## 20. Current component context

Yrkesväljaren's current component searches locally in-browser against loaded taxonomy data. Its lexical behavior prioritizes direct/exact/prefix/token matches and falls back to fuzzy matching. That behavior is the baseline to freeze and benchmark, not something semantic search is allowed to casually replace.

The current component/data distribution already separates runtime code from taxonomic data: latest data can be obtained automatically, while a consumer can pin a versioned data package. Therefore a future API primarily solves **semantic matcher/model iteration**, not simply taxonomy-data freshness.

## 21. Work sequence

### Now — Gate 1

- [x] Establish repository as SSOT.
- [x] Record current hypotheses and evidence hierarchy.
- [x] Measure active v31 native text coverage.
- [x] Measure immutable v31 common typed relations.
- [x] Freeze current valid aggregate findings and source hashes in repo.
- [x] Identify and quarantine the failed GraphQL relation extraction; its zeros are invalid.
- [ ] Build/maintain the source-adapter registry and unified per-concept join schema.
- [ ] Measure specialised native occupation→skill relations.
- [ ] Measure separate search-concept distribution.
- [ ] Add Yrkesväljaren adapter.
- [ ] Add Relevanta kompetenser adapter.
- [ ] Add Kompetensväljaren adapter.
- [ ] Add curated occupational-kinship adapter.
- [ ] Add Yrkesinformation adapter.
- [ ] Add advertisement/enrichment/query-language coverage adapters where the join semantics are reliable.
- [ ] Produce unified v31 coverage matrix and identify the actual lowest-coverage concept strata.

### Next — Gates 2–3

- [ ] Build judged benchmark/evaluation schema.
- [ ] Import/author first high-confidence evaluation cases.
- [ ] Implement A–D baselines without embeddings.
- [ ] Add E–G sources only where coverage/provenance is understood.
- [ ] Run vector retrieval in shadow evaluation.
- [ ] Decide whether embeddings add sufficient incremental recall.
- [ ] Only then test synthetic LLM enrichment (H).

### Later

- [ ] Evaluate central API vs local compiled artifacts using measured latency/operational requirements.
- [ ] Prototype description-search UX and `none of these` flow.
- [ ] Instrument privacy-reviewed query→candidate→selection feedback if permitted.
- [ ] Hard-negative mining/calibration/reranking only after benchmark evidence.

## 22. Open research questions

Resolved or partially resolved questions stay here with their measured answer so history is visible.

1. **What fraction of v31 `occupation-name` definitions are distinct from labels?** 1,636 / 2,105 = **77.7%**. Whether every distinct definition is equally useful is still open.
2. **What about `skill` and `job-title`?** Skill: 1,654 / 6,752 = **24.5%**. Job-title: 6 / 9,785 = **0.1% upper bound** on rich descriptions.
3. **How complete are alternative/hidden labels?** Measured native counts exist; coverage is sparse. Need evaluate retrieval value, not only presence.
4. **How many occupation names have related job titles?** 1,583 / 2,105 = **75.2%**. All 9,785 job titles relate to at least one occupation-name.
5. How many occupation names have specialised `essential`/`optional` skill relations directly in taxonomy? **Open; common distribution does not expose them.**
6. **What is ESCO mapping coverage?** Common v31 mapping coverage is measured separately by exact/broad/narrow/close; overlap means no single summed synonym percentage is valid.
7. How much semantic language is recoverable from ESCO without losing Swedish taxonomy scope?
8. What exact concept coverage exists in Yrkesväljaren, Relevanta kompetenser, Kompetensväljaren and occupational-information datasets?
9. Can historical-ad text be joined to exact occupation identities reliably enough for retrieval training/evaluation?
10. Do observed search logs contain useful query→selection labels, or only query frequency?
11. How much improvement comes from curated graph/text alone before embeddings?
12. Which query strata actually need embeddings?
13. Can a small multilingual model distinguish Swedish hard negatives better than graph-aware lexical retrieval?
14. When should the system abstain instead of returning a candidate?
15. Which data may legally/privacy-wise be retained for future product feedback loops?
16. What exactly does observed `quality-level` mean on non-occupation concept types in v31?
17. Which deprecated concepts should remain searchable solely for compatibility/migration and how should they map forward without polluting active identity?

## 23. Research discipline

Every important conclusion should be labelled mentally as one of:

- **measured** — produced by a reproducible inventory/evaluation
- **documented** — stated by an authoritative source
- **inferred** — reasonable deduction from measured/documented facts
- **hypothesis** — requires experiment

Do not promote hypotheses to architecture merely because they sound plausible.

When new evidence changes a conclusion, update this file and record why. The repo should tell a new researcher both **what we currently believe** and **what evidence would falsify it**.
