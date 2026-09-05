#!/usr/bin/env python3
"""One-shot asserted transition of the living research plan after Gate 1 closure."""
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


plan_path = Path("docs/research-plan.md")
text = plan_path.read_text(encoding="utf-8")

text = replace_once(text, "**Last updated:** 2026-09-04  ", "**Last updated:** 2026-09-06  ", "last-updated")

text = replace_once(
    text,
    """**Still open:** those legacy IDs/slugs have not yet been proven to map safely to v31 `occupation-name` identities. Distribution identity is resolved; canonical joinability is not.

Until that join is proven, Yrkesinformation text cannot inherit v31 authority merely through label similarity.

Extractor: `scripts/occupational_information_coverage.py`.""",
    """Canonical joinability is now measured across all 324 records:

- **85** records contain exactly one explicit active v31 `occupation-name` ID and may attach their semantic text to that identity;
- **34** contain multiple explicit active occupation IDs and remain ambiguous;
- **205** contain no explicit active occupation ID and remain blocked from canonical attachment.

Exact preferred/alternative-label equality is retrieval candidate evidence only. It does not resolve the 239 ambiguous/unkeyed records. We therefore use the safe 85-record subset and fail closed for the rest rather than manufacture a legacy-ID/slug mapping.

Evidence: `docs/findings/occupational-information-join-v31.md` and `research/coverage/v31/occupational-information-aggregate.json`.

Extractor: `scripts/occupational_information_coverage.py`.""",
    "yrkesinformation-decision",
)

text = replace_once(
    text,
    "Evidence: `docs/findings/job-ad-source-boundaries-2026-09-04.md`.\n\n## 6. Semantic boundaries",
    """Evidence: `docs/findings/job-ad-source-boundaries-2026-09-04.md`.

### 5.14 Deprecated → active compatibility v31

The replacement graph is now measured for **3,031** deprecated concepts in YV/KV-relevant types:

- **1,845** resolve to exactly one active same-type target;
- **277** resolve to multiple active targets and must disambiguate/fail closed;
- **909** have no active target;
- direct target type mismatches: **0**;
- unknown direct replacement targets: **0**.

For unique routes, YV still rejects 8 active job-title targets under its measured product policy. `replaced_by` therefore remains a separate migration/history signal, not synonymy and not a bypass around product admission.

Evidence: `docs/findings/deprecated-compatibility-coverage-v31.md` and `research/coverage/v31/deprecated-compatibility-aggregate.json`.

### 5.15 Unified per-target coverage v31

The complete hash-verified target matrix is now measured against current accepted v31 sources:

- YV occupation-name identities: **2,105**;
- selectable YV job-title-in-occupation-context rows: **10,225** from 9,580 unique job-title IDs;
- YV excluded active retrieval-only titles: **205**;
- KV active skills: **6,752**.

Important overlapping weak strata include **244** YV occupations that are canonical-text-poor and lack observed ad language, **1,410** critical-sparse KV skills, **1,701** skills without YV/KV relevance context, and the identity-risk populations of 1,186 multi-parent YV context rows plus 205 excluded-title routes.

This replaces the earlier partial offline matrix as the Gate-1 coverage result. The offline reconstruction remains useful provenance for the post-transfer outage, but `UNKNOWN` derived layers are no longer the current state.

Evidence: `docs/findings/unified-target-coverage-v31.md` and `research/coverage/v31/unified-target-coverage-aggregate.json`.

## 6. Semantic boundaries""",
    "gate1-measured-sections",
)

text = replace_once(
    text,
    """### Remaining before Gate 1 closes

- [ ] determine whether Yrkesinformation legacy ID/slug records can be canonically joined to active v31 occupation identities; otherwise explicitly mark it retrieval-only/blocked for canonical attachment
- [ ] measure/build deprecated → active compatibility semantics without polluting active identity
- [ ] build unified per-target coverage matrix and identify the lowest-coverage YV/KV strata

Generic public JobSearch Trends beyond the exact generator-bound snapshot are **not** a Gate-1 blocker. Their lineage can be sampled later if the measured YV snapshot is insufficient.

Gate 1 is complete only when the three remaining items are measured, explicitly blocked or scoped out with rationale.""",
    """### Gate 1 closure — 2026-09-06

- [x] Yrkesinformation legacy→v31 joinability measured: 85 records have one explicit active occupation identity; 34 are ambiguous and 205 unkeyed records fail closed
- [x] deprecated→active compatibility policy and full measurement completed
- [x] unified hash-verified per-target coverage matrix completed and lowest-coverage strata identified

Generic public JobSearch Trends beyond the exact generator-bound snapshot remain **not a Gate-1 blocker**. Their lineage can be sampled later if the measured YV snapshot is insufficient.

**Gate 1 is closed.** Every originally required item is measured, explicitly bounded or deliberately blocked with an authority-preserving rationale. Work now moves to Gate 2; new source discoveries do not reopen Gate 1 unless they invalidate an accepted source boundary or target universe.""",
    "gate1-checklist",
)

