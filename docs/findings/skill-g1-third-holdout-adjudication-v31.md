# KV G1 third-holdout adjudication — taxonomy v31

**Status:** post-result error review; no retrieval-policy change and no retroactive metric cleanup.

The frozen third natural-description holdout contains 26 queries over 17 unique P80 skill targets. The validated G1 candidate and the already-defined character-4gram lane each scored **20/26 Hit@5 = 76.9% (95% Wilson CI 58.0–89.0%)**. Their union-oracle scored **21/26 = 80.8% (95% Wilson CI 62.1–91.5%)**. The lanes disagree on only two queries: one genuine 4-gram rescue (`Kabelinstallationer`) and one genuine 4-gram regression (`Mätteknik`).

These raw metrics remain frozen. They are not recalculated after review.

## Why error adjudication matters

The AF labour-market-training mapping is curated evidence, but a mapped skill ID is not automatically the one uniquely inferable intent of the module description. The existing holdout builder required exactly one **P80** target, which can still admit a module carrying many other mapped skills outside P80. That produces false-looking retrieval failures when the query is genuinely multi-intent or when a near-equivalent taxonomy concept is returned instead.

All seven third-holdout cases where validated G1 missed or the two lanes disagreed were therefore reviewed against the frozen query, all source-mapped skills and current canonical labels/definitions.

## Adjudication

- `kv.training-skill-third-holdout.008` — **Mätteknik**: strong ground truth. The text repeatedly describes measurement methods, geodetic instruments and analysis. G1 ranks it first; 4-gram ranks it sixth. This is a real subword regression.
- `kv.training-skill-third-holdout.022` — **Kabelinstallationer**: strong ground truth. The source maps only this skill and the text explicitly describes copper-cable splicing, telecom-network construction and cable termination. G1 misses; 4-gram ranks it third. This is a real complementary rescue.
- `kv.training-skill-third-holdout.013` — **Städmaterial**: strong enough to count as a real retrieval gap. The source maps only this skill and the text describes cleaning tools, machines, accessories and base equipment. Both lanes miss.
- `kv.training-skill-third-holdout.004` — **Trädgårdsskötsel**: relevant but multi-intent. The same source also maps `Trädgårdsanläggning` and `Skötsel och underhåll av utemiljöer`, both strongly expressed by the text. A single-target failure is not an unambiguous product failure.
- `kv.training-skill-third-holdout.014` — **Plattsättning**: plausible but multi-intent. The source maps 11 skills. Both lanes already return `Kakel och klinker, plattsättningsvana` in top-5, a near-equivalent user-visible answer.
- `kv.training-skill-third-holdout.024` — **Städmaterial**: weak target. The query is about healthcare hygiene, cleaning methods and hygiene classes; the same source maps `Hygienstädning`, which is substantially more directly expressed. Do not tune retrieval to force `Städmaterial` here.
- `kv.training-skill-third-holdout.025` — **Plattsättning**: not reliably inferable from the query. The module title contains the clue, but the benchmark query deliberately excludes the title and leaves generic special-trade/building text with six mapped skills. This is a benchmark-label problem, not demonstrated retrieval failure.

Machine-readable adjudication: `research/evaluation/v31/skill-g1-third-holdout-adjudication.json`.

## Consequence

The 4-gram lane is genuinely complementary, but this holdout does **not** justify adding it to runtime: its one clear rescue is offset by one clear regression, and raw aggregate performance is unchanged.

More importantly, future confirmatory description holdouts should tighten source truth to **exactly one mapped skill in total**, not merely exactly one target inside the P80 evaluation envelope. Even then, every material miss, rescue and regression must be reviewed against source text and taxonomy before it drives product changes. Source annotations remain evidence, not unquestionable truth.
