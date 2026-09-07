# Semantic Taxonomy Search — living research plan

**Status:** active research  
**Target taxonomy snapshot:** v31 unless an experiment explicitly says otherwise  
**Last updated:** 2026-09-07  
**Authority:** this file is the single source of truth for product scope, current conclusions, research gates and experiment order. Findings and generated inventories provide evidence; when evidence changes a conclusion, this file must change too.

## 1. Product problem

The observed product problem is deliberately broader than a semantic-fallback residual: **users report that they sometimes cannot find the occupation or competence they are looking for**. We do not yet know which failure mechanisms dominate. The failure may occur in wording/lexical matching, ranking, title-vs-occupation modelling, product admission/exclusion, ambiguity/context handling, interaction behaviour, integration/hand-off, missing vocabulary, or genuinely semantic description search.

This repository builds a **reusable semantic search/fallback capability for occupations and skills/competences**. It does not own or rebuild YV/KV's ordinary selector UX. YV and KV are the first concrete reference consumers against which we establish the lexical/product baseline and determine what semantic search must add.

The YV/KV audit is therefore a deliberately bounded **Track-1 sidetrack for problem understanding, baseline quality and integration boundaries**, not the delivery scope of this repository. Findings may identify product-native YV/KV defects or bounded improvements, but adoption belongs to the owning product repositories and their protected integration process. GitHub branch/CI verification is evidence, not deployment. JobSearch/Platsbanken and other AF datasets are evidence sources, not the target product.

The core target spaces are intentionally simple:

- **occupation:** canonical active `occupation-name` identities;
- **skill:** canonical active `skill` identities.

A consuming service applies its own admission/profile rules after or around retrieval. YV may therefore admit published occupation/job-title identities with exact occupation context, while another service may admit a different occupation subset. KV is one concrete skill-selection profile.

Occupation context, job titles, SSYK, skill-headline, keyword, ESCO and other concepts may be used as evidence/routing/context. They are not interchangeable with the returned core identity.

Hard shared rule:

> Semantic retrieval may discover, expand, route, rank and explain candidates. It may never invent, merge or mutate canonical taxonomy identities, and it may never bypass the consuming service's explicit admission policy.

## 2. Product UX hypothesis

Do not replace ordinary selectors with a chatbot.

Keep fast lexical selection as the privileged path where a consuming service already has it. A live hypothesis is that **YV and KV may already be very good within their current selector architecture**; the vague report that some users cannot find an occupation/competence is not evidence that ordinary search is broadly broken. Track 1 therefore measures and fixes only demonstrated current-selector failures instead of assuming a semantic diagnosis.

A separate Track-2 hypothesis remains to be tested: **when ordinary YV/KV lookup does not produce a selection the user recognises as correct, describing the work or competence in ordinary language may recover an existing taxonomy identity before the user proposes a new one**. This is a hypothesis about one failure mechanism, not a claim that users generally do not know their occupation/competence terms.

The intended product sequence is a progressive fallback ladder around otherwise unchanged YV/KV selectors:

```text
1. ordinary YV/KV lookup exactly as the owning product provides it
2. if the user still cannot find a suitable existing result: [Beskriv ditt yrke] / [Beskriv din kompetens]
3. open description mode and interpret task/tool/method/responsibility language against existing admissible canonical candidates
4. if the user still cannot find what they mean: [Ge förslag] for a genuinely missing/unsuitable concept rather than silently accepting an arbitrary custom value
```

The labels are product-copy hypotheses, but the ordering is a scope contract for this research: **ordinary selector first → semantic description fallback → proposal last**. The semantic capability must try to recover an existing canonical identity; it must not turn free text into a new selectable taxonomy identity. `Ge förslag` is downstream product handling for the case where semantic retrieval still does not yield an acceptable existing concept.

Description mode explicitly includes ordinary first-person/task language such as `jag drog kabel, kopplade uttag och läste elscheman`, not only near-synonyms of taxonomy labels. Tasks, tools, methods, responsibilities and colloquial wording are first-class fallback input.

