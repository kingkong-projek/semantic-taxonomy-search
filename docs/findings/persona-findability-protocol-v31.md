# Persona-based findability protocol — taxonomy v31

## Purpose

The product complaint to explain is experiential: a person looking for an occupation or competence sometimes feels that the thing they mean is not there, even when a related or technically correct taxonomy identity may exist.

Ordinary Recall@K is therefore insufficient. We need an exploratory layer that asks what a real user with a particular goal, vocabulary and search strategy would *experience* while moving through YV and KV.

This protocol uses synthetic personas as **UX red-team instruments**, not as empirical users and not as benchmark ground truth.

## Guardrails

1. Personas vary occupational self-knowledge, labour-market history, language/search strategy and digital/search literacy. Do not infer behaviour from protected or demographic traits.
2. Freeze the persona's goal and first query before looking at selector output. Otherwise the simulation simply reverse-engineers the product.
3. A persona may generate hypotheses and candidate failures. A candidate becomes a finding only when independently supported by at least one of:
   - authoritative taxonomy/source truth;
   - observed query-frequency evidence;
   - reproducible current product code/data behaviour;
   - actual user feedback or human review.
4. Personas do not force a match. Ambiguous journeys may correctly end in clarification or abstention.
5. Do not use one model to generate a persona query, inspect the answer and then declare its own intended identity correct. Intent adjudication and product replay must remain separable.

## What varies

The initial matrix in `research/personas/v31/personas.json` covers these dimensions:

- user knows exact common title vs only local/employer title;
- canonical/current term vs old/deprecated term;
- Swedish canonical vocabulary vs English workplace vocabulary;
- exact spelling vs realistic typo/särskrivning;
- broad umbrella role vs narrow specialty;
- single-context vs multi-context job title;
- title-first vs task/tool/responsibility-first language;
- finding the old job vs changing career through transferable skills;
- formal credential search where false positives are especially costly;
- patient taxonomy-navigation vs top-3/top-5 recognition behaviour.

The matrix deliberately includes common high-volume concepts and known product stressors rather than exotic taxonomy tail cases.

## Journey format

Each simulated journey should be frozen before selector replay with at least:

```json
{
  "persona_id": "P08-multi-context-title",
  "goal": "I want to select the project-manager role I had in construction",
  "known_facts": ["my employer called me projektledare", "I worked in construction"],
  "first_query": "projektledare bygg",
  "allowed_followups": 2,
  "recognition_budget": 5,
  "success_condition": "the correct occupation/context is recognisable without knowing taxonomy internals"
}
```

Then replay the real product without rewriting the query to help it.

For each step record:

- exact text entered;
- direct/fuzzy/semantic lane used;
- top visible results in order;
- whether the authoritative intended identity/context is present;
- whether the label is *recognisable* to the persona;
- whether a misleading but plausible alternative is more salient;
- whether the user can reasonably recover with one follow-up;
- whether context survives YV -> KV;
- whether KV's visible skills are coherent with the selected occupation;
- whether the rational user action is select / reformulate / describe / abstain / give up.

## Experience-oriented failure classes

### A. Missing vocabulary

The user supplies a legitimate current alternative label, historical label, employer title, English title, colloquial competency phrase or other attested surface that the selector does not index.

### B. Recognition failure

The intended identity technically appears, but the presented label/context is not something the user can recognise as their own role. Example shape: a familiar title shown with an unexpected parenthetical occupation.

This is distinct from Recall@K.

### C. Variant overload

A broad ordinary query yields many narrow near-duplicates. The correct family may have high recall while still producing the experience "there is no normal/general version of my job here".

Record at least:

- number of visible near-duplicate variants;
- whether an umbrella/neutral route exists;
- rank of the first recognisable option;
- whether choosing one requires taxonomy knowledge the user cannot be expected to have.

### D. Context loss / context collapse

The user supplies enough context to distinguish one meaning of a title, but search, fuzzy deduplication, selection roundtrip or YV -> KV hand-off loses that distinction.

### E. Plausible wrong answer

The product shows a semantically/lexically plausible result that is materially wrong and more salient than the correct option. This can be worse than no result because the user may select it.

### F. KV coherence failure

After a plausible YV selection, the competence view contains highly salient skills/credentials that a reasonable user experiences as unrelated to the selected occupation. Measure the visible list, not only whether some relevant skill exists somewhere below it.

### G. Description-mode failure

The persona does not know a taxonomy title and uses tasks/tools/responsibilities. Ordinary lookup is expected to fail; semantic fallback is successful only if it produces a small recognisable candidate set or safely abstains.

## Metrics

Keep conventional retrieval metrics, but add user-experience views:

- **recognisable-at-3 / recognisable-at-5**: target or acceptable route is visible in language/context the persona can plausibly recognise;
- **recoverable-within-2**: success after at most two natural reformulations, without teaching the persona taxonomy vocabulary;
- **variant-overload rate**: broad ordinary intents whose visible list is dominated by near-duplicate specialisations without a neutral route;
- **context-preservation rate**: distinguished context survives query -> result -> selection -> downstream KV;
- **misleading-top-hit rate**: wrong but plausible result ranks above all recognisable acceptable results;
- **KV visible-coherence**: top visible competence suggestions are semantically coherent with the selected occupation according to independent source evidence/review;
- **give-up proxy**: no recognisable acceptable result inside the persona's declared recognition/follow-up budget;
- **safe abstention** for genuinely underdetermined journeys.

Do not aggregate these into one magic score initially. Failure mechanism matters more than a single number.

## Initial persona set

The v31 seed matrix contains 12 personas:

1. common known title;
2. employer-specific title;
3. task-first user;
4. old/deprecated title;
5. English workplace title;
6. realistic typo/mobile query;
7. broad umbrella category;
8. multi-context title;
9. career changer using transferable skills;
10. practical skill in everyday language;
11. formal credential/certificate search;
12. low-patience top-3/top-5 recognition behaviour.

These are composable. `P12` is especially useful as a behavioural layer on top of another occupational situation rather than a separate demographic persona.

## First anchored scenarios

Start from actual reported product symptoms and high-volume source evidence rather than invented curiosities:

- `projektledare` — broad umbrella / variant-overload and recognition journey;
- `projektkoordinator` — parenthetical/context recognition journey;
- common excluded titles such as `undersköterska`, `butikssäljare`, `sjuksköterska`, `kock`, `säljare` — source-attested high-volume route journeys;
- multi-context titles with realistic typo and context qualifier — fuzzy/context-preservation journey;
- YV selection -> KV visible list — coherence journey, explicitly looking for unrelated high-salience skills/credentials;
- task descriptions for common P80 occupations/skills — description-mode journey.

## Research order

1. Finish the source-attested `should-find` replay of current YV/KV.
2. Build a compact persona journey packet anchored in the failure classes above; freeze goals/queries before replay.
3. Replay the pinned product and record exact visible output and recovery path.
4. Verify each candidate failure independently against source truth/code/observed data.
5. Cluster verified failures by mechanism and demand/risk.
6. Fix the smallest material cause first.
7. Only then test whether semantic fallback materially improves the remaining experience.

This protocol complements, rather than replaces, the Pareto and safety benchmarks. Its job is to discover failure mechanisms that technically correct retrieval metrics may hide.
