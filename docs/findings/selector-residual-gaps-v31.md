# Selector residual gaps — taxonomy v31

**Status:** measured  
**Measured:** 2026-09-04  
**Extractor:** `scripts/selector_gap_analysis.py`  
**Accepted run:** patched relation parser, commit `9ee0dba01d1ba72d1584259780afaef63cce556e`

This analysis follows the first YV/KV selector inventory and resolves two residual questions without changing product semantics.

## 1. The 205 active job-title concepts absent from YV are mostly longstanding

Published YV v31 contains 9,580 of 9,785 active job-title IDs, leaving **205 active taxonomy job-title concepts absent**.

Cross-version analysis shows:

- new in taxonomy v31: **0**
- already active in taxonomy v30: **205 / 205**
- also absent from published YV v30: **204 / 205**
- present in YV v30 but absent in YV v31: **1 / 205**

Therefore the 205-title gap is overwhelmingly **not taxonomy release lag**. It is a persistent property of the YV production dataset/methodology, with one selector-version regression/change that still needs identification and explanation.

## 2. Missing YV titles are not relation-less

After correcting an initial relation-parser bug, every missing title has at least one active occupation-name relation in the immutable v31 graph.

Occupation-parent count distribution:

| occupation parents | missing job-title concepts |
|---:|---:|
| 1 | 84 |
| 2 | 9 |
| 4 | 46 |
| 5 | 13 |
| 6 | 14 |
| 7 | 5 |
| 8 | 4 |
| 9 | 4 |
| 10 | 3 |
| 11 | 1 |
| 12 | 4 |
| 13 | 1 |
| 15 | 2 |
| 17 | 2 |
| 18 | 9 |
| 19 | 1 |
| 25 | 2 |
| 38 | 1 |

Examples of very broad missing titles:

- `Jurist` → **38** occupation-name parents
- `Sjuksyster` → **25**
- `Säljare` → **25**
- `Specialistsjuksköterska` → **19**
- several generic/specialist physician titles → **18**
- `Sjöman` → **17**
- `Projektledare` → **17**

None of the 205 has a definition distinct from its preferred label.

### Interpretation boundary

Measured fact: many missing YV titles are highly multi-contextual, while 84 have only one occupation parent.

Hypothesis, **not yet established**: YV's persistent exclusion may partly reflect search-history/linkability or ambiguity/filtering rules. The published methodology says concepts are weighted from Platsbanken search history and notes that concepts with no linked search history receive the floor after smoothing, but the exact generator code/policy causing these 204 persistent omissions must be verified before assigning a cause.

Product implication:

> Do not blindly expand the semantic YV candidate universe from the published YV dataset to every active taxonomy job-title. The omitted population should become a dedicated research stratum: some may be useful aliases, some may be too generic or otherwise intentionally excluded.

## 3. KV `transferable_skills` is a real, separate skill vocabulary

`data.transferable_skills` in Kompetensväljaren v31 is a dictionary of **27 labels → 27 active skill taxonomy IDs**.

- active skill IDs referenced: **27**
- already represented in KV's ordinary regulated/essential/optional/calculated union: **14**
- additional active skills contributed only by this container: **13**
- unresolved ID-like values: **0**

Examples include:

- Administrativt arbete, erfarenhet
- Arbetsledarerfarenhet
- Digitala arbetssätt, erfarenhet
- Dokumentation
- Försäljning, erfarenhet
- Hållbarhetskompetens
- Informationssökning
- Kundbemötande och service
- Projektledning, erfarenhet
- Yrkesengelska

This looks semantically like broadly transferable competencies, but **how KV intends this list to be used is still a methodology question**. Its membership alone does not justify a retrieval boost or authority level.

Hard boundary:

> `transferable_skills` remains its own provenance signal. It must not be silently merged into `calculated_skills`, `essential_skills` or another relation class merely because some IDs overlap.

## 4. Why this matters for semantic search

### YV

The 205-title omission population is valuable for:

- hard negatives and ambiguity tests;
- deciding whether semantic search should ever surface active taxonomy titles outside the current YV publication;
- testing abstention/diversification for generic terms such as `Jurist`, `Säljare`, and `Projektledare`;
- checking whether task/context descriptions can safely disambiguate a generic title into the correct YV occupation context.

### KV

The 27 transferable skills add a small but semantically distinctive vocabulary. They should be evaluated as a separate retrieval lane or feature, not absorbed into one generic occupation→skill score.

## 5. Next questions

1. Identify the single job-title that was in YV v30 but not v31 and inspect its taxonomy/search-history changes.
2. Verify generator code/methodology for why 204 long-standing active job-title concepts remain outside YV.
3. Determine the intended semantics and UI role of KV `transferable_skills` from KV methodology/source code.
4. Include the broad missing-title population in Gate 2 rather than assuming all active taxonomy titles are desirable YV semantic outputs.
