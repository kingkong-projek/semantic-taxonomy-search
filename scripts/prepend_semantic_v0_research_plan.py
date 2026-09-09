#!/usr/bin/env python3
from pathlib import Path

p = Path("docs/research-plan.md")
s = p.read_text(encoding="utf-8")
marker = "<!-- SEMANTIC-DISPLAY-V0-OUTCOME-2026-09-09 -->"
if marker in s:
    raise SystemExit(0)
head = "# Semantic Taxonomy Search — living research plan\n"
if not s.startswith(head):
    raise SystemExit("unexpected research-plan header")
amendment = r'''

**Semantic display relevance v0 outcome amendment (2026-09-09) — AUTHORITATIVE.**

<!-- SEMANTIC-DISPLAY-V0-OUTCOME-2026-09-09 -->

The bounded semantic candidate-relevance oracle v0 has now completed. Retrieval and rank order stayed frozen; the teacher saw neither rank, structured target nor SSYK, candidate order was shuffled, and only source-bound candidate evidence was exposed.

**Primary 2024 proxy: STRONG PASS.** The frozen oracle retained **167/167 Hit@5 targets** and **87/87 rank-2–5 targets**, while safe different-SSYK4 rank-2–5 negatives fell **2,469 -> 908 (-63.22%)** and mean visible list fell **5.00 -> 2.67**. The source contains 674 rows but 672 unique case keys because two ad/query rows are exact duplicates; do not report 674 as independent cases.

**Exact frozen opened replay: FORMAL FAIL.** Aggregate transfer was strong: targetable Hit@5 **28/28 -> 28/28**, genuine rank-2–5 hits **13/13 -> 13/13**, mean visible list **4.593 -> 2.519**, and full five-result lists **49 -> 5**. The electrician sanity passed. The preregistered nursing sanity failed: `Sjukhusvaktmästare` was dropped, but `Apotekare` and `Receptarie` remained `uncertain`, so only one of the three prefrozen known-bad candidates was removed where at least two were required. Therefore the opened gate remains failed regardless of strong aggregate metrics.

**Decision:** do **not** distill v0; do **not** retune on `yv01`, `yv02`, or any opened 17/88 row. Opened remains replay/falsification-only. The evidence is nevertheless sufficient to keep candidate-level semantic relevance as the active display direction: unlike the lexical/SSYK-derived filter family, v0 preserved every observed lower-rank target while removing a large fraction of visible tails. The remaining mechanism question is narrower: whether richer **candidate-specific discriminative source-bound evidence** can resolve plausible adjacent roles instead of returning `uncertain`.

**Next experiment order:** use independent hard-confusion evidence that predates and excludes opened rows; preregister any v1 evidence contract and untouched evaluation before oracle outcomes; keep retrieval/order unchanged; only after an independent v1 pass may the unchanged opened set be replayed again. No compact runtime student and no runtime LLM/provider API before that independent gate passes. Fresh human/domain-expert relevance judgments remain the decisive promotion evidence when available.

Evidence: `SSOT.md`, `docs/findings/semantic-top5-relevance-oracle-v0-2026-09-09.md`, `research/evaluation/v31/p80-display-semantic-oracle-v0.json`, `research/evaluation/v31/p80-display-semantic-oracle-opened-replay-v0.json`, and `research/evaluation/v31/compile-time-semantic-a593-confusion-task-atoms-v0.json`.
'''
p.write_text(head + amendment + s[len(head):], encoding="utf-8")
