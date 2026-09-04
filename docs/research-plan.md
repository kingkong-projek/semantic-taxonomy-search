# Semantic Taxonomy Search — living research plan

**Status:** active research  
**Target taxonomy snapshot:** v31 unless an experiment explicitly says otherwise  
**Last updated:** 2026-09-04  
**Authority:** this file is the single source of truth for product scope, current conclusions, research gates and experiment order. Findings and generated inventories provide evidence; when evidence changes a conclusion, this file must change too.

## 1. Product problem

We are building semantic search for **both Yrkesväljaren (YV) and Kompetensväljaren (KV)**.

The common user problem is that a person often knows what they do or can do, but does not know the canonical taxonomy wording.

The products have **different canonical destination spaces**:

### YV

Free text / description must map to exact YV identities:

- `occupation-name`
- `job-title` **with its occupation-name context preserved**

A visible title string is not a globally unique occupation identity.

### KV

Free text / description must map to exact active:

- `skill`

Occupation-name, SSYK and other concepts may provide context/evidence for KV retrieval but are not interchangeable with the returned skill identity.

### Shared rule

Semantic retrieval may discover, expand, rank and explain candidates. It may **never invent, merge or mutate canonical taxonomy identities**.

## 2. Product UX hypothesis

Do not replace either picker with a chatbot.

Keep the current fast lexical picker as the privileged path. Add an explicit semantic fallback such as:

```text
Hittar du inte det du söker?
[Beskriv yrket]
```

for YV and correspondingly:

```text
Hittar du inte kompetensen?
[Beskriv kompetensen / vad du kan göra]
```

for KV.

Example YV flow:

```text
"Jag leder projektering av större byggprojekt
 och samordnar konsulter"

Vi tror att du menar:
○ Projektledare, bygg och anläggning
○ Projekteringsledare
○ ...
○ Inget av dessa
```

Example KV flow:

```text
"Jag programmerar styrda fräsar och skriver g-kod"

Vi tror att du menar:
○ CNC-programmering
○ CNC-teknik
○ ...
○ Inget av dessa
```

`Inget av dessa` / abstention is a first-class successful outcome. A vector search always has a nearest neighbour; the product is not allowed to turn that mathematical fact into false certainty.

A later feedback path may offer `Skicka in förslag`, but an all-rejected suggestion must become curation/evaluation data — never an automatically created taxonomy fact.

## 3. Architectural hypothesis

The problem is larger than "put embeddings on autocomplete".

```text
user text
  ↓
query interpretation
  ├─ lexical retrieval
  ├─ curated semantic text retrieval
  ├─ typed taxonomy graph retrieval
  ├─ AF-derived contextual retrieval
  ├─ corpus / observed-language retrieval
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

The retrieval infrastructure may be shared, but every request has an explicit target space:

```text
YV -> occupation/job-title-in-occupation-context
KV -> skill
```

Cross-entity bridges may generate evidence. They may not collapse target spaces.

Current strongest data principle:

> **Use existing semantics before manufacturing semantics.**

Deployment principle:

> **Compile semantics when practical; serve semantics where central iteration materially improves the product.**

Local/static versus API is a deployment decision, not a religion and not the same decision as relevance architecture.

## 4. Evidence / provenance classes

Every signal that can affect retrieval should retain a provenance class.

```text
canonical
curated_relation
derived_af
behavioral
corpus_derived
synthetic
```

Conceptually:

```text
                         TRUST / AUTHORITY
                                ▲
                                │
             canonical taxonomy concepts/text
                 curated typed relations
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

This is not a claim that higher layers are always better retrieval features. It is an authority boundary: a generated phrase, ad co-occurrence or calculated similarity must never silently become a canonical synonym or requirement.

## 5. Current measured state — taxonomy v31

### 5.1 Canonical/native text

Measured against the immutable active v31 snapshot:

