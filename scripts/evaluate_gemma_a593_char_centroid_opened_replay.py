#!/usr/bin/env python3
"""Opened diagnostic replay of prefrozen A593 char34 centroid top300.

Candidate selection happened entirely on the frozen 4,744 Gemma phrase holdouts.
This script performs no tuning. It evaluates the selected sparse semantic lane as a
standalone description retriever over the 593 teacher-covered occupations. Ordinary
YV lexical lookup remains a separate privileged product path.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

import evaluate_gemma_a149 as base
import evaluate_gemma_a593_sparse_paper_note as sparse
from evaluate_p80_lexical_ablation import expected_hash, fetch
from evaluate_yv_full_description_canonical import SOURCE_URL

TOPK = 300
CANDIDATE_ID = "YV-A593-char34-centroid-u8-top300-v0"


def build_semantic_lane(cids, phrases):
    documents = [phrase for cid in cids for phrase in phrases[cid]]
    vocab, idf = sparse.fit_idf(documents)
    centroids = sparse.full_centroids(cids, phrases, list(range(8)), vocab, idf)
    quantized, _ = sparse.prune_quantize(centroids, TOPK)
    inverted = collections.defaultdict(list)
    for cid, values in quantized.items():
        for feature, weight in values.items():
            inverted[feature].append((cid, weight))
    return vocab, idf, inverted


def rank_query(query, cids, vocab, idf, inverted):
    q = sparse.tfidf_vector(query, vocab, idf)
    if not q:
        return []
    scores = collections.defaultdict(float)
    for feature, q_weight in q.items():
        for cid, c_weight in inverted.get(feature, ()):
            scores[cid] += q_weight * c_weight
    ranked = [(score, cid) for cid, score in scores.items() if score > 0.0]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [cid for _, cid in ranked]


def compact_targetable(summary):
    cats = summary["categories"]
    names = ("direct", "colloquial", "noisy", "indirect")
    return {
        "cases": sum(cats[name]["target_cases"] for name in names),
        "top1_family_hit": sum(cats[name]["top1_family_hit"] for name in names),
        "top5_family_hit": sum(cats[name]["top5_family_hit"] for name in names),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--selected", default="research/evaluation/v31/compile-time-semantic-a593-sparse-paper-note.json")
    ap.add_argument("--raw-a593", default="research/evaluation/v31/compile-time-semantic-tournament-a593.json")
    ap.add_argument("--snowball", default="research/evaluation/v31/compile-time-semantic-tournament-a593-snowball.json")
    ap.add_argument("--output", default="artifacts/a593-char-centroid-opened-replay.json")
    args = ap.parse_args()

    selected = json.loads(Path(args.selected).read_text(encoding="utf-8"))
    if selected["selected_candidate"]["id"] != CANDIDATE_ID:
        raise RuntimeError("selected candidate drift")

    cids, phrases = sparse.load_teacher(Path(args.teacher))
    vocab, idf, inverted = build_semantic_lane(cids, phrases)

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
    strict_ranked = [rank_query(row["query"], cids, vocab, idf, inverted) for row in strict]
    strict_all = base.rank_metrics(strict, strict_ranked)
    strict_covered_cases = [row for row in strict if row["target_id"] in set(cids)]
    strict_covered_ranked = [rank_query(row["query"], cids, vocab, idf, inverted) for row in strict_covered_cases]
    strict_covered = base.rank_metrics(strict_covered_cases, strict_covered_ranked)

    stress = json.loads(Path(args.stress).read_text(encoding="utf-8"))
    yv = stress.get("yv") or []
    if len(yv) != 54:
        raise RuntimeError("stress suite drift")
    ranked = [rank_query(str(case["query"]), cids, vocab, idf, inverted) for case in yv]
    stress_result = base.stress_summary(yv, by_id, ranked)

    raw = json.loads(Path(args.raw_a593).read_text(encoding="utf-8"))
    snow = json.loads(Path(args.snowball).read_text(encoding="utf-8"))
    result = {
        "schema_version": 1,
        "status": "opened replay of prefrozen sparse A593 semantic lane; architecture evidence only",
        "candidate": selected["selected_candidate"],
        "lane_boundary": "standalone semantic description lane over the 593 teacher-covered occupations; ordinary lexical YV remains separate; no BM25 fusion weight was introduced",
        "coverage": raw["coverage"],
        "strict_source_attested_17": {
            "char_centroid_all17": strict_all,
            "char_centroid_teacher_covered_only": strict_covered,
            "raw_a593_reference": {k: v for k, v in raw["strict_source_attested_17"]["gemma_a593"].items() if k != "rows"},
            "snowball_a593_reference": {k: v for k, v in snow["strict_source_attested_17"]["gemma_a593_snowball"].items() if k != "rows"},
        },
        "opened_stress_54": {
            "char_centroid": stress_result,
            "targetable40": compact_targetable(stress_result),
            "raw_a593_targetable40": compact_targetable(raw["opened_stress_54"]["gemma_a593"]),
            "snowball_a593_targetable40": compact_targetable(snow["opened_stress_54"]["gemma_a593_snowball"]),
        },
        "artifact": selected["selected_candidate"]["full_eight_phrase_artifact"],
        "evidence_warning": "Candidate/top300 was frozen from model-authored leave-one-slot-out data before this replay. Opened 17/88 outcomes may falsify or diagnose it but must not tune it.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "targetable40": result["opened_stress_54"]["targetable40"],
        "strict17": {k: v for k, v in strict_all.items() if k != "rows"},
        "strict_covered": {k: v for k, v in strict_covered.items() if k != "rows"},
        "artifact": result["artifact"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
