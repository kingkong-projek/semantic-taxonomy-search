# Typed ESCO complement above validated KV G1 — v31

**Status:** negative complement result; no ESCO fusion admitted.

This experiment deliberately did **not** choose a fusion rule. It reproduced `KV-G1-4slot-single-desc` and ranked `exact_match`, `close_match`, `broad_match` and `narrow_match` ESCO text as four separate candidate lanes keyed back to AF P80 skill identities. The only question was whether any typed lane independently finds enough current G1 misses to justify a later fusion experiment.

## Natural-description result

On the later first-holdout diagnostic shape, G1 is 32/35 Hit@5. Exact ESCO independently rescues one of the three misses (`Ritningsläsning`); close, broad and narrow rescue none.

On the second holdout, G1 is 17/20 Hit@5. Exact ESCO independently rescues **one** of the three misses: `Produktionsplanering, tillverkning`. That is the already classified ambiguous case whose query explicitly names the currently surfaced `Produktionsteknik` and `Ständiga förbättringar/Lean`. Close, broad and narrow rescue **zero** of the three misses.

Crucially, `Städmaterial` — the cleanest source-language gap and the case whose exact ESCO concept `rengöringsprodukter` looked semantically promising on inspection — is still **not** top-5 in the exact ESCO lane. The mapping exists, but simple lexical ranking over that lane does not close the gap.

## Synthetic stress

ESCO has more oracle complement on the 12 synthetic cases: exact/close/broad each rescue one current miss, narrow rescues two. But this does not override the natural-description evidence. Adding another mapping source, index and fusion mechanism only for synthetic gains would violate the simple-first rule while leaving the clean natural residual untouched.

## Decision

Do **not** add an ESCO runtime lane to v0. Do not tune a C0/G1/ESCO fusion on the opened holdouts.

This is a useful negative result: typed ESCO semantics contain relevant concepts, but their incremental natural-description retrieval value above the human-training G1 lane is too small to pay for another source/mapping/fusion path. The ESCO path stays available as evidence/adjudication and can be reopened only if a new independent residual demonstrates material complement.

The next Track-2 question returns to the clean residual itself: what is the smallest build-time language representation that can bridge a phrase such as `kemisk-tekniska produkter ... städning` to `Städmaterial` **without** adding runtime inference or broadly degrading the validated candidate? Any such representation must be evaluated as a new candidate and independently validated before promotion.

Evidence: `research/evaluation/v31/skill-g1-esco-complement.json`; run `34061580681`, artifact `9997634154`.
