# YV + KV selector coverage — taxonomy v31

**Status:** measured  
**Measured:** 2026-09-04  
**Extractor:** `scripts/selector_coverage.py`  
**Taxonomy snapshot SHA-256:** `634fd9d848a172747e54e3e487160a912ae6c0fcb8219c50998767c8c9aacbcc`

This finding measures the two published selector read models against the same active v31 taxonomy snapshot used by the native-text and common-relations inventories.

## Yrkesväljaren

Published source:

`https://data.arbetsformedlingen.se/yrke/yrkesvaljaren/v1/yrkesvaljaren-t31.json`

SHA-256: `1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49`

The file contains **12,330 rows**.

| Type | active taxonomy | unique YV IDs | YV row occurrences | coverage | missing active |
|---|---:|---:|---:|---:|---:|
| `occupation-name` | 2,105 | 2,105 | 2,105 | **100.0%** | 0 |
| `job-title` | 9,785 | 9,580 | 10,225 | **97.905%** | 205 |

No YV IDs were unknown to the active snapshot, no type mismatches were found, and every emitted `occupation_name_id` resolved to an active occupation-name.

### Multi-occupation job titles are common, not an edge case

**541 unique job-title IDs are related to more than one occupation-name in the published YV data.** A job title has at most three occupation parents in this snapshot.

Examples include:

- `Travtränare` → two occupation-name contexts
- `Customer journey specialist` → three occupation-name contexts
- `Musiklärare` → three occupation-name contexts
- `VA-anläggare` → three occupation-name contexts
- `Handläggare, miljöfrågor` → two occupation-name contexts

This is direct measured evidence for the core YV identity invariant:

> A semantic matcher must never treat the visible job-title string as a globally unique occupation identity. The job-title ID and its occupation context must survive retrieval and disambiguation.

The 10,225 job-title row occurrences versus 9,580 unique job-title IDs are therefore not ordinary duplicate noise. A material part is intentional context expansion.

### YV weights

All published rows have positive weights.

- occupation-name median weight: ~0.5712
- job-title median weight: ~0.00792

These weights originate in behavioural/search-frequency semantics. They are useful as priors/ranking evidence but are **not evidence of concept meaning**.

## Kompetensväljaren

Published source:

`https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t31.json`

SHA-256: `da83f26bf316971caa407364d8feae6f791203bff5758e674cace3d919e4b524`

The `data` object contains two genuine taxonomy context spaces plus one special non-context container:

| Context type | records | active taxonomy | coverage |
|---|---:|---:|---:|
| `occupation-name` | 2,105 | 2,105 | **100.0%** |
| `ssyk-level-4` | 400 | 400 | **100.0%** |

There is additionally a special top-level entry named `transferable_skills`; it has no taxonomy context `type` and must be inventoried separately. It must **not** be counted as an unknown occupation or SSYK concept.

The current published skill lists are populated on occupation-name records; SSYK4 records exist as a separate context layer and must not be collapsed into occupation identities.

### KV skill layers

| Layer | edges | unique active skills | active v31 skill coverage | occupation contexts non-empty |
|---|---:|---:|---:|---:|
| `regulated_skills` | 137 | 33 | 0.489% | 109 |
| `essential_skills` | 151 | 55 | 0.815% | 132 |
| `optional_skills` | 2,727 | 1,463 | 21.668% | 796 |
| `calculated_skills` | 31,637 | 4,104 | 60.782% | 2,097 |

The union across all four layers contains **4,647 unique active skill IDs**, i.e. **68.824% of all 6,752 active v31 skills**.

All referenced skill IDs resolve to active `skill` concepts. No wrong skill types were observed.

The layers overlap, for example:

- optional ∩ calculated: 974 unique skills
- essential ∩ calculated: 13
- regulated ∩ calculated: 10
- regulated ∩ essential: 0

Therefore layer membership is not a partition and cannot be converted into a single categorical authority label.

### Critical semantic boundary

`regulated_skills`, `essential_skills`, `optional_skills`, and `calculated_skills` have different provenance/semantics. The search research must preserve the layer that caused a skill to be associated with a context.

In particular, the very broad `calculated_skills` layer is valuable semantic retrieval material but must not silently acquire the authority of an essential or regulated skill relation.

## Product consequence

This project targets **both selectors**:

### YV destination space

Free text / description → exact YV canonical candidate identity, preserving occupation-name vs job-title and job-title→occupation context.

### KV destination space

Free text / description → exact active `skill` candidate identity.

YV and KV may share retrieval infrastructure, representations, evaluation tooling and an optional remote API, but they are separate semantic decision spaces. Cross-entity graph/context signals may generate candidates; they may not collapse destination identities.

## Source caveats / next work

1. Inspect and measure the special KV `transferable_skills` container separately.
2. Determine why 205 active job-title concepts are absent from YV and whether this is intentional filtering/search-frequency policy.
3. Measure Relevanta kompetenser independently; do not assume it is equivalent to KV `calculated_skills`.
4. Measure dedicated search concepts and specialised native occupation↔skill relations.
5. Use the 541 multi-parent YV job titles as a mandatory ambiguity stratum in Gate 2 and as hard regression cases.