| Type | Concepts | definition differs from preferred label | label-copy definition | with alternative labels |
|---|---:|---:|---:|---:|
| `occupation-name` | 2,105 | **1,636 (77.7%)** | 469 | 197 |
| `skill` | 6,752 | **1,654 (24.5%)** | 5,098 | 819 |
| `job-title` | 9,785 | **6 (0.1%)** | 9,779 | 0 |
| `keyword` | 1,484 | 0 | 1,484 | 1 |

Consequences:

- occupation-name has much richer curated descriptive text than earlier documentation suggested;
- skill is substantially more text-sparse and needs more graph/context support;
- job-title is essentially vocabulary + relation/context, not a description corpus;
- keyword value is wording + typed relation, not definition text.

Finding: [`findings/native-text-coverage-v31.md`](findings/native-text-coverage-v31.md)

### 5.2 Immutable common graph

Snapshot SHA-256:

`634fd9d848a172747e54e3e487160a912ae6c0fcb8219c50998767c8c9aacbcc`

It contains 43,695 unique active concepts.

High-value coverage:

#### occupation-name

- related → job-title: 1,583 / 2,105 (75.2%), 11,198 edges
- related → keyword: 130 / 2,105 (6.2%)
- broader → SSYK4: 100%
- broader → ISCO4: 100%
- ESCO occupation mappings are substantial and split across exact/broad/narrow/close

#### skill

- broader → skill-headline: 100%
- related → SSYK4: 6,734 / 6,752 (99.7%), 17,884 edges
- ESCO skill mappings are substantial and split across exact/broad/narrow/close

#### job-title

All 9,785 active job-title concepts have at least one occupation-name relation in the common graph.

Finding: [`findings/common-relations-coverage-v31.md`](findings/common-relations-coverage-v31.md)

### 5.3 Published Yrkesväljaren v31

Source SHA-256:

`1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49`

Measured file: 12,330 rows.

| Type | active taxonomy | unique YV IDs | row occurrences | coverage |
|---|---:|---:|---:|---:|
| occupation-name | 2,105 | 2,105 | 2,105 | **100%** |
| job-title | 9,785 | 9,580 | 10,225 | **97.905%** |

Critical measured result:

> **541 unique job-title IDs are related to multiple occupation-name contexts in YV; maximum observed parents = 3.**

This directly quantifies the original title ambiguity problem. A semantic YV result cannot be represented merely as `preferred_label -> one occupation`.

No unknown YV IDs, wrong concept types or invalid occupation parent references were observed.

YV weights are behavioural/search-frequency priors. They are not concept meaning.

### 5.4 Published Kompetensväljaren v31

Source SHA-256:

`da83f26bf316971caa407364d8feae6f791203bff5758e674cace3d919e4b524`

The read model has two typed context spaces:

- all **2,105 / 2,105 occupation-name** contexts;
- all **400 / 400 SSYK4** contexts.

It also contains a special non-context entry `transferable_skills`, which remains to be inventoried separately.

Four skill layers are currently measured on occupation contexts:

| Layer | edges | unique active skills | active skill coverage | occupation contexts non-empty |
|---|---:|---:|---:|---:|
| regulated | 137 | 33 | 0.489% | 109 |
| essential | 151 | 55 | 0.815% | 132 |
| optional | 2,727 | 1,463 | 21.668% | 796 |
| calculated | 31,637 | 4,104 | 60.782% | 2,097 |

Union of all four layers:

**4,647 / 6,752 active skills = 68.824%**.

Every referenced skill ID resolves to an active `skill` concept.

The four layers overlap and have different semantics/provenance. They must never be flattened into one generic "related skill" authority level.

Finding: [`findings/selector-coverage-v31.md`](findings/selector-coverage-v31.md)

Machine aggregate: [`../research/coverage/v31/selector-aggregate.json`](../research/coverage/v31/selector-aggregate.json)

## 6. Important semantic distinctions

### 6.1 YV occupation-name vs job-title

`job-title` is a separate identity, not an alternative label for occupation-name.

A single job-title may belong to several occupations. The published YV data proves this for 541 active YV titles.

Hard invariant:

> all exact canonical matches dominate non-exact semantic candidates, while ambiguous job-title identities remain separately scoped by occupation until the user/context disambiguates them.

