#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

path = Path("docs/research-plan.md")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        """We are building semantic search for **both Yrkesväljaren (YV) and Kompetensväljaren (KV)**.\n\nA person often knows what they do or can do, but not the exact taxonomy wording. The products therefore need better retrieval without weakening canonical identity.\n\nThe destination spaces are intentionally different:\n\n- **YV:** published/selectable `occupation-name` and `job-title` with exact occupation-name context preserved.\n- **KV:** active `skill` identities.\n\nOccupation, SSYK, skill-headline, keyword, ESCO, excluded YV title vocabulary and other concepts may be used as evidence/routing/context. They are not interchangeable with the returned identity.\n\nHard shared rule:\n\n> Semantic retrieval may discover, expand, route, rank and explain candidates. It may never invent, merge or mutate canonical taxonomy identities or silently expand a product's selectable destination space.""",
        """We are building a **reusable semantic retrieval capability for occupations and skills/competences** in services where a user must identify or select taxonomy concepts without knowing the taxonomy's exact wording.\n\nYrkesväljaren (YV) and Kompetensväljaren (KV) are current **reference profiles**, not the scope boundary of the retrieval core. JobSearch/Platsbanken and other AF datasets are evidence sources, not the target product.\n\nThe core target spaces are intentionally simple:\n\n- **occupation:** canonical active `occupation-name` identities;\n- **skill:** canonical active `skill` identities.\n\nA consuming service applies its own admission/profile rules after or around retrieval. YV may therefore admit published occupation/job-title identities with exact occupation context, while another service may admit a different occupation subset. KV is one concrete skill-selection profile.\n\nOccupation context, job titles, SSYK, skill-headline, keyword, ESCO and other concepts may be used as evidence/routing/context. They are not interchangeable with the returned core identity.\n\nHard shared rule:\n\n> Semantic retrieval may discover, expand, route, rank and explain candidates. It may never invent, merge or mutate canonical taxonomy identities, and it may never bypass the consuming service's explicit admission policy.""",
    ),
    (
        """Do not replace either picker with a chatbot.\n\nKeep the current fast lexical picker as the privileged path. Add semantic description search when ordinary lookup is insufficient, for example:\n\n```text\nYV: Hittar du inte det du söker? [Beskriv yrket]\nKV: Hittar du inte kompetensen? [Beskriv kompetensen / vad du kan göra]\n```\n\nThe result remains exact canonical/product-valid YV/KV identities. `Inget av dessa` / abstention is a first-class successful outcome. A nearest neighbour is not proof that a valid match exists.""",
        """Do not replace ordinary selectors with a chatbot.\n\nKeep fast lexical selection as the privileged path where a consuming service already has it. Add semantic description search when ordinary lookup is insufficient. YV/KV remain useful reference UX examples:\n\n```text\nYV: Hittar du inte det du söker? [Beskriv yrket]\nKV: Hittar du inte kompetensen? [Beskriv kompetensen / vad du kan göra]\n```\n\nThe core result remains an exact canonical occupation/skill identity with provenance; the consumer then enforces its admission profile. `Inget av dessa` / abstention is a first-class successful outcome. A nearest neighbour is not proof that a valid match exists.""",
    ),
    (
        "Where real demand data exists, optimise the first release for cumulative user value rather than equal concept coverage. YV has measured Platsbanken search frequency for query sampling. For concept-level prioritisation across both products, Historical API taxonomy occurrence counts are now measured as one simple shared corpus/popularity proxy. They are **not user traffic** and are never mislabeled as query→selection evidence.",
        "Where real demand data exists, optimise the first release for cumulative user value rather than equal concept coverage. Platsbanken/YV provides one measured source of real occupation-query language for sampling; it is evidence about that usage context, not the scope of the engine. For concept-level prioritisation across occupation and skill target spaces, Historical API taxonomy occurrence counts are now measured as one simple shared corpus/popularity proxy. They are **not user traffic** and are never mislabeled as query→selection evidence.",
    ),
    (
        """The retrieval infrastructure may be shared, but each request has an explicit target space:\n\n```text\nYV -> published occupation / job-title-in-occupation-context\nKV -> active skill\n```\n\nCross-entity bridges generate evidence; they do not convert identity.""",
        """Each core request has an explicit semantic target space independent of the consuming service:\n\n```text\noccupation -> active canonical occupation-name candidates\nskill      -> active canonical skill candidates\n```\n\nA separate consumer/admission profile constrains what a specific service may present or select. YV and KV are the first measured profiles; they are not hard-coded engine target spaces. Cross-entity bridges generate evidence; they do not convert identity.""",
    ),
    (
        "The first semantic priority envelope is therefore **P80 = 159 YV occupations + 316 KV skills = 475 canonical targets**. P90/P95 are explicit expansion tiers. The exact ranked P95 memberships are frozen in repo, so P80/P90 are reproducible prefixes rather than hand-maintained lists.",
        "The first semantic priority envelope is therefore **P80 = 159 occupations + 316 skills = 475 canonical targets**. YV/KV are the measured reference profiles used to validate this envelope, not the definition of the core target spaces. P90/P95 are explicit expansion tiers. The exact ranked P95 memberships are frozen in repo, so P80/P90 are reproducible prefixes rather than hand-maintained lists.",
    ),
    (
        """Build separate but structurally compatible YV and KV suites.\n\nStart with a **compact 500–1,000 case decision benchmark**""",
        """Build structurally compatible **occupation** and **skill** suites. YV/KV-labelled cases remain reference-profile fixtures where product admission semantics matter; they do not define the core engine API.\n\nThe current benchmark schema keeps `product: YV | KV` for frozen-fixture compatibility. Treat that field as an **admission/reference-profile label**, not as the semantic engine's `target_space`. A future schema revision should change it only when doing so buys concrete value; do not migrate the 950 frozen cases merely for naming purity.\n\nStart with a **compact 500–1,000 case decision benchmark**""",
    ),
    (
        "Evaluate YV and KV separately; do not force source symmetry.",
        "Evaluate occupation and skill retrieval separately; do not force source symmetry. Keep YV/KV reference-profile slices separate where their admission/routing semantics materially differ.",
    ),
    (
        "- YV and KV destination spaces never collapse;",
        "- occupation and skill core target spaces never collapse;\n- consumer admission profiles never silently expand because retrieval found extra vocabulary;",
    ),
    (
        """Possible shared request contract:\n\n```json\n{\n  \"taxonomy_version\": 31,\n  \"target_space\": \"YV | KV\",\n  \"query\": \"...\",\n  \"limit\": 10\n}\n```\n\nResponse must preserve taxonomy version, matcher version, target space, canonical candidate identity and provenance.""",
        """Possible shared core request contract:\n\n```json\n{\n  \"taxonomy_version\": 31,\n  \"target_space\": \"occupation | skill\",\n  \"query\": \"...\",\n  \"limit\": 10,\n  \"admission_profile\": \"optional consumer-defined profile/version\"\n}\n```\n\nThe engine must not require a named AF product to retrieve canonical candidates. A profile may constrain the candidate set before/after ranking when a consuming service needs stricter admission semantics. Response must preserve taxonomy version, matcher version, target space, canonical candidate identity, profile/admission provenance when used, and retrieval provenance.""",
    ),
    (
        "- [x] prepare deterministic **top-50 high-volume unbound YV review packet** from the pinned real query corpus: 742.0M searches = 23.661% of all volume / 35.117% of unbound volume; remains fully `PENDING_HUMAN_REVIEW`",
        "- [x] prepare deterministic **top-50 high-volume Platsbanken/YV occupation-language review packet** from the pinned real query corpus: 742.0M searches = 23.661% of all volume / 35.117% of unbound volume; remains fully `PENDING_HUMAN_REVIEW`; this is one behavioral evidence slice, not the engine's product scope",
    ),
    (
        """### Product prototype after evidence\n\n- [ ] YV `Beskriv yrket` — v0 semantic destination envelope: P80 occupation-name only; lexical picker still supports full YV including job titles\n- [ ] KV `Beskriv kompetensen` — v0 semantic destination envelope: P80 skills; lexical picker still supports full KV\n- [ ] `Inget av dessa` + feedback flow""",
        """### Prototype after evidence\n\n- [ ] reusable core retrieval prototype with `target_space = occupation | skill` and explicit versioned provenance\n- [ ] YV reference integration: `Beskriv yrket` with P80 occupation core plus YV admission/routing policy; lexical picker still supports full YV including job titles\n- [ ] KV reference integration: `Beskriv kompetensen` with P80 skill core plus KV admission/context policy; lexical picker still supports full KV\n- [ ] `Inget av dessa` + feedback flow""",
    ),
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one SSOT marker, got {count}: {old[:100]!r}")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print(f"updated {len(replacements)} guarded scope markers")
