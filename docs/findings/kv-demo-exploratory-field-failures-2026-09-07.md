# Exploratory legacy demo field failures — 2026-09-07

Status: **opened exploratory product evidence; mixed intended stream unknown; not blind validation, not a tuning set**.

A tester explicitly exported and shared one local demo session from the first deployed browser prototype. That version exposed only the KV path, so every row was mechanically stamped `stream: skill` even though the tester later confirmed that some inputs were intended as occupation descriptions and others as competence descriptions. The export therefore MUST NOT be treated as 19 KV cases and the intended stream of individual legacy rows MUST NOT be reconstructed as ground truth after the fact.

The session contained 21 submissions / 19 unique descriptions. Several descriptions were intentionally weak, playful or arguably outside either target boundary. Others were ordinary task descriptions. Because the tester had already seen system output and the sample was not preregistered or independently adjudicated, these cases MUST NOT be reported as human validation accuracy and MUST NOT be tuned against as if they were a holdout.

No raw exported session is committed to the repository. Only non-identifying short examples and aggregate diagnostics needed to explain reproduced mechanisms are retained here.

The session is nevertheless material product evidence because it exposes failure modes that Hit@5 alone can hide.

## Cross-stream reproduction

The 19 unique legacy descriptions were replayed unchanged against the exact deployed `YV-C2-plain-v1` and `KV-G1+T3-plain-v1` browser assets. This is a diagnostic cross-stream replay only: it does not retroactively assign intended stream or acceptable target.

The deployed assets are deliberately narrow:

- KV ranks 316 P80 skill identities;
- YV's description-ranking C1/C2 envelope contains 165 occupation-name identities (P80 + six frozen boundary identities);
- YV additionally carries exact job-title -> occupation-name parent routes, but those routed parent identities are not generally rankable from arbitrary descriptions.

This matters materially. The YV asset contains labels for many plausible occupation parents through its exact router — for example `Massör`, `Djurvårdare`, `Veterinär`, `Fastighetsskötare`, `Eventansvarig/Eventkoordinator`, `Fastighetsmäklare`, `Journalist`, `Hundskötare`, `Yrkesfiskare`, `Städare` and `Park- och trädgårdsarbetare` — while none of those identities are in the 165 description-rankable documents. A description suggesting one of these occupations cannot retrieve that identity through C1 BM25. Narrow coverage is allowed by the Pareto contract, but only if unsupported/out-of-envelope input abstains rather than returning a confident-looking nearest neighbour.

## Reproduced root cause 1 — function words can dominate BM25

Per-result retrieval provenance was added to the deployed demo without changing ranking. Replaying the legacy session then exposed direct lexical causes for several visibly absurd results:

- an animal-care description produced `Google Ads` at KV rank 1 from the token `ut` alone, while `Hunddagis` was teacher-lane rank 1 on the meaningful `hundar` evidence;
- a mixed maintenance/outdoor description produced `Bokslut` at KV rank 1 from `av` alone;
- event-booking language produced `Terminal- och lagerarbete` at KV rank 1 from `och` alone;
- massage-like language produced `Arbete på väg steg 2 ...` at KV rank 1 from `på` alone;
- bread-baking language correctly produced `Pizzabakning` at rank 1 from `baka`, but most of ranks 2–5 were candidates supported only by `och`;
- in YV, bread-baking and massage-like descriptions could likewise rank unrelated occupations from `och` or `på` alone.

Using a deliberately narrow set of high-confidence Swedish function words for diagnosis, 5 of 18 non-empty KV rank-1 results in the legacy replay were supported in C0 only by such function words. The same was true for 2 of 15 non-empty YV rank-1 results. Presence of a function word is not itself a failure, but these function-word-only winners are direct reproduced ranking defects.

The current corpus construction therefore allows common grammatical tokens to become retrieval evidence. Because BM25 weights are corpus-relative, a word that is semantically weak in ordinary Swedish can still receive enough weight to win a lane when the meaningful query terms are absent from that lane.

## Reproduced root cause 2 — fixed slot fusion can promote a weaker lane ahead of stronger evidence

KV-G1+T3 is intentionally quota-based rather than calibrated:

1. preserve C0 rank 1;
2. admit one unique G1 candidate;
3. admit three unique teacher candidates;
4. backfill deterministically.

This preserved canonical safety during earlier recall experiments, but it also means C0 rank 1 wins the final list whenever C0 has any positive score, regardless of why it scored.

The animal-care reproduction is the clearest example: C0/G1 rank `Google Ads` first from `ut`, while teacher ranks `Hunddagis` first from `hundar`; the final fusion still places `Google Ads` first and `Hunddagis` third. The same structural pattern occurs in several other legacy queries. Across the 18 non-empty KV replays, teacher rank 1 differed from C0 rank 1 in 13 cases. That count is not a quality metric, but it shows that lane disagreement is common enough that unconditional C0 preservation requires product-level justification beyond canonical regression safety.

Do not respond by simply making teacher first. The lane scores are not calibrated across representations, and the opened 19 descriptions cannot select a new fusion policy. The finding is narrower: **the current fixed-slot contract can visibly expose weak lexical accidents before stronger description evidence**.

