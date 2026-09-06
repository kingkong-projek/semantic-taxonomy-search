#!/usr/bin/env python3
"""Classify the three frozen second-holdout KV-G1-4slot Hit@5 misses without tuning.

This is diagnostic only. It reproduces the already frozen validation shape, then records
labels, ranks, BM25 scores, lexical overlap, and source-attested enrichment coverage for
the three misses. It does not alter policy, features, weights, or benchmark truth.
"""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, ids_list, build_docs, rank
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1

MISS_IDS = {
    'kv.training-skill-second-holdout.006',
    'kv.training-skill-second-holdout.014',
    'kv.training-skill-second-holdout.018',
}


def label(c: dict[str, Any] | None) -> str:
    return str((c or {}).get('preferred_label') or '')


def position(rows: list[str], cid: str) -> int | None:
    try:
        return rows.index(cid) + 1
    except ValueError:
        return None


def scored(ranker: BM25, exact: dict[str, set[str]], query: str, cid: str) -> float:
    value = ranker.score(tokens(query), cid)
    if norm(query) in exact[cid]:
        value += 1_000_000.0
    return value


def overlap(query: str, doc_tokens: list[str]) -> dict[str, Any]:
    q = set(tokens(query)); d = set(doc_tokens); shared = sorted(q & d)
    return {
        'query_unique_tokens': len(q),
        'document_unique_tokens': len(d),
        'shared_unique_tokens': len(shared),
        'shared_tokens': shared,
    }


def main() -> int:
    first = load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'))
    second = load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl'))
    misses = [c for c in second if c.get('id') in MISS_IDS]
    if len(misses) != 3:
        raise RuntimeError(f'miss set drift: {len(misses)}')

    excluded = first + second
    excluded_ids = {mid for c in excluded for mid in ids_list(c.get('module_ids'))}
    excluded_texts = {norm(c['query']) for c in excluded}

    tbytes = fetch_training(); tsha = hashlib.sha256(tbytes).hexdigest()
    if tsha != TRAINING_SHA:
        raise RuntimeError('training source drift')
    tobj = json.loads(tbytes)
    modules = (tobj.get('data') or tobj.get('moduler') or tobj.get('modules')) if isinstance(tobj, dict) else tobj
    if not isinstance(modules, list):
        raise RuntimeError('training mapping root drift')

    registry = json.loads(Path('research/coverage/source-adapters.json').read_text())
    pareto = json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    tbody = fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json')
    taxsha = hashlib.sha256(tbody).hexdigest()
    if taxsha != expected_hash(registry, 'taxonomy-common-relations'):
        raise RuntimeError('taxonomy source drift')
    concepts = json.loads(tbody).get('data', {}).get('concepts')
    by_id = {str(c['id']): c for c in concepts if isinstance(c, dict) and c.get('id')}
    ids = p80_skill_ids(pareto)
    docs, exact, coverage = build_docs(by_id, ids, modules, excluded_ids, excluded_texts)
    c0 = BM25(docs['KV-C0'], exact); g1 = BM25(docs['KV-G1-single-desc'], exact)

    # Reconstruct source-attested single-P80 enrichment rows for evidence display only.
    p80 = set(ids)
    single_rows: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for module in modules:
        if not isinstance(module, dict):
            continue
        desc = str(module.get('modulbeskrivning') or '').strip(); ndesc = norm(desc)
        if not desc:
            continue
        mids = ids_list(module.get('modul_id'))
        if any(mid in excluded_ids for mid in mids) or ndesc in excluded_texts:
            continue
        mapped = sorted({str(x['koncept_id']) for x in (module.get('kompetenser_kopplade_till_modulen') or []) if isinstance(x, dict) and x.get('koncept_id') and str(x['koncept_id']) in p80})
        if len(mapped) == 1:
            single_rows[mapped[0]].append({
                'module_ids': mids,
                'module_name': str(module.get('modulnamn') or ''),
                'description': desc,
            })

    rows = []
    for case in misses:
        q = str(case['query']); target = str(case['target']['concept_id'])
        a = rank(c0, exact, q); b = rank(g1, exact, q); fused = fuse_preserve_c0_top1(a, b, 4)
        if target in fused[:5]:
            raise RuntimeError(f'{case["id"]} is no longer a miss')
        candidate_ids = []
        for cid in [target, *fused[:10], *b[:10], *a[:5]]:
            if cid not in candidate_ids:
                candidate_ids.append(cid)
        candidates = []
        for cid in candidate_ids:
            candidates.append({
                'concept_id': cid,
                'label': label(by_id.get(cid)),
                'fused_rank': position(fused, cid),
                'c0_rank': position(a, cid),
                'g1_rank': position(b, cid),
                'c0_score': round(scored(c0, exact, q, cid), 6),
                'g1_score': round(scored(g1, exact, q, cid), 6),
                'c0_overlap': overlap(q, docs['KV-C0'][cid]),
                'g1_overlap': overlap(q, docs['KV-G1-single-desc'][cid]),
                'g1_source_row_count': len(single_rows.get(cid, [])),
            })
        rows.append({
            'id': case['id'],
            'query': q,
            'target': {
                'concept_id': target,
                'label': label(by_id.get(target)),
                'occurrence_proxy': int(case['target'].get('occurrence_proxy') or 0),
                'all_mapped_skill_ids': [
                    {'concept_id': cid, 'label': label(by_id.get(cid)), 'in_p80': cid in p80}
                    for cid in case.get('all_mapped_skill_ids') or []
                ],
                'c0_rank': position(a, target),
                'g1_rank': position(b, target),
                'fused_rank': position(fused, target),
                'g1_source_rows': single_rows.get(target, []),
            },
            'fused_top10': [{'concept_id': cid, 'label': label(by_id.get(cid))} for cid in fused[:10]],
            'candidates': candidates,
        })

    result = {
        'schema_version': 1,
        'status': 'diagnostic only; no retrieval policy changes',
        'miss_ids': sorted(MISS_IDS),
        'taxonomy_sha256': taxsha,
        'training_sha256': tsha,
        'validation_exclusion': {'first_holdout_cases': len(first), 'second_holdout_cases': len(second), 'module_ids': len(excluded_ids), 'texts': len(excluded_texts)},
        'coverage': coverage,
        'cases': rows,
    }
    out = Path('artifacts/skill-g1-residual-v31.json'); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    compact = []
    for row in rows:
        t = row['target']
        compact.append({
            'id': row['id'], 'target': f"{t['label']} ({t['concept_id']})",
            'target_ranks': {'c0': t['c0_rank'], 'g1': t['g1_rank'], 'fused': t['fused_rank']},
            'target_g1_source_rows': len(t['g1_source_rows']),
            'all_mapped_skills': t['all_mapped_skill_ids'],
            'fused_top10': row['fused_top10'],
        })
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