### 6.2 KV skill vs occupation/SSYK context

KV returns skills. Occupation-name and SSYK are contextual evidence/routing spaces.

Hard invariant:

> an occupation or SSYK hit may cause skill candidates to be retrieved, but can never itself masquerade as a skill result.

### 6.3 Relation type matters

Never flatten:

- exact / broad / narrow / close ESCO mappings;
- regulated / essential / optional / calculated KV layers;
- job-title → occupation relations;
- keyword/search-concept relations;
- curated kinship;
- statistical similarity;
- ad co-occurrence.

The fact that two concepts are related does not imply synonymy and does not automatically imply symmetric retrieval strength.

### 6.4 UNKNOWN is not zero

A failed adapter, absent source or unresolved schema is `UNKNOWN`.

We already discarded an early GraphQL experiment because an extraction failure produced misleading zero relation counts. All accepted coverage now comes from reproducible versioned sources or explicitly documented adapters.

## 7. Known data landscape

| Source | What it can tell us | Search use | Authority caveat |
|---|---|---|---|
| Canonical taxonomy text | labels, real definitions where present | direct retrieval / embeddings | strongest concept-text authority |
| Alternative/hidden labels | explicit wording variants | lexical/semantic retrieval | stronger than generic related terms |
| Job-title relations | YV-specific title context | YV retrieval/disambiguation | never flatten parent context |
| Dedicated search concepts | user-facing search vocabulary | recall | not yet measured |
| SSYK hierarchy | occupational domain context | routing/context/hard negatives | membership ≠ equivalence |
| Skill-headline | broad skill grouping | KV context/diversification | grouping ≠ synonymy |
| ESCO mappings | cross-taxonomy semantics | enrichment/hard negatives | relation types differ |
| Yrkesväljaren | huge-search-corpus-derived weights | YV priors | popularity ≠ meaning |
| Kompetensväljaren | typed occupation→skill context layers | YV evidence + KV retrieval context | layers differ in provenance |
| Relevanta kompetenser | derived occupation→skill relevance | cross-entity candidate expansion | derived/noisy; not yet measured |
| Curated occupation kinship | task-level occupational similarity | YV expansion/hard negatives | preserve 75/25 semantics |
| Närliggande yrken | ad-derived similarity | YV discovery/context | statistical similarity ≠ equivalence |
| Historical ads | real employer language/tasks/tools | corpus retrieval/eval language | noisy labels/annotations |
| JobAd enrichments | extracted expressions | candidate enrichment | model-derived fields need provenance |
| Search logs / trends | real user vocabulary and drift | benchmark/ranking | frequency is not a labelled semantic mapping |
| Yrkesinformation | additional occupational text | possible YV enrichment | distribution metadata currently anomalous |
| Synthetic LLM phrases | manufactured paraphrases | last-resort recall | never taxonomy fact |

The current YV methodology reports about 2.603 billion retained Platsbanken searches after filtering. This is extremely valuable behavioural/language evidence, but it must not be described as billions of labelled `query -> canonical ID` examples unless the source actually contains that join.

Canonical adapter status: [`../research/coverage/source-adapters.json`](../research/coverage/source-adapters.json)

## 8. Synthetic data policy

Do **not** begin by generating N phrases per concept.

Real data is asymmetric. Some concepts have strong definitions, some have many titles, some have dense graph context, some have abundant ads, and some are long-tail.

Therefore we measure semantic coverage, not a quota such as "50 phrases per concept".

Synthetic phrases are permitted only as an experimental later layer after real/curated/observed sources have been ablated.

If used they must be:

```text
generated
-> provenance-tagged
-> validated
-> deduplicated
-> adversarially tested
-> versioned
```

They never become canonical synonyms merely because retrieval performance improved.

## 9. Research Gate 1 — Semantic Coverage Inventory

**Goal:** know exactly which semantic material exists for every canonical YV/KV target and relevant context concept in v31.

Primary destination spaces:

- YV: occupation-name + job-title-in-occupation-context
- KV: skill

Supporting/context spaces:

