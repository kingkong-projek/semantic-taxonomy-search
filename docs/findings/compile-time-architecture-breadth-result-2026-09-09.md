# Compile-time semantic architecture breadth result — 2026-09-09

## Decision

The short architecture-breadth phase is complete. **A — teacher-expanded sparse retrieval — is the surviving simple architecture family.**

Do not rescue the losing entrants with hyperparameter sweeps or combine them into a hybrid. Do not build the deferred two-stage `coarse retrieval -> local discriminator` architecture: the breadth evidence does not justify its added complexity.

The preferred product shape therefore remains:

```text
exact/canonical lexical route
        +
one semantic description ranker/index
```

The immediate next research question is no longer architecture. It is **training-language distribution inside A**: can source-bound teacher language that is materially more user-like improve transfer while keeping the same single-stage sparse runtime?

A2105/full-universe generation stays paused until that question is answered on A593.

## Evidence summary

### A — expanded sparse reference: SURVIVES

A remains the reference family because every materially different simple challenger lost to it on prefrozen/corpus-internal transfer diagnostics.

On the frozen hard-confusion gate of 11 source-bound confusion pairs / 66 held-out descriptions:

- Top1: **62/66 = 93.94%**
- Hit@5: **66/66 = 100%**
- MRR: **0.969697**
- correct side of the intended confusion pair: **63/66 = 95.45%**

This gate is model-authored/source-bound architecture evidence, not human accuracy.

### B — supervised sparse classifier: REJECT

The fixed one-vs-rest linear hinge classifier over char-word-boundary 3–5 gram TF-IDF features was deliberately not hyperparameter-tuned.

On the 593 fixed teacher slot-7 construction holdouts:

- same-feature centroid control: Top1 **165/593 = 27.82%**, Hit@5 **355/593 = 59.87%**, MRR **0.424596**
- B signed-int8 Top300: Top1 **147/593 = 24.79%**, Hit@5 **249/593 = 41.99%**, MRR **0.326345**

On the hard-confusion 66:

- Top1 **58/66 = 87.88%**
- Hit@5 **63/66 = 95.45%**
- pairwise correct **61/66 = 92.42%**

B is smaller but does not establish a higher quality ceiling. Reject without rescue tuning.

Evidence: `research/evaluation/v31/compile-time-semantic-a593-supervised-sparse-breadth.json` and `research/evaluation/v31/compile-time-semantic-a593-hard-confusion-breadth-abc.json`.

### C — task/activity representation: REJECT

C indexed four independently generated, source-bound task/activity atoms per concept and scored the query directly against those atoms. No occupation reranker was added.

On the hard-confusion 66:

- Top1 **46/66 = 69.70%**
- Hit@5 **55/66 = 83.33%**
- MRR **0.774881**
- pairwise correct **50/66 = 75.76%**, with 7 pairwise ties

A reaches 62/66 Top1 and 63/66 pairwise correct on the same frozen descriptions. The task layer therefore loses precisely where it was intended to help: neighbouring-role discrimination.

An earlier 15-concept / 60-query cross-style proxy saturated at 60/60 Top1 for both A and C and is explicitly treated as **too easy to select architectures**, not as positive evidence for C.

Evidence: `research/evaluation/v31/compile-time-semantic-a593-breadth-proxy-abc.json` and `research/evaluation/v31/compile-time-semantic-a593-hard-confusion-breadth-abc.json`.

### E — rank-64 latent student: REJECT

E was the last missing simple single-stage family: char-wb TF-IDF -> fixed rank-64 SVD projection -> cosine against 593 low-rank concept vectors. It uses no transformer/runtime teacher and fits the frontend size constraint, but loses too much quality.

On fixed 593 slot-7 construction holdouts:

- full centroid control: Top1 **174/593 = 29.34%**, Hit@5 **362/593 = 61.05%**, MRR **0.440617**
- E int8 rank-64: Top1 **92/593 = 15.51%**, Hit@5 **299/593 = 50.42%**, MRR **0.312324**

On the hard-confusion 66:

- A: Top1 **62/66 = 93.94%**, pairwise correct **63/66 = 95.45%**
- E int8: Top1 **46/66 = 69.70%**, pairwise correct **56/66 = 84.85%**

The compiled hard-confusion E estimate is about **840 kB gzip**, so size is not the failure; representation quality is.

Evidence: `research/evaluation/v31/compile-time-semantic-a593-lowrank-breadth.json`.

## Why D is not activated

The deferred `coarse retrieval -> local discriminator` architecture was permitted only if simpler single-stage lanes failed in a way that specifically justified an extra semantic stage and could plausibly earn the stronger complexity bar.

That condition is not met. A already performs very strongly on the dedicated 66-case neighbouring-role gate, while its known opened residual is concentrated in colloquial/indirect transfer. This points first to **language distribution/generalisation**, not to a demonstrated need for a second-stage discriminator.

Therefore D stays unbuilt.

## Next bounded experiment: A-language diversity

Freeze the A593 architecture. Do not change ranker form, stemming, negative weights, pair rules or fusion.

Test only the data hypothesis:

> With the same A593 identities and the same simple sparse runtime, does a separately generated source-bound corpus of more lexically distant user language materially improve transfer?

The first falsifier should:

1. select a deterministic bounded subset from the frozen A593 identities without using opened 17/88 outcomes;
2. freeze a new source-bound training-language prompt that favours colloquial first-person, indirect narrative, elliptical/noisy and concrete task/object/tool/responsibility wording while explicitly allowing `no usable evidence` rather than hallucination;
3. freeze a separate held-out query-generation prompt before evaluation;
4. compare **current A** against **A + diversified training language** over the same full A593 candidate universe;
5. choose only from the new prefrozen synthetic transfer proxy; opened 17/88 remains replay-only;
6. require a material gain, not a few per-mille points, before scaling the new language generation to all 593 or 2,105 identities.

If diversified language also fails to transfer materially, treat the current build-time expanded-sparse formulation as approaching its practical ceiling under the present evidence/teacher constraints. At that point do not respond by composing B/C/E/D into a stack; reassess whether the remaining description residual belongs behind a server/API semantic fallback or needs fresh human evidence before more architecture work.
