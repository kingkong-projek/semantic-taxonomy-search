#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

RAW = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pareto-demand-v31/aggregate.json")
raw = json.loads(RAW.read_text(encoding="utf-8"))
occ = raw["occupation_name"]
skill = raw["skill"]
op = occ["pareto_within_active_v31_observed_occurrence_mass"]
sp = skill["pareto_within_active_v31_observed_occurrence_mass"]


def threshold_copy(p):
    return {k: dict(v) for k, v in p["thresholds"].items()}


def ranked_p95(p):
    return [
        {
            "rank": i,
            "concept_id": row["concept_id"],
            "label": row["label"],
            "occurrences": row["occurrences"],
        }
        for i, row in enumerate(p["priority_sets"]["p95"], 1)
    ]


compact = {
    "schema_version": 1,
    "taxonomy_version": 31,
    "measured_at": raw["measured_at"],
    "semantics": raw["semantics"],
    "sources": raw["sources"],
    "selection_rule": {
        "initial_semantic_priority_envelope": "P80 prefix by Historical API occurrence count among active v31 concepts represented in the stats response",
        "expansion_tiers": ["P90", "P95"],
        "lexical_fallback": "full product-valid taxonomy universe remains available through the existing lexical picker",
        "p80_membership_reproduction": "take the first threshold.p80.concept_count rows from ranked_p95",
        "p90_membership_reproduction": "take the first threshold.p90.concept_count rows from ranked_p95",
    },
}
for name, source, pareto in (("occupation_name", occ, op), ("skill", skill, sp)):
    compact[name] = {
        "historical_stat_rows": source["historical_stat_rows"],
        "active_v31_rows": source["active_v31_rows"],
        "active_v31_target_universe": source["active_v31_target_universe"],
        "active_v31_targets_with_observed_occurrence_pct": source["active_v31_targets_with_observed_occurrence_pct"],
        "all_historical_occurrences": source["all_historical_occurrences"],
        "active_v31_occurrences": source["active_v31_occurrences"],
        "active_v31_share_of_returned_occurrences_pct": source["active_v31_share_of_returned_occurrences_pct"],
        "thresholds": threshold_copy(pareto),
        "ranked_p95": ranked_p95(pareto),
    }

