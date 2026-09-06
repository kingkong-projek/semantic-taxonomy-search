from pathlib import Path

p = Path('docs/research-plan.md')
s = p.read_text(encoding='utf-8')

replacements = [
    (
        """We are therefore investigating a **reusable findability/retrieval capability for occupations and skills/competences**, with semantic retrieval as one candidate capability rather than the assumed diagnosis. YV and KV are the first concrete products in which the findability problem is measured.

YV and KV are current **reference profiles and the first product problem to solve**, not the scope boundary of the retrieval core. JobSearch/Platsbanken and other AF datasets are evidence sources, not the target product.
""",
        """This repository builds a **reusable semantic search/fallback capability for occupations and skills/competences**. It does not own or rebuild YV/KV's ordinary selector UX. YV and KV are the first concrete reference consumers against which we establish the lexical/product baseline and determine what semantic search must add.

The YV/KV audit is therefore a deliberately bounded **Track-1 sidetrack for problem understanding, baseline quality and integration boundaries**, not the delivery scope of this repository. Findings may identify product-native YV/KV defects or bounded improvements, but adoption belongs to the owning product repositories and their protected integration process. GitHub branch/CI verification is evidence, not deployment. JobSearch/Platsbanken and other AF datasets are evidence sources, not the target product.
""",
        'scope',
    ),
    (
        """Even a near-perfect YV/KV selector still leaves a separate product need: some users do not know the occupational or competence term they need to search for. Semantic free-text is intended for that case, not as a replacement for a healthy lexical selector. The preferred UX is a progressive fallback ladder:

```text
1. ordinary YV/KV lookup
2. if the user does not get a useful match: [Sök med fritext]
3. interpret description/task/tool/method language and return canonical candidates
4. if confidence is still insufficient: [Ge förslag] / clarification rather than forcing a nearest neighbour
```

The exact labels are product copy hypotheses, not a frozen UI contract. The important contract is progressive disclosure: do not make users describe something semantically when they already know its name, but provide semantic help when naming/terminology is the actual obstacle. `Tillåt fritext` should therefore not be treated as a mere manual-string escape hatch; the semantic path should be framed as an active **search with free text**, with safe suggestions/clarification if a direct confident match is unavailable.
""",
        """A separate Track-2 hypothesis remains to be tested: **when ordinary YV/KV lookup does not produce a selection the user recognises as correct, describing the work or competence in ordinary language may recover an existing taxonomy identity before the user proposes a new one**. This is a hypothesis about one failure mechanism, not a claim that users generally do not know their occupation/competence terms.

The intended product sequence is a progressive fallback ladder around otherwise unchanged YV/KV selectors:

```text
1. ordinary YV/KV lookup exactly as the owning product provides it
2. if the user still cannot find a suitable existing result: [Beskriv ditt yrke] / [Beskriv din kompetens]
3. open description mode and interpret task/tool/method/responsibility language against existing admissible canonical candidates
4. if the user still cannot find what they mean: [Ge förslag] for a genuinely missing/unsuitable concept rather than silently accepting an arbitrary custom value
```

The labels are product-copy hypotheses, but the ordering is a scope contract for this research: **ordinary selector first → semantic description fallback → proposal last**. The semantic capability must try to recover an existing canonical identity; it must not turn free text into a new selectable taxonomy identity. `Ge förslag` is downstream product handling for the case where semantic retrieval still does not yield an acceptable existing concept.
""",
        'ux',
    ),
    (
        """**Track 1 — current YV/KV findability (NOW).** Explain and fix why people sometimes fail to find an occupation or competence in the existing selectors. This includes canonical vocabulary reachability, ranking/recognisability, broad-vs-specific variants, job-title/occupation context, typo/fuzzy behaviour, interaction, and YV→KV context/coherence. Run this track to a compact decision boundary before doing more free-text work.

**Track 2 — free-text description fallback (PAUSED).** Determine what `Beskriv yrket/kompetensen` should do for users who still cannot find what they need after Track 1. Existing C0/C1/C2/F1 and frozen description/synthetic-query evidence is retained, but no new model/source/tuning decision is allowed to be driven by Track 2 until Track 1 exits.
""",
        """**Track 1 — current YV/KV findability (NOW; bounded sidetrack).** Establish whether ordinary selectors already do their intended job well enough, and classify only material product-native failures that would otherwise be misdiagnosed as a need for semantic search. This includes canonical vocabulary reachability, ranking/recognisability, broad-vs-specific variants, job-title/occupation context, typo/fuzzy behaviour, interaction, and YV→KV context/coherence. Track 1 may produce evidence or product-branch proposals, but YV/KV implementation is outside this repository's semantic-search abstraction. Run this track only to a compact decision boundary before resuming semantic work.

**Track 2 — semantic description fallback (PAUSED).** Build and evaluate the capability behind `Beskriv ditt yrke` / `Beskriv din kompetens` for users who still cannot select a suitable existing concept through ordinary lookup. Existing C0/C1/C2/F1 and frozen description/synthetic-query evidence is retained, but no new model/source/tuning decision is allowed to be driven by Track 2 until Track 1 exits. If description search still yields no acceptable existing identity, the consumer may offer `Ge förslag`; proposal handling itself is outside the semantic retrieval core.
""",
        'tracks',
    ),
    (
        """**Track 1 status — canonical alias reachability measured (2026-09-06).** Against current YV `ab0b3f28576d8aebec2b593b771a70c7684b1eca`, current canonical alternative/hidden labels are overwhelmingly unambiguous (YV 361/362 unique-target surfaces; KV 1,289/1,317). The current selector already finds 318/357 strict YV alias cases and 1,056/1,278 KV cases at 5. A privileged exact-normalized current-alias lane would deterministically rescue the remaining **39 YV** and **222 KV** strict cases, reaching 100% on that bounded set. The YV increment is modest by observed alias-query volume (**1.422%**); the KV increment is materially larger by the available target-occurrence priority proxy (**50.902%** of the alias-set proxy mass rescued). Therefore the next cheapest Track-1 intervention is to implement current canonical aliases before any semantic expansion. Alias collisions fail closed / remain multi-candidate; deprecated `replaced_by` labels are explicitly excluded from synonym treatment. Evidence: `docs/findings/track1-canonical-alias-reachability-v31.md` and `research/evaluation/v31/track1-canonical-alias-rescue.json`.
""",
        """**Track 1 status — canonical alias reachability measured and branch-verified (2026-09-06).** Against the pinned current-selector baseline, current canonical alternative/hidden labels are overwhelmingly unambiguous. The current selector finds 318/357 strict YV alias cases and **1,056/1,279 KV** cases at 5. A privileged exact-normalized current-alias lane deterministically rescues the remaining **39 YV** and **223 KV** strict cases, reaching 100% on that bounded set. The safe implementation has been verified on the YV/KV product branch with full self-hosted build/tests, but it is not deployed by this research repository. Alias collisions fail closed / remain multi-candidate; deprecated `replaced_by` labels are explicitly excluded from synonym treatment. Evidence: `docs/findings/track1-canonical-alias-reachability-v31.md` and `research/evaluation/v31/track1-canonical-alias-rescue.json`.
""",
        'aliases',
    ),
]

for old, new, label in replacements:
    if old not in s:
        raise SystemExit(f'missing anchor: {label}')
    s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
