# YV generator-excluded title ranking — taxonomy v31

## Question

Do the 205 active job titles intentionally excluded by the YV generator represent a broad ordinary-search failure, and should exact excluded-title queries be routed parent-first?

## Sources and product contract

- YV selector commit: `1ad8c389a4f43caa5a704843487ca94419bf745a`
- Search-utils blob: `1eb706399ff97634b556164061e651a024b98003`
- Fuse.js: `7.5.0`
- Published YV SHA-256: `1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49`
- Pinned YV generator: `6dd9e4737d7db3cb2709f8082808b88e5c89ed6e`
- Query corpus SHA-256: `01a2550473091b06fdaaf450015eeea13b301471f1c78f5fb0dc8d3499645ae2`
- Corrected self-hosted run: `34055609446`
- Artifact: `9995858597`, ZIP SHA-256 `ac5bd1d8c014e7ebf43a4c3759d8d22bc31e0352a059008dc66785f3be0b5242`

The complete population is rebuilt from the generator's own two diagnostics: 101 `redundant_label` + 104 `too_many_parents` = 205 titles. Exact-query counts come from the same frozen Platsbanken query corpus used by the current-selector audit.

## Result

The 205 titles account for **349,760,282** observed exact queries in the retained corpus.

Under reproduced current YV product search:

- A generator-mapped occupation route is visible at rank 1 for **56.585%** of cases and within top 5 for **68.780%** of cases.
- Volume-weighted, the same figures are **85.162% at rank 1**, **97.924% within top 3**, and **98.863% within top 5**.
- **64/205** titles have no generator-mapped occupation visible in the returned product result.

That combination matters: the residual is broad by title count but small by observed traffic. It is a long-tail failure population, not evidence that ordinary YV search is generally broken.

### `redundant_label`

This class is essentially already routed by ordinary search:

- 101 titles, 265,510,870 observed exact queries.
- **99.780%** of volume has a mapped occupation at rank 1.
- **99.999%** has one within top 5.
- Only **1/101** cases has no mapped occupation visible.

A generic new routing layer is not justified for this class.

### `too_many_parents`

This class is structurally different:

- 104 titles, 84,249,412 observed exact queries.
- Only **22.115%** of cases have a mapped parent at rank 1 and **39.423%** within top 5.
- But volume-weighted coverage is **39.094% at rank 1**, **91.383% within top 3**, and **95.280% within top 5**.
- **63/104** cases have no mapped parent visible.

Thus a small number of very frequent broad terms are already served reasonably, while many low-volume titles remain unresolved.

## What happened to the apparent `Säljare` ranking defect?

The earlier four-query persona probe made `Säljare` look like a strong prefix-ranking defect. The population-level replay changes that conclusion.

`Säljare` has 41,047,237 observed exact queries and 25 generator-mapped parents. Current results begin with `Säljare hyrmaskiner`, but a mapped route is already at rank 2 through `Säljare, mat`, followed by mapped occupation rows at ranks 3–5. This is better classified as **variant overload / structural ambiguity** than missing findability.

`Jurist` is similar: 38 mapped parents and the first mapped route at rank 4. Parent-first ordering would make the list look cleaner, but it would not determine which legal profession the user intended.

Across all 205 cases, only **7** have a non-target direct prefix result before the first mapped route. Those cases represent 12.851% of excluded-title query volume because a few terms are extremely frequent. This is not enough to infer a general prefix-scoring defect.

## Real residual candidates

The high-volume cases where current product search exposes no generator-mapped route are more useful Track-1 targets. Examples include:

- `Grundskollärare` — 1,628,450 observed exact queries.
- `Slöjdlärare` — 787,437.
- `Samtalsterapeut` — 331,270.
- `Anläggningsmaskinförare` — 287,983.
- `Lärare historia` — 275,648.
- `Teacher` — 237,289.

These should be inspected individually for admission, canonical vocabulary, typo/variant normalization, or a narrowly grounded routing rule. They should not be sent to Track 2 merely because the current fuzzy result is wrong.

## Parent-recall caveat

The corrected metric counts **distinct generator-mapped occupation identities**. It does not double-count multiple YV rows that happen to route to the same parent.

Current micro distinct-parent recall is 22.508% at top 5 overall and only 10.204% for `too_many_parents`. That is not itself a defect: a title mapped to 25 or 38 occupations cannot sensibly expose every possible interpretation in a small dropdown. The product objective is useful routing and disambiguation, not exhaustive parent enumeration.

## Counterfactual

A diagnostic counterfactual placed all already-known generator parents first for an exact excluded-title query. It necessarily gives a mapped parent at rank 1 for 100% of cases and raises distinct-parent recall.

This is a ceiling, not a production recommendation. It manufactures visibility by construction but does not resolve user intent. A global parent-first rule is therefore **not adopted from this evidence**.

## Decision

Do **not** add a general excluded-title parent-first patch now.

The current product already exposes at least one generator-grounded route within top 5 for **98.863% of observed excluded-title exact-query volume**. The remaining material work is narrower:

1. review the highest-volume no-parent residuals individually;
2. keep ordinary YV/KV fixes separate from description/semantic fallback;
3. verify/fix YV → KV occupation-context handoff in an actual job-title integration path;
4. freeze the compact Track-1 failure-mode map and classify any remaining material failures before Track 2 resumes.
