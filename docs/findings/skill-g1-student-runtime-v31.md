# Compiled KV semantic student runtime — taxonomy v31

**Status:** validated runtime shape for `KV-G1-4slot`

## Decision

The validated skill-description candidate does not require a semantic API, embeddings, WebGPU, ONNX or any model inference in the browser.

All BM25 statistics and per-document contributions are compiled at build time. The browser receives one static dual-score inverted index:

```text
query
  -> normalize/tokenize
  -> one postings lookup pass
       posting = [skill ordinal, precomputed C0 score, precomputed G1 score]
  -> sum C0/G1 scores
  -> exact canonical-surface boost
  -> C0 rank 1 + up to four G1 candidates
  -> canonical AF skill IDs
```

Runtime dependencies: **zero**.

Ordinary YV/KV semantic payload: **zero bytes**. The asset is only eligible for loading after the user explicitly enters `Beskriv din kompetens`.

## Size

The evaluation-shaped index excludes both natural-description holdouts from G1 retrieval evidence:

- 4,099 terms;
- 10,081 postings;
- 444,138 raw bytes;
- **140,565 bytes gzip-9**.

The production-shaped index includes all eligible source-attested AF training language:

- 4,533 terms;
- 11,030 postings;
- 477,833 raw bytes;
- **151,768 bytes gzip-9**.

Keeping C0 and G1 as two independent assets would use 171,379 gzip bytes. The merged dual index saves 19,611 bytes (~11.4%) and removes a duplicated token pass / shared metadata surface.

At ~152 kB gzip, the whole semantic fallback is already small enough to lazy-load as one asset. **Do not introduce sharding yet.** Chunking remains an available deployment technique if later evidence materially increases the payload, not a requirement to build pre-emptively.

## Parity

The compiled implementation is exact against the Python reference at top 10 for **649 / 649** frozen cases:

- 617 canonical KV source-truth regressions;
- 20 independently frozen second-holdout descriptions;
- 12 synthetic KV description-stress queries.

There are zero parity failures.

## Runtime diagnostic

On the intentionally modest self-hosted `garderob` runner, the dependency-free JS dual runtime measured across 16,225 query executions:

- mean: **165.815 µs/query**;
- median round: 102.138 ms for 649 queries;
- p95 round: 109.235 ms for 649 queries.

These are implementation diagnostics, **not a low-end-mobile SLA**. The stronger conclusion is structural: runtime work consists only of ordinary string tokenisation, hash/object lookups, floating-point additions and sorting a small candidate set. No accelerator assumption is present.

## Build-time / student-model interpretation

The useful distinction is now concrete:

- build time may perform source ingestion, provenance checks, BM25 statistics, weighting, pruning and index compilation;
- runtime only consumes the distilled postings table.

This is effectively a student model whose representation is a deterministic lookup table rather than a neural network. Future expensive teacher/model work may be tested offline if a measured residual justifies it, but nothing in the current result requires such a layer.

## Decision boundary

Do not optimise runtime further now. The remaining Track-2 work should return to relevance: classify the three second-holdout Hit@5 misses and nominate the smallest next capability, without tuning on that holdout or contaminating future independent validation.

Evidence:

- frozen runtime summary: `research/evaluation/v31/skill-g1-student-runtime.json`;
- validated relevance summary: `research/evaluation/v31/skill-training-language-validated.json`;
- workflow run: `34060318525`;
- artifact: `9997255650`.
