#!/usr/bin/env python3
"""Evaluate an explicit source-bound pairwise contrast layer on frozen A593.

The relation-aware sparse lane establishes pair relevance. Gemma's source-bound
contrast note may only decide which member of an already-retrieved pair inherits the
higher of the pair's two base scores. It may not globally boost a pair.

Rule semantics:
- decisive_for_A/B: max cosine to that side's cue/description texts;
- shared_not_negative: if shared evidence is strongest, make no preference;
- ambiguous_do_not_force: distinguishable=false always makes no preference.

The pair set is A593-confusion-selected, so targeted teacher-holdout metrics are
strictly development evidence. Opened 17/88 queries are not read here.
"""
from __future__ import annotations

import argparse
import gzip
import json
import statistics
from pathlib import Path
from typing import Any

import evaluate_gemma_a593_hard_negative_distillation as hn
import evaluate_gemma_a593_relation_aware_negatives as rel
import evaluate_gemma_a593_sniper_contrasts as sniper
import evaluate_gemma_a593_sparse_paper_note as sparse

PHRASES_PER_CONCEPT = 8


def summarize(ranks: list[int]) -> dict[str, Any]:
    return {
        "cases": len(ranks),
        "top1_count": sum(r == 1 for r in ranks),
        "top1_rate": round(sum(r == 1 for r in ranks) / len(ranks), 6) if ranks else 0.0,
        "hit_at_5_count": sum(r <= 5 for r in ranks),
        "hit_at_5_rate": round(sum(r <= 5 for r in ranks) / len(ranks), 6) if ranks else 0.0,
        "mrr": round(sum(1.0 / r for r in ranks) / len(ranks), 6) if ranks else 0.0,
        "median_rank": statistics.median(ranks) if ranks else None,
    }


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(value * b.get(feature, 0.0) for feature, value in a.items())


def compile_rule(row: dict[str, Any], vocab, idf) -> dict[str, Any]:
    contrast = row["contrast"]
    vector = lambda text: sparse.tfidf_vector(str(text), vocab, idf)
    return {
        "a": str(row["a_concept_id"]),
        "b": str(row["b_concept_id"]),
        "distinguishable": bool(contrast["distinguishable"]),
        "a_vectors": [vector(text) for text in sniper.sniper_texts(row, "a")],
        "b_vectors": [vector(text) for text in sniper.sniper_texts(row, "b")],
        "shared_vectors": [vector(text) for text in contrast["shared_ambiguous"]],
    }


def compile_rules(rows, vocab, idf):
    rules = [compile_rule(row, vocab, idf) for row in rows]
    degree: dict[str, int] = {}
    for rule in rules:
        if not rule["distinguishable"]:
            continue
        for cid in (rule["a"], rule["b"]):
            degree[cid] = degree.get(cid, 0) + 1
    overlaps = {cid: count for cid, count in degree.items() if count > 1}
    if overlaps:
        raise RuntimeError(f"swap layer requires non-overlapping distinguishable pairs: {overlaps}")
    return rules


def max_similarity(q, vectors) -> float:
    return max((cosine(q, vector) for vector in vectors), default=0.0)


def decide(q, rule):
    if not rule["distinguishable"]:
        return "neutral", {"a": 0.0, "b": 0.0, "shared": 0.0}
    a = max_similarity(q, rule["a_vectors"])
    b = max_similarity(q, rule["b_vectors"])
    shared = max_similarity(q, rule["shared_vectors"])
    if a > b and a > shared:
        return "a", {"a": a, "b": b, "shared": shared}
    if b > a and b > shared:
        return "b", {"a": a, "b": b, "shared": shared}
    return "neutral", {"a": a, "b": b, "shared": shared}


