#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

SOURCE = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/p80-benchmark-v31")
DEST = Path("research/benchmark/v31/p80-source-truth")
FILES = ("yv-p80-source-truth.jsonl", "kv-p80-source-truth.jsonl", "manifest.json")

manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
if manifest.get("taxonomy_version") != 31:
    raise RuntimeError("expected taxonomy v31 benchmark")
if manifest.get("selection", {}).get("total_p80_targets") != 475:
    raise RuntimeError("expected 475 P80 targets")
if manifest.get("cases", {}).get("total") != 950:
    raise RuntimeError("expected 950 P80 source-truth cases")
if manifest.get("cases", {}).get("YV") != 333 or manifest.get("cases", {}).get("KV") != 617:
    raise RuntimeError("unexpected YV/KV case partition")

DEST.mkdir(parents=True, exist_ok=True)
for name in FILES:
    shutil.copyfile(SOURCE / name, DEST / name)

hashes = {
    name: {
        "sha256": hashlib.sha256((DEST / name).read_bytes()).hexdigest(),
        "bytes": (DEST / name).stat().st_size,
    }
    for name in FILES
}

finding = f"""# P80 source-truth decision benchmark — taxonomy v31

**Status:** frozen and validator-clean  
**Frozen:** 2026-09-06

## Result

The first deterministic Gate-2 benchmark now covers the full **475-target P80 semantic priority core** without synthetic wording or inferred labels.

| product | P80 targets | benchmark cases | preferred-label cases | canonical-definition cases | alternative-label cases |
|---|---:|---:|---:|---:|---:|
| YV | 159 occupation-name | **333** | 159 | 137 | 37 |
| KV | 316 skill | **617** | 316 | 193 | 108 |
| total | **475** | **950** | 475 | 330 | 145 |

Every P80 target is represented. One KV surface is source-truth ambiguous: `Marknadsföring` is an alternative label for both `Marknadsföring/PR` and `Marknadsföring/Marknadskommunikation`; the benchmark correctly retains both identities rather than forcing a single answer.

## What this benchmark proves

This suite is deliberately conservative:

- preferred labels, real canonical definitions and canonical alternative labels are taken from the accepted taxonomy v31 snapshot;
- YV positive identities are additionally checked against published Yrkesväljaren product admission;
- Historical API occurrence counts only selected the P80 population and never become destination truth;
- no observed free-text query, ad-derived phrase, model output or synthetic phrase is auto-labelled as truth.

It is therefore a strong regression/source-ingestion benchmark and a valid first ablation surface for simple lexical evidence layers.

## What it does not prove

The definition and alternative-label cases are source-attested text. They do **not** by themselves establish performance on natural user paraphrases. A small manually judged high-volume observed-query slice remains necessary before conclusions about embeddings or real semantic UX are made.

## Frozen files

- `research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl` — {hashes['yv-p80-source-truth.jsonl']['bytes']:,} bytes — SHA-256 `{hashes['yv-p80-source-truth.jsonl']['sha256']}`
- `research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl` — {hashes['kv-p80-source-truth.jsonl']['bytes']:,} bytes — SHA-256 `{hashes['kv-p80-source-truth.jsonl']['sha256']}`
- `research/benchmark/v31/p80-source-truth/manifest.json` — SHA-256 `{hashes['manifest.json']['sha256']}`

Builder: `scripts/build_p80_decision_benchmark.py`  
Validator: `scripts/validate_benchmark.py`
"""
Path("docs/findings/p80-decision-benchmark-v31.md").write_text(finding, encoding="utf-8")

plan_path = Path("docs/research-plan.md")
text = plan_path.read_text(encoding="utf-8")
old = "- [ ] freeze a 500–1,000 case benchmark around the 475-target P80 core plus compact safety/boundary slices\n- [ ] automatic strata construction only where source truth permits"
new = "- [x] freeze the **950-case P80 source-truth core benchmark**: 333 YV + 617 KV cases over all 475 P80 targets; preferred labels + 330 real canonical-definition cases + 145 alternative-label cases; validator-clean and frozen in repo\n- [x] automatic source-truth strata construction for preferred labels, real canonical definitions and alternative labels; no corpus/model/synthetic signal is auto-promoted to destination truth"
if text.count(old) != 1:
    raise RuntimeError("Gate-2 benchmark work-sequence marker not found exactly once")
text = text.replace(old, new, 1)

marker = "The initial benchmark should be sufficient to choose between simple baselines. It is not a census of the taxonomy.\n\nShared strata:"
replacement = """The initial benchmark should be sufficient to choose between simple baselines. It is not a census of the taxonomy.

The frozen source-truth core currently contains **950 cases**: 333 YV and 617 KV over all 475 P80 targets. It includes 475 preferred-label cases, 330 real canonical-definition cases and 145 alternative-label cases. This is deliberately a source-attested benchmark; it must be complemented by a small manually judged real-query slice before making claims about natural paraphrase performance.

Evidence: `docs/findings/p80-decision-benchmark-v31.md` and `research/benchmark/v31/p80-source-truth/manifest.json`.

Shared strata:"""
if text.count(marker) != 1:
    raise RuntimeError("Gate-2 benchmark intro marker not found exactly once")
text = text.replace(marker, replacement, 1)
plan_path.write_text(text, encoding="utf-8")

print(json.dumps({"hashes": hashes, "cases": manifest["cases"]}, ensure_ascii=False, indent=2, sort_keys=True))
