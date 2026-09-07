# Human description study v1 — data boundary

This directory contains only the study protocol boundary until real human evidence exists.

Do **not** seed it with model-authored examples, prior AF training descriptions or hand-written “representative users”. Those already have separate regression roles and do not satisfy the human gate.

The capability study uses three ordered exports:

1. `elicitation.jsonl` — approved/redacted participant descriptions and minimal pre-retrieval metadata.
2. `adjudication.jsonl` — blind taxonomy review, still before retrieval.
3. `outcomes.jsonl` — lexical/fallback results and participant recognition/selection, only after the first two exports are frozen.

A study `manifest.json` must record SHA-256 hashes of the frozen elicitation and adjudication files before outcomes are produced.

Raw identifiable research material is **not** automatically a repository artifact. Repository-bound text must be approved/redacted. Production telemetry must not copy raw free text here merely to measure uptake.

## Need/prevalence is a separate aggregate dataset

These case files cannot estimate how common the need is, because they contain only people who reached/submitted the study flow.

Production prevalence requires an aggregate denominator such as:

- eligible lexical-failure/retry exposures;
- fallback offers/views;
- fallback opens;
- fallback submissions;
- selections / `none`.

Those funnel counts do not require raw free text. A recruited or prompted human study may report stated willingness/usefulness, but must not label that as production uptake or prevalence.

## Elicitation record

Required fields:

- `case_id`: study-local stable identifier.
- `stream`: `occupation` or `skill`.
- `participant_id`: pseudonymous identifier.
- `description_redacted`: approved study text; retrieval must not have been run before freeze.
- `language`: e.g. `sv`, `en`.
- `entry_mode`: `observed-voluntary`, `observed-offered` or `study-prompted`.

Optional pre-retrieval metadata may include `title_known`, `lexical_attempt_redacted`, `fallback_would_use` and `recruitment_stratum`. Do not include retrieval ranks, candidate IDs or adjudication output.

## Adjudication record

Required fields:

- `case_id`.
- `status`: `mapped`, `ambiguous`, `clarification-needed`, `unmappable` or `out-of-scope`.
- `acceptable_targets`: list of `{ "canonical_id": "...", "in_frozen_demand_envelope": true|false }`.
- `adjudicator_ids`: pseudonymous reviewer IDs.
- `retrieval_blind`: must be `true`.

Status invariants:

- `mapped` = exactly one acceptable target;
- `ambiguous` = at least two acceptable targets;
- `clarification-needed`, `unmappable`, `out-of-scope` = zero targets.

Envelope membership is stored **per target**. This matters when an ambiguous description has one defensible identity inside P80 and another outside it. Never invent a single target merely to make Hit@5 calculable.

## Outcome record

Only after elicitation/adjudication hashes are frozen:

- `case_id`.
- `lexical_top5_ids`.
- `fallback_top5_ids`.
- `participant_recognized_ids` — subset of `fallback_top5_ids`.
- `participant_selected_id` — recognized fallback candidate or `null` for none.
- `clarification_was_offered`: boolean.

Occupation and skill outcomes are reported separately.

## Validation

Run:

```bash
python scripts/validate_human_description_study.py \
  --elicitation <path>/elicitation.jsonl \
  --adjudication <path>/adjudication.jsonl \
  --manifest <path>/manifest.json \
  [--outcomes <path>/outcomes.jsonl]
```

The validator enforces stage separation, hash freezes, unique IDs, per-target envelope semantics and adjudication/outcome invariants. It also rejects obvious email addresses and Swedish-style phone-number patterns in repository-bound description text. That regex guard is only a backstop, not a privacy review.

Contract self-test fixtures are generated only in a temporary directory and are never research evidence:

```bash
python scripts/selftest_human_description_study.py
```

Protocol and decision rules live in `docs/findings/description-fallback-human-validation-protocol-v31.md` and `research/evaluation/v31/description-fallback-human-validation-contract.json`.