def apply_pair_swaps(base_scores, q, rules):
    scores = dict(base_scores)
    decisions = []
    for rule in rules:
        decision, sims = decide(q, rule)
        a, b = rule["a"], rule["b"]
        before_a, before_b = scores.get(a, 0.0), scores.get(b, 0.0)
        changed = False
        if decision != "neutral" and (before_a > 0.0 or before_b > 0.0):
            high, low = max(before_a, before_b), min(before_a, before_b)
            after_a, after_b = ((high, low) if decision == "a" else (low, high))
            changed = (after_a, after_b) != (before_a, before_b)
            scores[a], scores[b] = after_a, after_b
        decisions.append({
            "a": a,
            "b": b,
            "decision": decision,
            "similarities": sims,
            "changed_pair_scores": changed,
        })
    return scores, decisions


def build_fold(cids, phrases, slots, rows):
    docs = [phrases[cid][slot] for cid in cids for slot in slots]
    base_vocab, base_idf = sparse.fit_idf(docs)
    positive = sparse.full_centroids(cids, phrases, slots, base_vocab, base_idf)
    protected, _ = rel.protected_neighbors(cids, positive)
    negative, _counts, hubs, _pairs, _skipped = rel.mine_relation_aware(
        cids, phrases, slots, base_vocab, base_idf, positive, protected
    )
    incumbent_float = hn.contrastive_centroids(positive, negative, hubs, rel.ALPHA)
    weights = hn.prune_quantize_signedless(incumbent_float)
    vocab, idf = sniper.extend_idf(base_vocab, base_idf, len(docs), rows)
    return base_vocab, base_idf, weights, vocab, idf, compile_rules(rows, vocab, idf)


def rule_guard(rows, vocab, idf, rules):
    by_pair = {(rule["a"], rule["b"]): rule for rule in rules}
    shared, decisive, indistinguishable = [], [], []
    for row in rows:
        key = (str(row["a_concept_id"]), str(row["b_concept_id"]))
        rule = by_pair[key]
        contrast = row["contrast"]
        for text in contrast["shared_ambiguous"]:
            decision, sims = decide(sparse.tfidf_vector(str(text), vocab, idf), rule)
            shared.append({"a": key[0], "b": key[1], "text": text, "decision": decision, "similarities": sims})
        if contrast["distinguishable"]:
            for side in ("a", "b"):
                for text in sniper.sniper_texts(row, side):
                    decision, sims = decide(sparse.tfidf_vector(str(text), vocab, idf), rule)
                    decisive.append({"a": key[0], "b": key[1], "expected": side, "text": text, "decision": decision, "similarities": sims})
        else:
            for text in contrast["shared_ambiguous"]:
                decision, sims = decide(sparse.tfidf_vector(str(text), vocab, idf), rule)
                indistinguishable.append({"a": key[0], "b": key[1], "text": text, "decision": decision, "similarities": sims})
    return {
        "shared": {"cases": len(shared), "neutral_count": sum(x["decision"] == "neutral" for x in shared), "details": shared},
        "decisive": {
            "cases": len(decisive),
            "correct_side_count": sum(x["decision"] == x["expected"] for x in decisive),
            "neutral_count": sum(x["decision"] == "neutral" for x in decisive),
            "wrong_side_count": sum(x["decision"] not in {x["expected"], "neutral"} for x in decisive),
            "details": decisive,
        },
        "indistinguishable": {
            "cases": len(indistinguishable),
            "neutral_count": sum(x["decision"] == "neutral" for x in indistinguishable),
            "details": indistinguishable,
        },
    }


