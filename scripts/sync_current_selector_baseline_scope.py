#!/usr/bin/env python3
from pathlib import Path

p=Path('docs/research-plan.md')
t=p.read_text(encoding='utf-8')

def r(old,new,label):
    global t
    n=t.count(old)
    if n!=1:
        raise RuntimeError(f'{label}: expected one match, got {n}')
    t=t.replace(old,new,1)

r(
"The core result remains an exact canonical occupation/skill identity with provenance; the consumer then enforces its admission profile. `Inget av dessa` / abstention is a first-class successful outcome. A nearest neighbour is not proof that a valid match exists.\n\n### 2.1 Pareto / simple-first delivery principle",
"""The core result remains an exact canonical occupation/skill identity with provenance; the consumer then enforces its admission profile. `Inget av dessa` / abstention is a first-class successful outcome. A nearest neighbour is not proof that a valid match exists.

### 2.1 Fallback-first product objective vs replacement potential

The **primary v0 product question is incremental fallback value**, not whether a research matcher can replace a working selector.

The pinned current implementation baseline is `kingkong-projek/yrkesvaljaren@0eba98e3a91079a43c1eaf6da09dfabe11e5bc8b`:

- current YV already performs exact, prefix/multi-token, substring and guarded Fuse fallback over preferred labels, with behavioural weight as ranking evidence;
- current KV already performs global exact/prefix/word-boundary/contains/fuzzy skill lookup, while occupation/SSYK/context lists and precomputed `weightedSkills` influence ranking among text/fuzzy candidates and provide the empty-query initial list.

Therefore decision-bearing semantic evaluation has two separate views:

1. **Fallback value — primary.** Evaluate description/task/tool/method/colloquial queries for which the current selector does not already provide an adequate small discovery list. Report semantic **increment over the pinned current selector** at K, not only absolute semantic accuracy.
2. **Full-replacement potential — secondary bonus.** Separately test whether one simple engine preserves or improves the current selectors' ordinary exact/prefix/substring/fuzzy/context behaviour while also solving description fallback. Do not make replacement a v0 requirement.

Canonical label, alternative-label, typo and ordinary substring cases remain essential regressions, but success on them alone is not evidence that semantic fallback adds product value. A future single implementation may still contain a privileged lexical lane internally; `one engine` does not imply semantic similarity must handle every query.

Evidence: `docs/findings/current-selector-baseline-2026-09-06.md`.

### 2.2 Pareto / simple-first delivery principle""",
'fallback objective')

r(
"The frozen source-truth core currently contains **950 cases**: 333 YV and 617 KV over all 475 P80 targets. It includes 475 preferred-label cases, 330 real canonical-definition cases and 145 alternative-label cases. This is deliberately a source-attested benchmark; it must be complemented by a small manually judged real-query slice before making claims about natural paraphrase performance.\n\nEvidence: `docs/findings/p80-decision-benchmark-v31.md` and `research/benchmark/v31/p80-source-truth/manifest.json`.",
"""The frozen source-truth core currently contains **950 cases**: 333 YV and 617 KV over all 475 P80 targets. It includes 475 preferred-label cases, 330 real canonical-definition cases and 145 alternative-label cases. This is deliberately a source-attested **regression/representation benchmark**. It does not measure incremental fallback value unless the pinned current selector is also run on the same fallback-eligible query.

The current YV/KV implementation is now baseline 0 for decision-bearing product evaluation. Description-style cases should record both current-selector Discovery@K and semantic-fallback Discovery@K; the decision metric is the incremental gain where ordinary lookup is insufficient.

Evidence: `docs/findings/p80-decision-benchmark-v31.md`, `research/benchmark/v31/p80-source-truth/manifest.json`, and `docs/findings/current-selector-baseline-2026-09-06.md`.""",
'benchmark interpretation')

r(
"```text\nA  canonical labels only\nB  A + real canonical definitions",
"""```text
P  pinned current YV/KV production selector baseline
A  canonical labels only
B  A + real canonical definitions""",
'gate3 baseline')

r(
"Primary product objective is **discovery**, not exact top-1 classification. A small visible candidate list succeeds when it contains what the user meant; broad/ambiguous queries may correctly expose several plausible canonical candidates. Use **Discovery Success@5** as the primary positive-intent metric and correct abstention as the primary NO_MATCH metric. Top-1 remains secondary ranking diagnostics.",
"""Primary product objective is **discovery**, not exact top-1 classification. A small visible candidate list succeeds when it contains what the user meant; broad/ambiguous queries may correctly expose several plausible canonical candidates. Use **Discovery Success@5** as the primary positive-intent metric and correct abstention as the primary NO_MATCH metric. Top-1 remains secondary ranking diagnostics.

For the primary fallback view, report **incremental Discovery Success@5 over the pinned current selector** and the share of tested queries that are genuinely fallback-eligible. Absolute semantic scores without the current-selector baseline are development diagnostics only. For the secondary replacement view, run the candidate engine against current ordinary-selector regression behaviour as well.""",
'metrics baseline')

marker="### Now — Gate 2\n\n- [x] benchmark schema and semantic validator contract"
replacement="""### Now — Gate 2

- [x] pin and code-audit the **current YV/KV selector implementation as baseline 0** (`kingkong-projek/yrkesvaljaren@0eba98e3a91079a43c1eaf6da09dfabe11e5bc8b`); separate primary fallback-value evaluation from secondary full-replacement potential
- [x] benchmark schema and semantic validator contract"""
r(marker,replacement,'work sequence baseline')

p.write_text(t,encoding='utf-8')
