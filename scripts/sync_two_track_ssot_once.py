#!/usr/bin/env python3
from pathlib import Path

p = Path('docs/research-plan.md')
s = p.read_text(encoding='utf-8')
anchor = "### 2.1.1 Persona-based experiential red-team\n"
if anchor not in s:
    raise RuntimeError('persona section anchor missing')
insert = """### 2.1.1 Two-track research order — Track 1 first

The work is now deliberately split into two separate tracks. They must not be blended into one residual metric.

**Track 1 — current YV/KV findability (NOW).** Explain and fix why people sometimes fail to find an occupation or competence in the existing selectors. This includes canonical vocabulary reachability, ranking/recognisability, broad-vs-specific variants, job-title/occupation context, typo/fuzzy behaviour, interaction, and YV→KV context/coherence. Run this track to a compact decision boundary before doing more free-text work.

**Track 2 — free-text description fallback (PAUSED).** Determine what `Beskriv yrket/kompetensen` should do for users who still cannot find what they need after Track 1. Existing C0/C1/C2/F1 and frozen description/synthetic-query evidence is retained, but no new model/source/tuning decision is allowed to be driven by Track 2 until Track 1 exits.

Track 1 exits only when all of the following are true:

- the source-attested current-selector `should-find` replay is frozen and its highest-signal misses are classified;
- verified product-native defects discovered by that audit are patched or explicitly accepted with measured materiality;
- canonical alternative-label reachability is measured for both YV and KV and the smallest safe improvement is evaluated;
- the frozen non-description persona journeys are replayed against the exact current product behaviour, with candidate failures independently verified rather than accepted from the persona itself;
- YV→KV context/coherence is verified in the accessible integration paths;
- a compact failure-mode map records mechanism, evidence class, examples, estimated materiality, cheapest fix, regression risk and status;
- remaining material failures are explicitly classified as requiring Track 2 rather than another cheaper current-selector fix.

Description journeys already frozen under `research/personas/v31/journeys.jsonl` remain immutable but **must not be replayed or used to choose retrieval changes during Track 1**.

Evidence: `docs/findings/current-selector-should-find-v31.md`, `research/evaluation/v31/current-selector-should-find-summary.json`, `docs/findings/persona-findability-protocol-v31.md`.

### 2.1.2 Persona-based experiential red-team
"""
s = s.replace(anchor, insert, 1)
# Strengthen old research-order sentence so it cannot conflict with the two-track gate.
old = "Research order is now: finish source-attested should-find replay → freeze a compact persona journey packet → replay exact product UX → independently verify candidate failures → cluster by mechanism/demand/risk → fix the smallest material cause → only then measure semantic fallback on the remaining experience."
new = "Track-1 research order is: freeze source-attested should-find replay → replay only the non-description persona journeys against exact current product UX → independently verify candidate failures → cluster by mechanism/demand/risk → fix and measure the smallest material causes → produce the failure-mode map and satisfy the Track-1 exit criteria. Only after that may Track 2 resume."
if old not in s:
    raise RuntimeError('research-order anchor missing')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
print('two-track SSOT sync complete')
