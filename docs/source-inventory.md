# Source inventory and epistemic roles

**Status:** living document  
**Last updated:** 2026-09-04

This document records the sources that may contribute to semantic taxonomy retrieval and, critically, what each source is and is not allowed to prove.

## 1. Labour Market Taxonomy API

Primary source:
- https://taxonomy.api.jobtechdev.se/
- Documentation: https://arbetsformedlingen.gitlab.io/taxonomy-dev/projects/jobtech-taxonomy/

### 1.1 `occupation-name`

Authoritative identity space for occupational designations.

Current documentation says:

- concepts may have `preferred-label`, `alternative-labels`, `hidden-labels`, `definition`, hierarchy/mapping relations and other metadata;
- `job-title` is a separate, narrower/different concept and must not be treated as a synonym;
- `keyword` is often broader/domain-like;
- occupation names can relate to SSYK/ISCO, ESCO occupations, job titles, keywords, other occupations and skills;
- `quality-level` is unique to `occupation-name`, with levels 1–3 describing how the concept update was anchored/researched;
- only a subset currently uses `quality-level`;
- most occupation-name concepts lack real definitions; `definition` is generally populated with the same term as `preferred-label` while definition work is incomplete;
- not all concepts are current.

Source:
- https://arbetsformedlingen.gitlab.io/taxonomy-dev/projects/jobtech-taxonomy/about/occupation-name.html

### 1.2 `job-title`

Important scope rule from the occupation-name documentation:

A job title linked to an occupation name is not necessarily an alternative label. It can represent a narrower scope and has its own canonical ID.

Retrieval use:
- excellent source of real title language;
- bridge to occupation-name;
- can support disambiguation and exact title matching.

Forbidden shortcut:
- flatten job titles into occupation-name synonyms.

### 1.3 Alternative and hidden labels

`alternative-labels` implement SKOS-style alternative labels and are intended for genuine synonym/abbreviation cases. Hidden labels are search-supporting labels but need coverage measurement and governance interpretation before use.

Retrieval use:
- strong lexical and semantic expansion;
- high-authority compared with generated phrases.

### 1.4 Keywords/search concepts

Keywords may represent broad concepts/domains and can be related to occupation names. The API's autocomplete documentation explicitly demonstrates finding an occupation through a keyword and following a relation to occupation concepts.

Retrieval use:
- candidate generation;
- broad-intent interpretation;
- explanations must preserve that the evidence is a related/broader search concept, not an exact synonym.

Sources:
- https://arbetsformedlingen.gitlab.io/taxonomy-dev/backend/jobtech-taxonomy-api/howto/getting-started.html
- https://arbetsformedlingen.gitlab.io/taxonomy-dev/projects/jobtech-taxonomy/about/occupation-name.html

### 1.5 SSYK hierarchy

Occupation names are tied to SSYK level 4. SSYK context can support:
- routing/sharding;
- hard-negative construction;
- broad query diversification;
- contextual reranking.

It is classification evidence, not evidence that two member occupations are equivalent.

### 1.6 Occupation↔skill relations

The occupation-name documentation describes `essential` and `optional` relations from occupation names to skills. This is potentially a strong semantic bridge.

Research requirement:
- measure actual v31 coverage;
- preserve essential vs optional;
- compare native relations with derived `Relevanta kompetenser` data rather than conflating them.

### 1.7 ESCO occupation mappings

Taxonomy occupation names are manually mapped to ESCO occupations using SKOS mapping relations such as exact, broad, narrow and close match.

Source:
- https://arbetsformedlingen.gitlab.io/taxonomy-dev/projects/jobtech-taxonomy/about/esco-occupation.html

Retrieval use:
- additional labels/descriptions/languages later;
- hard-negative and relation-aware enrichment;
- cross-lingual search experiments.

Constraint:
- mapping relation type must remain explicit.

### 1.8 Skills and ESCO skill mappings

