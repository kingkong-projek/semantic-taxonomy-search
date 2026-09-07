# KV v31 — simple retrieval boundary after full P80 teacher validation

## Decision

Keep **plain `KV-G1+T3`** as the strongest current low-complexity research candidate for descriptive competence retrieval.

Its runtime shape remains deliberately small:

1. canonical `C0` keeps rank 1;
2. one unique candidate may enter from the existing `G1` BM25 lane built from human-mapped AF training descriptions;
3. three unique candidates may enter from a second BM25 view containing the same G1 evidence plus three frozen teacher phrases per P80 skill;
4. duplicates are removed and backfilled deterministically.

There is no runtime language model, embedding/vector index, learned reranker, score calibration, query classifier or tuned confidence threshold.

Current evidence does **not** justify moving to a higher model class.

## What changed after the original G1 validation

`KV-G1-4slot` remains the strongest independently source-attested base. Across the three AF description holdouts it reaches **68/81 Hit@5 (83.95%)**. The later `G1+T3` candidate reaches **71/81 (87.65%)** on those same 81 source-attested descriptions while preserving the canonical regression guard at **617/617 Top1 and 617/617 Hit@5**.

That 71/81 figure must not be described as a new blind human accuracy estimate. The AF text is genuine source-attested language and is excluded from retrieval evidence, but those suites were already opened during later teacher/fusion development. They are therefore development and safety evidence for `G1+T3`.

The teacher representation was then extended across the complete 316-skill P80 envelope. The final 16 targets, ranks 301–316, were kept untouched until the candidate, teacher phrases and evaluation descriptions had been frozen in that order. On this final target-disjoint slice:

- `G1-4slot`: **2/16 Hit@5 (12.5%)**;
- plain `G1+T3`: **11/16 Hit@5 (68.8%)**.

Adding the last 16 teacher entries caused no observed Hit@5 regression on the canonical 617 cases, the 81 AF cases, or the already-opened ranks 101–300 synthetic suites. The earlier synthetic slices remain **93/100** for ranks 101–200 and **96/100** for ranks 201–300 after full teacher competition.

The final 16 are useful temporal generalization/falsification evidence, but they are not independent user accuracy: both the teacher phrases and test descriptions are model-authored.

## Negative results that matter

Several apparently plausible complexity increases failed to earn their cost:

- **Teacher-only** and **C0+teacher** representations performed well on synthetic descriptions but materially degraded the source-attested AF sets. Keep the existing G1 evidence inside the teacher lane.
- A **character 4-gram BM25 lane** remained 20/26 on the third AF holdout: one strong rescue was offset by one strong regression. Do not add it.
- Removing pure numeric tokens from both expansion documents and queries fixed the observed `Ekonomistyrning` rank-6 boundary, but the prefrozen final gate exposed a new `Svetsteknik` regression from fused rank 5 to rank 215. The query itself contained no numbers; changing document tokenization changed global BM25 length normalization and moved the target across the fixed teacher-slot boundary. That broader sanitation rule is rejected.
- Removing pure integers **only from G1/teacher query tokens** avoids that document-statistics side effect. On already-opened data it improves the AF aggregate from 71/81 to 72/81 with zero Hit@5 regressions, keeps canonical at 617/617 and creates zero rank moves on the opened nonnumeric synthetic suites. However, there is no remaining unused AF source row satisfying the prefrozen independence/non-leakage criteria while also containing a pure integer token. A zero-retrieval builder found **0 eligible cases**. Therefore the query-only tweak remains an unpromoted development candidate; we do not weaken the benchmark criteria or manufacture synthetic numeric cases after seeing the result.

## Complexity boundary

The evidence now supports a stop rule rather than another retrieval experiment:

> **Do not add embeddings, a neural reranker, another retrieval lane, stemming/subword machinery or additional fusion logic until new independent evidence identifies a material residual that plain G1+T3 cannot address cheaply.**

This is not a claim that G1+T3 is globally sufficient. It is a claim about burden of proof: the simple deterministic candidate has already made large gains on the measured description task, while several extra mechanisms either failed to improve source-attested data or introduced new regressions.

The next higher-value evidence is therefore product/user evidence: can people who fail ordinary lexical lookup express enough task/tool/method/responsibility information for a small G1+T3 candidate list to contain a result they recognise and select? That tests the actual `Beskriv din kompetens` hypothesis without replacing ordinary KV lookup or assuming semantic fallback is broadly needed.

Structured decision record: `research/evaluation/v31/kv-g1-t3-simple-boundary.json`.
