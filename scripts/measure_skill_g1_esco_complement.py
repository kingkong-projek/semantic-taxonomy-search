#!/usr/bin/env python3
"""Measure headroom from separate typed ESCO candidate lanes above KV-G1-4slot.

No fusion is chosen here. The validated G1 policy is reproduced with both natural holdouts
excluded from training-language evidence. Each ESCO mapping type is then ranked separately,
keyed back to AF P80 skill identities. We report only independent lane recall and oracle
complement to answer whether a later bounded fusion experiment is justified.
"""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, ids_list, build_docs, rank
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1

MAPPINGS = ('exact_match', 'close_match', 'broad_match', 'narrow_match')


def relation_ids(c: dict[str, Any], field: str, by_id: dict[str, dict[str, Any]]) -> list[str]:
    value = c.get(field)
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        rid = str(item.get('id') if isinstance(item, dict) else item or '')
        if rid and by_id.get(rid, {}).get('type') == 'esco-skill':
            out.append(rid)
    return sorted(set(out))


def canonical_text(c: dict[str, Any]) -> str:
    label = str(c.get('preferred_label') or '').strip()
    definition = str(c.get('definition') or '').strip()
    if norm(definition) == norm(label):
        definition = ''
    alternatives = [str(x) for x in as_list(c.get('alternative_labels')) if norm(x) != norm(label)]
    return ' '.join(x for x in [label, definition, *alternatives] if x)


def positive_rank(ranker: BM25, query: str) -> list[str]:
    q = tokens(query); scored = []
    for sid in ranker.documents:
        score = ranker.score(q, sid)
        if score > 0.0:
            scored.append((score, sid))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [sid for _, sid in scored]


def target_ids(case: dict[str, Any]) -> set[str]:
    target = case.get('target')
    if isinstance(target, dict) and target.get('concept_id'):
        return {str(target['concept_id'])}
    return {str(x['concept_id']) for x in (case.get('must') or []) if isinstance(x, dict) and x.get('concept_id')}


def hit(rows: list[str], wanted: set[str], k: int = 5) -> bool:
    return bool(set(rows[:k]) & wanted)


def evaluate_suite(cases: list[dict[str, Any]], baseline_rows: list[list[str]], lane_rows: dict[str, list[list[str]]]) -> dict[str, Any]:
    n = len(cases); baseline_hits = []
    for case, rows in zip(cases, baseline_rows, strict=True):
        baseline_hits.append(hit(rows, target_ids(case)))
    misses = [i for i, ok in enumerate(baseline_hits) if not ok]
    result = {
        'cases': n,
        'baseline_hit_at_5': sum(baseline_hits),
        'baseline_hit_at_5_pct': round(100 * sum(baseline_hits) / n, 3) if n else 0.0,
        'baseline_misses': len(misses),
        'mapping_lanes': {},
    }
    for mapping, rows_list in lane_rows.items():
        lane_hits = []
        rescued = []
        for i, (case, rows) in enumerate(zip(cases, rows_list, strict=True)):
            ok = hit(rows, target_ids(case)); lane_hits.append(ok)
            if i in misses and ok:
                rescued.append(i)
        oracle = [a or b for a, b in zip(baseline_hits, lane_hits, strict=True)]
        result['mapping_lanes'][mapping] = {
            'lane_hit_at_5': sum(lane_hits),
            'lane_hit_at_5_pct': round(100 * sum(lane_hits) / n, 3) if n else 0.0,
            'baseline_misses_rescued_at_5': len(rescued),
            'baseline_miss_rescue_pct': round(100 * len(rescued) / len(misses), 3) if misses else 0.0,
            'oracle_hit_at_5': sum(oracle),
            'oracle_hit_at_5_pct': round(100 * sum(oracle) / n, 3) if n else 0.0,
            'rescued_cases': [
                {
                    'id': cases[i].get('id'),
                    'targets': sorted(target_ids(cases[i])),
                    'lane_top5': rows_list[i][:5],
                }
                for i in rescued
            ],
        }
    return result


