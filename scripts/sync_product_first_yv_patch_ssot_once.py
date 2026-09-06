#!/usr/bin/env python3
from pathlib import Path

path = Path('docs/research-plan.md')
text = path.read_text(encoding='utf-8')


def rep(old: str, new: str) -> None:
    global text
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f'expected exactly one anchor, got {n}: {old[:100]!r}')
    text = text.replace(old, new, 1)


rep(
    "Evidence: `docs/findings/current-selector-baseline-2026-09-06.md`.\n\n### 2.2 Pareto / simple-first delivery principle",
    """Evidence: `docs/findings/current-selector-baseline-2026-09-06.md`.

**Product-first gate before semantic expansion:** real YV/KV users report that they sometimes cannot find the occupation or competence they need. Before attributing a residual to missing semantic intelligence, audit the ordinary selectors against their published data, interaction paths and integration contracts. Fix cheap native reachability/identity/vocabulary problems first; description-semantic fallback is evaluated on the residual that remains.

The first YV audit materially narrowed the problem. Ordinary multi-context dropdown lookup is healthy (**541/541** exact multi-context titles expose all intended context rows). Two narrow context-preservation defects were verified and patched in `kingkong-projek/yrkesvaljaren@81a7cb5e7d52e2c5a0d343011774a2f4dbcf6991` (PR #34): rich `setSelection()` now preserves the selected `related` occupation context, and a bare ambiguous exact title no longer silently auto-selects the first context on blur. Normal YV search/ranking was not changed.

Evidence: `docs/findings/current-selector-failure-audit-v31.md` and `research/coverage/v31/current-selector-failure-audit.json`.

### 2.2 Pareto / simple-first delivery principle""",
)

rep(
    "### 5.6 Published Kompetensväljaren v31",
    """### 5.5.2 Product-first YV/KV selector audit

The current products are now audited as products, not only as semantic data sources.

YV:

- ordinary exact multi-context dropdown lookup is healthy: **541/541** multi-context job-title IDs expose all intended contextual rows in direct top 10;
- the earlier **11.153% excluded-title volume** must not be read as an 11% failure rate: current deterministic direct YV already routes **96.073%** of that volume to at least one generator-mapped occupation in top 10;
- the remaining direct-lane excluded-title residual is **13,734,681 queries = 0.438% of all retained query volume** before guarded Fuse fallback;
- two narrow identity/interaction defects were fixed in YV commit `81a7cb5e`: rich roundtrip now preserves `related` occupation context and bare ambiguous blur no longer selects row 1 arbitrarily;
- 197 admitted concepts expose 362 canonical alternative-label surfaces; **51** currently lack a deterministic direct YV result.

KV:

- all 6,752 active skills are present, but candidate generation is driven primarily by preferred labels/tokens;
- **819** skills expose 1,308 canonical alternative-label surfaces, with **260** lacking a canonical contains match in the current direct lane;
- **1,654** skills have a definition distinct from the preferred label, but definitions do not participate in ordinary candidate generation;
- occupation/SSYK context can rank/filter lexical candidates but cannot create a candidate when the user's wording is absent from the skill label.

The repo's stepped YV→KV demo also demonstrates an integration footgun: a job-title selection carries the occupation parent as `related.id`, while the demo passes `selection.id` to KV. This is proven in the demo, not yet in production consumers.

**Current decision:** do not add semantic model/source complexity merely because ordinary selector behaviour has not yet been measured honestly. Next product-native checks are exact current-Fuse replay on the 0.438% YV direct residual, demand/gain from unused canonical alternative labels, and YV→KV job-title hand-off. Description fallback remains the separate capability for users who still cannot discover their concept after those ordinary paths are sound.

Evidence: `docs/findings/current-selector-failure-audit-v31.md` and `research/coverage/v31/current-selector-failure-audit.json`.

### 5.6 Published Kompetensväljaren v31""",
)

rep(
    "The current YV/KV implementation is now baseline 0 for decision-bearing product evaluation. Description-style cases should record both current-selector Discovery@K and semantic-fallback Discovery@K; the decision metric is the incremental gain where ordinary lookup is insufficient.\n\nEvidence: `docs/findings/p80-decision-benchmark-v31.md`, `research/benchmark/v31/p80-source-truth/manifest.json`, and `docs/findings/current-selector-baseline-2026-09-06.md`.",
    """The current YV/KV implementation is now baseline 0 for decision-bearing product evaluation. Description-style cases should record both current-selector Discovery@K and semantic-fallback Discovery@K; the decision metric is the incremental gain where ordinary lookup is insufficient.

**Product-native residual gate:** before another semantic source/model layer is admitted, close or explicitly measure the cheapest ordinary-selector residuals first:

- [x] YV rich multi-context `setSelection()` roundtrip preserves chosen occupation context (`81a7cb5e`);
- [x] YV bare ambiguous exact-title blur no longer silently selects first context (`81a7cb5e`);
- [ ] replay the remaining **0.438%** excluded-title direct residual through the exact current Fuse.js lane;
- [ ] measure actual demand and Discovery@5 gain from currently unused canonical alternative-label vocabulary in YV/KV;
- [ ] verify/fix YV→KV job-title occupation-context hand-off with an actual integration test / production-consumer inspection.

Evidence: `docs/findings/p80-decision-benchmark-v31.md`, `research/benchmark/v31/p80-source-truth/manifest.json`, `docs/findings/current-selector-baseline-2026-09-06.md`, and `docs/findings/current-selector-failure-audit-v31.md`.""",
)

rep(
    "## 11. Research Gate 3 — controlled ablation\n\nEvaluate occupation and skill retrieval separately; do not force source symmetry. Keep YV/KV reference-profile slices separate where their admission/routing semantics materially differ.",
    """## 11. Research Gate 3 — controlled ablation

**Ordering constraint:** further semantic expansion is paused while the product-native residual gate in Gate 2 has cheaper unresolved checks. Existing C0/C1/C2/F1 measurements remain valid evidence; they do not outrank fixes or measurements of the current YV/KV selector paths.

Evaluate occupation and skill retrieval separately; do not force source symmetry. Keep YV/KV reference-profile slices separate where their admission/routing semantics materially differ.""",
)

path.write_text(text, encoding='utf-8')
print('product-first YV patch SSOT sync complete')