The core result remains an exact canonical occupation/skill identity with provenance; the consumer then enforces its admission profile. `Inget av dessa` / abstention is a first-class successful outcome. A nearest neighbour is not proof that a valid match exists.

### 2.1 Findability-first product objective

The **primary v0 product question is end-to-end findability**: for a user trying to locate the right occupation or competence, does the product surface the intended valid identity in a small usable result set? Semantic fallback is one possible intervention and its incremental value remains useful to measure, but it must not redefine the original problem as only the subset of queries left after ordinary lookup fails.

Evaluation must therefore distinguish failure mechanism before choosing a fix: ordinary lexical reachability, ranking, title/occupation routing, ambiguity/context, product admission, integration/hand-off, and description-style semantic retrieval. The smallest intervention that fixes a material measured findability failure wins.

The pinned current implementation baseline is `kingkong-projek/yrkesvaljaren@ab0b3f28576d8aebec2b593b771a70c7684b1eca`:

- current YV already performs exact, prefix/multi-token, substring and guarded Fuse fallback over preferred labels, with behavioural weight as ranking evidence;
- current KV already performs global exact/prefix/word-boundary/contains/fuzzy skill lookup, while occupation/SSYK/context lists and precomputed `weightedSkills` influence ranking among text/fuzzy candidates and provide the empty-query initial list.

Therefore decision-bearing semantic evaluation has two separate views:

1. **Fallback value — primary.** Evaluate description/task/tool/method/colloquial queries for which the current selector does not already provide an adequate small discovery list. Report semantic **increment over the pinned current selector** at K, not only absolute semantic accuracy.
2. **Full-replacement potential — secondary bonus.** Separately test whether one simple engine preserves or improves the current selectors' ordinary exact/prefix/substring/fuzzy/context behaviour while also solving description fallback. Do not make replacement a v0 requirement.

Canonical label, alternative-label, typo and ordinary substring cases remain essential regressions, but success on them alone is not evidence that semantic fallback adds product value. A future single implementation may still contain a privileged lexical lane internally; `one engine` does not imply semantic similarity must handle every query.

Evidence: `docs/findings/current-selector-baseline-2026-09-06.md`.

**Product-first gate before semantic expansion:** real YV/KV users report that they sometimes cannot find the occupation or competence they need. Treat that report as the phenomenon to explain, not as evidence for a predetermined residual or semantic diagnosis. Audit the complete findability path against published data, interaction paths and integration contracts; classify observed failures by mechanism; then fix the cheapest material cause. Description-semantic fallback is evaluated as one capability within that broader findability problem, not as the definition of the problem.

