# KV G1 human-text variant ablation — taxonomy v31

**Status:** negative exploratory result; retain validated `KV-G1-4slot-single-desc`.

After the three second-holdout misses were inspected, the smallest already-owned representation changes were compared under the **same fixed 4-slot fusion**. This is therefore development evidence, not a new independent validation.

All first- and second-holdout module IDs/texts remained excluded from every retrieval lane. No source, tokenizer, BM25 parameter, slot count or runtime mechanism changed.

## Variants

- `single-desc`: validated baseline; canonical text + descriptions from modules mapping to exactly one P80 skill.
- `single-name-desc`: same, plus the existing AF module name.
- `all-desc`: broad control; descriptions from all non-holdout modules are attached to each mapped P80 skill.

## Result

| 4-slot lane | first natural Hit@5* | second Hit@5 (post-hoc) | weighted second | synthetic Hit@5 | canonical top1/Hit@5 |
|---|---:|---:|---:|---:|---:|
| **single-desc** | **91.429%** | **85.0%** | **89.331%** | **66.667%** | 100% / 100% |
| single-name-desc | 88.571% | 85.0% | 89.304% | 66.667% | 100% / 100% |
| all-desc | 88.571% | 75.0% | 84.623% | 50.0% | 100% / 100% |

\*This later diagnostic shape excludes **both** natural holdouts from G1 evidence. It must not replace the independently frozen 88.571% first-holdout headline from the earlier validation sequence.

Module names move the already-inspected `Produktionsplanering, tillverkning` case from fused rank 40 to rank 5, but that local rescue does not improve aggregate second-holdout Hit@5 and slightly worsens the weighted score. It also loses a case on the first natural slice. This is exactly the kind of post-hoc win that should **not** trigger candidate promotion.

The broad `all-desc` lane is worse: second-holdout Hit@5 falls to 75% and synthetic Hit@5 to 50%. More human text is therefore not automatically better semantic evidence when attribution is ambiguous.

## Decision

Keep `KV-G1-4slot-single-desc` unchanged. Do not build a third blind holdout merely to validate a representation that failed to beat the current candidate in development evidence.

The remaining residual should next be investigated by **coverage diagnostics**, not weight/representation tuning: determine whether already-pinned semantic mappings (especially typed ESCO mappings) materially cover the three residual targets and whether their text contains the missing distinctions. A new retrieval lane is justified only if that diagnostic shows plausible residual coverage.

Evidence: `research/evaluation/v31/skill-g1-text-variant-fusion.json`; run `34061286183`, artifact `9997541822`.
