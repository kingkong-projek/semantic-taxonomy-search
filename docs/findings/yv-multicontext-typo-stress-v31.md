# YV multi-context typo stress — taxonomy v31

## Decision

The current guarded fuzzy lane does **not** show a general context-collapse problem for ordinary one-character typos on admitted multi-context job titles. Keep the current architecture unless real-user evidence points to a narrower failure.

This is a structural stress probe, not a demand estimate. The typo strings are deterministic synthetic mutations and must not be interpreted as observed user traffic.

## Population and method

The published v31 YV has **541** job-title IDs represented in more than one occupation context. Exact preferred-label lookup already exposes all intended contexts in direct top 10 for **541/541**.

For titles with an eligible alphabetic token of at least five characters, the probe generated two deterministic single-edit variants:

- delete one internal character near the midpoint of the longest token;
- transpose one adjacent internal character pair near the midpoint of the longest token.

This yielded **538** cases per mutation type, **1,076** total. Each query was replayed through the pinned current YV search behaviour with Fuse.js 7.5.0, preserving contextual identity as `job-title id + occupation-name id`.

## Result

| Stress | cases | any intended context | all intended contexts | intended top 1 | zero results |
|---|---:|---:|---:|---:|---:|
| deletion | 538 | 534 (99.257%) | 533 (99.071%) | 511 (94.981%) | 0 |
| transposition | 538 | 531 (98.699%) | 530 (98.513%) | 507 (94.238%) | 0 |
| combined | 1,076 | 1,065 (98.978%) | **1,063 (98.792%)** | 1,018 (94.610%) | 0 |

Only **13/1,076** cases failed to preserve every intended context; **11/1,076** lost every intended context. Median context recall remained 1.0.

This falsifies the broad hypothesis that a small typo generally destroys YV's multi-context disambiguation. The persona case `projektledre` therefore remains a narrow, position-sensitive counterexample rather than evidence of a systemic failure.

## Residual risk

The rare failures are qualitatively important because the selector can return plausible but unrelated alternatives rather than no result. Examples from this synthetic probe include:

- `Bonde` → `Bode` / `Bnode`: no intended context survives;
- `Chaufför` → `Chafuför`: no intended context survives;
- `Arborrare` → `Arborare`: no intended context survives;
- `Kypare` → `Kyapre`: no intended context survives;
- `Lektör` → `Lekör` / `Letkör`: no intended context survives;
- `Matbud` → `Mabtud`: no intended context survives;
- `Rallare` → `Ralare` / `Ralalre`: no intended context survives.

These cases motivate a later **safe-abstention / misleading-fuzzy** audit if real query evidence shows meaningful demand. They do not justify globally weakening or replacing the current fuzzy lane from this synthetic probe alone.

## Reproduction

Reproducer: `scripts/measure_yv_multicontext_typo_stress.mjs`.

Self-hosted run: `34054618954` on `garderob`.

Artifact: `yv-multicontext-typo-stress-v31`, artifact ID `9995619591`, ZIP SHA-256 `235bef9aab1c0b481ac7732b1180a52eab2c954aa48a7a7035d5cc8a866dab4c`.
