#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

PARETO = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pareto-demand-v31/aggregate.json")
EVAL = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/p80-lexical-ablation-v31.json")

fresh_pareto = json.loads(PARETO.read_text(encoding="utf-8"))
evaluation = json.loads(EVAL.read_text(encoding="utf-8"))
frozen_path = Path("research/coverage/v31/pareto-demand-aggregate.json")
frozen = json.loads(frozen_path.read_text(encoding="utf-8"))

# The API response contains volatile timing metadata. We may update only source-hash
# semantics here; the priority population and measured counts must remain identical.
for section in ("occupation_name", "skill"):
    fresh = fresh_pareto[section]
    old = frozen[section]
    fp = fresh["pareto_within_active_v31_observed_occurrence_mass"]
    for key in (
        "historical_stat_rows",
        "active_v31_rows",
        "active_v31_target_universe",
        "active_v31_targets_with_observed_occurrence_pct",
        "all_historical_occurrences",
        "active_v31_occurrences",
        "active_v31_share_of_returned_occurrences_pct",
    ):
        if fresh[key] != old[key]:
            raise RuntimeError(f"Pareto measurement drift in {section}.{key}: {old[key]!r} -> {fresh[key]!r}")
    if fp["thresholds"] != old["thresholds"]:
        raise RuntimeError(f"Pareto threshold drift in {section}")
    fresh_ranked = [
        {"rank": i, "concept_id": r["concept_id"], "label": r["label"], "occurrences": r["occurrences"]}
        for i, r in enumerate(fp["priority_sets"]["p95"], 1)
    ]
    if fresh_ranked != old["ranked_p95"]:
        raise RuntimeError(f"Pareto ranked P95 membership drift in {section}")

canonical_hash = fresh_pareto["sources"]["historical_stats"]["sha256"]
hash_semantics = fresh_pareto["sources"]["historical_stats"]["hash_semantics"]
raw_hash = fresh_pareto["sources"]["historical_stats"]["raw_response_sha256"]
if canonical_hash != "049a3979c3e9458fe60191575a352f7d780ede7196a4aacffd1c335b0ecf99c7":
    raise RuntimeError(f"unexpected canonical stats hash {canonical_hash}")

frozen["schema_version"] = max(2, int(frozen.get("schema_version") or 1))
frozen["sources"]["historical_stats"] = {
    "url": fresh_pareto["sources"]["historical_stats"]["url"],
    "sha256": canonical_hash,
    "hash_semantics": hash_semantics,
    "last_observed_raw_response_sha256": raw_hash,
}
frozen_path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

# Update finding wording only; measured population is unchanged.
finding_path = Path("docs/findings/pareto-demand-priority-v31.md")
finding = finding_path.read_text(encoding="utf-8")
old = "- Historical stats response SHA-256: `3dce0048b0c5f5ecf6854a3f2d3b4d0cbd0a5bcddca884dd5584d241ca014f7b`"
new = f"- Canonical Historical `stats` payload SHA-256: `{canonical_hash}`\n- Hash semantics: `{hash_semantics}`"
if finding.count(old) != 1:
    raise RuntimeError("old Pareto finding hash marker not found exactly once")
finding_path.write_text(finding.replace(old, new, 1), encoding="utf-8")

# Update source registry adapter without touching unrelated adapters.
registry_path = Path("research/coverage/source-adapters.json")
registry = json.loads(registry_path.read_text(encoding="utf-8"))
adapters = registry.get("adapters")
if not isinstance(adapters, list):
    raise RuntimeError("source adapter registry missing adapters")
matches = [a for a in adapters if isinstance(a, dict) and a.get("id") == "historical-taxonomy-demand-stats"]
if len(matches) != 1:
    raise RuntimeError("expected exactly one historical-taxonomy-demand-stats adapter")
adapter = matches[0]
adapter["source_sha256"] = canonical_hash
adapter["source_hash_semantics"] = hash_semantics
adapter["notes"] = (
    "Historical API server-side taxonomy occurrence statistics. Used only as a corpus/popularity proxy for simple-first target prioritisation; "
    "not user query intent, semantic ground truth, canonical authority, or skill-essentiality evidence. P80 is the initial semantic priority envelope; "
    "full lexical product coverage remains unchanged. source_sha256 hashes only the canonical JSON `stats` object because response timing metadata is volatile."
)
registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Freeze compact evaluation result.
for product in ("YV", "KV"):
    c = evaluation["products"][product]["C_plus_alternative_labels"]
    if c["top1_miss_count"] != 0:
        raise RuntimeError(f"expected zero C top1 misses for {product}")
    for metric in ("top1", "recall_at_10", "mrr", "ndcg_at_10"):
        if c["overall"][metric] != 1.0:
            raise RuntimeError(f"expected perfect C {product} {metric}, got {c['overall'][metric]}")

out = Path("research/evaluation/v31/p80-lexical-ablation.json")
out.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(EVAL, out)
eval_sha = hashlib.sha256(out.read_bytes()).hexdigest()

