#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

pareto = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
evaluation_path = Path(sys.argv[2])
evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
frozen_path = Path("research/coverage/v31/pareto-demand-aggregate.json")
frozen = json.loads(frozen_path.read_text(encoding="utf-8"))

# Pareto source may be re-hashed only if every measured value and ranked P95 member
# remains identical to the frozen result.
for section in ("occupation_name", "skill"):
    fresh = pareto[section]
    old = frozen[section]
    fp = fresh["pareto_within_active_v31_observed_occurrence_mass"]
    for key in (
        "historical_stat_rows", "active_v31_rows", "active_v31_target_universe",
        "active_v31_targets_with_observed_occurrence_pct", "all_historical_occurrences",
        "active_v31_occurrences", "active_v31_share_of_returned_occurrences_pct",
    ):
        if fresh[key] != old[key]:
            raise RuntimeError(f"Pareto drift: {section}.{key}")
    if fp["thresholds"] != old["thresholds"]:
        raise RuntimeError(f"Pareto threshold drift: {section}")
    ranked = [
        {"rank": i, "concept_id": r["concept_id"], "label": r["label"], "occurrences": r["occurrences"]}
        for i, r in enumerate(fp["priority_sets"]["p95"], 1)
    ]
    if ranked != old["ranked_p95"]:
        raise RuntimeError(f"Pareto ranked membership drift: {section}")

source = pareto["sources"]["historical_stats"]
semantic_hash = str(source["sha256"])
hash_semantics = str(source["hash_semantics"])
if len(semantic_hash) != 64 or "normalized occupation-name/skill statistic rows" not in hash_semantics:
    raise RuntimeError("unexpected Historical semantic hash contract")

frozen["schema_version"] = max(2, int(frozen.get("schema_version") or 1))
frozen["sources"]["historical_stats"] = {
    "url": source["url"],
    "sha256": semantic_hash,
    "hash_semantics": hash_semantics,
    "last_observed_raw_response_sha256": source["raw_response_sha256"],
}
frozen_path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

finding_path = Path("docs/findings/pareto-demand-priority-v31.md")
finding = finding_path.read_text(encoding="utf-8")
old_hash_line = "- Historical stats response SHA-256: `3dce0048b0c5f5ecf6854a3f2d3b4d0cbd0a5bcddca884dd5584d241ca014f7b`"
new_hash_lines = f"- Normalized Historical statistic-row SHA-256: `{semantic_hash}`\n- Hash semantics: `{hash_semantics}`"
if finding.count(old_hash_line) != 1:
    raise RuntimeError("old Historical hash line missing")
finding_path.write_text(finding.replace(old_hash_line, new_hash_lines, 1), encoding="utf-8")

registry_path = Path("research/coverage/source-adapters.json")
registry = json.loads(registry_path.read_text(encoding="utf-8"))
matches = [a for a in registry.get("adapters", []) if isinstance(a, dict) and a.get("id") == "historical-taxonomy-demand-stats"]
if len(matches) != 1:
    raise RuntimeError("historical source adapter missing/duplicated")
adapter = matches[0]
adapter["source_sha256"] = semantic_hash
adapter["source_hash_semantics"] = hash_semantics
adapter["notes"] = (
    "Historical API server-side taxonomy occurrence statistics. Used only as a corpus/popularity proxy for simple-first target prioritisation; "
    "not user query intent, semantic ground truth, canonical authority, or skill-essentiality evidence. P80 is the initial semantic priority envelope; "
    "full lexical product coverage remains unchanged. source_sha256 hashes only normalized statistic rows used by the measurement; volatile API metadata is excluded."
)
registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

for product in ("YV", "KV"):
    c = evaluation["products"][product]["C_plus_alternative_labels"]
    if c["top1_miss_count"] != 0 or any(c["overall"][metric] != 1.0 for metric in ("top1", "recall_at_10", "mrr", "ndcg_at_10")):
        raise RuntimeError(f"C source-truth evaluation not perfect for {product}")

