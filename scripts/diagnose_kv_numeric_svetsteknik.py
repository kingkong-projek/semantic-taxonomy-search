#!/usr/bin/env python3
"""Diagnose the single fresh rank301-316 regression caused by numeric sanitation.

Diagnostic only. Does not change policy, teacher phrases, queries or retrieval behavior.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evaluate_kv_drop_numeric_expansion_only import rankers, no_numbers
from evaluate_kv_final_p80_gate import teacher_map
from evaluate_kv_three_lane_fusion import fuse_quotas
from evaluate_p80_lexical_ablation import expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, rank

CASE_ID='kv.model-authored-301-316.310'
TARGET='agUF_zx8_iKE'


def semantic_rank(ranker,exact,q,variant):
    if variant=='current': return rank(ranker,exact,q)
    qt=no_numbers(tokens(q)); nq=norm(q); scored=[]
    for cid in ranker.documents:
        s=ranker.score(qt,cid)
        if nq and nq in exact.get(cid,set()): s+=1_000_000.0
        if s>0: scored.append((s,cid))
    scored.sort(key=lambda x:(-x[0],x[1])); return [cid for _,cid in scored]


def contributions(ranker,q,cid):
    qts=tokens(q); tf=ranker.tf[cid]; dl=ranker.lengths[cid]; rows=[]
    for term in sorted(set(qts)):
        f=tf.get(term,0)
        if not f: continue
        idf=ranker.idf.get(term,0.0)
        denom=f+ranker.k1*(1-ranker.b+ranker.b*dl/max(ranker.avgdl,1e-9))
        val=idf*(f*(ranker.k1+1)/denom)
        rows.append({'term':term,'doc_tf':f,'idf':round(idf,6),'contribution':round(val,6)})
    rows.sort(key=lambda x:(-x['contribution'],x['term']))
    return rows


def main()->int:
    cases=load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks301-316/cases.jsonl'))
    case=next(c for c in cases if c['id']==CASE_ID)
    if str(case['target']['concept_id'])!=TARGET: raise RuntimeError('target drift')
    teacher=teacher_map(True)
    registry=json.loads(Path('research/coverage/source-adapters.json').read_text()); pareto=json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    tax=fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json')
    if hashlib.sha256(tax).hexdigest()!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy drift')
    concepts=json.loads(tax).get('data',{}).get('concepts') or []; by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    trb=fetch_training()
    if hashlib.sha256(trb).hexdigest()!=TRAINING_SHA: raise RuntimeError('training drift')
    tj=json.loads(trb); modules=(tj.get('data') or tj.get('moduler') or tj.get('modules')) if isinstance(tj,dict) else tj
    ids=p80_skill_ids(pareto); q=str(case['query'])

    variants={}
    for variant in ('current','drop_numeric_expansion_only'):
        c0,g1,t,exact,coverage=rankers(by_id,ids,modules,teacher,[],variant)
        a=rank(c0,exact,q); b=semantic_rank(g1,exact,q,variant); tr=semantic_rank(t,exact,q,variant)
        fused=fuse_quotas(a,b,tr,1,3)
        variants[variant]={
            'positions':{
                'C0':a.index(TARGET)+1 if TARGET in a else None,
                'G1':b.index(TARGET)+1 if TARGET in b else None,
                'teacher':tr.index(TARGET)+1 if TARGET in tr else None,
                'fused':fused.index(TARGET)+1 if TARGET in fused else None,
            },
            'top5':{
                'G1':[(cid,by_id.get(cid,{}).get('preferred_label')) for cid in b[:5]],
                'teacher':[(cid,by_id.get(cid,{}).get('preferred_label')) for cid in tr[:5]],
                'fused':[(cid,by_id.get(cid,{}).get('preferred_label')) for cid in fused[:5]],
            },
            'target':{
                'g1_doc_length':g1.lengths[TARGET],
                'g1_avgdl':round(g1.avgdl,3),
                'teacher_doc_length':t.lengths[TARGET],
                'teacher_avgdl':round(t.avgdl,3),
                'g1_score':round(g1.score(no_numbers(tokens(q)) if variant!='current' else tokens(q),TARGET),6),
                'teacher_score':round(t.score(no_numbers(tokens(q)) if variant!='current' else tokens(q),TARGET),6),
                'teacher_contributions':contributions(t,q,TARGET),
                'g1_contributions':contributions(g1,q,TARGET),
                'teacher_phrases':teacher[TARGET],
            },
            'coverage':coverage,
        }
    result={'schema_version':1,'status':'diagnostic only; frozen inputs unchanged','case':case,'query_tokens':tokens(q),'variants':variants}
    out=Path('artifacts/kv-numeric-svetsteknik-diagnostic.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
