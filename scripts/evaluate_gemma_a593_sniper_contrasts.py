#!/usr/bin/env python3
"""Evaluate bounded Gemma sniper-contrast training data on A593.

The sniper pair set is development-selected from the frozen A593 confusion inventory,
so targeted holdout metrics are training-distribution diagnostics, not independent
accuracy. The sniper text itself is generated only from public canonical taxonomy
evidence and never from A593 teacher phrases or opened 17/88 queries.

Fixed challenger: start from the frozen relation-aware clamped hard-negative model and,
for distinguishable sniper pairs only, apply

    concept := concept + 0.50 * own_sniper_prototype - 0.25 * opposite_prototype

then clamp at zero, L2-normalize, prune top300 and uint8-quantize. No sweep.
Shared/ambiguous sniper descriptions are never training input; they are a separate guard.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
from pathlib import Path
from typing import Any

import evaluate_gemma_a593_hard_negative_distillation as hn
import evaluate_gemma_a593_relation_aware_negatives as rel
import evaluate_gemma_a593_signed_context_sparse as sc
import evaluate_gemma_a593_sparse_paper_note as sparse

PHRASES_PER_CONCEPT = 8
TOPK = 300
OWN_BETA = 0.50
OPPOSITE_GAMMA = 0.25


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


def load_sniper(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise RuntimeError("empty sniper training file")
    seen = set()
    for row in rows:
        pair = frozenset((str(row["a_concept_id"]), str(row["b_concept_id"])))
        if len(pair) != 2 or pair in seen:
            raise RuntimeError("duplicate/invalid sniper pair")
        seen.add(pair)
    return rows


def sniper_texts(row: dict[str, Any], side: str) -> list[str]:
    c = row["contrast"]
    return [str(x) for x in c[f"{side}_cues"] + c[f"{side}_descriptions"]]


def extend_idf(base_vocab, base_idf, base_document_count: int, rows: list[dict[str, Any]]):
    docs = []
    for row in rows:
        if not row["contrast"]["distinguishable"]:
            continue
        docs.extend(sniper_texts(row, "a"))
        docs.extend(sniper_texts(row, "b"))
    df = collections.Counter()
    for text in docs:
        df.update(set(sparse.char_wb_ngrams(text)))
    vocab = set(base_vocab) | set(df)
    idf = dict(base_idf)
    total_docs = base_document_count + len(docs)
    for feature, count in df.items():
        if feature not in idf:
            idf[feature] = math.log((1 + total_docs) / (1 + count)) + 1.0
    return vocab, idf


def prototype(texts: list[str], vocab, idf):
    values = collections.defaultdict(float)
    for text in texts:
        for feature, value in sparse.tfidf_vector(text, vocab, idf).items():
            values[feature] += value
    norm = math.sqrt(sum(v * v for v in values.values()))
    return ({feature: value / norm for feature, value in values.items()} if norm else {})


def apply_sniper(base: dict[str, dict[str, float]], rows, vocab, idf):
    adjusted = {cid: dict(values) for cid, values in base.items()}
    for row in rows:
        if not row["contrast"]["distinguishable"]:
            continue
        a, b = str(row["a_concept_id"]), str(row["b_concept_id"])
        ap = prototype(sniper_texts(row, "a"), vocab, idf)
        bp = prototype(sniper_texts(row, "b"), vocab, idf)
        for cid, own, opposite in ((a, ap, bp), (b, bp, ap)):
            current = adjusted[cid]
            features = set(current) | set(own) | set(opposite)
            values = {
                f: max(0.0, current.get(f, 0.0) + OWN_BETA * own.get(f, 0.0) - OPPOSITE_GAMMA * opposite.get(f, 0.0))
                for f in features
            }
            values = {f: v for f, v in values.items() if v > 0.0}
            norm = math.sqrt(sum(v * v for v in values.values()))
            adjusted[cid] = ({f: v / norm for f, v in values.items()} if norm else {})
    return adjusted


def rank_queries(cids, phrases, holdout, vocab, idf, weights):
    inv = hn.inverted(weights)
    ranks = {}
    for target in cids:
        q = sparse.tfidf_vector(phrases[target][holdout], vocab, idf)
        order = hn.ranked(cids, hn.scores_for(q, inv))
        ranks[target] = order.index(target) + 1
    return ranks


def build_fold(cids, phrases, slots, rows):
    docs = [phrases[cid][slot] for cid in cids for slot in slots]
    base_vocab, base_idf = sparse.fit_idf(docs)
    positive = sparse.full_centroids(cids, phrases, slots, base_vocab, base_idf)
    protected, _ = rel.protected_neighbors(cids, positive)
    negative, _counts, hubs, _pairs, _skipped = rel.mine_relation_aware(cids, phrases, slots, base_vocab, base_idf, positive, protected)
    incumbent_float = hn.contrastive_centroids(positive, negative, hubs, rel.ALPHA)
    incumbent_q = hn.prune_quantize_signedless(incumbent_float)

    vocab, idf = extend_idf(base_vocab, base_idf, len(docs), rows)
    sniper_float = apply_sniper(incumbent_float, rows, vocab, idf)
    sniper_q = hn.prune_quantize_signedless(sniper_float)
    return base_vocab, base_idf, incumbent_q, vocab, idf, sniper_q


def full_candidate(cids, phrases, rows):
    slots = list(range(PHRASES_PER_CONCEPT))
    docs = [phrases[cid][slot] for cid in cids for slot in slots]
    base_vocab, base_idf = sparse.fit_idf(docs)
    positive = sparse.full_centroids(cids, phrases, slots, base_vocab, base_idf)
    protected, _ = rel.protected_neighbors(cids, positive)
    negative, _counts, hubs, _pairs, _skipped = rel.mine_relation_aware(cids, phrases, slots, base_vocab, base_idf, positive, protected)
    incumbent_float = hn.contrastive_centroids(positive, negative, hubs, rel.ALPHA)
    vocab, idf = extend_idf(base_vocab, base_idf, len(docs), rows)
    sniper_float = apply_sniper(incumbent_float, rows, vocab, idf)
    sniper_q = hn.prune_quantize_signedless(sniper_float)
    return vocab, idf, sniper_q


def ambiguous_guard(cids, rows, vocab, idf, weights):
    inv = hn.inverted(weights)
    cases = []
    for row in rows:
        a, b = str(row["a_concept_id"]), str(row["b_concept_id"])
        for text in row["contrast"]["shared_ambiguous"]:
            q = sparse.tfidf_vector(str(text), vocab, idf)
            scores = hn.scores_for(q, inv)
            order = hn.ranked(cids, scores)
            ar, br = order.index(a) + 1, order.index(b) + 1
            cases.append({
                "a_concept_id": a,
                "b_concept_id": b,
                "text": text,
                "a_rank": ar,
                "b_rank": br,
                "top1_concept_id": order[0],
                "top1_in_pair": order[0] in {a, b},
                "at_least_one_pair_top5": min(ar, br) <= 5,
                "both_pair_top5": max(ar, br) <= 5,
            })
    return {
        "cases": len(cases),
        "top1_in_pair_count": sum(x["top1_in_pair"] for x in cases),
        "at_least_one_pair_top5_count": sum(x["at_least_one_pair_top5"] for x in cases),
        "both_pair_top5_count": sum(x["both_pair_top5"] for x in cases),
        "details": cases,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--sniper", default="research/training/v31/a593-gemma4-sniper-contrasts-v0.jsonl")
    ap.add_argument("--relation-result", default="research/evaluation/v31/compile-time-semantic-a593-relation-aware-negatives.json")
    ap.add_argument("--output", default="artifacts/a593-sniper-contrast-diagnostic.json")
    args = ap.parse_args()

    cids, phrases = sparse.load_teacher(Path(args.teacher))
    rows = load_sniper(Path(args.sniper))
    relation_result = json.loads(Path(args.relation_result).read_text(encoding="utf-8"))
    frozen_inc = relation_result["selected_metrics"]
    targeted = {
        cid for row in rows if row["contrast"]["distinguishable"]
        for cid in (str(row["a_concept_id"]), str(row["b_concept_id"]))
    }

    control_all, sniper_all = [], []
    control_targeted, sniper_targeted = [], []
    per_concept = {cid: {"control": [], "sniper": []} for cid in targeted}

    for holdout in range(PHRASES_PER_CONCEPT):
        slots = [slot for slot in range(PHRASES_PER_CONCEPT) if slot != holdout]
        base_vocab, base_idf, incumbent_q, vocab, idf, sniper_q = build_fold(cids, phrases, slots, rows)
        control = rank_queries(cids, phrases, holdout, base_vocab, base_idf, incumbent_q)
        # Control parity under extended query feature space: added features have no control weights.
        control_ext = rank_queries(cids, phrases, holdout, vocab, idf, incumbent_q)
        if control != control_ext:
            raise RuntimeError("extended-vocabulary control changed ranking")
        sniper = rank_queries(cids, phrases, holdout, vocab, idf, sniper_q)
        for cid in cids:
            control_all.append(control[cid])
            sniper_all.append(sniper[cid])
            if cid in targeted:
                control_targeted.append(control[cid])
                sniper_targeted.append(sniper[cid])
                per_concept[cid]["control"].append(control[cid])
                per_concept[cid]["sniper"].append(sniper[cid])

    control_metrics = summarize(control_all)
    if (control_metrics["top1_count"], control_metrics["hit_at_5_count"], control_metrics["mrr"]) != (
        frozen_inc["top1_count"], frozen_inc["hit_at_5_count"], frozen_inc["mrr"]
    ):
        raise RuntimeError(f"relation-aware incumbent parity failed: {control_metrics} != {frozen_inc}")

    sniper_metrics = summarize(sniper_all)
    target_control = summarize(control_targeted)
    target_sniper = summarize(sniper_targeted)
    gate = (
        sniper_metrics["hit_at_5_count"] >= control_metrics["hit_at_5_count"]
        and sniper_metrics["mrr"] >= control_metrics["mrr"]
        and target_sniper["mrr"] > target_control["mrr"]
        and (target_sniper["top1_count"] > target_control["top1_count"] or target_sniper["hit_at_5_count"] > target_control["hit_at_5_count"])
    )

    pair_deltas = []
    for row in rows:
        a, b = str(row["a_concept_id"]), str(row["b_concept_id"])
        if a not in targeted or b not in targeted:
            continue
        before = per_concept[a]["control"] + per_concept[b]["control"]
        after = per_concept[a]["sniper"] + per_concept[b]["sniper"]
        pair_deltas.append({
            "a_concept_id": a,
            "a_label": row.get("a_label"),
            "b_concept_id": b,
            "b_label": row.get("b_label"),
            "cases": len(before),
            "control_mrr": round(sum(1/r for r in before)/len(before), 6),
            "sniper_mrr": round(sum(1/r for r in after)/len(after), 6),
            "top1_delta": sum(r == 1 for r in after) - sum(r == 1 for r in before),
            "hit5_delta": sum(r <= 5 for r in after) - sum(r <= 5 for r in before),
        })
    pair_deltas.sort(key=lambda x: (-(x["sniper_mrr"]-x["control_mrr"]), -x["hit5_delta"], -x["top1_delta"], x["a_concept_id"]))

    vocab, idf, full_q = full_candidate(cids, phrases, rows)
    artifact = sc.runtime_blob(cids, idf, full_q, signed=False)
    guard = ambiguous_guard(cids, rows, vocab, idf, full_q)

    result = {
        "schema_version": 1,
        "status": "A593 sniper-contrast development diagnostic; pair selection is confusion-selected and not independent accuracy evidence",
        "fixed_design": {
            "base": "relation-aware clamped hard-negative alpha=0.75",
            "own_sniper_beta": OWN_BETA,
            "opposite_sniper_gamma": OPPOSITE_GAMMA,
            "clamp_negative_weights_to_zero": True,
            "topk_features_per_concept": TOPK,
            "no_parameter_sweep": True,
            "shared_ambiguous_used_for_training": False,
        },
        "training_data": {
            "pairs_total": len(rows),
            "pairs_distinguishable": sum(bool(r["contrast"]["distinguishable"]) for r in rows),
            "pairs_indistinguishable": sum(not bool(r["contrast"]["distinguishable"]) for r in rows),
            "targeted_concepts": len(targeted),
        },
        "all_4744": {"control": control_metrics, "sniper": sniper_metrics},
        "targeted_teacher_holdouts": {"control": target_control, "sniper": target_sniper},
        "delta_all_vs_control": {
            "top1_count": sniper_metrics["top1_count"] - control_metrics["top1_count"],
            "hit_at_5_count": sniper_metrics["hit_at_5_count"] - control_metrics["hit_at_5_count"],
            "mrr": round(sniper_metrics["mrr"] - control_metrics["mrr"], 6),
        },
        "delta_targeted_vs_control": {
            "top1_count": target_sniper["top1_count"] - target_control["top1_count"],
            "hit_at_5_count": target_sniper["hit_at_5_count"] - target_control["hit_at_5_count"],
            "mrr": round(target_sniper["mrr"] - target_control["mrr"], 6),
        },
        "opened_replay_gate_passed": gate,
        "pair_deltas": pair_deltas,
        "ambiguous_shared_guard": guard,
        "selected_candidate": {
            "id": "YV-A593-relation-aware-sniper-v0",
            "runtime_shape": "char3/4 TF-IDF + uint8 sparse concept weights; pair-specific source-grounded contrast distilled compile-time",
            "artifact": artifact,
            "teacher_dependency_at_runtime": False,
        },
        "guard": "Sniper pair selection is A593 confusion-selected, so targeted teacher-holdout gains are development evidence. No opened 17/88 query participates in generation or candidate selection; replay them only after this fixed candidate passes the prefrozen gate.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "training_data": result["training_data"],
        "delta_all_vs_control": result["delta_all_vs_control"],
        "delta_targeted_vs_control": result["delta_targeted_vs_control"],
        "opened_replay_gate_passed": gate,
        "artifact": artifact,
        "ambiguous_shared_guard": {k:v for k,v in guard.items() if k != "details"},
        "best_pair_deltas": pair_deltas[:6],
        "worst_pair_deltas": pair_deltas[-6:],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
