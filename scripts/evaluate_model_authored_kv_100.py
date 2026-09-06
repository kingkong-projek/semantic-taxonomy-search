#!/usr/bin/env python3
"""Evaluate 100 model-authored KV descriptions against simple Track-2 candidates.

This is deliberately development evidence, not confirmatory validation. The queries were
written after the G1 architecture existed. The evaluator therefore focuses on breadth,
uncertainty reporting, disagreement surfacing, and reviewability rather than claiming an
unbiased production accuracy estimate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, build_docs, rank
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1


EXPECTED_CASES = 100
EVIDENCE_CLASS = "synthetic_model_authored_development"


def wilson95(successes: int, n: int) -> list[float] | None:
    if n <= 0:
        return None
    z = 1.959963984540054
    p = successes / n
    den = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt((p * (1 - p) / n) + (z * z / (4 * n * n))) / den
    return [round(100 * max(0.0, center - half), 1), round(100 * min(1.0, center + half), 1)]


def metric(successes: int, n: int) -> dict[str, Any]:
    return {
        "hits": successes,
        "n": n,
        "pct": round(100 * successes / n, 1) if n else None,
        "wilson95_pct": wilson95(successes, n),
        "evidence_class": EVIDENCE_CLASS,
    }


def rank_pos(ranked: list[str], target: str) -> int | None:
    try:
        return ranked.index(target) + 1
    except ValueError:
        return None


def compact_top(ranked: list[str], by_id: dict[str, dict[str, Any]], n: int = 5) -> list[dict[str, str]]:
    out = []
    for sid in ranked[:n]:
        concept = by_id.get(sid) or {}
        out.append({"concept_id": sid, "label": str(concept.get("preferred_label") or "")})
    return out


def evaluate_rows(
    cases: list[dict[str, Any]],
    rankings: dict[str, list[list[str]]],
    by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    results: dict[str, Any] = {}
    for name, rows in rankings.items():
        h1 = h5 = h10 = 0
        for case, ranked in zip(cases, rows, strict=True):
            target = str(case["target"]["concept_id"])
            h1 += int(bool(ranked and ranked[0] == target))
            h5 += int(target in ranked[:5])
            h10 += int(target in ranked[:10])
        results[name] = {
            "top1": metric(h1, len(cases)),
            "hit_at_5": metric(h5, len(cases)),
            "hit_at_10": metric(h10, len(cases)),
        }

    details = []
    for i, case in enumerate(cases):
        target = str(case["target"]["concept_id"])
        row = {
            "id": case["id"],
            "query": case["query"],
            "difficulty": case.get("difficulty"),
            "target": case["target"],
            "rank": {},
            "top5": {},
        }
        for name in rankings:
            ranked = rankings[name][i]
            row["rank"][name] = rank_pos(ranked, target)
            row["top5"][name] = compact_top(ranked, by_id, 5)
        details.append(row)
    return results, details


def difficulty_breakdown(cases: list[dict[str, Any]], fusion: list[list[str]]) -> dict[str, Any]:
    groups: dict[str, list[tuple[dict[str, Any], list[str]]]] = {}
    for case, ranked in zip(cases, fusion, strict=True):
        key = str(case.get("difficulty") or "unspecified")
        groups.setdefault(key, []).append((case, ranked))
    out = {}
    for key, rows in sorted(groups.items()):
        h5 = sum(str(case["target"]["concept_id"]) in ranked[:5] for case, ranked in rows)
        out[key] = {"hit_at_5": metric(int(h5), len(rows))}
    return out


def deterministic_hit_sample(details: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    hits = [row for row in details if row["rank"]["C0-top1+G1d-4slot"] is not None and row["rank"]["C0-top1+G1d-4slot"] <= 5]
    hits.sort(key=lambda row: hashlib.sha256(str(row["id"]).encode("utf-8")).hexdigest())
    return hits[:limit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--cases", default="research/benchmark/v31/model-authored-kv-100/cases.jsonl")
    ap.add_argument("--manifest", default="research/benchmark/v31/model-authored-kv-100/manifest.json")
    ap.add_argument("--output", default="artifacts/model-authored-kv-100-v31.json")
    args = ap.parse_args()

    cases = load_jsonl(Path(args.cases))
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if len(cases) != EXPECTED_CASES or manifest.get("case_count") != EXPECTED_CASES:
        raise RuntimeError(f"case count drift: {len(cases)} / {manifest.get('case_count')}")
    ids = [str(c.get("id")) for c in cases]
    if len(set(ids)) != EXPECTED_CASES:
        raise RuntimeError("duplicate synthetic case id")
    if any(c.get("evidence_class") != "synthetic_model_authored" for c in cases):
        raise RuntimeError("unexpected evidence class")

    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    ranked = pareto.get("skill", {}).get("ranked_p95") or []
    top100 = ranked[:EXPECTED_CASES]
    if len(top100) != EXPECTED_CASES:
        raise RuntimeError("P80 ranking does not contain 100 skill rows")
    for i, (case, expected) in enumerate(zip(cases, top100, strict=True), start=1):
        target = case.get("target") or {}
        if int(target.get("p80_rank") or -1) != i:
            raise RuntimeError(f"rank mismatch at case {i}")
        if str(target.get("concept_id")) != str(expected.get("concept_id")):
            raise RuntimeError(f"concept mismatch at rank {i}: {target.get('concept_id')} != {expected.get('concept_id')}")
        if str(target.get("label")) != str(expected.get("label")):
            raise RuntimeError(f"label mismatch at rank {i}: {target.get('label')} != {expected.get('label')}")
        # Exact preferred-label leakage would make a natural-description stress case too trivial.
        if norm(str(target.get("label"))) and norm(str(target.get("label"))) in norm(str(case.get("query"))):
            raise RuntimeError(f"direct preferred-label leakage in {case.get('id')}: {target.get('label')}")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    version = str(args.version)
    taxonomy_body = fetch(f"https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json")
    taxonomy_sha = hashlib.sha256(taxonomy_body).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(taxonomy_body).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    training_body = fetch_training()
    training_sha = hashlib.sha256(training_body).hexdigest()
    if training_sha != TRAINING_SHA:
        raise RuntimeError("training source drift")
    training_json = json.loads(training_body)
    modules = (training_json.get("data") or training_json.get("moduler") or training_json.get("modules")) if isinstance(training_json, dict) else training_json
    if not isinstance(modules, list):
        raise RuntimeError("unexpected training source root")

    p80_ids = p80_skill_ids(pareto)
    docs, exact, coverage = build_docs(by_id, p80_ids, modules, set(), set())
    c0 = BM25(docs["KV-C0"], exact)
    g1 = BM25(docs["KV-G1-single-desc"], exact)

    rankings = {"C0": [], "G1-single-desc": [], "C0-top1+G1d-4slot": []}
    for case in cases:
        q = str(case["query"])
        a = rank(c0, exact, q)
        b = rank(g1, exact, q)
        rankings["C0"].append(a)
        rankings["G1-single-desc"].append(b)
        rankings["C0-top1+G1d-4slot"].append(fuse_preserve_c0_top1(a, b, 4))

    results, details = evaluate_rows(cases, rankings, by_id)
    fusion_details = details
    fusion_misses = [row for row in fusion_details if row["rank"]["C0-top1+G1d-4slot"] is None or row["rank"]["C0-top1+G1d-4slot"] > 5]
    c0_misses = [row for row in fusion_details if row["rank"]["C0"] is None or row["rank"]["C0"] > 5]
    rescued_vs_c0 = [row for row in fusion_details if (row["rank"]["C0"] is None or row["rank"]["C0"] > 5) and row["rank"]["C0-top1+G1d-4slot"] is not None and row["rank"]["C0-top1+G1d-4slot"] <= 5]
    regressed_vs_c0 = [row for row in fusion_details if row["rank"]["C0"] is not None and row["rank"]["C0"] <= 5 and (row["rank"]["C0-top1+G1d-4slot"] is None or row["rank"]["C0-top1+G1d-4slot"] > 5)]

    result = {
        "schema_version": 1,
        "status": "development stress test; model-authored after G1 architecture existed",
        "evidence_class": EVIDENCE_CLASS,
        "taxonomy_version": int(version),
        "taxonomy_sha256": taxonomy_sha,
        "training_sha256": training_sha,
        "case_count": len(cases),
        "unique_target_count": len({str(c["target"]["concept_id"]) for c in cases}),
        "coverage": coverage,
        "candidate": "production-form C0-top1+G1d-4slot; all eligible non-benchmark AF training-language evidence available at build time",
        "results": results,
        "difficulty_breakdown": difficulty_breakdown(cases, rankings["C0-top1+G1d-4slot"]),
        "disagreements": {
            "c0_hit5_miss_count": len(c0_misses),
            "fusion_hit5_miss_count": len(fusion_misses),
            "fusion_rescued_vs_c0_count": len(rescued_vs_c0),
            "fusion_regressed_vs_c0_count": len(regressed_vs_c0),
            "fusion_hit5_misses": fusion_misses,
            "fusion_rescued_vs_c0": rescued_vs_c0,
            "fusion_regressed_vs_c0": regressed_vs_c0,
        },
        "manual_review_packet": {
            "policy": "review every fusion miss and regression plus a deterministic 15-case sample of nominal fusion hits; raw score is never post-hoc rewritten",
            "misses_and_regressions": fusion_misses + [row for row in regressed_vs_c0 if row not in fusion_misses],
            "deterministic_hit_sample": deterministic_hit_sample(details, 15),
        },
        "all_details": details,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    compact = {
        "results": results,
        "disagreements": {k: v for k, v in result["disagreements"].items() if not isinstance(v, list)},
        "fusion_misses": [
            {
                "id": row["id"],
                "target": row["target"],
                "query": row["query"],
                "fusion_rank": row["rank"]["C0-top1+G1d-4slot"],
                "fusion_top5": row["top5"]["C0-top1+G1d-4slot"],
            }
            for row in fusion_misses
        ],
        "review_hit_sample": [
            {"id": row["id"], "target": row["target"], "query": row["query"], "fusion_rank": row["rank"]["C0-top1+G1d-4slot"], "fusion_top5": row["top5"]["C0-top1+G1d-4slot"]}
            for row in result["manual_review_packet"]["deterministic_hit_sample"]
        ],
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
