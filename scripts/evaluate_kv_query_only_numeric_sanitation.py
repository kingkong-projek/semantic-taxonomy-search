#!/usr/bin/env python3
"""Development ablation: drop pure integer tokens only from G1/teacher queries.

All indexed documents, C0 ranking, exact surfaces, fusion quotas and teacher representation stay
unchanged. This tests whether the proven numbered-section artifact can be removed without the
BM25 document-length side effect that regressed frozen Svetsteknik. All suites are now opened;
this script can nominate a future candidate but cannot independently validate/promo it.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_kv_drop_numeric_tokens import evaluate, metric, paired
from evaluate_kv_final_p80_gate import teacher_map
from evaluate_kv_three_lane_fusion import fuse_quotas
from evaluate_kv_drop_numeric_expansion_only import rankers
from evaluate_p80_lexical_ablation import expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, rank


def rank_query_only(ranker,exact,q:str)->list[str]:
    qt=[t for t in tokens(q) if not t.isdigit()]; nq=norm(q); scored=[]
    for cid in ranker.documents:
        s=ranker.score(qt,cid)
        if nq and nq in exact.get(cid,set()): s+=1_000_000.0
        if s>0: scored.append((s,cid))
    scored.sort(key=lambda x:(-x[0],x[1])); return [cid for _,cid in scored]


def run_variant(cases,by_id,ids,modules,teacher,excluded,query_only:bool):
    c0,g1,t,exact,coverage=rankers(by_id,ids,modules,teacher,excluded,'current')
    rows=[]
    for case in cases:
        q=str(case['query']); a=rank(c0,exact,q)
        if query_only:
            b=rank_query_only(g1,exact,q); tr=rank_query_only(t,exact,q)
        else:
            b=rank(g1,exact,q); tr=rank(t,exact,q)
        rows.append(fuse_quotas(a,b,tr,1,3))
    return evaluate(cases,rows),coverage


def canonical(by_id,ids,modules,teacher,query_only):
    cases=load_jsonl(Path('research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl'))
    c0,g1,t,exact,_=rankers(by_id,ids,modules,teacher,[],'current')
    h1=h5=0; misses=[]
    for case in cases:
        q=str(case['query']); rel={str(x['concept_id']) for x in case['must']}; a=rank(c0,exact,q)
        b=rank_query_only(g1,exact,q) if query_only else rank(g1,exact,q)
        tr=rank_query_only(t,exact,q) if query_only else rank(t,exact,q)
        fused=fuse_quotas(a,b,tr,1,3); one=bool(fused and fused[0] in rel); five=any(x in rel for x in fused[:5])
        h1+=int(one); h5+=int(five)
        if not one or not five: misses.append({'id':case['id'],'query':q,'expected':sorted(rel),'top5':fused[:5]})
    return {'top1':metric(h1,len(cases)),'hit5':metric(h5,len(cases)),'misses':misses}


def compact(ev:dict[str,Any])->dict[str,Any]: return {k:v for k,v in ev.items() if k!='details'}


def main()->int:
    teacher=teacher_map(True)
    registry=json.loads(Path('research/coverage/source-adapters.json').read_text()); pareto=json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    tax=fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json'); tsha=hashlib.sha256(tax).hexdigest()
    if tsha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy drift')
    concepts=json.loads(tax).get('data',{}).get('concepts') or []; by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}; ids=p80_skill_ids(pareto)
    trb=fetch_training(); trsha=hashlib.sha256(trb).hexdigest()
    if trsha!=TRAINING_SHA: raise RuntimeError('training drift')
    tj=json.loads(trb); modules=(tj.get('data') or tj.get('moduler') or tj.get('modules')) if isinstance(tj,dict) else tj

    first=load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl')); second=load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl')); third=load_jsonl(Path('research/benchmark/v31/training-skill-third-holdout/cases.jsonl'))
    r101=load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks101-200/cases.jsonl')); r201=load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks201-300/cases.jsonl')); r301=load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks301-316/cases.jsonl'))
    suites={'AF_first35':(first,first),'AF_second20':(second,[*first,*second]),'AF_third26':(third,[*first,*second,*third]),'synthetic_ranks101_200':(r101,[]),'synthetic_ranks201_300':(r201,[]),'synthetic_ranks301_316_opened':(r301,[])}
    results={}
    for name,(cases,excluded) in suites.items():
        cur,cov=run_variant(cases,by_id,ids,modules,teacher,excluded,False); cand,_=run_variant(cases,by_id,ids,modules,teacher,excluded,True); d=paired(cur,cand,cases)
        results[name]={'cases':len(cases),'coverage':cov,'current':cur,'query_only_numeric':cand,'rescues':d['rescues'],'regressions':d['regressions'],'rank_moves':d['rank_moves']}
    can_cur=canonical(by_id,ids,modules,teacher,False); can_cand=canonical(by_id,ids,modules,teacher,True)
    human=('AF_first35','AF_second20','AF_third26')
    agg={'queries':81,'current_hit5':sum(results[s]['current']['hit_at_5']['hits'] for s in human),'candidate_hit5':sum(results[s]['query_only_numeric']['hit_at_5']['hits'] for s in human),'rescues':sum(len(results[s]['rescues']) for s in human),'regressions':sum(len(results[s]['regressions']) for s in human)}
    known='kv.training-skill-second-holdout.017'; fresh='kv.model-authored-301-316.310'
    def detail(suite,variant,cid): return next(x for x in results[suite][variant]['details'] if x['id']==cid)
    output={'schema_version':1,'status':'opened-data development ablation; not independent validation','change':'remove pure integer tokens from G1/teacher query scoring only; documents, C0, exact surfaces and fusion unchanged','aggregate_source_attested':agg,'canonical':{'current':can_cur,'candidate':can_cand},'known_numbered_AF_case':{'current':detail('AF_second20','current',known),'candidate':detail('AF_second20','query_only_numeric',known)},'known_no_number_fresh_case':{'current':detail('synthetic_ranks301_316_opened','current',fresh),'candidate':detail('synthetic_ranks301_316_opened','query_only_numeric',fresh)},'results':results,'decision_rule':'Nominate for a new independent prefrozen gate only if canonical stays 617/617 Top1+Hit5, source-attested gains are preserved with zero Hit5 regression, no-number cases are ranking-identical, and opened synthetic suites show no Hit5 regression. Do not promote from these opened suites alone.'}
    out=Path('artifacts/kv-query-only-numeric-sanitation-v31.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(output,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'aggregate_source_attested':agg,'canonical_candidate':can_cand,'known_AF':output['known_numbered_AF_case'],'known_fresh':output['known_no_number_fresh_case'],'synthetic':{s:{'current':compact(results[s]['current']),'candidate':compact(results[s]['query_only_numeric']),'rescues':len(results[s]['rescues']),'regressions':len(results[s]['regressions']),'rank_moves':len(results[s]['rank_moves'])} for s in ('synthetic_ranks101_200','synthetic_ranks201_300','synthetic_ranks301_316_opened')}},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
