# Compact YV reference-profile safety slices — taxonomy v31

**Status:** measured/frozen where source truth permits; routing review remains pending  
**Measured:** 2026-09-06

These slices test YV-specific admission/routing semantics on top of the reusable `occupation` retrieval core. They are **not** the generic engine scope.

## Multi-parent ambiguity

Population: **541** admitted job-title IDs with multiple YV occupation contexts.

Simple-first selection: the **20 highest-volume exact title queries** from the pinned observed-query corpus, totaling **31,374,980 searches**.

The 20 cases are `AUTO_HIGH_CONFIDENCE` because the exact canonical job-title identity, typed occupation contexts and published YV admission are all source-attested. Every case requires all admitted context-specific identities to remain available; the system may not collapse them prematurely.

Top examples:

- `Chaufför` — 12,330,700 searches, 3 contexts
- `Gymnasielärare` — 5,100,388 searches, 2 contexts
- `Butiksmedarbetare` — 3,453,970 searches, 3 contexts
- `Serveringspersonal` — 2,160,417 searches, 2 contexts
- `Musiklärare` — 1,890,727 searches, 3 contexts
- `Farmaceut` — 1,198,757 searches, 2 contexts
- `Bildlärare` — 979,003 searches, 3 contexts
- `Skribent` — 654,818 searches, 2 contexts
- `Butiksbiträde` — 579,095 searches, 3 contexts
- `Underhållstekniker` — 447,150 searches, 2 contexts

## Excluded-title routing review

Population: **205** active job-title IDs excluded by the pinned YV generator policy.

Simple-first selection: the **20 highest-volume exact excluded-title queries**, totaling **340,823,768 searches**. In this top-20 slice the generator reasons are exactly **10 `redundant_label` + 10 `too_many_parents`**.

These rows remain `PENDING_HUMAN_REVIEW`. The generator exclusion reason is source truth; related occupation identities are only routing/context candidates and are **not** auto-promoted to benchmark destination truth.

Top examples:

- `Undersköterska` — 58,994,102 searches — `redundant_label`
- `Butikssäljare` — 55,275,922 searches — `redundant_label`
- `Sjuksköterska` — 52,465,935 searches — `redundant_label`
- `Kock` — 42,198,933 searches — `redundant_label`
- `Säljare` — 41,047,237 searches — `too_many_parents`
- `Projektledare` — 40,208,930 searches — `redundant_label`
- `Grundlärare` — 25,557,308 searches — `too_many_parents`
- `Specialistläkare` — 4,674,163 searches — `redundant_label`
- `Jurist` — 3,283,699 searches — `too_many_parents`
- `Vaktmästare` — 3,206,024 searches — `redundant_label`

## Why this is enough for now

The initial safety budget follows the Pareto rule. We do not manually adjudicate all 541 multi-parent titles or all 205 excluded titles before the simple system has demonstrated that broader coverage changes a decision. The remaining small safety requirement is hard-negative/no-match/abstention judgment.

## Reproducibility

- generator commit: `6dd9e4737d7db3cb2709f8082808b88e5c89ed6e`
- query corpus SHA-256: `01a2550473091b06fdaaf450015eeea13b301471f1c78f5fb0dc8d3499645ae2`
- taxonomy SHA-256: `634fd9d848a172747e54e3e487160a912ae6c0fcb8219c50998767c8c9aacbcc`
- Yrkesväljaren SHA-256: `1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49`
- frozen manifest SHA-256: `72b1445d26c6bb0149c2ef9178add5fb232bbcfa9b0d1e3460df97a3bce3bb03`
- multi-parent JSONL SHA-256: `8c0586e1252f119ec6c061fda4455afd65e8bc2a8a08a940eab33f79d014f3d3`
- excluded-routing JSONL SHA-256: `396b07714d36ed21e77badf5d5c4fdb418b1f055221d8ad908dab8a5e685dc98`
