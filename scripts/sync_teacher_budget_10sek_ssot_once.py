#!/usr/bin/env python3
from pathlib import Path

p = Path('docs/research-plan.md')
t = p.read_text(encoding='utf-8')

old = (
    "**Compile-time semantic tournament (ACTIVE next architecture phase; 2026-09-07).** The target universe is small and mostly static, so the next architecture question is not `which neural model can the browser tolerate?` but **how much semantic intelligence can be paid once at build time and compiled into a tiny deterministic runtime artifact**. **Teacher/build marginal-cost budget is 0 SEK. No local teacher inference is available.** The currently allowed teacher pool is therefore limited to **Muse Spark**, **Gemma 4 through the already-available zero-cost hosted access**, and **GPT-5.6 Sol in the existing ChatGPT conversation**. No new paid API spend and no local/open-weight teacher run is authorized. The browser must not inherit teacher parameter count or runtime dependency."
)
new = (
    "**Compile-time semantic tournament (ACTIVE next architecture phase; 2026-09-07).** The target universe is small and mostly static, so the next architecture question is not `which neural model can the browser tolerate?` but **how much semantic intelligence can be paid once at build time and compiled into a tiny deterministic runtime artifact**. **Teacher/build marginal-cost budget is capped at 10 SEK total. No local teacher inference is available.** The executable teacher pool is limited to **Gemma 4 through the already-available zero-cost hosted access as the default volume teacher**, **Muse Spark as an optional secondary/adversarial teacher within the 10 SEK total cap**, and **GPT-5.6 Sol in the existing ChatGPT conversation for bounded prompt design, difficult boundary cases and quality review**. Do not add any other paid API or local/open-weight teacher run without a new explicit project decision. The browser must not inherit teacher parameter count or runtime dependency."
)
if t.count(old) != 1:
    raise RuntimeError(f'expected exactly one teacher-budget paragraph, got {t.count(old)}')
t = t.replace(old, new, 1)

old2 = (
    "Teacher diversity is desirable, but the executable pool is deliberately narrow under the **0 SEK / no-local-inference constraint**: Muse Spark and Gemma 4 provide scalable hosted generation where the existing free access permits it; GPT-5.6 Sol in ChatGPT is the high-capability interactive teacher/judge for bounded batches, prompt design, difficult boundary cases and corpus quality review. Do not assume Sol is a reproducible batch API. If a teacher is unavailable within this pool at zero marginal cost, skip it rather than substitute a paid or local model. Teacher disagreement must be retained as evidence rather than silently collapsed into false ground truth. Source-attested taxonomy/AF evidence remains provenance-distinct from generated teacher language. Any external teacher input must be public or synthetic by construction; user logs, personal data and unpublished sensitive material are excluded from this build path."
)
new2 = (
    "Teacher diversity is desirable, but the executable pool is deliberately narrow under the **<=10 SEK total / no-local-inference constraint**: **Gemma 4 is first choice for scalable hosted generation because its available path is zero-cost and operationally simplest**; Muse Spark is reserved for targeted diversity, adversarial generation or Gemma-weak boundary cases while keeping aggregate marginal spend within 10 SEK; GPT-5.6 Sol in ChatGPT is the high-capability interactive teacher/judge for bounded batches, prompt design, difficult boundary cases and corpus quality review. Do not assume Sol is a reproducible batch API. Teacher disagreement must be retained as evidence rather than silently collapsed into false ground truth. Source-attested taxonomy/AF evidence remains provenance-distinct from generated teacher language. Any external teacher input must be public or synthetic by construction; user logs, personal data and unpublished sensitive material are excluded from this build path."
)
if t.count(old2) != 1:
    raise RuntimeError(f'expected exactly one teacher-pool paragraph, got {t.count(old2)}')
t = t.replace(old2, new2, 1)

p.write_text(t, encoding='utf-8')
