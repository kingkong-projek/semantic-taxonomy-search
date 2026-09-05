# Yrkesinformation legacy → taxonomy v31 join decision

**Status:** measured; Gate-1 join decision closed  
**Measured:** 2026-09-06  
**Workflow run:** `33995395508`  
**Artifact:** `occupational-information-v31` (`9977890222`)

`Yrkesinformation interimslösning` contains 324 legacy Hitta yrken records. All 324 are text-rich, but the record identity cannot be assumed to equal a v31 `occupation-name` merely because labels match.

## Measured joinability

- source records: **324**
- exactly one explicit active v31 `occupation-name` ID embedded in the record: **85**
- multiple explicit active v31 occupation IDs: **34**
- no explicit active v31 occupation ID: **205**
- unique exact preferred-label candidate: 171
- unique exact any-taxonomy-label candidate: 178
- no exact taxonomy-label candidate: 146

The explicit IDs occur in source fields such as `occupational_groups[].taxonomy_id` and `occupational_titles[].taxonomy_id`. Some legacy records deliberately contain several active occupation identities, so choosing one by label would collapse source semantics.

## Gate-1 decision

Canonical attachment of Yrkesinformation semantic text is permitted only for the **85 records with exactly one explicit active v31 occupation-name ID**.

The remaining **239 records** fail closed for canonical attachment:

- 34 require disambiguation because the source itself exposes multiple active occupation identities;
- 205 have no explicit active occupation identity.

Exact label equality remains useful retrieval/join-candidate evidence but is not an authority key. We do not manufacture a canonical mapping for those 239 records.

This resolves the Gate-1 question without requiring a speculative legacy-ID/slug mapping. Future evidence may enlarge the safe subset, but it must provide an independent canonical key or equivalent authoritative mapping.

Machine-readable frozen aggregate: `research/coverage/v31/occupational-information-aggregate.json`.
