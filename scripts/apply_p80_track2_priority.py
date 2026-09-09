#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARETO = ROOT / "research/coverage/v31/pareto-demand-aggregate.json"
DIVERSE = ROOT / "research/training/v31/a593-language-diversity-training-v0.jsonl"
REPORT = ROOT / "research/evaluation/v31/p80-track2-priority-coverage.json"
POPULATION = ROOT / "research/human/description-fallback-v1/p80-occupation-priority-population.json"
FINDING = ROOT / "docs/findings/p80-track2-priority-2026-09-09.md"
SSOT = ROOT / "SSOT.md"
PLAN = ROOT / "docs/research-plan.md"

MARKER = "P80-FIRST-TRACK2-2026-09-09"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def p80_rows(occupation: dict) -> list[dict]:
    total = int(occupation["active_v31_occurrences"])
    ranked = occupation["ranked_p95"]
    cumulative = 0
    rows = []
    for row in ranked:
        rows.append(row)
        cumulative += int(row["occurrences"])
        if cumulative / total >= 0.80:
            break
    if len(rows) != 159:
        raise SystemExit(f"P80 drift: expected frozen v31 count 159, got {len(rows)}")
    return rows


def insert_after_heading(path: Path, heading: str, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return
    pos = text.find(heading)
    if pos < 0:
        raise SystemExit(f"Could not find insertion heading {heading!r} in {path}")
    end = pos + len(heading)
    new_text = text[:end] + "\n\n" + block.strip() + "\n" + text[end:]
    path.write_text(new_text, encoding="utf-8")


def main() -> None:
    pareto = load_json(PARETO)
    occupation = pareto["occupation_name"]
    p80 = p80_rows(occupation)
    p80_ids = {row["concept_id"] for row in p80}

    diverse_rows = load_jsonl(DIVERSE)
    usable_diverse = {
        row["concept_id"]: row
        for row in diverse_rows
        if row.get("usable") and any(v for v in (row.get("phrases") or {}).values())
    }
    enriched_p80_ids = p80_ids & set(usable_diverse)
    missing_p80_ids = p80_ids - enriched_p80_ids

    p80_occ = sum(int(row["occurrences"]) for row in p80)
    enriched_p80_occ = sum(
        int(row["occurrences"]) for row in p80 if row["concept_id"] in enriched_p80_ids
    )

    enriched_rows = [
        {**row, "already_diversified_v0": row["concept_id"] in enriched_p80_ids}
        for row in p80
        if row["concept_id"] in enriched_p80_ids
    ]
    missing_rows = [
        {**row, "already_diversified_v0": False}
        for row in p80
        if row["concept_id"] in missing_p80_ids
    ]

    report = {
        "schema": "p80-track2-priority-coverage-v0",
        "taxonomy": "v31",
        "decision": {
            "optimization_priority": "P80-first",
            "occupation_candidate_universe": int(occupation["active_v31_target_universe"]),
            "candidate_universe_policy": "all active v31 occupation-name identities remain eligible",
            "synthetic_scaling_policy": "paused; do not mass-generate current Gemma diversification policy",
            "next_decision_bearing_evidence": "fresh independent human/user descriptions, P80-primary",
            "expansion_order": ["P80", "P90", "P95", "full long tail only when justified"],
        },
        "p80": {
            "occupation_count": len(p80),
            "historical_occurrences": p80_occ,
            "share_of_observed_active_v31_occurrences": p80_occ / int(occupation["active_v31_occurrences"]),
            "existing_diversified_v0_count": len(enriched_p80_ids),
            "missing_diversified_v0_count": len(missing_p80_ids),
            "existing_diversified_v0_share_of_p80_count": len(enriched_p80_ids) / len(p80),
            "existing_diversified_v0_share_of_p80_occurrence_mass": enriched_p80_occ / p80_occ,
        },
        "existing_diversified_v0": enriched_rows,
        "missing_diversified_v0": missing_rows,
        "notes": [
            "Coverage is planning metadata, not evidence that diversified synthetic language transfers to users.",
            "The full 2,105 occupation candidate universe remains unchanged.",
            "P80 is a quality/recruitment/evaluation priority stratum, not an allow-list.",
        ],
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    population = {
        "schema": "human-description-p80-occupation-priority-population-v0",
        "taxonomy": "v31",
        "purpose": "recruitment/evaluation priority for fresh independent human occupation descriptions",
        "candidate_universe": int(occupation["active_v31_target_universe"]),
        "priority_population_count": len(p80),
        "policy": "P80-primary sampling; valid non-P80 targets remain valid and must never be coerced into P80",
        "occupations": [
            {
                "rank": int(row["rank"]),
                "concept_id": row["concept_id"],
                "label": row["label"],
                "historical_occurrences": int(row["occurrences"]),
                "already_diversified_v0": row["concept_id"] in enriched_p80_ids,
            }
            for row in p80
        ],
    }
    POPULATION.write_text(json.dumps(population, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    finding = f"""# P80-first Track-2 priority — 2026-09-09

<!-- {MARKER} -->

## Decision

Track 2 now uses **P80-first optimization and evaluation** for occupations while preserving the full **{occupation['active_v31_target_universe']:,}** active-v31 occupation candidate universe.

The frozen demand proxy puts **{len(p80)} occupations at 80% of observed active-v31 historical occurrence mass**. These occupations are therefore the primary short-feedback-loop population. P90/P95/full-tail quality work is deferred until P80 evidence justifies expansion.

This is a prioritization rule, not an eligibility rule: a valid non-P80 occupation must remain retrievable and must never be coerced to a P80 identity.

## Current language-diversity overlap

Of the {len(p80)} P80 occupations, **{len(enriched_p80_ids)}** already have usable phrases in the frozen `a593-language-diversity-training-v0` corpus and **{len(missing_p80_ids)}** do not.

The already-diversified subset represents **{enriched_p80_occ / p80_occ:.1%}** of P80 historical occurrence mass.

This overlap is planning metadata only. The existing synthetic Gemma diversification policy is **not promoted for mass generation** because its large synthetic holdout gain did not reproduce on the corrected opened full-universe residual.

## Next short loop

1. Keep architecture A and all 2,105 occupation identities eligible.
2. Collect fresh independent human/user descriptions with **P80 as the primary recruitment/evaluation stratum** under the existing frozen human-study contract.
3. Report P80 separately, plus a small long-tail safety slice when evidence exists; do not use the tail to delay the P80 decision.
4. Compare current A against any language-enriched challenger only on evidence frozen before retrieval.
5. Expand quality work to P90 (302 occupations), then P95 (455), only after a material P80 result warrants it.

Machine-readable coverage: `research/evaluation/v31/p80-track2-priority-coverage.json`.
Human-study priority population: `research/human/description-fallback-v1/p80-occupation-priority-population.json`.
"""
    FINDING.write_text(finding, encoding="utf-8")

    ssot_block = f"""## Current amendment — 2026-09-09: P80-first Track-2 feedback loop

<!-- {MARKER} -->

Occupation Track 2 now optimizes and evaluates **P80 first: {len(p80)} occupations covering 80% of the frozen historical occurrence proxy**. This is a quality-priority stratum only; all **{occupation['active_v31_target_universe']:,}** active v31 `occupation-name` identities remain eligible retrieval destinations.

Current frozen diversified-language overlap is **{len(enriched_p80_ids)}/{len(p80)} P80 occupations**; this does not authorize generating the same synthetic policy for the remaining {len(missing_p80_ids)}. Broad synthetic scaling remains paused after the mixed full-universe opened replay. The next decision-bearing loop is fresh independent human/user description evidence sampled primarily from P80 under the existing frozen human-study contract. P90/P95/full-tail optimization is deferred until P80 evidence warrants expansion.

Evidence: `docs/findings/p80-track2-priority-2026-09-09.md` and `research/evaluation/v31/p80-track2-priority-coverage.json`.
"""
    insert_after_heading(SSOT, "## Authority order", ssot_block)

    plan_block = f"""**P80-first Track-2 priority amendment (2026-09-09) — {MARKER}.** Keep the full {occupation['active_v31_target_universe']:,}-occupation candidate universe, but make the frozen {len(p80)}-occupation P80 demand stratum the primary short-feedback-loop population for human recruitment, evaluation and quality work. The existing diversified-language corpus covers {len(enriched_p80_ids)}/{len(p80)} P80 occupations; that overlap is planning metadata, not permission to mass-generate the remaining {len(missing_p80_ids)} with the current synthetic Gemma policy. Broad synthetic scaling remains paused. The next decision-bearing gate is fresh independent human/user descriptions, P80-primary, with valid non-P80 targets preserved and a small long-tail safety view reported separately when available. Expand to P90/P95 only after material P80 evidence warrants it. Evidence: `docs/findings/p80-track2-priority-2026-09-09.md` and `research/evaluation/v31/p80-track2-priority-coverage.json`.
"""
    insert_after_heading(PLAN, "# Semantic Taxonomy Search — living research plan", plan_block)

    print(json.dumps({
        "p80": len(p80),
        "already_diversified": len(enriched_p80_ids),
        "missing": len(missing_p80_ids),
        "candidate_universe": occupation["active_v31_target_universe"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
