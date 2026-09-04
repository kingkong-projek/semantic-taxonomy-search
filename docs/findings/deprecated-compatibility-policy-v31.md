# Deprecated concept compatibility policy — taxonomy v31

**Status:** documented semantic policy; coverage measurement pending  
**Reviewed:** 2026-09-04  
**Target:** active taxonomy v31 retrieval for YV and KV

## 1. Problem

Semantic search should understand old taxonomy wording and IDs without allowing historical concepts to pollute the active result universe.

The taxonomy exposes `deprecated`, `replaced_by` and `replaces` relationships. The public common-relations distribution also publishes `replaced_by` / `replaces` alongside the other typed relations.

These relationships are useful for migration and historical searchability, but **replacement is not the same semantic claim as synonymy**.

Historical Taxonomy documentation explicitly describes cases where a deprecated concept points to a nearby concept that is not exactly the same. Therefore a replacement edge may preserve migration/search continuity while changing scope or meaning.

Sources:

- https://data.jobtechdev.se/dataset/concepts-and-common-relations/
- https://taxonomy.api.jobtechdev.se/v1/taxonomy/graphiql
- https://gitlab.com/arbetsformedlingen/taxonomy-dev/backend/jobtech-taxonomy-api
- https://gitlab.com/arbetsformedlingen/job-ads/jobsearch/jobsearch-apis/-/issues/81

## 2. Separate two concepts that are easy to conflate

### A. Legacy migration routing

A historical concept may tell us where an old ID should be routed in a newer taxonomy version.

```text
old concept ID
  -> replaced_by chain
  -> zero / one / many active targets in v31
```

This is identity/version compatibility.

### B. Semantic equivalence

A query phrase may mean the same thing as an active concept.

This is a retrieval/relevance claim.

`replaced_by` does **not** by itself prove B merely because it supports A.

Hard rule:

> A replacement edge is canonical taxonomy-history evidence, but not canonical synonym evidence.

## 3. Legacy concepts stay outside the active destination universe

Deprecated concepts must never be emitted as active YV/KV result identities.

Instead compile a separate compatibility layer:

```ts
LegacyConceptRoute = {
  legacyConceptId,
  legacyType,
  legacyPreferredLabel,
  legacyAlternativeLabels,
  legacyHiddenLabels,
  replacementTargets,
  resolution,
  chain,
  taxonomyTargetVersion
}
```

Old labels may enter a retrieval-only vocabulary with provenance `canonical_history` / `legacy_retrieval_vocabulary`.

They do not become alternative labels on the active concept object.

## 4. Replacement-chain resolution

Resolve the complete directed `replaced_by` graph against target taxonomy version v31.

Each deprecated source concept must end in exactly one of these states:

```text
UNIQUE_ACTIVE_TARGET
MULTIPLE_ACTIVE_TARGETS
NO_ACTIVE_TARGET
CYCLE_OR_INVALID
TYPE_MISMATCH
```

### `UNIQUE_ACTIVE_TARGET`

Exactly one reachable non-deprecated target of the expected destination-compatible type exists.

This may support deterministic legacy-ID migration routing.

It still does not assert that every historical label is an exact semantic synonym of the target.

### `MULTIPLE_ACTIVE_TARGETS`

The historical concept branches into more than one active target.

Do not choose one automatically. Use the old concept/label as retrieval context, return/disambiguate among product-valid targets, or abstain.

### `NO_ACTIVE_TARGET`

No active replacement can be reached.

Fail closed. Historical wording can remain observable evidence but cannot manufacture a target.

### `CYCLE_OR_INVALID`

The replacement graph cycles, references missing concepts or otherwise cannot be safely resolved.

Fail closed and record an anomaly.

### `TYPE_MISMATCH`

A replacement chain ends in a type that cannot satisfy the requested product target space.

Do not coerce across identity spaces.

## 5. Product-specific admission remains authoritative

Replacement resolution is not the last gate.

### YV

Even if a deprecated `job-title` resolves uniquely to an active `job-title`, that target may be intentionally absent from the published YV destination space.

Therefore:

```text
legacy concept
  -> active taxonomy replacement
  -> YV admission policy
  -> product-valid occupation / job-title-in-context OR disambiguation/abstention
```

A replacement edge cannot bypass the measured YV generator policy.

Likewise, job-title occupation context must remain preserved.

### KV

A deprecated skill may route only to active skill targets for KV.

An occupation, SSYK, skill-headline or another concept type cannot masquerade as the skill result merely because it appears in a historical replacement chain.

## 6. Retrieval use

Deprecated wording is valuable especially for:

- old CV/job-ad terminology;
- users using previous taxonomy labels;
- historical ads/query language;
- migrated stored IDs;
- regression testing across taxonomy releases.

Recommended retrieval evidence type:

```text
LEGACY_LABEL
LEGACY_REPLACEMENT_ROUTE
```

The explanation should remain truthful, for example:

```text
"Äldre taxonomibegrepp som ersatts av …"
```

not:

```text
"Synonym till …"
```

unless independent semantic evidence establishes synonymy.

## 7. Measurement required for Gate 1

For YV/KV-relevant deprecated concepts, measure:

- count by concept type;
- with/without direct `replaced_by`;
- direct replacement target multiplicity;
- complete chain depth;
- `UNIQUE_ACTIVE_TARGET` / `MULTIPLE_ACTIVE_TARGETS` / `NO_ACTIVE_TARGET` / `CYCLE_OR_INVALID` / `TYPE_MISMATCH` counts;
- number of old preferred/alternative/hidden labels available as retrieval-only vocabulary;
- how many resolved active job-title targets are admitted vs excluded by YV v31;
- how many deprecated skills resolve to active KV-valid skills;
- examples/anomalies for every non-unique state.

The measurement must build the graph locally from direct edges rather than trusting recursive API expansion.

## 8. Implementation invariants

When this becomes production code/property tests:

- replacement-chain resolution is deterministic;
- duplicate edges are idempotent;
- input ordering cannot change the result;
- cycles terminate and fail closed;
- missing targets fail closed;
- branching never selects an arbitrary winner;
- type mismatch never crosses the YV/KV destination boundary;
- a deprecated ID is never returned as an active result;
- resolved active job-title still passes YV admission/context rules;
- wrong taxonomy target version fails closed;
- adding an unrelated replacement component cannot change another concept's route;
- explanation provenance cites the exact legacy concept and replacement path used.

## 9. Gate decision

Deprecated compatibility belongs in semantic search, but as a **separate version-migration/retrieval layer**, not by mutating active taxonomy labels or flattening historical concepts into current identity.

This keeps old language searchable while preserving exactly the semantic boundary the feature is intended to strengthen.
