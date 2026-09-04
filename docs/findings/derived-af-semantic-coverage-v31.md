# AF-derived semantic coverage — taxonomy v31

**Status:** measured  
**Measured:** 2026-09-04  
**Extractor:** `scripts/derived_af_coverage.py`  
**Accepted workflow run:** `33864929163`

This finding measures three AF-derived evidence sources against the same immutable active taxonomy v31 snapshot used by the rest of Gate 1. These sources are valuable retrieval evidence, but none of them is canonical taxonomy truth.

## 1. Relevanta kompetenser is a large additional skill representation

Source:

`https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/v1/relevanta-kompetenser-t31.json.zst`

Wire SHA-256: `e66679cdb48af23700734bcf26d8d6531d842cbdad2cba80c67baa71ceb3a897`  
Decompressed JSON SHA-256: `500107de25abe94f19bb3800377df13bc4ad756601af11b1f88c2074f2441829`

Measured coverage:

- occupation records: **2,105 / 2,105 = 100%**
- occupation→skill edge occurrences: **41,096**
- unique active skill IDs: **4,685 / 6,752 = 69.387%**
- unknown occupation IDs: **0**
- unknown skill references: **0**
- wrong skill types: **0**
- skills per occupation: min **0**, median **20**, mean **19.523**, max **30**
- occupations with exactly 30 returned skills: **724**
- relevance points: min **3.01**, median **14**, mean **27.284**, max **3,310**

The large population at exactly 30 is a warning that the published list is likely bounded/truncated by methodology. Absence below the top-N must therefore not be interpreted as proof that a skill is irrelevant.

### Delta against Kompetensväljaren

Relevanta kompetenser and KV overlap heavily but are not identical.

- Relevanta unique skills: **4,685**
- ordinary KV four-layer union: **4,647**
- Relevanta ∩ ordinary KV: **4,281**
- Relevanta skills not present in ordinary KV: **404**
- the same **404** remain additional even after adding KV `transferable_skills`
- KV skills not present in Relevanta: **366**
- combined Relevanta + ordinary KV union: **5,051 / 6,752 = 74.807%** active skill coverage

Layer-specific overlap with Relevanta:

| KV layer | KV unique skills | overlap with Relevanta |
|---|---:|---:|
| `calculated_skills` | 4,104 | **4,104** |
| `optional_skills` | 1,463 | 1,145 |
| `essential_skills` | 55 | 17 |
| `regulated_skills` | 33 | 13 |

The fact that **every KV calculated skill is in the Relevanta skill universe** is important structural evidence, but it does not by itself prove how KV calculated skills were generated. Source methodology/code must establish causality.

Per occupation, the ordinary KV union and Relevanta are similar but not identical:

- mean Jaccard: **0.829**
- median Jaccard: **0.833**
- mean Relevanta-only skills per occupation: **3.749**
- median Relevanta-only: **0**
- max Relevanta-only: **10**

### Retrieval consequence

Relevanta kompetenser is not redundant. It materially broadens skill coverage and can serve both products:

- **YV:** a work/task description can hit skills and bridge to occupations.
- **KV:** it provides occupation-contextual candidate generation beyond the current KV read model.

But `relevance_points` is a source-specific derived score. It must not be interpreted as essentiality, requirement strength or generic semantic confidence.

## 2. Real employer language is already available at useful scale

Source:

`https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t31/relevans-nyckelord.json.zst`

Wire SHA-256: `2fb4be00e42a89dca97f23547942b128820fe3b794ff5e25ac0f872978fe5b00`  
Decompressed JSON SHA-256: `197436eabee3c34a8fec3a7682640c371dfcc630e4b86ba92772df9e9b525d03`

Source metadata:

- total ads: **7,367,297**
- enriched ads: **6,937,543**
- historical years included: **2016–2025**
- data created: **2026-08-17**

Measured occupation coverage:

- occupation-name records: **1,051 / 2,105 = 49.929%**
- SSYK4 records: **384 / 400 = 96.0%**
- unknown occupation IDs: **0**
- unknown SSYK4 IDs: **0**
- distinct employer-language keyword strings across occupation records: **11,085**
- keyword count per covered occupation: min **1**, median **96**, mean **108.843**, max **200**
- ads per covered occupation: min **200**, median **1,412**, mean **6,342.849**, max **401,817**
- metric occurrences: **114,394** each for weighted frequency, TF-IDF, BM25 and RCA

### It directly fills part of the native-definition gap

There are 469 active occupation-name concepts whose taxonomy definition is only a copy of the preferred label.

Of those, **198 / 469 = 42.217%** have an ad-derived keyword representation.

This is important: for a substantial fraction of occupations where curated descriptive text is absent, we already have real observed employer language tied to the exact canonical occupation ID.

That makes synthetic LLM paraphrases substantially less compelling as an early solution.

### Authority boundary

Ad-derived keywords are empirical language, not canonical definitions. They may encode:

- tasks and tools;
- industry terminology;
- credentials and methods;
- common co-occurring but non-defining terms;
- recruitment conventions and historical noise.

The four published metrics must retain their identities. We should benchmark which weighting/combination helps retrieval instead of summing them blindly.

## 3. Närliggande yrken is broad but only covers the ad-supported half of occupation space

Source:

`https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t31/narliggande-yrken.json`

SHA-256: `1f476198bea046c88d18fc8a09c80fbb88107bcb046644b95ffdc441db679396`

Measured:

- source occupation records: **1,050 / 2,105 = 49.881%**
- similarity edge occurrences: **10,218**
- unique target occupations: **934**
- neighbours/source: min **1**, median **10**, mean **9.731**, max **10**
- unknown source IDs: **0**
- unknown target refs: **0**

This is useful for candidate expansion, diversification and hard negatives, but it must not be treated as synonymy or as proof that two occupations are interchangeable/career transitions.

## 4. Current consequence for the research plan

The evidence order should now favour real data much more strongly:

1. canonical labels/definitions;
2. typed taxonomy graph;
3. YV/KV published read-model evidence;
4. **Relevanta kompetenser**;
5. **real ad-derived employer language**;
6. other observed query/ad sources;
7. embeddings/reranking over the trusted/observed representations;
8. synthetic text only for residual, measured gaps.

The ad-keyword source is especially promising for YV description search. Relevanta kompetenser is especially promising for the YV↔skill bridge and KV skill candidate generation.

## 5. Next experiments created by this finding

- Measure which occupations are covered by definition vs ad language vs both vs neither.
- Characterise the 1,054 occupations without ad-keyword records: are they long-tail, non-advertised, leadership/regulatory roles, or other systematic strata?
- Benchmark BM25/TF-IDF/RCA/weighted-frequency-derived text representations separately.
- Determine whether the 30-skill ceiling in Relevanta is an explicit published top-N and make absence semantics explicit.
- Carry the 404 Relevanta-only skills into the KV benchmark as a dedicated incremental-coverage stratum.
- Do not design synthetic paraphrase generation until these real-data layers have been evaluated.
