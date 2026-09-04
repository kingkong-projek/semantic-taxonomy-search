# Semantic Taxonomy Search — living research plan

**Status:** active research  
**Target taxonomy snapshot:** v31 unless an experiment explicitly says otherwise  
**Last updated:** 2026-09-04  
**Authority:** this file is the single source of truth for product scope, current conclusions, research gates and experiment order. Findings and generated inventories provide evidence; when evidence changes a conclusion, this file must change too.

## 1. Product problem

We are building semantic search for **both Yrkesväljaren (YV) and Kompetensväljaren (KV)**.

A person often knows what they do or can do, but not the exact taxonomy wording. The products therefore need better retrieval without weakening canonical identity.

The destination spaces are intentionally different:

- **YV:** `occupation-name` and `job-title` with exact occupation-name context preserved.
- **KV:** active `skill` identities.

Occupation, SSYK, skill-headline, keyword, ESCO and other concepts may be used as evidence/routing/context. They are not interchangeable with the returned identity.

Hard shared rule:

> Semantic retrieval may discover, expand, rank and explain candidates. It may never invent, merge or mutate canonical taxonomy identities.

## 2. Product UX hypothesis

Do not replace either picker with a chatbot.

Keep the current fast lexical picker as the privileged path. Add semantic description search when normal lookup is insufficient, for example:

```text
YV: Hittar du inte det du söker? [Beskriv yrket]
KV: Hittar du inte kompetensen? [Beskriv kompetensen / vad du kan göra]
```

The result remains exact canonical YV/KV identities. `Inget av dessa` / abstention is a first-class successful outcome. A nearest neighbour is not proof that a valid match exists.

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
 typed canonical candidates + provenance