def main() -> int:
    first = load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'))
    second = load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl'))
    synthetic = [c for c in load_jsonl(Path('research/benchmark/v31/synthetic-description-stress/cases.jsonl')) if c.get('product') == 'KV']
    if (len(first), len(second), len(synthetic)) != (35, 20, 12):
        raise RuntimeError('suite count drift')

    excluded = first + second
    excluded_ids = {mid for c in excluded for mid in ids_list(c.get('module_ids'))}
    excluded_texts = {norm(c['query']) for c in excluded}

    tbytes = fetch_training(); tsha = hashlib.sha256(tbytes).hexdigest()
    if tsha != TRAINING_SHA:
        raise RuntimeError('training source drift')
    tobj = json.loads(tbytes)
    modules = (tobj.get('data') or tobj.get('moduler') or tobj.get('modules')) if isinstance(tobj, dict) else tobj
    if not isinstance(modules, list):
        raise RuntimeError('training root drift')

    registry = json.loads(Path('research/coverage/source-adapters.json').read_text())
    pareto = json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    url = 'https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json'
    body = fetch(url); taxsha = hashlib.sha256(body).hexdigest()
    if taxsha != expected_hash(registry, 'taxonomy-common-relations'):
        raise RuntimeError('taxonomy source drift')
    concepts = json.loads(body).get('data', {}).get('concepts')
    by_id = {str(c['id']): c for c in concepts if isinstance(c, dict) and c.get('id')}
    skill_ids = p80_skill_ids(pareto)

    docs, exact, coverage = build_docs(by_id, skill_ids, modules, excluded_ids, excluded_texts)
    c0 = BM25(docs['KV-C0'], exact); g1 = BM25(docs['KV-G1-single-desc'], exact)

    esco_docs: dict[str, dict[str, list[str]]] = {m: {} for m in MAPPINGS}
    esco_coverage = {}
    for mapping in MAPPINGS:
        edges = 0
        for sid in skill_ids:
            tids = relation_ids(by_id[sid], mapping, by_id); edges += len(tids)
            text = ' '.join(canonical_text(by_id[tid]) for tid in tids if canonical_text(by_id[tid]))
            if text:
                esco_docs[mapping][sid] = tokens(text)
        esco_coverage[mapping] = {'p80_skills_with_text': len(esco_docs[mapping]), 'edges': edges}
    esco_rankers = {m: BM25(d, {sid: set() for sid in d}) for m, d in esco_docs.items()}

    suites = {'first_holdout_posthoc_shape': first, 'second_holdout_posthoc': second, 'synthetic_stress': synthetic}
    suite_results = {}
    for name, cases in suites.items():
        baseline_rows = [fuse_preserve_c0_top1(rank(c0, exact, str(c['query'])), rank(g1, exact, str(c['query'])), 4) for c in cases]
        lane_rows = {m: [positive_rank(r, str(c['query'])) for c in cases] for m, r in esco_rankers.items()}
        suite_results[name] = evaluate_suite(cases, baseline_rows, lane_rows)

    # Drift guards for the already measured diagnostic shape.
    if suite_results['first_holdout_posthoc_shape']['baseline_hit_at_5'] != 32:
        raise RuntimeError('first baseline drift')
    if suite_results['second_holdout_posthoc']['baseline_hit_at_5'] != 17:
        raise RuntimeError('second baseline drift')
    if suite_results['synthetic_stress']['baseline_hit_at_5'] != 8:
        raise RuntimeError('synthetic baseline drift')

    result = {
        'schema_version': 1,
        'role': 'oracle/complement diagnostic only; no ESCO fusion policy selected',
        'validated_baseline': 'KV-G1-4slot-single-desc',
        'mapping_semantics_guard': 'exact/close/broad/narrow remain separate candidate lanes',
        'retrieval_exclusion': {'first_holdout_cases': 35, 'second_holdout_cases': 20, 'module_ids': len(excluded_ids), 'texts': len(excluded_texts)},
        'g1_coverage': coverage,
        'esco_coverage': esco_coverage,
        'taxonomy_sha256': taxsha,
        'training_sha256': tsha,
        'suites': suite_results,
        'decision_rule': 'Only a material complement above the validated G1 residual can justify a later bounded fusion experiment; this diagnostic itself changes no candidate.',
    }
    p = Path('artifacts/skill-g1-esco-complement-v31.json'); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    compact = {
        suite: {
            'baseline': data['baseline_hit_at_5_pct'],
            **{m: {'lane_hit5': x['lane_hit_at_5_pct'], 'misses_rescued': x['baseline_misses_rescued_at_5'], 'oracle_hit5': x['oracle_hit_at_5_pct'], 'rescued_ids': [r['id'] for r in x['rescued_cases']]} for m, x in data['mapping_lanes'].items()}
        }
        for suite, data in suite_results.items()
    }
    print(json.dumps({'esco_coverage': esco_coverage, 'suites': compact}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
