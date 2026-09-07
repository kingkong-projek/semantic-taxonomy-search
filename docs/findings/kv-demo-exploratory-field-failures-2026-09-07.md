# Exploratory KV demo field failures — 2026-09-07

Status: **opened exploratory product evidence; not blind validation, not a tuning set**.

A tester explicitly exported and shared one local demo session from the deployed `KV-G1+T3-plain-v1` browser prototype. The session contained 21 submissions / 19 unique descriptions. Several descriptions were intentionally weak, playful or arguably outside the KV target boundary. Others were ordinary task descriptions. Because the tester had already seen system output and the sample was not preregistered or independently adjudicated, these cases MUST NOT be reported as human validation accuracy and MUST NOT be tuned against as if they were a holdout.

The session is nevertheless material product evidence because it exposes failure modes that Hit@5 alone can hide.

## Representative observed failures

Examples below are deliberately selective rather than a raw-session reproduction.

- `gå ut med hundar` returned `Google Ads` rank 1 and `Bararbete` rank 2 before `Hunddagis` rank 3.
- `ta hand om skadade duvhökar` returned `Däckbyten` rank 1 and `Receptionsvana` rank 2; `Hunddagis` appeared at rank 3.
- `ringa artister och boka evenemang` returned `Terminal- och lagerarbete` rank 1 and `Fastighetsskötsel` rank 2 before `Besöksbokning` rank 3.
- `prova restauranger och skriva recensioner` returned `Programmering` rank 1.
- a mixed outdoor/maintenance description (`sopa grus`, `måla fasader`, `rensa rabatter`, `damma av bokhyllor`) returned `Bokslut` rank 1.

The same session also contained plausible behavior:

- `hantera fakturor` returned `Faktureringsvana` rank 1, followed by `Ekonomiadministration` and `Reskontrabokföring`.
- `planera arbete` returned `Arbetsledarerfarenhet` rank 1 and other related leadership/planning candidates.
- `guida agenter` produced no result, demonstrating that abstention is technically possible when no indexed term matches.

## What this falsifies

### Hit@5 is insufficient as the product-facing quality signal

A semantically plausible candidate at rank 3 can count as a Hit@5 success while ranks 1–2 are trust-breaking. The frozen G1+T3 evidence remains valid for its stated metric, but it does not establish acceptable ordering, precision or user trust.

### Matched-term count is not a sufficient confidence gate

The bad `gå ut med hundar` case matched 4/4 unique query terms. `analysera människors beteende på webbplatser` matched 5/5 unique terms yet ranked `Utmanande beteende, omsorgserfarenhet` above `Google Analytics`. Therefore a simple minimum matched-term or matched-term-ratio threshold cannot by itself solve the observed failure class.

### Fail-open behavior is visibly harmful on weak/out-of-boundary descriptions

Some intentionally weak/out-of-boundary descriptions produced arbitrary-looking five-result lists instead of abstaining. The product should prefer a conservative `inga rimliga förslag` state over confident-looking lexical accidents when support is weak.

## Structural interpretation

The current KV fusion always admits the C0 top candidate when C0 has any positive score, then reserves a G1 slot and teacher slots. This is useful for recall experiments but has no calibrated evidence threshold. Sparse or incidental lexical overlap can therefore become a prominent final suggestion even when there is no reason to believe the candidate is acceptable.

This is primarily a **ranking/calibration/abstention** problem, not evidence that another broad retrieval micro-optimization should be started immediately.

## Next falsifiable work

1. Keep this exact session opened and excluded from optimization/validation scoring.
2. Extend demo diagnostics/export so each returned candidate records lane provenance and compact support diagnostics (candidate score/support terms where feasible without exposing source documents).
3. Define a conservative abstention/ranking-guard candidate using model-internal evidence such as lane agreement, candidate support and score/margin information. Do not choose thresholds from these 19 unique descriptions alone.
4. Freeze a new independent natural-description set before evaluating that guard.
5. Report rank-sensitive and user-facing outcomes in addition to Hit@5: selected rank / reciprocal rank when selected, acceptable-candidate recognition by rank, selected-none rate, and fallback-hit-but-no-recognition.
6. Preserve the existing requirement that genuinely out-of-scope or semantically unsupported input may abstain.

No production prevalence claim follows from this session. No raw exported session is committed to the repository.
