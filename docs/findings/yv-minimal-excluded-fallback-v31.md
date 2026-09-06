# Minimal YV fallback for generator-excluded exact titles — taxonomy v31

## Question

Can the remaining material ordinary-search failures among generator-excluded YV titles be recovered without reranking already-working queries or turning excluded job-title identities back into selectable concepts?

## Candidate rule

The evaluated rule is deliberately narrow and is **not yet a product change**.

It activates only when all of the following hold:

1. the query exactly matches a generator-excluded active job-title label;
2. current reproduced YV search exposes no generator-mapped occupation route;
3. the title is either:
   - `too_many_parents` with exactly **4** mapped occupations — the minimum overflow above the generator's existing `>3` exclusion boundary; or
   - `redundant_label` with exactly **1** mapped occupation;
4. the fallback emits only allowed `occupation-name` identities. The excluded job-title remains query vocabulary and never becomes selectable identity.

If current search already exposes a generator-grounded route, nothing changes. Thus broad queries such as `Säljare`, `Jurist`, `Projektledare` and `Kock` are explicitly outside the fallback.

## Reproduced baseline

The corrected 205-title product replay leaves **64** cases with no generator-mapped occupation visible. They represent **3,978,003** observed exact queries:

- **1.137%** of all generator-excluded exact-title volume;
- **0.127%** of the full retained YV query corpus.

## Counterfactual effect

Self-hosted run `34056007065` on `garderob` reproduced the current selector first and then evaluated the bounded fallback.

The rule triggers for **37** of the 64 residual cases and covers **3,687,311** observed exact queries.

That is:

- **92.693%** of current residual volume recovered;
- weighted excluded-title top-5 grounded reachability rises from **98.863%** to **99.917%**;
- only **27** no-parent cases remain;
- remaining observed volume is **290,692**, or **0.009%** of the full retained YV query corpus.

Highest-volume recovered cases include:

- `Grundskollärare` — 1,628,450 queries, 4 mapped occupations;
- `Slöjdlärare` — 787,437, 4;
- `Samtalsterapeut` — 331,270, 4;
- `Anläggningsmaskinförare` — 287,983, 4;
- `Lärare historia` — 275,648, 4;
- `Managementkonsult` — 82,664, 4;
- `Träslöjdslärare` — 82,601, 4.

The main remaining observed cases are structurally broader: `Teacher` (237,289 queries / 9 parents), `Yrkesförare` (22,556 / 12), `Sjökapten` (18,202 / 6), `Analyschef` (6,426 / 5) and `Montessoripedagog` (5,594 / 5).

## Why this is different from global parent-first ranking

The earlier global counterfactual placed generator parents first for every excluded title. That trivially improved visibility but also rewrote already-useful result lists and did not resolve broad intent.

This rule does neither. It is fallback-only and bound to the generator's existing admission policy. In particular:

- it does not touch the 98.863% of excluded-title traffic that already has a grounded route within top 5;
- it does not flatten titles with 5–38 possible parents into an arbitrary small dropdown;
- it uses the generator's own relation evidence rather than semantic inference;
- it cannot introduce an excluded job-title as a selectable identity.

## Decision

Classify this as a **strong bounded Track-1 candidate**, not as an adopted production change yet.

The measured benefit is unusually concentrated: 37 narrowly defined cases recover 92.693% of the residual exact-query volume while existing grounded behavior is preserved by construction. Before implementation, the remaining Track-1 integration and SSOT exit criteria should be closed and this rule should be represented explicitly in the compact failure-mode map.

Sources: run `34056007065`, artifact `9995975414`, artifact ZIP SHA-256 `3713464f706954034916349d6fc7d905f99f83f25a56d6bb18e03fbc521614be`.