- SSYK4 and other hierarchy concepts
- keyword/search concepts
- ESCO occupation/skill
- curated/derived occupation↔skill data
- deprecated concepts only in a separate compatibility layer

Per concept/context capture dimensions separately; do not make one opaque coverage score.

### Gate 1 completed measurements

- [x] active v31 canonical text for occupation-name, skill, job-title, keyword
- [x] immutable common typed relation graph
- [x] SSYK/ISCO hierarchy coverage
- [x] ESCO mapping coverage split by mapping type
- [x] YV v31 per-concept weight coverage
- [x] YV job-title parent multiplicity / ambiguity
- [x] KV v31 occupation-name context coverage
- [x] KV v31 SSYK4 context coverage
- [x] KV regulated/essential/optional/calculated skill-layer coverage
- [x] source adapter registry and immutable hashes for accepted sources

### Gate 1 remaining

- [ ] KV `transferable_skills` special container
- [ ] explain/characterise the 205 active job-title IDs absent from YV
- [ ] specialised native occupation↔skill relations independently of KV read model
- [ ] dedicated search-concept dataset
- [ ] Relevanta kompetenser v31/current distribution and per-ID coverage
- [ ] curated Släktskap mellan yrkesbenämningar
- [ ] Närliggande yrken and any published corpus-derived keywords
- [ ] resolve Yrkesinformation distribution metadata anomaly
- [ ] historical/current advertisement coverage by trustworthy canonical join
- [ ] JobAd enrichment provenance/coverage
- [ ] real query/search-language datasets and exact join semantics
- [ ] deprecated/replacement compatibility layer
- [ ] unified per-target coverage matrix and lowest-coverage strata

Gate 1 is **not complete** until these are either measured, explicitly blocked, or explicitly scoped out with rationale.

## 10. Research Gate 2 — judged relevance benchmark

Create separate but structurally compatible YV and KV benchmark suites.

Initial target: roughly 1,000–3,000 judged queries overall, expanded as strata expose weaknesses.

### Shared strata

- exact preferred label
- alternative label/synonym
- spelling error
- Swedish compounds
- abbreviation
- English/international wording
- colloquial language
- task descriptions
- tools/method descriptions
- long natural-language descriptions
- rare/long-tail concepts
- hard negatives / confusable siblings
- broad/underspecified intent
- deliberate no-valid-match / abstention

### Mandatory YV strata

- exact job-title
- **multi-parent job-title ambiguity** using the measured 541-title population
- descriptions that should map through skills/tasks to occupations
- same/similar title in different occupational contexts

### Mandatory KV strata

- skill descriptions without canonical terminology
- software/tool/certificate/qualification/experience-style skill subtypes
- occupation phrase → relevant skills
- descriptions where a nearby skill is semantically related but should be MUST_NOT

A judged case should support more than one acceptable answer when reality is genuinely ambiguous:

```text
query
MUST
ACCEPTABLE
MUST_NOT
expected_intent: SINGLE | AMBIGUOUS | NO_MATCH
```

## 11. Research Gate 3 — controlled ablation

Run YV and KV separately against the same methodological layers. Do not force a source into one product merely for symmetry.

```text
A  canonical labels only
B  A + real/distinct canonical definitions
C  B + alternative/hidden labels + title/search vocabulary
D  C + typed taxonomy graph + ESCO context
E  D + published selector evidence (YV priors / KV typed context layers)
F  E + other AF-derived curated/statistical datasets
G  F + real ad/query language corpora
H  G + vector retrieval / neural reranking over trusted representations
I  H + synthetic LLM-generated enrichment, only for measured residual gaps
```

Important change from the earliest plan: **embeddings/vector retrieval are tested before synthetic text generation**. Embedding existing trusted/observed material changes retrieval representation; synthetic phrases manufacture new text claims and therefore deserve a later, stricter gate.

Every layer must report incremental gain and regressions per stratum.

If I adds negligible value or increases false-confidence/hard-negative errors, do not ship it.

## 12. Evaluation metrics

At minimum:

