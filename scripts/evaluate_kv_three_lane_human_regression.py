#!/usr/bin/env python3
"""Regression-control bounded teacher fusion on source-attested AF description holdouts.

Teacher phrases were not authored from these AF holdout queries. G1 is rebuilt per suite
with every holdout text/module that was excluded in that suite's established validation
protocol removed from retrieval evidence. This is a regression/generalization control for
fixed quota policies, not proof of production user prevalence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_kv_three_lane_fusion import fuse_quotas
from evaluate_model_authored_kv_100 import metric
from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import (
    TRAINING_SHA,
    build_docs,
    fetch_training,
    ids_list,
    rank,
)

POLICIES = ((4, 0), (3, 1), (2, 2), (1, 3))


def evaluate(cases: list[dict[str, Any]], rows: list[list[str]]) -> dict[str, Any]:
    h1 = h5 = h10 = 0
    details = []
    for case, ranked in zip(cases, rows, strict=True):
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


def paired(base: dict[str, Any], cand: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    rescues = []
    regressions = []
    for case, b, c in zip(cases, base['details'], cand['details'], strict=True):
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
    first = load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'))
    second = load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl'))
    third = load_jsonl(Path('research/benchmark/v31/training-skill-third-holdout/cases.jsonl'))
    if (len(first), len(second), len(third)) != (35, 20, 26):
        raise RuntimeError('holdout count drift')
    manifest = json.loads(Path('research/benchmark/v31/training-skill-third-holdout/manifest.json').read_text())
    if manifest['benchmark_sha256'] != '2903954d7b68cac0dbdd0b7e841a1222938a2e2670e366444cd63b7f12ed3e29':
        raise RuntimeError('third holdout hash drift')

    teacher_rows = [
        *load_jsonl(Path('research/enrichment/v31/model-teacher-kv-top100/phrases.jsonl')),
        *load_jsonl(Path('research/enrichment/v31/model-teacher-kv-ranks101-200/phrases.jsonl')),
    ]
    teacher_by_id: dict[str, list[str]] = {}
    for row in teacher_rows:
        cid = str(row['concept_id'])
        if cid in teacher_by_id:
            raise RuntimeError(f'duplicate teacher target {cid}')
        phrases = [str(p) for p in row.get('phrases') or []]
        if len(phrases) != 3:
            raise RuntimeError(f'teacher phrase count {cid}')
        teacher_by_id[cid] = phrases

    training_body = fetch_training()
    if hashlib.sha256(training_body).hexdigest() != TRAINING_SHA:
        raise RuntimeError('training source drift')
    tj = json.loads(training_body)
    modules = (tj.get('data') or tj.get('moduler') or tj.get('modules')) if isinstance(tj, dict) else tj

    registry = json.loads(Path('research/coverage/source-adapters.json').read_text())
    pareto = json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    tax_body = fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json')
    if hashlib.sha256(tax_body).hexdigest() != expected_hash(registry, 'taxonomy-common-relations'):
        raise RuntimeError('taxonomy source drift')
    concepts = json.loads(tax_body).get('data', {}).get('concepts') or []
    by_id = {str(c['id']): c for c in concepts if isinstance(c, dict) and c.get('id')}
    ids = p80_skill_ids(pareto)

    suites = {
        # Mirror the exclusion boundary used when each lane was evaluated.
        'first35_opened': (first, first),
        'second20_validation_opened': (second, [*first, *second]),
        'third26_source_attested_opened': (third, [*first, *second, *third]),
    }
    results: dict[str, Any] = {}
    for suite_name, (cases, excluded_cases) in suites.items():
        exids = {mid for c in excluded_cases for mid in ids_list(c.get('module_ids'))}
        extexts = {norm(c['query']) for c in excluded_cases}
        docs, exact, coverage = build_docs(by_id, ids, modules, exids, extexts)
        c0 = BM25(docs['KV-C0'], exact)
        g1 = BM25(docs['KV-G1-single-desc'], exact)
        tdocs = {
            sid: [*docs['KV-G1-single-desc'][sid], *tokens(' '.join(teacher_by_id.get(sid, [])))]
            for sid in ids
        }
        teacher = BM25(tdocs, exact)

        policy_rows = {f'G{g}+T{t}': [] for g, t in POLICIES}
        for case in cases:
            q = str(case['query'])
            a = rank(c0, exact, q)
            b = rank(g1, exact, q)
            t = rank(teacher, exact, q)
            for gs, ts in POLICIES:
                policy_rows[f'G{gs}+T{ts}'].append(fuse_quotas(a, b, t, gs, ts))

        base = evaluate(cases, policy_rows['G4+T0'])
        policies = {}
        for name, rows in policy_rows.items():
            ev = evaluate(cases, rows)
            delta = paired(base, ev, cases)
            policies[name] = {
                **ev,
                'rescues_vs_G4_T0': len(delta['rescues']),
                'regressions_vs_G4_T0': len(delta['regressions']),
                'rescue_cases': delta['rescues'],
                'regression_cases': delta['regressions'],
            }
        results[suite_name] = {
            'cases': len(cases),
            'excluded_module_ids': len(exids),
            'excluded_normalized_texts': len(extexts),
            'coverage': coverage,
            'policies': policies,
        }

    # Strongly adjudicated third-holdout cases are a qualitative guardrail; raw metrics
    # remain primary and unchanged.
    adjudication = json.loads(Path('research/evaluation/v31/skill-g1-third-holdout-adjudication.json').read_text())
    strong_ids = {
        row['id'] for row in adjudication['cases']
        if str(row.get('classification', '')).startswith('strong_ground_truth')
    }
    third_policy_details = results['third26_source_attested_opened']['policies']
    strong_guard = {}
    for name, payload in third_policy_details.items():
        selected = [d for d in payload['details'] if d['id'] in strong_ids]
        strong_guard[name] = {
            'cases': len(selected),
            'hit5': sum(int(d['rank'] is not None and d['rank'] <= 5) for d in selected),
            'details': selected,
        }

    output = {
        'schema_version': 1,
        'status': 'source-attested regression control for bounded synthetic teacher fusion; all suites already opened',
        'teacher_source': '200 model-authored build-time phrase rows; no holdout query text ingested',
        'fusion': 'C0 rank1 protected; fixed G1/teacher quota in remaining four top5 slots',
        'results': results,
        'third_holdout_strong_adjudication_guard': strong_guard,
        'decision_rule': 'Do not select a policy that creates a material source-attested regression merely to improve synthetic suites. Candidate selection remains development-only until a fresh prefrozen target/teacher/query slice passes.',
    }
    out = Path('artifacts/kv-three-lane-human-regression-v31.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + '\n')

    compact = {}
    for suite, data in results.items():
        compact[suite] = {
            name: {
                'hit5': p['hit_at_5'],
                'rescues': p['rescues_vs_G4_T0'],
                'regressions': p['regressions_vs_G4_T0'],
            }
            for name, p in data['policies'].items()
        }
    print(json.dumps({'results': compact, 'strong_guard': strong_guard}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
