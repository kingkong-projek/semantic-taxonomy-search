# JobStream skill provenance probe — 2026-09-06

**Status:** bounded source/provenance finding; no retrieval evidence admitted.

A hard-bounded probe read **500 current JobStream v2 ads within 5.77 MB** from `/v2/snapshot`. The snapshot is a compact JSON array, not NDJSON; an earlier parser assumption caused a false zero-ad result and was explicitly discarded.

Among the valid 500-ad sample:

- 4 ads contained `must_have.skills` items (4 items total),
- 14 ads contained `nice_to_have.skills` items (27 items total),
- observed skill item keys were only `weight`, `concept_id`, `label`, and `legacy_ams_taxonomy_id`,
- no machine-visible per-item key indicated source/origin/original/enriched/derived/provider/model lineage.

This does **not** show that the skill annotations are wrong or model-generated. It shows that the current snapshot payload by itself cannot prove which annotations are original recruiter/employer input versus later enrichment lineage.

Therefore current ad text must not be blindly paired with these structured skill IDs as semantic-search training or evaluation truth. The existing job-ad source boundary remains in force: observed text is useful language evidence; structured skill IDs require independently established lineage; model-derived enrichments are features/pseudo-labels rather than ground truth.

Machine-readable aggregate: `research/coverage/jobstream-skill-language-probe-2026-09-06.json`.

The probe persists no ad ID, headline, description or address text.
