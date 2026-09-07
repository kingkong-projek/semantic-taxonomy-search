# Exploratory legacy demo field failures — 2026-09-07

Status: **opened exploratory product evidence; mixed intended stream unknown; not blind validation, not a tuning set**.

A tester explicitly exported and shared one local demo session from the first deployed browser prototype. That version exposed only the KV path, so every row was mechanically stamped `stream: skill` even though the tester later confirmed that some inputs were intended as occupation descriptions and others as competence descriptions. The export therefore MUST NOT be treated as 19 KV cases and the intended stream of individual legacy rows MUST NOT be reconstructed as ground truth after the fact.

The session contained 21 submissions / 19 unique descriptions. Several descriptions were intentionally weak, playful or arguably outside either target boundary. Others were ordinary task descriptions. Because the tester had already seen system output and the sample was not preregistered or independently adjudicated, these cases MUST NOT be reported as human validation accuracy and MUST NOT be tuned against as if they were a holdout.

No raw exported session is committed to the repository. Earlier selective verbatim examples have been removed now that the repository is public; only coarse failure categories are retained here.

The session is nevertheless material product evidence because it exposes failure modes that Hit@5 alone can hide.

## Observed failure classes

The opened session showed several qualitatively different problems:

- a plausible animal-care candidate could appear at rank 3 behind two obviously unrelated candidates;
- event-booking language could retrieve unrelated warehouse/property candidates before a related booking competence;
- restaurant-review language could rank programming-related competences prominently;
- mixed maintenance/outdoor work language could rank an accounting concept first despite also surfacing some related maintenance candidates lower down;
- web-behaviour analysis language could surface a care-related behaviour concept above a web-analytics concept;
- simple invoice-handling and work-planning competence descriptions could also produce coherent, useful lists;
- some unsupported language produced no candidates, demonstrating that abstention is technically possible.

A separate cross-stream probe against the deployed `YV-C2-plain-v1` and `KV-G1+T3-plain-v1` artifacts showed that the problem is not safely attributable to KV alone. Several occupation-like task descriptions also produce visibly poor YV lists. Because legacy intended stream is not recorded, that probe is diagnostic only, not an accuracy evaluation.

## What this falsifies

### Hit@5 is insufficient as the product-facing quality signal

A semantically plausible candidate at rank 3 can count as a Hit@5 success while ranks 1–2 are trust-breaking. The frozen G1+T3 evidence remains valid for its stated metric, but it does not establish acceptable ordering, precision or user trust. The same warning applies to occupation description evaluation: a small natural-language positive holdout is not enough to establish list quality.

### Matched-term count is not a sufficient confidence gate

Some visibly bad rankings matched all unique query terms. Therefore a simple minimum matched-term or matched-term-ratio threshold cannot by itself solve the observed failure class.

### Fail-open behavior is visibly harmful on weak/out-of-boundary descriptions

Some intentionally weak/out-of-boundary descriptions produced arbitrary-looking five-result lists instead of abstaining. The product should prefer a conservative `inga rimliga förslag` state over confident-looking lexical accidents when support is weak.

## Structural interpretation

The current KV fusion always admits the C0 top candidate when C0 has any positive score, then reserves a G1 slot and teacher slots. This is useful for recall experiments but has no calibrated evidence threshold. Sparse or incidental lexical overlap can therefore become a prominent final suggestion even when there is no reason to believe the candidate is acceptable.

YV C2 has a different failure shape. Its previously strong fresh holdout contained only five positive natural-language occupation cases; the legacy cross-stream probe indicates that full first-person/task descriptions remain materially under-tested. This is evidence to widen rank-sensitive occupation validation, not permission to tune C2 against the opened legacy phrases.

## Rank-sensitive metric contract

For human/opened product evaluation, Hit@5 is retained only as a secondary recall-style diagnostic. Primary list-quality reporting must include, per stream:

- Top1 acceptable;
- first acceptable rank and reciprocal rank;
- nDCG@5 when multiple acceptable identities exist;
- count of unacceptable results before the first acceptable result;
- candidate-list precision over the candidates actually shown;
- number of unacceptable candidates returned;
- correct abstention for clarification-needed, unmappable and out-of-scope cases;
- participant recognition and selection of acceptable candidates.

Thus a list with two unacceptable results followed by one acceptable result at rank 3 is explicitly reported as `Hit@5=yes`, `Top1=no`, `first acceptable rank=3`, `unacceptable prefix=2`, rather than being summarized as a success.

## Next falsifiable work

1. Keep this exact legacy session opened and excluded from optimization/validation scoring.
2. Preserve future demo `stream` selection in exports so YV and KV evidence cannot be conflated again.
3. Use the added per-result lane/support diagnostics to understand failure mechanisms without changing ranking on these opened cases.
4. Define conservative ranking/abstention candidates only from general model evidence; do not choose thresholds from the 19 opened descriptions alone.
5. Freeze new independent natural-description sets separately for occupation and skill before evaluating changes.
6. Report the rank-sensitive metric contract above; Hit@5 remains secondary historical comparability only.
7. Preserve the existing requirement that genuinely out-of-scope or semantically unsupported input may abstain.

No production prevalence claim follows from this session. No raw exported session is committed to the repository.
