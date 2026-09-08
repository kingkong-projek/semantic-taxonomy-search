#!/usr/bin/env python3
"""Opened replay of the prefrozen A593 hard-negative sparse candidate.

The alpha=0.75 feature-discount variant was selected only from the frozen 4,744
Gemma-authored outer-fold holdouts. No opened 17/88 query is used to fit or select
weights here.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

import evaluate_gemma_a149 as base
import evaluate_gemma_a593_sparse_paper_note as sparse
import evaluate_gemma_a593_hard_negative_distillation as hn
from evaluate_p80_lexical_ablation import expected_hash, fetch
from evaluate_yv_full_description_canonical import SOURCE_URL

ALPHA = 0.75
TOPK = 300
CANDIDATE_ID = "YV-A593-char34-centroid-u8-top300-hardneg-a075-v0"


def build_lane(cids, phrases):
    slots = list(range(8))
    documents = [phrases[cid][slot] for cid in cids for slot in slots]
    vocab, idf = sparse.fit_idf(documents)
    positive = sparse.full_centroids(cids, phrases, slots, vocab, idf)
    negative, counts, hubs, pairs = hn.mine_negative_profiles(
        cids, phrases, slots, vocab, idf, positive
    )
    adjusted = hn.contrastive_centroids(positive, negative, hubs, ALPHA)
    quantized, _ = sparse.prune_quantize(adjusted, TOPK)
    inv = hn.inverted(quantized)
    return vocab, idf, inv, counts, pairs


def rank_query(query, cids, vocab, idf, inv):
    q = sparse.tfidf_vector(query, vocab, idf)
    if not q:
        return []
    scores = hn.scores_for(q, inv)
    order = hn.ranked(cids, scores)
    return [cid for cid in order if scores.get(cid, 0.0) > 0.0]


def targetable(summary):
    cats = summary["categories"]
    names = ("direct", "colloquial", "noisy", "indirect")
    return {
        "cases": 40,
        "top1_family_hit": sum(cats[n]["top1_family_hit"] for n in names),
        "top5_family_hit": sum(cats[n]["top5_family_hit"] for n in names),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--hard-negative", default="research/evaluation/v31/compile-time-semantic-a593-hard-negative-distillation.json")
    ap.add_argument("--char-replay", default="research/evaluation/v31/compile-time-semantic-tournament-a593-char-centroid.json")
    ap.add_argument("--raw-a593", default="research/evaluation/v31/compile-time-semantic-tournament-a593.json")
    ap.add_argument("--snowball", default="research/evaluation/v31/compile-time-semantic-tournament-a593-snowball.json")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--output", default="artifacts/a593-hard-negative-opened-replay.json")
    args = ap.parse_args()

    frozen = json.loads(Path(args.hard_negative).read_text(encoding="utf-8"))
    if frozen["selected_variant"] != "hard_negative_discount_alpha_0.75":
        raise RuntimeError("hard-negative selection drift")
    cids, phrases = sparse.load_teacher(Path(args.teacher))
    vocab, idf, inv, counts, pairs = build_lane(cids, phrases)

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    taxonomy_url = "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json"
    taxonomy_wire = fetch(taxonomy_url)
    if hashlib.sha256(taxonomy_wire).hexdigest() != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    taxonomy = json.loads(taxonomy_wire)
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active_occ = {cid for cid, c in by_id.items() if c.get("type") == "occupation-name"}
    if len(active_occ) != 2105 or not set(cids) <= active_occ:
        raise RuntimeError("occupation universe drift")

    source_wire = fetch(SOURCE_URL)
    if hashlib.sha256(source_wire).hexdigest() != expected_hash(registry, "occupational-information"):
        raise RuntimeError("occupational-information source drift")
    strict = base.strict_source_cases(json.loads(source_wire), by_id, active_occ)
    strict_ranked = [rank_query(row["query"], cids, vocab, idf, inv) for row in strict]
    strict_all = base.rank_metrics(strict, strict_ranked)
    covered = [row for row in strict if row["target_id"] in set(cids)]
    strict_cov = base.rank_metrics(
        covered, [rank_query(row["query"], cids, vocab, idf, inv) for row in covered]
    )

    stress = json.loads(Path(args.stress).read_text(encoding="utf-8"))
    yv = stress.get("yv") or []
    if len(yv) != 54:
        raise RuntimeError("stress suite drift")
    stress_result = base.stress_summary(
        yv, by_id, [rank_query(str(row["query"]), cids, vocab, idf, inv) for row in yv]
    )

    char = json.loads(Path(args.char_replay).read_text(encoding="utf-8"))
    raw = json.loads(Path(args.raw_a593).read_text(encoding="utf-8"))
    snow = json.loads(Path(args.snowball).read_text(encoding="utf-8"))
    result = {
        "schema_version": 1,
        "status": "opened replay of prefrozen A593 hard-negative sparse semantic lane; no runtime promotion",
        "candidate": {
            "id": CANDIDATE_ID,
            "base": "YV-A593-char34-centroid-u8-top300-v0",
            "alpha": ALPHA,
            "topk_features_per_concept": TOPK,
            "runtime_shape": "char_wb 3/4-gram TF-IDF + uint8 sparse concept weights; hard-negative intelligence compiled into weights",
            "teacher_dependency_at_runtime": False,
        },
        "selection_evidence": frozen["selected_metrics"],
        "lane_boundary": "standalone 593-occupation semantic description lane; ordinary YV lexical lookup remains separate",
        "strict_source_attested_17": {
            "hard_negative_all17": strict_all,
            "hard_negative_teacher_covered_only": strict_cov,
        },
        "opened_stress_54": {
            "hard_negative": stress_result,
            "targetable40": targetable(stress_result),
            "char_centroid_targetable40": char["opened_stress_54"]["targetable40"],
            "raw_a593_targetable40": targetable(raw["opened_stress_54"]["gemma_a593"]),
            "snowball_a593_targetable40": targetable(snow["opened_stress_54"]["gemma_a593_snowball"]),
        },
        "training_hard_negative_summary": {
            "false_candidate_assignments": sum(counts.values()),
            "unique_directed_pairs": len(pairs),
        },
        "evidence_warning": "alpha=0.75 was frozen using only Gemma-authored outer-fold evidence before this replay. Opened outcomes are diagnostic only and must not tune alpha or features.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "targetable40": result["opened_stress_54"]["targetable40"],
        "strict17": {k: v for k, v in strict_all.items() if k != "rows"},
        "strict_covered": {k: v for k, v in strict_cov.items() if k != "rows"},
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
