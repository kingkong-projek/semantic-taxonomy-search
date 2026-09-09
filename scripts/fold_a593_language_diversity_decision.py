#!/usr/bin/env python3
from pathlib import Path

p = Path("docs/research-plan.md")
text = p.read_text(encoding="utf-8")
marker = "**Authority:** this file is the single source of truth for product scope, current conclusions, research gates and experiment order. Findings and generated inventories provide evidence; when evidence changes a conclusion, this file must change too.\n"
if marker not in text:
    raise SystemExit("research-plan authority marker missing")
if "**A593 training-language distribution checkpoint (2026-09-09):" in text:
    raise SystemExit("checkpoint already folded")
block = """

**A593 training-language distribution checkpoint (2026-09-09): SYNTHETIC GATE PASSED, FULL-UNIVERSE OPENED TRANSFER MIXED; DO NOT SCALE YET.** Architecture A remains the surviving simple Track-2 family, but the current synthetic Gemma diversification policy is not promoted for broad generation. With the ranker frozen, 466 accepted source-bound diversified phrases across 133 A593 concepts improved the separately generated 446-case heldout proxy from **64.13% -> 72.42% Top1 (+8.30 pp)** and **85.20% -> 91.03% Hit@5 (+5.83 pp)**; synthetic `shift_story` Top1 improved **+15.57 pp**, so the prefrozen materiality gate passed. The subsequent correctly replayed full-2,105 opened diagnostic hard-matches the original A593 control (**strict17 5 Top1 / 10 Hit@5 / MRR 0.424510; targetable40 15 Top1 / 26 Hit@5**) and is mixed: targetable40 **15 -> 16 Top1 but 26 -> 24 Hit@5**; strict17 stays **5/10** while MRR moves **0.424510 -> 0.418237**. The two targetable Hit@5 losses are colloquial and indirect; the visible Top1 gain is noisy. Therefore the large same-source synthetic narrative gain does not reproduce on the opened colloquial/indirect residual. **Keep A2105 paused, keep broad synthetic-language scaling paused, do not tune prompts from opened rows, and do not revive B/C/E or activate D. The next decision-bearing gate is fresh independent human/user description evidence under the existing frozen human-study contract.** The earlier `a593-language-diversity-opened-replay.json` is superseded because it accidentally used a 593-only candidate universe; use `a593-language-diversity-opened-replay-full-universe.json`. Evidence: `docs/findings/a593-language-diversity-2026-09-09.md`, `research/evaluation/v31/a593-language-diversity-result-v0.json`, and `research/evaluation/v31/a593-language-diversity-opened-replay-full-universe.json`.
"""
text = text.replace(marker, marker + block, 1)
p.write_text(text, encoding="utf-8")