text = replace_once(
    text,
    """### Now — close Gate 1

- [x] native text + common graph
- [x] YV/KV selector inventories
- [x] YV ambiguity + exact generator admission/exclusion policy
- [x] YV observed query-language measurement
- [x] KV transferable skills
- [x] native occupation→skill / KV exact relationship
- [x] Relevanta kompetenser
- [x] dedicated keyword/search concepts
- [x] curated substitutability
- [x] Närliggande yrken + employer-language keyword coverage
- [x] Yrkesinformation distribution discovery
- [x] ad / enrichment provenance boundary; raw full-corpus ETL scoped to Gate 2
- [ ] Yrkesinformation legacy→v31 canonical join decision
- [ ] deprecated→active compatibility policy + measurement
- [ ] unified coverage matrix + lowest-coverage strata

### Next — Gate 2

- [ ] benchmark schema""",
    """### Gate 1 — closed 2026-09-06

- [x] native text + common graph
- [x] YV/KV selector inventories
- [x] YV ambiguity + exact generator admission/exclusion policy
- [x] YV observed query-language measurement
- [x] KV transferable skills
- [x] native occupation→skill / KV exact relationship
- [x] Relevanta kompetenser
- [x] dedicated keyword/search concepts
- [x] curated substitutability
- [x] Närliggande yrken + employer-language keyword coverage
- [x] Yrkesinformation distribution + fail-closed legacy→v31 join decision
- [x] deprecated→active compatibility policy + measurement
- [x] unified coverage matrix + lowest-coverage strata
- [x] ad / enrichment provenance boundary; raw full-corpus ETL scoped to Gate 2

### Now — Gate 2

- [x] benchmark schema and semantic validator contract""",
    "work-sequence",
)

text = replace_once(
    text,
    "21. Yrkesinformation distribution? **Resolved; legacy→v31 canonical join still open**.",
    "21. Yrkesinformation distribution/join? **Resolved: 85/324 records have one explicit active v31 occupation ID and may attach canonically; 34 are ambiguous and 205 have none, so 239 fail closed.**",
    "question-21",
)
text = replace_once(
    text,
    "24. How should deprecated concepts support old wording without polluting active identity?",
    "24. Deprecated concepts? **Separate legacy retrieval/migration layer: 1,845 unique active routes, 277 branching routes and 909 without active target; replacement is not synonymy and product admission still applies.**",
    "question-24",
)
text = replace_once(
    text,
    "25. Which YV/KV targets have the lowest combined semantic coverage once all accepted layers are composed?",
    "25. Lowest combined coverage? **Measured overlapping strata include 244 YV text-poor occupations without observed ad language, 6 YV occupations without skill context, 1,410 critical-sparse KV skills and 1,701 KV skills without YV/KV relevance context.**",
    "question-25",
)

text = replace_once(
    text,
    "No deployment choice is final before relevance, latency, privacy, availability, payload and iteration speed are measured.\n\n## 18. Work sequence",
    """No deployment choice is final before relevance, latency, privacy, availability, payload and iteration speed are measured.

### Research execution status

After the repository transfer, GitHub-hosted jobs were failing before their first step. Active research workflows now use the available self-hosted `Linux/X64` runner (`garderob` operationally). Benchmark contract, deprecated compatibility, resolved Gate-1 coverage and unified target coverage have all completed successfully on this path; this is execution infrastructure, not a product deployment decision.

## 18. Work sequence""",
    "runner-status",
)

plan_path.write_text(text, encoding="utf-8")

coverage_path = Path("scripts/unified_target_coverage.py")
coverage = coverage_path.read_text(encoding="utf-8")
coverage = replace_once(
    coverage,
    '            "Yrkesinformation legacy-to-v31 semantic text attachment until canonical join is resolved",\n            "deprecated historical vocabulary until replacement-graph measurement succeeds",',
    '            "Yrkesinformation text is canonically attachable only for records with exactly one explicit active v31 occupation ID; ambiguous/unkeyed records remain blocked",\n            "deprecated historical vocabulary is measured separately and remains outside the active target matrix by design",',
    "unified-pending-wording",
)
coverage_path.write_text(coverage, encoding="utf-8")
