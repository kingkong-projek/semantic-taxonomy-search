#!/usr/bin/env python3
"""Test whether visible YV candidates can be relevance-gated without destroying Hit@5.

This is a prefrozen synthetic mechanism/calibration experiment, not human accuracy.
The ranker is not changed. P80 concepts are deterministically split by concept id
before any threshold is selected:

- calibration concepts choose one simple per-candidate display rule;
- evaluation concepts measure target retention and irrelevant-candidate removal;
- opened 17/88 stress rows are never loaded.

The exact synthetic target identity is treated as the positive candidate. Semantically
acceptable siblings are therefore counted as negatives, making display precision a
conservative proxy rather than human relevance truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_a593_language_diversity_falsifier import load_diverse_training, load_teacher
from evaluate_gemma_a149 import build_ranker
from evaluate_p80_lexical_ablation import expected_hash, fetch, tokens
from evaluate_pareto_c1 import rank_c1

TAXONOMY_URL = (
    "https://data.jobtechdev.se/taxonomy/version/31/query/"
    "concepts-and-common-relations/concepts-and-common-relations.json"
)
STYLES = ("compressed_note", "outcome_context", "plain_search", "shift_story")
EXPECTED_UNIVERSE = 2105
SPLIT_SALT = "p80-display-relevance-calibration-v0"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def add_teacher(dst: dict[str, list[str]], src: dict[str, list[str]], allowed: set[str] | None = None) -> None:
    for cid, values in src.items():
        if allowed is not None and cid not in allowed:
            continue
        dst.setdefault(cid, []).extend(values)


def split_for(cid: str) -> str:
    digest = hashlib.sha256(f"{SPLIT_SALT}:{cid}".encode()).digest()
    # 60/40 concept-level split; no query from one identity crosses the boundary.
    return "calibration" if digest[0] % 5 < 3 else "evaluation"


def load_cases(
    a593_holdout: Path,
    p80_holdout: Path,
    rescue_holdout: Path,
    existing_ids: set[str],
    missing_ids: set[str],
    a593_train: dict[str, list[str]],
    p80_train: dict[str, list[str]],
    rescue_train: dict[str, list[str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def ingest(path: Path, allowed: set[str], trained: dict[str, list[str]], source: str) -> None:
        for row in read_jsonl(path):
            cid = str(row.get("concept_id") or "")
            if cid not in allowed or cid not in trained or not row.get("usable"):
                continue
            for style in STYLES:
                query = (row.get("queries") or {}).get(style)
                if not isinstance(query, str) or not query.strip():
                    continue
                key = (cid, style, query.strip())
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "concept_id": cid,
                    "label": str(row.get("label") or cid),
                    "style": style,
                    "query": query.strip(),
                    "source": source,
                    "split": split_for(cid),
                })

    ingest(a593_holdout, existing_ids, a593_train, "a593_diverse_holdout")
    ingest(p80_holdout, missing_ids, p80_train, "p80_diverse_holdout")
    # Rescue identities are a subset of missing_ids and were not usable in the
    # canonical-definition P80 generator. Their independent rescue holdout is additive.
    ingest(rescue_holdout, missing_ids, rescue_train, "source_thin_rescue_holdout")
    return rows


def candidate_features(ranker, query: str, scored: list[tuple[str, float, str]]) -> list[dict[str, Any]]:
    top = scored[:5]
    if not top:
        return []
    qtokens = sorted(set(tokens(query)))
    top_score = float(top[0][1])
    max_idf = max(ranker.idf.values(), default=1.0)
    # Unseen query terms get max-IDF weight: unusual unsupported words should reduce
    # evidence coverage rather than disappear from the denominator.
    query_mass = sum(float(ranker.idf.get(t, max_idf)) for t in qtokens) or 1.0
    out = []
    for rank, (cid, score, signal) in enumerate(top, 1):
        shared = [t for t in qtokens if ranker.tf[cid].get(t, 0)]
        idf_mass = sum(float(ranker.idf.get(t, max_idf)) for t in shared)
        token_coverage = len(shared) / max(1, len(qtokens))
        idf_coverage = idf_mass / query_mass
        ratio = float(score / top_score) if top_score > 0 else 0.0
        out.append({
            "rank": rank,
            "concept_id": cid,
            "score": float(score),
            "score_ratio": ratio,
            "shared_count": len(shared),
            "token_coverage": token_coverage,
            "idf_coverage": idf_coverage,
            "combined": ratio * idf_coverage,
            "signal": signal,
        })
    return out


def average_precision(items: list[tuple[float, bool]]) -> float:
    positives = sum(int(y) for _, y in items)
    if not positives:
        return 0.0
    ranked = sorted(items, key=lambda x: -x[0])
    seen_pos = 0
    total = 0.0
    for i, (_score, y) in enumerate(ranked, 1):
        if y:
            seen_pos += 1
            total += seen_pos / i
    return total / positives


def roc_auc(items: list[tuple[float, bool]]) -> float:
    pos = [s for s, y in items if y]
    neg = [s for s, y in items if not y]
    if not pos or not neg:
        return 0.0
    wins = 0.0
    for p in pos:
        for n in neg:
            wins += 1.0 if p > n else 0.5 if p == n else 0.0
    return wins / (len(pos) * len(neg))


def separability(rows: list[dict[str, Any]], *, tail_only: bool) -> dict[str, Any]:
    candidates = [
        c
        for row in rows
        for c in row["candidates"]
        if (not tail_only or c["rank"] >= 2)
    ]
    result: dict[str, Any] = {
        "candidate_rows": len(candidates),
        "positive_rows": sum(int(c["is_target"]) for c in candidates),
    }
    for feature in ("score_ratio", "shared_count", "token_coverage", "idf_coverage", "combined"):
        items = [(float(c[feature]), bool(c["is_target"])) for c in candidates]
        result[feature] = {
            "roc_auc": round(roc_auc(items), 6),
            "average_precision": round(average_precision(items), 6),
        }
    return result


def keep_candidate(c: dict[str, Any], rule: dict[str, Any]) -> bool:
    return (
        float(c["score_ratio"]) >= float(rule["score_ratio_min"])
        and float(c["token_coverage"]) >= float(rule["token_coverage_min"])
        and float(c["idf_coverage"]) >= float(rule["idf_coverage_min"])
        and int(c["shared_count"]) >= int(rule["shared_count_min"])
    )


def summarize_rule(rows: list[dict[str, Any]], rule: dict[str, Any]) -> dict[str, Any]:
    baseline_hits = 0
    retained_hits = 0
    baseline_tail_hits = 0
    retained_tail_hits = 0
    displayed = 0
    irrelevant = 0
    zero = 0
    rank_retention: dict[str, list[int]] = {str(i): [0, 0] for i in range(1, 6)}

    for row in rows:
        target = row["concept_id"]
        candidates = row["candidates"]
        target_row = next((c for c in candidates if c["concept_id"] == target), None)
        if target_row:
            baseline_hits += 1
            r = int(target_row["rank"])
            rank_retention[str(r)][0] += 1
            if r >= 2:
                baseline_tail_hits += 1
        kept = [c for c in candidates if keep_candidate(c, rule)]
        if not kept:
            zero += 1
        displayed += len(kept)
        irrelevant += sum(c["concept_id"] != target for c in kept)
        if target_row and target_row in kept:
            retained_hits += 1
            r = int(target_row["rank"])
            rank_retention[str(r)][1] += 1
            if r >= 2:
                retained_tail_hits += 1

    n = len(rows)
    return {
        "queries": n,
        "baseline_hit5": baseline_hits,
        "retained_hit5": retained_hits,
        "hit5_retention": round(retained_hits / max(1, baseline_hits), 6),
        "baseline_tail_hits_rank2_5": baseline_tail_hits,
        "retained_tail_hits_rank2_5": retained_tail_hits,
        "tail_hit_retention": round(retained_tail_hits / max(1, baseline_tail_hits), 6),
        "mean_displayed": round(displayed / max(1, n), 6),
        "mean_irrelevant_displayed_exact_target_proxy": round(irrelevant / max(1, n), 6),
        "zero_result_rate": round(zero / max(1, n), 6),
        "rank_retention": {
            rank: {
                "baseline": values[0],
                "retained": values[1],
                "rate": round(values[1] / max(1, values[0]), 6),
            }
            for rank, values in rank_retention.items()
        },
    }


def choose_rule(calibration: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    # Frozen small grid. Objective: remove the most exact-target-negative visible
    # candidates while retaining >=98% of baseline Hit@5 AND >=98% of rank2-5 hits.
    ratios = [0.0, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75]
    coverages = [0.0, 0.10, 0.20, 0.30, 0.40]
    idf_coverages = [0.0, 0.10, 0.20, 0.30, 0.40]
    counts = [1, 2, 3]
    feasible: list[tuple[tuple[float, float, float, float], dict[str, Any], dict[str, Any]]] = []
    fallback: list[tuple[tuple[float, float, float], dict[str, Any], dict[str, Any]]] = []
    for ratio in ratios:
        for cov in coverages:
            for idf_cov in idf_coverages:
                for count in counts:
                    rule = {
                        "score_ratio_min": ratio,
                        "token_coverage_min": cov,
                        "idf_coverage_min": idf_cov,
                        "shared_count_min": count,
                    }
                    metrics = summarize_rule(calibration, rule)
                    # Primary objective: fewer irrelevant visible candidates, then shorter
                    # lists, then stronger retention. Tie-breakers prefer simpler/lower gates.
                    key = (
                        metrics["mean_irrelevant_displayed_exact_target_proxy"],
                        metrics["mean_displayed"],
                        -metrics["hit5_retention"],
                        ratio + cov + idf_cov + count / 10,
                    )
                    if metrics["hit5_retention"] >= 0.98 and metrics["tail_hit_retention"] >= 0.98:
                        feasible.append((key, rule, metrics))
                    fb_key = (
                        -min(metrics["hit5_retention"], metrics["tail_hit_retention"]),
                        metrics["mean_irrelevant_displayed_exact_target_proxy"],
                        metrics["mean_displayed"],
                    )
                    fallback.append((fb_key, rule, metrics))
    if feasible:
        feasible.sort(key=lambda x: x[0])
        _key, rule, metrics = feasible[0]
        return rule, {"constraint_feasible": True, "calibration": metrics}
    fallback.sort(key=lambda x: x[0])
    _key, rule, metrics = fallback[0]
    return rule, {"constraint_feasible": False, "calibration": metrics}


def baseline_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return summarize_rule(rows, {
        "score_ratio_min": 0.0,
        "token_coverage_min": 0.0,
        "idf_coverage_min": 0.0,
        "shared_count_min": 0,
    })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--teacher", default="research/enrichment/v31/gemma4-yv-a593/phrases.jsonl")
    ap.add_argument("--priority", default="research/evaluation/v31/p80-track2-priority-coverage.json")
    ap.add_argument("--a593-train", default="research/training/v31/a593-language-diversity-training-v0.jsonl")
    ap.add_argument("--p80-train", default="research/training/v31/p80-language-diversity-training-v0.jsonl")
    ap.add_argument("--rescue-train", default="research/training/v31/p80-source-thin-rescue-training-v0.jsonl")
    ap.add_argument("--a593-holdout", default="research/evaluation/v31/a593-language-diversity-holdout-v0.jsonl")
    ap.add_argument("--p80-holdout", default="research/evaluation/v31/p80-language-diversity-holdout-v0.jsonl")
    ap.add_argument("--rescue-holdout", default="research/evaluation/v31/p80-source-thin-rescue-holdout-v0.jsonl")
    ap.add_argument("--output", default="research/evaluation/v31/p80-display-relevance-calibration-v0.json")
    args = ap.parse_args()

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    wire = fetch(TAXONOMY_URL)
    if hashlib.sha256(wire).hexdigest() != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != EXPECTED_UNIVERSE:
        raise RuntimeError("candidate universe drift")

    priority = json.loads(Path(args.priority).read_text(encoding="utf-8"))
    existing_ids = {str(r["concept_id"]) for r in priority.get("existing_diversified_v0") or []}
    missing_ids = {str(r["concept_id"]) for r in priority.get("missing_diversified_v0") or []}
    if len(existing_ids | missing_ids) != 159:
        raise RuntimeError("P80 membership drift")

    _teacher_ids, base_teacher = load_teacher(Path(args.teacher))
    a593_train, _ = load_diverse_training(Path(args.a593_train))
    p80_train, _ = load_diverse_training(Path(args.p80_train))
    rescue_train, rescue_meta = load_diverse_training(Path(args.rescue_train))
    if len(rescue_meta) != 22:
        raise RuntimeError("rescue metadata drift")

    teacher = {cid: list(values) for cid, values in base_teacher.items()}
    add_teacher(teacher, a593_train, existing_ids)
    add_teacher(teacher, p80_train, missing_ids)
    add_teacher(teacher, rescue_train, existing_ids | missing_ids)
    ranker, exact, surfaces = build_ranker(by_id, ids, teacher)

    cases = load_cases(
        Path(args.a593_holdout), Path(args.p80_holdout), Path(args.rescue_holdout),
        existing_ids, missing_ids, a593_train, p80_train, rescue_train,
    )
    rows: list[dict[str, Any]] = []
    for case in cases:
        scored = rank_c1(ranker, case["query"], exact, surfaces)
        candidates = candidate_features(ranker, case["query"], scored)
        for c in candidates:
            c["is_target"] = c["concept_id"] == case["concept_id"]
        rows.append({**case, "candidates": candidates})

    calibration = [r for r in rows if r["split"] == "calibration"]
    evaluation = [r for r in rows if r["split"] == "evaluation"]
    if len(calibration) < 150 or len(evaluation) < 100:
        raise RuntimeError(f"calibration split too small: {len(calibration)}/{len(evaluation)}")

    selected_rule, selection = choose_rule(calibration)
    eval_baseline = baseline_metrics(evaluation)
    eval_gated = summarize_rule(evaluation, selected_rule)
    reduction = 1.0 - (
        eval_gated["mean_irrelevant_displayed_exact_target_proxy"]
        / max(1e-12, eval_baseline["mean_irrelevant_displayed_exact_target_proxy"])
    )
    # Decision gate is deliberately strict: preserve >=98% overall and rank2-5
    # baseline hits on untouched concepts while removing >=25% of visible exact-target
    # negatives. If this fails, simple existing-score calibration is not enough.
    passed = (
        selection["constraint_feasible"]
        and eval_gated["hit5_retention"] >= 0.98
        and eval_gated["tail_hit_retention"] >= 0.98
        and reduction >= 0.25
    )

    result = {
        "id": "YV-P80-display-relevance-calibration-v0",
        "evidence_class": "prefrozen model-authored P80 holdout calibration/evaluation; mechanism evidence only, not human relevance accuracy",
        "opened_17_88_loaded": False,
        "candidate_universe": 2105,
        "ranker_changed": False,
        "split": {
            "policy": f"concept-level SHA256 split, salt={SPLIT_SALT}, 60/40 calibration/evaluation",
            "calibration_queries": len(calibration),
            "evaluation_queries": len(evaluation),
            "calibration_concepts": len({r['concept_id'] for r in calibration}),
            "evaluation_concepts": len({r['concept_id'] for r in evaluation}),
        },
        "label_boundary": "Only the generating target identity is positive. Semantically acceptable siblings count as negatives; precision/removal metrics are therefore conservative proxies.",
        "separability": {
            "calibration_all_top5": separability(calibration, tail_only=False),
            "calibration_rank2_5": separability(calibration, tail_only=True),
            "evaluation_all_top5": separability(evaluation, tail_only=False),
            "evaluation_rank2_5": separability(evaluation, tail_only=True),
        },
        "rule_family": "per-candidate conjunction of score_ratio, query-token coverage, IDF-weighted query coverage, and shared-term count; no rank cutoff",
        "selection_constraint": "calibration Hit@5 retention >=98% AND calibration rank2-5 target retention >=98%; among feasible rules minimize visible exact-target negatives",
        "selected_rule": selected_rule,
        "calibration_selection": selection,
        "evaluation": {
            "baseline": eval_baseline,
            "gated": eval_gated,
            "irrelevant_candidate_reduction": round(reduction, 6),
        },
        "decision_gate": {
            "rule": "untouched evaluation: overall Hit@5 retention >=98%; rank2-5 target retention >=98%; >=25% exact-target-negative visible-candidate reduction",
            "passed": passed,
            "if_pass": "existing ranker signals are sufficient for a simple display/calibration layer; validate on human relevance when available before production promotion",
            "if_fail": "do not hide results with a cosmetic cutoff; existing ranker signals cannot safely distinguish enough relevant rank2-5 candidates from visible negatives, so test a bounded query-candidate relevance mechanism next",
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "split": result["split"],
        "selected_rule": selected_rule,
        "calibration": selection,
        "evaluation": result["evaluation"],
        "decision_gate": result["decision_gate"],
        "tail_separability": result["separability"]["evaluation_rank2_5"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