The first YV audit materially narrowed the problem. Ordinary multi-context dropdown lookup is healthy (**541/541** exact multi-context titles expose all intended context rows). Two narrow context-preservation defects were verified and patched in `kingkong-projek/yrkesvaljaren@81a7cb5e7d52e2c5a0d343011774a2f4dbcf6991` (PR #34): rich `setSelection()` now preserves the selected `related` occupation context, and a bare ambiguous exact title no longer silently auto-selects the first context on blur. Normal YV search/ranking was not changed.

Evidence: `docs/findings/current-selector-failure-audit-v31.md` and `research/coverage/v31/current-selector-failure-audit.json`.

### 2.1.1 Two-track research order — Track 2 active; Track 1 parked

The work remains split into two separate tracks. They must not be blended into one residual metric.

**Track 1 — current YV/KV findability (PARKED; bounded sidetrack).** The product audit already produced useful baseline evidence and branch-verified product findings, but YV/KV implementation is outside this repository's semantic-search abstraction. By explicit project decision on 2026-09-06, do not continue expanding this sidetrack now. Its remaining exit criteria stay recorded below so the audit can be resumed later without losing state.

**Track 2 — semantic description fallback (ACTIVE).** Build and evaluate the capability behind `Beskriv ditt yrke` / `Beskriv din kompetens` for users who still cannot select a suitable existing concept through ordinary lookup. If description search still yields no acceptable existing identity, the consumer may offer `Ge förslag`; proposal handling itself is outside the semantic retrieval core.

Current Track-2 result: occupation discovery remains on the simple deterministic C2 boundary because no measured fresh-holdout residual has justified more complexity. For skills, **`KV-G1-4slot` remains the independently source-attested base**, while the strongest current low-complexity research candidate is **`KV-G1+T3`**: preserve canonical C0 rank 1, admit one unique candidate from the existing G1 BM25 lane, then admit three unique candidates from a second BM25 view containing the same G1 evidence plus three frozen teacher phrases per P80 skill. Runtime still uses no language model, embeddings/vector index, learned reranker, score calibration or query classifier.

Across the three source-attested AF description sets, G1 reaches **68/81 Hit@5 (83.95%)** and the later G1+T3 candidate reaches **71/81 (87.65%)**, with the canonical guard still **617/617 Top1 and Hit@5**. Those 81 AF cases were already opened during later teacher/fusion development, so 71/81 is development/safety evidence rather than a new blind human accuracy estimate. The final untouched P80 slice, ranks 301–316, was frozen in the order candidate → teacher phrases → queries → retrieval: G1 reaches **2/16**, while plain G1+T3 reaches **11/16 Hit@5**. That slice is temporally prefrozen and target-disjoint but model-authored, so it is generalization/falsification evidence rather than independent user accuracy.

The complexity boundary is now explicit. Teacher-only/C0+teacher representations and a character-4gram lane failed to earn their cost. Removing pure numeric tokens from expansion documents and queries was **rejected** after the prefrozen final gate exposed a new `Svetsteknik` regression from rank 5 to 215 through BM25 document-length normalization. A still smaller query-only integer filter is favorable on already-opened data (71/81 → 72/81, zero opened Hit@5 regressions, canonical 617/617), but **must not be promoted**: a source-only blinded builder found zero remaining unused AF cases satisfying the prefrozen quality/independence criteria and containing a pure integer token. Do not weaken those criteria or manufacture post-hoc synthetic validation.

Therefore **plain G1+T3 is the current simple research boundary and no higher model class is justified now**. Stop retrieval micro-optimization until new independent human/user evidence or a measured product failure identifies a material residual. The next evidence priority is the bounded product hypothesis itself: whether users who fail ordinary lexical lookup can describe tasks/tools/methods/responsibilities well enough to recognise and select the intended canonical candidate from a small fallback result set.

**Exploratory demo failure evidence (2026-09-07): the stop condition has now been met for a bounded KV ranking/calibration investigation.** One explicitly exported tester session contained 21 submissions / 19 unique descriptions and exposed several trust-breaking rank orders, including plausible task descriptions where a related candidate appeared below obviously unrelated top results. This session is opened, non-preregistered product evidence and MUST NOT be reported as blind human accuracy or used as a tuning holdout. It does falsify the assumption that Hit@5 alone is sufficient for product quality: a rank-3 hit can coexist with unusable rank 1–2 results. Simple matched-term coverage is also insufficient as a confidence gate because some visibly bad rankings matched all unique query terms. The next bounded retrieval work is therefore diagnostics plus conservative ranking/abstention gating, evaluated on a newly frozen independent description set; do not tune directly to the 19 opened descriptions and do not escalate model class without that evidence. Evidence: `docs/findings/kv-demo-exploratory-field-failures-2026-09-07.md`.

**Human-gate status (2026-09-07): collection-ready, not started.** The no-example participant prompt, blind adjudication rules, per-target P80-envelope semantics, staged case validator, preregistration template, preregistration→manifest SHA binding, raw-text-free need/prevalence funnel format and repository stage-order guard are now frozen and self-tested on the `garderob` runner. No real human description, adjudication or outcome file is present in the repository yet. Before the first participant, `preregistration.json` must replace all template placeholders and be committed with status `frozen-before-first-participant`; retrieval may run only after elicitation and blind adjudication are frozen and a manifest binds all three SHA-256 values. A recruited capability study must not be reported as production prevalence without the separate eligible lexical-failure denominator.

Evidence: `docs/findings/skill-training-language-validated-v31.md`, `research/evaluation/v31/skill-training-language-validated.json`, `docs/findings/kv-g1-t3-simple-boundary-v31.md`, `research/evaluation/v31/kv-g1-t3-simple-boundary.json`, `research/evaluation/v31/kv-query-only-numeric-validation-boundary.json`, `docs/findings/description-fallback-human-validation-protocol-v31.md` and `research/evaluation/v31/description-fallback-human-validation-contract.json`.

Track 1 exits only when all of the following are true:

- the source-attested current-selector `should-find` replay is frozen and its highest-signal misses are classified;
- verified product-native defects discovered by that audit are patched or explicitly accepted with measured materiality;
- canonical alternative-label reachability is measured for both YV and KV and the smallest safe improvement is evaluated;
- the frozen non-description persona journeys are replayed against the exact current product behaviour, with candidate failures independently verified rather than accepted from the persona itself;
- YV→KV context/coherence is verified in the accessible integration paths;
- a compact failure-mode map records mechanism, evidence class, examples, estimated materiality, cheapest fix, regression risk and status;
- remaining material failures are explicitly classified as requiring Track 2 rather than another cheaper current-selector fix.

Description journeys already frozen under `research/personas/v31/journeys.jsonl` remain immutable but **must not be replayed or used to choose retrieval changes during Track 1**.

Evidence: `docs/findings/current-selector-should-find-v31.md`, `research/evaluation/v31/current-selector-should-find-summary.json`, `docs/findings/persona-findability-protocol-v31.md`.

**Track 1 status — canonical alias reachability measured and branch-verified (2026-09-06).** Against the pinned current-selector baseline, current canonical alternative/hidden labels are overwhelmingly unambiguous. The current selector finds 318/357 strict YV alias cases and **1,056/1,279 KV** cases at 5. A privileged exact-normalized current-alias lane deterministically rescues the remaining **39 YV** and **223 KV** strict cases, reaching 100% on that bounded set. The safe implementation has been verified on the YV/KV product branch with full self-hosted build/tests, but it is not deployed by this research repository. Alias collisions fail closed / remain multi-candidate; deprecated `replaced_by` labels are explicitly excluded from synonym treatment. Evidence: `docs/findings/track1-canonical-alias-reachability-v31.md` and `research/evaluation/v31/track1-canonical-alias-rescue.json`.

### 2.1.2 Persona-based experiential red-team

Conventional retrieval metrics can miss the reported user experience even when a technically valid identity appears somewhere in the result set. Add an exploratory **persona journey** layer that asks whether different realistic jobseekers can *recognise and recover* the occupation/competence they mean. Personas vary occupational self-knowledge, labour-market vocabulary, title-vs-task search strategy, current vs historical terms, Swedish vs English workplace language, typo tolerance, ambiguity/context needs and willingness to inspect/reformulate results. Do **not** infer behaviour from protected/demographic traits.

Personas are synthetic discovery instruments, **not empirical users and not benchmark ground truth**. Freeze each journey's goal and first query before inspecting selector output. A persona-generated failure becomes a finding only after independent verification against authoritative taxonomy/source truth, observed query evidence, reproducible product code/data or actual human feedback. Ambiguous journeys may correctly end in clarification or abstention.

In addition to Recall@K, inspect experience-level properties: **recognisable-at-3/5**, recoverable within two natural reformulations, variant overload, misleading plausible top hits, context preservation through selection and YV→KV, visible KV coherence, give-up proxy and safe abstention. Keep these mechanism-specific initially rather than collapsing them into one score.

The initial v31 matrix has 12 composable personas and starts from reported/high-volume anchors such as broad `projektledare`, `projektkoordinator` with parenthetical context, common excluded titles, multi-context titles under realistic typo/context qualification, YV→KV coherence, and task-first description journeys. Full protocol: `docs/findings/persona-findability-protocol-v31.md`; structured matrix: `research/personas/v31/personas.json`.

Track-1 research order is: freeze source-attested should-find replay → replay only the non-description persona journeys against exact current product UX → independently verify candidate failures → cluster by mechanism/demand/risk → fix and measure the smallest material causes → produce the failure-mode map and satisfy the Track-1 exit criteria. Only after that may Track 2 resume.

### 2.2 Pareto / simple-first delivery principle

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

**Experimental discipline: do not build the palace first.** Every step should be the smallest falsifiable increment over a frozen baseline. Measure it, keep it only if it earns its complexity, and let negative results delete entire ideas. Do not pre-build general frameworks, shard hierarchies, model-serving abstractions or future-proof extension points merely because they may become useful later. A deliberately plain implementation is preferred when it answers the current decision question.

Build-time work and runtime work have different budgets. Expensive offline analysis, model-assisted adjudication or future teacher-model generation is allowed when it can be provenance-preservingly distilled into a simpler static representation and independently validated. Such generated evidence never becomes canonical truth merely because a strong model produced it. Runtime complexity receives no credit for being sophisticated; the smallest validated student representation wins.

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

Current deployment constraint:

> **Frontend-only, build-time-first, low-end-mobile-first. Compile as much semantic work as practical before release; ordinary YV/KV pays zero semantic payload/runtime cost; lazy-load the smallest static fallback asset only after the user explicitly enters description mode.**

The current consuming architecture has no semantic search/inference API. API serving is therefore out of scope for v0 rather than an open experiment. Runtime must require no accelerator and must not depend on WebGPU, ONNX or a heavyweight local model. A future architecture change may revisit that boundary, but current relevance work must remain deployable as static assets plus deterministic browser computation.

The validated KV student runtime now demonstrates the intended shape concretely. C0 and G1 BM25 statistics are precomputed at build time into one dual-score inverted index. Browser work is only normalization/tokenization, postings lookup, floating-point addition, a deterministic small sort and bounded fusion. The complete production-shaped dual index is **151,768 bytes gzip-9**, has zero runtime dependencies and is loaded only for `Beskriv din kompetens`. It reproduces the reference top-10 exactly on **649/649** frozen parity cases. `garderob` measures about **166 microseconds/query** as an implementation diagnostic; that timing is not a mobile SLA.

Because the whole currently validated KV semantic payload is only about 152 kB compressed, **do not shard it now**. Chunking remains available if later measured evidence grows the asset enough to justify the extra requests/cache/complexity. Likewise, embeddings or local neural inference remain deferred until a relevance residual proves that the static student approach is insufficient.

Evidence: `docs/findings/skill-g1-student-runtime-v31.md` and `research/evaluation/v31/skill-g1-student-runtime.json`.

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

### 5.5.2 Product-first YV/KV selector audit

The current products are now audited as products, not only as semantic data sources.

YV:

- ordinary exact multi-context dropdown lookup is healthy: **541/541** multi-context job-title IDs expose all intended contextual rows in direct top 10;
- the earlier **11.153% excluded-title volume** must not be read as an 11% failure rate: current deterministic direct YV already routes **96.073%** of that volume to at least one generator-mapped occupation in top 10;
- the remaining direct-lane excluded-title residual is **13,734,681 queries = 0.438% of all retained query volume** before guarded Fuse fallback;
- two narrow identity/interaction defects were fixed in YV commit `81a7cb5e`: rich roundtrip now preserves `related` occupation context and bare ambiguous blur no longer selects row 1 arbitrarily;
- 197 admitted concepts expose 362 canonical alternative-label surfaces; **51** currently lack a deterministic direct YV result.

KV:

- all 6,752 active skills are present, but candidate generation is driven primarily by preferred labels/tokens;
- **819** skills expose 1,308 canonical alternative-label surfaces, with **260** lacking a canonical contains match in the current direct lane;
- **1,654** skills have a definition distinct from the preferred label, but definitions do not participate in ordinary candidate generation;
- occupation/SSYK context can rank/filter lexical candidates but cannot create a candidate when the user's wording is absent from the skill label.

The repo's stepped YV→KV demo also demonstrates an integration footgun: a job-title selection carries the occupation parent as `related.id`, while the demo passes `selection.id` to KV. This is proven in the demo, not yet in production consumers.

**Current decision:** do not add semantic model/source complexity merely because ordinary selector behaviour has not yet been measured honestly. Next product-native checks are exact current-Fuse replay on the 0.438% YV direct residual, demand/gain from unused canonical alternative labels, and YV→KV job-title hand-off. Description fallback remains the separate capability for users who still cannot discover their concept after those ordinary paths are sound.

Evidence: `docs/findings/current-selector-failure-audit-v31.md` and `research/coverage/v31/current-selector-failure-audit.json`.

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

Synthetic **queries for evaluation** and synthetic **retrieval/enrichment text** are different things and must not be conflated.

Synthetic query generation is allowed now as a separate benchmark/stress-testing tool, especially for realistic description-mode input such as first-person work history, tasks, tools, methods and colloquial wording that is not available with selected-ID ground truth in public query logs. Such cases must be tagged `synthetic_query`, kept separate from real/source-attested traffic metrics, and never assigned traffic weights. Their expected identity must be anchored in source-attested taxonomy evidence or separately adjudicated. Preferred/alternative target-label leakage should be excluded unless leakage is the explicit stratum under test.

Synthetic queries are **not training data by default** and must not be copied into retrieval documents merely because they expose failures.

Synthetic retrieval/enrichment phrases remain deferred until ablation shows a concrete residual gap that real/curated/observed sources do not solve. If used they must be provenance-tagged, validated, deduplicated, adversarially tested and versioned. They never become canonical synonyms merely because retrieval metrics improve.

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

The frozen source-truth core currently contains **950 cases**: 333 YV and 617 KV over all 475 P80 targets. It includes 475 preferred-label cases, 330 real canonical-definition cases and 145 alternative-label cases. This is deliberately a source-attested **regression/representation benchmark**. It does not measure incremental fallback value unless the pinned current selector is also run on the same fallback-eligible query.

The current YV/KV implementation is now baseline 0 for decision-bearing product evaluation. Description-style cases should record both current-selector Discovery@K and semantic-fallback Discovery@K; the decision metric is the incremental gain where ordinary lookup is insufficient.

**Product-native residual discipline:** prefer cheap ordinary-selector fixes before adding semantic complexity **within the affected target space**. The verified YV context defects are fixed (`81a7cb5e`). The remaining YV Fuse/alternative-label/handoff checks stay useful reference-product hygiene, but they no longer globally block independently measured `skill` fallback research. Skill work may proceed because the pinned current KV product has now been measured on the same blind description benchmark.

Non-blocking YV follow-ups:

- [ ] replay the remaining **0.438%** excluded-title direct residual through the exact current Fuse.js lane;
- [ ] measure actual demand and Discovery@5 gain from currently unused canonical alternative-label vocabulary in YV;
- [ ] verify YV→KV job-title occupation-context hand-off in production consumers.

Evidence: `docs/findings/p80-decision-benchmark-v31.md`, `research/benchmark/v31/p80-source-truth/manifest.json`, `docs/findings/current-selector-baseline-2026-09-06.md`, `docs/findings/current-selector-failure-audit-v31.md`, and `docs/findings/skill-fallback-increment-v31.md`.

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
- a small high-volume unbound observed-query sample receives explicitly provenance-tagged adjudication (human or model judgment);
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

**Ordering constraint:** within each target space, prefer cheaper product-native fixes before adding semantic complexity. Unresolved YV reference-product hygiene does not block the separately measured KV description fallback. For skills, the pinned current KV selector is now baseline P on the blind holdout: it returns no result for 35/35 cases, while deterministic KV-C0 rescues 11/35. Further skill complexity must therefore be justified against that incremental baseline and validated on fresh evidence.

Evaluate occupation and skill retrieval separately; do not force source symmetry. Keep YV/KV reference-profile slices separate where their admission/routing semantics materially differ.

```text
P  pinned current YV/KV production selector baseline
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

For the primary fallback view, report **incremental Discovery Success@5 over the pinned current selector** and the share of tested queries that are genuinely fallback-eligible. Absolute semantic scores without the current-selector baseline are development diagnostics only. For the secondary replacement view, run the candidate engine against current ordinary-selector regression behaviour as well.

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

- [x] pin and code-audit the **current YV/KV selector implementation as baseline 0** (`kingkong-projek/yrkesvaljaren@0eba98e3a91079a43c1eaf6da09dfabe11e5bc8b`); separate primary fallback-value evaluation from secondary full-replacement potential
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


C2 result: the smallest next capability was enough again. C2 keeps C1 unchanged and adds only an exact active `job-title` preferred-label lookup whose already-typed `occupation-name` parents are unioned into the candidate list. On the previously opened holdout, volume-weighted Discovery Success@5 rises from C1 **84.788%** to C2 **93.677%**, with 100% NO_MATCH abstention; only `lager` and `administration` remain failures there. Because this holdout was opened before C2 design, that number is development evidence only. The independent capability sentinel is excluded-title ranks 21–50: **30 unseen high-volume rows / 7.21M searches**, with **100% Any-parent Hit@5**, **93.220% volume-weighted typed-parent Recall@5**, and no regression on the frozen 333-case source-truth suite.

Decision: planned C is complete enough for v0 research. Do not add a special residual rule, D/ESCO, embeddings or more source engineering yet. First build and adjudicate a fresh next-volume natural-language holdout with C2 outputs hidden, then evaluate the frozen C2 configuration unchanged.

Evidence: `docs/findings/c2-job-title-router-v31.md` and `research/evaluation/v31/c2-job-title-router.json`.


Independent C2 validation: a second natural-language holdout was selected from previously unseen unbound observed-query ranks **51–80** (**30 cases / 138.1M searches**). Its taxonomy-only judgments were frozen before C2 was run. Frozen C2 then achieved **100% Discovery Success@5**, **100% volume-weighted Discovery Success@5**, **100% positive-intent Discovery@5 (5/5)** and **100% NO_MATCH abstention (25/25)** while preserving the 333-case source-truth suite at 100%. None of the five positive cases required the job-title route; C1 itself surfaced a judged-positive occupation.

Interpretation: this is strong independent evidence for the simple occupation configuration but not a claim of universal 100% relevance—the holdout contains only five positive occupation queries and is dominated by geography/other intent. Crucially, it produces **no measured occupation residual that can justify more retrieval complexity**. D/ESCO, vectors and synthetic enrichment therefore remain deferred. The next evidence gap moves to the other generic target space: natural-language **skill** discovery.

Evidence: `docs/findings/c2-fresh-natural-holdout-v31.md`, `research/benchmark/v31/fresh-natural-holdout/` and `research/evaluation/v31/c2-fresh-natural-holdout.json`.

Current-selector lexical-gap audit (Track 1): a corrected source-attested replay of the current v31 YV/KV selectors shows that ordinary known-term lookup is already strong in YV but has a cheap canonical-vocabulary residual in KV. After excluding ambiguous alias surfaces and aliases colliding with current preferred labels, YV has **357** strict current canonical alias cases: **318** already hit@5 and **39** deterministic exact-alias rescues. KV has **1,279** strict cases: **1,056** already hit@5 (**82.565%**) and **223** deterministic rescues. An exact normalized current `alternative_labels`/`hidden_labels` lane before fuzzy therefore closes this measured slice to 100% without semantic retrieval. `replaced_by` history remains migration/routing evidence and is not promoted to synonymy; ambiguous surfaces fail closed. The product implementation on `fix/canonical-alias-search` passes the full quality/build/package chain on self-hosted `garderob`, including all versioned data-package builds. GitHub PR #38 is a draft verification surface only and must not be merged; YV/KV `main` remains governed by the protected GitLab branch and its sync process.

Evidence: `docs/findings/track1-canonical-alias-reachability-v31.md` and `research/evaluation/v31/track1-canonical-alias-rescue.json`.

Skill independent validation: the first source-attested natural-description skill benchmark exposed a real gap that canonical C0 does not solve. On a separately frozen **35-case blind holdout**, KV-C0 reaches **31.429% Discovery Hit@5 (34.734% occurrence-proxy weighted)**. The only surviving minimal development candidate, `KV-F1-close-one-slot`, does **not** improve unweighted Hit@5 and falls to **31.955% weighted**. The 617-case canonical regression remains 100%.

The pinned current KV product was then replayed on **the same 35 frozen descriptions** using `kingkong-projek/yrkesvaljaren@0eba98e3`, Fuse.js 7.5.0 and the exact no-context `HybridSearchEngine.search(query, '', [], 5)` path. It returns **no result for 35/35 cases: 0.000% Discovery@5**. KV-C0 therefore provides **11 semantic rescues**, an incremental **+31.429 percentage points Discovery@5** and **+34.734 points occurrence-proxy weighted** over the actual product baseline. All 35 cases are fallback-eligible relative to current KV.

Decision: description fallback has now demonstrated material incremental product capability. Keep deterministic KV-C0 as the minimum semantic baseline and keep F1 rejected. The remaining 24 misses are an opened development residual, not future independent validation. Next build the separate provenance-tagged synthetic-query stress suite for first-person/task/tool/method language, use it only to nominate the smallest next capability, and validate any promoted capability on a new unopened source-attested holdout.

Evidence: `docs/findings/skill-fresh-holdout-v31.md`, `docs/findings/skill-fallback-increment-v31.md`, `research/benchmark/v31/training-skill-fresh-holdout/`, `research/evaluation/v31/skill-fresh-holdout.json`, and the reproducible pinned-product workflow `.github/workflows/pinned-kv-description-baseline.yml`.

- [x] preliminary **A/B/C0** source-truth lexical ablation on P80 core, where C0 = preferred labels + real canonical definitions + canonical alternative labels
- [x] **C1:** P80 + six measured high-volume boundary occupations + short-query lexical surface/component/fuzzy evidence + conservative definition-only abstention; 100% on the 34-row development slice, 100% on the frozen 333-case source-truth regression, and **83.173% volume-weighted decision accuracy on untouched 36-row holdout** vs C0 59.765%
- [x] **complete planned C retrieval vocabulary:** C2 adds exact active job-title preferred-label → typed occupation-name parent routing, with job-title retained as retrieval vocabulary only. On the already-opened 36-case holdout C2 reaches **93.677% volume-weighted Discovery Success@5** with 100% NO_MATCH abstention. On a new unseen excluded-title ranks 21–50 sentinel it achieves **100% volume-weighted Any-parent Hit@5** and **93.220% volume-weighted typed-parent Recall@5**; the 333-case source-truth regression remains 100%.
- [x] validate frozen C2 on a **fresh blinded natural-language next-volume holdout**: unbound query ranks 51–80 were adjudicated and frozen before C2 output existed; **30 cases / 138.1M searches**, with **100% volume-weighted Discovery Success@5**, **100% positive-intent Discovery@5 (5/5)**, **100% NO_MATCH abstention (25/25)** and no 333-case source-truth regression
- [x] **natural-language skill discovery source-attested validation:** 76 development cases plus a separately frozen **35-case blind holdout** from AF manual learning-outcome→skill mappings; on the blind holdout KV-C0 reaches **31.429% Discovery@5 / 34.734% weighted**, while preselected `KV-F1-close-one-slot` fails to generalize (**31.429% / 31.955% weighted**) and is rejected; canonical 617-case regression remains 100%
- [x] measure the pinned **current KV selector** on the same blind 35-case description holdout: current KV returns **0/35** results / **0.000% Discovery@5**; KV-C0 rescues **11/35 = 31.429%**, giving **+31.429pp** incremental Discovery@5 (**+34.734pp occurrence-proxy weighted**)
- [ ] add a separate **synthetic-query description stress suite** for YV and KV (`synthetic_query` provenance; task/tool/method/first-person phrasing; no retrieval ingestion and no traffic weighting)
- [ ] D typed graph/ESCO remains deferred: the fresh YV holdout exposes no occupation residual that justifies it; add D only if a later occupation or skill benchmark demonstrates material value
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