- Recall@K
- MRR / nDCG@K
- top-1 precision where one answer is justified
- exact-label preservation
- YV ambiguous-title recall/context preservation
- KV skill-identity precision
- hard-negative violation rate
- false-confident mapping rate
- abstention precision/recall
- no-result rate
- long-tail recall
- per-stratum metrics, never only one global average
- incremental gain by evidence layer
- explanation/provenance coverage
- latency
- cold-start
- payload/model/index size
- browser/server memory where relevant
- result diversity for broad queries

## 13. Retrieval lanes to test

Do not construct one mystical `semantic_score`.

Candidate lanes:

0. exact/explicit labels
1. prefix/token/fuzzy
2. curated semantic text
3. typed graph/context expansion
4. AF-derived evidence
5. corpus-derived text
6. vector similarity
7. optional cross-encoder reranker

Heterogeneous rankings should use explicit constrained fusion/rank fusion rather than arbitrary addition of incomparable raw scores.

Exact lexical evidence gets explicit dominance guarantees where appropriate.

## 14. Embeddings hypothesis

Embeddings remain plausible and likely useful for description-style queries, but they are an experiment, not the architecture.

Test:

- small multilingual encoders first;
- one-vector vs multi-view concept representations;
- separate views for label, definition/tasks, graph context, occupation context, observed language;
- hard-negative mining from near taxonomy concepts;
- precomputed concept/document vectors per taxonomy release;
- optional top-K cross-encoder reranking only if measured value justifies latency/cost.

Do not invent synthetic descriptions merely to make text-sparse concepts look symmetrical.

## 15. Cross-entity bridge

The graph/context can make the search much stronger than direct query→final-label embeddings.

YV example:

```text
"svetsa rostfria rör"
  -> TIG-svetsning / Rörsvetsning skill evidence
  -> typed occupation contexts
  -> YV occupation candidates
```

KV example:

```text
"undersköterska"
  -> occupation context
  -> typed skill layers / other relevant-skill evidence
  -> KV skill candidates
```

The bridge is evidence generation, not identity conversion.

## 16. Diversification and disambiguation

Broad queries should not return ten near-duplicates.

YV may diversify across occupational interpretations. KV may diversify across skill interpretations/subtypes.

Hard negatives can also power an "anti-search" interaction:

> Menade du X snarare än Y?

This should be based on measured confusability, not decorative suggestions.

## 17. Hard invariants

Regardless of implementation:

- semantic retrieval never invents taxonomy IDs;
- YV and KV destination spaces never collapse;
- job-title identity retains occupation context;
- exact duplicate/ambiguous YV identities remain separately available until disambiguated;
- occupation/SSYK context cannot masquerade as a KV skill result;
- relation and evidence provenance survives candidate generation;
- generated phrases never become canonical synonyms;
- failed/unmeasured source = UNKNOWN, not zero;
- wrong taxonomy version fails closed;
- same taxonomy version + matcher version + query is reproducible;
- semantic service unavailable must not silently corrupt lexical baseline;
- duplicate enrichment is idempotent;
- explanations may only cite evidence actually present in the retrieval trace;
- low confidence can and should abstain.

These should become property/metamorphic tests as implementation starts.

## 18. Deployment research — local-first vs API

There is no ideological opposition to a server/API.

The current static/local distribution has major advantages:

- host apps receive versioned data;
- no runtime server dependency for ordinary picker use;
- excellent availability and privacy characteristics;
- deterministic local snapshot behaviour.

A central semantic API has a different major advantage:

> ranking/index/model/calibration improvements can reach every host immediately without waiting for package upgrades.

That may be extremely valuable for a new semantic feature that will improve rapidly.

Current strongest deployment hypothesis:

```text
existing local lexical picker
        ↓
strong lexical result? -> return locally
        ↓ no / user chooses "describe"
optional central semantic service
        ↓
versioned canonical candidates + provenance
        ↓
client validates/displays exact taxonomy identities
```

API outage should preferably degrade the semantic enhancement, not make YV/KV unusable.

Possible shared request contract:

```json
{
  "taxonomy_version": 31,
  "target_space": "YV | KV",
  "query": "...",
  "limit": 10
}
```

