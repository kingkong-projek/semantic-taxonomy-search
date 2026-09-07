#!/usr/bin/env python3
"""Compile the frozen deterministic YV C2 retriever for the zero-backend browser demo.

This is packaging, not a new retrieval experiment. The browser asset mirrors the existing
C1/C2 research implementation:
- C1 P80 + six frozen boundary occupation identities;
- canonical label/definition/alternative-label BM25;
- the frozen short-query surface/component/fuzzy guard and conservative abstention;
- C2 exact job-title preferred-label -> typed occupation-name parent routing.

The compiler also emits an authoritative parity packet. Browser CI must reproduce the
Python C2 top five exactly before the asset can be deployed.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_c2_job_title_router import build_c1_index, relation_parent_ids
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm
from evaluate_pareto_c1 import BOUNDARY_IDS, p80_ids, rank_c1


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def bm25_postings(ranker: Any, ids: list[str]) -> dict[str, list[list[float | int]]]:
    """Precompute one-query-term BM25 contributions without changing rank semantics."""
    out: dict[str, list[list[float | int]]] = defaultdict(list)
    for index, cid in enumerate(ids):
        dl = ranker.lengths[cid]
        tf = ranker.tf[cid]
        for term, frequency in tf.items():
            idf = ranker.idf.get(term, 0.0)
            denom = frequency + ranker.k1 * (
                1.0 - ranker.b + ranker.b * dl / max(ranker.avgdl, 1e-9)
            )
            contribution = idf * (frequency * (ranker.k1 + 1.0) / denom)
            if contribution > 0.0:
                out[term].append([index, contribution])
    return {term: rows for term, rows in sorted(out.items())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--source-truth", default="research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl")
    ap.add_argument("--natural-holdout", default="research/benchmark/v31/fresh-natural-holdout/benchmark.jsonl")
    ap.add_argument("--output", default="demo/assets/yv-c2.json")
    ap.add_argument("--parity-output", default="artifacts/yv-demo-parity-v1.json")
    ap.add_argument("--build-id", default="local")
    args = ap.parse_args()

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    version = str(args.version)
    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    body = fetch(taxonomy_url)
    taxonomy_sha = hashlib.sha256(body).hexdigest()
    if taxonomy_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(body).get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    base_p80 = p80_ids(pareto)
    ids = sorted(set(base_p80) | BOUNDARY_IDS)
    if len(ids) != 165:
        raise RuntimeError(f"C1/C2 target envelope drift: {len(ids)}")
    ranker, exact_surfaces, surface_tokens = build_c1_index(by_id, ids)

    occurrence = {
        str(row["concept_id"]): int(row["occurrences"])
        for row in pareto["occupation_name"]["ranked_p95"]
    }
    label_to_parent_ids: dict[str, set[str]] = defaultdict(set)
    for cid, concept in by_id.items():
        if concept.get("type") != "job-title":
            continue
        label = norm(concept.get("preferred_label"))
        if not label:
            continue
        parents = relation_parent_ids(concept, by_id)
        if parents:
            label_to_parent_ids[label].update(parents)

    def parent_sort_key(cid: str) -> tuple[int, str, str]:
        return (-occurrence.get(cid, 0), norm(by_id[cid].get("preferred_label")), cid)

    routes = {
        label: sorted(parent_ids, key=parent_sort_key)
        for label, parent_ids in sorted(label_to_parent_ids.items())
    }

    def rank_c2(query: str) -> list[str]:
        c1_scored = rank_c1(ranker, query, exact_surfaces, surface_tokens)
        c1_ranked = [cid for cid, _, _ in c1_scored]
        nq = norm(query)
        exact_canonical = [cid for cid in c1_ranked if nq and nq in exact_surfaces[cid]]
        routed = routes.get(nq, [])
        merged: list[str] = []
        for cid in [*exact_canonical, *routed, *c1_ranked]:
            if cid not in merged:
                merged.append(cid)
        return merged

    exact_index: dict[str, list[int]] = defaultdict(list)
    for index, cid in enumerate(ids):
        for surface in sorted(exact_surfaces[cid]):
            exact_index[surface].append(index)

    routed_ids = sorted({cid for parent_ids in routes.values() for cid in parent_ids})
    labels_by_id = {
        cid: str(by_id[cid].get("preferred_label") or cid)
        for cid in sorted(set(ids) | set(routed_ids))
    }
    asset = {
        "schema_version": 1,
        "engine": "YV-C2-plain-v1",
        "document_ids": ids,
        "labels": [labels_by_id[cid] for cid in ids],
        "label_by_id": labels_by_id,
        "postings": bm25_postings(ranker, ids),
        "exact_surfaces": {surface: indexes for surface, indexes in sorted(exact_index.items())},
        "surface_tokens": [sorted(surface_tokens[cid]) for cid in ids],
        "job_title_routes": routes,
        "metadata": {
            "taxonomy_version": int(version),
            "taxonomy_sha256": taxonomy_sha,
            "target_count": len(ids),
            "p80_target_count": len(base_p80),
            "boundary_target_count": len(BOUNDARY_IDS),
            "job_title_route_surface_count": len(routes),
            "routed_parent_count": len(routed_ids),
            "runtime_dependencies": [],
            "build_id": str(args.build_id),
            "retrieval_contract": "frozen C2 = C1 + exact job-title preferred-label to typed occupation-name parents",
        },
    }

    parity_cases: list[dict[str, Any]] = []
    source_truth = read_jsonl(Path(args.source_truth))
    natural_holdout = read_jsonl(Path(args.natural_holdout))
    if len(source_truth) != 333 or len(natural_holdout) != 30:
        raise RuntimeError(f"YV parity corpus drift: {len(source_truth)}/{len(natural_holdout)}")
    for case in source_truth:
        query = str(case["query"])
        parity_cases.append({"id": str(case["id"]), "query": query, "expected_top5": rank_c2(query)[:5]})
    for case in natural_holdout:
        query = str(case["query"])
        parity_cases.append({"id": str(case["id"]), "query": query, "expected_top5": rank_c2(query)[:5]})
    for index, query in enumerate(routes):
        parity_cases.append({
            "id": f"yv.c2.route.{index:05d}",
            "query": query,
            "expected_top5": rank_c2(query)[:5],
        })

    parity = {
        "schema_version": 1,
        "engine": asset["engine"],
        "taxonomy_sha256": taxonomy_sha,
        "semantics": "browser packaging parity only; not new validation evidence",
        "cases": parity_cases,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(asset, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    output.write_bytes(raw)
    parity_output = Path(args.parity_output)
    parity_output.parent.mkdir(parents=True, exist_ok=True)
    parity_output.write_text(json.dumps(parity, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "engine": asset["engine"],
        "targets": len(ids),
        "job_title_route_surfaces": len(routes),
        "routed_parents": len(routed_ids),
        "parity_cases": len(parity_cases),
        "asset_bytes": len(raw),
        "asset_gzip_bytes": len(gzip.compress(raw, compresslevel=9)),
        "runtime_dependencies": [],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
