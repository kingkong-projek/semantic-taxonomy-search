#!/usr/bin/env python3
from pathlib import Path

p = Path("docs/research-plan.md")
t = p.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global t
    n = t.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected one match, got {n}")
    t = t.replace(old, new, 1)


replace_once(
    "- a small high-volume unbound observed-query sample receives human judgments;",
    "- a small high-volume unbound observed-query sample receives explicitly provenance-tagged adjudication (human or model judgment);",
    "adjudication wording",
)

replace_once(
    "- [ ] **complete planned C retrieval vocabulary next:** add exact active job-title preferred-label → typed occupation-name parent routing. Optimize/evaluate primarily for **Discovery Success@5**, not rank 1; the holdout shows exact job-title routing is the dominant remaining candidate-generation gap. Evaluate on a new next-volume sentinel before D/ESCO.\n- [ ] D typed graph/ESCO only if the adjudicated real-query/safety residual justifies it; do not add D merely to complete an ablation ladder",
    "- [x] **complete planned C retrieval vocabulary:** C2 adds exact active job-title preferred-label → typed occupation-name parent routing, with job-title retained as retrieval vocabulary only. On the already-opened 36-case holdout C2 reaches **93.677% volume-weighted Discovery Success@5** with 100% NO_MATCH abstention. On a new unseen excluded-title ranks 21–50 sentinel it achieves **100% volume-weighted Any-parent Hit@5** and **93.220% volume-weighted typed-parent Recall@5**; the 333-case source-truth regression remains 100%.\n- [ ] validate frozen C2 on a **fresh natural-language next-volume holdout** adjudicated before C2 output is inspected; do not special-case the two development residuals (`lager`, `administration`) before this test\n- [ ] D typed graph/ESCO only if the fresh adjudicated natural-query residual justifies it; do not add D merely to complete an ablation ladder",
    "planned C checkbox",
)

anchor = "Evidence: `docs/findings/discovery-objective-v31.md` and `research/evaluation/v31/pareto-holdout-discovery.json`.\n"
addition = """

C2 result: the smallest next capability was enough again. C2 keeps C1 unchanged and adds only an exact active `job-title` preferred-label lookup whose already-typed `occupation-name` parents are unioned into the candidate list. On the previously opened holdout, volume-weighted Discovery Success@5 rises from C1 **84.788%** to C2 **93.677%**, with 100% NO_MATCH abstention; only `lager` and `administration` remain failures there. Because this holdout was opened before C2 design, that number is development evidence only. The independent capability sentinel is excluded-title ranks 21–50: **30 unseen high-volume rows / 7.21M searches**, with **100% Any-parent Hit@5**, **93.220% volume-weighted typed-parent Recall@5**, and no regression on the frozen 333-case source-truth suite.

Decision: planned C is complete enough for v0 research. Do not add a special residual rule, D/ESCO, embeddings or more source engineering yet. First build and adjudicate a fresh next-volume natural-language holdout with C2 outputs hidden, then evaluate the frozen C2 configuration unchanged.

Evidence: `docs/findings/c2-job-title-router-v31.md` and `research/evaluation/v31/c2-job-title-router.json`.
"""
if addition.strip() not in t:
    if t.count(anchor) != 1:
        raise RuntimeError(f"C2 finding anchor count: {t.count(anchor)}")
    t = t.replace(anchor, anchor + addition, 1)

p.write_text(t, encoding="utf-8")
