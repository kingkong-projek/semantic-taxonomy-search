#!/usr/bin/env python3
"""Compile the frozen plain KV-G1+T3 candidate into a tiny browser runtime asset.

All expensive source fetching, document construction and BM25 weighting happens here.
The browser only tokenizes a query, adds precomputed posting contributions and applies the
frozen C0-top1 + G1-1slot + teacher-3slot fusion. No benchmark text is ingested.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from evaluate_kv_drop_numeric_expansion_only import rankers
from evaluate_kv_three_lane_fusion import fuse_quotas
from evaluate_p80_lexical_ablation import expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, rank

TEACHER_PATHS = (
    'research/enrichment/v31/model-teacher-kv-top100/phrases.jsonl',
    'research/enrichment/v31/model-teacher-kv-ranks101-200/phrases.jsonl',
    'research/enrichment/v31/model-teacher-kv-ranks201-300/phrases.jsonl',
    'research/enrichment/v31/model-teacher-kv-ranks301-316/phrases.jsonl',
)
PARITY_PATHS = (
    'research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl',
    'research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl',
    'research/benchmark/v31/training-skill-second-holdout/cases.jsonl',
    'research/benchmark/v31/training-skill-third-holdout/cases.jsonl',
    'research/benchmark/v31/model-authored-kv-ranks101-200/cases.jsonl',
    'research/benchmark/v31/model-authored-kv-ranks201-300/cases.jsonl',
    'research/benchmark/v31/model-authored-kv-ranks301-316/cases.jsonl',
)


def teacher_map() -> dict[str, list[str]]:
    rows: list[dict[str, Any]] = []
    for path in TEACHER_PATHS:
        rows.extend(load_jsonl(Path(path)))
    if len(rows) != 316:
        raise RuntimeError(f'teacher count drift: {len(rows)} != 316')
    out: dict[str, list[str]] = {}
    for row in rows:
        cid = str(row['concept_id'])
        phrases = [str(x) for x in row.get('phrases') or []]
        if cid in out or len(phrases) != 3:
            raise RuntimeError(f'teacher identity/phrase drift: {cid}')
        out[cid] = phrases
    return out


def contribution(ranker: Any, cid: str, term: str) -> float:
    f = ranker.tf[cid].get(term, 0)
    if not f:
        return 0.0
    dl = ranker.lengths[cid]
    denom = f + ranker.k1 * (1.0 - ranker.b + ranker.b * dl / max(ranker.avgdl, 1e-9))
    return ranker.idf.get(term, 0.0) * (f * (ranker.k1 + 1.0) / denom)


def compile_asset(c0: Any, g1: Any, teacher: Any, exact: dict[str, set[str]], by_id: dict[str, dict[str, Any]], ids: list[str], metadata: dict[str, Any]) -> dict[str, Any]:
    doc_ids = sorted(ids)
    pos = {cid: i for i, cid in enumerate(doc_ids)}
    lanes = (c0, g1, teacher)
    postings: dict[str, dict[int, list[float]]] = {}
    for lane_idx, lane in enumerate(lanes):
        for cid in doc_ids:
            for term in lane.tf[cid]:
                value = contribution(lane, cid, term)
                if not value:
                    continue
                row = postings.setdefault(term, {}).setdefault(pos[cid], [0.0, 0.0, 0.0])
                row[lane_idx] = round(value, 12)
    compact_postings = {
        term: [[idx, *scores] for idx, scores in sorted(rows.items())]
        for term, rows in sorted(postings.items())
    }
    inverted_exact: dict[str, list[int]] = {}
    for cid in doc_ids:
        for surface in exact[cid]:
            if surface:
                inverted_exact.setdefault(surface, []).append(pos[cid])
    inverted_exact = {surface: sorted(set(rows)) for surface, rows in sorted(inverted_exact.items())}
    labels = [str(by_id[cid].get('preferred_label') or cid) for cid in doc_ids]
    return {
        'schema_version': 1,
        'engine': 'KV-G1+T3-plain-v1',
        'fusion': {'c0_top1': 1, 'g1_slots': 1, 'teacher_slots': 3, 'backfill': ['teacher', 'g1', 'c0']},
        'document_ids': doc_ids,
        'labels': labels,
        'postings': compact_postings,
        'exact_surfaces': inverted_exact,
        'metadata': metadata,
    }


def compiled_rank(asset: dict[str, Any], query: str) -> list[str]:
    ids = asset['document_ids']
    scores = [[0.0] * len(ids) for _ in range(3)]
    for term in sorted(set(tokens(query))):
        for row in asset['postings'].get(term, []):
            idx = int(row[0])
            scores[0][idx] += float(row[1]); scores[1][idx] += float(row[2]); scores[2][idx] += float(row[3])
    for idx in asset['exact_surfaces'].get(norm(query), []):
        for lane in scores:
            lane[int(idx)] += 1_000_000.0
    def order(lane: list[float]) -> list[str]:
        rows = [(score, ids[i]) for i, score in enumerate(lane) if score > 0]
        rows.sort(key=lambda x: (-x[0], x[1]))
        return [cid for _, cid in rows]
    return fuse_quotas(order(scores[0]), order(scores[1]), order(scores[2]), 1, 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default='demo/assets/kv-g1-t3.json')
    ap.add_argument('--parity-output', default='artifacts/kv-demo-parity-v1.json')
    ap.add_argument('--build-id', default=os.environ.get('GITHUB_SHA', 'local'))
    args = ap.parse_args()

    registry = json.loads(Path('research/coverage/source-adapters.json').read_text(encoding='utf-8'))
    pareto = json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text(encoding='utf-8'))
    tax_url = 'https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json'
    tax_body = fetch(tax_url)
    tax_sha = hashlib.sha256(tax_body).hexdigest()
    if tax_sha != expected_hash(registry, 'taxonomy-common-relations'):
        raise RuntimeError('taxonomy source drift')
    concepts = json.loads(tax_body).get('data', {}).get('concepts') or []
    by_id = {str(c['id']): c for c in concepts if isinstance(c, dict) and c.get('id')}
    ids = p80_skill_ids(pareto)
    if len(ids) != 316:
        raise RuntimeError(f'P80 skill count drift: {len(ids)}')

    training_body = fetch_training()
    training_sha = hashlib.sha256(training_body).hexdigest()
    if training_sha != TRAINING_SHA:
        raise RuntimeError('training source drift')
    tj = json.loads(training_body)
    modules = (tj.get('data') or tj.get('moduler') or tj.get('modules')) if isinstance(tj, dict) else tj
    if not isinstance(modules, list):
        raise RuntimeError('training source root drift')

    teacher = teacher_map()
    if set(teacher) != set(ids):
        raise RuntimeError('teacher/P80 identity drift')
    c0, g1, t_lane, exact, coverage = rankers(by_id, ids, modules, teacher, [], 'current')
    metadata = {
        'taxonomy_version': 31,
        'taxonomy_sha256': tax_sha,
        'training_sha256': training_sha,
        'target_count': len(ids),
        'teacher_phrases_per_target': 3,
        'build_id': str(args.build_id)[:40],
        'runtime_dependencies': [],
        'coverage': coverage,
    }
    asset = compile_asset(c0, g1, t_lane, exact, by_id, ids, metadata)

    parity_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for path in PARITY_PATHS:
        for row in load_jsonl(Path(path)):
            query = str(row.get('query') or '')
            key = (path, str(row.get('id') or query))
            if not query or key in seen:
                continue
            seen.add(key)
            expected = fuse_quotas(rank(c0, exact, query), rank(g1, exact, query), rank(t_lane, exact, query), 1, 3)[:5]
            actual = compiled_rank(asset, query)[:5]
            if actual != expected:
                raise RuntimeError(f'compiled parity failure {path}:{row.get("id")}: {actual} != {expected}')
            parity_rows.append({'id': str(row.get('id') or len(parity_rows)), 'query': query, 'expected_top5': expected})

    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(asset, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    out.write_bytes(encoded)
    parity_out = Path(args.parity_output); parity_out.parent.mkdir(parents=True, exist_ok=True)
    parity_out.write_text(json.dumps({'schema_version': 1, 'engine': asset['engine'], 'cases': parity_rows}, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    result = {
        'engine': asset['engine'],
        'targets': len(ids),
        'terms': len(asset['postings']),
        'exact_surfaces': len(asset['exact_surfaces']),
        'parity_cases': len(parity_rows),
        'json_bytes': len(encoded),
        'gzip_bytes': len(gzip.compress(encoded, compresslevel=9)),
        'build_id': metadata['build_id'],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
