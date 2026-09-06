# Exact ESCO text for skill discovery — taxonomy v31

**Decision status:** negative development result on the primary Discovery@5 objective; do not adopt this lane as-is.

The 76-case manual labour-market-training benchmark had already been opened by KV-C0, so this is development evidence only.

## Safest ESCO lane tested

Only AF v31 `skill` → `exact_match` → `esco-skill` edges from the already-pinned immutable `concepts-and-common-relations` snapshot were admitted.

For the matched ESCO nodes, preferred label, real definition and canonical alternative labels were appended as BM25 token context. AF preferred/alternative labels remained the only exact lexical surfaces and the only emitted/selectable identities remained AF v31 `skill` IDs.

`broad_match`, `narrow_match` and `close_match` were explicitly excluded.

## Coverage

Across the 316 P80 skills:

- 96 have at least one exact ESCO skill mapping;
- 107 exact mapping edges are present;
- all 107 mapped ESCO nodes used by the experiment have a real definition;
- 31/76 benchmark targets have exact ESCO coverage;
- 24/63 primary descriptive/non-leaky targets have exact ESCO coverage.

## Result

### Primary 63 descriptive, non-leaky cases

| configuration | top-1 | Discovery@5 | weighted Discovery@5 | Hit@10 | weighted Hit@10 |
|---|---:|---:|---:|---:|---:|
| KV-C0 | 30.159% | 46.032% | 57.083% | 47.619% | 58.675% |
| KV-D1 exact ESCO text | 30.159% | 44.444% | 45.528% | 50.794% | 61.895% |

Exact ESCO text improves some deeper ranking and weighted top-1 behavior but **hurts the primary Discovery@5 objective**, especially on the occurrence-proxy-weighted score.

### Canonical regression

Both KV-C0 and the exact-ESCO variant remain 100% top-1 and 100% Discovery@5 on the frozen 617-case canonical KV source-truth suite.

## Decision

Do not adopt exact-ESCO text as a blanket document expansion.

This result does **not** imply that every ESCO mapping type should be tried indiscriminately. Before another retrieval variant, measure exact/close/broad/narrow mapping coverage specifically on the remaining natural-text C0 misses, including target multiplicity. Only a mapping lane that materially covers the measured residual should justify another ablation, and mapping semantics must remain separate.

The result also does not create an API requirement: the ESCO nodes used here already live in the pinned taxonomy snapshot and could be compiled into static frontend data. The lane was rejected on relevance, not deployability.
