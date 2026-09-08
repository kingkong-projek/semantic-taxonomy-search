# Gemma 4 YV teacher A0/A1 — quality and sparse-fusion diagnostic

**Date:** 2026-09-08  
**Status:** opened architecture evidence; no runtime promotion

## Question

Does zero-marginal-cost Gemma 4 generation contain useful Swedish description language for YV, and can the first 149 generated occupation documents improve the existing full-universe canonical BM25 without breaking the simple-first/canonical guards?

## Frozen teacher source

The teacher run used `gemma-4-26b-a4b-it` with public JobTech Taxonomy v31 preferred label, definition and alternative labels only. No opened evaluation/stress query was teacher input.

- generation run: `34189574629`
- head: `d521562463d0316b01e4e997a15b414732a0a727`
- artifact: `10042936282`
- JSONL SHA-256: `1a6e26840480d0cd6ffce23e3214d026cefa202397f4e84115e9fe2ac1e1045b`
- 150 requested occupations; 149 succeeded; 1 (`Mediasäljare`) failed structured output
- 8 phrases per successful occupation = 1,192 phrases

## Quality audit

The corpus is useful synthetic expansion evidence, not canonical truth.

A query-independent audit/filter found:

- 104/1,192 phrases contain at most two tokens;
- 7 normalized phrase values are exact duplicates globally (7 excess occurrences);
- one exact duplicate occurs within the same occupation;
- 3 phrases contain the target preferred/alternative surface despite the prompt prohibition;
- 9 phrases use clearly undesirable stereotyped colloquialisms such as `elgubbe`, `butikstjejer` or `ekonomipamp`.

The frozen mechanical filter removes within-concept duplicates, preferred/alternative-label leaks and the small predeclared stereotyped-colloquial stem set. It does **not** inspect evaluation queries, scores or retrieval outcomes. 1,179 phrases remain.

This is intentionally a narrow hygiene filter. It does not certify factual correctness. Manual review also found weak/generic phrases and some claims whose support in the supplied evidence is uncertain; future generation must therefore constrain source entailment more tightly rather than treating plausible teacher knowledge as evidence.

## A0 — direct document concatenation

A0 compared the existing 2,105-occupation canonical BM25 with the same documents extended by the eight Gemma phrases for the 149 covered occupations. Raw and mechanically filtered variants produced the same measured rankings.

### Canonical regression guard

| candidate | Top1 | Hit@5 | MRR |
|---|---:|---:|---:|
| canonical baseline | 333/333 | 333/333 | 1.000000 |
| filtered Gemma concat | 330/333 | 333/333 | 0.994995 |

Three frozen canonical ranks changed. This alone rejects document concatenation under the current guard.

### Strict source-attested work-task diagnostic

| candidate | Top1 | Hit@5 | MRR |
|---|---:|---:|---:|
| canonical baseline | 6/17 | 9/17 | 0.418849 |
| filtered Gemma concat | 6/17 | 9/17 | 0.443722 |

Only 2/17 targets are among the teacher-covered top-149 occupations, so this bounded corpus cannot establish broad YV accuracy. A provenance-separated canonical+teacher oracle reaches 10/17 Hit@5, showing at least one complementary recovery that concatenation does not preserve.

### Opened stress diagnostic

Hit@5 changes from canonical → filtered concat:

- direct: 8/12 → 10/12
- colloquial: 2/12 → 3/12
- noisy: 5/8 → 7/8
- indirect: 3/8 → 4/8

The separate canonical+teacher oracle is much stronger on colloquial input: 7/12. This is architecture/complementarity evidence only; the stress set is already opened and must not select a production rule.

**A0 decision:** reject canonical+teacher concatenation. The generated sequence-level language contains useful signal, but mixing it into canonical documents both loses complementarity and perturbs the protected canonical ranking. BM25 document-length effects are a plausible mechanism, consistent with earlier numeric-expansion regressions, but the rejection does not depend on proving that mechanism.

## A1 — one guarded teacher slot

A1 froze one minimal fusion before evaluation:

`canonical rank 1 -> one positive-score filtered teacher-BM25 candidate -> remaining canonical order`

It intentionally protects canonical rank 1 and does not tune weights, thresholds or slot counts.

### Results

- canonical source-truth: 333/333 Top1, 333/333 Hit@5, MRR 1.0, zero rank changes;
- strict 17 cases: Hit@5 stays 9/17; MRR 0.418849 → 0.433067;
- opened stress Hit@5:
  - direct 8/12 → 8/12
  - colloquial 2/12 → 3/12
  - noisy 5/8 → 5/8
  - indirect 3/8 → 4/8.

The more important failure is abstention/calibration. On the 13 opened cases that should abstain or have no expected family and should clarify, the teacher lane has positive lexical evidence on **11/13**. Examples include:

- `Jag hjälper människor` → `Kock storhushåll`
- `och av på ut med till för från` → `Rekryterare/Rekryteringskonsult`
- `Min chef är dum och kaffet är slut` → `Biträdande rektor`

A positive teacher BM25 match is therefore not a confidence signal.

**A1 decision:** reject unconditional one-slot teacher fusion. It preserves the canonical guard but earns no strict-source Hit@5 gain, produces only small opened-stress improvements, and exposes the exact weak-input failure the product contract requires us to solve.

## Conclusion and next action

The experiment falsifies two simple implementations without falsifying the teacher-language hypothesis:

1. **Retain:** sequence-level Gemma language as provenance-separated candidate evidence. The opened stress oracle shows meaningful complementary colloquial/indirect reach.
2. **Reject:** raw teacher text as truth, canonical-document concatenation, and unconditional one-slot fusion.
3. **Do next:** harden teacher generation using source-only quality rules, expand teacher coverage beyond the current 149 high-demand occupations, and keep the generated language in a separate representation.
4. **Hard gate:** abstention/calibration must be designed and measured alongside retrieval. A nearest lexical teacher hit cannot be interpreted as confidence.
5. **Evidence discipline:** do not tune further on these opened A0/A1 cases and do not promote a runtime candidate from them. Fresh independent stream-separated evidence remains required.

Structured result: `research/evaluation/v31/gemma4-yv-teacher-a0-a1.json`.
