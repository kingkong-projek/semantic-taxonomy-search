#!/usr/bin/env python3
"""Test pure-number sanitation only in semantic expansion lanes.

C0 remains byte-for-byte/token-for-token equivalent to the established lexical baseline.
Only G1 and teacher BM25 token streams drop pure integer tokens. Exact surfaces remain
unchanged in all lanes. Fusion remains C0-top1 + G1-1slot + teacher-3slot.

This is a development ablation on opened suites. If it passes all guards, freeze it before
creating any teacher/query evidence for untouched P80 ranks 301-316.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_kv_drop_numeric_tokens import evaluate, metric, paired, load_teacher
from evaluate_kv_three_lane_fusion import fuse_quotas
from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import (
    TRAINING_SHA,
    build_docs,
    fetch_training,
    ids_list,
    rank,
)

POLICY=(1,3)
VARIANTS=('current','drop_numeric_expansion_only')


def no_numbers(ts:list[str])->list[str]:
    return [t for t in ts if not t.isdigit()]


def rankers(by_id:dict[str,dict[str,Any]],ids:list[str],modules:list[dict[str,Any]],teacher_by_id:dict[str,list[str]],excluded:list[dict[str,Any]],variant:str):
    exids={mid for c in excluded for mid in ids_list(c.get('module_ids'))}
    extexts={norm(c['query']) for c in excluded}
    docs,exact,coverage=build_docs(by_id,ids,modules,exids,extexts)
    # C0 is deliberately untouched in both variants.
    c0=BM25(docs['KV-C0'],exact)
    if variant=='current':
        gdocs={sid:list(ts) for sid,ts in docs['KV-G1-single-desc'].items()}
        tdocs={sid:[*gdocs[sid],*[t for phrase in teacher_by_id.get(sid,[]) for t in __import__('evaluate_p80_lexical_ablation').tokens(phrase)]] for sid in ids}
    elif variant=='drop_numeric_expansion_only':
        gdocs={sid:no_numbers(list(ts)) for sid,ts in docs['KV-G1-single-desc'].items()}
        tokenizer=__import__('evaluate_p80_lexical_ablation').tokens
        tdocs={sid:[*gdocs[sid],*no_numbers([t for phrase in teacher_by_id.get(sid,[]) for t in tokenizer(phrase)])] for sid in ids}
    else:
        raise RuntimeError(variant)
    g1=BM25(gdocs,exact); teacher=BM25(tdocs,exact)
    return c0,g1,teacher,exact,coverage


def run(cases:list[dict[str,Any]],by_id,ids,modules,teacher_by_id,excluded,variant):
    c0,g1,teacher,exact,coverage=rankers(by_id,ids,modules,teacher_by_id,excluded,variant)
    rows=[]
    for case in cases:
        q=str(case['query'])
        # C0 query tokenization stays current. G1/teacher query tokens must mirror their
        # document sanitation. We reuse BM25 directly for the expansion variants while
        # retaining exact-surface dominance.
        a=rank(c0,exact,q)
        if variant=='current':
            b=rank(g1,exact,q); t=rank(teacher,exact,q)
        else:
            from evaluate_p80_lexical_ablation import tokens
            qtokens=no_numbers(tokens(q)); nq=norm(q)
            def rr(ranker):
                scored=[]
                for cid in ranker.documents:
                    score=ranker.score(qtokens,cid)
                    if nq and nq in exact.get(cid,set()): score+=1_000_000.0
                    if score>0: scored.append((score,cid))
                scored.sort(key=lambda row:(-row[0],row[1])); return [cid for _,cid in scored]
            b=rr(g1); t=rr(teacher)
        rows.append(fuse_quotas(a,b,t,*POLICY))
    return evaluate(cases,rows),coverage


def main()->int:
    teacher_by_id=load_teacher()
    registry=json.loads(Path('research/coverage/source-adapters.json').read_text()); pareto=json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    tb=fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json'); tax_sha=hashlib.sha256(tb).hexdigest()
    if tax_sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(tb).get('data',{}).get('concepts') or []; by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}; ids=p80_skill_ids(pareto)
    trb=fetch_training(); training_sha=hashlib.sha256(trb).hexdigest()
    if training_sha!=TRAINING_SHA: raise RuntimeError('training source drift')
    tr=json.loads(trb); modules=(tr.get('data') or tr.get('moduler') or tr.get('modules')) if isinstance(tr,dict) else tr
    if not isinstance(modules,list): raise RuntimeError('training source root drift')

    first=load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl')); second=load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl')); third=load_jsonl(Path('research/benchmark/v31/training-skill-third-holdout/cases.jsonl')); r101=load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks101-200/cases.jsonl')); r201=load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks201-300/cases.jsonl'))
    if (len(first),len(second),len(third),len(r101),len(r201))!=(35,20,26,100,100): raise RuntimeError('suite count drift')
    suites={'AF_first35_opened':(first,first),'AF_second20_opened':(second,[*first,*second]),'AF_third26_opened':(third,[*first,*second,*third]),'synthetic_ranks101_200_opened':(r101,[]),'synthetic_ranks201_300_opened':(r201,[])}
    results={}
    for name,(cases,excluded) in suites.items():
        variants={}; coverage=None
        for variant in VARIANTS:
            ev,coverage=run(cases,by_id,ids,modules,teacher_by_id,excluded,variant); variants[variant]=ev
        d=paired(variants['current'],variants['drop_numeric_expansion_only'],cases)
        results[name]={'cases':len(cases),'coverage':coverage,'current':variants['current'],'drop_numeric_expansion_only':variants['drop_numeric_expansion_only'],'rescues':d['rescues'],'regressions':d['regressions'],'rank_moves':d['rank_moves']}

    canonical=load_jsonl(Path('research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl'))
    if len(canonical)!=617: raise RuntimeError('canonical count drift')
    canonical_results={}
    for variant in VARIANTS:
        c0,g1,teacher,exact,_=rankers(by_id,ids,modules,teacher_by_id,[],variant); h1=h5=0; misses=[]
        for c in canonical:
            rel={str(x['concept_id']) for x in c['must']}; q=str(c['query']); a=rank(c0,exact,q)
            if variant=='current': b=rank(g1,exact,q); t=rank(teacher,exact,q)
            else:
                from evaluate_p80_lexical_ablation import tokens
                qt=no_numbers(tokens(q)); nq=norm(q)
                def rr(ranker):
                    scored=[]
                    for cid in ranker.documents:
                        score=ranker.score(qt,cid)
                        if nq and nq in exact.get(cid,set()): score+=1_000_000.0
                        if score>0: scored.append((score,cid))
                    scored.sort(key=lambda x:(-x[0],x[1])); return [cid for _,cid in scored]
                b=rr(g1); t=rr(teacher)
            fused=fuse_quotas(a,b,t,*POLICY); one=bool(fused and fused[0] in rel); five=any(x in rel for x in fused[:5]); h1+=int(one); h5+=int(five)
            if not one or not five: misses.append({'id':c['id'],'query':q,'expected':sorted(rel),'top5':fused[:5]})
        canonical_results[variant]={'top1':metric(h1,len(canonical)),'hit5':metric(h5,len(canonical)),'misses':misses}

    known_id='kv.training-skill-second-holdout.017'; known={variant:next(d for d in results['AF_second20_opened'][variant]['details'] if d['id']==known_id) for variant in VARIANTS}
    human=('AF_first35_opened','AF_second20_opened','AF_third26_opened')
    aggregate={'queries':81,'current_hits_at_5':sum(results[s]['current']['hit_at_5']['hits'] for s in human),'candidate_hits_at_5':sum(results[s]['drop_numeric_expansion_only']['hit_at_5']['hits'] for s in human),'rescues':sum(len(results[s]['rescues']) for s in human),'regressions':sum(len(results[s]['regressions']) for s in human)}
    output={'schema_version':1,'status':'opened-suite development ablation; C0 fixed, only G1/teacher pure-number sanitation','change':'drop pure integer tokens from G1 and teacher semantic BM25 document/query streams; leave C0 and all exact surfaces unchanged','fusion':'unchanged C0-top1 + G1-1slot + teacher-3slot','teacher_representation':'unchanged G1 + teacher phrases','results':results,'canonical_guard':canonical_results,'known_boundary_case':known,'aggregate_source_attested':aggregate,'decision_rule':'Nominate only if canonical remains 617/617 Top1+Hit5, the known source-attested boundary regression is removed, aggregate source-attested has zero Hit5 regressions, and opened synthetic Hit5 does not materially degrade. If nominated, freeze before ranks301-316 evidence authoring.'}
    out=Path('artifacts/kv-drop-numeric-expansion-only-v31.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(output,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    def compact(ev): return {k:v for k,v in ev.items() if k!='details'}
    print(json.dumps({'aggregate_source_attested':aggregate,'known_case':{k:{'rank':v['rank'],'top5':v['top5']} for k,v in known.items()},'suites':{s:{'current':compact(r['current']),'candidate':compact(r['drop_numeric_expansion_only']),'rescues':len(r['rescues']),'regressions':len(r['regressions']),'rank_moves':len(r['rank_moves'])} for s,r in results.items()},'canonical':canonical_results},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
