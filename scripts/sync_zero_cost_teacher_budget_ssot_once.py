#!/usr/bin/env python3
from pathlib import Path

p = Path('docs/research-plan.md')
t = p.read_text(encoding='utf-8')

old = (
    "**Compile-time semantic tournament (ACTIVE next architecture phase; 2026-09-07).** The target universe is small and mostly static, so the next architecture question is not `which neural model can the browser tolerate?` but **how much semantic intelligence can be paid once at build time and compiled into a tiny deterministic runtime artifact**. Large/expensive teachers may therefore be used freely offline to generate, score, contrast, distil and prune evidence. The browser must not inherit their parameter count or runtime dependency."
)
new = (
    "**Compile-time semantic tournament (ACTIVE next architecture phase; 2026-09-07).** The target universe is small and mostly static, so the next architecture question is not `which neural model can the browser tolerate?` but **how much semantic intelligence can be paid once at build time and compiled into a tiny deterministic runtime artifact**. **Teacher/build marginal-cost budget is 0 SEK.** Teacher work may therefore use local/open-weight inference, already-paid interactive tools, or externally hosted models only when a genuinely free quota covers the run; no paid API spend is authorized. The browser must not inherit teacher parameter count or runtime dependency."
)
if t.count(old) != 1:
    raise RuntimeError(f'expected exactly one compile-time tournament intro, got {t.count(old)}')
t = t.replace(old, new, 1)

old2 = (
    "Teacher diversity is allowed and desirable at compile time: dense retrievers, Swedish sentence models, cross-encoders and capable LLMs may all contribute labels, generated language, pairwise preferences and hard negatives. Their disagreement must be retained as evidence rather than silently collapsed into false ground truth. Source-attested taxonomy/AF evidence remains provenance-distinct from generated teacher language."
)
new2 = (
    "Teacher diversity is allowed and desirable at compile time **within the 0 SEK marginal-cost constraint**: local/open-weight dense retrievers, Swedish sentence models, cross-encoders and capable LLMs may contribute labels, generated language, pairwise preferences and hard negatives; hosted models may participate only through genuinely free quota or an already-paid interactive product, never via new paid API spend. Their disagreement must be retained as evidence rather than silently collapsed into false ground truth. Source-attested taxonomy/AF evidence remains provenance-distinct from generated teacher language. Any external teacher input must be public or synthetic by construction; user logs, personal data and unpublished sensitive material are excluded from this build path."
)
if t.count(old2) != 1:
    raise RuntimeError(f'expected exactly one teacher-diversity paragraph, got {t.count(old2)}')
t = t.replace(old2, new2, 1)

p.write_text(t, encoding='utf-8')
