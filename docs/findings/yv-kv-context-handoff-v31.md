# YV → KV occupation-context handoff — taxonomy v31

## Problem

KV accepts occupation-name or SSYK4 identity as occupation context. A YV job-title selection carries its contextual occupation in `selection.related.id`.

The stepped repo demo previously passed `selection.id` directly to KV. For a job-title that value is the job-title ID, so KV cannot recognize it as occupation context and falls back to context-free/global behaviour.

## Branch-local fix

On `kingkong-projek/yrkesvaljaren` branch `fix/canonical-alias-search`, the integration now resolves context as follows:

- job-title → `selection.related.id`, but only when `related.type === 'occupation-name'`;
- occupation-name → `selection.id`;
- malformed, missing or unrelated selections → empty context / fail closed.

This work remains **unmerged**. GitHub PR #38 is draft/DO NOT MERGE; the protected GitLab `main` remains authoritative.

## Verification

Self-hosted `garderob` run `34056120385`, job `101548226190`, passed end to end.

Resolver unit regression:

- 4/4 passed;
- verifies job-title related occupation identity;
- verifies occupation-name identity;
- verifies malformed job-title fail-closed behaviour;
- verifies unrelated/missing selection fail closed.

Chromium browser regression (`tests/e2e/05b-yv-kv-context-handoff.spec.ts`):

- **2/2 passed**;
- a job-title event assigns its related occupation-name ID to `#stepped-kv`'s `af-occupation-id`;
- the job-title ID is explicitly not used;
- KV subsequently exposes occupation-specific `vanligast för yrket` behaviour;
- an occupation-name selection keeps its own ID.

The same run also completed the full branch build and E2E preparation before the browser test.

## Decision

The accessible YV→KV integration-path Track-1 exit criterion is satisfied for this branch implementation. The original demo footgun is no longer merely source-theoretical: the corrected identity path has deterministic unit coverage and browser-level behaviour coverage.

This does **not** claim deployment or merge. The branch must remain unmerged on GitHub and be carried through the normal protected GitLab process separately.
