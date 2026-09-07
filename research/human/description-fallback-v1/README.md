# Human description study v1 — data boundary

This directory contains only the study protocol boundary until real human evidence exists.

Do **not** seed it with model-authored examples, prior AF training descriptions or hand-written “representative users”. Those already have separate regression roles and do not satisfy the human gate.

The capability study uses three ordered exports:

1. `elicitation.jsonl` — approved/redacted participant descriptions and minimal pre-retrieval metadata.
2. `adjudication.jsonl` — blind taxonomy review, still before retrieval.
3. `outcomes.jsonl` — lexical/fallback results and participant recognition/selection, only after the first two exports are frozen.

Before the first real participant, copy `preregistration-template.json` to `preregistration.json`, replace every placeholder, set `status` to `frozen-before-first-participant`, set freeze metadata, review it, and commit it. Do not start collection from the template itself.

The preregistration must also pin the **exact repository commit** that will be used for retrieval. For every enabled stream it names the frozen `candidate_id` and its definition file. The current frozen boundaries are `YV-description-full-v0-canonical-router` for occupation and plain `KV-G1+T3` for skill. Changing the pinned commit or candidate after retrieval has been seen starts a new study version.

After elicitation and blind adjudication are frozen, create `manifest.json` with the repository tool. The manifest binds three SHA-256 values: preregistration, elicitation and adjudication. Because the retrieval commit and candidate definitions live inside the preregistration, `preregistration_sha256` also freezes the exact retrieval candidate transitively. Retrieval must not run before that manifest exists and must run from the pinned commit.

Raw identifiable research material is **not** automatically a repository artifact. Repository-bound text must be approved/redacted. Production telemetry must not copy raw free text here merely to measure uptake.

## Need/prevalence is a separate aggregate dataset

These case files cannot estimate how common the need is, because they contain only people who reached/submitted the study flow.

Production prevalence requires an aggregate denominator such as:

- eligible lexical-failure/retry exposures;
- fallback offers/views;
- fallback opens;
- fallback submissions;
- selections / `none`.

Those funnel counts do not require raw free text. A recruited or prompted human study may report stated willingness/usefulness, but must not label that as production uptake or prevalence. Format: `need-funnel-format.md`.

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

The legacy `in_frozen_demand_envelope` field is stored **per target**, but its meaning is stream-specific. For `skill`, it records membership in the frozen 316-skill P80 capability envelope and mixed inside/outside ambiguous cases are valid. For `occupation`, the frozen capability universe is all **2,105 active v31 `occupation-name` identities**, so every valid active occupation target must set the field to `true`; P80/non-P80 is a separate demand-priority reporting stratum. Never coerce a valid non-P80 occupation to the nearest P80 identity merely to make Hit@5 calculable.

## Freeze before retrieval

Create the manifest only after preregistration, elicitation and blind adjudication are final:

```bash
python scripts/freeze_human_description_study_manifest.py \
  --preregistration <path>/preregistration.json \
  --elicitation <path>/elicitation.jsonl \
  --adjudication <path>/adjudication.jsonl \
  --output <path>/manifest.json
```

The freeze tool refuses to overwrite an existing manifest. Verification rejects a preregistration whose pinned retrieval commit or enabled-stream candidate differs from the frozen simple boundary, and any post-freeze edit changes `preregistration_sha256` and invalidates the manifest.

## Outcome record

Only after the manifest exists:

- `case_id`.
- `lexical_top5_ids`.
- `fallback_top5_ids`.
- `participant_recognized_ids` — subset of `fallback_top5_ids`.
- `participant_selected_id` — recognized fallback candidate or `null` for none.
- `clarification_was_offered`: boolean.

Occupation and skill outcomes are reported separately.

## Verification

Verify the complete frozen chain:

```bash
python scripts/verify_human_description_study.py \
  --preregistration <path>/preregistration.json \
  --elicitation <path>/elicitation.jsonl \
  --adjudication <path>/adjudication.jsonl \
  --manifest <path>/manifest.json \
  [--outcomes <path>/outcomes.jsonl] \
  [--funnel <path>/need-funnel.json]
```

The staged validator enforces stage separation, hash freezes, unique IDs, stream-specific per-target capability-universe semantics and adjudication/outcome invariants. The wrapper additionally proves that the manifest is bound to the frozen preregistration, including the pinned retrieval commit and stream candidates. It also rejects obvious email addresses and Swedish-style phone-number patterns in repository-bound description text. That regex guard is only a backstop, not a privacy review.

Contract self-test fixtures are generated only in a temporary directory and are never research evidence:

```bash
python scripts/selftest_human_description_study.py
python scripts/selftest_human_description_preregistration.py
```

Protocol and decision rules live in `docs/findings/description-fallback-human-validation-protocol-v31.md` and `research/evaluation/v31/description-fallback-human-validation-contract.json`.
