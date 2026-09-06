#!/usr/bin/env python3
from pathlib import Path

p=Path('docs/research-plan.md')
text=p.read_text(encoding='utf-8')

def rep(old,new):
    global text
    n=text.count(old)
    if n!=1:
        raise RuntimeError(f'expected one SSOT anchor, got {n}: {old[:120]!r}')
    text=text.replace(old,new,1)

rep(
"""**Product-native residual gate:** before another semantic source/model layer is admitted, close or explicitly measure the cheapest ordinary-selector residuals first:

- [x] YV rich multi-context `setSelection()` roundtrip preserves chosen occupation context (`81a7cb5e`);
- [x] YV bare ambiguous exact-title blur no longer silently selects first context (`81a7cb5e`);
- [ ] replay the remaining **0.438%** excluded-title direct residual through the exact current Fuse.js lane;
- [ ] measure actual demand and Discovery@5 gain from currently unused canonical alternative-label vocabulary in YV/KV;
- [ ] verify/fix YV→KV job-title occupation-context hand-off with an actual integration test / production-consumer inspection.

Evidence: `docs/findings/p80-decision-benchmark-v31.md`, `research/benchmark/v31/p80-source-truth/manifest.json`, `docs/findings/current-selector-baseline-2026-09-06.md`, and `docs/findings/current-selector-failure-audit-v31.md`.""",
"""**Product-native residual discipline:** prefer cheap ordinary-selector fixes before adding semantic complexity **within the affected target space**. The verified YV context defects are fixed (`81a7cb5e`). The remaining YV Fuse/alternative-label/handoff checks stay useful reference-product hygiene, but they no longer globally block independently measured `skill` fallback research. Skill work may proceed because the pinned current KV product has now been measured on the same blind description benchmark.

Non-blocking YV follow-ups:

- [ ] replay the remaining **0.438%** excluded-title direct residual through the exact current Fuse.js lane;
- [ ] measure actual demand and Discovery@5 gain from currently unused canonical alternative-label vocabulary in YV;
- [ ] verify YV→KV job-title occupation-context hand-off in production consumers.

Evidence: `docs/findings/p80-decision-benchmark-v31.md`, `research/benchmark/v31/p80-source-truth/manifest.json`, `docs/findings/current-selector-baseline-2026-09-06.md`, `docs/findings/current-selector-failure-audit-v31.md`, and `docs/findings/skill-fallback-increment-v31.md`."""
)

rep(
"**Ordering constraint:** further semantic expansion is paused while the product-native residual gate in Gate 2 has cheaper unresolved checks. Existing C0/C1/C2/F1 measurements remain valid evidence; they do not outrank fixes or measurements of the current YV/KV selector paths.",
"**Ordering constraint:** within each target space, prefer cheaper product-native fixes before adding semantic complexity. Unresolved YV reference-product hygiene does not block the separately measured KV description fallback. For skills, the pinned current KV selector is now baseline P on the blind holdout: it returns no result for 35/35 cases, while deterministic KV-C0 rescues 11/35. Further skill complexity must therefore be justified against that incremental baseline and validated on fresh evidence."
)

rep(
"""Skill independent validation: the first source-attested natural-description skill benchmark exposed a real gap that canonical C0 does not solve. On a separately frozen **35-case blind holdout**, KV-C0 reaches **31.429% Discovery Hit@5 (34.734% occurrence-proxy weighted)**. The only surviving minimal development candidate, `KV-F1-close-one-slot`, does **not** improve unweighted Hit@5 and falls to **31.955% weighted**. The 617-case canonical regression remains 100%.

Decision: reject that F1 lane. The next decision-bearing comparison is against the pinned current KV selector itself; synthetic task/tool/method/first-person queries may be added as a separate stress suite, but may not be treated as traffic, ground-truth source evidence or retrieval enrichment.

Evidence: `docs/findings/skill-fresh-holdout-v31.md`, `research/benchmark/v31/training-skill-fresh-holdout/` and `research/evaluation/v31/skill-fresh-holdout.json`.""",
"""Skill independent validation: the first source-attested natural-description skill benchmark exposed a real gap that canonical C0 does not solve. On a separately frozen **35-case blind holdout**, KV-C0 reaches **31.429% Discovery Hit@5 (34.734% occurrence-proxy weighted)**. The only surviving minimal development candidate, `KV-F1-close-one-slot`, does **not** improve unweighted Hit@5 and falls to **31.955% weighted**. The 617-case canonical regression remains 100%.

The pinned current KV product was then replayed on **the same 35 frozen descriptions** using `kingkong-projek/yrkesvaljaren@0eba98e3`, Fuse.js 7.5.0 and the exact no-context `HybridSearchEngine.search(query, '', [], 5)` path. It returns **no result for 35/35 cases: 0.000% Discovery@5**. KV-C0 therefore provides **11 semantic rescues**, an incremental **+31.429 percentage points Discovery@5** and **+34.734 points occurrence-proxy weighted** over the actual product baseline. All 35 cases are fallback-eligible relative to current KV.

Decision: description fallback has now demonstrated material incremental product capability. Keep deterministic KV-C0 as the minimum semantic baseline and keep F1 rejected. The remaining 24 misses are an opened development residual, not future independent validation. Next build the separate provenance-tagged synthetic-query stress suite for first-person/task/tool/method language, use it only to nominate the smallest next capability, and validate any promoted capability on a new unopened source-attested holdout.

Evidence: `docs/findings/skill-fresh-holdout-v31.md`, `docs/findings/skill-fallback-increment-v31.md`, `research/benchmark/v31/training-skill-fresh-holdout/`, `research/evaluation/v31/skill-fresh-holdout.json`, and the reproducible pinned-product workflow `.github/workflows/pinned-kv-description-baseline.yml`."""
)

rep(
"- [ ] measure the pinned **current KV selector** on the same blind 35-case description holdout so fallback value is reported as increment over the actual product baseline",
"- [x] measure the pinned **current KV selector** on the same blind 35-case description holdout: current KV returns **0/35** results / **0.000% Discovery@5**; KV-C0 rescues **11/35 = 31.429%**, giving **+31.429pp** incremental Discovery@5 (**+34.734pp occurrence-proxy weighted**)"
)

p.write_text(text,encoding='utf-8')
print('skill fallback increment SSOT sync complete')
