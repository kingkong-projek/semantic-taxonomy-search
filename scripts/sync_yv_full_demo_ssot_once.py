#!/usr/bin/env python3
from pathlib import Path

p = Path('docs/research-plan.md')
t = p.read_text(encoding='utf-8')

old = "- This full-universe candidate is the active YV description baseline for the next human gate. **C2 remains a regression/demo reference;** the ad-language and Relevanta-kompetenser lanes remain diagnostic-only and are not fused into the frozen candidate."
new = "- This full-universe candidate is the active YV description baseline for the next human gate. **C2 remains a regression reference only;** the public zero-backend demo now packages `YV-description-full-v0-canonical-router` over all 2,105 active occupation-name identities with the exact job-title router. The ad-language and Relevanta-kompetenser lanes remain diagnostic-only and are not fused into the frozen candidate."
count = t.count(old)
if count != 1:
    raise RuntimeError(f'expected exactly one stale C2 demo-reference sentence, got {count}')
t = t.replace(old, new, 1)

p.write_text(t, encoding='utf-8')