```

The retrieval infrastructure may be shared, but each request has an explicit target space:

```text
YV -> occupation/job-title-in-occupation-context
KV -> skill
```

Cross-entity bridges generate evidence; they do not convert identity.

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

This is an authority boundary, not a simple ranking order. A generated phrase, calculated similarity or ad-derived term can be useful retrieval evidence without becoming a canonical synonym, requirement or definition.

## 5. Current measured state — taxonomy v31

### 5.1 Canonical/native text

| Type | Concepts | real definition distinct from label | label-copy definition | with alternative labels |
|---|---:|---:|---:|---:|
| `occupation-name` | 2,105 | **1,636 (77.7%)** | 469 | 197 |
| `skill` | 6,752 | **1,654 (24.5%)** | 5,098 | 819 |
| `job-title` | 9,785 | **6 (0.1%)** | 9,779 | 0 |
| `keyword` | 1,484 | 0 | 1,484 | 1 |

Implication: occupation-name already has useful curated text, while skill and especially job-title need much more context/evidence.

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

#### Residual YV title population

The 205 active job-title IDs absent from YV are now characterised:

- 205 / 205 were already active in taxonomy v30;
- 204 / 205 were already absent from YV v30;
- only one title dropped between YV v30 and v31;
- all 205 still have active occupation-name relations in the taxonomy graph;
- many are extremely broad: `Jurist` has 38 occupation parents, `Säljare` 25, `Projektledare` 17;
- 84 of the 205 have only one occupation parent, so ambiguity alone cannot explain the whole exclusion policy.

Conclusion: this is a persistent YV methodology/selection population, not simple taxonomy release lag. Do **not** silently expand YV output to all active taxonomy job-title IDs until generator/methodology semantics are verified.

Evidence: `docs/findings/selector-residual-gaps-v31.md`.

### 5.4 Published Kompetensväljaren v31

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

#### KV transferable skills

`data.transferable_skills` is now measured separately:

- 27 labels → 27 active skill IDs;
- 14 already occur in ordinary KV layers;
- 13 are additional to the ordinary union;
- unresolved ID-like values: 0.

The list appears semantically broad/transferable, but its intended ranking/UI semantics are still a methodology question. It remains a distinct provenance signal.

Evidence: `docs/findings/selector-coverage-v31.md` and `docs/findings/selector-residual-gaps-v31.md`.

### 5.5 Relevanta kompetenser v31

The current file is published as compressed `relevanta-kompetenser-t31.json.zst`.

Measured:

- occupation coverage: **2,105 / 2,105 = 100%**;
- 41,096 occupation→skill edge occurrences;
- **4,685 unique active skill IDs = 69.387%** of active skills;
- 724 occupations return the apparent cap of 30 skills;
- 4,281 of these skills overlap ordinary KV layers;
- **404 skills are added beyond ordinary KV**;
- the same 404 remain additional after including KV transferable skills;
- Relevanta + ordinary KV union: **5,051 / 6,752 = 74.807%**.

`relevance_points` is a source-specific derived score. It is not numerically interchangeable with KV fields and does not mean required/essential skill.

Evidence: `docs/findings/derived-af-semantic-coverage-v31.md`.

### 5.6 Employer-language keywords and nearby occupations

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

### 5.7 Dedicated keyword/search-concept view

The versioned `keyword-concepts-with-relations` dataset contains all 1,484 active keyword concepts, but it is **not a broad YV/KV synonym bank**:

- 34 keywords point directly to occupation-name;
- 151 such edges reach 130 unique occupations = 6.176% occupation coverage;
- 5 keywords point to skills;
- 8 such edges reach 7 unique skills = 0.104% skill coverage;
- 1,443 relation edges instead target `sun-education-field-4`.

Conclusion: keep it as typed supporting evidence, but reduce its priority for YV/KV semantic retrieval.

Evidence: `docs/findings/taxonomy-special-relations-v31.md`.

### 5.8 Curated occupation substitutability

The versioned `substitutability-relations-between-occupations` distribution covers all 2,105 occupation-name concepts.

Measured directional edges:

- `substituted_by`: 4,394 edges, 993 non-empty sources;
- `substitutes`: 4,394 edges, 968 non-empty sources;
- per direction: 1,977 edges at 25 and 2,417 at 75.

Direction and 25/75 semantics must be preserved. Neither value means canonical equivalence.

This is strong YV context/hard-negative material and substantially more useful than treating relation IDs generically.

Evidence: `docs/findings/taxonomy-special-relations-v31.md`.

## 6. Semantic boundaries

### YV occupation-name vs job-title

`job-title` is a separate identity, not an alternative label. A title can belong to multiple occupations. Exact duplicate/ambiguous identities must remain separately scoped until context/user choice disambiguates them.

### KV skill vs context

KV returns skills. Occupation-name and SSYK may retrieve/rank skills but can never masquerade as the result identity.

### Relation type matters

Never flatten:

- exact/broad/narrow/close ESCO mappings;
- regulated/essential/optional/calculated/transferable KV signals;
- job-title→occupation relations;
- keyword relations;
- substitutability 25/75 and direction;
- statistical similarity;
- ad-derived language/co-occurrence.

### UNKNOWN is not zero

Failed adapters, missing sources and unresolved schemas are `UNKNOWN`. No source may silently produce zero semantic coverage because extraction failed.

## 7. Data priority after current measurements

Current evidence order for experiments:

```text
canonical taxonomy text/identity
→ typed curated taxonomy relations
→ YV/KV published read models
→ Relevanta kompetenser
→ real employer/ad language + measured AF similarity
→ real query/search language where join semantics are known
→ embeddings/reranking over the above
→ synthetic LLM text only for measured residual gaps
```

This ordering is methodological, not a claim that every higher source always ranks better.

The new ad-language and Relevanta measurements materially reduce the justification for early synthetic phrase generation.

## 8. Synthetic data policy

Do **not** generate N phrases per concept as the baseline.

Synthetic phrases are allowed only after ablation shows a concrete residual gap that real/curated/observed sources do not solve. If used they must be generated, provenance-tagged, validated, deduplicated, adversarially tested and versioned. They never become canonical synonyms merely because retrieval metrics improve.

## 9. Research Gate 1 — Semantic Coverage Inventory

Goal: know which semantic material exists for every canonical YV/KV target and relevant context concept in v31.

### Completed / measured

- [x] active canonical text for occupation-name, skill, job-title, keyword
- [x] immutable common typed relation graph
- [x] SSYK/ISCO hierarchy coverage
- [x] ESCO mapping coverage split by mapping type
- [x] YV per-concept weights and active coverage
- [x] YV job-title parent multiplicity / ambiguity
- [x] YV 205-title residual population cross-version + graph characterisation
- [x] KV occupation-name and SSYK4 context coverage
- [x] KV regulated/essential/optional/calculated layer coverage
- [x] KV `transferable_skills` inventory
- [x] Relevanta kompetenser v31 schema and per-ID coverage
- [x] dedicated keyword/search-concept v31 distribution
- [x] curated occupation substitutability distribution and 25/75 semantics
- [x] Närliggande yrken current v31 distribution and basic coverage
- [x] published employer-language keyword coverage from Närliggande yrken
- [x] source adapter registry and hashes for accepted sources

### Remaining

- [ ] verify exact YV generator/methodology cause for the 204 persistent missing titles and identify the one v30→v31 dropout
- [ ] resolve specialised native occupation↔skill relation semantics independently of KV/Relevanta read models
- [ ] resolve Yrkesinformation distribution metadata anomaly
- [ ] measure raw historical/current advertisement coverage by trustworthy canonical joins beyond the already published derived keyword dataset
- [ ] establish JobAd enrichment field provenance and coverage
- [ ] resolve real query/search-language datasets and whether any contain true query→selection joins rather than frequency only
- [ ] build deprecated/replacement compatibility layer without polluting active identity
- [ ] build unified per-target coverage matrix and identify lowest-coverage YV/KV strata

Gate 1 is complete only when each remaining item is measured, explicitly blocked or scoped out with rationale.

## 10. Research Gate 2 — judged relevance benchmark

Build separate but structurally compatible YV and KV suites. Initial target: roughly 1,000–3,000 judged queries, expanded where strata expose weakness.

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
- rare/long-tail concepts;
- hard negatives/confusable siblings;
- broad/underspecified intent;
- deliberate no-valid-match / abstention.

Mandatory YV strata:

- exact job-title;
- measured 541-title multi-parent ambiguity population;
- the 205 active-title YV-exclusion population as a separate research stratum;
- task/skill description→occupation;
- same/similar title in different occupational contexts;
- substitutability 25/75 neighbours as hard-negative/context material.

Mandatory KV strata:

- skill descriptions without canonical terminology;
- software/tool/certificate/qualification/experience-like skill subtypes;
- occupation phrase→relevant skills;
- ordinary vs transferable skill evidence;
- nearby/confusable skills that must remain MUST_NOT.

Judged cases must allow genuine ambiguity:

```text
query
MUST
ACCEPTABLE
MUST_NOT
expected_intent: SINGLE | AMBIGUOUS | NO_MATCH
```

## 11. Research Gate 3 — controlled ablation

Evaluate YV and KV separately; do not force source symmetry.

```text
A  canonical labels only
B  A + real canonical definitions
C  B + alternative labels + title vocabulary
D  C + typed taxonomy graph + ESCO context
E  D + YV/KV selector evidence
F  E + Relevanta kompetenser + curated substitutability + other AF-derived data
G  F + real ad/query language corpora
H  G + vector retrieval / neural reranking over trusted representations
I  H + synthetic LLM enrichment only for measured residual gaps
```

Embeddings are intentionally tested **before** synthetic text. Every layer reports incremental gain and regressions per stratum.

## 12. Evaluation metrics

At minimum:

- Recall@K;
- MRR / nDCG@K;
- top-1 precision where one answer is justified;
- exact-label preservation;
- YV ambiguous-title recall/context preservation;
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

0. exact/explicit labels
1. prefix/token/fuzzy
2. curated semantic text
3. typed graph/context expansion
4. AF-derived evidence
5. corpus-derived observed language
6. vector similarity
7. optional cross-encoder reranker

Heterogeneous rankings require constrained deterministic fusion/rank fusion. Exact lexical evidence gets explicit dominance guarantees where appropriate.

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
  -> YV occupation candidates
```

