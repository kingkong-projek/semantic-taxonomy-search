# Current YV/KV product failure-mode audit — taxonomy v31

**Status:** measured / code-audited

**Pinned YV generator:** `6dd9e4737d7db3cb2709f8082808b88e5c89ed6e`

**Pinned YV/KV frontend:** `0eba98e3a91079a43c1eaf6da09dfabe11e5bc8b`

## Why this audit exists

Real users report that they sometimes cannot find the occupation or competence they need in YV/KV. Before adding semantic complexity, the first question must therefore be which failure modes already exist in the ordinary selectors and which of them can be fixed with data/logic the products already own.

This audit corrects an earlier over-broad interpretation of YV's excluded-title and multi-context populations. It evaluates the published v31 data, pinned generator, pinned frontend source and observed YV query-frequency corpus together.

## YV: multi-context job titles are not broken in ordinary dropdown search

Published YV contains **541 job-title IDs in multiple occupation-name contexts**, represented by **1,186 selectable context rows**. For an exact preferred-label query, the current deterministic direct lane exposes **all intended contexts within top 10 for 541/541 titles**. The measured exact-query population is **35,949,704 searches**, and all of that volume belongs to cases whose ordinary dropdown contains every intended context.

Therefore the parenthesis/disambiguation model itself is not the primary YV retrieval defect. The ordinary path works when the user types the exact title and explicitly chooses a displayed context row.

## YV: context can still collapse outside the explicit dropdown choice

The frontend has three separate context-preservation hazards:

1. `findExactMatch()` is used on blur/free-text confirmation and resolves with `taxonomyData.find(...)`. It accepts either the full display label or the bare preferred label. For a bare exact label shared by multiple context rows, this chooses the first row without an explicit context choice. The **541 multi-context IDs / 35.95M exact-query volume** are an *exposed population*, not a measured failure count because no event log tells us how often users blur/tab instead of clicking a row.
2. Programmatic `setSelection()` validates rich job-title input but then resolves taxonomy data by job-title ID only. Of the 1,186 multi-context rows, **645 are non-first contextual rows** that can collapse to another parent on such a roundtrip.
3. Standard form serialization writes only the job-title ID. It therefore cannot encode the chosen occupation parent for any of the **1,186 multi-context rows**. Multi-select duplicate handling also compares job-title ID first, so two contexts of the same title cannot coexist.

These are product identity/interaction issues, not reasons to add embeddings.

## YV: 11.153% excluded-title query volume is not an 11% product failure rate

Generator policy excludes 205 active job titles: 104 with more than three mapped occupation parents and 101 redundant-label titles. The observed corpus contains **349,760,282 exact searches** for 141 of those labels, or **11.153%** of all retained query volume.

Replaying the current deterministic direct YV lane changes the interpretation materially:

- relevant mapped occupation in direct top 10 for **100/101 redundant-label titles**;
- relevant mapped occupation in direct top 10 for **8/104 too-many-parent titles**;
- because those eight include very high-volume broad labels, **336,025,601 / 349,760,282 = 96.073%** of excluded-title exact-query volume already has at least one mapped occupation in direct top 10;
- only **13,734,681 = 3.927%** of excluded-title volume lacks such a deterministic direct route;
- that unresolved direct-lane volume is **0.438% of all retained query volume**.

This is a direct-lane measurement only. Guarded Fuse fallback may rescue additional cases, so 0.438% is not a final product failure rate either.

Highest-volume unresolved examples include `Lastbilsförare` (2,475,234), `Lagermedarbetare` (2,148,491), `Grundskollärare` (1,628,450), `Lastbilschaufför` (1,376,452), `Beteendevetare` (1,376,342), `Idrottslärare` (952,555) and `Slöjdlärare` (787,437).

## Existing canonical vocabulary is underused

Both current products generate candidates primarily from preferred labels.

YV:

- **197** admitted concepts expose canonical alternative-label vocabulary;
- **362** distinct alternative-label surfaces;
- **51** of those surfaces produce no deterministic direct YV result.

KV:

- **819** skills expose alternative labels;
- **1,308** distinct alternative-label surfaces;
- **260** have no canonical contains-match in the current direct label lane;
- **1,654** skills have a canonical definition distinct from the preferred label;
- current KV candidate generation indexes preferred labels/tokens only. Occupation/SSYK context can rank/filter already generated lexical candidates but cannot add missing query vocabulary.

This is the first cheap retrieval surface to evaluate before manufacturing new semantic text.

## YV → KV hand-off has a demonstrated integration footgun

KV accepts `occupation-name` or `ssyk-level-4` IDs as context. A YV `job-title` selection exposes its occupation parent as `selection.related.id`.

The repository's own stepped YV→KV demo instead passes `selection.id` directly to `af-occupation-id`. For a job-title row this is the job-title ID, which KV does not recognise as context, so it falls back to context-free/global behaviour.

This proves the API is easy to integrate incorrectly and the repo demo currently does so for job-title selections. It does **not** prove production consumers make the same mistake; production integration must be inspected separately.

## Product-first decision

Before any further semantic-source expansion, embeddings or synthetic-query-driven model tuning:

1. protect explicit YV context identity across blur/autoselect, programmatic roundtrip and form output where applicable;
2. verify/fix YV→KV occupation-context hand-off with an actual job-title integration test;
3. measure the demand and gain from already-canonical alternative labels in YV/KV;
4. evaluate the remaining high-volume excluded-title direct-route misses with the exact current fuzzy selector before adding a new router;
5. replay real user-reported failures when available and classify them against these failure modes;
6. only then continue description-semantic fallback experiments for cases the ordinary selector still cannot discover.

The separate description fallback remains valuable: current KV still fails genuine long descriptive skill queries in the frozen benchmark. This audit changes **experiment order**, not the long-term fallback use case.

## Reproduction

Frozen compact aggregate: `research/coverage/v31/current-selector-failure-audit.json`

Reproducer: `scripts/audit_current_selector_failure_modes.py`

Workflow: `.github/workflows/current-selector-failure-audit.yml`
