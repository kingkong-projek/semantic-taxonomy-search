# YV high-volume real-query review slice — taxonomy v31

**Status:** prepared, not adjudicated  
**Prepared:** 2026-09-06

## Selection

The review packet contains the **50 highest-volume unbound query strings** recomputed directly from the pinned Yrkesväljaren generator corpus (`6dd9e4737d7db3cb2709f8082808b88e5c89ed6e`). No semantic filter is used to choose them.

They represent:

- **742,033,566 searches**;
- **23.661% of all frozen query volume**;
- **35.117% of the previously measured unbound query volume**.

The packet remains `PENDING_HUMAN_REVIEW`. Observed frequency is not query→destination truth and the candidate list is not a label.

## Immediate diagnostic value

The raw high-volume slice visibly mixes occupation-like strings (`lärare`, `lagerarbetare`, `systemutvecklare`, `civilingenjör`, `programmerare`, `handläggare`) with general/geographic search strings (`stockholms län`, `göteborg`, `stockholm`, `umeå`, `skåne län`, `malmö`, etc.).

This means **raw unbound JobSearch text cannot be treated as an occupation-intent benchmark merely because it is frequent**. Intent/adjudication must precede relevance scoring.

The current simple C0 representation (P80 preferred labels + real canonical definitions + alternative labels) has zero positive lexical evidence for **29/50 queries**, accounting for **49.491% of the packet's volume**. Those rows now explicitly abstain rather than returning an arbitrary zero-score nearest occupation.

Positive lexical evidence is still only reviewer context. For example, a geographic string may overlap incidental words in canonical definitions; that is precisely why the packet must be judged before it becomes evaluation truth.

## Next review task

For each query, the reviewer decides:

- `SINGLE`, `AMBIGUOUS` or `NO_MATCH/OTHER_INTENT` for the YV semantic occupation task;
- exact `MUST`, `ACCEPTABLE` and `MUST_NOT` occupation identities where an occupation intent exists;
- whether the correct target is inside P80 or requires P90/P95/tail expansion;
- a short note only when the decision is not obvious.

Do not judge from the current top-5 candidate list. It is shown only to reduce lookup work.

## Frozen files

- `research/benchmark/v31/yv-real-query-review/review-packet.jsonl` — SHA-256 `d454518e1cca4fcdb6690c7288d992623fed8882d32aada5ee6e381c528b7822`
- `research/benchmark/v31/yv-real-query-review/manifest.json` — SHA-256 `7361364238e8f935a02c61625ae1b97e0fce3dc15ca2f905ed00c88b7e55ed9e`
- `research/benchmark/v31/yv-real-query-review/review.md` — SHA-256 `d24d937da30618dc0a07ad0dd2920d82c5fa15671990fcc207fb25659b5b1612`
