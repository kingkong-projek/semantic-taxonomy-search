#!/usr/bin/env python3
from pathlib import Path

p = Path('docs/research-plan.md')
text = p.read_text(encoding='utf-8')
text = text.replace('**Last updated:** 2026-09-08', '**Last updated:** 2026-09-09', 1)
marker = 'Tournament entrants, at minimum:'
if marker not in text:
    raise SystemExit('tournament marker missing')
if '**Architecture breadth closeout (2026-09-09):' in text:
    raise SystemExit('breadth closeout already folded')
block = """**Architecture breadth closeout (2026-09-09): A SURVIVES; B/C/E REJECTED; D NOT ACTIVATED.** The short simple-first breadth phase is complete. A fixed supervised sparse classifier (B) regressed against its same-feature centroid control and trailed A on the frozen 66-case hard-confusion gate. A direct task/activity-atom representation (C) reached only **46/66 Top1** and **50/66 correct confusion-pair side**, versus A **62/66 Top1** and **63/66 correct pair side**. The final fixed rank-64 latent student (E) fit the frontend size constraint (~0.84 MB gzip estimate) but also reached only **46/66 Top1** and strongly regressed on the 593 construction holdout. Do not rescue B/C/E with sweeps and do not compose them into a hybrid. The deferred two-stage D (`coarse retrieval -> local discriminator`) is **not activated** because A is already strong on the dedicated neighbouring-role gate; the remaining measured weakness is transfer to colloquial/indirect user language, not demonstrated within-family candidate discrimination. Therefore **A — teacher-expanded sparse retrieval — is the surviving simple family**, A2105 remains paused, and the next bounded question is **training-language distribution inside frozen A593**. Freeze ranker form and test current A versus A plus separately generated, source-bound, lexically more distant user language on a separately prefrozen transfer proxy; opened 17/88 remains replay-only. Scale language generation only if the bounded gain is material. If language diversity also fails materially, do not respond by building a B/C/E/D stack; reassess the residual against fresh human evidence and the existing server/API escape hatch. Evidence: `docs/findings/compile-time-architecture-breadth-result-2026-09-09.md`, `research/evaluation/v31/compile-time-semantic-architecture-breadth-result.json`, `research/evaluation/v31/compile-time-semantic-a593-hard-confusion-breadth-abc.json` and `research/evaluation/v31/compile-time-semantic-a593-lowrank-breadth.json`.

**Simplicity contract after breadth closeout:** the preferred final form remains **exact/canonical lexical route + one semantic description ranker/index**. A second semantic stage requires new independent evidence that clears the stronger complexity bar; it is not a default next step.

Historical tournament entrants, at minimum:"""
text = text.replace(marker, block, 1)
p.write_text(text, encoding='utf-8')
