# Semantic Top-5 relevance oracle v0 — result (2026-09-09)

## Question

Can additional candidate-level semantic information clean an already-retrieved YV Top-5 without destroying useful lower-ranked hits?

This experiment did **not** change retrieval, candidate universe or rank order and does **not** propose a runtime LLM.

## Frozen contract

- model: `gemma-4-26b-a4b-it`
- prompt: `yv-p80-semantic-display-oracle-v0`
- rank, structured target and SSYK hidden from teacher
- candidates deterministically shuffled
- source-bound evidence only: `label-alt3-definition50-task2x24-v0`
- verdicts: `keep | uncertain | drop`
- rank 1 always retained; lower ranks removed only on `drop`
- opened user-style rows unavailable to prompt/model/rule selection

Preregistration: `research/evaluation/v31/p80-display-semantic-oracle-preregistration-v0.json`.

## Primary natural 2024 proxy

Frozen result: `research/evaluation/v31/p80-display-semantic-oracle-v0.json`.

Result:

| metric | before | after |
|---|---:|---:|
| target Hit@5 | 167 | 167 |
| target hits rank 2–5 | 87 | 87 |
| safe different-SSYK4 negatives rank 2–5 | 2,469 | 908 |
| mean visible list | 5.00 | 2.669 |

Safe cross-SSYK4 tail-negative reduction was **63.224%**. Target retention was 100% at every rank represented in the target set: `80/80`, `37/37`, `18/18`, `19/19`, `13/13` for ranks 1–5.

The preregistered **strong gate passed**.

Sampling note: the result file contains 674 evaluation rows but 672 unique case keys because two ad/query rows are exact duplicates. They carry the same target, candidates and judgments. Report this explicitly; do not treat 674 as 674 independent cases.

## Exact frozen opened replay

Frozen result: `research/evaluation/v31/p80-display-semantic-oracle-opened-replay-v0.json`.

Aggregate transfer was strong:

| metric | before | after |
|---|---:|---:|
| targetable Hit@5 | 28 | 28 |
| targetable rank-2–5 hits | 13 | 13 |
| mean visible list | 4.593 | 2.519 |
| full five-result lists | 49 | 5 |

The electrician product sanity (`yv02`) passed.

The preregistered opened acceptance nevertheless **failed**. In `yv01` the oracle retained the nursing-family results and dropped `Sjukhusvaktmästare`, but classified both `Apotekare` and `Receptarie` as `uncertain`. The frozen product check required at least two of those three known-bad candidates to be removed while a nursing-family result remained.

Therefore `prefrozen_opened_acceptance_passed=false` is the authoritative outcome. The excellent aggregate metrics do not convert this into a pass.

## Interpretation

Two conclusions can both be true:

1. **Semantic candidate information is the first display mechanism tested here that shows a large, reproducible capability advantage over lexical/SSYK-derived filtering while preserving all observed useful lower-rank hits.**
2. **v0 is not sufficient for distillation.** Its compact source-bound evidence can leave plausible adjacent-domain roles unresolved as `uncertain`.

The failure is narrower than the earlier lexical failures. The residual is no longer “can we remove irrelevant tails at all?” It is “can source-bound candidate evidence reliably distinguish plausible nearby roles without over-dropping legitimate alternatives?”

## Decision

- Do not distill v0.
- Do not retune on `yv01`, `yv02`, or any opened 17/88 row.
- Keep opened rows replay/falsification-only.
- Continue semantic candidate relevance research using **independent source-bound hard-confusion evidence**.
- Any v1 evidence/prompt change must be motivated and developed without opened outcomes, preregistered before evaluation, and evaluated on untouched independent data before opened replay.
- Retrieval/rank order stay frozen during this work.
- Runtime LLM/provider API remains out of scope.

## Next hypothesis

Existing independent compile-time confusion work indicates that richer task/responsibility evidence can expose role distinctions without feeding contrast cues to the generator. The next experiment should therefore test **richer candidate-specific discriminative evidence**, not another score threshold.

Relevant prior independent mechanism artifact: `research/evaluation/v31/compile-time-semantic-a593-confusion-task-atoms-v0.json` (11 pairs / 22 concepts, `contrast_cues_or_descriptions_sent_to_generator=false`).
