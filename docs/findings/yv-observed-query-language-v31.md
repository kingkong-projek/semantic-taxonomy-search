# Yrkesväljaren observed query language — v31 source snapshot

**Status:** measured  
**Measured:** 2026-09-04  
**Generator source commit:** `6dd9e4737d7db3cb2709f8082808b88e5c89ed6e`  
**Accepted CI run:** `33867438390`  
**Extractor:** `scripts/yv_query_language_coverage.py`

This measurement characterises the real Platsbanken search-language corpus used by the public Yrkesväljaren generator without pretending that query frequency is labelled user intent.

## 1. Corpus semantics

The generator snapshot contains `data/sokningar-platsbanken.json.zip`:

- SHA-256: `01a2550473091b06fdaaf450015eeea13b301471f1c78f5fb0dc8d3499645ae2`;
- date range: **2022-05-04 → 2026-08-16**;
- **115,553 distinct query strings** after the generator pipeline's filtering/aggregation;
- **3,136,136,606 aggregate searches**.

The underlying YV update code consumes approved search terms as `(query string, count)` and aggregates them. It does **not** contain the canonical taxonomy identity selected by the searcher.

Therefore:

> This corpus is observed language + popularity, not `query → selected canonical ID` ground truth.

The only automatically labelled association accepted in this finding is an **exact textual equality** between an observed query and a known YV/generator label.

## 2. Exact textual binding

| Class | distinct queries | term share | query volume | volume share |
|---|---:|---:|---:|---:|
| admitted YV label | 4,181 | 3.618% | 673,338,841 | **21.470%** |
| excluded `>3 parents` job-title label | 58 | 0.050% | 84,249,412 | **2.686%** |
| excluded redundant job-title label | 83 | 0.072% | 265,510,870 | **8.466%** |
| no exact admitted/excluded YV label binding | 111,231 | 96.260% | 2,113,037,483 | **67.377%** |

The `unbound` bucket is intentionally broad. It contains plausible occupational language such as `lärare`, `lagerarbetare`, `försäljare`, `systemutvecklare`, `civilingenjör`, `ämneslärare` and `programmerare`, but also geography and non-occupation intent such as `Stockholms län`, `Göteborg`, `sommarjobb` and `distans`.

It must not be treated as automatically labelled taxonomy training data.

## 3. Generator-excluded titles are high-volume retrieval vocabulary

The 205 active job-title identities excluded by YV's generator policy are not merely rare edge cases.

Within the observed query corpus, **141 of their exact labels occur as search queries**, producing:

- **349,760,282 searches**;
- **11.153% of the entire measured query volume**;
- **34.186%** of all volume whose query exactly matches either an admitted YV label or an excluded YV job-title label.

High-volume examples from the redundancy-policy population include:

| query | searches |
|---|---:|
| `undersköterska` | 58,994,102 |
| `butikssäljare` | 55,275,922 |
| `sjuksköterska` | 52,465,935 |
| `kock` | 42,198,933 |
| `projektledare` | 40,208,930 |

High-volume examples from the `>3 occupation parents` population include:

| query | searches |
|---|---:|
| `säljare` | 41,047,237 |
| `grundlärare` | 25,557,308 |
| `jurist` | 3,283,699 |
| `lastbilsförare` | 2,475,234 |
| `lagermedarbetare` | 2,148,491 |

## 4. Product implication: retrieval vocabulary ≠ selectable destination

This measurement strengthens the destination-space rule from `yv-generator-exclusion-policy-v31.md`.

A generator-excluded title should be available to the search engine as **strong retrieval/routing vocabulary**, while remaining outside the selectable YV job-title identity set.

Example shape:

```text
query: "undersköterska"
  ↓ exact observed/excluded-title vocabulary hit
excluded job-title identity
  ↓ typed occupation relation / generator policy
allowed YV occupation candidate(s)
```

The search engine must not solve the current UX problem by silently reintroducing the excluded job-title as a selectable YV result.

The `>3 parents` population especially should trigger disambiguation/diversification rather than arbitrary single-parent ranking.

## 5. Multi-context exact admitted titles also matter at scale

**240 observed query strings** exactly match an admitted YV label that occurs on multiple YV rows because the same job-title identity has multiple occupation contexts.

Together they represent:

- **35,949,704 searches**;
- **1.146% of total query volume**;
- **5.339% of admitted exact-label volume**.

Examples:

- `chaufför`: 12,330,700 searches, 3 YV contexts;
- `gymnasielärare`: 5,100,388, 2 contexts;
- `butiksmedarbetare`: 3,453,970, 3 contexts;
- `serveringspersonal`: 2,160,417, 2 contexts;
- `musiklärare`: 1,890,727, 3 contexts.

All measured multi-row exact matches correspond to the **same job-title ID repeated across occupation contexts**, not multiple independent job-title IDs.

So context preservation is not merely a theoretical identity invariant; it affects substantial observed traffic.

## 6. Semantic-search implication of the 67.377% unbound volume

The largest observed-language bucket has no exact YV admitted/excluded label binding: **67.377% of query volume**.

This is a major opportunity for better semantic retrieval, but it is not a free labelled dataset.

Use it for:

- benchmark query sampling;
- language-drift / vocabulary analysis;
- candidate-generation research;
- manually judged high-volume strata;
- discovering likely missing lexical aliases and semantic patterns.

Do not use it as automatic positive training pairs unless another trustworthy signal supplies the intended canonical identity.

## 7. Recommended benchmark strata created by this finding

YV Gate 2 should explicitly contain:

1. high-volume admitted exact labels;
2. high-volume exact excluded redundant titles;
3. high-volume exact excluded `>3 parents` titles;
4. admitted exact multi-context titles;
5. high-volume unbound occupational-looking queries, manually judged;
6. high-volume unbound non-occupation/search-filter queries that should abstain or remain outside YV concept mapping.

This will test both recall and false semantic confidence.

## 8. Guardrails

- Frequency is a ranking/coverage signal, not semantic authority.
- Exact string equality is not global synonymy; here it is only a safe textual binding to the known label identity/policy.
- Unbound terms are never automatically positive labels.
- Generator-excluded titles can route retrieval but cannot bypass the YV destination contract.
- Multi-context job-title identities must preserve each occupation context through retrieval and UX disambiguation.
- Any future telemetry that contains actual query→selection events must be measured separately from this corpus.

Machine aggregate: `research/coverage/v31/yv-query-language-aggregate.json`.
