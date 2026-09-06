# Validated human training-language skill fallback — taxonomy v31

**Status:** independently validated Track-2 candidate  
**Candidate:** `KV-G1-4slot`

## Result

The strongest simple KV description-search increment found so far does not use embeddings, a runtime language model or generated retrieval text. It uses existing Arbetsförmedlingen labour-market-training descriptions whose learning outcomes have been manually mapped to skill identities.

The retrieval policy is deliberately conservative:

```text
KV-C0
  = P80 skill preferred label
  + real canonical definition
  + canonical alternative labels

KV-G1-single-desc
  = C0
  + build-time descriptions from other AF training modules
    that map to exactly one P80 skill

KV-G1-4slot result list
  = keep C0 rank 1
  + admit up to four unique G1 candidates
  + fill remaining ranks from C0
```

Only AF v31 `skill` identities may be returned. Training text is retrieval evidence, never a new canonical synonym/definition/identity.

## First fresh holdout

The original fresh natural-description holdout contains 35 source-attested, manually mapped descriptions. None of its module IDs or normalized description text entered G1 retrieval evidence.

| configuration | Discovery Hit@5 | weighted Discovery Hit@5 |
|---|---:|---:|
| KV-C0 | 31.429% | 34.734% |
| KV-G1-4slot | **88.571%** | **82.769%** |

This slice had already been opened when the 3-slot/4-slot fusion policies were compared, so it is development evidence for the final fusion choice rather than its final independent validation.

## Second blind holdout

A second benchmark was therefore built before either predeclared fusion candidate was evaluated. The builder contains no retrieval/model code. It excludes all module IDs and normalized texts from the earlier 76-case development benchmark and the first 35-case holdout, then deterministically chooses one clean unused module per remaining unique P80 skill.

Frozen benchmark:

- 20 cases;
- SHA-256 `3960fd217deb9d7346fd78d4f281a62b614ce927e18e4ed12cbebec08a898aa7`;
- exactly one P80 target per case;
- no direct target-label leakage;
- non-terse descriptions.

Before evaluation, both the first and second holdouts were removed from G1 retrieval evidence. The 3-slot and 4-slot policies were already declared and were not retuned after seeing the new results.

| configuration | top-1 | Discovery Hit@5 | weighted Hit@5 | Hit@10 |
|---|---:|---:|---:|---:|
| KV-C0 | 20.0% | 30.0% | 19.639% | 30.0% |
| C0 top1 + 3 G1 slots | 20.0% | 75.0% | 84.623% | 80.0% |
| **C0 top1 + 4 G1 slots** | **20.0%** | **85.0%** | **89.331%** | **85.0%** |

The 4-slot candidate leaves three Hit@5 misses.

## Canonical safety

The bounded fusion preserves C0 rank 1. On the frozen 617-case canonical KV source-truth regression it therefore remains:

- top-1: **100%**;
- Discovery Hit@5: **100%**;
- Hit@10: **100%**.

Blanket G1 ranking is not adopted: it improves description top-1 but introduces small canonical regressions. The bounded fusion intentionally optimises the current v0 objective — a small recognisable candidate set — rather than pretending that description top-1 is already solved.

## Interpretation

This is strong evidence for the Track-2 description-fallback hypothesis on the measured P80 skill slice. It is not a claim that 85% of production users will succeed, nor that all 6,752 skills have equivalent natural-language evidence.

The important architectural result is simpler:

> **Existing human-curated AF text already supplies a large semantic increment. Do not manufacture new semantics or add neural runtime complexity while this cheaper evidence remains sufficient.**

The remaining residual should be classified before another capability is added. Any new retrieval feature chosen after inspecting those misses needs new independent validation before promotion.

Evidence:

- frozen summary: `research/evaluation/v31/skill-training-language-validated.json`;
- first fusion run: `34059728835`;
- second independent validation run: `34059968131`;
- second frozen benchmark: `research/benchmark/v31/training-skill-second-holdout/`.
