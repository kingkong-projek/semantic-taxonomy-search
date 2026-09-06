# Skill lexical rescue — taxonomy v31

**Decision status:** negative development result; do not adopt this lane.

The benchmark had already been opened by KV-C0, so this is development evidence only.

## Hypothesis

Maybe the first natural-text skill residual is mostly Swedish inflection/compound mismatch rather than missing semantic text.

The experiment kept KV-C0 retrieval documents unchanged and built a second surface ranker from canonical skill preferred/alternative-label tokens only. Signals were deterministic:

1. exact token;
2. token component/substring;
3. common-prefix similarity;
4. bounded edit distance.

Fusion preserved C0 rank 1 and offered at most one or two of the remaining top-5 slots to surface candidates.

## Primary 63-case result

| configuration | Discovery Hit@5 | occurrence-proxy weighted Hit@5 |
|---|---:|---:|
| KV-C0 | 46.032% | 57.083% |
| one surface-rescue slot | 42.857% | 43.341% |
| two surface-rescue slots | 41.270% | 39.025% |

A surface-only top-5 finds 26.984% of the primary cases. Even an oracle that counts a case solved when **either** C0 top-5 or surface-only top-5 contains the target reaches only 49.206% — just two cases above C0.

Among the 34 primary C0 misses:

- 19 have no target-label morphology signal at all;
- 4 have an exact target label token somewhere in the long query;
- 8 have component/substring evidence;
- 3 have common-prefix evidence;
- none require only the bounded-edit-distance class.

Thus surface morphology exists in some misses but is not discriminative enough to rank the correct skill reliably among 316 P80 skills.

## Regression

Because fusion preserves C0 rank 1, all three configurations remain 100% top-1 and Discovery@5 on the frozen 617-case canonical KV source-truth suite.

## Decision

Do not add more fuzzy/stemming/compound heuristics now. The residual is predominantly semantic rather than orthographic.

The next justified layer is richer semantic text using the safest already-pinned mapping first: v31 skill → `exact_match` → `esco-skill`. ESCO mapping types remain separate; do not collapse exact/broad/narrow/close. Start with exact only and use ESCO text as retrieval evidence, never as a replacement AF identity.

Like C0, this entire path remains compatible with a static frontend data package: ESCO-derived retrieval text can be compiled at build time. The experiment creates no runtime API requirement.