KV example:

```text
"undersköterska"
  -> occupation context
  -> KV/Relevanta skill evidence
  -> exact KV skill candidates
```

The bridge is evidence generation, not identity conversion.

## 16. Hard invariants

- semantic retrieval never invents taxonomy IDs;
- YV and KV destination spaces never collapse;
- job-title identity retains occupation context;
- exact ambiguous YV identities remain available until disambiguated;
- active taxonomy job-title outside published YV is not automatically a valid YV output;
- occupation/SSYK context cannot masquerade as a KV skill;
- provenance survives candidate generation/fusion;
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
client validates/displays exact taxonomy identities
```

Possible shared request contract:

```json
{
  "taxonomy_version": 31,
  "target_space": "YV | KV",
  "query": "...",
  "limit": 10
}
```

Response must preserve taxonomy version, matcher version, target space, canonical candidate identity and provenance. API outage should degrade semantic enhancement, not make the selectors unusable.

No deployment choice is final before relevance, latency, privacy, availability, payload and iteration speed are measured.

## 18. Work sequence

### Now — finish Gate 1

- [x] establish repo/docs as SSOT
- [x] native text + common graph
- [x] YV and KV selector inventories
- [x] YV ambiguity/residual-title measurements
- [x] KV transferable skills
- [x] Relevanta kompetenser
- [x] dedicated keyword/search concepts
- [x] curated substitutability
- [x] Närliggande yrken + employer-language keyword coverage
- [ ] specialised native occupation↔skill semantics
- [ ] YV generator cause for persistent missing titles
- [ ] Yrkesinformation anomaly
- [ ] raw ads / JobAd enrichments / query-language joins
- [ ] deprecated compatibility
- [ ] unified coverage matrix + lowest-coverage strata

### Next — Gate 2

- [ ] benchmark schema
- [ ] high-confidence judged seed cases
- [ ] automatic strata construction where source truth permits
- [ ] 541-title ambiguity corpus/sample
- [ ] 205-title excluded-YV corpus/sample
- [ ] no-match and hard-negative corpus

### Then — Gate 3

- [ ] A–D non-neural baseline
- [ ] E–G evidence layers separately
- [ ] H vectors/reranking in shadow evaluation
- [ ] local compiled vs central API deployment benchmark
- [ ] I synthetic enrichment only if residual gaps justify it

### Product prototype after evidence

- [ ] YV `Beskriv yrket`
- [ ] KV `Beskriv kompetensen`
- [ ] `Inget av dessa` + feedback flow
- [ ] privacy-reviewed query→candidate→selection telemetry if permitted
- [ ] canary/rollback/versioned semantic API if API wins deployment evaluation

## 19. Open research questions

Resolved answers remain listed when useful.

1. occupation-name real definition coverage? **77.7%**.
2. skill real definition coverage? **24.5%**.
3. job-title real definition coverage? **~0.1%**.
4. YV occupation-name coverage? **100%**.
5. YV job-title coverage? **97.905%; 205 active titles absent**.
6. How common is multi-context YV title identity? **541 IDs, max 3 published YV parents**.
7. Are the 205 absent titles release lag? **No: 204/205 were already absent in YV v30**.
8. KV ordinary four-layer union? **4,647 skills = 68.824%**.
9. KV transferable skills? **27 active skills; 13 additional beyond ordinary layers; ranking semantics still open**.
10. Relevanta kompetenser coverage? **2,105 occupations, 4,685 skills; adds 404 skills beyond ordinary KV**.
11. Relevanta + ordinary KV union? **5,051 skills = 74.807%**.
12. Dedicated search concepts useful as broad YV/KV synonym source? **No; direct YV/KV coverage is very small**.
13. Employer-language keyword coverage? **1,051 occupations, 11,085 distinct terms; rescues 198/469 text-poor occupations**.
14. Curated substitutability coverage? **4,394 directional edges per field with explicit 25/75 semantics**.
15. What exact generator rule explains the 204 persistent YV title exclusions?
16. What are the native occupation↔skill relation semantics independent of KV/Relevanta?
17. How reliably can raw historical/current ads be joined to canonical YV/KV identities?
18. Which JobAd enrichment fields are human/source-derived vs model-derived?
19. Do search datasets contain true query→selection labels or only query frequency?
20. Which query strata actually need embeddings?
21. What abstention calibration is safe enough?
22. Does central API materially outperform compiled local semantics after operational costs?
23. How should deprecated concepts support old wording without polluting active identity?
24. What does observed `quality-level` mean on non-occupation types?
25. What is the intended product role of KV transferable skills?

## 20. Research discipline

Every important statement is one of:

- **measured** — reproduced by an inventory/evaluation;
- **documented** — stated by an authoritative source;
- **inferred** — deduction from measured/documented facts;
- **hypothesis** — requires experiment.

Do not promote attractive hypotheses to architecture. Do not turn unavailable data into zero. Do not hide source semantics inside a generic score. When evidence changes a conclusion, update this file.
