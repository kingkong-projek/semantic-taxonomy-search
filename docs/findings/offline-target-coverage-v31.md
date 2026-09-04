# Offline target coverage — taxonomy v31

**Status:** partially measured / artifact-reconstructed  
**Measured:** 2026-09-04  
**Purpose:** recover trustworthy per-target Gate-1 coverage while post-transfer GitHub Actions jobs fail before their first step.

This finding composes four already accepted pre-transfer measurement artifacts without re-fetching source data and without converting aggregate coverage into per-ID facts.

## 1. Source artifacts

| Semantic layer | accepted run | artifact ID | archive SHA-256 |
|---|---:|---:|---|
| native canonical text | `33860719240` | `9932067713` | `610fd64a48ef0fa07ad28c2fb2deba4260ab4bd6a27e950a25c2f8903093c08b` |
| common typed relations | `33861288432` | `9932211469` | `da1d3c2b453107563fd64596939696271d5595400eb7d44333d9aed0d10e1519` |
| YV/KV selector coverage | `33863555154` | `9933045595` | `75ae45406daa9f21d385940d2323106374caf5e0642c843534346c0ea902e7fa` |
| selector residual gaps | `33864077660` | `9933248443` | `441f8a7d7a04b03c0453727e4a1ec59e2ad6d123d3433aa523ea0b7a53dbd29e` |

The accepted underlying source hashes remain:

- taxonomy common snapshot: `634fd9d848a172747e54e3e487160a912ae6c0fcb8219c50998767c8c9aacbcc`;
- YV v31: `1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49`;
- KV v31: `da83f26bf316971caa407364d8feae6f791203bff5758e674cace3d919e4b524`.

## 2. Hard boundary: the old GraphQL zeros remain invalid

The historical `semantic-coverage-v31` artifact contains the useful per-concept REST text profile, but its GraphQL relation extraction failed with HTTP 400 for every target type.

Therefore this reconstruction consumes from that artifact only:

- preferred label;
- definition and whether it differs from the label;
- alternative labels;
- hidden labels;
- quality metadata.

It consumes all relation coverage from the later accepted `common-relations-v31` artifact instead.

The old relation zeros are not used anywhere in this matrix.

## 3. Tri-state semantics

Per-target dimensions are explicitly one of:

```text
KNOWN_TRUE
KNOWN_FALSE
UNKNOWN
```

`UNKNOWN` is required when an accepted historical artifact contains only aggregate coverage rather than the per-ID membership needed for a target row.

In particular, the accepted derived-AF artifact records aggregate coverage for Relevanta kompetenser and ad-derived relevance keywords, but not their complete per-target rows. Those dimensions therefore remain `UNKNOWN` in this offline matrix.

No aggregate percentage is imputed back onto individual concepts.

## 4. YV occupation-name coverage

Universe: **2,105 / 2,105 active occupation-name targets**. Product admission is known true for all of them.

Canonical text:

- **469** have no definition distinct from the preferred label;
- **58** of those 469 still have at least one alternative label;
- therefore **411** are `canonical_text_poor`: no real definition and no alternative label.

The common taxonomy graph changes the interpretation substantially:

- **0** occupation-name targets are `common_graph_retrieval_sparse` under the measured criterion of having none of job-title, keyword, ESCO or substitutability context;
- every occupation-name still has its SSYK4 hierarchy relation.

So a missing/label-copy definition is not equivalent to a semantically isolated YV target.

The remaining unresolved question for these 469 targets is the marginal value of the per-ID derived layers such as employer language and Relevanta/KV context. Those columns remain `UNKNOWN` in this artifact-only reconstruction.

## 5. KV skill coverage

Universe: **6,752 / 6,752 active skill targets**. Product admission is known true for all of them.

Canonical text:

- **5,098** skills have a definition equal to their preferred label;
- **684** of those still have one or more alternative labels;
- therefore **4,414** are `canonical_text_poor`.

Common relation coverage is much richer than the raw definition count suggests:

- only **18** skills have no SSYK4 relation;
- **784** have no ESCO mapping;
- all active skills retain a skill-headline relation in the accepted common graph;
- only **one** skill simultaneously has no real definition, no SSYK4 context and no ESCO mapping.

That single case is:

- `WWM6_QMA_eMc` — **Utlandstjänstgöring, erfarenhet**.

It is not actually context-free: the selector-gap artifact independently establishes that it belongs to KV's typed `transferable_skills` container. This is a useful example of why coverage must remain multi-dimensional rather than being collapsed to “has description / has no description”.

## 6. YV job-title product boundary

Active taxonomy job-title concepts: **9,785**.

Product admission is fully known at concept level:

- **9,580** admitted by YV;
- **205** excluded by the already proven generator policy and therefore retrieval-only vocabulary.

Context identity is a separate issue.

The offline artifact set retains exact YV context IDs for:

- all **541** admitted multi-context job-title IDs;
- **1,186** corresponding selectable `(job-title ID, occupation-name ID)` rows;
- all 205 excluded job-title taxonomy parent sets, totalling **973** retrieval-routing context rows.

For the remaining **9,039 admitted single-context job-title IDs**, this artifact set proves that each has exactly one taxonomy occupation parent but does not retain that parent's ID. Their product admission is known, but their complete YV identity is therefore `UNKNOWN` in the offline matrix.

We do **not** invent those parent IDs from labels or counts.

## 7. Why this result matters

This answers part of the original “how much semantic data do we need per concept?” question.

The answer is clearly not a fixed number of descriptions or generated phrases:

- hundreds of YV occupations have weak canonical text but useful curated graph context;
- thousands of KV skills have weak canonical text but very broad SSYK/ESCO/headline context;
- a title can be excellent retrieval vocabulary while deliberately not being a selectable YV identity;
- sparse text and sparse semantics are different states.

The benchmark should therefore stratify by **which semantic channels are absent**, not by a single text-length or “has description” flag.

## 8. Gate-2 strata enabled now

The artifact reconstruction safely enables sampling of:

### YV

- 411 canonical-text-poor occupation-name targets;
- 469 occupation-name targets with label-copy definitions;
- 541 admitted multi-context job titles with preserved context identities;
- 205 generator-excluded retrieval-only job-title IDs and their 973 taxonomy routing contexts.

### KV

- 4,414 canonical-text-poor skills;
- 18 skills without SSYK4 context;
- 784 skills without ESCO mapping;
- the single `canonical_and_common_context_poor` case;
- the 27 explicitly known transferable skills.

These are diagnostics and benchmark strata, not ranking weights.

## 9. Still UNKNOWN / next work

This is intentionally not called the full Gate-1 matrix yet.

Still unresolved per target:

1. Relevanta kompetenser membership/counts from a regenerated per-ID artifact;
2. ad-derived relevance-keyword counts from a regenerated per-ID artifact;
3. nearby-occupation counts per occupation from a regenerated per-ID artifact;
4. the 9,039 admitted single-context YV job-title parent IDs if source snapshots cannot be re-fetched;
5. safe Yrkesinformation legacy→v31 identity join;
6. deprecated/replacement compatibility measurement.

The first three are known aggregate sources, but aggregate evidence must not be converted into per-ID facts.

## 10. Machine outputs

Committed compact outputs:

- `research/coverage/v31/offline-target-coverage-aggregate.json`;
- `research/coverage/v31/offline-target-coverage-source-manifest.json`.

The large generated JSONL matrices are deliberately not committed. They are reproducible research artifacts, not new source-of-truth datasets.