out = Path("research/evaluation/v31/p80-lexical-ablation.json")
out.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(evaluation_path, out)
eval_sha = hashlib.sha256(out.read_bytes()).hexdigest()

def percent(value: float) -> str:
    return f"{100 * value:.1f}%"

yv, kv = evaluation["products"]["YV"], evaluation["products"]["KV"]
Path("docs/findings/p80-lexical-ablation-v31.md").write_text(f"""# P80 lexical A/B/C ablation — taxonomy v31

**Status:** measured and frozen  
**Measured:** 2026-09-06

## Result

| configuration | YV top-1 | YV Recall@10 | KV top-1 | KV Recall@10 |
|---|---:|---:|---:|---:|
| A — preferred labels only | {percent(yv['A_labels']['overall']['top1'])} | {percent(yv['A_labels']['overall']['recall_at_10'])} | {percent(kv['A_labels']['overall']['top1'])} | {percent(kv['A_labels']['overall']['recall_at_10'])} |
| B — + real canonical definitions | {percent(yv['B_plus_definitions']['overall']['top1'])} | {percent(yv['B_plus_definitions']['overall']['recall_at_10'])} | {percent(kv['B_plus_definitions']['overall']['top1'])} | {percent(kv['B_plus_definitions']['overall']['recall_at_10'])} |
| C — + canonical alternative labels | **100.0%** | **100.0%** | **100.0%** | **100.0%** |

C has **zero top-1 misses** on all 950 frozen source-truth cases. It is deterministic BM25 over the P80 target documents, with exact canonical preferred/alternative labels treated as exact indexed lexical surfaces.

The first C run exposed punctuation/tokenisation failures for `C`, `C++`, `SQL` and `Windows`. The correction was not a fuzzy special case: exact canonical alternative labels receive the same deterministic exact-surface dominance as preferred labels.

## Boundary

This is an ingestion/retrieval test over source-attested text, **not proof of natural paraphrase performance**. Definitions and alternative labels come from the same accepted taxonomy source used to build the representations.

The result therefore supports one simple decision:

> Do not add embeddings, ESCO enrichment, ad-language ETL or a semantic service merely to consume semantics already present in the P80 taxonomy core.

The next decision-bearing experiment is a small manually judged high-volume real-query sample plus compact safety cases. Additional complexity is deferred until those external-language cases expose a material residual.

## Reproducibility

- benchmark: `research/benchmark/v31/p80-source-truth/`
- evaluator: `scripts/evaluate_p80_lexical_ablation.py`
- result: `research/evaluation/v31/p80-lexical-ablation.json`
- result SHA-256: `{eval_sha}`
- taxonomy v31 SHA-256: `{evaluation['source']['taxonomy_sha256']}`
""", encoding="utf-8")

plan_path = Path("docs/research-plan.md")
text = plan_path.read_text(encoding="utf-8")
old = "First decision: run the **smallest useful baseline** on the compact Pareto benchmark before adding more data engineering.\n\n- [ ] A–D non-neural baseline"
new = """First decision: run the **smallest useful baseline** on the compact Pareto benchmark before adding more data engineering.

Preliminary source-truth result: A/B/C is complete on the 950-case P80 core. C (`preferred labels + real canonical definitions + canonical alternative labels`) reaches **100% top-1 and Recall@10 for both YV and KV** on this source-attested suite. This is an ingestion/retrieval result, not natural-paraphrase proof. The next decision-bearing step is the small manually judged real-query + safety slice before adding D/ESCO or neural retrieval.

Evidence: `docs/findings/p80-lexical-ablation-v31.md` and `research/evaluation/v31/p80-lexical-ablation.json`.

- [x] preliminary A–C source-truth lexical ablation on P80 core
- [ ] D typed graph/ESCO only if the real-query/safety residual justifies it; do not add D merely to complete an ablation ladder"""
if text.count(old) != 1:
    raise RuntimeError("Gate-3 baseline marker missing")
plan_path.write_text(text.replace(old, new, 1), encoding="utf-8")

print(json.dumps({"historical_semantic_sha256": semantic_hash, "evaluation_sha256": eval_sha}, indent=2))
