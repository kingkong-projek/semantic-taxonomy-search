#!/usr/bin/env python3
"""Development ablation of teacher-lane evidence separation under the frozen G1+T3 fusion.

No new model class or fusion policy is introduced. We vary only which build-time text is
compiled into the existing teacher BM25 lane:
  1) current: G1 + teacher phrases
  2) C0 + teacher phrases
  3) teacher phrases only
All evaluated suites are already opened; any winner requires a fresh untouched gate.
"""
from __future__ import annotations

import hashlib, json, math
from pathlib import Path
from typing import Any

from evaluate_kv_three_lane_fusion import fuse_quotas
from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, build_docs, fetch_training, ids_list, rank

POLICY=(1,3)
LANES=('G1_plus_teacher','C0_plus_teacher','teacher_only')


def wilson(k:int,n:int,z:float=1.959963984540054)->list[float]:
    if not n: return [0.0,0.0]
    p=k/n; den=1+z*z/n; c=(p+z*z/(2*n))/den; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [round(100*max(0,c-h),1),round(100*min(1,c+h),1)]

def metric(k:int,n:int)->dict[str,Any]: return {'hits':k,'n':n,'pct':round(100*k/n,1) if n else 0.0,'wilson95_pct':wilson(k,n)}

def evaluate(cases:list[dict[str,Any]], rows:list[list[str]])->dict[str,Any]:
    h1=h5=h10=0; details=[]
    for c,r in zip(cases,rows,strict=True):
        tid=str(c['target']['concept_id'])
        try: pos=r.index(tid)+1
        except ValueError: pos=None
        h1+=int(pos==1); h5+=int(pos is not None and pos<=5); h10+=int(pos is not None and pos<=10)
        details.append({'id':c['id'],'target':c['target'],'rank':pos,'top5':r[:5]})
    return {'top1':metric(h1,len(cases)),'hit_at_5':metric(h5,len(cases)),'hit_at_10':metric(h10,len(cases)),'details':details}

def paired(base:dict[str,Any],cand:dict[str,Any],cases:list[dict[str,Any]])->dict[str,Any]:
    resc=[]; regs=[]
    for c,b,x in zip(cases,base['details'],cand['details'],strict=True):
        bh=b['rank'] is not None and b['rank']<=5; xh=x['rank'] is not None and x['rank']<=5
        row={'id':c['id'],'target':c['target'],'base_rank':b['rank'],'candidate_rank':x['rank'],'candidate_top5':x['top5']}
        if xh and not bh: resc.append(row)
        elif bh and not xh: regs.append(row)
    return {'rescues':resc,'regressions':regs}

def build_teacher_docs(name:str,docs:dict[str,dict[str,list[str]]],ids:list[str],phrases:dict[str,list[str]])->dict[str,list[str]]:
    out={}
    for sid in ids:
        pt=tokens(' '.join(phrases.get(sid,[])))
        if name=='G1_plus_teacher': out[sid]=[*docs['KV-G1-single-desc'][sid],*pt]
        elif name=='C0_plus_teacher': out[sid]=[*docs['KV-C0'][sid],*pt]
        elif name=='teacher_only': out[sid]=pt
        else: raise RuntimeError(name)
    return out

