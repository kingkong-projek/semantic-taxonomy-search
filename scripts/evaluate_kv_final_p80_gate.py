#!/usr/bin/env python3
"""Evaluate the final untouched KV P80 ranks301-316 gate.

Freeze order is contractual:
  expansion-only numeric sanitation -> final teacher phrases -> final queries -> retrieval.
No policy/teacher/query editing or alternate fusion search is allowed after this evaluator runs.
The final representation contains teacher phrases for all 316 P80 skills. Safety is rechecked
against canonical source truth, all source-attested AF holdouts, and prior synthetic slices so
cross-target competition from the last 16 teacher entries is observable.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_kv_drop_numeric_expansion_only import rankers, run
from evaluate_kv_drop_numeric_tokens import evaluate, metric, paired
from evaluate_kv_three_lane_fusion import fuse_quotas
from evaluate_p80_lexical_ablation import expected_hash, fetch, load_jsonl, norm
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, rank

CANDIDATE_COMMIT='ff3cb147dbdfacea8b9b505680e18a1f7d31f223'
TEACHER_COMMIT='9b47eb893c1148cf2f159c25901acd8abb04d2f0'
QUERY_COMMIT='38494a4040c662c4f4ba518df9c74fb95719027b'
CURRENT='current'
CANDIDATE='drop_numeric_expansion_only'

TEACHER_300=(
    'research/enrichment/v31/model-teacher-kv-top100/phrases.jsonl',
    'research/enrichment/v31/model-teacher-kv-ranks101-200/phrases.jsonl',
    'research/enrichment/v31/model-teacher-kv-ranks201-300/phrases.jsonl',
)
TEACHER_FINAL='research/enrichment/v31/model-teacher-kv-ranks301-316/phrases.jsonl'


def teacher_map(include_final: bool)->dict[str,list[str]]:
    rows=[]
    for p in TEACHER_300:
        rows.extend(load_jsonl(Path(p)))
    if include_final:
        rows.extend(load_jsonl(Path(TEACHER_FINAL)))
    expected=316 if include_final else 300
    if len(rows)!=expected:
        raise RuntimeError(f'teacher count drift {len(rows)} != {expected}')
    out={}
    for row in rows:
        cid=str(row['concept_id']); phrases=[str(x) for x in row.get('phrases') or []]
        if cid in out or len(phrases)!=3:
            raise RuntimeError(f'teacher identity/phrase drift {cid}')
        out[cid]=phrases
    return out


def baseline_g1(cases,by_id,ids,modules,teacher,excluded):
    c0,g1,_t,exact,coverage=rankers(by_id,ids,modules,teacher,excluded,CURRENT)
    rankings=[]
    for case in cases:
        q=str(case['query'])
        a=rank(c0,exact,q); b=rank(g1,exact,q)
        rankings.append(fuse_quotas(a,b,[],4,0))
    return evaluate(cases,rankings),coverage


def compact(ev:dict[str,Any])->dict[str,Any]:
    return {k:v for k,v in ev.items() if k!='details'}


def delta(base:dict[str,Any],cand:dict[str,Any],cases:list[dict[str,Any]])->dict[str,Any]:
    d=paired(base,cand,cases)
    return {'rescues':d['rescues'],'regressions':d['regressions'],'rank_moves':d['rank_moves']}


def canonical_guard(by_id,ids,modules,teacher,variant):
    cases=load_jsonl(Path('research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl'))
    if len(cases)!=617: raise RuntimeError('canonical count drift')
    c0,g1,t,exact,_=rankers(by_id,ids,modules,teacher,[],variant)
    from evaluate_kv_drop_numeric_expansion_only import no_numbers
    from evaluate_p80_lexical_ablation import tokens
    h1=h5=0; misses=[]
    for case in cases:
        q=str(case['query']); rel={str(x['concept_id']) for x in case['must']}
        a=rank(c0,exact,q)
        if variant==CURRENT:
            b=rank(g1,exact,q); tr=rank(t,exact,q)
        else:
            qt=no_numbers(tokens(q)); nq=norm(q)
            def rr(ranker):
                scored=[]
                for cid in ranker.documents:
                    s=ranker.score(qt,cid)
                    if nq and nq in exact.get(cid,set()): s+=1_000_000.0
                    if s>0: scored.append((s,cid))
                scored.sort(key=lambda x:(-x[0],x[1])); return [cid for _,cid in scored]
            b=rr(g1); tr=rr(t)
        fused=fuse_quotas(a,b,tr,1,3)
        one=bool(fused and fused[0] in rel); five=any(x in rel for x in fused[:5])
        h1+=int(one); h5+=int(five)
        if not one or not five:
            misses.append({'id':case['id'],'query':q,'expected':sorted(rel),'top5':fused[:5]})
    return {'top1':metric(h1,617),'hit5':metric(h5,617),'misses':misses}


def main()->int:
    manifest=json.loads(Path('research/benchmark/v31/model-authored-kv-ranks301-316/manifest.json').read_text())
    freeze=manifest['freeze_order']
    if freeze['candidate_commit']!=CANDIDATE_COMMIT or freeze['teacher_commit']!=TEACHER_COMMIT or freeze['query_commit']!=QUERY_COMMIT:
        raise RuntimeError('freeze-order commit drift')
    if not freeze['candidate_before_teacher'] or not freeze['teacher_before_queries'] or freeze['retrieval_before_all_freezes']:
        raise RuntimeError('freeze-order contract drift')
    if manifest['evaluation_policy']['no_alternate_policy_search'] is not True or manifest['evaluation_policy']['no_posthoc_query_or_teacher_cleaning'] is not True:
        raise RuntimeError('evaluation contract drift')

    final=load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks301-316/cases.jsonl'))
    prior101=load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks101-200/cases.jsonl'))
    prior201=load_jsonl(Path('research/benchmark/v31/model-authored-kv-ranks201-300/cases.jsonl'))
    first=load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'))
    second=load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl'))
    third=load_jsonl(Path('research/benchmark/v31/training-skill-third-holdout/cases.jsonl'))
    if (len(final),len(prior101),len(prior201),len(first),len(second),len(third))!=(16,100,100,35,20,26):
        raise RuntimeError('suite count drift')

    ranks=[int(c['target']['p80_rank']) for c in final]
    if ranks!=list(range(301,317)): raise RuntimeError('final rank slice drift')
    ids_final={str(c['target']['concept_id']) for c in final}
    ids_prior={str(c['target']['concept_id']) for c in [*prior101,*prior201]}
    if ids_final & ids_prior: raise RuntimeError('target overlap with prior synthetic suites')
    nq_final=[norm(c['query']) for c in final]
    nq_prior={norm(c['query']) for c in [*prior101,*prior201]}
    if len(set(nq_final))!=16 or set(nq_final)&nq_prior: raise RuntimeError('query overlap/drift')
    teacher316=teacher_map(True); teacher300=teacher_map(False)
    teacher_phrases={norm(p) for ps in teacher316.values() for p in ps}
    if set(nq_final)&teacher_phrases: raise RuntimeError('exact teacher/query overlap')
    if ids_final-{*teacher316}: raise RuntimeError('final targets missing teacher evidence')

    registry=json.loads(Path('research/coverage/source-adapters.json').read_text())
    pareto=json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    tax=fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json')
    tax_sha=hashlib.sha256(tax).hexdigest()
    if tax_sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(tax).get('data',{}).get('concepts') or []
    by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    ids=p80_skill_ids(pareto)
    if len(ids)!=316 or set(ids_final)!=set(ids[300:316]): raise RuntimeError('P80 final target identity drift')
    trb=fetch_training(); training_sha=hashlib.sha256(trb).hexdigest()
    if training_sha!=TRAINING_SHA: raise RuntimeError('training source drift')
    tj=json.loads(trb); modules=(tj.get('data') or tj.get('moduler') or tj.get('modules')) if isinstance(tj,dict) else tj
    if not isinstance(modules,list): raise RuntimeError('training source root drift')

    suites={
        'AF_first35':(first,first),
        'AF_second20':(second,[*first,*second]),
        'AF_third26':(third,[*first,*second,*third]),
        'synthetic_ranks101_200':(prior101,[]),
        'synthetic_ranks201_300':(prior201,[]),
        'fresh_ranks301_316':(final,[]),
    }
    results={}
    for name,(cases,excluded) in suites.items():
        base,coverage=baseline_g1(cases,by_id,ids,modules,teacher316,excluded)
        current,_=run(cases,by_id,ids,modules,teacher316,excluded,CURRENT)
        prefinal,_=run(cases,by_id,ids,modules,teacher300,excluded,CANDIDATE)
        finalcand,_=run(cases,by_id,ids,modules,teacher316,excluded,CANDIDATE)
        results[name]={
            'cases':len(cases),'coverage':coverage,
            'G1_4slot_baseline':base,
            'G1_T3_current_tokenization':current,
            'prefinal_candidate_teacher300':prefinal,
            'final_candidate_teacher316':finalcand,
            'final_vs_G1':delta(base,finalcand,cases),
            'numeric_sanitation_effect_full316':delta(current,finalcand,cases),
            'last16_teacher_competition_effect':delta(prefinal,finalcand,cases),
        }

    canonical_current=canonical_guard(by_id,ids,modules,teacher316,CURRENT)
    canonical_final=canonical_guard(by_id,ids,modules,teacher316,CANDIDATE)
    human=('AF_first35','AF_second20','AF_third26')
    aggregate={
        'queries':81,
        'G1_hits_at_5':sum(results[s]['G1_4slot_baseline']['hit_at_5']['hits'] for s in human),
        'current_G1T3_hits_at_5':sum(results[s]['G1_T3_current_tokenization']['hit_at_5']['hits'] for s in human),
        'final_candidate_hits_at_5':sum(results[s]['final_candidate_teacher316']['hit_at_5']['hits'] for s in human),
        'last16_teacher_regressions':sum(len(results[s]['last16_teacher_competition_effect']['regressions']) for s in human),
        'numeric_regressions':sum(len(results[s]['numeric_sanitation_effect_full316']['regressions']) for s in human),
    }
    fresh=results['fresh_ranks301_316']
    safety={
        'canonical_617_top1_and_hit5': canonical_final['top1']['hits']==617 and canonical_final['hit5']['hits']==617,
        'zero_AF_regressions_from_last16_teacher': aggregate['last16_teacher_regressions']==0,
        'zero_AF_regressions_from_numeric_sanitation': aggregate['numeric_regressions']==0,
        'zero_prior_synthetic_hit5_regressions_from_last16_teacher': all(len(results[s]['last16_teacher_competition_effect']['regressions'])==0 for s in ('synthetic_ranks101_200','synthetic_ranks201_300')),
        'fresh_gate_no_hit5_regression_vs_G1': len(fresh['final_vs_G1']['regressions'])==0,
    }
    output={
        'schema_version':1,
        'status':'first retrieval on final prefrozen P80 ranks301-316; no post-hoc policy/query/teacher changes allowed',
        'freeze_order':freeze,
        'taxonomy_sha256':tax_sha,'training_sha256':training_sha,
        'disjointness':{'final_targets':16,'target_overlap_prior':0,'exact_query_overlap_prior':0,'exact_teacher_query_overlap':0},
        'aggregate_source_attested':aggregate,
        'canonical_guard':{'current_full316':canonical_current,'final_candidate':canonical_final},
        'safety_checks':safety,
        'results':results,
        'interpretation_boundary':manifest['interpretation_boundary'],
        'decision_rule':'Promote the low-complexity candidate only from the frozen evidence as observed. Do not repair a miss by changing policy, teacher phrases, queries, token rules or adding a higher-complexity model. Any future change requires a new prefrozen gate.'
    }
    out=Path('artifacts/kv-final-p80-gate-v31.json'); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(output,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({
        'fresh':{
            'G1':compact(fresh['G1_4slot_baseline']),
            'current_G1T3':compact(fresh['G1_T3_current_tokenization']),
            'final_candidate':compact(fresh['final_candidate_teacher316']),
            'rescues_vs_G1':len(fresh['final_vs_G1']['rescues']),
            'regressions_vs_G1':len(fresh['final_vs_G1']['regressions']),
        },
        'aggregate_source_attested':aggregate,
        'canonical_final':canonical_final,
        'safety_checks':safety,
        'prior_synthetic':{s:{'prefinal_hit5':results[s]['prefinal_candidate_teacher300']['hit_at_5']['hits'],'final_hit5':results[s]['final_candidate_teacher316']['hit_at_5']['hits'],'teacher_regressions':len(results[s]['last16_teacher_competition_effect']['regressions'])} for s in ('synthetic_ranks101_200','synthetic_ranks201_300')},
    },ensure_ascii=False,indent=2,sort_keys=True))
    return 0

if __name__=='__main__': raise SystemExit(main())
