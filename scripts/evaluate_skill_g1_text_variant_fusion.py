#!/usr/bin/env python3
"""Exploratory post-residual ablation of already-owned AF training text variants.

The second holdout has now been inspected, so this script is development evidence only.
It does not tune BM25, slot count, tokenizer or add a source/model. It keeps the validated
4-slot fusion fixed and asks whether two already-built human-text representations are worth
independent re-validation:

- single-desc: validated baseline;
- single-name-desc: same single-P80 descriptions plus AF module names;
- all-desc: broad control, attaches descriptions from any module mapping the P80 skill.

Both natural holdouts are excluded from retrieval evidence for every lane.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, ids_list, build_docs, rank, evaluate_synthetic
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1
from evaluate_skill_training_language_second_holdout import evaluate

VARIANTS = {
    'KV-G1-4slot-single-desc': 'KV-G1-single-desc',
    'KV-G1-4slot-single-name-desc': 'KV-G1-single-name-desc',
    'KV-G1-4slot-all-desc': 'KV-G1-all-desc',
}
MISS_IDS = {
    'kv.training-skill-second-holdout.006',
    'kv.training-skill-second-holdout.014',
    'kv.training-skill-second-holdout.018',
}


def relevant(case: dict[str, Any]) -> set[str]:
    if isinstance(case.get('target'), dict) and case['target'].get('concept_id'):
        return {str(case['target']['concept_id'])}
    return {str(x['concept_id']) for x in (case.get('must') or []) if isinstance(x, dict) and x.get('concept_id')}


def pos(rows: list[str], target: str) -> int | None:
    try:
        return rows.index(target) + 1
    except ValueError:
        return None


def fused_rankings(cases: list[dict[str, Any]], c0: BM25, lane: BM25, exact: dict[str, set[str]]) -> list[list[str]]:
    return [fuse_preserve_c0_top1(rank(c0, exact, str(c['query'])), rank(lane, exact, str(c['query'])), 4) for c in cases]


def main() -> int:
    first = load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'))
    second = load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl'))
    canonical = load_jsonl(Path('research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl'))
    synthetic = [c for c in load_jsonl(Path('research/benchmark/v31/synthetic-description-stress/cases.jsonl')) if c.get('product') == 'KV']
    if (len(first), len(second), len(canonical), len(synthetic)) != (35, 20, 617, 12):
        raise RuntimeError('benchmark count drift')

    holdout_hash = hashlib.sha256(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl').read_bytes()).hexdigest()
    if holdout_hash != '3960fd217deb9d7346fd78d4f281a62b614ce927e18e4ed12cbebec08a898aa7':
        raise RuntimeError('second holdout drift')

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
    c0 = BM25(docs['KV-C0'], exact)

    results: dict[str, Any] = {}
    for name, doc_name in VARIANTS.items():
        lane = BM25(docs[doc_name], exact)
        first_rows = fused_rankings(first, c0, lane, exact)
        second_rows = fused_rankings(second, c0, lane, exact)
        canonical_rows = fused_rankings(canonical, c0, lane, exact)
        # Keep the existing synthetic evaluator semantics by evaluating the fused result directly here.
        syn_rows = fused_rankings(synthetic, c0, lane, exact)
        syn = evaluate(synthetic, syn_rows, False)
        residual = []
        for case, rows in zip(second, second_rows, strict=True):
            if case.get('id') not in MISS_IDS:
                continue
            target = next(iter(relevant(case)))
            residual.append({'id': case['id'], 'target': target, 'label': str((by_id.get(target) or {}).get('preferred_label') or ''), 'rank': pos(rows, target), 'top5': [{'concept_id': cid, 'label': str((by_id.get(cid) or {}).get('preferred_label') or '')} for cid in rows[:5]]})
        results[name] = {
            'representation': doc_name,
            'first_holdout': evaluate(first, first_rows, True),
            'second_holdout_posthoc': evaluate(second, second_rows, True),
            'canonical_regression': evaluate(canonical, canonical_rows, False),
            'synthetic_stress': syn,
            'opened_residual_cases': residual,
        }

    # Strip verbose miss lists from stdout only; keep full artifact.
    summary = {}
    for name, r in results.items():
        summary[name] = {
            'first_hit5': r['first_holdout']['discovery_hit_at_5_pct'],
            'first_weighted_hit5': r['first_holdout']['weighted_discovery_hit_at_5_pct'],
            'second_hit5_posthoc': r['second_holdout_posthoc']['discovery_hit_at_5_pct'],
            'second_weighted_hit5_posthoc': r['second_holdout_posthoc']['weighted_discovery_hit_at_5_pct'],
            'canonical_top1': r['canonical_regression']['top1_pct'],
            'canonical_hit5': r['canonical_regression']['discovery_hit_at_5_pct'],
            'synthetic_hit5': r['synthetic_stress']['discovery_hit_at_5_pct'],
            'residual_ranks': {x['id']: x['rank'] for x in r['opened_residual_cases']},
        }

    out = {
        'schema_version': 1,
        'status': 'exploratory development evidence after second-holdout residual inspection; not independent validation',
        'fixed_policy': 'preserve C0 rank1; take up to four unique candidate slots from chosen human-text G1 lane; fill tail from C0',
        'retrieval_exclusion': {'first_holdout_cases': 35, 'second_holdout_cases': 20, 'excluded_module_ids': len(excluded_ids), 'excluded_normalized_texts': len(excluded_texts)},
        'coverage': coverage,
        'taxonomy_sha256': taxsha,
        'training_sha256': tsha,
        'results': results,
        'promotion_rule': 'Any changed candidate must earn new independent validation before replacing KV-G1-4slot-single-desc.',
    }
    path = Path('artifacts/skill-g1-text-variant-fusion-v31.json'); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
