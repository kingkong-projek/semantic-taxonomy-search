#!/usr/bin/env python3
"""Development ablation for the smallest bounded C0/G1/teacher fusion.

Both model-authored suites are already opened. This script may choose a simple quota policy
from them, but may not promote it. Any selected policy must face a fresh, disjoint,
prefrozen target/teacher/query slice before it becomes validation evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_model_authored_kv_100 import metric
from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import (
    TRAINING_SHA,
    build_docs,
    fetch_training,
    rank,
)

POLICIES = ((4, 0), (3, 1), (2, 2), (1, 3), (0, 4))


def fuse_quotas(c0: list[str], g1: list[str], teacher: list[str], g1_slots: int, teacher_slots: int) -> list[str]:
    """Preserve C0 rank1, then admit bounded unique candidates from G1 and teacher.

    The first five positions are deterministic and quota-based. Any unused quota caused by
    duplicates is backfilled from the other semantic lane before falling back to C0.
    """
    if not c0:
        seed: list[str] = []
    else:
        seed = [c0[0]]
    out = list(seed)

    def admit(source: list[str], limit: int) -> None:
        added = 0
        for sid in source:
            if sid in out:
                continue
            out.append(sid)
            added += 1
            if added >= limit:
                break

    admit(g1, g1_slots)
    admit(teacher, teacher_slots)
    # If duplicates left fewer than four semantic positions, use the strongest remaining
    # candidates without creating a new scoring system.
    for source in (teacher, g1, c0):
        for sid in source:
            if sid not in out:
                out.append(sid)
            if len(out) >= 5:
                break
        if len(out) >= 5:
            break
    # Preserve a total ordering for diagnostics beyond top5.
    for source in (g1, teacher, c0):
        for sid in source:
            if sid not in out:
                out.append(sid)
    return out


def evaluate(cases: list[dict[str, Any]], rankings: list[list[str]]) -> dict[str, Any]:
    h1 = h5 = h10 = 0
    details = []
    for case, ranked in zip(cases, rankings, strict=True):
        tid = str(case['target']['concept_id'])
        try:
            pos = ranked.index(tid) + 1
        except ValueError:
            pos = None
        h1 += int(pos == 1)
        h5 += int(pos is not None and pos <= 5)
        h10 += int(pos is not None and pos <= 10)
        details.append({'id': case['id'], 'target': case['target'], 'rank': pos, 'top5': ranked[:5]})
    return {
        'top1': metric(h1, len(cases)),
        'hit_at_5': metric(h5, len(cases)),
        'hit_at_10': metric(h10, len(cases)),
        'details': details,
    }


def compare(base: dict[str, Any], candidate: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    rescues = []
    regressions = []
    for case, b, c in zip(cases, base['details'], candidate['details'], strict=True):
        bh = b['rank'] is not None and b['rank'] <= 5
        ch = c['rank'] is not None and c['rank'] <= 5
        row = {
            'id': case['id'],
            'target': case['target'],
            'baseline_rank': b['rank'],
            'candidate_rank': c['rank'],
        }
        if ch and not bh:
            rescues.append(row)
        elif bh and not ch:
            regressions.append(row)
    return {'rescues': rescues, 'regressions': regressions}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', default='31')
    ap.add_argument('--registry', default='research/coverage/source-adapters.json')
    ap.add_argument('--pareto', default='research/coverage/v31/pareto-demand-aggregate.json')
    ap.add_argument('--output', default='artifacts/kv-three-lane-fusion-v31.json')
    args = ap.parse_args()

    old = load_jsonl(Path('research/benchmark/v31/model-authored-kv-100/cases.jsonl'))
    new = load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks101-200/cases.jsonl'))
    canonical = load_jsonl(Path('research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl'))
    t_old = load_jsonl(Path('research/enrichment/v31/model-teacher-kv-top100/phrases.jsonl'))
    t_new = load_jsonl(Path('research/enrichment/v31/model-teacher-kv-ranks101-200/phrases.jsonl'))
    if (len(old), len(new), len(canonical), len(t_old), len(t_new)) != (100, 100, 617, 100, 100):
        raise RuntimeError('benchmark/teacher count drift')
    old_ids = {str(c['target']['concept_id']) for c in old}
    new_ids = {str(c['target']['concept_id']) for c in new}
    if old_ids & new_ids:
        raise RuntimeError('target slices overlap')

    registry = json.loads(Path(args.registry).read_text())
    pareto = json.loads(Path(args.pareto).read_text())
    version = str(args.version)
    tax_body = fetch(f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json')
    tax_sha = hashlib.sha256(tax_body).hexdigest()
    if tax_sha != expected_hash(registry, 'taxonomy-common-relations'):
        raise RuntimeError('taxonomy source drift')
    concepts = json.loads(tax_body).get('data', {}).get('concepts') or []
    by_id = {str(c['id']): c for c in concepts if isinstance(c, dict) and c.get('id')}

    training_body = fetch_training()
    if hashlib.sha256(training_body).hexdigest() != TRAINING_SHA:
        raise RuntimeError('training source drift')
    tj = json.loads(training_body)
    modules = (tj.get('data') or tj.get('moduler') or tj.get('modules')) if isinstance(tj, dict) else tj
    ids = p80_skill_ids(pareto)
    docs, exact, coverage = build_docs(by_id, ids, modules, set(), set())

    teacher_by_id: dict[str, list[str]] = {}
    for row in [*t_old, *t_new]:
        cid = str(row['concept_id'])
        if cid in teacher_by_id:
            raise RuntimeError(f'duplicate teacher target {cid}')
        phrases = [str(p) for p in (row.get('phrases') or [])]
        if len(phrases) != 3:
            raise RuntimeError(f'teacher phrase count {cid}')
        teacher_by_id[cid] = phrases

    c0 = BM25(docs['KV-C0'], exact)
    g1 = BM25(docs['KV-G1-single-desc'], exact)
    tdocs = {
        sid: [*docs['KV-G1-single-desc'][sid], *tokens(' '.join(teacher_by_id.get(sid, [])))]
        for sid in ids
    }
    teacher = BM25(tdocs, exact)

    suites = {'top100_opened': old, 'ranks101_200_opened': new}
    results: dict[str, Any] = {}
    for suite_name, cases in suites.items():
        c0_rows = []
        g1_rows = []
        t_rows = []
        policy_rows = {f'G{g}+T{t}': [] for g, t in POLICIES}
        for case in cases:
            q = str(case['query'])
            a = rank(c0, exact, q)
            b = rank(g1, exact, q)
            t = rank(teacher, exact, q)
            c0_rows.append(a); g1_rows.append(b); t_rows.append(t)
            for gs, ts in POLICIES:
                policy_rows[f'G{gs}+T{ts}'].append(fuse_quotas(a, b, t, gs, ts))
        baseline_rows = policy_rows['G4+T0']
        baseline = evaluate(cases, baseline_rows)
        suite_result = {
            'C0': evaluate(cases, c0_rows),
            'G1': evaluate(cases, g1_rows),
            'teacher': evaluate(cases, t_rows),
            'policies': {},
        }
        for name, rows in policy_rows.items():
            ev = evaluate(cases, rows)
            delta = compare(baseline, ev, cases)
            suite_result['policies'][name] = {
                **ev,
                'rescues_vs_G4_T0': len(delta['rescues']),
                'regressions_vs_G4_T0': len(delta['regressions']),
                'rescue_cases': delta['rescues'],
                'regression_cases': delta['regressions'],
            }
        results[suite_name] = suite_result

    canonical_results = {}
    for gs, ts in POLICIES:
        name = f'G{gs}+T{ts}'
        h1 = h5 = 0
        for case in canonical:
            rel = {str(x['concept_id']) for x in case['must']}
            q = str(case['query'])
            fused = fuse_quotas(rank(c0, exact, q), rank(g1, exact, q), rank(teacher, exact, q), gs, ts)
            h1 += int(bool(fused and fused[0] in rel))
            h5 += int(any(x in rel for x in fused[:5]))
        canonical_results[name] = {'top1': metric(h1, len(canonical)), 'hit_at_5': metric(h5, len(canonical))}

    # Development ordering only. Prefer zero regression on the old opened suite, then new
    # Hit@5, then fewer teacher slots (simpler/safer), then stable name.
    order = sorted(
        (f'G{g}+T{t}' for g, t in POLICIES if t > 0),
        key=lambda name: (
            results['top100_opened']['policies'][name]['regressions_vs_G4_T0'],
            -results['ranks101_200_opened']['policies'][name]['hit_at_5']['hits'],
            int(name.split('+T')[1]),
            name,
        ),
    )

    output = {
        'schema_version': 1,
        'status': 'development ablation on two already-open synthetic suites; not validation',
        'evidence_class': 'synthetic_model_teacher_three_lane_development',
        'fusion_rule': 'preserve C0 rank1; divide the remaining four top5 slots by fixed G1/teacher quotas; backfill duplicates deterministically; no learned scores or thresholds',
        'teacher_targets': len(teacher_by_id),
        'coverage': coverage,
        'results': results,
        'canonical_regression': canonical_results,
        'development_order': order,
        'next_gate': 'select at most one bounded policy, freeze it, then author/freeze teacher phrases and queries for a fresh disjoint target slice before retrieval',
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + '\n')

    compact = {}
    for suite, payload in results.items():
        compact[suite] = {
            name: {
                'hit5': p['hit_at_5'],
                'rescues': p['rescues_vs_G4_T0'],
                'regressions': p['regressions_vs_G4_T0'],
            }
            for name, p in payload['policies'].items()
        }
    print(json.dumps({'development_order': order, 'policies': compact, 'canonical': canonical_results}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
