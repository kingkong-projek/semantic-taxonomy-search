# C2 fresh natural-language holdout — v31

## Decision

**Do not add D/ESCO, embeddings, reranking or synthetic enrichment for occupation discovery now.** Frozen C2 passed the independent natural-language validation slice without a measured residual.

C2 remains entirely deterministic:

```text
C1: preferred labels + canonical definitions + alternative labels
    + six measured boundary occupations
    + short-query surface/component/fuzzy evidence
    + conservative abstention
C2: C1 + exact active job-title preferred label -> typed occupation-name parents
```

No machine learning is used by retrieval.

## Blinding

A new holdout was selected from unbound observed-query ranks **51–80**. It contains **30 cases / 138,075,677 observed searches**.

The workflow generating the holdout explicitly did not invoke C2. Taxonomy-only context was prepared, then the 30 judgments were frozen and validator-clean before a separate C2 evaluation workflow was created/run.

Judgments:

- 25 `NO_MATCH` cases, largely geography plus `distans`;
- 4 `AMBIGUOUS`: `enhetschef`, `lärare i grundskolan`, `hr`, `utredare`;
- 1 `SINGLE`: `kommunikatör`.

They are explicitly `MODEL_ADJUDICATED` with `model_judgment` provenance, not source or human truth.

## Result

Frozen C2, unchanged:

- Discovery Success@5: **100.0%**;
- volume-weighted Discovery Success@5: **100.0%**;
- positive-intent Discovery Success@5: **100.0%** (5/5);
- volume-weighted positive-intent Discovery Success@5: **100.0%**;
- NO_MATCH abstention: **100.0%** (25/25);
- top-1 diagnostic: **100.0%** in this slice;
- frozen 333-case YV source-truth regression: **100.0% top-1 and Hit@5**.

None of the five positive cases required the C2 job-title route; the C1 part already surfaced a judged-positive occupation. That is useful evidence for the underlying simple lexical representation, not evidence that every natural-language occupation query is solved.

## Interpretation

This result is strong but bounded. The holdout is dominated by other-intent/geographic queries and contains only five positive occupation queries. Therefore **100% must not be generalized to all occupation language**.

What it does establish is the decision needed now:

1. C2 generalizes safely to a fresh high-volume slice;
2. conservative abstention remains reliable;
3. no new occupation-retrieval capability is justified by measured residuals;
4. the next research gap should move to the other core target space — natural-language **skill** discovery — rather than optimizing the opened YV residuals or expanding the occupation stack.

ESCO/source enrichment may still become useful later, but only after a skill or future occupation benchmark demonstrates a material residual.

## Reproducibility

- Blinded benchmark commit: `2a5d1a6af2e49ec7197f4843e678fcdb6c92c9df`
- Evaluation workflow run: `34026624445`
- Evaluation head: `08477d1870d19b5ab6cf170749541b3ac2222d16`
- Artifact: `c2-fresh-natural-holdout-v31`
- Artifact digest: `sha256:e8f34def0b4037d55225a4361158eee81223c86ec2928240c056ac3cb1c78b63`
- Frozen compact result: `research/evaluation/v31/c2-fresh-natural-holdout.json`