out = Path("research/coverage/v31/pareto-demand-aggregate.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(compact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def top_lines(rows, n=12):
    return "\n".join(
        f"- `{r['concept_id']}` — {r['label']}: {r['occurrences']:,}" for r in rows[:n]
    )


finding = f"""# Pareto demand priority — taxonomy v31

**Status:** measured  
**Measured:** 2026-09-06

## Conclusion

The first semantic-search release does not need equal semantic coverage of all 2,105 occupations and 6,752 skills.

Historical API exposes server-side taxonomy occurrence statistics for both `occupation-name` and `skill`. Intersected with active v31 identities, the occurrence mass is strongly concentrated:

| share of observed active-v31 occurrence mass | occupations | skills |
|---:|---:|---:|
| 50% | {op['thresholds']['p50']['concept_count']:,} | {sp['thresholds']['p50']['concept_count']:,} |
| 80% | **{op['thresholds']['p80']['concept_count']:,}** | **{sp['thresholds']['p80']['concept_count']:,}** |
| 90% | {op['thresholds']['p90']['concept_count']:,} | {sp['thresholds']['p90']['concept_count']:,} |
| 95% | {op['thresholds']['p95']['concept_count']:,} | {sp['thresholds']['p95']['concept_count']:,} |
| 99% | {op['thresholds']['p99']['concept_count']:,} | {sp['thresholds']['p99']['concept_count']:,} |

The **P80 core is therefore 159 occupation-name identities + 316 skill identities = 475 canonical targets**. P90 and P95 are explicit expansion tiers rather than launch requirements.

Active v31 concepts represented in the Historical stats response:

- occupations: **{occ['active_v31_rows']:,}/{occ['active_v31_target_universe']:,} = {occ['active_v31_targets_with_observed_occurrence_pct']}%**;
- skills: **{skill['active_v31_rows']:,}/{skill['active_v31_target_universe']:,} = {skill['active_v31_targets_with_observed_occurrence_pct']}%**.

The frozen aggregate stores the full ranked P95 population. P80/P90 memberships are deterministic prefixes of that ranking, so no hand-maintained allow-list is needed.

## Semantics and boundary

These counts are a **corpus/popularity proxy derived from historical job-ad taxonomy occurrences**. They are useful for deciding what to make good first. They are not:

- user query→selection ground truth;
- proof that a skill is essential or required;
- canonical meaning;
- a reason to remove tail concepts from the products.

The full lexical picker remains the fallback over the entire product-valid taxonomy. The Pareto set limits only what the first semantic description lane is required to solve well.

YV additionally has real Platsbanken search-frequency evidence. That source remains valuable for query sampling and a later traffic-weighted cross-check, but its free text cannot be fully mapped to canonical destinations automatically. Using Historical occurrence counts gives one simple, explicit concept-level priority proxy shared by YV occupations and KV skills.

## v0 simplification

For the first semantic decision benchmark and prototype:

- **YV semantic destinations:** the 159 P80 `occupation-name` identities;
- **KV semantic destinations:** the 316 P80 active `skill` identities;
- **YV job titles:** continue to work through the existing lexical picker and may act as router/retrieval vocabulary, but are not required as direct semantic destinations in v0;
- a small safety/regression slice still covers multi-parent titles, excluded-title routing, hard negatives and abstention;
- P90/P95 and the remaining long tail are measured expansion tiers only.

This does not change YV's product-valid destination universe. It narrows only the first semantic lane.

## Top observed occupations

{top_lines(op['priority_sets']['p80'])}

## Top observed skills

{top_lines(sp['priority_sets']['p80'])}

## Reproducibility

- Taxonomy v31 source SHA-256: `{raw['sources']['taxonomy']['sha256']}`
- Historical API Swagger SHA-256: `{raw['sources']['historical_api_swagger']['sha256']}`
- Historical stats response SHA-256: `{raw['sources']['historical_stats']['sha256']}`
- Measurement code: `scripts/pareto_demand_coverage.py`
- Frozen machine evidence: `research/coverage/v31/pareto-demand-aggregate.json`
"""
Path("docs/findings/pareto-demand-priority-v31.md").write_text(finding, encoding="utf-8")

# Source registry.
registry_path = Path("research/coverage/source-adapters.json")
registry = json.loads(registry_path.read_text(encoding="utf-8"))
registry["last_updated"] = "2026-09-06"
adapter = {
    "id": "historical-taxonomy-demand-stats",
    "status": "measured",
    "provenance_class": "corpus_derived",
    "target_types": ["occupation-name", "skill"],
    "join_key": "taxonomy concept_id, intersected with active v31 identity universe",
    "dimensions": [
        "historical occurrence count",
        "P50/P80/P90/P95/P99 cumulative occurrence tiers",
        "ranked P95 priority membership",
    ],
    "source": raw["sources"]["historical_stats"]["url"],
    "source_sha256": raw["sources"]["historical_stats"]["sha256"],
    "evidence": [
        "docs/findings/pareto-demand-priority-v31.md",
        "research/coverage/v31/pareto-demand-aggregate.json",
    ],
    "notes": "Historical API server-side taxonomy occurrence statistics. Used only as a corpus/popularity proxy for simple-first target prioritisation; not user query intent, semantic ground truth, canonical authority, or skill-essentiality evidence. P80 is the initial semantic priority envelope; full lexical product coverage remains unchanged.",
}
adapters = registry.get("adapters")
if not isinstance(adapters, list):
    raise RuntimeError("source adapter registry missing adapters list")
registry["adapters"] = [
    a for a in adapters if not (isinstance(a, dict) and a.get("id") == adapter["id"])
] + [adapter]
registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# SSOT guarded updates.
plan_path = Path("docs/research-plan.md")
text = plan_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one marker, got {count}")
    text = text.replace(old, new, 1)


replace_once(
    "Where real demand data exists, optimise the first release for cumulative user value rather than equal concept coverage. YV can use measured search frequency as a demand signal. KV currently lacks equivalent query→skill demand telemetry, so source-supported/common product contexts may be used only as an explicit proxy, never mislabeled as traffic.",
    "Where real demand data exists, optimise the first release for cumulative user value rather than equal concept coverage. YV has measured Platsbanken search frequency for query sampling. For concept-level prioritisation across both products, Historical API taxonomy occurrence counts are now measured as one simple shared corpus/popularity proxy. They are **not user traffic** and are never mislabeled as query→selection evidence.",
    "pareto principle source paragraph",
)

section_marker = "Evidence: `docs/findings/unified-target-coverage-v31.md` and `research/coverage/v31/unified-target-coverage-aggregate.json`.\n\n## 6. Semantic boundaries"
section = """Evidence: `docs/findings/unified-target-coverage-v31.md` and `research/coverage/v31/unified-target-coverage-aggregate.json`.

### 5.16 Pareto demand priority

Historical API server-side taxonomy occurrence statistics provide a cheap concept-level popularity proxy for both occupations and skills. After intersecting with active v31 identities:

| cumulative share of observed active-v31 occurrence mass | occupation-name | skill |
|---:|---:|---:|
| 50% | 33 | 63 |
| 80% | **159** | **316** |
| 90% | 302 | 614 |
| 95% | 455 | 976 |
| 99% | 834 | 1,848 |

The first semantic priority envelope is therefore **P80 = 159 YV occupations + 316 KV skills = 475 canonical targets**. P90/P95 are explicit expansion tiers. The exact ranked P95 memberships are frozen in repo, so P80/P90 are reproducible prefixes rather than hand-maintained lists.

This is a `corpus_derived` popularity proxy, not user intent or destination ground truth. Existing lexical search continues to cover the full product-valid taxonomy.

**v0 semantic-lane simplification:** YV semantic description search is required initially to emit only the P80 `occupation-name` set. Published job titles remain fully available in the existing lexical picker and may be semantic routing/context vocabulary, but direct semantic `job-title` destinations are deferred until benchmark/telemetry shows material value. KV semantic description search starts with the P80 skill set.

Evidence: `docs/findings/pareto-demand-priority-v31.md` and `research/coverage/v31/pareto-demand-aggregate.json`.

## 6. Semantic boundaries"""
replace_once(section_marker, section, "Pareto measured-state insertion")

old_gate = """Mandatory YV strata:

- exact published job-title;
- measured 541-title multi-parent ambiguity population;
- 205-title excluded-YV retrieval-vocabulary population, split by >3-context vs redundant-label policy;
- high-frequency excluded-title terms from observed query data;
- unbound observed query-language samples with **manual judgments**, not auto-labels;
- raw daily JobSearch Trends recency/long-tail samples, with `q_approved` treated only as privacy-filtered behavioral wording;
- task/skill description→occupation;
- same/similar title in different occupational contexts;
- substitutability 25/75 neighbours as hard-negative/context material.

Mandatory KV strata:

- skill descriptions without canonical terminology;
- software/tool/certificate/qualification/experience-like skill subtypes;
- occupation phrase→relevant skills;
- native curated vs calculated vs transferable evidence;
- Relevanta-only incremental skill population;
- nearby/confusable skills that must remain MUST_NOT."""
new_gate = """Initial YV benchmark priority:

- the **159 P80 occupation-name identities** are the core semantic destination population;
- exact/prefix lexical behavior remains a full-universe regression baseline, not something semantic v0 must reimplement;
- high-volume admitted/excluded job-title wording is sampled as router language into product-valid occupations;
- a **small** multi-parent-title safety slice is retained; the full 541-title population is not an initial benchmark requirement;
- a **small** excluded-title routing safety slice is retained; the full 205-title population is reproducible but not all must be manually judged now;
- a small high-volume unbound observed-query sample receives human judgments;
- task/skill description→occupation and hard-negative/no-match cases focus primarily on P80;
- P90/P95/tail contribute only small boundary/sentinel samples initially.

Initial KV benchmark priority:

- the **316 P80 active skill identities** are the core semantic destination population;
- exact/alternative labels plus description-style cases focus on that core;
- occupation→skill bridge, transferable/calculated/Relevanta and subtype cases are sampled where they materially exercise the P80 core;
- nearby/confusable skills and no-match/abstention remain explicit safety cases;
- P90/P95/tail contribute only small boundary/sentinel samples initially."""
replace_once(old_gate, new_gate, "Gate-2 strata")

replace_once(
    "- [ ] define the compact Pareto decision slice: demand-weighted where real demand exists, otherwise explicit source-strength/context proxy\n- [ ] freeze 500–1,000 high-confidence/source-truth seed cases sufficient to compare simple baselines",
    "- [x] define the compact Pareto decision slice: **P80 = 159 occupation-name + 316 skill targets**, using Historical API occurrence counts as an explicit corpus/popularity proxy; exact P95 membership frozen in repo\n- [ ] freeze a 500–1,000 case benchmark around the 475-target P80 core plus compact safety/boundary slices",
    "Gate-2 work sequence",
)

replace_once(
    "- [ ] YV `Beskriv yrket`\n- [ ] KV `Beskriv kompetensen`",
    "- [ ] YV `Beskriv yrket` — v0 semantic destination envelope: P80 occupation-name only; lexical picker still supports full YV including job titles\n- [ ] KV `Beskriv kompetensen` — v0 semantic destination envelope: P80 skills; lexical picker still supports full KV",
    "prototype scope",
)

replace_once(
    "34. What cumulative share of real YV demand can a simple configuration solve at acceptable precision before long-tail enrichment is added?\n35. What is the smallest evidence/retrieval configuration whose Pareto performance is statistically/materially indistinguishable from more complex alternatives?",
    "34. Concept-level Pareto priority? **Historical ad-taxonomy occurrence proxy gives P80 = 159 active occupations + 316 active skills; P90 = 302 + 614; P95 = 455 + 976. This is popularity, not query→selection truth.**\n35. What cumulative share of real YV query demand does the P80 occupation envelope cover once high-volume observed wording is manually/safely mapped?\n36. What is the smallest evidence/retrieval configuration whose Pareto performance is statistically/materially indistinguishable from more complex alternatives?",
    "open research questions",
)

plan_path.write_text(text, encoding="utf-8")
