# Live dual-stream semantic stress test — 2026-09-07

Status: **opened assistant-authored exploratory stress test; not blind validation, not a tuning set**.

## Exact runtime under test

The replay used the exact GitHub Pages artifact from workflow run `34122692734`:

- deployment head: `e1331f927764c70adfbff0875bf8e78b8dbaa93e`;
- Pages artifact id: `10018828856`;
- artifact digest: `sha256:b0c63add9e83b89e0c4975a11d0cc185453602d6679b7ca35cf61f4bc9b9b169`;
- YV engine: `YV-description-full-v0-canonical-router`, 2,105 occupation targets;
- KV engine: `KV-G1+T3-plain-v1`, 316 skill targets.

The artifact was unpacked and replayed directly through the deployed `search-engine.js`; this is therefore a runtime replay, not a reimplementation of the rankers.

## Stress design

The suite contained **88 fresh assistant-authored inputs** written before replay:

- 54 YV descriptions;
- 34 KV descriptions.

The inputs deliberately span:

- direct task descriptions with domain vocabulary;
- colloquial first-person paraphrases;
- terse/noisy keyword-like input;
- indirect or narrative descriptions;
- deliberately ambiguous descriptions;
- nonsense and out-of-scope input where abstention is preferable.

For targetable cases, expected label-family substrings were written before replay. The mechanical family score is intentionally strict: a semantically adjacent taxonomy label can therefore count as a miss. The examples below are necessary to interpret the aggregate. This suite is opened synthetic/product-probing evidence only and MUST NOT be used to claim independent user accuracy or to tune/promote a retrieval change.

## Mechanical stress profile

### YV

| Input style | Cases | Top1 family hit | Top5 family hit |
|---|---:|---:|---:|
| Direct task language | 12 | 5/12 | 8/12 |
| Colloquial paraphrase | 12 | 0/12 | 2/12 |
| Noisy/keyword-like | 8 | 2/8 | 5/8 |
| Indirect/narrative | 8 | 2/8 | 3/8 |

For explicit nonsense/out-of-scope cases where the intended behavior was empty/abstain, YV abstained on only **1/8**.

### KV

| Input style | Cases | Top1 family hit | Top5 family hit |
|---|---:|---:|---:|
| Direct task language | 10 | 7/10 | 10/10 |
| Colloquial paraphrase | 8 | 1/8 | 3/8 |
| Noisy/keyword-like | 6 | 3/6 | 6/6 |

For explicit nonsense/out-of-scope cases where the intended behavior was empty/abstain, KV abstained on only **1/6**.

These numbers are not accuracy estimates. Their value is the *shape*: both engines are dramatically stronger when the query shares recognizable domain vocabulary with indexed evidence, and dramatically weaker on ordinary paraphrase/indirect language.

## Reproduced qualitative failures

### YV: direct vocabulary can still lose to grammatical overlap

`Jag drar elkabel, kopplar uttag och felsöker elinstallationer i hus`

Top five:

1. `Växeltelefonist`
2. `Maskinoperatör metallformning`
3. `Ställningsbyggare, utan yrkesbevis`
4. `Obduktionstekniker`
5. `Ställningsbyggare`

The rank-1 support terms were `i`, `kopplar`, `och`; the meaningful electrical wording did not provide enough indexed overlap to recover an electrician identity.

### YV: paraphrase brittleness

The same underlying intent can swing from correct to absurd as wording changes.

For baking:

- direct `Jag bakar bröd och bullar ... degar och ugnar` -> `Bagare/Konditor` rank 1;
- noisy `bakar brö bullar kakor ugn deg jäst` -> `Bagare/Konditor` rank 1;
- colloquial `Jag står med deg klockan fyra på morgonen och fyller plåtar innan folk vaknar` -> `Bergarbetare, gruva` rank 1, target absent from Top5.

The colloquial winner was supported by `fyller`, `innan`, `med`, `och`, `på`, not by baking semantics.

### YV: the user's castle-style stress case still fails semantically

`Jag rider runt slottet och hjälper kungen`

Top five:

1. `Taltjänsttolk`
2. `Trafikinformatör`
3. `Ergonom`
4. `Sprinklermontör`
5. `Ljudassistent`