def main()->int:
    teachers=[]
    for p in ('research/enrichment/v31/model-teacher-kv-top100/phrases.jsonl','research/enrichment/v31/model-teacher-kv-ranks101-200/phrases.jsonl','research/enrichment/v31/model-teacher-kv-ranks201-300/phrases.jsonl'):
        teachers.extend(load_jsonl(Path(p)))
    if len(teachers)!=300: raise RuntimeError('teacher count drift')
    phrases={str(x['concept_id']):[str(p) for p in x.get('phrases') or []] for x in teachers}
    if len(phrases)!=300 or any(len(v)!=3 for v in phrases.values()): raise RuntimeError('teacher identity/phrase drift')

    registry=json.loads(Path('research/coverage/source-adapters.json').read_text()); pareto=json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    tb=fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json')
    if hashlib.sha256(tb).hexdigest()!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(tb).get('data',{}).get('concepts') or []; by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    trb=fetch_training()
    if hashlib.sha256(trb).hexdigest()!=TRAINING_SHA: raise RuntimeError('training source drift')
    tr=json.loads(trb); modules=(tr.get('data') or tr.get('moduler') or tr.get('modules')) if isinstance(tr,dict) else tr
    ids=p80_skill_ids(pareto)

    first=load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl')); second=load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl')); third=load_jsonl(Path('research/benchmark/v31/training-skill-third-holdout/cases.jsonl'))
    r101=load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks101-200/cases.jsonl')); r201=load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks201-300/cases.jsonl'))
    if (len(first),len(second),len(third),len(r101),len(r201))!=(35,20,26,100,100): raise RuntimeError('suite count drift')
    suites={
      'synthetic_ranks101_200_opened':(r101,[]),
      'synthetic_ranks201_300_opened':(r201,[]),
      'AF_first35_opened':(first,first),
      'AF_second20_opened':(second,[*first,*second]),
      'AF_third26_opened':(third,[*first,*second,*third]),
    }
    results={}
    for sname,(cases,excluded) in suites.items():
        exids={mid for c in excluded for mid in ids_list(c.get('module_ids'))}; extexts={norm(c['query']) for c in excluded}
        docs,exact,coverage=build_docs(by_id,ids,modules,exids,extexts); c0=BM25(docs['KV-C0'],exact); g1=BM25(docs['KV-G1-single-desc'],exact)
        query_rankings=[]
        for c in cases:
            q=str(c['query']); query_rankings.append((rank(c0,exact,q),rank(g1,exact,q),q))
        lanes={}
        for lname in LANES:
            tdocs=build_teacher_docs(lname,docs,ids,phrases); tranker=BM25(tdocs,{sid:set() for sid in tdocs})
            rows=[]
            for a,b,q in query_rankings:
                t=rank(tranker,{sid:set() for sid in tdocs},q)
                rows.append(fuse_quotas(a,b,t,*POLICY))
            lanes[lname]=evaluate(cases,rows)
        current=lanes['G1_plus_teacher']; packed={}
        for lname,ev in lanes.items():
            d=paired(current,ev,cases)
            packed[lname]={**ev,'rescues_vs_current':len(d['rescues']),'regressions_vs_current':len(d['regressions']),'rescue_cases':d['rescues'],'regression_cases':d['regressions']}
        results[sname]={'cases':len(cases),'coverage':coverage,'lanes':packed}

    canonical=load_jsonl(Path('research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl'))
    if len(canonical)!=617: raise RuntimeError('canonical count drift')
    docs,exact,_=build_docs(by_id,ids,modules,set(),set()); c0=BM25(docs['KV-C0'],exact); g1=BM25(docs['KV-G1-single-desc'],exact)
    canonical_guard={}
    for lname in LANES:
        td=build_teacher_docs(lname,docs,ids,phrases); tranker=BM25(td,{sid:set() for sid in td}); h1=h5=0
        for c in canonical:
            rel={str(x['concept_id']) for x in c['must']}; q=str(c['query']); fused=fuse_quotas(rank(c0,exact,q),rank(g1,exact,q),rank(tranker,{sid:set() for sid in td},q),*POLICY)
            h1+=int(bool(fused and fused[0] in rel)); h5+=int(any(x in rel for x in fused[:5]))
        canonical_guard[lname]={'top1':metric(h1,len(canonical)),'hit5':metric(h5,len(canonical))}

    def compact(ev): return {'hit5':ev['hit_at_5'],'top1':ev['top1'],'rescues_vs_current':ev['rescues_vs_current'],'regressions_vs_current':ev['regressions_vs_current']}
    order=sorted(('C0_plus_teacher','teacher_only'),key=lambda n:(
        sum(results[s]['lanes'][n]['regressions_vs_current'] for s in ('AF_first35_opened','AF_second20_opened','AF_third26_opened')),
        -sum(results[s]['lanes'][n]['hit_at_5']['hits'] for s in ('AF_first35_opened','AF_second20_opened','AF_third26_opened')),
        -results['synthetic_ranks201_300_opened']['lanes'][n]['hit_at_5']['hits'],n))
    output={'schema_version':1,'status':'opened-suite development ablation; representation only, fusion fixed G1+T3','representations':{
      'G1_plus_teacher':'current teacher lane duplicates G1 text then appends teacher phrases',
      'C0_plus_teacher':'teacher lane contains canonical C0 text plus teacher phrases, no G1 training descriptions',
      'teacher_only':'teacher lane contains only three prefrozen teacher phrases per enriched target; C0 and G1 remain separate fusion lanes'},'results':results,'canonical_guard':canonical_guard,'development_order':order,'next_gate':'If a separated lane dominates materially, freeze exactly one representation and validate it on untouched P80 ranks 301-316 before promotion.'}
    out=Path('artifacts/kv-teacher-lane-separation-v31.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(output,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'development_order':order,'suites':{s:{n:compact(v) for n,v in d['lanes'].items()} for s,d in results.items()},'canonical':canonical_guard},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