The taxonomy has roughly thousands of native skill concepts while ESCO has a materially larger and generally more fine-grained skill vocabulary. Current docs describe manual mapping between taxonomy skills and ESCO skills.

Source:
- https://arbetsformedlingen.gitlab.io/taxonomy-dev/projects/jobtech-taxonomy/about/esco-skill.html

Retrieval use:
- enrich sparse native skills;
- possible descriptions and multilingual labels from ESCO;
- identify over-broad native concepts and confusable fine-grained variants.

Constraint:
- broad/narrow mappings must not be treated as synonyms.

## 2. Taxonomy downloadable datasets

Catalog:
- https://data.arbetsformedlingen.se/dataset/
- https://data.arbetsformedlingen.se/dataservice/employer-market-taxonomy/

Relevant distributions include:

- all concepts;
- occupation names;
- search concepts;
- concept types;
- occupation fields/SSYK/occupation relations;
- SSYK level 4 with related skills and occupation names;
- other specialised lists.

These may be preferable to repeated API graph walks for reproducible build-time inventory. Exact distribution URLs and snapshot/version metadata must be captured by the machine inventory before relying on them.

## 3. Yrkesväljaren data

Documentation:
- https://gitlab.com/arbetsformedlingen/taxonomy-dev/backend/yrkesvaljaren
- https://gitlab.com/arbetsformedlingen/taxonomy-dev/backend/yrkesvaljaren/-/blob/main/Metodbeskrivning.md
- Dataset page: https://data.arbetsformedlingen.se/dataset/occupation-suggester/

Documented semantics:

- contains `occupation-name` and `job-title` with weights derived from Platsbanken search frequency;
- occupation names inherit search counts from related job titles;
- weights are normalised and adjusted;
- update frequency follows taxonomy releases.

Reported source corpus:
- search interval stated as 2022-05-04 through 2026-02-14;
- very low-frequency searches filtered;
- retained search count reported as 2,603,440,552.

Known limitations stated by source:
- language drift is slow to affect the aggregate because of corpus size;
- Platsbanken does not represent the entire labour market.

Important interpretation:

This is excellent **behavioural ranking evidence**. It is not automatically a labelled semantic corpus. A query count attached to a title does not prove that arbitrary natural-language descriptions map to that concept.

Source anomaly:
The current methodology page includes the phrase `2026-12-15 var omfattningen...`, which is later than this document's date. Preserve this as a source anomaly until verified rather than silently treating it as a trustworthy observation date.

## 4. Relevanta kompetenser

Documentation:
- https://gitlab.com/arbetsformedlingen/taxonomy-dev/backend/relevanta-kompetenser
- https://gitlab.com/arbetsformedlingen/taxonomy-dev/backend/relevanta-kompetenser/-/blob/main/Metodbeskrivning.md
- Dataset: https://data.arbetsformedlingen.se/dataset/relevant-skills-for-occupations/

Purpose:
- propose relevant native `skill` concepts from a selected `occupation-name`;
- derived through mappings between Arbetsförmedlingen's taxonomy and ESCO.

Documented observations:
- majority of occupation names and skill concepts are mapped to ESCO;
- ESCO has much finer skill granularity;
- scoring/filtering is derived rather than canonical taxonomy truth.

Retrieval use:
- cross-entity candidate generation;
- skill ranking in occupation context;
- hard-negative analysis.

Constraint:
- never promote a derived relevance edge into canonical taxonomy identity or mandatory skill semantics.

## 5. Kompetensväljaren

Known project context:
- local/versioned read-model data;
- base manifest plus context shards;
- occupation→SSYK4→SSYK3 routing;
- relevant context shard loaded rather than a runtime backend query;
- taxonomy releases are versioned and relatively infrequent.

Research use:
- inspect exact source/build pipeline and semantics in a later adapter;
- measure which native skills receive usable occupation-context coverage;
- test hierarchical semantic routing aligned with existing SSYK sharding.

