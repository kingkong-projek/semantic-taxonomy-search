#!/usr/bin/env python3
from pathlib import Path

p = Path('docs/research-plan.md')
text = p.read_text(encoding='utf-8')

old = """## 1. Product problem\n\nWe are building a **reusable semantic retrieval capability for occupations and skills/competences** in services where a user must identify or select taxonomy concepts without knowing the taxonomy's exact wording. The project is concretely motivated by reports from users of Yrkesväljaren (YV) and Kompetensväljaren (KV) who cannot find the occupation or competence they are looking for with the current selector wording.\n"""
new = """## 1. Product problem\n\nThe observed product problem is deliberately broader than a semantic-fallback residual: **users report that they sometimes cannot find the occupation or competence they are looking for**. We do not yet know which failure mechanisms dominate. The failure may occur in wording/lexical matching, ranking, title-vs-occupation modelling, product admission/exclusion, ambiguity/context handling, interaction behaviour, integration/hand-off, missing vocabulary, or genuinely semantic description search.\n\nWe are therefore investigating a **reusable findability/retrieval capability for occupations and skills/competences**, with semantic retrieval as one candidate capability rather than the assumed diagnosis. YV and KV are the first concrete products in which the findability problem is measured.\n"""
if text.count(old) != 1:
    raise RuntimeError('product problem anchor drift')
text = text.replace(old, new, 1)

old = """### 2.1 Fallback-first product objective vs replacement potential\n\nThe **primary v0 product question is incremental fallback value**, not whether a research matcher can replace a working selector.\n"""
new = """### 2.1 Findability-first product objective\n\nThe **primary v0 product question is end-to-end findability**: for a user trying to locate the right occupation or competence, does the product surface the intended valid identity in a small usable result set? Semantic fallback is one possible intervention and its incremental value remains useful to measure, but it must not redefine the original problem as only the subset of queries left after ordinary lookup fails.\n\nEvaluation must therefore distinguish failure mechanism before choosing a fix: ordinary lexical reachability, ranking, title/occupation routing, ambiguity/context, product admission, integration/hand-off, and description-style semantic retrieval. The smallest intervention that fixes a material measured findability failure wins.\n"""
if text.count(old) != 1:
    raise RuntimeError('objective anchor drift')
text = text.replace(old, new, 1)

old = """**Product-first gate before semantic expansion:** real YV/KV users report that they sometimes cannot find the occupation or competence they need. Before attributing a residual to missing semantic intelligence, audit the ordinary selectors against their published data, interaction paths and integration contracts. Fix cheap native reachability/identity/vocabulary problems first; description-semantic fallback is evaluated on the residual that remains.\n"""
new = """**Product-first gate before semantic expansion:** real YV/KV users report that they sometimes cannot find the occupation or competence they need. Treat that report as the phenomenon to explain, not as evidence for a predetermined residual or semantic diagnosis. Audit the complete findability path against published data, interaction paths and integration contracts; classify observed failures by mechanism; then fix the cheapest material cause. Description-semantic fallback is evaluated as one capability within that broader findability problem, not as the definition of the problem.\n"""
if text.count(old) != 1:
    raise RuntimeError('product gate anchor drift')
text = text.replace(old, new, 1)

p.write_text(text, encoding='utf-8')
