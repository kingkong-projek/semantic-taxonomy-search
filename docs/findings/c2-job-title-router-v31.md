# C2 exact job-title router — v31

## Decision

Accept the deterministic C2 retrieval lane for further validation:

```text
C1
+ exact active job-title preferred-label lookup
+ typed occupation-name parents as candidates
```

`job-title` remains retrieval vocabulary only. It is never emitted as an occupation result and never bypasses a consumer admission profile.

No ML, embeddings, ESCO expansion, synthetic text or additional source engineering is used.

## Why C2 was justified

On the independently adjudicated C1 holdout, most remaining Discovery@5 failures were exact active job-title expressions. Taxonomy already provides typed job-title→occupation relations, so this is a source-attested candidate-generation gap rather than a reason to add semantic model complexity.

## Results

### Previously opened natural-language holdout

36 cases / 208,583,095 observed searches:

- Discovery Success@5: **94.444%** unweighted.
- Volume-weighted Discovery Success@5: **93.677%**.
- NO_MATCH abstention: **100%**.
- Remaining failures: only `lager` and `administration`.

This view is development-only because the holdout had already been opened before C2 was designed. It cannot serve as independent proof of natural-language generalization.

### Unseen excluded-title sentinel

The next 30 highest-volume excluded-title rows (ranks 21–50) were not used to design C2. They cover 7,205,252 observed searches.

- Any source-attested typed parent present in top 5: **100%**.
- Volume-weighted any-parent Hit@5: **100%**.
- Mean typed-parent Recall@5: **92.395%**.
- Volume-weighted typed-parent Recall@5: **93.220%**.
- All typed parents visible in top 5: **80.0%** of rows / **79.049%** volume-weighted.

The all-parent metric is diagnostic only. For discovery, a query with 6–12 legitimate parents cannot expose every parent in a five-item list by construction; the primary question is whether useful typed parents are present.

### Regression

The frozen 333-case YV P80 source-truth suite remains:

- top-1: **100%**;
- Discovery Hit@5: **100%**;
- top-1 misses: **0**.

## Interpretation

C2 materially closes the dominant C1 candidate-generation gap using a dictionary/graph lookup. The result is consistent with the simple-first hypothesis: trusted taxonomy structure is still buying more value than additional semantic infrastructure.

Do **not** add a special rule for `lager` or `administration` from the opened holdout. The next decision-bearing step is a fresh natural-language holdout drawn from the next highest-volume observed-query population and adjudicated before C2 output is inspected.

Only if that fresh holdout exposes a material residual should the next capability be added. D/ESCO, embeddings, reranking and synthetic enrichment remain deferred.

## Reproducibility

- Workflow: `C2 exact job-title router`
- Run: `34022726840`
- Head: `23bb0e121fd22b4913f9af78bbf1057e9225c3ca`
- Artifact: `c2-job-title-router-v31`
- Artifact digest: `sha256:0b350df51af9b636a7a4329210ca2c07603c6ac81bf271693a9c695572b932ec`
- Frozen compact result: `research/evaluation/v31/c2-job-title-router.json`
