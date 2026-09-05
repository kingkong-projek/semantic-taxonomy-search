# Deprecated compatibility coverage — taxonomy v31

**Status:** measured; Gate-1 requirement closed  
**Measured:** 2026-09-06  
**Workflow run:** `33995216353`  
**Artifact:** `deprecated-compatibility-v31` (`9977844140`)

The replacement graph was measured on the self-hosted Linux/X64 runner against taxonomy v31 and the published YV v31 destination space.

## Result

YV/KV-relevant deprecated concepts: **3,031**.

| Type | deprecated | unique active target | multiple active targets | no active target |
|---|---:|---:|---:|---:|
| `occupation-name` | 2,007 | 1,729 | 277 | 1 |
| `job-title` | 563 | 37 | 0 | 526 |
| `skill` | 296 | 79 | 0 | 217 |
| `keyword` | 165 | 0 | 0 | 165 |
| **Total** | **3,031** | **1,845** | **277** | **909** |

There were **0 direct target type mismatches** and **0 unknown direct replacement targets**. All measured replacement chains ended at depth 0 or 1 in this snapshot.

Product admission still changes the usable result: among unique active replacements, 1,729 occupation targets are admitted to YV, 29 job-title targets are admitted to YV, 8 active job-title targets remain excluded by YV policy, and 79 skill targets are active KV-valid skills.

## Decision

`replaced_by` is canonical taxonomy-history/migration evidence, not a synonym declaration.

Deprecated IDs and labels remain in a separate legacy retrieval/compatibility layer. A unique replacement may support deterministic migration routing, but the active target must still pass YV/KV product admission. Branching and targetless routes fail closed; no arbitrary winner is chosen.

Machine-readable frozen aggregate: `research/coverage/v31/deprecated-compatibility-aggregate.json`.
