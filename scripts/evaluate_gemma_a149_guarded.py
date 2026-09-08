#!/usr/bin/env python3
"""Re-evaluate Gemma A149 with the product's lexical-primary boundary made explicit.

Exact canonical/alternative-label queries keep the frozen canonical BM25 ranking.
Only non-exact description queries use the Gemma-expanded BM25 representation.
This is an architectural invariant, not a rule selected from the opened benchmarks.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import evaluate_gemma_a149 as base
from evaluate_p80_lexical_ablation import expected_hash, fetch, load_jsonl, norm
from evaluate_yv_full_description_canonical import SOURCE_URL


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--source-truth", default="research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl")
    ap.add_argument("--output", default="artifacts/gemma-a149-guarded-tournament.json")
    args = ap.parse_args()

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    taxonomy_url = "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json"
    taxonomy_wire = fetch(taxonomy_url)
    taxonomy_sha = hashlib.sha256(taxonomy_wire).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(taxonomy_wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active_occ = {cid for cid, c in by_id.items() if c.get("type") == "occupation-name"}
    if len(active_occ) != 2105:
        raise RuntimeError(f"active YV universe drift: {len(active_occ)}")
    ids = sorted(active_occ)

    teacher, teacher_sha, compact = base.load_teacher(Path(args.teacher), active_occ)
    baseline_ranker, baseline_exact, baseline_surfaces = base.build_ranker(by_id, ids)
    a149_ranker, a149_exact, a149_surfaces = base.build_ranker(by_id, ids, teacher)
    exact_lookup = {surface for surfaces in baseline_exact.values() for surface in surfaces}

    def baseline_rank(query: str) -> list[str]:
        return base.rank_ids(baseline_ranker, baseline_exact, baseline_surfaces, query)

    def raw_a149_rank(query: str) -> list[str]:
        return base.rank_ids(a149_ranker, a149_exact, a149_surfaces, query)

    def guarded_a149_rank(query: str) -> list[str]:
        # In the actual product this is an O(1) exact-surface lookup/router.
        # The description lane only receives queries that are not exact known surfaces.
        if norm(query) in exact_lookup:
            return baseline_rank(query)
        return raw_a149_rank(query)

    source_wire = fetch(SOURCE_URL)
    source_sha = hashlib.sha256(source_wire).hexdigest()
    if source_sha != expected_hash(registry, "occupational-information"):
        raise RuntimeError("occupational-information source drift")
    strict = base.strict_source_cases(json.loads(source_wire), by_id, active_occ)
    baseline_strict = base.rank_metrics(strict, [baseline_rank(row["query"]) for row in strict])
    raw_strict = base.rank_metrics(strict, [raw_a149_rank(row["query"]) for row in strict])
    guarded_strict = base.rank_metrics(strict, [guarded_a149_rank(row["query"]) for row in strict])
    if (baseline_strict["top1"], baseline_strict["hit_at_5"]) != (6, 9):
        raise RuntimeError("strict baseline parity failed")

    stress = json.loads(Path(args.stress).read_text(encoding="utf-8"))
    yv_stress = stress.get("yv") or []
    if len(yv_stress) != 54:
        raise RuntimeError(f"YV stress suite drift: {len(yv_stress)}")
    baseline_stress = base.stress_summary(yv_stress, by_id, [baseline_rank(str(c["query"])) for c in yv_stress])
    raw_stress = base.stress_summary(yv_stress, by_id, [raw_a149_rank(str(c["query"])) for c in yv_stress])
    guarded_stress = base.stress_summary(yv_stress, by_id, [guarded_a149_rank(str(c["query"])) for c in yv_stress])
    expected_baseline = {"direct": 8, "colloquial": 2, "noisy": 5, "indirect": 3}
    for category, expected_hits in expected_baseline.items():
        if baseline_stress["categories"][category].get("top5_family_hit") != expected_hits:
            raise RuntimeError(f"stress baseline parity failed for {category}")

    source_truth = load_jsonl(Path(args.source_truth))
    if len(source_truth) != 333:
        raise RuntimeError(f"canonical source-truth drift: {len(source_truth)}")

    def guard_metrics(rank_fn) -> dict[str, int]:
        top1 = hit5 = 0
        for case in source_truth:
            expected = {str(x["concept_id"]) for x in case.get("must") or []}
            ranked = rank_fn(str(case["query"]))
            top1 += int(bool(ranked) and ranked[0] in expected)
            hit5 += int(any(cid in expected for cid in ranked[:5]))
        return {"cases": len(source_truth), "top1": top1, "hit_at_5": hit5}

    baseline_guard = guard_metrics(baseline_rank)
    raw_guard = guard_metrics(raw_a149_rank)
    guarded_guard = guard_metrics(guarded_a149_rank)
    if baseline_guard != {"cases": 333, "top1": 333, "hit_at_5": 333}:
        raise RuntimeError(f"baseline canonical guard parity failed: {baseline_guard}")
    if guarded_guard != baseline_guard:
        raise RuntimeError(f"guarded candidate regressed exact lexical behavior: {guarded_guard}")

    teacher_labels = [norm(by_id[cid].get("preferred_label")) for cid in teacher]
    stress_coverage = {}
    for category in ("direct", "colloquial", "noisy", "indirect"):
        subset = [c for c in yv_stress if c.get("category") == category and c.get("expect")]
        covered = 0
        for case in subset:
            needles = [norm(x) for x in case.get("expect") or [] if norm(x)]
            covered += int(any(any(needle in label for needle in needles) for label in teacher_labels))
        stress_coverage[category] = {"target_cases": len(subset), "teacher_family_covered": covered}

    compact_gzip = gzip.compress(compact, compresslevel=9, mtime=0)
    result = {
        "schema_version": 1,
        "status": "opened partial A architecture diagnostic; no runtime promotion",
        "candidate": {
            "id": "YV-A149-Gemma4-26B-sequence-expansion-v0-lexical-guarded",
            "universe": 2105,
            "teacher_expanded_concepts": len(teacher),
            "teacher_phrases": sum(len(v) for v in teacher.values()),
            "teacher_model": base.EXPECTED_TEACHER_MODEL,
            "teacher_jsonl_sha256": teacher_sha,
            "routing": "exact canonical/alternative surface -> frozen lexical baseline; otherwise Gemma-expanded description BM25",
        },
        "coverage": {
            "strict17_target_concepts_expanded": sum(row["target_id"] in teacher for row in strict),
            "stress_target_family_coverage": stress_coverage,
        },
        "size": {
            "incremental_compact_teacher_json_raw_bytes": len(compact),
            "incremental_compact_teacher_json_gzip9_bytes": len(compact_gzip),
            "rough_linear_full_2105_projection_gzip9_bytes": round(len(compact_gzip) * 2105 / len(teacher)),
            "projection_warning": "linear projection only; not a measured full-corpus artifact",
        },
        "strict_source_attested_17": {
            "baseline_full_canonical": baseline_strict,
            "gemma_a149_raw": raw_strict,
            "gemma_a149_guarded": guarded_strict,
        },
        "opened_stress_54": {
            "baseline_full_canonical": baseline_stress,
            "gemma_a149_raw": raw_stress,
            "gemma_a149_guarded": guarded_stress,
        },
        "canonical_source_truth_333": {
            "baseline_full_canonical": baseline_guard,
            "gemma_a149_raw": raw_guard,
            "gemma_a149_guarded": guarded_guard,
        },
        "sources": {
            "taxonomy_sha256": taxonomy_sha,
            "occupational_information_sha256": source_sha,
            "stress_path": args.stress,
        },
        "evidence_warning": "17-case and 54-case suites are already-opened development evidence. The lexical guard is a pre-existing product boundary, not tuned from these outcomes.",
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "candidate": result["candidate"],
        "coverage": result["coverage"],
        "size": result["size"],
        "strict_source_attested_17": {
            k: {kk: vv for kk, vv in v.items() if kk != "rows"}
            for k, v in result["strict_source_attested_17"].items()
        },
        "opened_stress_categories": {
            k: v["categories"] for k, v in result["opened_stress_54"].items()
        },
        "canonical_source_truth_333": result["canonical_source_truth_333"],
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
