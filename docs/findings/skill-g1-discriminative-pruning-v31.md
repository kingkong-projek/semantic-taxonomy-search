# Discriminative pruning of KV G1 training language — v31

**Status:** negative development result; keep the full validated G1 representation.

After typed ESCO failed to add material natural-description recall, the next cheaper hypothesis was that G1 might contain too much generic training text. This ablation added no source and no runtime mechanism. It kept canonical C0 intact, ranked enrichment terms per skill by corpus rarity plus log-saturated within-skill frequency, and retained only the top 8/16/32/64/128 unique terms before applying the same fixed `C0 rank 1 + four G1 slots` policy.

Both source-attested natural holdouts were already open and were excluded from G1 evidence. The result is therefore development evidence only.

## Result

The unpruned later diagnostic shape is:

- first 35-case slice: 91.429% Hit@5 / 84.632% weighted;
- second 20-case slice: **85.0% Hit@5 / 89.331% weighted**;
- synthetic KV stress: 66.667% Hit@5;
- canonical regression: 100% Hit@5.

The least aggressive pruning, K=128, retains 69.238% of unique skill→enrichment-term pairs. It improves the older first slice to 94.286% and synthetic stress to 75%, but the more important second natural slice falls to **75.0% / 84.623% weighted** and creates two additional misses. K=64 and K=32 fall to 70% on the second slice; K=16 and K=8 remain at 75% with substantially worse weighted results.

All variants preserve the canonical 617-case suite because C0 rank 1 remains privileged.

## Decision

Do **not** prune G1 into a small discriminative keyword list. The apparent gains on already-open development/synthetic slices do not generalize across the second natural slice. Full human training descriptions are currently the safer static representation.

This also sharpens the residual diagnosis: the clean `Städmaterial` case is not primarily a document-noise problem. Its held-out phrase about chemical-technical cleaning products is genuinely absent from the allowed G1 target text. The next candidate, if any, must add missing **build-time semantic language** rather than merely rearrange or delete existing words.

Any such representation must be created without ingesting benchmark queries and must be independently validated on a new unopened source-attested holdout before it can replace `KV-G1-4slot`.

Evidence: `research/evaluation/v31/skill-g1-discriminative-pruning.json`; run `34061833973`, artifact `9997714040`.
