# Unified per-target semantic coverage — taxonomy v31

**Status:** measured; Gate-1 requirement closed  
**Measured:** 2026-09-06  
**Workflow run:** `33995365668`  
**Artifact:** `unified-target-coverage-v31` (`9977882211`)

The full per-target matrix was rebuilt from current hash-verified v31 sources instead of imputing aggregate measurements onto individual IDs.

## Target universe

- YV occupation-name identities: **2,105**
- YV selectable job-title-in-occupation-context rows: **10,225** from **9,580** unique published job-title IDs
- active YV-excluded retrieval-only job titles: **205**
- KV active skill identities: **6,752**

## Diagnostic gap strata

The strata overlap and are benchmark diagnostics, not ranking weights.

| Stratum | targets / context rows |
|---|---:|
| YV occupation canonical text poor | 411 |
| YV occupation no observed ad language | 1,054 |
| YV occupation no skill context | 6 |
| YV sparse occupation context | 263 |
| YV text-poor without observed ad language | **244** |
| multi-parent YV job-title context rows | 1,186 |
| YV job-title rows with no own semantic text | 10,219 |
| KV skill canonical text poor | 4,407 |
| KV skill no YV/KV relevance context | **1,701** |
| KV skill critical sparse | **1,410** |
| KV skill text-poor with derived-only support | 2,945 |
| KV skill without SSYK context | 18 |
| transferable skill | 27 |

The important correction to the earlier offline reconstruction is that Relevanta kompetenser, KV calculated context, ad-derived language and nearby occupations are now known per target. The largest weak strata are therefore measurable rather than `UNKNOWN`.

## Decision

Gate 2 must deliberately oversample the weak and identity-risk strata rather than optimize one global average. In particular: the 244 YV text-poor/no-observed-language occupations, the 1,410 critical-sparse KV skills, the 1,701 skills without YV/KV relevance context, the 541 multi-parent job-title IDs represented by 1,186 selectable context rows, and the 205 excluded-title routing population.

No composite semantic score is emitted. Direct canonical evidence, inherited context and derived AF evidence remain separate with provenance.

Machine-readable frozen aggregate: `research/coverage/v31/unified-target-coverage-aggregate.json`.
