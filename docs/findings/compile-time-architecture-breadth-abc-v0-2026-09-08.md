# Compile-time architecture breadth — A/B/C v0 result

Date: 2026-09-08

## Result

The first deliberately broad simple-architecture round does **not** justify leaving the expanded sparse A family.

### Easy cross-style proxy was non-discriminating

The prefrozen 16-concept cross-style proxy produced 15 usable concepts / 60 cases. On that small, source-near candidate cohort:

- A expanded sparse BM25: **60/60 Top1**;
- B supervised sparse v0: **58/60 Top1**;
- C task-atom BM25 v0: **60/60 Top1**.

This proxy is therefore too easy to choose between A and C. Its correct interpretation is saturation, not a C win.

Evidence: `research/evaluation/v31/compile-time-semantic-a593-breadth-proxy-abc.json`.

### Frozen hard-confusion proxy separates the architectures

A stronger gate reuses the already-frozen 11 distinguishable A593 confusion pairs. The 66 test descriptions (3 per side) were generated from public canonical evidence without old A593 teacher phrases or opened 17/88 queries. A/B never trained on these descriptions. C task atoms were generated later, independently, from canonical source evidence only; the contrast cues/descriptions were explicitly not sent to that generator. The A/B/C evaluator itself was committed before the C task-atom output existed.

All three entrants rank the same 22-concept hard-confusion cohort:

| entrant | Top1 | Hit@5 | MRR | correct side vs pair mate |
| --- | ---: | ---: | ---: | ---: |
| A expanded sparse BM25 | **62/66 (93.94%)** | **66/66** | **0.9697** | **63/66 (95.45%)** |
| B supervised sparse v0 | 58/66 (87.88%) | 63/66 | 0.9073 | 61/66 (92.42%) |
| C task-atom BM25 v0 | 46/66 (69.70%) | 55/66 | 0.7749 | 50/66 (75.76%), 7 ties |

Evidence:

- `research/evaluation/v31/compile-time-semantic-a593-confusion-task-atoms-v0.json`
- `research/evaluation/v31/compile-time-semantic-a593-hard-confusion-breadth-abc.json`

## Decision

- **A remains the reference family.** This is not a promotion claim; opened transfer still shows its colloquial/indirect ceiling.
- **B-v0 is killed.** The earlier 593-case construction diagnostic already made it materially worse than its same-feature centroid control, and the hard-confusion transfer gate also trails A. Do not rescue it with a parameter sweep.
- **C-v0 is killed.** Task/activity atoms are conceptually attractive, but this minimal single-stage implementation loses badly on the exact confusion regime it was supposed to help. Do not build a task hierarchy, reranker or hybrid to rescue it.
- The original random cross-style proxy remains useful only as evidence that source-near generated cases can saturate and must not be used as a selection benchmark.

This does **not** establish that A is the global optimum. Before considering the deliberately deferred two-stage retrieval -> local-discriminator architecture, run one final materially different **simple single-stage** breadth falsifier: a tiny learned/latent low-rank domain student. Round-0 C0 was PCA over mean-token geometry rather than a trained sequence/domain student, so that architecture question has not yet been answered cleanly.

If the low-rank entrant also fails the prefrozen construction + hard-confusion gates, end the breadth round with A as the surviving simple family and return to the actual measured bottleneck (training-language/user-language transfer), rather than adding architectural stages.