Only three query terms matched indexed evidence at all. The winner was supported by `hjälper` and `och`. `rider`, `slottet` and `kungen` did not establish a useful semantic bridge. This is a genuine paraphrase/semantic representation gap, not a candidate-universe problem.

### YV: nonsensical input fails open

`och av på ut med till för från` returned `Bussvärd` rank 1 and four further occupations. `banan raket kung kaffe blå tisdag` returned `Kaféföreståndare` from the single term `kaffe`. `Min chef är dum och kaffet är slut` returned `Rabbin` rank 1.

### KV: meaningful teacher evidence can still be placed behind lexical accidents

`Jag kan sköta hästar, mocka, fodra och ta hand om stall`

Top five:

1. `Fönsterputsning`
2. `Däckbyten`
3. `Hästskötsel`
4. `Hunddagis`
5. `Bararbete`

`Hästskötsel` is teacher-lane rank 1 with strong support from `hästar`, `mocka`, `sköta`, but fixed fusion preserves a C0/G1 winner whose evidence is only `kan`, `och`, `ta`.

`Jag kan knåda ömma ryggar och axlar` similarly returned `Digitalt färdskrivarkort` rank 1 while the target `Klassisk massage` was absent from Top5.

### KV: nonsense also fails open

`och av på ut med till för från` returned `Google Ads` rank 1. `Min chef är dum och kaffet är slut` returned `Hydraulik` rank 1.

## Function-word dominance is material, but not the whole problem

Using a conservative diagnostic set of high-confidence Swedish grammatical/function words, **12/33 (36.4%)** non-empty KV Top1 winners in this stress replay were supported only by such terms. YV had **3/51 (5.9%)** function-word-only Top1 winners by the same narrow diagnostic.

A query-only stopword-removal counterfactual was then replayed purely to diagnose mechanism, not to select a candidate.

YV:

- direct Top5: 8/12 -> 8/12;
- colloquial Top5: 2/12 -> 1/12;
- noisy Top5: 5/8 -> 5/8;
- indirect Top5: 3/8 -> 3/8;
- explicit abstention: 1/8 -> 2/8.

KV:

- direct Top1: 7/10 -> 8/10, Top5 remains 10/10;
- colloquial Top1: 1/8 -> 3/8, Top5 3/8 -> 4/8;
- noisy Top5 remains 6/6;
- explicit abstention: 1/6 -> 2/6.

Therefore stopword handling is a real defect source, especially in KV, but **it is not sufficient**. The YV colloquial slice even worsens under this simple filter. Vocabulary, morphology, paraphrase and confidence/calibration residuals remain.

## Runtime scale is not the bottleneck

On a Node 24 replay of the exact static artifact (not a browser UX benchmark):

- YV median search time: **9.34 ms**, p95 **31.48 ms**, max **42.95 ms** across 54 probes;
- KV median: **0.47 ms**, p95 **1.82 ms**, max **3.58 ms** across 34 probes.

The present taxonomy sizes therefore do not challenge BM25 computationally. The limiting problem is quality, not technical scale.

## What this stress test establishes

1. Expanding YV from 165 to 2,105 targets fixed the hard coverage exclusion, but did **not** make canonical BM25 a robust free-language semantic interpreter.
2. Both engines are useful when users supply domain terms that occur in their evidence, including terse/noisy keyword input.
3. Both are brittle under colloquial paraphrase and indirect narrative wording; YV is particularly weak there.
4. KV's fixed lane fusion still visibly promotes weak lexical evidence over stronger teacher evidence.
5. Confidence/abstention is currently inadequate in both streams. Random, generic and out-of-scope language frequently produces confident-looking lists.
6. Stopword removal alone cannot close the gap.
7. The next quality problem is therefore semantic representation/reranking plus conservative confidence behavior, not corpus-size scalability.

This does **not** promote embeddings, a reranker, a stopword policy or any other new runtime mechanism. The suite is opened and assistant-authored. It is suitable for architecture diagnosis and future regression replay, but any promotion still requires independent stream-separated evidence under the existing rank-sensitive gate.