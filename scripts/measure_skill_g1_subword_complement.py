#!/usr/bin/env python3
"""Measure one cheap subword candidate lane above validated KV-G1-4slot.

The lane uses only character 4-grams generated from the existing C0 + G1 single-description
text. It is an oracle/complement diagnostic only: no fusion is chosen, no benchmark text is
ingested, and no candidate can be promoted without a new independent holdout.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids, pct
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, ids_list, build_docs, rank
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1

N=4


def grams_from_token(t:str)->list[str]:
    if len(t)<N: return []
    return [t[i:i+N] for i in range(len(t)-N+1)]

def grams(ts:list[str])->list[str]:
    return [g for t in ts for g in grams_from_token(t)]

def qgrams(q:str)->list[str]:
    return grams(tokens(q))

def rank_grams(ranker:BM25,q:str)->list[str]:
    qs=qgrams(q); scored=[]
    for sid in ranker.documents:
        s=ranker.score(qs,sid)
        if s>0: scored.append((s,sid))
    scored.sort(key=lambda x:(-x[0],x[1])); return [sid for _,sid in scored]

def relevant(case:dict[str,Any])->set[str]:
    if isinstance(case.get('target'),dict) and case['target'].get('concept_id'): return {str(case['target']['concept_id'])}
    return {str(x['concept_id']) for x in (case.get('must') or []) if isinstance(x,dict) and x.get('concept_id')}

def measure(cases:list[dict[str,Any]],c0:BM25,g1:BM25,exact:dict[str,set[str]],sub:BM25,weighted:bool)->dict[str,Any]:
    base_hit=lane_hit=oracle=rescues=0; wt=base_w=lane_w=oracle_w=rescue_w=0; miss=[]
    for c in cases:
        q=str(c['query']); rel=relevant(c); a=rank(c0,exact,q); b=rank(g1,exact,q); base=fuse_preserve_c0_top1(a,b,4); sr=rank_grams(sub,q)
        bh=any(x in rel for x in base[:5]); lh=any(x in rel for x in sr[:5]); oh=bh or lh; rs=(not bh) and lh
        base_hit+=int(bh); lane_hit+=int(lh); oracle+=int(oh); rescues+=int(rs)
        w=int((c.get('target') or {}).get('occurrence_proxy') or 0) if weighted else 0; wt+=w; base_w+=w*int(bh); lane_w+=w*int(lh); oracle_w+=w*int(oh); rescue_w+=w*int(rs)
        if not bh:
            positions=[sr.index(x)+1 for x in rel if x in sr]; miss.append({'id':c['id'],'query':q,'expected':sorted(rel),'subword_rank':min(positions) if positions else None,'subword_hit5':lh,'subword_top5':sr[:5]})
    out={'cases':len(cases),'baseline_hit5_pct':pct(base_hit,len(cases)),'subword_lane_hit5_pct':pct(lane_hit,len(cases)),'baseline_misses':len(cases)-base_hit,'misses_rescued':rescues,'base_or_subword_oracle_hit5_pct':pct(oracle,len(cases)),'baseline_miss_detail':miss}
    if weighted: out.update({'weighted_baseline_hit5_pct':pct(base_w,wt),'weighted_subword_lane_hit5_pct':pct(lane_w,wt),'weighted_oracle_hit5_pct':pct(oracle_w,wt),'weighted_rescue_share_of_baseline_miss_pct':pct(rescue_w,wt-base_w)})
    return out

def main()->int:
    first=load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl')); second=load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl')); synthetic=[c for c in load_jsonl(Path('research/benchmark/v31/synthetic-description-stress/cases.jsonl')) if c.get('product')=='KV']
    if (len(first),len(second),len(synthetic))!=(35,20,12): raise RuntimeError('benchmark count drift')
    excluded=first+second; exids={mid for c in excluded for mid in ids_list(c.get('module_ids'))}; extexts={norm(c['query']) for c in excluded}
    tb=fetch_training(); tsha=hashlib.sha256(tb).hexdigest();
    if tsha!=TRAINING_SHA: raise RuntimeError('training source drift')
    tj=json.loads(tb); modules=(tj.get('data') or tj.get('moduler') or tj.get('modules')) if isinstance(tj,dict) else tj
    registry=json.loads(Path('research/coverage/source-adapters.json').read_text()); pareto=json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    body=fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json'); sha=hashlib.sha256(body).hexdigest()
    if sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(body).get('data',{}).get('concepts'); by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}; ids=p80_skill_ids(pareto)
    docs,exact,coverage=build_docs(by_id,ids,modules,exids,extexts); c0=BM25(docs['KV-C0'],exact); g1=BM25(docs['KV-G1-single-desc'],exact)
    subdocs={sid:grams(ts) for sid,ts in docs['KV-G1-single-desc'].items()}; sub=BM25(subdocs,{sid:set() for sid in subdocs})
    stats={'doc_count':len(subdocs),'total_4gram_occurrences':sum(len(v) for v in subdocs.values()),'unique_4gram_skill_pairs':sum(len(set(v)) for v in subdocs.values())}
    result={'schema_version':1,'status':'development oracle/complement diagnostic; no fusion selected','lane':'character 4-gram BM25 over existing C0 + G1 single-desc text','runtime_note':'would require a separate subword postings representation if ever adopted; this run measures relevance complement only','taxonomy_sha256':sha,'training_sha256':tsha,'g1_coverage':coverage,'subword_stats':stats,'first_holdout_posthoc':measure(first,c0,g1,exact,sub,True),'second_holdout_posthoc':measure(second,c0,g1,exact,sub,True),'synthetic_stress':measure(synthetic,c0,g1,exact,sub,False)}
    out=Path('artifacts/skill-g1-subword-complement-v31.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    compact={k:{kk:vv for kk,vv in result[k].items() if kk!='baseline_miss_detail'} for k in ('first_holdout_posthoc','second_holdout_posthoc','synthetic_stress')}; compact['subword_stats']=stats; print(json.dumps(compact,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
