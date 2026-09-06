#!/usr/bin/env python3
"""Evaluate the already-defined character-4gram lane on the frozen third KV holdout.

This script MUST NOT tune N, fusion, tokenization or evidence. It validates only the lane
that existed before the third holdout was built. The third holdout is excluded from all G1
retrieval evidence together with the earlier natural holdouts.
"""
from __future__ import annotations

import hashlib, json, math
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, ids_list, build_docs, rank
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1

N = 4  # frozen before this holdout existed


def pct(n:int,d:int)->float: return round(100*n/d,3) if d else 0.0

def wilson(k:int,n:int,z:float=1.959963984540054)->dict[str,float]:
    if n<=0: return {'low_pct':0.0,'high_pct':0.0}
    p=k/n; den=1+z*z/n; centre=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return {'low_pct':round(100*max(0,centre-half),2),'high_pct':round(100*min(1,centre+half),2)}

def grams_from_token(t:str)->list[str]:
    return [] if len(t)<N else [t[i:i+N] for i in range(len(t)-N+1)]

def grams(ts:list[str])->list[str]: return [g for t in ts for g in grams_from_token(t)]
def qgrams(q:str)->list[str]: return grams(tokens(q))
def rank_grams(ranker:BM25,q:str)->list[str]:
    qs=qgrams(q); scored=[]
    for sid in ranker.documents:
        s=ranker.score(qs,sid)
        if s>0: scored.append((s,sid))
    scored.sort(key=lambda x:(-x[0],x[1])); return [sid for _,sid in scored]

def relevant(c:dict[str,Any])->set[str]: return {str(c['target']['concept_id'])}

def pos(r:list[str], rel:set[str])->int|None:
    ps=[r.index(x)+1 for x in rel if x in r]
    return min(ps) if ps else None


def main()->int:
    first=load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'))
    second=load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl'))
    third=load_jsonl(Path('research/benchmark/v31/training-skill-third-holdout/cases.jsonl'))
    manifest=json.loads(Path('research/benchmark/v31/training-skill-third-holdout/manifest.json').read_text())
    if (len(first),len(second),len(third))!=(35,20,26): raise RuntimeError('holdout count drift')
    if manifest['benchmark_sha256']!='2903954d7b68cac0dbdd0b7e841a1222938a2e2670e366444cd63b7f12ed3e29': raise RuntimeError('third holdout hash drift')

    excluded=first+second+third
    exids={mid for c in excluded for mid in ids_list(c.get('module_ids'))}
    extexts={norm(c['query']) for c in excluded}

    tb=fetch_training(); tsha=hashlib.sha256(tb).hexdigest()
    if tsha!=TRAINING_SHA: raise RuntimeError('training source drift')
    tj=json.loads(tb); modules=(tj.get('data') or tj.get('moduler') or tj.get('modules')) if isinstance(tj,dict) else tj
    registry=json.loads(Path('research/coverage/source-adapters.json').read_text()); pareto=json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    body=fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json'); sha=hashlib.sha256(body).hexdigest()
    if sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(body).get('data',{}).get('concepts'); by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}; ids=p80_skill_ids(pareto)
    docs,exact,coverage=build_docs(by_id,ids,modules,exids,extexts)
    c0=BM25(docs['KV-C0'],exact); g1=BM25(docs['KV-G1-single-desc'],exact)
    subdocs={sid:grams(ts) for sid,ts in docs['KV-G1-single-desc'].items()}; sub=BM25(subdocs,{sid:set() for sid in subdocs})

    base_hits=sub_hits=oracle_hits=0
    base_only=sub_only=both=neither=0
    details=[]
    unique_targets=set()
    for c in third:
        q=str(c['query']); rel=relevant(c); unique_targets |= rel
        a=rank(c0,exact,q); b=rank(g1,exact,q); base=fuse_preserve_c0_top1(a,b,4); sr=rank_grams(sub,q)
        bh=any(x in rel for x in base[:5]); sh=any(x in rel for x in sr[:5]); oh=bh or sh
        base_hits+=bh; sub_hits+=sh; oracle_hits+=oh
        if bh and sh: both+=1
        elif bh: base_only+=1
        elif sh: sub_only+=1
        else: neither+=1
        if (bh != sh) or not bh:
            details.append({
                'id':c['id'],'target':c['target'],'module_name':c.get('module_name'),'query':q,
                'all_mapped_skill_ids':c.get('all_mapped_skill_ids',[]),
                'base_hit5':bh,'subword_hit5':sh,'base_rank':pos(base,rel),'subword_rank':pos(sr,rel),
                'base_top5':base[:5],'subword_top5':sr[:5],
                'review_required':True,
                'review_reason':'candidate disagreement or validated-base miss; source annotation must be manually adjudicated before interpreting metric'
            })

    def metric(k:int)->dict[str,Any]: return {'hits':k,'cases':len(third),'hit5_pct':pct(k,len(third)),'wilson_95_pct':wilson(k,len(third))}
    result={
        'schema_version':1,
        'status':'fixed-lane validation; no fusion selected or tuned',
        'evidence_class':'third frozen source-attested holdout; 4-gram lane fixed before holdout build; human later saw some frozen texts before retrieval outputs, so do not use this set to choose a fusion policy',
        'holdout':{'cases':len(third),'unique_target_skills':len(unique_targets),'max_cases_per_skill':manifest['max_cases_per_skill'],'benchmark_sha256':manifest['benchmark_sha256']},
        'lane':{'name':'character-4gram BM25','n':N,'source_text':'existing C0 + G1 single-desc evidence only','new_semantic_source':False},
        'validated_base':metric(base_hits),'subword_lane':metric(sub_hits),'base_or_subword_oracle':metric(oracle_hits),
        'paired':{'both_hit':both,'base_only_hit':base_only,'subword_only_hit':sub_only,'neither_hit':neither,'discordant_cases':base_only+sub_only},
        'g1_coverage':coverage,
        'manual_adjudication_required':'Review every detail row against source text and taxonomy. AF mapping is evidence, not infallible ground truth; do not promote the subword lane from raw metric alone.',
        'review_cases':details,
        'statistics_note':'Wilson interval is query-level descriptive uncertainty only; 26 queries cluster over 17 unique target skills. Occurrence-weighted pseudo-N is not used as inferential sample size.'
    }
    out=Path('artifacts/skill-g1-subword-third-holdout-v31.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:result[k] for k in ('holdout','validated_base','subword_lane','base_or_subword_oracle','paired')},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
