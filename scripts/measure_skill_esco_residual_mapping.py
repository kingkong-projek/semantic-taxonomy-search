#!/usr/bin/env python3
"""Measure ESCO mapping-type coverage specifically on frozen KV-C0 natural-text misses.

This is a diagnostic only. It does not rank with ESCO text and does not collapse mapping
semantics. The purpose is to decide whether any next ESCO lane is justified at all.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import expected_hash, fetch, load_jsonl
from evaluate_skill_c0_training_validation import build_c0, p80_skill_ids, positive_rank

MAPPINGS = ("exact_match", "close_match", "broad_match", "narrow_match")


def relation_ids(c: dict[str, Any], field: str, by_id: dict[str, dict[str, Any]]) -> list[str]:
    v = c.get(field)
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        rid = str(x.get("id") if isinstance(x, dict) else x or "")
        if rid and by_id.get(rid, {}).get("type") == "esco-skill":
            out.append(rid)
    return sorted(set(out))


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--version',default='31')
    ap.add_argument('--registry',default='research/coverage/source-adapters.json')
    ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json')
    ap.add_argument('--benchmark',default='research/benchmark/v31/training-skill-validation/cases.jsonl')
    ap.add_argument('--output',default='artifacts/skill-esco-residual-mapping-v31.json')
    args=ap.parse_args()

    cases=load_jsonl(Path(args.benchmark)); primary=[c for c in cases if c.get('primary_descriptive_nonleaky')]
    if len(cases)!=76 or len(primary)!=63: raise RuntimeError('benchmark count drift')
    registry=json.loads(Path(args.registry).read_text(encoding='utf-8')); pareto=json.loads(Path(args.pareto).read_text(encoding='utf-8')); version=str(args.version)
    url=f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json'
    body=fetch(url); sha=hashlib.sha256(body).hexdigest()
    if sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(body).get('data',{}).get('concepts')
    if not isinstance(concepts,list): raise RuntimeError('taxonomy missing concepts')
    by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    ids=p80_skill_ids(pareto); ranker,exact=build_c0(by_id,ids)

    rows=[]; misses=[]
    for case in primary:
        sid=str(case['target']['concept_id']); ranked=positive_rank(ranker,exact,str(case['query'])); c0_hit=sid in ranked[:5]
        c=by_id[sid]
        mappings={m:relation_ids(c,m,by_id) for m in MAPPINGS}
        row={'id':case['id'],'target_id':sid,'target_label':case['target']['label'],'c0_hit_at_5':c0_hit,'mappings':mappings}
        rows.append(row)
        if not c0_hit: misses.append(row)
    if len(misses)!=34: raise RuntimeError(f'expected 34 primary C0 misses, got {len(misses)}')

    def summarize(group: list[dict[str,Any]]) -> dict[str,Any]:
        n=len(group); out={'cases':n,'mapping_types':{}}
        for m in MAPPINGS:
            counts=[len(r['mappings'][m]) for r in group]
            out['mapping_types'][m]={
                'cases_with_any':sum(x>0 for x in counts),
                'coverage_pct':round(100*sum(x>0 for x in counts)/n,3) if n else 0.0,
                'edges':sum(counts),
                'single_target_cases':sum(x==1 for x in counts),
                'multi_target_cases':sum(x>1 for x in counts),
                'max_targets':max(counts,default=0),
            }
        combos=Counter()
        for r in group:
            present=tuple(m for m in MAPPINGS if r['mappings'][m])
            combos['+'.join(present) if present else 'none']+=1
        out['mapping_type_combinations']=dict(sorted(combos.items()))
        return out

    # Incremental availability among misses after the safest lanes.
    incremental={}
    covered=set()
    for m in MAPPINGS:
        ids_with={r['id'] for r in misses if r['mappings'][m]}
        incremental[m]={
            'misses_with_mapping':len(ids_with),
            'new_misses_beyond_prior_types':len(ids_with-covered),
        }
        covered |= ids_with
    incremental['any_mapping']={'misses_covered':len(covered),'misses_uncovered':len(misses)-len(covered)}

    # ESCO target text availability, kept by mapping type.
    text_availability={}
    for m in MAPPINGS:
        tids={tid for r in misses for tid in r['mappings'][m]}
        real_defs=0; labels=0
        for tid in tids:
            t=by_id[tid]; label=str(t.get('preferred_label') or '').strip(); definition=str(t.get('definition') or '').strip()
            labels+=int(bool(label)); real_defs+=int(bool(definition) and definition.casefold()!=label.casefold())
        text_availability[m]={'unique_esco_targets':len(tids),'with_label':labels,'with_real_definition':real_defs}

    result={
        'schema_version':1,'taxonomy_version':int(version),'taxonomy_sha256':sha,
        'role':'diagnostic only; no ESCO retrieval ranking performed',
        'mapping_semantics_guard':'exact/close/broad/narrow remain distinct; counts are not relevance scores',
        'primary_all':summarize(rows),'primary_c0_misses':summarize(misses),
        'incremental_miss_coverage_in_order_exact_close_broad_narrow':incremental,
        'miss_esco_text_availability':text_availability,
        'misses':misses,
    }
    p=Path(args.output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('primary_all','primary_c0_misses','incremental_miss_coverage_in_order_exact_close_broad_narrow','miss_esco_text_availability')},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
