#!/usr/bin/env python3
from pathlib import Path
p=Path('docs/research-plan.md'); t=p.read_text(encoding='utf-8')

def r(old,new,label):
    global t
    n=t.count(old)
    if n!=1: raise RuntimeError(f'{label}: expected one match, got {n}')
    t=t.replace(old,new,1)

r(
"- [ ] validate frozen C2 on a **fresh natural-language next-volume holdout** adjudicated before C2 output is inspected; do not special-case the two development residuals (`lager`, `administration`) before this test\n- [ ] D typed graph/ESCO only if the fresh adjudicated natural-query residual justifies it; do not add D merely to complete an ablation ladder",
"- [x] validate frozen C2 on a **fresh blinded natural-language next-volume holdout**: unbound query ranks 51–80 were adjudicated and frozen before C2 output existed; **30 cases / 138.1M searches**, with **100% volume-weighted Discovery Success@5**, **100% positive-intent Discovery@5 (5/5)**, **100% NO_MATCH abstention (25/25)** and no 333-case source-truth regression\n- [ ] **next core gap: natural-language skill discovery.** Build a small source-attested text→skill validation slice before changing retrieval; prefer curated/manual mappings where published text is sufficient, and keep model/synthetic text out of ground truth\n- [ ] D typed graph/ESCO remains deferred: the fresh YV holdout exposes no occupation residual that justifies it; add D only if a later occupation or skill benchmark demonstrates material value",
'fresh C2 checklist')

anchor="Evidence: `docs/findings/c2-job-title-router-v31.md` and `research/evaluation/v31/c2-job-title-router.json`.\n"
addition="""

Independent C2 validation: a second natural-language holdout was selected from previously unseen unbound observed-query ranks **51–80** (**30 cases / 138.1M searches**). Its taxonomy-only judgments were frozen before C2 was run. Frozen C2 then achieved **100% Discovery Success@5**, **100% volume-weighted Discovery Success@5**, **100% positive-intent Discovery@5 (5/5)** and **100% NO_MATCH abstention (25/25)** while preserving the 333-case source-truth suite at 100%. None of the five positive cases required the job-title route; C1 itself surfaced a judged-positive occupation.

Interpretation: this is strong independent evidence for the simple occupation configuration but not a claim of universal 100% relevance—the holdout contains only five positive occupation queries and is dominated by geography/other intent. Crucially, it produces **no measured occupation residual that can justify more retrieval complexity**. D/ESCO, vectors and synthetic enrichment therefore remain deferred. The next evidence gap moves to the other generic target space: natural-language **skill** discovery.

Evidence: `docs/findings/c2-fresh-natural-holdout-v31.md`, `research/benchmark/v31/fresh-natural-holdout/` and `research/evaluation/v31/c2-fresh-natural-holdout.json`.
"""
if addition.strip() not in t:
    if t.count(anchor)!=1: raise RuntimeError(f'anchor count {t.count(anchor)}')
    t=t.replace(anchor,anchor+addition,1)
p.write_text(t,encoding='utf-8')
