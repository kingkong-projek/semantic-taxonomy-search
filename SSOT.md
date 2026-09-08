# Single source of truth

This file is the canonical entrypoint for current project state.

## Authority order

1. `docs/research-plan.md` — product scope, research architecture, evidence rules, gates and experiment order.
2. `docs/findings/*` and `research/*` — evidence supporting or falsifying the plan. They do not silently override it.
3. `docs/findings/field-feedback-findability-2026-09-07.md` + `research/evaluation/v31/field-feedback-findability-2026-09-07.json` — current real-user field-feedback evidence and frozen derived corpus.

## Current amendment — 2026-09-08: Track-2 architecture breadth phase

The latest A593 evidence changes the immediate Track-2 experiment order recorded in the large living plan.

The explicit source-bound pair-contrast layer is useful on the exact teacher-held-out confusion pairs but does not transfer to the opened user-like/source-attested diagnostics: on 4,744 frozen teacher holdouts it changes Top1 `1576 -> 1586` (+10) and Hit@5 `2957 -> 2965` (+8), while the subsequent opened replay has **zero delta** on targetable40 Top1/Hit@5 and strict17 Top1/Hit@5/MRR.

Therefore the older research-plan wording that continues local A593 sparse/context tuning before widening the architecture search is now stale. Until folded into `docs/research-plan.md`, the active Track-2 order is:

- **freeze the current A593 expanded-sparse family as the reference;**
- **keep A2105/full Gemma generation paused;**
- stop local stemming/hub/hard-negative/pair-rule micro-tuning during architecture selection;
- freeze one common, source-bound, cross-style transfer proxy that does not use opened 17/88 wording or outcomes;
- test two deliberately simple single-stage challengers: **B supervised sparse classifier** and **C task/activity representation**;
- compare A/B/C on the same frozen transfer evidence plus canonical guards and frontend byte/runtime constraints;
- kill losing architecture families and then optimise only the simplest surviving winner;
- do not build a coarse-retrieval -> local-discriminator stack unless both single-stage challengers fail and diagnostics specifically justify the extra stage.

The simplicity contract is explicit: the preferred final shape is **exact/canonical lexical route + one semantic description ranker/index**. Do not combine weak entrants into a hybrid merely to gain benchmark points. A single-stage challenger must earn roughly **>=5 absolute percentage points** on a primary prefrozen transfer metric to justify continued work; a later two-stage semantic architecture must earn roughly **>=10 absolute percentage points over the best surviving single-stage candidate** to justify its added complexity. These are decision bars, not tuning targets.

Detailed frozen decision and machine-readable gate:

- `docs/findings/compile-time-architecture-breadth-gate-2026-09-08.md`
- `research/evaluation/v31/compile-time-semantic-architecture-breadth-gate.json`

## Current amendment — 2026-09-07: bounded Track-1 field-feedback replay

The field-feedback finding is new independent user evidence of the exact class that `docs/research-plan.md` names as a trigger for renewed product investigation.

Therefore the older sentence in section 2.1.1 that says Track 1 is simply `PARKED` is stale in one narrow respect:

- broad Track-1 expansion remains parked;
- **a bounded Track-1 field-feedback replay is ACTIVE**;
- its purpose is only to classify the 2026-09-07 real-user failures against exact current YV/KV behaviour and promote reproduced product-native defects to the owning repository;
- Track 2 remains active and is not replaced by this replay;
- consumer-service investigation is out of scope; that team has been informed separately.

The detailed evidence and action order are in `docs/findings/field-feedback-findability-2026-09-07.md`.

At the next safe consolidation of the large living research plan, both current amendments should be folded into the relevant sections and reduced to pointers. Until then, this root file resolves status precedence explicitly so no future session needs conversation memory to recover the active execution order.

## Cross-repository boundary

`kingkong-projek/semantic-taxonomy-search` owns evidence, classification, semantic-retrieval research and the decision about whether a residual justifies Track 2.

`kingkong-projek/yrkesvaljaren` owns reproducible YV/KV product behaviour, fixes and regression tests. Its feedback-specific product SSOT is `docs/findability-feedback-ssot.md`.
