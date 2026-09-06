#!/usr/bin/env python3
"""Evaluate a conservative morphology/compound rescue over unchanged KV-C0.

The baseline candidate documents stay identical to KV-C0. A second ranker looks only at
canonical skill preferred/alternative label tokens and assigns deterministic surface
signals for exact token, component, common-prefix and bounded edit-distance similarity.
Fusion always preserves KV-C0 rank 1; at most one or two remaining top-5 slots are offered
to surface candidates before filling with the original C0 order.

This is a development ablation on a benchmark already opened by KV-C0. Any selected rule
requires a fresh holdout before it is accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_pareto_c1 import bounded_levenshtein, fuzzy_limit
from evaluate_skill_c0_training_validation import build_c0, p80_skill_ids, pct, positive_rank

CONFIGS = ("KV-C0", "KV-L1-one-slot", "KV-L1-two-slot")


def common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def pair_signal(qt: str, st: str) -> tuple[int, int]:
    """Return (signal class, specificity). Only long-ish tokens get approximate matching."""
    if qt == st:
        return 4, len(st)
    if min(len(qt), len(st)) >= 5 and (qt in st or st in qt):
        return 3, min(len(qt), len(st))
    if min(len(qt), len(st)) >= 6:
        cp = common_prefix_len(qt, st)
        if cp >= 5 and cp / min(len(qt), len(st)) >= 0.65:
            return 2, cp
    if min(len(qt), len(st)) >= 6:
        limit = min(fuzzy_limit(qt), fuzzy_limit(st))
        if limit:
            distance = bounded_levenshtein(qt, st, limit)
            if distance <= limit:
                return 1, max(len(qt), len(st)) - distance
    return 0, 0


def surface_score(query: str, surface_tokens: set[str]) -> tuple[int, int, int]:
    qtokens = set(tokens(query))
    best_class = best_specificity = pair_hits = 0
    for qt in qtokens:
        best_for_q = (0, 0)
        for st in surface_tokens:
            signal = pair_signal(qt, st)
            if signal > best_for_q:
                best_for_q = signal
        if best_for_q[0] > 0:
            pair_hits += 1
            if best_for_q > (best_class, best_specificity):
                best_class, best_specificity = best_for_q
    return best_class, pair_hits, best_specificity


def surface_rank(query: str, surfaces_by_id: dict[str, set[str]]) -> list[str]:
    scored = []
    for sid, sts in surfaces_by_id.items():
        signal_class, pair_hits, specificity = surface_score(query, sts)
        if signal_class > 0:
            scored.append((signal_class, pair_hits, specificity, sid))
    scored.sort(key=lambda row: (-row[0], -row[1], -row[2], row[3]))
    return [sid for _, _, _, sid in scored]


def fuse(c0: list[str], surface: list[str], rescue_slots: int) -> list[str]:
    if not c0:
        return surface[:5]
    merged = [c0[0]]
    for sid in surface:
        if sid not in merged:
            merged.append(sid)
        if len(merged) >= 1 + rescue_slots:
            break
    for sid in c0[1:]:
        if sid not in merged:
            merged.append(sid)
        if len(merged) >= 5:
            break
    return merged[:5]


def summarize(cases: list[dict[str, Any]], ranker: BM25, exact: dict[str, set[str]], surfaces: dict[str, set[str]], rescue_slots: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    s = defaultdict(float)
    details = []
    for case in cases:
        target = str(case["target"]["concept_id"])
        weight = int(case["target"]["occurrence_proxy"])
        c0 = positive_rank(ranker, exact, str(case["query"]))
        sr = surface_rank(str(case["query"]), surfaces)
        top5 = c0[:5] if rescue_slots == 0 else fuse(c0, sr, rescue_slots)
        h1 = bool(top5 and top5[0] == target)
        h5 = target in top5
        s["cases"] += 1; s["weight"] += weight
        s["h1"] += int(h1); s["h5"] += int(h5)
        s["wh1"] += weight * int(h1); s["wh5"] += weight * int(h5)
        base_h5 = target in c0[:5]
        surface_h5 = target in sr[:5]
        s["base_h5"] += int(base_h5); s["surface_h5"] += int(surface_h5)
        s["complement_oracle"] += int(base_h5 or surface_h5)
        details.append({
            "id": case["id"], "target_id": target,
            "base_hit5": base_h5, "surface_hit5": surface_h5, "fused_hit5": h5,
            "target_surface_signal": surface_score(str(case["query"]), surfaces[target]),
            "surface_top5_ids": sr[:5], "fused_top5_ids": top5,
        })
    return {
        "cases": int(s["cases"]), "occurrence_proxy_weight": int(s["weight"]),
        "top1_pct": pct(s["h1"], s["cases"]), "weighted_top1_pct": pct(s["wh1"], s["weight"]),
        "discovery_hit_at_5_pct": pct(s["h5"], s["cases"]), "weighted_discovery_hit_at_5_pct": pct(s["wh5"], s["weight"]),
        "surface_only_hit_at_5_pct": pct(s["surface_h5"], s["cases"]),
        "c0_or_surface_oracle_hit_at_5_pct": pct(s["complement_oracle"], s["cases"]),
    }, details


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--benchmark", default="research/benchmark/v31/training-skill-validation/cases.jsonl")
    ap.add_argument("--source-truth", default="research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl")
    ap.add_argument("--output", default="artifacts/skill-lexical-rescue-v31.json")
    args = ap.parse_args()

    cases = load_jsonl(Path(args.benchmark))
    source_truth = load_jsonl(Path(args.source_truth))
    primary = [c for c in cases if c.get("primary_descriptive_nonleaky")]
    if len(cases) != 76 or len(primary) != 63 or len(source_truth) != 617:
        raise RuntimeError("benchmark count drift")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    version = str(args.version)
    url = f"https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    body = fetch(url)
    taxonomy_sha = hashlib.sha256(body).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(body).get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    ids = p80_skill_ids(pareto)
    ranker, exact = build_c0(by_id, ids)
    surfaces: dict[str, set[str]] = {}
    for sid in ids:
        c = by_id[sid]
        label = str(c.get("preferred_label") or "").strip()
        alternatives = [x for x in as_list(c.get("alternative_labels")) if norm(x) != norm(label)]
        surfaces[sid] = {t for text in [label, *alternatives] for t in tokens(text) if t}

    configs = {
        "KV-C0": 0,
        "KV-L1-one-slot": 1,
        "KV-L1-two-slot": 2,
    }
    benchmark_out = {}
    details_out = {}
    regression_out = {}
    for name, slots in configs.items():
        all_summary, details = summarize(cases, ranker, exact, surfaces, slots)
        primary_summary, _ = summarize(primary, ranker, exact, surfaces, slots)
        benchmark_out[name] = {"all_cases": all_summary, "primary_descriptive_nonleaky": primary_summary}
        details_out[name] = details

        top1 = hit5 = 0
        misses = []
        for case in source_truth:
            positive = {str(x["concept_id"]) for x in case["must"]}
            c0 = positive_rank(ranker, exact, str(case["query"]))
            sr = surface_rank(str(case["query"]), surfaces)
            ranked5 = c0[:5] if slots == 0 else fuse(c0, sr, slots)
            t1 = bool(ranked5 and ranked5[0] in positive)
            h5 = any(sid in positive for sid in ranked5)
            top1 += int(t1); hit5 += int(h5)
            if not t1 or not h5:
                misses.append({"id": case["id"], "query": case["query"], "top5": ranked5, "top1_ok": t1, "hit5": h5})
        regression_out[name] = {
            "cases": 617, "top1_pct": pct(top1, 617), "discovery_hit_at_5_pct": pct(hit5, 617),
            "failure_count": len(misses), "failures_first_20": misses[:20],
        }

    c0_primary_details = details_out["KV-C0"]
    miss_ids = {d["id"] for d in c0_primary_details if not d["base_hit5"]}
    morphology_on_misses = defaultdict(int)
    for case in primary:
        if case["id"] not in miss_ids:
            continue
        target = str(case["target"]["concept_id"])
        signal_class, pair_hits, specificity = surface_score(str(case["query"]), surfaces[target])
        morphology_on_misses["c0_misses"] += 1
        if signal_class:
            morphology_on_misses["missa_with_any_target_surface_signal"] += 1
        morphology_on_misses[f"signal_class_{signal_class}"] += 1

    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "taxonomy_sha256": taxonomy_sha,
        "experiment_role": "development ablation; training benchmark was opened by KV-C0 before L1 design",
        "configuration": {
            "base": "unchanged KV-C0 canonical documents",
            "surface_evidence": "preferred/alternative-label tokens only; exact token > component > common-prefix > bounded edit distance",
            "fusion": "preserve C0 rank 1; offer at most one or two remaining top-5 slots to surface candidates, then fill from C0",
            "runtime_implication": "fully deterministic and precompilable/client-side; no API or ML required",
        },
        "benchmark": benchmark_out,
        "source_truth_regression": regression_out,
        "morphology_on_primary_c0_misses": dict(morphology_on_misses),
        "cases_detail": details_out,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "benchmark": benchmark_out,
        "source_truth_regression": regression_out,
        "morphology_on_primary_c0_misses": dict(morphology_on_misses),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
