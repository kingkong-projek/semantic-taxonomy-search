# Current YV/KV should-find audit — taxonomy v31

**Status:** measured, track 1 only

This audit investigates the reported experience **“I cannot find my occupation/competence”** in the ordinary YV/KV selectors. It deliberately does not evaluate the free-text/description fallback. Track 2 is paused until the current-selector failure modes are understood and the cheapest material fixes are measured.

## Method

Build query surfaces with independent target evidence and replay the pinned current selectors exactly.

Strongest evidence class:

- current canonical alternative labels for active concepts.

Additional diagnostic classes:

- deprecated labels with one active `replaced_by` destination — migration/history route evidence only, never synonym ground truth;
- observed YV title + extra context words where those words uniquely name one published occupation parent among the title's sibling contexts;
- synthetic one-edit typo stress over real multi-context YV rows to isolate structural fuzzy behavior.

Cases with a current preferred-label collision against another target are excluded from the primary should-find metric because the user phrase is intrinsically ambiguous in the current product vocabulary.

Reproducer:

- `scripts/build_findability_should_find_cases.py`
- `scripts/evaluate_findability_should_find.mjs`
- `.github/workflows/findability-should-find-audit.yml`

Frozen decision summary: `research/evaluation/v31/current-selector-should-find-summary.json`.

## YV — common traffic is strong, but the misses look exactly like real findability failures

Across **444 non-collision should-find queries actually present in the pinned YV query corpus**, representing **150,300,906 searches**, current YV surfaces the attested target within top 5 for **97.380% of observed volume**.

This confirms that YV is generally strong. It also means a small percentage can still represent millions of frustrating searches.

### Canonical alternative labels

For current canonical alternative labels:

- 357 non-collision cases;
- 318 Hit@5;
- **89.076% unweighted Discovery@5**;
- 95,842,570 observed searches across the cases with traffic;
- 94,479,709 searches hit the intended target within top 5;
- **1,362,861 observed searches miss despite using canonical alternative vocabulary**.

These are the strongest current-selector failure candidates because the taxonomy itself says the surface belongs to the active concept.

High-signal examples:

- `Miljöstrateg` → canonical target `Miljö- och klimatstrateg`; current visible result is instead `Arbetsmiljöstrateg`.
- `PT` → canonical target `Personlig tränare`; current top five are `PTP-psykolog`, `Receptionist`, `Receptarie`, `Hotellreceptionist`, `Optiker`.
- `Flygvärdinna` → canonical target `Kabinpersonal`; current fuzzy results are `Frukostvärdinna`, `Konferensvärdinna`, `Bingovärdinna`.
- `Nagelteknolog` → canonical target `Nagelterapeut`; current fuzzy results begin with `Språkteknolog`, `Chief Technology Officer/CTO/Teknologichef`, `Anestesiolog`.

These are not “no-result” failures. They are often worse from a user perspective: the product confidently shows plausible-looking but wrong alternatives, so the user may conclude that their occupation is absent.

### Deprecated vocabulary

For labels whose deprecated concept has one active replacement:

- 1,066 cases;
- 521 Hit@5;
- 48.874% unweighted Discovery@5;
- 60,841,727 observed searches;
- 94.803% of observed volume reaches the replacement in top 5.

Do not interpret the remaining misses as confirmed user-intent failures. `replaced_by` is migration/history evidence, not synonymy. Broad examples such as `Designer` demonstrate why these cases need experience/domain review before they become product findings.

Still, some high-volume cases are strong candidates for investigation, such as `Hotellstädare`, where the current result set contains `Hemstädare`, `Hotelldirektör` and `Hotellmedarbetare` while the migration destination is `Städare`.

### Multi-context title qualification

There are 43 observed queries where title tokens plus additional words uniquely identify one of the title's published sibling occupation contexts.

- 35/43 Hit@5 = **81.395%** unweighted;
- 705,856 / 719,510 observed volume Hit@5 = **98.102%** weighted.

This is narrow inferred intent rather than click ground truth, but it directly tests whether a user can write something like `titel + bransch/context` and get the matching parenthetical variant.

### Verified fuzzy multi-context collapse

A separate structural stress test generated one realistic edit typo for every multi-context title for which current YV entered fuzzy fallback and still recognised the job-title.

- **539 eligible real multi-context job titles**;
- expected 2–3 contextual rows per title;
- **0/539 preserved all contexts**;
- **539/539 returned exactly one context row**.

Cause: the current fuzzy lane deduplicates candidates by job-title ID. Multiple parenthetical rows intentionally share that ID, so the first fuzzy row suppresses its sibling contexts.

This proves a product behavior, not its traffic incidence. It is nevertheless a direct, cheap bug because fuzzy search should preserve the same contextual identity model that exact/direct search preserves.

A surgical YV patch is being verified separately; no semantic retrieval is required.

## KV — current canonical vocabulary is materially underused

Across 1,358 non-collision source-attested KV surfaces:

- **78.130% Discovery@5**;
- **17.894% produce no results at all**.

KV has no equivalent query-frequency log, so traffic-weighted claims are not possible. Historical occurrence is retained only as a target-popularity proxy.

### Canonical alternative labels

This is the strongest KV result:

- 1,269 canonical alternative-label cases;
- 1,052 Hit@5;
- **217 misses**;
- **82.900% Discovery@5**.

Examples:

- `Microsoft Office` → `MS Office`: **no results**.
- `Officepaketet` → `MS Office`: **no results**.
- `Kundvård` → `Customer Relationship Management/CRM`: fuzzy results are instead dominated by `hudvård` concepts.
- `Javascript-kompetens` → `JavaScript, programmeringsspråk`: **no results**.
- `Javascript-kunskap`, `Javascript-utveckling`, `Javascriptkompetens`, `Javascriptkunskap` likewise miss the same active skill.
- `Legitimation som sjukgymnast` → `Legitimation som fysioterapeut`: **no results**.

These examples support a simple diagnosis before any semantic model: KV's candidate generation indexes preferred labels/tokens but does not exploit canonical alternative vocabulary already owned by the taxonomy.

### Hidden and deprecated labels

Canonical hidden labels: 4/9 Hit@5. Hidden labels need explicit product-policy review before being made user-searchable.

Deprecated unique-replacement labels: 8/88 Hit@5. Again, this is migration evidence only and must not be treated as synonym ground truth.

## Track-1 decision

We now explicitly have two project tracks:

1. **Track 1 — current YV/KV findability.** Explain and fix why people cannot find occupations/competences in the existing selector experience: vocabulary, ranking, recognisability, ambiguity/context, fuzzy behavior, variant overload, interaction and YV→KV hand-off.
2. **Track 2 — free-text description fallback.** Evaluate what `Beskriv yrket/kompetensen` should do after ordinary findability has been made honest.

**Track 2 is paused.** Existing semantic C0/C1/C2 experiments remain useful evidence but do not drive new work until Track 1 is run to its decision boundary.

Immediate Track-1 order:

1. patch and regression-test the verified YV fuzzy multi-context collapse;
2. replay the frozen persona journeys against exact current YV/KV behavior;
3. classify high-signal canonical alias misses by recognisability, ambiguity and demand;
4. prototype the smallest canonical-alias inclusion for YV/KV and measure gain/regression before broader changes;
5. verify YV→KV context coherence in real integration paths where accessible;
6. produce a compact failure-mode map with estimated materiality and recommended product fixes;
7. only then resume Track 2.