def pct(v: float) -> str:
    return f"{100.0*v:.1f}%"

yv = evaluation["products"]["YV"]
kv = evaluation["products"]["KV"]
eval_finding = f"""# P80 lexical A/B/C ablation — taxonomy v31

**Status:** measured and frozen  
**Measured:** 2026-09-06

## Result

The smallest deterministic retrieval configuration already consumes the frozen P80 source truth very well.

| configuration | YV top-1 | YV Recall@10 | KV top-1 | KV Recall@10 |
|---|---:|---:|---:|---:|
| A — preferred labels only | {pct(yv['A_labels']['overall']['top1'])} | {pct(yv['A_labels']['overall']['recall_at_10'])} | {pct(kv['A_labels']['overall']['top1'])} | {pct(kv['A_labels']['overall']['recall_at_10'])} |
| B — + real canonical definitions | {pct(yv['B_plus_definitions']['overall']['top1'])} | {pct(yv['B_plus_definitions']['overall']['recall_at_10'])} | {pct(kv['B_plus_definitions']['overall']['top1'])} | {pct(kv['B_plus_definitions']['overall']['recall_at_10'])} |
| C — + canonical alternative labels | **{pct(yv['C_plus_alternative_labels']['overall']['top1'])}** | **{pct(yv['C_plus_alternative_labels']['overall']['recall_at_10'])}** | **{pct(kv['C_plus_alternative_labels']['overall']['top1'])}** | **{pct(kv['C_plus_alternative_labels']['overall']['recall_at_10'])}** |

C has **zero top-1 misses** on all 950 frozen source-truth cases. It uses deterministic BM25 over only the P80 target documents plus exact indexed lexical-surface dominance for preferred/alternative labels.

The first run exposed four punctuation/tokenisation failures (`C`, `C++`, `SQL`, `Windows`). They were fixed by treating exact canonical alternative labels as exact indexed surfaces rather than adding fuzzy/token-specific exceptions. After that correction C is perfect on this suite.

## Interpretation

This is deliberately **not** evidence that natural-language semantic search is solved. The benchmark text comes from the same canonical source family used to build A/B/C representations:

- preferred labels test exact identity retrieval;
- canonical definitions test whether real curated descriptive text can be consumed;
- alternative labels test canonical vocabulary expansion.

What it does establish is important for the simple-first plan:

> We do not need embeddings, ESCO enrichment, ad-language ETL or a semantic service merely to exploit the semantics already present in the P80 taxonomy core.

The next decision-bearing experiment is therefore a **small manually judged sample of high-volume real observed YV queries**, plus compact safety cases. Additional source/model complexity is deferred until that external-language slice shows a residual that A/B/C cannot solve safely.

## Reproducibility

- frozen benchmark: `research/benchmark/v31/p80-source-truth/`
- evaluator: `scripts/evaluate_p80_lexical_ablation.py`
- machine result: `research/evaluation/v31/p80-lexical-ablation.json`
- result SHA-256: `{eval_sha}`
- taxonomy v31 SHA-256: `{evaluation['source']['taxonomy_sha256']}`
"""
Path("docs/findings/p80-lexical-ablation-v31.md").write_text(eval_finding, encoding="utf-8")

# Synchronize SSOT without claiming Gate 3 A-D is complete.
plan_path = Path("docs/research-plan.md")
text = plan_path.read_text(encoding="utf-8")
old = "First decision: run the **smallest useful baseline** on the compact Pareto benchmark before adding more data engineering.\n\n- [ ] A–D non-neural baseline"
new = """First decision: run the **smallest useful baseline** on the compact Pareto benchmark before adding more data engineering.

Preliminary source-truth result: A/B/C is complete on the 950-case P80 core. C (`preferred labels + real canonical definitions + canonical alternative labels`) reaches **100% top-1 and Recall@10 for both YV and KV** on this source-attested suite. This is an ingestion/retrieval result, not natural-paraphrase proof. The next decision-bearing step is the small manually judged real-query + safety slice before adding D/ESCO or neural retrieval.

Evidence: `docs/findings/p80-lexical-ablation-v31.md` and `research/evaluation/v31/p80-lexical-ablation.json`.

- [x] preliminary A–C source-truth lexical ablation on P80 core
- [ ] D typed graph/ESCO only if the real-query/safety residual justifies it; do not add D merely to complete an ablation ladder"""
if text.count(old) != 1:
    raise RuntimeError("Gate-3 A-D marker not found exactly once")
text = text.replace(old, new, 1)
plan_path.write_text(text, encoding="utf-8")

print(json.dumps({
    "canonical_stats_sha256": canonical_hash,
    "evaluation_sha256": eval_sha,
    "YV_C": yv["C_plus_alternative_labels"]["overall"],
    "KV_C": kv["C_plus_alternative_labels"]["overall"],
}, indent=2, sort_keys=True))
