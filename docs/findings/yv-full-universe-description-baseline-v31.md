# YV full-universe description baseline — taxonomy v31

**Status:** frozen for human validation  
**Date:** 2026-09-07  
**Structured evidence:** `research/evaluation/v31/yv-full-universe-description-baseline.json`

## Decision

Freeze the minimum occupation-description candidate as:

1. **all 2,105 active v31 `occupation-name` identities**;
2. one deterministic canonical BM25 representation per occupation: preferred label + real canonical definition + canonical alternative labels;
3. the existing exact active `job-title` preferred-label router to typed `occupation-name` parents, preserving its deterministic parent ordering.

Do **not** promote ad-language fusion, Relevanta-kompetenser fusion, RRF, embeddings, neural reranking or generated teacher text yet.

This replaces the old interpretation that C2's 165 occupation identities could be the Track-2 description universe. C2 remains useful historical regression/router evidence, not the full occupation-description candidate.

## Why the universe correction matters

A strict source-attested development diagnostic uses Yrkesinformation `work_task` text only where the record contains exactly one explicit active v31 occupation ID. The evaluation text is never ingested into the candidate, and cases containing the target preferred/alternative label or a related active job-title surface are excluded by normalized token-sequence matching.

That leaves 17 opened development cases:

| candidate | Top1 | Hit@5 | MRR |
|---|---:|---:|---:|
| old C1/C2 description universe, 165 targets | 1/17 (5.9%) | 1/17 (5.9%) | 0.059 |
| full canonical universe, 2,105 targets | 6/17 (35.3%) | 9/17 (52.9%) | 0.419 |

Only 2/17 targets are inside the old 165-target universe. Among the 15 outside it, the old candidate necessarily has 0/15 Hit@5, while the full canonical candidate reaches 8/15 Hit@5. This is direct evidence that candidate-universe exclusion, not merely ranking weakness, caused false description failures.

This 17-case slice is opened development evidence, not independent human accuracy and not representative of the hardest long tail.

## Full-universe regression is clean

The frozen YV source-truth suite contains 333 canonical cases over the 159 P80 occupations:

- 159 preferred-label queries;
- 137 real canonical-definition queries;
- 37 canonical alternative-label queries.

Using the **same** canonical ranker while expanding the candidate universe gives:

| universe | Top1 | Hit@5 | Hit@10 | MRR |
|---|---:|---:|---:|---:|
| P80 159 | 100% | 100% | 100% | 1.0 |
| C2 165 | 100% | 100% | 100% | 1.0 |
| full 2,105 | **100%** | **100%** | **100%** | **1.0** |

There are **zero rank regressions** and zero rank improvements from 165 to 2,105: all 333 expected targets remain rank 1 exactly. Therefore the full-universe correction does not trade away the frozen canonical regression contract.

Workflow: `34118409268`. Artifact: `10017192311`. Frozen benchmark SHA-256: `7bd44757b2eb663e56e2928438caa4789cb0eef064ad01fd3051c9f020de17f9`.

## Exact job-title routing also survives the expansion

The independent C2 capability sentinel consists of the previously unseen excluded-title ranks 21–50: 30 source-attested exact job-title queries covering 7.21M observed searches. Replaying the same typed-parent routing on top of the full 2,105 canonical universe gives:

- route-set drift: **0/30**;
- new foreign exact-canonical collisions ahead of the route: **0/30**;
- Any-parent Hit@5: **100%**;
- volume-weighted Any-parent Hit@5: **100%**;
- mean typed-parent Recall@5: **92.395%**;
- volume-weighted typed-parent Recall@5: **93.220%**;
- all typed parents visible at 5: **80.0%** of rows, **79.049%** volume-weighted.

These are the same routing-quality figures that matter from the C2 sentinel; expanding the canonical candidate universe does not crowd routed parents out of the visible list. The first workflow attempt failed only because the sentinel rebuild omitted the generator `SOURCE_COMMIT.txt` marker; the corrected run rebuilt the frozen sentinel successfully and passed all route-integrity assertions.

Workflow: `34118874430`. Artifact: `10017370535`.

## Real AF evidence is complementary, but fusion is not earned

On the same 17 opened description cases:

- canonical full-universe lane hits 9/17 at 5;
- AF ad-keyword lane hits 5/17 and rescues **4** canonical misses;
- canonical ∪ ad reaches **13/17**;
- Relevanta-kompetenser skill labels + real skill definitions hit 4/17 and rescue **2** canonical misses;
- those two skill-context rescues are new beyond canonical+ad: `Utbildningshandläggare` and `Skorstensfejartekniker`;
- oracle union of the three independent lanes reaches **15/17**.

The remaining two targets are `Arbetsmiljöinspektör` and `Bildpedagog`. Both lack a real canonical occupation definition and canonical alternative labels. Their residuals are therefore at least as plausibly evidence/identity/adjudication problems as proof that a higher model class is needed.

The complementary recall justifies retaining ad language and occupation-linked skill context as first-class **diagnostic evidence lanes**. It does not justify a fusion rule from these already-opened 17 cases.

## Fusion attempts rejected

Three cheap fusion families were tested before considering a higher model class.

### Fixed visible slots

Static five-result allocations displaced canonical rank-4/5 hits. Rejected.

### One concatenated BM25 document

Concatenating canonical + ad + relevant-skill text into one occupation document reaches 11/17 Hit@5, but Top1 falls from canonical 6/17 to 5/17 and the result remains well below the independent-lane oracle union 15/17. Rejected: source evidence remains provenance-separate and one BM25 document does not preserve complementarity.

Workflow: `34117814531`. Artifact: `10016964816`.

### Equal-weight reciprocal-rank fusion

Standard-like equal-weight RRF with `k=60` over canonical + ad + skill lanes reaches only 9/17 Hit@5 and 3/17 Top1. A `k=10` sensitivity run reaches 12/17 Hit@5 but only 2/17 Top1. Because those 17 cases are already opened, `k=10` is not promoted or tuned further.

Workflow: `34118060170`. Artifact: `10017060508`.

## Human gate

The **candidate-construction gate is now cleared** for occupation:

`YV-description-full-v0-canonical-router`

Human collection has **not** started. Before collection, the existing preregistration template must still be replaced by a real frozen preregistration and the existing recruitment/data-handling requirements must be satisfied.

The next decision-bearing occupation evidence is therefore not another retrieval micro-ablation. It is newly frozen, stream-separated human descriptions with blind taxonomy adjudication, followed by rank-sensitive list-quality and abstention evaluation.

Ad language and Relevanta-kompetenser should remain available as candidate next capabilities. They may be promoted only if new independent human residuals show that their incremental value can be captured without unacceptable list-quality regressions.
