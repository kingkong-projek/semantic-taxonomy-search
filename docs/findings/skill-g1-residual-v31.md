# KV G1 residual classification — taxonomy v31

**Status:** frozen diagnostic; no retrieval change  
**Validated baseline:** `KV-G1-4slot`

The independently validated second holdout leaves 3/20 Discovery Hit@5 misses. They are not one failure class, so they must not be used as three interchangeable tuning targets.

## 1. Kabelinstallationer

Target: `Kabelinstallationer` (`VQxj_dHG_UCE`), occurrence proxy 205.

- C0: no positive rank;
- G1: rank 8;
- fused 4-slot: not surfaced;
- four allowed non-holdout training descriptions already provide target evidence;
- target/query lexical overlap is substantial (21 shared unique tokens).

This is primarily **ranking separation in long technical text**, not absence of source language. Generic electrical/installation/fault-finding vocabulary gives other P80 skills higher BM25 scores.

There is also an evaluation-envelope boundary: the held-out training module is manually mapped to several non-P80 skills, including `Gatubelysning, installation och underhåll`, which is more directly named by the query than the single P80 target. The benchmark's exactly-one-P80 construction is useful for controlled measurement but must not be mistaken for proof of unique user intent.

## 2. Städmaterial

Target: `Städmaterial` (`iu18_YyQ_hmh`), occurrence proxy 108.

- C0: no positive rank;
- G1: rank 7;
- fused 4-slot: not surfaced;
- three allowed non-holdout source descriptions exist;
- only four unique query tokens overlap the target G1 document.

This is the cleanest **missing semantic phrase/source-coverage** case. The held-out query is specifically about kemisk-tekniska produkter and their cleaning uses. Existing non-holdout `Städmaterial` descriptions instead cover ergonomics/hygiene, tools and cleaning machines. The needed language is simply not present in the current source-attested target document.

`Storstädning` appears at rank 5, so the broad cleaning domain is partly recognised; the missing distinction is material/product-specific.

## 3. Produktionsplanering, tillverkning

Target: `Produktionsplanering, tillverkning` (`kvLG_4uo_M5p`), occurrence proxy 95.

- C0: rank 39;
- G1: rank 13;
- fused: rank 40;
- three allowed non-holdout source descriptions exist;
- only three unique query tokens overlap the target G1 document.

The returned top two are `Produktionsteknik` and `Ständiga förbättringar/Lean`. The held-out query explicitly says *produktionsteknik* and *Lean produktion*. Those are therefore plausible user-facing answers, while the intended target is only weakly signalled through productionsekonomi/beredning.

This is a mix of **missing target language and fine-grained intent/evaluation separation**, not a clean case where the engine is obviously semantically wrong.

## Decision

Do not tune weights, slot count, stemming, graph context or ESCO directly against these three opened cases.

The next permissible experiment is deliberately smaller: compare the already-owned human training-text variants under the same bounded 4-slot fusion, especially adding existing module names to the single-target descriptions. This adds no source, model or runtime mechanism. Because the residual has now been inspected, that comparison is development evidence only. A changed candidate can be promoted only after new independent validation.

Prior negative evidence still applies:

- broad inverted occupation context hurt retrieval and canonical safety;
- fuzzy/morphology rescue hurt Discovery Hit@5;
- blanket exact-ESCO text hurt the primary Discovery Hit@5 objective.

So the residual does **not** justify embeddings, neural runtime, more fuzzy rules or indiscriminate graph expansion.

Evidence: `research/evaluation/v31/skill-g1-residual.json`; diagnostic run `34061036918`, artifact `9997464989`.
