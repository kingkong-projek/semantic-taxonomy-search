#!/usr/bin/env python3
"""Validate the frozen KV G1+T3 policy on prefrozen, disjoint P80 ranks 201-300.

Freeze order is contractual and asserted in the benchmark manifest:
policy -> teacher phrases -> evaluation queries -> this evaluator/retrieval.
No alternate quota, threshold, score fusion or teacher/query editing is allowed here.
Synthetic evidence tests representational generalization; AF holdouts remain the stronger
source-attested regression guard and canonical source truth is a hard lexical safety gate.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from evaluate_kv_three_lane_fusion import fuse_quotas
from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import (
    TRAINING_SHA,
    build_docs,
    fetch_training,
    ids_list,
    rank,
)

POLICY = (1, 3)
POLICY_NAME = 'C0-top1+G1-1slot+teacher-3slot'
EVIDENCE = 'synthetic_model_authored_prefrozen_validation'
POLICY_COMMIT = '61808d52e4253e912a6e1a75f02491e100457466'
TEACHER_COMMIT = 'd7464ab4a0feb946d9fc475ab7911df6664c019b'
QUERY_COMMIT = '1468f1594c5789b21efb98264a9bd3f99afa163f'


def wilson(k: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n <= 0:
        return [0.0, 0.0]
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(100 * max(0.0, center - half), 1), round(100 * min(1.0, center + half), 1)]


def metric(k: int, n: int, evidence: str = EVIDENCE) -> dict[str, Any]:
    return {
        'evidence_class': evidence,
        'hits': k,
        'n': n,
        'pct': round(100 * k / n, 1) if n else 0.0,
        'wilson95_pct': wilson(k, n),
    }


def evaluate(cases: list[dict[str, Any]], rankings: list[list[str]], evidence: str) -> dict[str, Any]:
    h1 = h5 = h10 = 0
    details = []
    for case, ranked in zip(cases, rankings, strict=True):
        target = str(case['target']['concept_id'])
        try:
            pos = ranked.index(target) + 1
        except ValueError:
            pos = None
        one = pos == 1
        five = pos is not None and pos <= 5
        ten = pos is not None and pos <= 10
        h1 += int(one); h5 += int(five); h10 += int(ten)
        details.append({
            'id': case['id'],
            'target': case['target'],
            'rank': pos,
            'top5': ranked[:5],
        })
    return {
        'top1': metric(h1, len(cases), evidence),
        'hit_at_5': metric(h5, len(cases), evidence),
        'hit_at_10': metric(h10, len(cases), evidence),
        'details': details,
    }


def paired(base: dict[str, Any], candidate: dict[str, Any], cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rescues = []
    regressions = []
    for case, b, c in zip(cases, base['details'], candidate['details'], strict=True):
        bh = b['rank'] is not None and b['rank'] <= 5
        ch = c['rank'] is not None and c['rank'] <= 5
        row = {
            'id': case['id'],
            'query': case['query'],
            'target': case['target'],
            'baseline_rank': b['rank'],
            'candidate_rank': c['rank'],
            'candidate_top5': c['top5'],
        }
        if ch and not bh:
            rescues.append(row)
        elif bh and not ch:
            regressions.append(row)
    return rescues, regressions


def teacher_rows() -> list[dict[str, Any]]:
    paths = [
        'research/enrichment/v31/model-teacher-kv-top100/phrases.jsonl',
        'research/enrichment/v31/model-teacher-kv-ranks101-200/phrases.jsonl',
        'research/enrichment/v31/model-teacher-kv-ranks201-300/phrases.jsonl',
    ]
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(load_jsonl(Path(path)))
    return rows


def build_rankers(
    by_id: dict[str, dict[str, Any]],
    ids: list[str],
    modules: list[dict[str, Any]],
    teacher_by_id: dict[str, list[str]],
    excluded_cases: list[dict[str, Any]],
) -> tuple[BM25, BM25, BM25, dict[str, set[str]], dict[str, Any]]:
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
    return c0, g1, teacher, exact, coverage


def run_policy_suite(
    cases: list[dict[str, Any]],
    c0: BM25,
    g1: BM25,
    teacher: BM25,
    exact: dict[str, set[str]],
    evidence: str,
) -> dict[str, Any]:
    baseline_rows = []
    candidate_rows = []
    c0_rows = []
    g1_rows = []
    teacher_rows_ = []
    for case in cases:
        q = str(case['query'])
        a = rank(c0, exact, q)
        b = rank(g1, exact, q)
        t = rank(teacher, exact, q)
        c0_rows.append(a); g1_rows.append(b); teacher_rows_.append(t)
        baseline_rows.append(fuse_quotas(a, b, t, 4, 0))
        candidate_rows.append(fuse_quotas(a, b, t, *POLICY))
    base = evaluate(cases, baseline_rows, evidence)
    cand = evaluate(cases, candidate_rows, evidence)
    rescues, regressions = paired(base, cand, cases)
    misses = [
        {'id': c['id'], 'query': c['query'], 'target': c['target'], 'rank': d['rank'], 'top5': d['top5']}
        for c, d in zip(cases, cand['details'], strict=True)
        if d['rank'] is None or d['rank'] > 5
    ]
    return {
        'C0': evaluate(cases, c0_rows, evidence),
        'G1': evaluate(cases, g1_rows, evidence),
        'teacher': evaluate(cases, teacher_rows_, evidence),
        'G1_4slot_baseline': base,
        'frozen_G1_T3_candidate': cand,
        'rescues_vs_G1_4slot': rescues,
        'regressions_vs_G1_4slot': regressions,
        'candidate_hit5_misses': misses,
    }


def strip_details(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if k != 'details'}


def main() -> int:
    manifest = json.loads(Path('research/benchmark/v31/model-authored-kv-ranks201-300/manifest.json').read_text())
    if manifest['freeze_order']['policy_commit'] != POLICY_COMMIT:
        raise RuntimeError('policy freeze commit drift')
    if manifest['freeze_order']['teacher_commit'] != TEACHER_COMMIT:
        raise RuntimeError('teacher freeze commit drift')
    if manifest['freeze_order']['query_commit'] != QUERY_COMMIT:
        raise RuntimeError('query freeze commit drift')
    if manifest['frozen_policy']['name'] != POLICY_NAME or not manifest['evaluation_policy']['no_alternate_policy_search']:
        raise RuntimeError('frozen policy contract drift')

    new = load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks201-300/cases.jsonl'))
    prior1 = load_jsonl(Path('research/benchmark/v31/model-authored-kv-100/cases.jsonl'))
    prior2 = load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks101-200/cases.jsonl'))
    if (len(new), len(prior1), len(prior2)) != (100, 100, 100):
        raise RuntimeError('synthetic benchmark count drift')

    new_ranks = [int(c['target']['p80_rank']) for c in new]
    if new_ranks != list(range(201, 301)):
        raise RuntimeError('new rank slice drift')
    new_ids = [str(c['target']['concept_id']) for c in new]
    prior_ids = {str(c['target']['concept_id']) for c in [*prior1, *prior2]}
    if len(set(new_ids)) != 100 or set(new_ids) & prior_ids:
        raise RuntimeError('target disjointness failed')

    new_queries = [norm(c['query']) for c in new]
    prior_queries = {norm(c['query']) for c in [*prior1, *prior2]}
    if len(set(new_queries)) != 100:
        raise RuntimeError('duplicate new normalized query')
    exact_prior_overlap = sorted(set(new_queries) & prior_queries)
    if exact_prior_overlap:
        raise RuntimeError(f'exact query overlap with prior suite: {exact_prior_overlap[:3]}')

    teachers = teacher_rows()
    if len(teachers) != 300:
        raise RuntimeError(f'teacher count drift {len(teachers)}')
    teacher_by_id: dict[str, list[str]] = {}
    phrase_norms: list[str] = []
    for row in teachers:
        cid = str(row['concept_id'])
        if cid in teacher_by_id:
            raise RuntimeError(f'duplicate teacher target {cid}')
        phrases = [str(x) for x in row.get('phrases') or []]
        if len(phrases) != 3:
            raise RuntimeError(f'teacher phrase count {cid}')
        teacher_by_id[cid] = phrases
        phrase_norms.extend(norm(x) for x in phrases)
    if len(set(phrase_norms)) != 900:
        raise RuntimeError('duplicate normalized teacher phrase')
    exact_teacher_query_overlap = sorted(set(phrase_norms) & set(new_queries))
    if exact_teacher_query_overlap:
        raise RuntimeError(f'exact teacher/query overlap: {exact_teacher_query_overlap[:3]}')

    direct_full_label_mentions = sum(
        int(bool(norm(c['target']['label']) and norm(c['target']['label']) in norm(c['query'])))
        for c in new
    )

    registry = json.loads(Path('research/coverage/source-adapters.json').read_text())
    pareto = json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    expected_slice = pareto['skill']['ranked_p95'][200:300]
    if [str(r['concept_id']) for r in expected_slice] != new_ids:
        raise RuntimeError('P80 target identity drift')

    tax_body = fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json')
    tax_sha = hashlib.sha256(tax_body).hexdigest()
    if tax_sha != expected_hash(registry, 'taxonomy-common-relations'):
        raise RuntimeError('taxonomy source drift')
    concepts = json.loads(tax_body).get('data', {}).get('concepts') or []
    by_id = {str(c['id']): c for c in concepts if isinstance(c, dict) and c.get('id')}
    ids = p80_skill_ids(pareto)

    training_body = fetch_training()
    training_sha = hashlib.sha256(training_body).hexdigest()
    if training_sha != TRAINING_SHA:
        raise RuntimeError('training source drift')
    tj = json.loads(training_body)
    modules = (tj.get('data') or tj.get('moduler') or tj.get('modules')) if isinstance(tj, dict) else tj
    if not isinstance(modules, list):
        raise RuntimeError('unexpected training mapping root')

    # Primary fresh synthetic gate: no AF query text is part of this suite, so normal
    # production-form G1 evidence is available. No rank201-300 query text can enter it.
    c0, g1, teacher, exact, coverage = build_rankers(by_id, ids, modules, teacher_by_id, [])
    new_result = run_policy_suite(new, c0, g1, teacher, exact, EVIDENCE)

    # Cross-target synthetic diagnostics only; never used for policy tuning here.
    prior2_result = run_policy_suite(prior2, c0, g1, teacher, exact, 'synthetic_model_authored_opened_regression_diagnostic')

    # Source-attested controls mirror each suite's established G1 evidence exclusions.
    first = load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'))
    second = load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl'))
    third = load_jsonl(Path('research/benchmark/v31/training-skill-third-holdout/cases.jsonl'))
    if (len(first), len(second), len(third)) != (35, 20, 26):
        raise RuntimeError('AF holdout count drift')
    human_suites = {
        'first35': (first, first),
        'second20': (second, [*first, *second]),
        'third26': (third, [*first, *second, *third]),
    }
    human_results = {}
    for name, (cases, excluded) in human_suites.items():
        hc0, hg1, ht, hexact, hcoverage = build_rankers(by_id, ids, modules, teacher_by_id, excluded)
        result = run_policy_suite(cases, hc0, hg1, ht, hexact, 'source_attested_AF_description_regression_control')
        human_results[name] = {'coverage': hcoverage, 'result': result}

    # Canonical source truth must remain intact under the exact frozen fusion policy.
    canonical = load_jsonl(Path('research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl'))
    if len(canonical) != 617:
        raise RuntimeError('canonical benchmark count drift')
    canonical_top1 = canonical_hit5 = 0
    canonical_misses = []
    for case in canonical:
        rel = {str(x['concept_id']) for x in case['must']}
        q = str(case['query'])
        fused = fuse_quotas(rank(c0, exact, q), rank(g1, exact, q), rank(teacher, exact, q), *POLICY)
        t1 = bool(fused and fused[0] in rel)
        h5 = any(x in rel for x in fused[:5])
        canonical_top1 += int(t1); canonical_hit5 += int(h5)
        if not t1 or not h5:
            canonical_misses.append({'id': case['id'], 'query': q, 'expected': sorted(rel), 'top5': fused[:5]})

    result = {
        'schema_version': 1,
        'status': 'prefrozen validation of the fixed G1+T3 candidate; no alternate-policy search',
        'taxonomy_version': 31,
        'taxonomy_sha256': tax_sha,
        'training_sha256': training_sha,
        'policy': {'name': POLICY_NAME, 'g1_slots': 1, 'teacher_slots': 3},
        'freeze_order': {'policy_commit': POLICY_COMMIT, 'teacher_commit': TEACHER_COMMIT, 'query_commit': QUERY_COMMIT},
        'disjointness': {
            'new_cases': len(new),
            'target_overlap_with_ranks1_200': 0,
            'exact_query_overlap_with_prior_synthetic': len(exact_prior_overlap),
            'teacher_phrases_total': len(phrase_norms),
            'exact_teacher_query_overlap': len(exact_teacher_query_overlap),
            'direct_full_label_mentions': direct_full_label_mentions,
        },
        'production_form_G1_coverage': coverage,
        'primary_ranks201_300': new_result,
        'prior_ranks101_200_cross_target_diagnostic': prior2_result,
        'source_attested_regression_control': human_results,
        'canonical_guard': {
            'cases': len(canonical),
            'top1': metric(canonical_top1, len(canonical), 'canonical_source_truth_guard'),
            'hit_at_5': metric(canonical_hit5, len(canonical), 'canonical_source_truth_guard'),
            'misses': canonical_misses,
        },
        'interpretation_boundary': 'Synthetic teacher/query evidence tests frozen representational generalization and ranking competition, not independent human accuracy. AF suites are source-attested but small and some mappings are ambiguous. No policy promotion should ignore their paired regressions.',
    }
    out = Path('artifacts/kv-g1-t3-ranks201-300-v31.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n')

    compact_human = {}
    for name, payload in human_results.items():
        r = payload['result']
        compact_human[name] = {
            'baseline': strip_details(r['G1_4slot_baseline']),
            'candidate': strip_details(r['frozen_G1_T3_candidate']),
            'rescues': len(r['rescues_vs_G1_4slot']),
            'regressions': len(r['regressions_vs_G1_4slot']),
        }
    print(json.dumps({
        'disjointness': result['disjointness'],
        'new': {
            'C0': strip_details(new_result['C0']),
            'G1': strip_details(new_result['G1']),
            'teacher': strip_details(new_result['teacher']),
            'baseline': strip_details(new_result['G1_4slot_baseline']),
            'candidate': strip_details(new_result['frozen_G1_T3_candidate']),
            'rescues': len(new_result['rescues_vs_G1_4slot']),
            'regressions': len(new_result['regressions_vs_G1_4slot']),
            'misses': len(new_result['candidate_hit5_misses']),
        },
        'human': compact_human,
        'canonical': result['canonical_guard'],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
