# Common relation coverage — v31

**Status:** measured  
**Measured:** 2026-09-04  
**Taxonomy version:** 31  
**Immutable source:** `concepts-and-common-relations.json`  
**Source SHA-256:** `634fd9d848a172747e54e3e487160a912ae6c0fcb8219c50998767c8c9aacbcc`  
**Workflow run:** `33861288432`

## Source integrity

The version-specific distribution URL resolves successfully for v31 and contains:

- **43,695 concepts**
- **43,695 unique IDs**
- 2,105 `occupation-name`
- 6,752 `skill`
- 9,785 `job-title`
- 1,484 `keyword`

These target counts exactly match the independently paged v31 REST extraction.

The file is therefore the preferred reproducible backbone for the common graph relations it publishes.

## Occupation-name relation coverage

| Relation | Target | Concepts with ≥1 | Coverage | Edges |
|---|---|---:|---:|---:|
| `related` | `job-title` | 1,583 | 75.2% | 11,198 |
| `related` | `keyword` | 130 | 6.2% | 151 |
| `broader` | `ssyk-level-4` | 2,105 | 100.0% | 2,105 |
| `broader` | `isco-level-4` | 2,105 | 100.0% | 2,107 |
| `exact_match` | `esco-occupation` | 982 | 46.7% | 1,177 |
| `broad_match` | `esco-occupation` | 595 | 28.3% | 616 |
| `narrow_match` | `esco-occupation` | 487 | 23.1% | 1,404 |
| `close_match` | `esco-occupation` | 553 | 26.3% | 626 |
| `substituted_by` | `occupation-name` | 993 | 47.2% | 4,394 |
| `substitutes` | `occupation-name` | 968 | 46.0% | 4,394 |

### Interpretation

The job-title graph is already a large semantic language-expansion asset: three quarters of occupation-name concepts have at least one linked job title and the graph contains 11,198 occupation↔job-title edges.

Keywords are much sparser as direct occupation-name expansion in this common snapshot. That does not imply that the separate search-concept distribution is unimportant; it means it needs to be inventoried as its own source rather than assumed to be equivalent to the common `keyword` edges.

Every active occupation-name has exactly one SSYK4 broader edge. Every occupation-name also has at least one ISCO4 broader edge; two extra ISCO edges exist because two concepts have multiple such parents.

ESCO coverage is substantial but heterogeneous. The four mapping relations overlap and **must not be summed into synonym coverage**. An occupation can have several relation kinds and several targets.

## Skill relation coverage

| Relation | Target | Concepts with ≥1 | Coverage | Edges |
|---|---|---:|---:|---:|
| `broader` | `skill-headline` | 6,752 | 100.0% | 6,752 |
| `related` | `ssyk-level-4` | 6,734 | 99.7% | 17,884 |
| `exact_match` | `esco-skill` | 1,251 | 18.5% | 1,363 |
| `broad_match` | `esco-skill` | 4,017 | 59.5% | 4,913 |
| `narrow_match` | `esco-skill` | 2,495 | 37.0% | 11,302 |
| `close_match` | `esco-skill` | 1,283 | 19.0% | 2,211 |

### Interpretation

The native skill text is sparse — only 24.5% had a definition distinct from its label — but the skill graph is **not** sparse:

- all skills have a skill-headline parent;
- 99.7% have at least one SSYK4 relation;
- ESCO mapping is extensive, particularly `broad_match` and `narrow_match`.

Therefore skill semantic retrieval should be graph/context-first rather than attempting to compensate immediately with generated descriptions.

The 18 skills without an SSYK4 relation should be inspected. Documentation notes that some cross-occupational skills are intentionally not connected to SSYK4, so absence is not automatically a data defect.

## Job-title relation coverage

All **9,785 / 9,785 (100%)** active job titles have at least one `related → occupation-name` relation, with **11,198 edges** total.

This directly confirms the product-relevant distinction:

- a job title is its own canonical concept;
- it can point to one or several occupation names;
- the title's own description is almost always just its label;
- its semantic power comes from the title wording plus its curated relation(s).

This is especially important for ambiguous titles: the semantic matcher may use the user's description to rank the linked occupations, but must not collapse the linked canonical identities.

## Keyword relation coverage

Within the common-relation snapshot:

- 34 / 1,484 keywords have `related → occupation-name`, 151 edges;
- 5 / 1,484 have `related → skill`, 8 edges.

The source distribution reports `related` on 1,483 keywords overall, so most keyword relations target **other concept types**. This reinforces the need to inventory the entire typed relation matrix and the separate search-concept dataset instead of treating `keyword` as an occupation synonym list.

## Unresolved relation targets resolved conceptually

The first aggregate reported **2,122 unique relation target IDs** that were absent from the active v31 snapshot. A second analysis of the per-concept relation matrix showed that these unresolved targets occur **only on `replaces` edges**:

- occupation-name: 2,443 `replaces` edges from 966 active concepts
- skill: 79 edges from 56 active concepts
- job-title: 37 edges from 30 active concepts

This is consistent with active concepts pointing backward to concepts that are no longer part of the default active snapshot. It does **not** contaminate the measured job-title, keyword, SSYK or ESCO coverage above.

When deprecated concepts are inventoried later, replacement-history coverage should be measured separately from the active retrieval corpus.

## What this distribution does not contain

The published field list does not include the newer/special `essential` and `optional` occupation→skill relations described by the taxonomy documentation. Those remain **unknown**, not zero.

They require a separate typed adapter/API extraction.

Likewise, the following are not answered by this common graph pass:

- Yrkesväljaren behavioural weights
- Relevanta kompetenser derived edges
- Kompetensväljaren weights/context
- curated släktskap dataset as its own source
- Yrkesinformation coverage
- historical/current ad corpus coverage
- JobSearch Trends/query-language coverage

Semantic Coverage Inventory Gate 1 remains open until these source-specific dimensions have been joined per canonical ID or explicitly scoped out with evidence.
