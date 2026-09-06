#!/usr/bin/env python3
"""Verify the compiled frontend student index against frozen C0 behavior.

This is primarily an architecture experiment: relevance must be exactly the same as the
existing deterministic C0 baseline while moving almost all scoring work to build time.
The output also contains browser-runtime test vectors and device-independent operation
counts for later JS/browser smoke tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, load_jsonl, norm, tokens


def build_reference(by_id: dict[str, dict[str, Any]], ids: list[str], kind: str) -> tuple[BM25, dict[str, set[str]]]:
    docs: dict[str, list[str]] = {}
    exact: dict[str, set[str]] = {}
    for cid in ids:
        c = by_id.get(cid)
        if not isinstance(c, dict) or c.get("type") != kind:
            raise RuntimeError(f"invalid target {cid}")
        label = str(c.get("preferred_label") or "").strip()
        definition = str(c.get("definition") or "").strip()
        real_definition = definition if definition and norm(definition) != norm(label) else ""
        alternatives = [x for x in as_list(c.get("alternative_labels")) if norm(x) != norm(label)]
        docs[cid] = tokens(" ".join([label, real_definition, *alternatives]))
        exact[cid] = {norm(label), *[norm(x) for x in alternatives if norm(x)]}
    return BM25(docs, exact), exact


def reference_rank(ranker: BM25, exact: dict[str, set[str]], query: str) -> list[str]:
    q = tokens(query)
    nq = norm(query)
    scored: list[tuple[float, str]] = []
    for cid in ranker.documents:
        score = ranker.score(q, cid)
        if nq and nq in exact[cid]:
            score += 1_000_000.0
        if score > 0.0:
            scored.append((score, cid))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [cid for _, cid in scored]


def compiled_rank(asset: dict[str, Any], query: str) -> tuple[list[str], dict[str, int]]:
    ids = [str(x) for x in asset["document_ids"]]
    scores: dict[int, float] = defaultdict(float)
    qtokens = sorted(set(tokens(query)))
    postings_visited = 0
    matched_terms = 0
    for term in qtokens:
        rows = asset["postings"].get(term)
        if not rows:
            continue
        matched_terms += 1
        for ordinal, contribution in rows:
            scores[int(ordinal)] += float(contribution)
            postings_visited += 1
    nq = norm(query)
    exact_rows = asset["exact_surfaces"].get(nq, []) if nq else []
    for ordinal in exact_rows:
        scores[int(ordinal)] += 1_000_000.0
    ranked = sorted(((score, ids[ordinal]) for ordinal, score in scores.items() if score > 0.0), key=lambda row: (-row[0], row[1]))
    return [cid for _, cid in ranked], {
        "query_tokens_unique": len(qtokens),
        "matched_terms": matched_terms,
        "postings_visited": postings_visited,
        "candidate_docs_scored": len(scores),
        "exact_surface_docs": len(exact_rows),
    }


def relevant_ids(case: dict[str, Any]) -> set[str]:
    if isinstance(case.get("target"), dict) and case["target"].get("concept_id"):
        return {str(case["target"]["concept_id"])}
    out: set[str] = set()
    for key in ("must", "acceptable"):
        for item in case.get(key) or []:
            if isinstance(item, dict) and item.get("concept_id"):
                out.add(str(item["concept_id"]))
    return out


def summarize(cases: list[dict[str, Any]], rankings: list[list[str]]) -> dict[str, Any]:
    top1 = hit5 = hit10 = no_match_ok = no_match_total = 0
    for case, ranked in zip(cases, rankings, strict=True):
        intent = str(case.get("expected_intent") or "SINGLE")
        relevant = relevant_ids(case)
        if intent == "NO_MATCH":
            no_match_total += 1
            no_match_ok += int(not ranked)
            continue
        top1 += int(bool(ranked and ranked[0] in relevant))
        hit5 += int(any(cid in relevant for cid in ranked[:5]))
        hit10 += int(any(cid in relevant for cid in ranked[:10]))
    positives = len(cases) - no_match_total
    pct = lambda n, d: round(100.0 * n / d, 3) if d else None
    return {
        "cases": len(cases),
        "positive_cases": positives,
        "top1_pct_positive": pct(top1, positives),
        "discovery_hit_at_5_pct_positive": pct(hit5, positives),
        "hit_at_10_pct_positive": pct(hit10, positives),
        "no_match_cases": no_match_total,
        "no_match_abstention_pct": pct(no_match_ok, no_match_total),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--index-dir", default="artifacts/frontend-student-index-v31")
    ap.add_argument("--output", default="artifacts/frontend-student-index-v31/evaluation.json")
    ap.add_argument("--vectors", default="artifacts/frontend-student-index-v31/runtime-vectors.json")
    args = ap.parse_args()

    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    url = f"https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    body = fetch(url)
    sha = hashlib.sha256(body).hexdigest()
    if sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(body).get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    index_dir = Path(args.index_dir)
    assets = {
        "YV": json.loads((index_dir / "yv-p80-c0-index.json").read_text(encoding="utf-8")),
        "KV": json.loads((index_dir / "kv-p80-c0-index.json").read_text(encoding="utf-8")),
    }
    references = {
        "YV": build_reference(by_id, [str(x) for x in assets["YV"]["document_ids"]], "occupation-name"),
        "KV": build_reference(by_id, [str(x) for x in assets["KV"]["document_ids"]], "skill"),
    }

    suites: list[tuple[str, str, Path, Any]] = [
        ("yv_source_truth", "YV", Path("research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl"), None),
        ("kv_source_truth", "KV", Path("research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl"), None),
        ("yv_fresh_natural", "YV", Path("research/benchmark/v31/fresh-natural-holdout/cases.jsonl"), None),
        ("kv_fresh_natural", "KV", Path("research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl"), None),
        ("synthetic_description", "BOTH", Path("research/benchmark/v31/synthetic-description-stress/cases.jsonl"), None),
    ]

    all_vectors: list[dict[str, Any]] = []
    suite_results: dict[str, Any] = {}
    total_ops = defaultdict(int)
    total_cases = 0
    parity_failures: list[dict[str, Any]] = []

    for suite_name, suite_product, path, _ in suites:
        cases = load_jsonl(path)
        if suite_product == "BOTH":
            partitions = [("YV", [c for c in cases if c.get("product") == "YV"]), ("KV", [c for c in cases if c.get("product") == "KV"])]
        else:
            partitions = [(suite_product, cases)]
        combined_summaries = {}
        for product, part in partitions:
            asset = assets[product]
            ref_ranker, ref_exact = references[product]
            compiled_rankings: list[list[str]] = []
            for case in part:
                query = str(case["query"])
                ranked, ops = compiled_rank(asset, query)
                reference = reference_rank(ref_ranker, ref_exact, query)
                if ranked[:10] != reference[:10]:
                    parity_failures.append({
                        "suite": suite_name,
                        "id": case.get("id"),
                        "product": product,
                        "query": query,
                        "compiled_top10": ranked[:10],
                        "reference_top10": reference[:10],
                    })
                compiled_rankings.append(ranked)
                for key, value in ops.items():
                    total_ops[key] += value
                total_cases += 1
                all_vectors.append({
                    "suite": suite_name,
                    "id": case.get("id"),
                    "product": product,
                    "query": query,
                    "expected_top10": ranked[:10],
                    "ops": ops,
                })
            combined_summaries[product] = summarize(part, compiled_rankings)
        suite_results[suite_name] = combined_summaries

    if parity_failures:
        raise RuntimeError(f"compiled/reference top10 parity failed for {len(parity_failures)} cases; first={parity_failures[0]}")

    manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "taxonomy_sha256": sha,
        "engine": "compiled-c0-bm25-student",
        "reference": "frozen Python C0 BM25 semantics",
        "top10_parity_cases": total_cases,
        "top10_parity_failures": 0,
        "asset_manifest": manifest,
        "suites": suite_results,
        "runtime_operation_totals": dict(sorted(total_ops.items())),
        "runtime_operation_means": {key: round(value / max(1, total_cases), 3) for key, value in sorted(total_ops.items())},
        "interpretation": "relevance-equivalent build-time compilation; operation counts are device-independent, not wall-clock mobile benchmarks",
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    Path(args.vectors).write_text(json.dumps({"schema_version": 1, "cases": all_vectors}, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
