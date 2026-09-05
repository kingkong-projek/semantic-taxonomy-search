# Yrkesväljaren + JobSearch Trends source audit

**Status:** measured  
**Measured:** 2026-09-06  
**Yrkesväljaren source commit:** `6dd9e4737d7db3cb2709f8082808b88e5c89ed6e`  
**JobSearch Trends source commit:** `7f3d919a876550678341ff43fecb98f42b98896b`

This audit follows the complete current Yrkesväljaren generator repository and its upstream public JobSearch Trends generator. It corrects an important source-boundary ambiguity in the earlier research plan.

## 1. The Yrkesväljaren repository is small and fully tractable

Current source snapshot contains 33 files and about 487 Python lines across `main.py` and `utils/*.py`, plus generated data/output files and documentation. The complete production path is:

```text
public daily JobSearch Trends files
        ↓
update_search_terms.py
        ↓
data/sokningar-platsbanken.json.zip
        ↓
add_weights_to_searches.py + Taxonomy GraphQL
        ↓
create_weighted_occupational_data.py
        ↓
published Yrkesväljaren read model
```

The already accepted v31 generator policy result remains valid: the committed v31 output is byte-identical to the published YV v31 artifact, and its two exclusion rules explain all 205 omitted active job-title IDs.

## 2. `sokningar-platsbanken.json.zip` is derived, not the raw public source

The committed aggregate currently contains:

- date range: `2022-05-04` through `2026-08-16`;
- 115,553 retained distinct terms;
- 3,136,136,606 retained aggregate searches;
- SHA-256: `01a2550473091b06fdaaf450015eeea13b301471f1c78f5fb0dc8d3499645ae2`.

`utils/update_search_terms.py` builds this from the public JobSearch Trends file area. For every new daily file it reads only `q_approved`, keeps a term only when its daily count is at least 10, sums counts over time, performs small whitespace/hyphen normalization, then removes aggregate terms below 100.

Therefore the committed YV file loses:

1. daily/time-series information;
2. approved free-text terms below the YV thresholds;
3. every public JobSearch Trends parameter except `q_approved`;
4. exact per-file provenance/hashes.

It remains an excellent reproducible snapshot for the published YV weighting policy, but it should not be treated as the complete public observed-language source.

## 3. What the public raw source actually is

JobSearch Trends source code states that it summarizes daily `/search` requests from JobSearch API logs. The public file contains **daily aggregate counts**, split by request parameter. It does not publish complete request combinations.

The current public file area exposes 1,256 dated ZIP files from `2022-05-04` through `2026-09-04`. This span contains 1,585 calendar days, so the current listing has 329 dates without a published ZIP. Absence of a file is not interpreted as zero searches.

Two sampled daily files show the scale change:

| date | distinct public `q_approved` values | example top terms |
|---|---:|---|
| 2022-05-04 | 15,425 | `stockholms län`, `haninge`, `ekonomiskt bistånd` |
| 2026-09-04 | 100,342 | `personlig assistent`, `undersköterska`, `stockholms län` |

The raw daily source is therefore materially richer than the cumulative YV snapshot for language research and recency analysis.

## 4. `q_approved` is a privacy class, not a semantic class

This is the most important semantic correction.

The upstream generator takes raw free-text `q` values, cleans/lower-cases them and checks their words against a large whitelist built from taxonomy words, locations, employers, schools, common words and other allow-lists, including Swedish stemming. Values that pass become `q_approved`; rejected/not-checked values stay only in the internal result.

Thus:

```text
q_approved
!= query judged relevant to an occupation
!= query mapped to a taxonomy identity
!= user selected a result
```

It means roughly: **public-safe free-text query after the source's PII-removal/whitelist process**.

The data confirms this: high-frequency public values include locations, organisations and other non-occupation intent as well as occupations/job titles.

## 5. Structured fields are useful behavior signals, but they are marginal counts

Daily public files also contain aggregate counts for several structured JobSearch parameters, including taxonomy-backed occupation fields/groups/names, geography and employment attributes.

Example, `2026-09-04`:

- `occupation-group`: 628 distinct IDs in the daily aggregate;
- `occupation-field`: 428 values;
- `occupation-name`: only 1 direct parameter value in that day's public file;
- `stats`: `occupation-name` was requested 17,301 times.

This distinction matters. A request such as free text plus `stats=occupation-name` is not a user selection of an occupation. The public output also deliberately splits every request into parameter-wise counters.

Hard boundary:

> **A free-text term and a taxonomy ID appearing in the same daily file are not evidence that they belonged to the same request or user action.**

The current public whitelist does not include the structured `skill` parameter even though the upstream field documentation describes it. Public raw Search Trends therefore does not give us direct skill-selection counts for KV.

## 6. Yrkesväljaren weights are behavioral priors, not semantic labels

`add_weights_to_searches.py` performs exact lookup of lower-cased canonical preferred labels against the cumulative search-term dictionary.

For job titles:

- an exact preferred-label search count is attached to the job-title concept;
- the same count is also inherited by **every related occupation-name**.

For occupation names:

- exact preferred-label searches count directly;
- slash-separated label parts can add further counts;
- inherited related-title counts are added.

The resulting counts are rank-bucketed into weights. Therefore:

- YV weight is a product ranking prior;
- it is not query→target ground truth;
- multi-parent title volume can contribute to several occupations, so inherited volume is not a conserved event count;
- alternative labels, spelling variants and most free text do not create a canonical mapping in this algorithm.

A minor implementation detail is that rank weighting processes complete groups of ten only; a final remainder below ten concepts is not assigned an explicit search-derived weight. This does not affect identity/admission semantics but should be remembered if reproducing exact weights.

## 7. Reproducibility caveat in the incremental updater

`update_search_terms.py` decides whether a public daily file is new only by testing whether its date falls outside the previously stored `[start_date, end_date]` interval.

Consequently, if a missing historical date were published/backfilled later **inside** that interval, the current updater would not ingest it.

Our semantic-search adapter must therefore use an explicit dated-file manifest (and ideally per-file hashes), not only minimum/maximum dates.

## 8. What changes for Semantic Taxonomy Search

Gate 1 remains closed: this discovery does not change the canonical YV/KV target universe or invalidate previous v31 measurements.

It does change Gate-2 source priority.

Raw public JobSearch Trends becomes a first-class `behavioral` source, separate from the generator-bound cumulative YV snapshot:

```text
raw daily JobSearch Trends
  -> observed wording + recency + trend/frequency sampling
  -> benchmark strata / retrieval-language evidence
  -> never destination ground truth by itself

Yrkesväljaren cumulative snapshot
  -> exact accepted historical weighting reproduction
  -> published YV policy analysis
```

Recommended next implementation is a bounded streaming/date-range adapter, not an immediate all-history ETL. It should:

1. discover and persist the exact daily file manifest;
2. retain date and source-file identity;
3. extract `q_approved` plus selected public structured fields separately;
4. never create same-request joins from daily marginals;
5. make recent-window and long-history samples reproducible;
6. quantify what the YV `>=10/day` and `>=100 cumulative` filters remove;
7. surface vocabulary changes over time for Gate-2 sampling.

For the judged benchmark, raw observed terms still require canonical evidence or human/domain judgment before they can become MUST/ACCEPTABLE/MUST_NOT labels.

Machine evidence: `research/coverage/jobsearch-trends-source-probe-2026-09-06.json`.
