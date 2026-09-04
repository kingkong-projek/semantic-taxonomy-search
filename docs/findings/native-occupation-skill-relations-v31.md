# Native occupation→skill relation semantics — taxonomy v31

**Status:** measured  
**Measured:** 2026-09-04  
**Extractor:** `scripts/native_occupation_skill_coverage.py`  
**Accepted CI run:** `33866563660`  
**Accepted run commit:** `2fa5fc46d7f13f43115c1e73fba1e8eaf6eb1acc`

This measurement resolves whether Taxonomy-native `essential` / `optional` occupation→skill relations and similarly named Kompetensväljaren fields are independent semantic sources.

## 1. Native Taxonomy relations

The GraphQL query was pinned to taxonomy version 31 and all returned source/target IDs were validated against the immutable v31 common snapshot.

| Native relation | occupations non-empty | occupation coverage | directed edges | unique active skills | active skill coverage |
|---|---:|---:|---:|---:|---:|
| `essential` | 141 | 6.698% | 288 | 88 | 1.303% |
| `optional` | 796 | 37.815% | 2,727 | 1,463 | 21.668% |

GraphQL returned exactly all **2,105 / 2,105** active occupation-name concepts. No invalid native relation targets were observed.

## 2. KV optional is an exact projection of native optional

Exact directed-pair comparison:

- native `optional`: **2,727** edges;
- KV `optional_skills`: **2,727** edges;
- intersection: **2,727**;
- native-only: **0**;
- KV-only: **0**;
- Jaccard: **1.0**.

Therefore, for taxonomy v31:

> `KV optional_skills == Taxonomy native optional`

This is identity-level equality of directed `(occupation-name ID, skill ID)` pairs, not just equal counts.

## 3. KV splits native essential into regulated and non-regulated

The canonical skill collection is named `Reglerande behörigheter` and has ID `4P8B_LtK_JgE`. It contains **33 active skill IDs**.

Of the **288** native `essential` edges:

- **137** target a skill in `Reglerande behörigheter`;
- **151** target another essential skill.

Exact pair comparisons show:

### Regulated partition

- native essential edges targeting the regulated collection: **137**;
- KV `regulated_skills`: **137**;
- intersection: **137**;
- differences: **0 / 0**.

So:

> `KV regulated_skills == native essential restricted to Reglerande behörigheter`

### Non-regulated partition

- native non-regulated essential edges: **151**;
- KV `essential_skills`: **151**;
- intersection: **151**;
- differences: **0 / 0**.

So:

> `KV essential_skills == native essential excluding Reglerande behörigheter`

And consequently:

> `Taxonomy native essential == KV essential_skills ∪ KV regulated_skills`

The union comparison is exact **288 / 288** directed pairs with zero differences.

## 4. Product/retrieval implication

We should not model these as three unrelated semantic authorities.

The source semantics are:

```text
Taxonomy native optional
  └─ KV optional_skills           exact projection

Taxonomy native essential
  ├─ KV essential_skills          non-regulated partition
  └─ KV regulated_skills          regulated-skill partition
```

`regulated_skills` should still remain separately typed in the retrieval trace and UI/search representation because the distinction is meaningful. But it does **not** constitute an independent relevance signal in addition to native essential. Double-counting native essential plus the two KV partitions would count the same evidence twice.

`calculated_skills`, `transferable_skills` and Relevanta kompetenser remain separate derived/context signals and are not affected by this equivalence result.

## 5. Guardrails

- Relation equality is established only for the measured taxonomy/KV v31 snapshots.
- Future versions must be revalidated rather than assuming the projection contract remains exact.
- `essential` means native taxonomy relation semantics; it is not a generic relevance score.
- `regulated` is a typed partition of essential evidence, not a stronger numeric score by definition.
- Exact pair equality permits provenance consolidation; it does not permit collapsing skill identities or relation meaning.

Machine aggregate: `research/coverage/v31/native-occupation-skill-aggregate.json`.
