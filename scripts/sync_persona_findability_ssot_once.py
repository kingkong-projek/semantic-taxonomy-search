#!/usr/bin/env python3
from pathlib import Path

p = Path('docs/research-plan.md')
s = p.read_text(encoding='utf-8')
marker = '### 2.2 Pareto / simple-first delivery principle\n'
if '### 2.1.1 Persona-based experiential red-team' in s:
    print('persona section already present')
    raise SystemExit(0)
if marker not in s:
    raise RuntimeError('SSOT insertion marker not found')
section = '''### 2.1.1 Persona-based experiential red-team\n\nConventional retrieval metrics can miss the reported user experience even when a technically valid identity appears somewhere in the result set. Add an exploratory **persona journey** layer that asks whether different realistic jobseekers can *recognise and recover* the occupation/competence they mean. Personas vary occupational self-knowledge, labour-market vocabulary, title-vs-task search strategy, current vs historical terms, Swedish vs English workplace language, typo tolerance, ambiguity/context needs and willingness to inspect/reformulate results. Do **not** infer behaviour from protected/demographic traits.\n\nPersonas are synthetic discovery instruments, **not empirical users and not benchmark ground truth**. Freeze each journey's goal and first query before inspecting selector output. A persona-generated failure becomes a finding only after independent verification against authoritative taxonomy/source truth, observed query evidence, reproducible product code/data or actual human feedback. Ambiguous journeys may correctly end in clarification or abstention.\n\nIn addition to Recall@K, inspect experience-level properties: **recognisable-at-3/5**, recoverable within two natural reformulations, variant overload, misleading plausible top hits, context preservation through selection and YV→KV, visible KV coherence, give-up proxy and safe abstention. Keep these mechanism-specific initially rather than collapsing them into one score.\n\nThe initial v31 matrix has 12 composable personas and starts from reported/high-volume anchors such as broad `projektledare`, `projektkoordinator` with parenthetical context, common excluded titles, multi-context titles under realistic typo/context qualification, YV→KV coherence, and task-first description journeys. Full protocol: `docs/findings/persona-findability-protocol-v31.md`; structured matrix: `research/personas/v31/personas.json`.\n\nResearch order is now: finish source-attested should-find replay → freeze a compact persona journey packet → replay exact product UX → independently verify candidate failures → cluster by mechanism/demand/risk → fix the smallest material cause → only then measure semantic fallback on the remaining experience.\n\n'''
s = s.replace(marker, section + marker, 1)
p.write_text(s, encoding='utf-8')
print('synced persona-based findability protocol into SSOT')
