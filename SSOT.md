# Single source of truth

This file is the canonical entrypoint for current project state.

## Authority order

1. `docs/research-plan.md` — product scope, research architecture, evidence rules, gates and experiment order.
2. `docs/findings/*` and `research/*` — evidence supporting or falsifying the plan. They do not silently override it.
3. `docs/findings/field-feedback-findability-2026-09-07.md` + `research/evaluation/v31/field-feedback-findability-2026-09-07.json` — current real-user field-feedback evidence and frozen derived corpus.
4. `docs/findings/gemma4-yv-teacher-a0-a1-2026-09-08.md` + `research/evaluation/v31/gemma4-yv-teacher-a0-a1.json` — current compile-time YV teacher-quality/representation evidence.

## Current amendment — 2026-09-08 — compile-time YV teacher tournament

The first frozen Gemma 4 YV teacher corpus and its A0/A1 replay have now falsified two simple implementations without falsifying the teacher-language hypothesis:

- 149 high-demand YV occupations produced 1,192 synthetic teacher phrases from public taxonomy evidence only;
- the raw corpus contains measurable quality defects and is **not canonical truth**; source-only deterministic hygiene leaves 1,179 phrases;
- canonical+teacher BM25 document concatenation is **REJECTED** because it changes 3/333 protected canonical Top1 ranks and does not improve strict source-attested Hit@5 beyond 9/17;
- a guarded `canonical rank1 -> one teacher candidate -> remaining canonical` fusion is also **REJECTED** as a promoted rule: it preserves 333/333 canonical Top1 but still stays 9/17 on the strict source-attested diagnostic, gives only small opened-stress gains, and returns positive teacher lexical evidence on 11/13 opened abstain/empty-clarify cases;
- the provenance-separated teacher lane remains useful **architecture evidence** because its opened oracle shows complementary colloquial/indirect reach; this does not authorize runtime promotion.

Therefore the next Track-2 architecture action is **not** another fusion tweak on the opened A0/A1 cases. Harden teacher generation from source-only quality rules, expand coverage beyond the current 149 occupations, preserve teacher evidence as a separate representation, and treat abstention/calibration as a hard gate. Fresh independent stream-separated evidence is still required before any retrieval/fusion/runtime promotion.

Detailed evidence: `docs/findings/gemma4-yv-teacher-a0-a1-2026-09-08.md` and `research/evaluation/v31/gemma4-yv-teacher-a0-a1.json`.

At the next safe consolidation of the large living research plan, fold this amendment into the compile-time tournament section and reduce this note to a pointer.

## Current amendment — 2026-09-07 — field-feedback replay

The field-feedback finding is new independent user evidence of the exact class that `docs/research-plan.md` names as a trigger for renewed product investigation.

Therefore the older sentence in section 2.1.1 that says Track 1 is simply `PARKED` is stale in one narrow respect:

- broad Track-1 expansion remains parked;
- **a bounded Track-1 field-feedback replay is ACTIVE**;
- its purpose is only to classify the 2026-09-07 real-user failures against exact current YV/KV behaviour and promote reproduced product-native defects to the owning repository;
- Track 2 remains active and is not replaced by this replay;
- consumer-service investigation is out of scope; that team has been informed separately.

The detailed evidence and action order are in `docs/findings/field-feedback-findability-2026-09-07.md`.

At the next safe consolidation of the large living research plan, this amendment should be folded into section 2.1.1 and this note reduced to a pointer. Until then, this root file resolves the status precedence explicitly so no future session needs conversation memory to know that the bounded replay is active.

## Cross-repository boundary

`kingkong-projek/semantic-taxonomy-search` owns evidence, classification, semantic-retrieval research and the decision about whether a residual justifies Track 2.

`kingkong-projek/yrkesvaljaren` owns reproducible YV/KV product behaviour, fixes and regression tests. Its feedback-specific product SSOT is `docs/findability-feedback-ssot.md`.
