# Human description study v1 — data boundary

This directory is intentionally empty until real human evidence exists.

Do **not** seed it with model-authored examples, prior AF training descriptions or hand-written “representative users”. Those already have separate regression roles and do not satisfy the human gate.

The study uses three ordered exports:

1. `elicitation.jsonl` — approved/redacted participant descriptions and minimal metadata, before taxonomy adjudication or retrieval.
2. `adjudication.jsonl` — blind taxonomy review, still before retrieval.
3. `outcomes.jsonl` — lexical/fallback results and participant recognition/selection, only after the first two exports are frozen.

A study `manifest.json` must record SHA-256 hashes of the frozen elicitation and adjudication files before outcomes are produced.

Raw identifiable research material is **not** automatically a repository artifact. The repo export should contain only text approved for this study, preferably redacted. Production telemetry should not be copied here as raw free text without an explicit data-handling basis.

## Elicitation record

Required fields:

- `case_id`: study-local stable identifier.
- `stream`: `occupation` or `skill`.
- `participant_id`: pseudonymous identifier.
- `description_redacted`: the approved study text; retrieval must not have been run before it was frozen.
- `language`: e.g. `sv`, `en`.

Optional pre-retrieval metadata may include `title_known`, `lexical_attempt_redacted`, `recruitment_stratum` and non-identifying sector/language strata. Do not include retrieval ranks, candidate IDs or adjudication output.

## Adjudication record

Required fields:

- `case_id`.
- `status`: `mapped`, `ambiguous`, `clarification-needed`, `unmappable` or `out-of-scope`.
- `acceptable_canonical_ids`: zero or more canonical IDs. `mapped` requires at least one; `ambiguous` requires at least two.
- `in_frozen_demand_envelope`: `true`, `false` or `null` when no target is mapped.
- `adjudicator_ids`: pseudonymous reviewer IDs.
- `retrieval_blind`: must be `true`.

An adjudicator may map multiple defensible identities. Never invent a single target merely to make Hit@5 calculable.

## Outcome record

Only after elicitation/adjudication hashes are frozen:

- `case_id`.
- `lexical_top5_ids`.
- `fallback_top5_ids`.
- `participant_recognized_ids`.
- `participant_selected_id`: canonical ID or `null` for none.
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

The validator enforces stage separation, hash freezes, unique IDs and the basic adjudication invariants. It also rejects obvious email addresses and Swedish-style phone-number patterns in repository-bound description text. That regex guard is only a backstop, not a privacy review.

Protocol and decision rules live in `docs/findings/description-fallback-human-validation-protocol-v31.md` and `research/evaluation/v31/description-fallback-human-validation-contract.json`.