Do not assume its scores/relations have the same authority as native taxonomy relations.

## 6. Historical Platsbanken ads

Documentation/catalog entry:
- https://data.arbetsformedlingen.se/annonser/historiska

Potential value:
- real employer vocabulary;
- task descriptions;
- tools/methods;
- co-occurring skills;
- title variants over time;
- source for hard positives and negatives.

Risks:
- occupation annotation may be missing or incorrect;
- ad text is noisy and employer-specific;
- current job language may differ from older text;
- ad corpus frequency can overwhelm rare but correct taxonomy semantics.

Use first as corpus-derived retrieval/evaluation evidence, not authority.

## 7. Current JobSearch / JobStream

Documentation:
- https://jobsearch.api.jobtechdev.se/
- https://jobstream.api.jobtechdev.se/

Potential use:
- recent language drift;
- current ad vocabulary;
- current structured occupation/skill associations.

JobSearch documentation explicitly notes that structured occupation fields can give higher certainty but may miss relevant ads when employers did not set the occupation field. This is a useful warning for any ad-derived ground truth.

## 8. JobAd Links

API:
- https://links.api.jobtechdev.se/

Current documentation says the dataset adds references/metadata from major job boards and contains roughly 30% more ads than Platsbanken, with ML classification to SSYK.

Potential use:
- broaden labour-market language coverage;
- external-platform drift comparison.

Constraint:
- ML classification is derived evidence, not canonical ground truth.

## 9. JobAd enrichments / structured requirements

Current job-ad APIs expose structured requirements such as skills and work experience, and historical data may include enrichment.

Potential use:
- relation/corpus features;
- candidate-language mining;
- co-occurrence statistics.

Research requirement:
- identify exactly which fields are human-entered vs automatically enriched for each data source/version before treating them as labels.

## 10. Närliggande yrken

Known source semantics from prior research:
- occupational similarity derived statistically from millions of ads using methods including TF-IDF/BM25/RCA/cosine plus filters;
- source documentation frames it as showing possibilities rather than certifying suitable career transitions.

Potential use:
- candidate expansion;
- diversity;
- hard-negative generation;
- graph/context signal.

Constraint:
- similarity is not equivalence and not proof of career feasibility.

## 11. Yrkesinformation

Catalog currently exposes an interim occupational-information dataset while a replacement backend is being built.

Potential use:
- richer human-authored descriptions for some occupations;
- additional task/context text.

Research requirement:
- measure exact concept coverage;
- identify version/update cadence;
- distinguish editorial description from forecast/barometer fields.

## 12. Source precedence for retrieval research

Working precedence for meaning/authority:

1. canonical taxonomy identity and explicit canonical attributes;
2. curated taxonomy relation with exact relation type;
3. manually curated external mapping with relation type (e.g. ESCO mapping);
4. documented AF-derived datasets;
5. observed behaviour/search data;
6. corpus-derived/ad-derived signal;
7. synthetic/generated language.

This precedence is not the same as ranking weight. A behavioural signal may be extremely useful for ranking while still being weaker evidence about what a concept means.

## 13. Coverage inventory adapter backlog

The machine inventory should eventually produce per-concept coverage columns for:

- [x] native taxonomy concept text fields
- [ ] native taxonomy graph relations
- [ ] ESCO mappings
- [ ] Yrkesväljaren weights
- [ ] Relevanta kompetenser
- [ ] Kompetensväljaren read-model coverage
- [ ] occupational-information coverage
- [ ] historical-ad counts/usable corpus evidence
- [ ] current-ad language signal
- [ ] JobAd Links signal if useful
- [ ] search-term/keyword distributions

Each adapter must record:

```text
source_name
source_version_or_snapshot
retrieved_at
join_key
coverage_semantics
warnings
```

A source adapter is not considered complete merely because it can download data; its join semantics and epistemic meaning must be documented.
