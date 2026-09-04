# Job-ad semantic source boundaries

**Status:** documented source/provenance boundary  
**Reviewed:** 2026-09-04  
**Gate:** Semantic Coverage Inventory / benchmark-source safety

This finding establishes which job-ad signals may be used as observed language, which are structured publisher inputs, and which may be model-derived. It deliberately does **not** assign per-concept coverage where we have not measured it.

## 1. Why the distinction matters

Historical/current ads are attractive semantic-search material because they contain the language employers actually use for tasks, tools and roles. But an ad is not one homogeneous evidence source.

For evaluation and retrieval we must distinguish at least:

```text
raw ad text
employer/recruiter structured taxonomy input
system-derived taxonomy context
model-derived enrichment
```

If these are flattened, a benchmark can accidentally use a model prediction as its own ground truth.

## 2. Current JobSearch field semantics

The JobSearch field documentation states that `occupation` is a JobTech taxonomy item and is added by employers/recruiters when the ad is created. It also documents `must_have` and `nice_to_have` requirement objects containing weighted taxonomy skills, languages and work-experience concepts.

The documentation separately notes that some context fields such as occupation field/group are looked up from taxonomy relationships during ingestion.

Therefore these signals have different provenance even when all contain taxonomy IDs:

| Signal | Provenance for search research | Safe interpretation |
|---|---|---|
| `description.text`, headline and other free text | observed employer language | corpus text, not canonical semantics |
| `occupation` | structured employer/recruiter taxonomy input | comparatively strong occupation-labelled ad join, subject to source quality/version |
| `must_have.skills` / `nice_to_have.skills` | structured weighted requirement fields | requirement evidence; do not equate occurrence with canonical synonymy |
| derived occupation group/field | taxonomy-derived context | routing/context, not independent employer assertion |

Source: https://gitlab.com/arbetsformedlingen/job-ads/jobsearch/jobsearch-api/-/blob/main/docs/AdFields.md

## 3. Historical Ads is enriched

Arbetsförmedlingen's current open-data description states that the Historical Ads API contains unpublished Platsbanken ads from 2016 onward and that **all advertisements are enriched with competencies**. The downloadable historical corpus contains more than seven million ads since 2006, and separate enriched files are published for 2016 onward, including 2026 quarterly files.

Sources:

- https://data.arbetsformedlingen.se/dataset/job-ads/
- https://data.arbetsformedlingen.se/dataservice/historiska_annonser/
- https://data.arbetsformedlingen.se/annonser/historiska/
- https://data.arbetsformedlingen.se/annonser/historiska/berikade/kompletta/
- https://data.arbetsformedlingen.se/annonser/historiska/berikade/exempel/

This creates a hard boundary:

> a skill annotation in an enriched historical-ad representation must not automatically be treated as human-entered ground truth unless field lineage proves that it came from the original structured ad.

## 4. JobAd Enrichments is explicitly model-derived extraction

The JobAd Enrichments project describes its API as extracting relevant labour-market data automatically from job-ad text. Current JobSearch importer development also calls an `enrichtextdocuments` service during ad import.

Sources:

- https://gitlab.com/arbetsformedlingen/enrichment/jobtech-jobad-enrichments
- https://gitlab.com/arbetsformedlingen/job-ads/jobsearch/jobsearch-api/-/merge_requests/62

Therefore model-derived enrichments are useful candidate/evidence features, but they are not independent labels for training or evaluation of the same semantic mapping problem.

## 5. Gate-1 decision

Do **not** make a full raw-ad reprocessing pipeline a prerequisite for Gate 1.

We already have a version-bound, occupation-linked derived ad-language source in `relevans-nyckelord.json.zst`, measured from 7.37M ads, with explicit taxonomy context and provenance. That is sufficient to represent the existence and broad coverage of observed employer language in Gate 1.

Raw/enriched ad-level material should instead be used in Gate 2 in bounded samples where every case records:

```text
ad_id
publication/version context
raw text provenance
original structured occupation/requirements if distinguishable
model-derived enrichment fields separately
taxonomy identity/version
```

This avoids building an expensive normalization pipeline before we know which query strata need it.

## 6. Hard rules for benchmark construction

- Raw ad text may supply realistic query/task language, but does not by itself label the intended canonical concept.
- Employer/recruiter `occupation` IDs may seed occupation-labelled examples when the taxonomy version and identity can be validated.
- Structured requirement skills must stay distinct from automatically enriched skills.
- JobAd Enrichments outputs are **features/pseudo-labels**, never evaluation ground truth for the same model family.
- Taxonomy-derived group/field context is not an independent observation.
- Historical concept IDs must be version-resolved before being compared with v31 active identities.
- If provenance cannot be reconstructed for a field, mark it `UNKNOWN` rather than assuming human or model origin.

## 7. Consequence for the semantic-search plan

Gate 1 needs the source/provenance boundary, not a second seven-million-ad ETL platform. The measured AF ad-keyword publication remains the primary corpus-derived coverage layer for the first ablation. Bounded raw historical-ad samples become part of Gate 2 query construction and later ablation if they add information beyond that publication.