## Reproduced root cause 3 — YV C2 is not yet a proven arbitrary-description retriever

YV C2 was frozen as a simple occupation discovery boundary, not as a broad full-taxonomy semantic retriever. Its earlier fresh natural-language holdout contained only five positive occupation cases.

The browser implementation also has a deliberate discontinuity:

- queries with at most three tokens require an exact/component/substring/fuzzy surface signal before a candidate is admitted;
- longer queries may rank from BM25 evidence without that surface guard.

That policy is sensible for conservative short lexical discovery, but the legacy replay shows why it is under-validated for `Beskriv ditt yrke`: a short task description can abstain even when a rankable occupation is conceptually plausible, while a slightly longer description can return unrelated candidates based on grammatical overlap. Combined with the 165-identity description envelope, out-of-envelope occupation descriptions are particularly likely to need explicit abstention.

This does not falsify prior C2 results. It falsifies the stronger interpretation that those results already establish good arbitrary first-person/task-description UX.

## Reproduced root cause 4 — genuine vocabulary/coverage gaps remain after function-word noise is removed

Function-word filtering is not sufficient. Some descriptions still fail because meaningful wording is absent from the relevant lane or because the intended identity is outside the rankable envelope.

For example, `Klassisk massage` is inside the KV target universe and its teacher evidence contains `knådningar`, but the colloquial verb form used in the legacy massage-like description did not match it. Removing grammatical noise therefore changed the case from an absurd five-result list to abstention rather than recovering the plausible target. That is a vocabulary/morphology/paraphrase residual, not a stopword problem.

Likewise, many occupation-like legacy descriptions point naturally toward YV identities that exist in taxonomy/router data but lie outside the 165 description-ranking envelope. Those are coverage + abstention questions, not evidence that a heavier runtime model is required.

## Query-only function-word probe — diagnostic only

A cheap query-only function-word filter was probed without changing index documents, BM25 document lengths or the deployed engine. This was explicitly an opened diagnostic, not a candidate promotion.

Results:

- on the frozen source-attested AF second holdout (20 cases), target ranks were unchanged in all 20 cases: Top1 remained 4/20, Hit@5 remained 20/20 and MRR remained 0.60;
- on 173 query/target pairs extractable from already-opened development artifacts, 14 target ranks improved, 4 worsened and 155 were unchanged; Hit@5 changed 162 -> 161 while MRR changed 0.317 -> 0.347;
- one apparent Hit@5 regression in that opened material occurred even though the target retained substantial meaningful support, demonstrating that stopword filtering can change quota competition and therefore cannot be promoted from intuition alone.

This is enough to justify a fresh test of query-side function-word handling. It is not enough to turn it on. The next comparison must be prefrozen and rank-sensitive.

## What this falsifies

### Hit@5 is insufficient as the product-facing quality signal

A semantically plausible candidate at rank 3 can count as a Hit@5 success while ranks 1–2 are trust-breaking. The frozen G1+T3 evidence remains valid for its stated metric, but it does not establish acceptable ordering, precision or user trust. The same warning applies to occupation description evaluation: a small natural-language positive holdout is not enough to establish list quality.

### Matched-term count is not a sufficient confidence gate

Some visibly bad rankings matched all unique query terms. Therefore a simple minimum matched-term or matched-term-ratio threshold cannot by itself solve the observed failure class.

### Fail-open behavior is visibly harmful on weak/out-of-boundary descriptions

Some intentionally weak/out-of-boundary descriptions produced arbitrary-looking five-result lists instead of abstaining. The product should prefer a conservative `inga rimliga förslag` state over confident-looking lexical accidents when support is weak.

### P80 coverage and product quality are separate questions

A narrow P80 rankable envelope is an allowed v0 trade-off only when the product can distinguish `not covered / not confident` from `here are five nearest things`. Coverage expansion must not be used as a substitute for confidence/abstention, and poor out-of-envelope behavior must not be misreported as in-envelope ranking accuracy.

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

The preregistered human-study scorecard now encodes this contract; occupation and skill remain separate and Hit@5 is secondary historical comparability only.

## Next falsifiable work

1. Keep this exact legacy session opened and excluded from optimization/validation scoring.
2. Preserve future demo `stream` selection in exports so YV and KV evidence cannot be conflated again.
3. Keep per-result lane/support diagnostics in exported demo feedback.
4. Freeze separate new occupation and skill description sets before comparing any retrieval change.
5. On the fresh sets, compare at minimum: current baseline, query-only high-confidence function-word handling, conservative abstention/confidence gating, and only then the smallest justified fusion change.
6. Treat YV coverage-envelope misses separately from in-envelope ranking failures.
7. Report Top1/MRR/nDCG/list precision/unacceptable-prefix/abstention; keep Hit@5 secondary.
8. Do not escalate to embeddings, a runtime LLM or a learned reranker unless the fresh rank-sensitive residual survives the cheaper interventions.

No production prevalence claim follows from this session. No raw exported session is committed to the repository.
