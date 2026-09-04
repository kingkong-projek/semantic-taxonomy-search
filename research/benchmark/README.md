# Judged semantic-search benchmark

This directory is the Gate-2 relevance contract for Yrkesväljaren (YV) and Kompetensväljaren (KV).

The benchmark measures whether retrieval returns the **right product-valid canonical identities**. It must not accidentally turn retrieval vocabulary, search frequency, ad annotations or model outputs into ground truth.

## Case format

Cases are JSONL objects validated by:

- `research/benchmark/schema/benchmark-case.schema.json` — structural contract;
- `scripts/validate_benchmark.py` — cross-field semantic/product invariants;
- `scripts/test_validate_benchmark.py` — negative regression tests for the authority boundaries.

Run locally:

```bash
python scripts/test_validate_benchmark.py
python scripts/validate_benchmark.py research/benchmark/cases/*.jsonl
```

## Destination identity

### YV

A result is either:

```json
{"kind":"occupation-name","concept_id":"..."}
```

or a job title **in an exact occupation context**:

```json
{
  "kind":"job-title",
  "concept_id":"...",
  "occupation_name_id":"..."
}
```

A bare job-title ID is deliberately invalid. The same job-title ID under two occupation-name IDs counts as two distinct benchmark identities.

YV also has a product-admission boundary in addition to canonical taxonomy identity. A scored positive YV case therefore requires explicit `product_admission` evidence from the published YV read model. Canonical identity alone is insufficient.

An active taxonomy job-title excluded by the measured YV generator policy may be query/retrieval evidence but cannot occur in `MUST`, `ACCEPTABLE` or `MUST_NOT` as though it were a selectable YV identity unless the exact identity/context is a published YV row.

### KV

A result is exactly:

```json
{"kind":"skill","concept_id":"..."}
```

Occupation, SSYK, skill-headline and other concept types may provide evidence but are not KV result identities.

## Judgment sets

`MUST` means the identity must occur within `top_k` for the case to satisfy recall.

`ACCEPTABLE` means the identity is relevant/defensible if returned but is not required for success.

`MUST_NOT` is a known confusable or invalid result that must not be promoted as though it answered the query.

The sets are disjoint.

Intent semantics:

- `SINGLE`: exactly one `MUST` identity;
- `AMBIGUOUS`: at least two positive identities across `MUST + ACCEPTABLE`;
- `NO_MATCH`: no positive identities and `allow_abstention=true`.

A broad query is not forced into `AMBIGUOUS` merely because many things are semantically nearby. It is `AMBIGUOUS` only when multiple product identities are genuinely justified by the judgment.

## Query origin is not ground truth

`query_origin` records where the query wording came from:

- `canonical_label`
- `alternative_label`
- `observed_query`
- `ad_text`
- `legacy_label`
- `manual`
- `synthetic`

It says nothing by itself about the correct destination.

Examples:

- a high-frequency observed Platsbanken query is behavioral evidence, not a selected taxonomy ID;
- raw ad text is corpus language, not a canonical synonym declaration;
- a deprecated label is historical retrieval vocabulary, not automatically an active synonym;
- an LLM-generated phrase is synthetic evidence, never benchmark truth merely because it sounds plausible.

## Evidence roles and provenance

Every case has `source_evidence`. Each evidence item has a provenance class and a role.

Allowed destination-ground-truth provenance is deliberately narrow:

```text
canonical
curated_relation
human_judgment
```

The validator rejects the following as destination ground truth:

```text
derived_af
behavioral
corpus_derived
model_derived
synthetic
canonical_history
```

Those sources may still be high-value `query_origin`, `context_only` or `hard_negative` evidence.

`product_admission` is intentionally a different role from destination ground truth. For YV it records that the exact occupation or job-title-in-occupation-context is present in the published YV read model. Its provenance remains `behavioral`, because the YV data also carries search-frequency-derived weighting and generator methodology. The role does **not** turn YV weight into semantic truth.

This separation prevents two opposite errors:

1. accepting any canonical job-title as a YV destination even when YV intentionally excludes it; or
2. promoting YV behavioral weight/admission into canonical concept meaning.

It also prevents circular evaluation such as testing semantic extraction against labels produced by JobAd Enrichments itself.

## Adjudication

`AUTO_HIGH_CONFIDENCE` is restricted to canonical preferred/alternative-label cases whose destination follows from canonical/curated evidence. For YV, the same case must also carry explicit published-YV `product_admission` evidence. It is not a shortcut for auto-labeling observed queries.

`HUMAN_SINGLE` requires at least one reviewer and explicit `human_judgment` ground-truth evidence.

`HUMAN_DOUBLE` requires at least two reviewers and explicit `human_judgment` ground-truth evidence. This is the preferred status for ambiguous, no-match, observed-query, task-description and difficult hard-negative cases.

`PENDING` cases may be accumulated before judgment, but they are excluded from scored benchmark slices.

## Required strata

The schema contains shared strata plus explicit YV/KV risk populations. Important non-average slices include:

### YV

- exact published job titles;
- 541 multi-parent title identities;
- the 205 generator-excluded titles as **routing vocabulary**, split by >3-context and redundant-label causes;
- high-volume observed excluded-title queries;
- unbound observed query language requiring manual judgment;
- task/skill → occupation bridge cases;
- substitutability neighbours as confusables/hard negatives.

### KV

- descriptions without canonical terminology;
- occupation phrase → skill bridge cases;
- ordinary/native vs calculated vs transferable evidence;
- Relevanta-only incremental skill population;
- close/confusable skills.

Shared slices include spelling, compounds, abbreviations, English/international terminology, colloquial language, long descriptions, rare concepts, hard negatives and true no-match cases.

## Benchmark construction policy

1. Start with high-confidence canonical cases and known difficult populations.
2. Sample observed YV query language by frequency **and** long tail; do not only test head queries.
3. Human-judge unbound observed queries rather than auto-labeling from string/vector similarity.
4. Use bounded raw-ad samples with field provenance; do not make a seven-million-ad ETL pipeline a prerequisite.
5. Include deliberately adversarial near-neighbours, not only obvious positives.
6. Keep YV and KV metrics separate even when they share the same retrieval kernel.
7. Freeze a benchmark release before model/retrieval tuning and keep a held-out slice to limit benchmark overfitting.

## Metrics derived from the contract

The contract supports:

- Recall@K over `MUST`;
- ranking metrics over `MUST`/`ACCEPTABLE`;
- `MUST_NOT` violation rate;
- exact-label preservation;
- ambiguous-title context preservation;
- excluded-title routing correctness;
- abstention precision/recall;
- per-stratum metrics and evidence-layer ablations.

Do not reduce this benchmark to one global score. A model that gains average nDCG by collapsing ambiguous job-title identities or confidently mapping no-match queries is a regression.