def runtime_rule_blob(rows):
    compiled = []
    for row in rows:
        c = row["contrast"]
        compiled.append({
            "distinguishable": bool(c["distinguishable"]),
            "a": {"id": str(row["a_concept_id"]), "texts": sniper.sniper_texts(row, "a")},
            "b": {"id": str(row["b_concept_id"]), "texts": sniper.sniper_texts(row, "b")},
            "shared": [str(x) for x in c["shared_ambiguous"]],
        })
    raw = json.dumps(compiled, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"pairs": len(compiled), "raw_bytes": len(raw), "gzip9_bytes": len(gzip.compress(raw, compresslevel=9))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--sniper", default="research/training/v31/a593-gemma4-sniper-contrasts-v0.jsonl")
    ap.add_argument("--relation-result", default="research/evaluation/v31/compile-time-semantic-a593-relation-aware-negatives.json")
    ap.add_argument("--output", default="artifacts/a593-explicit-contrast-layer.json")
    args = ap.parse_args()

    cids, phrases = sparse.load_teacher(Path(args.teacher))
    rows = sniper.load_sniper(Path(args.sniper))
    relation_result = json.loads(Path(args.relation_result).read_text(encoding="utf-8"))
    frozen_inc = relation_result["selected_metrics"]
    targeted = {
        cid for row in rows if row["contrast"]["distinguishable"]
        for cid in (str(row["a_concept_id"]), str(row["b_concept_id"]))
    }

    control_all, challenger_all = [], []
    control_targeted, challenger_targeted = [], []
    per_concept = {cid: {"control": [], "challenger": []} for cid in targeted}
    activation = {"a": 0, "b": 0, "neutral": 0, "changed_pair_scores": 0}

    for holdout in range(PHRASES_PER_CONCEPT):
        slots = [slot for slot in range(PHRASES_PER_CONCEPT) if slot != holdout]
        base_vocab, base_idf, weights, contrast_vocab, contrast_idf, rules = build_fold(cids, phrases, slots, rows)
        inv = hn.inverted(weights)
        for target in cids:
            query = phrases[target][holdout]
            base_q = sparse.tfidf_vector(query, base_vocab, base_idf)
            base_scores = hn.scores_for(base_q, inv)
            control_order = hn.ranked(cids, base_scores)
            contrast_q = sparse.tfidf_vector(query, contrast_vocab, contrast_idf)
            adjusted, decisions = apply_pair_swaps(base_scores, contrast_q, rules)
            challenger_order = hn.ranked(cids, adjusted)
            cr, rr = control_order.index(target) + 1, challenger_order.index(target) + 1
            control_all.append(cr)
            challenger_all.append(rr)
            for item in decisions:
                activation[item["decision"]] += 1
                activation["changed_pair_scores"] += int(item["changed_pair_scores"])
            if target in targeted:
                control_targeted.append(cr)
                challenger_targeted.append(rr)
                per_concept[target]["control"].append(cr)
                per_concept[target]["challenger"].append(rr)

    control_metrics = summarize(control_all)
    if (control_metrics["top1_count"], control_metrics["hit_at_5_count"], control_metrics["mrr"]) != (
        frozen_inc["top1_count"], frozen_inc["hit_at_5_count"], frozen_inc["mrr"]
    ):
        raise RuntimeError(f"relation-aware incumbent parity failed: {control_metrics} != {frozen_inc}")

    challenger_metrics = summarize(challenger_all)
    targeted_control = summarize(control_targeted)
    targeted_challenger = summarize(challenger_targeted)

    docs = [phrases[cid][slot] for cid in cids for slot in range(PHRASES_PER_CONCEPT)]
    base_vocab, base_idf = sparse.fit_idf(docs)
    guard_vocab, guard_idf = sniper.extend_idf(base_vocab, base_idf, len(docs), rows)
    guard = rule_guard(rows, guard_vocab, guard_idf, compile_rules(rows, guard_vocab, guard_idf))

    pair_deltas = []
    for row in rows:
        if not row["contrast"]["distinguishable"]:
            continue
        a, b = str(row["a_concept_id"]), str(row["b_concept_id"])
        before = per_concept[a]["control"] + per_concept[b]["control"]
        after = per_concept[a]["challenger"] + per_concept[b]["challenger"]
        pair_deltas.append({
            "a_concept_id": a,
            "a_label": row.get("a_label"),
            "b_concept_id": b,
            "b_label": row.get("b_label"),
            "cases": len(before),
            "top1_delta": sum(r == 1 for r in after) - sum(r == 1 for r in before),
            "hit5_delta": sum(r <= 5 for r in after) - sum(r <= 5 for r in before),
            "mrr_delta": round(sum(1/r for r in after)/len(after) - sum(1/r for r in before)/len(before), 6),
        })
    pair_deltas.sort(key=lambda x: (-x["mrr_delta"], -x["hit5_delta"], -x["top1_delta"], x["a_concept_id"]))

    gate = (
        challenger_metrics["hit_at_5_count"] >= control_metrics["hit_at_5_count"]
        and challenger_metrics["mrr"] >= control_metrics["mrr"]
        and targeted_challenger["mrr"] > targeted_control["mrr"]
        and (
            targeted_challenger["top1_count"] > targeted_control["top1_count"]
            or targeted_challenger["hit_at_5_count"] > targeted_control["hit_at_5_count"]
        )
        and guard["shared"]["neutral_count"] == guard["shared"]["cases"]
        and guard["indistinguishable"]["neutral_count"] == guard["indistinguishable"]["cases"]
    )

    result = {
        "schema_version": 1,
        "status": "A593 explicit source-bound pairwise contrast-layer development diagnostic; no opened 17/88 queries read",
        "candidate": {
            "id": "YV-A593-explicit-pair-contrast-v0",
            "base": "relation-aware clamped hard-negative alpha=0.75",
            "mechanism": "base sparse lane determines pair relevance; contrast rule may only swap the pair's two existing base scores",
            "decision_rule": "prefer A iff decisive_A similarity is strictly greater than both decisive_B and shared; symmetric for B; otherwise neutral",
            "numeric_pair_boost": False,
            "global_concept_weight_mutation": False,
            "teacher_dependency_at_runtime": False,
        },
        "training_data": {
            "pairs_total": len(rows),
            "pairs_distinguishable": sum(bool(row["contrast"]["distinguishable"]) for row in rows),
            "pairs_indistinguishable": sum(not bool(row["contrast"]["distinguishable"]) for row in rows),
            "targeted_concepts": len(targeted),
        },
        "all_4744": {"control": control_metrics, "challenger": challenger_metrics},
        "targeted_teacher_holdouts": {"control": targeted_control, "challenger": targeted_challenger},
        "delta_all_vs_control": {
            "top1_count": challenger_metrics["top1_count"] - control_metrics["top1_count"],
            "hit_at_5_count": challenger_metrics["hit_at_5_count"] - control_metrics["hit_at_5_count"],
            "mrr": round(challenger_metrics["mrr"] - control_metrics["mrr"], 6),
        },
        "delta_targeted_vs_control": {
            "top1_count": targeted_challenger["top1_count"] - targeted_control["top1_count"],
            "hit_at_5_count": targeted_challenger["hit_at_5_count"] - targeted_control["hit_at_5_count"],
            "mrr": round(targeted_challenger["mrr"] - targeted_control["mrr"], 6),
        },
        "activation": activation,
        "rule_guard": guard,
        "pair_deltas": pair_deltas,
        "runtime_rule_blob": runtime_rule_blob(rows),
        "opened_replay_gate_passed": gate,
        "guard": "Pair selection is A593 confusion-selected. This run uses only frozen A593 teacher phrases plus source-bound sniper notes. Opened 17/88 may be replayed only after this fixed gate.",
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "delta_all_vs_control": result["delta_all_vs_control"],
        "delta_targeted_vs_control": result["delta_targeted_vs_control"],
        "opened_replay_gate_passed": gate,
        "runtime_rule_blob": result["runtime_rule_blob"],
        "rule_guard": {
            "shared": {k: v for k, v in guard["shared"].items() if k != "details"},
            "decisive": {k: v for k, v in guard["decisive"].items() if k != "details"},
            "indistinguishable": {k: v for k, v in guard["indistinguishable"].items() if k != "details"},
        },
        "best_pair_deltas": pair_deltas[:6],
        "worst_pair_deltas": pair_deltas[-6:],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
