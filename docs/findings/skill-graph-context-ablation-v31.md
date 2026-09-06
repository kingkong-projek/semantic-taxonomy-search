# Skill graph-context ablation — taxonomy v31

**Decision status:** negative development result; do not adopt this lane.

The frozen 76-case manual labour-market-training benchmark was first opened by KV-C0. The graph-context variants below are therefore development evidence, not independent holdout evidence.

## Question

Can the first natural-text skill residual be solved by the smallest already-owned typed graph context, without ESCO, embeddings or new source engineering?

The tested context was deliberately narrow and frontend-compilable:

- `KV-C0`: P80 skill preferred label + real canonical definition + canonical alternative labels;
- `KV-C1e`: C0 plus preferred labels of occupations that carry the skill as native/KV essential or regulated;
- `KV-C1all`: C1e plus preferred labels of occupations that carry the skill as optional.

Occupation names were BM25 token context only. They were never promoted to exact skill surfaces. Training-module benchmark text was never ingested into retrieval documents.

## Coverage

Across 316 P80 skills:

- 34 have essential/regulated occupation context (203 distinct skill→occupation context edges);
- 193 have any essential/regulated/optional occupation context (835 distinct context edges).

## Result on the 63 primary descriptive, non-leaky natural-text cases

| configuration | Discovery Hit@5 | occurrence-proxy weighted Hit@5 | Hit@10 | weighted Hit@10 |
|---|---:|---:|---:|---:|
| KV-C0 | 46.032% | 57.083% | 47.619% | 58.675% |
| KV-C1e | 44.444% | 55.710% | 49.206% | 59.454% |
| KV-C1all | 44.444% | 44.700% | 49.206% | 60.473% |

The broader optional-context lane is especially harmful on the primary weighted @5 metric.

## Canonical regression

KV-C0 remains 100% top-1 and Discovery@5 on the frozen 617-case canonical source-truth suite.

Both context variants regress that suite:

- top-1: 98.865%;
- Discovery@5: 99.352%;
- seven top-1 misses each.

The misses include canonical definition/exam/licence cases where occupation-name tokens overpower the skill concept's own canonical text. This is a real semantic-noise failure, not a CI/runtime failure.

## Decision

Do **not** put inverted occupation context into the skill retrieval document merely because the relation is curated and available. More graph data is not automatically better retrieval data.

The next smallest justified experiment is retrieval-only lexical normalization/compound tolerance over the same canonical KV-C0 documents. Preserve C0's canonical rank-1 behavior and test whether a small number of top-5 discovery slots can be rescued from skill label/alternative-label morphology. Do not move to ESCO or embeddings until that cheaper hypothesis is measured.

This negative result does not create an API requirement. All tested context could have been precompiled into a static data package; it was rejected on relevance, not runtime architecture.
