# Native taxonomy text coverage — v31

**Status:** measured  
**Measured:** 2026-09-04  
**Taxonomy version:** 31  
**Extractor:** `scripts/semantic_coverage_inventory.py` at commit `422e0ae77e5476424ca1efcbb15f94bb8da88316`  
**Workflow run:** `33860719240`

## Executive finding

The v31 data materially changes the starting assumption.

A non-empty `definition` field is **not** useful as a coverage metric because the API fills it for all measured concepts. The useful first distinction is whether the normalized definition is different from the preferred label.

| Type | Concepts | Definition distinct from preferred label | Label-copy definition | Alternative labels | Hidden labels |
|---|---:|---:|---:|---:|---:|
| `occupation-name` | 2,105 | 1,636 (77.7%) | 469 (22.3%) | 197 (9.4%) | 0 |
| `skill` | 6,752 | 1,654 (24.5%) | 5,098 (75.5%) | 819 (12.1%) | 7 (0.1%) |
| `job-title` | 9,785 | 6 (0.1%) | 9,779 (99.9%) | 0 | 0 |
| `keyword` | 1,484 | 0 | 1,484 (100%) | 1 (0.1%) | 0 |

### Immediate implications

1. **Occupation-name descriptions are already a major semantic asset.** Roughly three quarters of current v31 occupation names have definition text that is not merely the label.
2. **Job titles are primarily vocabulary/graph evidence, not descriptive documents.** Almost every job-title definition is just its label.
3. **Native skills are text-sparse relative to occupations.** Only about one quarter have distinct definition text, so skill retrieval will need much more help from graph/context/ESCO/derived datasets than occupation-name retrieval.
4. **Keywords are routing/search language, not descriptive documents.** Their value is primarily in their relations to other concepts.
5. A single representation strategy for all concept types would waste information in `occupation-name` and fabricate information for `job-title`/`keyword`.

## Occupation-name

- Total active concepts returned by the v31 REST query: **2,105**.
- Non-empty `definition`: **2,105 / 2,105 (100%)**.
- Definition distinct from preferred label: **1,636 / 2,105 (77.7%)**.
- Definition equal to preferred label: **469 / 2,105 (22.3%)**.
- At least one alternative label: **197 / 2,105 (9.4%)**.
- Hidden labels: **0**.
- `quality-level` present in REST output: **1,717 / 2,105 (81.6%)**.
  - level 1: 767
  - level 2: 197
  - level 3: 753

The user-provided example `Kammarrättspresident` (`xbZT_DjD_aWc`) is in the rich-definition group: 594 characters, distinct from the label, quality level 3.

### Documentation drift

The current occupation-name documentation says that most occupation-name concepts lack definitions and that the definition is generally populated with the preferred label. The v31 measurement shows the opposite for the currently returned active concept set: **77.7% have distinct definition text**.

Treat the measured immutable v31 snapshot as the authority for coverage statistics, while retaining the documentation as evidence about intended semantics/governance. This mismatch is itself a research finding and should be rechecked in future versions.

## Skill

- Total: **6,752**.
- Non-empty `definition`: **6,752 (100%)**.
- Distinct definition: **1,654 (24.5%)**.
- Label-copy definition: **5,098 (75.5%)**.
- At least one alternative label: **819 (12.1%)**.
- Hidden labels: **7 (0.1%)**.
- `quality-level` appears in REST output for **611 (9.0%)**:
  - level 1: 308
  - level 2: 80
  - level 3: 223

The skill documentation itself warns that native skills are vaguely defined and structurally heterogeneous: a skill may represent a qualification, technology, software, licence/certificate or other prerequisite. That heterogeneity must become an explicit evaluation stratum rather than being hidden inside one generic `skill` benchmark.

## Job-title

- Total: **9,785**.
- Distinct definition: **6 (0.1%)**.
- Label-copy definition: **9,779 (99.9%)**.
- Alternative labels: **0**.
- Hidden labels: **0**.
- `quality-level` appears in REST output for **148 (1.5%)**.

The six distinct-definition rows need manual inspection. At least some are normalization/correction cases rather than genuine rich descriptions (for example `Chief operating office` → definition `Chief operating officer`). Therefore even **6** is an upper bound on genuinely descriptive job-title coverage.

Job-title documentation says these are deliberately independent concepts, usually more specific than occupation names, manually linked through `related`, and often sourced from the synonym dictionary used by JobAd Enrichments. That makes their relation edges potentially very valuable for semantic recall even though their own text is nearly empty.

## Keyword

- Total: **1,484**.
- Distinct definitions: **0**.
- Label-copy definitions: **1,484 (100%)**.
- Alternative labels: **1**.
- Hidden labels: **0**.
- `quality-level` appears in REST output for **2**.

Keyword value therefore depends almost entirely on the language itself and its typed relations to other concepts.

## Unexpected `quality-level` finding

The current occupation-name documentation says `quality-level` is unique to occupation-name. The v31 REST response nevertheless contains `taxonomy/quality-level` for:

- 1,717 occupation names
- 611 skills
- 148 job titles
- 2 keywords

This is a **documentation/data mismatch**, not something to explain away. Before using `quality-level` as a retrieval feature, we must determine whether:

1. the field has recently expanded to other concept types and documentation is stale;
2. it is inherited/copied through an editorial migration;
3. the REST representation has semantics not captured by the conceptual documentation.

Until resolved, `quality-level` is recorded as observed metadata but is **not** used as an authority/ranking feature outside occupation-name.

## Extraction failure that must not be mistaken for zero coverage

The first GraphQL relation extraction returned HTTP 400 for every type. Therefore all relation counts printed as zero by that first script run are invalid and **must not be interpreted as measured zero coverage**.

Root cause identified after the run: the generated GraphQL query serialized `version` as a string (`"31"`) although the GraphQL schema expects an integer (`31`). The relation extraction is being replaced/fixed. In addition, common relations will preferentially be read from Arbetsförmedlingen's stable, versioned `concepts-and-common-relations` distribution so the inventory is reproducible without many live graph queries.

## Method

For each concept returned by:

`GET /v1/taxonomy/main/concepts?type=<TYPE>&version=31`

we normalized whitespace and case and classified:

```text
definition_nonempty
definition_distinct_from_label
definition_same_as_label
definition_chars
alternative_label_count
hidden_label_count
quality_level_present
```

The API was paged and de-duplicated by canonical concept ID.

This inventory currently covers the active concepts returned by the endpoint. A separate deprecated-concept inventory may be useful for search compatibility/migrations, but should not be mixed into the primary active search corpus without an explicit policy.

## Next measured layer

The next native-taxonomy pass must add typed relation coverage for every concept, especially:

- `job-title` ↔ `occupation-name`
- `keyword` ↔ target concepts
- occupation-name → SSYK4
- skill → SSYK4 / skill hierarchy
- occupation-name ↔ skill (`essential` / `optional` where present)
- occupation/skill ↔ ESCO split by `exact`, `broad`, `narrow`, `close`
- substitutability/curated occupation relations

After that, external AF datasets are joined per canonical ID as separate provenance-bearing adapters. This document does **not** mark Semantic Coverage Inventory Gate 1 complete.
