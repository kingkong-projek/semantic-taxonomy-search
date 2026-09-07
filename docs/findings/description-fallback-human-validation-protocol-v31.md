# Description fallback — independent human validation protocol

## Why this is the next gate

Retrieval micro-optimization is now stopped. The open question is no longer whether another BM25 variant can move a synthetic score; it is whether the proposed fallback solves a real user problem.

The product hypothesis is deliberately bounded:

> When ordinary title/skill lookup is insufficient, some users can describe what they do or can do more reliably than they can name the taxonomy concept. A secondary description route may therefore surface a small canonical candidate set they can recognise and select.

This is a hypothesis, not a premise. The study must be able to conclude that the fallback is unnecessary, undiscoverable, hard to express into, or insufficiently accurate.

Structured contract: `research/evaluation/v31/description-fallback-human-validation-contract.json`.
Operational data boundary: `research/human/description-fallback-v1/README.md`.

## Keep three questions separate

### 1. Does the need exist?

Observe actual lexical failure/retry/abandonment situations or recruit people specifically from that state. Measure whether they can and want to describe the underlying job/competence instead of trying another taxonomy word.

A successful retrieval benchmark does not establish prevalence. Conversely, a common lexical failure does not prove semantic retrieval solves it.

A recruited/prompted human capability study also does **not** establish production prevalence, because everyone in that study has already reached the description task. Production uptake needs a separate aggregate denominator: eligible lexical-failure/retry exposures, fallback offers, opens, submissions and selections. Those counts do not require raw query/description text. Format: `research/human/description-fallback-v1/need-funnel-format.md`.

### 2. Can people express enough evidence?

The first benchmark must **not show examples**. Ask for tasks, tools/systems, environment/method and responsibility/result, but do not seed occupational or skill vocabulary.

If a description is too vague, record `clarification-needed`. Do not repair it behind the scenes. That outcome tests the interaction hypothesis: perhaps a one-question clarification is needed, or perhaps description fallback is not intuitive enough.

### 3. Can the frozen simple candidate map that evidence?

Only after participant text and blind taxonomy adjudication are frozen may retrieval run. Compare ordinary lexical search and the frozen simple fallback on exactly the same description.

For skills the candidate is plain `KV-G1+T3`. The favorable query-only numeric tweak is not part of the candidate because it lacks independent validation.

Occupation and skill are separate streams. KV evidence must never be quoted as occupation accuracy.

## Blinded evidence order

For each case:

1. capture a participant description without retrieval output;
2. freeze the description and minimal non-sensitive metadata;
3. have a taxonomy-domain reviewer, blind to retrieval, assign zero, one or multiple acceptable canonical identities;
4. record demand-envelope membership **per acceptable identity**, then freeze the adjudication;
5. record SHA-256 hashes for elicitation and adjudication in the study manifest;
6. run ordinary lexical baseline and the frozen simple fallback;
7. show fallback candidate labels to the participant and record what they recognise/select, including `none`;
8. only then classify the residual.

Multiple acceptable canonical identities are valid. A person describing overlapping work must not be forced into a fake single-label ground truth.

For KV, each acceptable target is independently marked inside/outside the frozen 316-skill P80 envelope. An out-of-envelope target is a coverage result, not a retrieval miss, and must not be silently replaced with the nearest P80 skill. Apply the equivalent per-target envelope check to occupation discovery. Mixed ambiguous cases are therefore representable: one defensible identity may be inside the envelope while another is outside it.

## What to measure

Report two groups of metrics rather than one headline score.

**Need/expressibility:** observed production uptake only when an eligible lexical-failure denominator exists; otherwise stated willingness/usefulness must be labeled as such. Also report sufficiently-informative-description rate, clarification-needed rate and demand-envelope coverage.

**Capability:** acceptable-target Hit@5, paired Hit@5 delta versus ordinary lexical lookup, participant recognition@5, selected-candidate/none rate, and the complete residual distribution. Participant-recognised identities must be a subset of the actually shown fallback top 5.

Always report numerator/N, unique participants and unique target identities. Wilson intervals may describe uncertainty for proportions; occurrence weights are not independent trials.

Do not pool occupation and skill into one accuracy number.

## Residual taxonomy

Every failure should land in one of these buckets before anyone proposes another model:

- insufficient description;
- taxonomy ambiguity / several defensible identities;
- target outside current demand envelope;
- missing source/evidence coverage;
- retrieval/ranking miss despite adequate in-envelope evidence;
- participant rejects the blind adjudication;
- UI/discoverability failure.

Only the fifth bucket is direct evidence for stronger retrieval semantics.

## Burden of proof for more model complexity

One miss is not a reason to add embeddings. Before testing a higher model class we need a set of independent human cases that were frozen before retrieval, have adequate discriminating detail, have at least one blind acceptable target inside the current envelope, and still fail the simple candidate across multiple participants and target identities.

Any case used as positive evidence for escalating model complexity should receive stronger adjudication than an exploratory pilot case — preferably at least two independent taxonomy reviewers or an explicitly preregistered conflict-resolution step — before it is allowed to drive architecture.

Residual review must show that retrieval semantics — rather than coverage, taxonomy, source evidence, UI wording or ambiguity — is the dominant problem. A more complex candidate must then be frozen **before a new independent holdout**.

This protects the project from gradually turning every discovered edge case into another runtime mechanism.

## Modal/examples are a separate experiment

The proposed modal with examples can still be good product design, but examples contaminate the primary expressibility measurement by anchoring vocabulary.

First measure natural descriptions without examples. Then test example copy separately for discoverability and completion. Good example copy should vary sector and description shape, demonstrate tasks rather than sneak in target titles, and avoid prompting names, employers or sensitive personal details.

## Product boundary

Ordinary YV/KV stays primary for users who know roughly what to type. Description fallback is an explicit secondary route.

The occupation + commuting-municipality omnibox is another product hypothesis. Location parsing/filtering should remain deterministic and independently testable; it must not become justification for routing ordinary location input through semantic occupation classification.

## Privacy and data handling

Participants should be instructed not to provide names, personal identifiers, employer identifiers or unnecessary sensitive personal information. Use pseudonymous participant IDs. Raw research descriptions require an approved data-handling basis; ordinary production funnel telemetry should not store raw free text by default merely to measure uptake and completion.

Repository-bound study text is an approved/redacted export, not the raw research archive. The validator's email/phone checks are only a backstop and do not replace privacy review.

Published findings should use aggregate metrics and carefully redacted examples.

## Pre-registration before collection

Before the first real participant is enrolled, freeze the recruitment source, intended sample size or stopping rule, language/sector stratification, adjudicator procedure, data-handling basis and any exclusion rules. Do not choose those after seeing retrieval outcomes.

The staged case schema is versioned before collection. Changing target/envelope semantics after seeing retrieval output starts a new study version; it does not silently rewrite the old holdout.

Synthetic/model-authored descriptions remain useful regression fixtures, but they can never satisfy this human evidence gate.
