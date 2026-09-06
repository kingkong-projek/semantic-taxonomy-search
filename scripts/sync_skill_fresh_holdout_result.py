#!/usr/bin/env python3
"""Freeze the independent skill holdout result and sync the research SSOT once."""
from __future__ import annotations

import json
from pathlib import Path

RESULT = Path("artifacts/skill-fresh-holdout-v31.json")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected one match, got {n}")
    return text.replace(old, new, 1)


def main() -> int:
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    c0 = result["configurations"]["KV-C0"]
    f1 = result["configurations"]["KV-F1-close-one-slot"]
    reg = result["source_truth_regression"]
    assert c0["cases"] == 35
    assert c0["discovery_hit_at_5_pct"] == 31.429
    assert c0["weighted_discovery_hit_at_5_pct"] == 34.734
    assert f1["discovery_hit_at_5_pct"] == 31.429
    assert f1["weighted_discovery_hit_at_5_pct"] == 31.955
    assert result["delta"]["weighted_discovery_hit_at_5_percentage_points"] == -2.779
    assert reg["top1_pct"] == 100.0 and reg["discovery_hit_at_5_pct"] == 100.0

    dst = Path("research/evaluation/v31/skill-fresh-holdout.json")
    dst.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    finding = """# Blind natural-description skill holdout — taxonomy v31

**Status:** independent validation; frozen benchmark predates evaluator and candidate exposure.  
**Target space:** P80 active `skill` identities.  
**Benchmark:** 35 source-attested labour-market-training descriptions, one previously unused descriptive/non-leaky module per unique P80 skill.

## Result

| configuration | Discovery Hit@5 | weighted Discovery Hit@5 | Hit@10 | canonical regression |
|---|---:|---:|---:|---:|
| KV-C0 | 31.429% | 34.734% | 40.000% | 617/617 = 100% |
| KV-F1 close-match one-slot | 31.429% | 31.955% | 31.429% | 617/617 = 100% |

The preselected one-slot `close_match` ESCO lane therefore gives **0.000 percentage-point unweighted gain and -2.779 points weighted** on the blind holdout. Its small development gain did not generalize.

## Decision

Reject `KV-F1-close-one-slot` as the next skill configuration. Keep KV-C0 as the smallest benchmark baseline. Do not add this ESCO lane merely because it helped the opened development slice.

The holdout confirms the actual remaining problem: natural task/tool/method descriptions are materially harder than canonical label/definition regression. The next experiments must diagnose that gap without contaminating retrieval documents with benchmark text.

Synthetic **queries** may now be used as a separate provenance-tagged stress suite for realistic first-person/task/tool/method wording. They are evaluation probes, not traffic evidence, training data, canonical synonyms or retrieval enrichment. Synthetic retrieval/enrichment text remains deferred until a measured residual justifies it.

Evidence: `research/benchmark/v31/training-skill-fresh-holdout/` and `research/evaluation/v31/skill-fresh-holdout.json`.
"""
    Path("docs/findings/skill-fresh-holdout-v31.md").write_text(finding, encoding="utf-8")

    p = Path("docs/research-plan.md")
    t = p.read_text(encoding="utf-8")
    t = replace_once(
        t,
        "We are building a **reusable semantic retrieval capability for occupations and skills/competences** in services where a user must identify or select taxonomy concepts without knowing the taxonomy's exact wording.\n\nYrkesväljaren (YV) and Kompetensväljaren (KV) are current **reference profiles**, not the scope boundary of the retrieval core.",
        "We are building a **reusable semantic retrieval capability for occupations and skills/competences** in services where a user must identify or select taxonomy concepts without knowing the taxonomy's exact wording. The project is concretely motivated by reports from users of Yrkesväljaren (YV) and Kompetensväljaren (KV) who cannot find the occupation or competence they are looking for with the current selector wording.\n\nYV and KV are current **reference profiles and the first product problem to solve**, not the scope boundary of the retrieval core.",
        "product motivation",
    )
    t = replace_once(
        t,
        "```text\nYV: Hittar du inte det du söker? [Beskriv yrket]\nKV: Hittar du inte kompetensen? [Beskriv kompetensen / vad du kan göra]\n```\n\nThe core result remains",
        "```text\nYV: Hittar du inte det du söker? [Beskriv yrket]\nKV: Hittar du inte kompetensen? [Beskriv kompetensen / vad du kan göra]\n```\n\nDescription mode explicitly includes ordinary first-person/task language such as `jag drog kabel, kopplade uttag och läste elscheman`, not only near-synonyms of taxonomy labels. Tasks, tools, methods, responsibilities and colloquial wording are first-class fallback input.\n\nThe core result remains",
        "description intent",
    )
    t = replace_once(
        t,
        """## 8. Synthetic data policy

Do **not** generate N phrases per concept as the baseline.

Synthetic phrases are allowed only after ablation shows a concrete residual gap that real/curated/observed sources do not solve. If used they must be generated, provenance-tagged, validated, deduplicated, adversarially tested and versioned. They never become canonical synonyms merely because retrieval metrics improve.""",
        """## 8. Synthetic data policy

Synthetic **queries for evaluation** and synthetic **retrieval/enrichment text** are different things and must not be conflated.

Synthetic query generation is allowed now as a separate benchmark/stress-testing tool, especially for realistic description-mode input such as first-person work history, tasks, tools, methods and colloquial wording that is not available with selected-ID ground truth in public query logs. Such cases must be tagged `synthetic_query`, kept separate from real/source-attested traffic metrics, and never assigned traffic weights. Their expected identity must be anchored in source-attested taxonomy evidence or separately adjudicated. Preferred/alternative target-label leakage should be excluded unless leakage is the explicit stratum under test.

Synthetic queries are **not training data by default** and must not be copied into retrieval documents merely because they expose failures.

Synthetic retrieval/enrichment phrases remain deferred until ablation shows a concrete residual gap that real/curated/observed sources do not solve. If used they must be provenance-tagged, validated, deduplicated, adversarially tested and versioned. They never become canonical synonyms merely because retrieval metrics improve.""",
        "synthetic query policy",
    )
    t = replace_once(
        t,
        "- [ ] **next core gap: natural-language skill discovery.** Build a small source-attested text→skill validation slice before changing retrieval; prefer curated/manual mappings where published text is sufficient, and keep model/synthetic text out of ground truth\n- [ ] D typed graph/ESCO remains deferred:",
        "- [x] **natural-language skill discovery source-attested validation:** 76 development cases plus a separately frozen **35-case blind holdout** from AF manual learning-outcome→skill mappings; on the blind holdout KV-C0 reaches **31.429% Discovery@5 / 34.734% weighted**, while preselected `KV-F1-close-one-slot` fails to generalize (**31.429% / 31.955% weighted**) and is rejected; canonical 617-case regression remains 100%\n- [ ] measure the pinned **current KV selector** on the same blind 35-case description holdout so fallback value is reported as increment over the actual product baseline\n- [ ] add a separate **synthetic-query description stress suite** for YV and KV (`synthetic_query` provenance; task/tool/method/first-person phrasing; no retrieval ingestion and no traffic weighting)\n- [ ] D typed graph/ESCO remains deferred:",
        "work sequence skill holdout",
    )
    marker = "Evidence: `docs/findings/c2-fresh-natural-holdout-v31.md`, `research/benchmark/v31/fresh-natural-holdout/` and `research/evaluation/v31/c2-fresh-natural-holdout.json`.\n\n"
    addition = marker + """Skill independent validation: the first source-attested natural-description skill benchmark exposed a real gap that canonical C0 does not solve. On a separately frozen **35-case blind holdout**, KV-C0 reaches **31.429% Discovery Hit@5 (34.734% occurrence-proxy weighted)**. The only surviving minimal development candidate, `KV-F1-close-one-slot`, does **not** improve unweighted Hit@5 and falls to **31.955% weighted**. The 617-case canonical regression remains 100%.

Decision: reject that F1 lane. The next decision-bearing comparison is against the pinned current KV selector itself; synthetic task/tool/method/first-person queries may be added as a separate stress suite, but may not be treated as traffic, ground-truth source evidence or retrieval enrichment.

Evidence: `docs/findings/skill-fresh-holdout-v31.md`, `research/benchmark/v31/training-skill-fresh-holdout/` and `research/evaluation/v31/skill-fresh-holdout.json`.

"""
    t = replace_once(t, marker, addition, "gate3 skill result")
    p.write_text(t, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
