#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

source = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/yv-real-query-review-v31")
manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
if manifest.get("status") != "PENDING_HUMAN_REVIEW" or manifest.get("queries") != 50:
    raise RuntimeError("unexpected review packet state")
if manifest.get("selected_share_of_all_frozen_query_volume_pct") != 23.661:
    raise RuntimeError("review selection volume drift")
if manifest.get("selected_share_of_unbound_query_volume_pct") != 35.117:
    raise RuntimeError("review unbound-volume share drift")
if manifest.get("simple_C_zero_evidence_queries") != 29:
    raise RuntimeError("simple C0 zero-evidence count drift")
if manifest.get("simple_C_zero_evidence_share_of_selected_volume_pct") != 49.491:
    raise RuntimeError("simple C0 zero-evidence volume drift")

rows = [json.loads(line) for line in (source / "review-packet.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
if len(rows) != 50:
    raise RuntimeError("expected 50 review rows")
if any(row["adjudication"]["status"] != "PENDING_HUMAN_REVIEW" for row in rows):
    raise RuntimeError("review packet contains adjudicated row")
if any(row["adjudication"][bucket] for row in rows for bucket in ("must", "acceptable", "must_not")):
    raise RuntimeError("pending review packet contains destination judgments")

out = Path("research/benchmark/v31/yv-real-query-review")
out.mkdir(parents=True, exist_ok=True)
for name in ("review-packet.jsonl", "manifest.json", "review.md"):
    shutil.copyfile(source / name, out / name)

hashes = {name: hashlib.sha256((out / name).read_bytes()).hexdigest() for name in ("review-packet.jsonl", "manifest.json", "review.md")}

Path("docs/findings/yv-high-volume-real-query-review-v31.md").write_text(f"""# YV high-volume real-query review slice — taxonomy v31

**Status:** prepared, not adjudicated  
**Prepared:** 2026-09-06

## Selection

The review packet contains the **50 highest-volume unbound query strings** recomputed directly from the pinned Yrkesväljaren generator corpus (`6dd9e4737d7db3cb2709f8082808b88e5c89ed6e`). No semantic filter is used to choose them.

They represent:

- **742,033,566 searches**;
- **23.661% of all frozen query volume**;
- **35.117% of the previously measured unbound query volume**.

The packet remains `PENDING_HUMAN_REVIEW`. Observed frequency is not query→destination truth and the candidate list is not a label.

## Immediate diagnostic value

The raw high-volume slice visibly mixes occupation-like strings (`lärare`, `lagerarbetare`, `systemutvecklare`, `civilingenjör`, `programmerare`, `handläggare`) with general/geographic search strings (`stockholms län`, `göteborg`, `stockholm`, `umeå`, `skåne län`, `malmö`, etc.).

This means **raw unbound JobSearch text cannot be treated as an occupation-intent benchmark merely because it is frequent**. Intent/adjudication must precede relevance scoring.

The current simple C0 representation (P80 preferred labels + real canonical definitions + alternative labels) has zero positive lexical evidence for **29/50 queries**, accounting for **49.491% of the packet's volume**. Those rows now explicitly abstain rather than returning an arbitrary zero-score nearest occupation.

Positive lexical evidence is still only reviewer context. For example, a geographic string may overlap incidental words in canonical definitions; that is precisely why the packet must be judged before it becomes evaluation truth.

## Next review task

For each query, the reviewer decides:

- `SINGLE`, `AMBIGUOUS` or `NO_MATCH/OTHER_INTENT` for the YV semantic occupation task;
- exact `MUST`, `ACCEPTABLE` and `MUST_NOT` occupation identities where an occupation intent exists;
- whether the correct target is inside P80 or requires P90/P95/tail expansion;
- a short note only when the decision is not obvious.

Do not judge from the current top-5 candidate list. It is shown only to reduce lookup work.

## Frozen files

- `research/benchmark/v31/yv-real-query-review/review-packet.jsonl` — SHA-256 `{hashes['review-packet.jsonl']}`
- `research/benchmark/v31/yv-real-query-review/manifest.json` — SHA-256 `{hashes['manifest.json']}`
- `research/benchmark/v31/yv-real-query-review/review.md` — SHA-256 `{hashes['review.md']}`
""", encoding="utf-8")

plan_path = Path("docs/research-plan.md")
text = plan_path.read_text(encoding="utf-8")
old = "- [ ] compact safety/regression slices: multi-parent ambiguity, excluded-YV routing, hard negatives and no-match/abstention\n- [ ] small manually judged sample from high-volume unbound observed language"
new = """- [ ] compact safety/regression slices: multi-parent ambiguity, excluded-YV routing, hard negatives and no-match/abstention
- [x] prepare deterministic **top-50 high-volume unbound YV review packet** from the pinned real query corpus: 742.0M searches = 23.661% of all volume / 35.117% of unbound volume; remains fully `PENDING_HUMAN_REVIEW`
- [ ] adjudicate the prepared top-50 real-query packet into occupation intent vs other/no-match and MUST/ACCEPTABLE/MUST_NOT identities; do not score it before review"""
if text.count(old) != 1:
    raise RuntimeError("Gate-2 real-query marker missing")
text = text.replace(old, new, 1)

old2 = "- [x] preliminary A–C source-truth lexical ablation on P80 core\n- [ ] D typed graph/ESCO only if the real-query/safety residual justifies it; do not add D merely to complete an ablation ladder"
new2 = """- [x] preliminary **A/B/C0** source-truth lexical ablation on P80 core, where C0 = preferred labels + real canonical definitions + canonical alternative labels
- [ ] complete planned C's product-title/retrieval-vocabulary portion only where the real-query/safety slice demonstrates value; do not conflate C0 with full planned C
- [ ] D typed graph/ESCO only if the adjudicated real-query/safety residual justifies it; do not add D merely to complete an ablation ladder"""
if text.count(old2) != 1:
    raise RuntimeError("Gate-3 C0 marker missing")
text = text.replace(old2, new2, 1)

old3 = "Preliminary source-truth result: A/B/C is complete on the 950-case P80 core. C (`preferred labels + real canonical definitions + canonical alternative labels`) reaches **100% top-1 and Recall@10 for both YV and KV** on this source-attested suite."
new3 = "Preliminary source-truth result: A/B/C0 is complete on the 950-case P80 core. C0 (`preferred labels + real canonical definitions + canonical alternative labels`) reaches **100% top-1 and Recall@10 for both YV and KV** on this source-attested suite. C0 intentionally does **not** yet include the planned C layer's product-title/retrieval vocabulary."
if text.count(old3) != 1:
    raise RuntimeError("Gate-3 prose C0 marker missing")
text = text.replace(old3, new3, 1)

plan_path.write_text(text, encoding="utf-8")
print(json.dumps({"hashes": hashes, "manifest": manifest}, ensure_ascii=False, indent=2, sort_keys=True))
