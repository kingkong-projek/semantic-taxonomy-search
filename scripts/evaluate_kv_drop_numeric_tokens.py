#!/usr/bin/env python3
"""Test the smallest general tokenizer correction for KV semantic fallback.

A diagnostic found that a source-attested course description containing enumerated sections
(1), (2), (3), ... gave the skill "Arbete på väg steg 2" a large accidental BM25 boost.
This ablation changes only semantic BM25 token streams: pure integer tokens are removed
from both documents and queries. Exact canonical surfaces are preserved unchanged, so an
exact query such as a credential/product label containing digits still gets the normal
exact-surface dominance.

No stopword list, stemming, subwords, score calibration, learned fusion or new model lane is
introduced. The current G1+teacher representation and frozen C0-top1 + G1-1slot +
teacher-3slot fusion remain unchanged. All suites here are already opened; a winning
sanitation rule must be frozen before the untouched ranks 301-316 gate is authored.
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
VARIANTS = ('current', 'drop_pure_numeric')


def semantic_tokens(text: Any, variant: str) -> list[str]:
    ts = tokens(text)
    if variant == 'current':
        return ts
    if variant == 'drop_pure_numeric':
        return [t for t in ts if not t.isdigit()]
    raise RuntimeError(variant)


def sanitize_docs(docs: dict[str, list[str]], variant: str) -> dict[str, list[str]]:
    if variant == 'current':
        return {cid: list(ts) for cid, ts in docs.items()}
    return {cid: [t for t in ts if not t.isdigit()] for cid, ts in docs.items()}


def rank_semantic(ranker: BM25, exact: dict[str, set[str]], query: str, variant: str) -> list[str]:
    q = semantic_tokens(query, variant)
    nq = norm(query)
    scored = []
    for cid in ranker.documents:
        score = ranker.score(q, cid)
        # Preserve exact canonical/alias behavior exactly as the established lexical lane.
        if nq and nq in exact.get(cid, set()):
            score += 1_000_000.0
        if score > 0:
            scored.append((score, cid))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [cid for _, cid in scored]


def wilson(k: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n <= 0:
        return [0.0, 0.0]
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(100 * max(0.0, center - half), 1), round(100 * min(1.0, center + half), 1)]


def metric(k: int, n: int) -> dict[str, Any]:
    return {'hits': k, 'n': n, 'pct': round(100 * k / n, 1) if n else 0.0, 'wilson95_pct': wilson(k, n)}


def evaluate(cases: list[dict[str, Any]], rankings: list[list[str]]) -> dict[str, Any]:
    h1 = h5 = h10 = 0
    details = []
    for case, ranked in zip(cases, rankings, strict=True):
        target = str(case['target']['concept_id'])
        try:
            pos = ranked.index(target) + 1
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


def paired(base: dict[str, Any], candidate: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    rescues = []
    regressions = []
    rank_moves = []
    for case, b, c in zip(cases, base['details'], candidate['details'], strict=True):
        br = b['rank']; cr = c['rank']
        bh = br is not None and br <= 5
        ch = cr is not None and cr <= 5
        row = {
            'id': case['id'],
            'target': case['target'],
            'baseline_rank': br,
            'candidate_rank': cr,
            'candidate_top5': c['top5'],
        }
        if ch and not bh:
            rescues.append(row)
        elif bh and not ch:
            regressions.append(row)
        if br != cr:
            rank_moves.append(row)
    return {'rescues': rescues, 'regressions': regressions, 'rank_moves': rank_moves}


def load_teacher() -> dict[str, list[str]]:
    rows = []
    for path in (
        'research/enrichment/v31/model-teacher-kv-top100/phrases.jsonl',
        'research/enrichment/v31/model-teacher-kv-ranks101-200/phrases.jsonl',
        'research/enrichment/v31/model-teacher-kv-ranks201-300/phrases.jsonl',
    ):
        rows.extend(load_jsonl(Path(path)))
    if len(rows) != 300:
        raise RuntimeError(f'teacher count drift {len(rows)}')
    out: dict[str, list[str]] = {}
    for row in rows:
        cid = str(row['concept_id'])
        phrases = [str(x) for x in row.get('phrases') or []]
        if cid in out or len(phrases) != 3:
            raise RuntimeError(f'teacher identity/phrase drift {cid}')
        out[cid] = phrases
    return out


def build_rankers(
    by_id: dict[str, dict[str, Any]],
    ids: list[str],
    modules: list[dict[str, Any]],
    teacher_by_id: dict[str, list[str]],
    excluded_cases: list[dict[str, Any]],
    variant: str,
) -> tuple[BM25, BM25, BM25, dict[str, set[str]], dict[str, Any]]:
    exids = {mid for c in excluded_cases for mid in ids_list(c.get('module_ids'))}
    extexts = {norm(c['query']) for c in excluded_cases}
    docs, exact, coverage = build_docs(by_id, ids, modules, exids, extexts)
    c0_docs = sanitize_docs(docs['KV-C0'], variant)
    g1_docs = sanitize_docs(docs['KV-G1-single-desc'], variant)
    teacher_docs = {
        sid: [*g1_docs[sid], *semantic_tokens(' '.join(teacher_by_id.get(sid, [])), variant)]
        for sid in ids
    }
    return BM25(c0_docs, exact), BM25(g1_docs, exact), BM25(teacher_docs, exact), exact, coverage


def run_suite(
    cases: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    ids: list[str],
    modules: list[dict[str, Any]],
    teacher_by_id: dict[str, list[str]],
    excluded_cases: list[dict[str, Any]],
    variant: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    c0, g1, teacher, exact, coverage = build_rankers(by_id, ids, modules, teacher_by_id, excluded_cases, variant)
    rows = []
    for case in cases:
        q = str(case['query'])
        a = rank_semantic(c0, exact, q, variant)
        b = rank_semantic(g1, exact, q, variant)
        t = rank_semantic(teacher, exact, q, variant)
        rows.append(fuse_quotas(a, b, t, *POLICY))
    return evaluate(cases, rows), coverage


def main() -> int:
    teacher_by_id = load_teacher()
    registry = json.loads(Path('research/coverage/source-adapters.json').read_text())
    pareto = json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())

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
        raise RuntimeError('training source root drift')

    first = load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'))
    second = load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl'))
    third = load_jsonl(Path('research/benchmark/v31/training-skill-third-holdout/cases.jsonl'))
    r101 = load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks101-200/cases.jsonl'))
    r201 = load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks201-300/cases.jsonl'))
    if (len(first), len(second), len(third), len(r101), len(r201)) != (35, 20, 26, 100, 100):
        raise RuntimeError('suite count drift')

    suites = {
        'AF_first35_opened': (first, first),
        'AF_second20_opened': (second, [*first, *second]),
        'AF_third26_opened': (third, [*first, *second, *third]),
        'synthetic_ranks101_200_opened': (r101, []),
        'synthetic_ranks201_300_opened': (r201, []),
    }
    results: dict[str, Any] = {}
    for suite_name, (cases, excluded) in suites.items():
        variants = {}
        coverage = None
        for variant in VARIANTS:
            ev, cv = run_suite(cases, by_id, ids, modules, teacher_by_id, excluded, variant)
            variants[variant] = ev
            coverage = cv
        delta = paired(variants['current'], variants['drop_pure_numeric'], cases)
        results[suite_name] = {
            'cases': len(cases),
            'coverage': coverage,
            'current': variants['current'],
            'drop_pure_numeric': variants['drop_pure_numeric'],
            'rescues': delta['rescues'],
            'regressions': delta['regressions'],
            'rank_moves': delta['rank_moves'],
        }

    # Canonical guard: exact surfaces must remain fully intact. Evaluate both policies from
    # scratch with normal production G1 evidence.
    canonical = load_jsonl(Path('research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl'))
    if len(canonical) != 617:
        raise RuntimeError('canonical count drift')
    canonical_results = {}
    for variant in VARIANTS:
        c0, g1, teacher, exact, _ = build_rankers(by_id, ids, modules, teacher_by_id, [], variant)
        h1 = h5 = 0
        misses = []
        for case in canonical:
            rel = {str(x['concept_id']) for x in case['must']}
            q = str(case['query'])
            fused = fuse_quotas(
                rank_semantic(c0, exact, q, variant),
                rank_semantic(g1, exact, q, variant),
                rank_semantic(teacher, exact, q, variant),
                *POLICY,
            )
            t1 = bool(fused and fused[0] in rel)
            five = any(x in rel for x in fused[:5])
            h1 += int(t1); h5 += int(five)
            if not t1 or not five:
                misses.append({'id': case['id'], 'query': q, 'expected': sorted(rel), 'top5': fused[:5]})
        canonical_results[variant] = {'top1': metric(h1, len(canonical)), 'hit5': metric(h5, len(canonical)), 'misses': misses}

    # Pin the exact known diagnostic case as an explicit falsification target, but do not
    # tune any rule specifically for it.
    known = next(c for c in second if c['id'] == 'kv.training-skill-second-holdout.017')
    known_positions = {
        variant: next(d for d in results['AF_second20_opened'][variant]['details'] if d['id'] == known['id'])
        for variant in VARIANTS
    }

    human_suites = ('AF_first35_opened', 'AF_second20_opened', 'AF_third26_opened')
    human_current = sum(results[s]['current']['hit_at_5']['hits'] for s in human_suites)
    human_candidate = sum(results[s]['drop_pure_numeric']['hit_at_5']['hits'] for s in human_suites)
    human_rescues = sum(len(results[s]['rescues']) for s in human_suites)
    human_regressions = sum(len(results[s]['regressions']) for s in human_suites)

    output = {
        'schema_version': 1,
        'status': 'opened-suite development ablation; no promotion without fresh untouched gate',
        'change': 'remove pure integer tokens from semantic BM25 document/query token streams only; preserve exact canonical surfaces unchanged',
        'fusion': 'unchanged C0-top1 + G1-1slot + teacher-3slot',
        'teacher_representation': 'unchanged G1 + teacher phrases',
        'taxonomy_sha256': tax_sha,
        'training_sha256': training_sha,
        'results': results,
        'canonical_guard': canonical_results,
        'known_boundary_regression_case': {'case': known, 'positions': known_positions},
        'aggregate_source_attested': {
            'queries': sum(len(suites[s][0]) for s in human_suites),
            'current_hits_at_5': human_current,
            'drop_numeric_hits_at_5': human_candidate,
            'rescues': human_rescues,
            'regressions': human_regressions,
        },
        'decision_rule': 'Only nominate drop_pure_numeric if canonical stays 617/617, it removes the proven numbering artifact without material source-attested Hit@5 regression, and synthetic diagnostics do not reveal a broad collapse. If nominated, freeze before authoring any ranks301-316 teacher/query data.',
    }
    out = Path('artifacts/kv-drop-numeric-tokens-v31.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + '\n')

    def compact(ev: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in ev.items() if k != 'details'}
    print(json.dumps({
        'aggregate_source_attested': output['aggregate_source_attested'],
        'known_case_positions': {k: {'rank': v['rank'], 'top5': v['top5']} for k, v in known_positions.items()},
        'suites': {
            s: {
                'current': compact(r['current']),
                'drop_pure_numeric': compact(r['drop_pure_numeric']),
                'rescues': len(r['rescues']),
                'regressions': len(r['regressions']),
                'rank_moves': len(r['rank_moves']),
            }
            for s, r in results.items()
        },
        'canonical': canonical_results,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