Response must include at least:

```json
{
  "taxonomy_version": 31,
  "matcher_version": "...",
  "target_space": "YV | KV",
  "candidates": []
}
```

YV candidate identity needs enough scope to preserve job-title→occupation context. KV candidates are exact skill IDs.

The API decision is not final until relevance gain, latency, privacy, availability, payload size and operational iteration speed are measured.

## 19. Work sequence

### Now — finish Gate 1

- [x] establish repo/docs as SSOT
- [x] native text inventory
- [x] common typed graph inventory
- [x] YV published read-model inventory
- [x] quantify YV title ambiguity
- [x] KV context/layer inventory
- [x] adapter registry
- [ ] KV transferable-skills inventory
- [ ] YV missing-job-title analysis
- [ ] Relevanta kompetenser adapter
- [ ] dedicated search-concept adapter
- [ ] specialised native occupation↔skill adapter
- [ ] curated occupation-kinship adapter
- [ ] Närliggande yrken adapter
- [ ] resolve Yrkesinformation anomaly
- [ ] ads/enrichments/query-language adapters
- [ ] unified v31 semantic coverage matrix

### Next — Gate 2

- [ ] benchmark schema
- [ ] high-confidence judged seed cases
- [ ] automatic strata construction where source truth permits
- [ ] mandatory 541-title ambiguity corpus/sample
- [ ] no-match and hard-negative corpus

### Then — Gate 3

- [ ] A–D non-neural baseline
- [ ] E–G evidence layers one at a time
- [ ] H vector retrieval/reranking in shadow evaluation
- [ ] central API vs local compiled deployment benchmark
- [ ] I synthetic enrichment only if residual gaps justify it

### Product prototype after evidence

- [ ] YV `Beskriv yrket` UX
- [ ] KV `Beskriv kompetensen` UX
- [ ] `Inget av dessa` + feedback flow
- [ ] privacy-reviewed query→candidate→selection telemetry if permitted
- [ ] canary/rollback/versioned semantic API if API wins deployment evaluation

## 20. Open research questions

Resolved questions remain listed with their answer when useful.

1. occupation-name real definition coverage? **77.7%**.
2. skill real definition coverage? **24.5%**.
3. job-title real definition coverage? **~0.1% upper bound**.
4. occupation-name with job-title common relation? **75.2%**.
5. YV occupation-name coverage? **100%**.
6. YV job-title coverage? **97.905%; 205 active titles absent** — reason still open.
7. How common is one YV title across occupations? **541 job-title IDs, max 3 parents**.
8. KV occupation context coverage? **100% of 2,105 active occupation-name**.
9. KV SSYK4 context coverage? **100% of 400 active SSYK4**.
10. KV four-layer union skill coverage? **68.824% of active skills**.
11. What exactly is KV `transferable_skills` and how should it affect search?
12. What extra coverage/semantics does Relevanta kompetenser add beyond KV?
13. What is the dedicated search-concept coverage for YV and KV targets?
14. How much semantic language does ESCO add without scope drift?
15. How reliably can historical ads be joined to canonical YV/KV identities?
16. Do search logs contain true query→selection labels or only query frequency?
17. Which query strata actually need embeddings?
18. What abstention calibration is safe enough for description search?
19. Does a central API materially outperform local compiled semantics in relevance/iteration without unacceptable latency/availability/privacy cost?
20. Which user feedback/telemetry may legally and appropriately be retained?
21. What does observed `quality-level` mean on non-occupation types?
22. How should deprecated concepts support old language without polluting active identity?

## 21. Research discipline

Every important statement should be treated as one of:

- **measured** — reproduced by an inventory/evaluation;
- **documented** — stated by an authoritative source;
- **inferred** — deduction from measured/documented facts;
- **hypothesis** — requires experiment.

Do not promote an attractive hypothesis to architecture because it sounds plausible.

Do not silently turn unavailable data into zero.

Do not hide source semantics inside a generic score.

When evidence changes a conclusion, update this file. A new researcher should be able to read the repo and know both **what we currently believe** and **what would falsify it**.
