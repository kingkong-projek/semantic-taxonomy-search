# Track 1 canonical alias reachability — taxonomy v31

## Decision

A small deterministic lane for **current canonical alternative/hidden labels** is justified before adding semantic complexity. It should run before fuzzy matching and preserve the canonical concept identity. Ambiguous alias surfaces must not silently force a single target.

This is not permission to treat `replaced_by` history as synonymy. Deprecated labels remain migration/history routing evidence because terms such as broad historical labels can legitimately collide with current concrete occupations.

## Measured current baseline

The replay is pinned to `kingkong-projek/yrkesvaljaren@ab0b3f28576d8aebec2b593b771a70c7684b1eca`, including contextual fuzzy identity (`job-title id + occupation-name context`). The measurement ran successfully on self-hosted `garderob` as Actions run `34045443253`.

| | YV | KV |
|---|---:|---:|
| distinct canonical alias surfaces | 362 | 1,317 |
| ambiguous across targets | 1 (0.276%) | 28 (2.126%) |
| strict unique alias cases | 357 | 1,278 |
| current hit@5 | 318 (89.076%) | 1,056 (82.629%) |
| deterministic exact-alias rescues | **39** | **222** |
| post-lane hit@5 on strict unique aliases | **100%** | **100%** |

YV already handles canonical alias traffic well. Within YV alias cases that occur exactly in the pinned query corpus, current hit@5 is **98.578% by observed volume**. The 39 deterministic rescues account for **1,362,861 searches / 1.422%** of that alias-set volume.

KV has a much larger cheap residual. The 222 deterministic rescues account for **18,765 / 50.902%** of the Historical-API target-occurrence proxy mass represented by the remaining unique-alias failures. This proxy prioritises work; it is not user query intent.

Examples include `Microsoft Office`/`Officepaketet` → `MS Office`, `Legitimation som sjukgymnast` → `Legitimation som fysioterapeut`, and JavaScript competence/knowledge variants → `JavaScript, programmeringsspråk`.

## Product implication

Implement current canonical aliases as a privileged deterministic lexical lane. Keep preferred labels and existing search behaviour intact, preserve all product admission rules, and fail closed on alias ambiguity instead of guessing. Re-run the same packet after the product patch.

The result supports the broader Track-1 hypothesis: YV may already be strong for ordinary known-name lookup, while KV has a material vocabulary gap that does not require semantic retrieval to fix. Neither result removes the separate need for free-text semantic fallback when the user does not know the occupational/competence term.

Structured result: `research/evaluation/v31/track1-canonical-alias-rescue.json`.
