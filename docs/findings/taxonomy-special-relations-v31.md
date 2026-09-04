# Taxonomy special relation coverage — v31

**Status:** measured  
**Measured:** 2026-09-04  
**Extractor:** `scripts/taxonomy_special_relations_coverage.py`  
**Accepted workflow run:** `33864929163`

This finding measures two versioned taxonomy distributions that were previously only hypotheses in the semantic-search plan.

## 1. `keyword` is mostly not YV/KV search vocabulary

Source:

`https://data.jobtechdev.se/taxonomy/version/31/query/keyword-concepts-with-relations/keyword-concepts-with-relations.json`

SHA-256: `91bb2d3649f6cf061475b64c63966d0a9818ca012e9d040ea054626229189c85`

All **1,484 / 1,484** active keyword concepts are present. Their related edges are distributed as:

| Target type | edges | source keywords |
|---|---:|---:|
| `sun-education-field-4` | **1,443** | 1,443 |
| `occupation-name` | 151 | 34 |
| `employment-type` | 9 | 8 |
| `skill` | 8 | 5 |
| `job-title` | 0 | 0 |

For the two product destination spaces this means:

- only **34 / 1,484 = 2.291%** of keyword concepts point to occupations;
- those reach **130 / 2,105 = 6.176%** of active occupation-name concepts;
- only **5 / 1,484 = 0.337%** point to skills;
- those reach **7 / 6,752 = 0.104%** of active skills;
- none point directly to job-title.

No unknown keyword IDs or relation targets were observed.

### Consequence

The earlier working assumption that the dedicated keyword/search-concept dataset might be a rich synonym/search-language layer for YV/KV was wrong.

For these products it is a **small, typed supplemental recall source**, not a central semantic corpus. Most of the keyword vocabulary serves education-field relations.

The direct occupation/skill edges are still useful, but they should be evaluated as curated relation evidence and should not be called synonyms without source semantics supporting that claim.

## 2. Curated occupation substitutability adds a real 25/75 signal

Source:

`https://data.jobtechdev.se/taxonomy/version/31/query/substitutability-relations-between-occupations/substitutability-relations-between-occupations.json`

SHA-256: `8761f938505ab9f276b8054d235c9a574bf2da1ff56c3761d9ce836f6fc93c60`

All **2,105 / 2,105** active occupation-name concepts are represented.

| Relation field | sources non-empty | source coverage | directed edges | 25% | 75% |
|---|---:|---:|---:|---:|---:|
| `substituted_by` | 993 | 47.173% | 4,394 | 1,977 | 2,417 |
| `substitutes` | 968 | 45.986% | 4,394 | 1,977 | 2,417 |

All 4,394 `substitutes` edges match the reverse direction of the 4,394 `substituted_by` edges with the same percentage. No invalid source/target IDs or wrong relation types were found.

This dedicated distribution therefore adds something important beyond the common graph: **the curated substitutability percentage**.

### Retrieval consequence

The 25/75 signal is promising for:

- YV candidate expansion;
- hard-negative selection;
- semantic neighbourhood/context;
- broad-query diversification;
- benchmark construction around close-but-not-identical occupations.

But it must retain source semantics:

- direction is explicit;
- 25 and 75 remain distinct;
- neither means canonical equivalence;
- neither automatically means suitable career transition;
- it should not silently override exact lexical identity.

## 3. Plan correction

Gate 1 can now mark both sources measured.

The keyword source should be **deprioritised** relative to definitions, YV/KV read models, Relevanta kompetenser and real ad language because its direct YV/KV coverage is tiny.

Substitutability should stay as a meaningful YV graph/evaluation feature because it adds typed expert-curated strength unavailable in the ordinary common-relation ID lists.
