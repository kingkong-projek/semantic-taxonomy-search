# Yrkesväljaren generator exclusion policy — taxonomy v31

**Status:** measured  
**Measured:** 2026-09-04  
**Generator source commit:** `6dd9e4737d7db3cb2709f8082808b88e5c89ed6e`  
**Accepted CI run:** `33867012366`  
**Analyzer:** `scripts/analyze_yv_generator_policy.py`

This resolves the previously unexplained population of **205 active v31 job-title IDs that are absent from the published Yrkesväljaren v31**.

## 1. Production-source binding

The public generator repository contains a committed `output/v1/yrkesvaljaren-t31.json`.

That file is **byte-for-byte identical** to the published YV v31 artifact:

`SHA-256 1036f9525416fac4ce475c1c1d3909b9e2849ebcf7094ffd38104955e4c2ee49`

Therefore the measured generator snapshot is directly bound to the published v31 dataset rather than being merely a plausible implementation.

## 2. The two exclusion rules

The generator in `utils/create_weighted_occupational_data.py` excludes a job-title when either rule applies.

### Rule A — too many occupation contexts

If a job-title is related to **more than three** occupation-name concepts, it is not emitted into YV.

The generator records these separately in `jobbtitlar-mappad-till-för-många-yb-t31.json`.

Measured v31 population: **104 titles**.

Parent-count distribution:

| parents | titles |
|---:|---:|
| 4 | 46 |
| 5 | 11 |
| 6 | 14 |
| 7 | 4 |
| 8 | 3 |
| 9 | 3 |
| 10 | 3 |
| 11 | 1 |
| 12 | 4 |
| 13 | 1 |
| 15 | 2 |
| 17 | 1 |
| 18 | 7 |
| 19 | 1 |
| 25 | 2 |
| 38 | 1 |

This explains broad titles such as `Jurist`, `Säljare` and `Projektledare` that we previously observed in the residual population.

### Rule B — title considered redundant inside occupation label

The generator computes:

```text
all(job_title_label.lower() in occupation_label.lower()
    for every mapped occupation-name)
```

If true, the job-title is not emitted because the title is considered already represented by every connected occupation label.

The generator records these separately in `jobbtitlar-del-av-yb-t31.json`.

Measured v31 population: **101 titles**.

Parent-count distribution:

| parents | titles |
|---:|---:|
| 1 | 84 |
| 2 | 9 |
| 5 | 2 |
| 7 | 1 |
| 8 | 1 |
| 9 | 1 |
| 17 | 1 |
| 18 | 2 |

This explains why the residual population included many single-parent titles: ambiguity was never the only exclusion criterion.

## 3. Exact closure of the 205-title gap

Active v31 job-title universe: **9,785**.

Published YV unique job-title IDs: **9,580**.

Missing active job-title IDs: **205**.

Generator diagnostics:

- too many occupation contexts: **104**;
- redundant-title rule: **101**;
- overlap between the two diagnostic label sets: **0**;
- total: **205**.

The reproducible analyzer resolves diagnostic labels back to active v31 job-title IDs and proves:

> **The 205 diagnostic IDs exactly equal the 205 active v31 job-title IDs absent from YV.**

There are no unexplained active-title omissions in the current v31 file.

## 4. The single active v30→v31 dropout

Only one title that is still active in taxonomy v31 was present in YV v30 but absent in YV v31:

- ID: `c57D_hnj_zGv`
- label: `Präst`
- v30 YV parent: `Stiftsadjunkt` (`udVE_5Hy_qGb`)
- v31 mapped occupation label: `Präst, Svenska kyrkan`
- v31 exclusion reason: `redundant_label`

The relation/context changed such that `Präst` is now a substring of its mapped occupation label. It therefore newly satisfies Rule B.

The other four job-title IDs present in YV v30 but not v31 are not part of the active v31 title universe and are therefore a different lifecycle/deprecation question, not unexplained YV filtering.

## 5. Semantic-search implication

The published YV destination space is **intentionally narrower than all active taxonomy job-title concepts**.

For the semantic YV feature, the default output contract should therefore remain:

```text
canonical YV identities
= all active occupation-name identities
+ only job-title identities admitted by the YV generator policy
```

The 205 excluded titles remain useful as:

- query vocabulary;
- ambiguity/disambiguation evidence;
- hard-negative and abstention cases;
- bridge terms that can lead to an admitted occupation-name result.

But they must not silently become selectable YV job-title results merely because semantic retrieval finds them.

In particular:

- a `>3 parents` title is strong evidence that flat single-result mapping is unsafe;
- a redundant title can often act as wording that retrieves its occupation-name without becoming a separate visible identity.

This is an important distinction between **retrieval vocabulary** and **product destination identity**.

## 6. Guardrails

- The generator policy is version-bound; revalidate on future YV/taxonomy releases.
- Do not interpret the `>3` rule as a taxonomy truth about semantic ambiguity; it is a YV product/generator policy.
- Do not interpret substring redundancy as canonical synonymy.
- The 205 excluded job-title concepts may contribute retrieval evidence, but are not selectable YV identities under the current v31 contract.
- Exact preferred-label matching against an excluded title should route/disambiguate toward allowed YV identities rather than bypass the policy.

Machine aggregate: `research/coverage/v31/yv-generator-policy-aggregate.json`.
