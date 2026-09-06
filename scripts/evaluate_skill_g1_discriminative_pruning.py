#!/usr/bin/env python3
"""Development ablation: prune G1 training language to discriminative build-time keywords.

No new source, tokenizer, runtime scorer or fusion policy is introduced. The validated
KV-G1-single-desc documents are decomposed into canonical C0 tokens plus enrichment tokens.
Enrichment terms are ranked per skill by corpus-level IDF * log-saturated within-skill TF,
and only the top K unique terms are retained once. This asks whether reducing source noise
can improve the same fixed C0-top1 + four-G1-slot policy while shrinking the static index.

Both natural holdouts remain excluded from G1 evidence. Results are development evidence
only; any promoted representation requires a new unopened source-attested holdout.
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm
from evaluate_skill_c0_training_validation import p80_skill_ids, pct
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, ids_list, build_docs, rank
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1

KS=(8,16,32,64,128)


def relevant(case: dict[str,Any]) -> set[str]:
    if isinstance(case.get('target'),dict) and case['target'].get('concept_id'):
        return {str(case['target']['concept_id'])}
    return {str(x['concept_id']) for x in (case.get('must') or []) if isinstance(x,dict) and x.get('concept_id')}


def evaluate(cases:list[dict[str,Any]], c0:BM25, g1:BM25, exact:dict[str,set[str]], weighted:bool) -> dict[str,Any]:
    h1=h5=h10=wt=wh5=0; misses=[]
    for case in cases:
        q=str(case['query']); rel=relevant(case); a=rank(c0,exact,q); b=rank(g1,exact,q); fused=fuse_preserve_c0_top1(a,b,4)
        one=bool(fused and fused[0] in rel); five=any(x in rel for x in fused[:5]); ten=any(x in rel for x in fused[:10])
        h1+=int(one); h5+=int(five); h10+=int(ten)
        if weighted:
            w=int((case.get('target') or {}).get('occurrence_proxy') or 0); wt+=w; wh5+=w*int(five)
        if not five: misses.append({'id':case.get('id'),'query':case.get('query'),'expected':sorted(rel),'top5':fused[:5]})
    out={'cases':len(cases),'top1_pct':pct(h1,len(cases)),'hit5_pct':pct(h5,len(cases)),'hit10_pct':pct(h10,len(cases)),'miss_count':len(misses),'misses':misses}
    if weighted: out['weighted_hit5_pct']=pct(wh5,wt)
    return out


def prune_docs(c0_docs:dict[str,list[str]], g1_docs:dict[str,list[str]], k:int) -> tuple[dict[str,list[str]],dict[str,Any]]:
    enrichment={}
    df=collections.Counter()
    for sid in c0_docs:
        extra=collections.Counter(g1_docs[sid]) - collections.Counter(c0_docs[sid])
        enrichment[sid]=extra
        df.update(extra.keys())
    n=len(c0_docs)
    idf={term:math.log(1.0+(n-freq+0.5)/(freq+0.5)) for term,freq in df.items()}
    out={}; selected_total=0; original_total=sum(sum(c.values()) for c in enrichment.values())
    original_unique=sum(len(c) for c in enrichment.values())
    for sid in c0_docs:
        extra=enrichment[sid]
        ranked=sorted(extra, key=lambda t:(-(idf.get(t,0.0)*(1.0+math.log(max(1,extra[t])))),t))
        chosen=ranked[:k]
        selected_total+=len(chosen)
        out[sid]=[*c0_docs[sid],*chosen]
    return out,{
        'k_unique_enrichment_terms_per_skill':k,
        'original_enrichment_token_occurrences':original_total,
        'original_unique_skill_term_pairs':original_unique,
        'selected_unique_skill_term_pairs':selected_total,
        'selected_vs_original_unique_pct':round(100*selected_total/max(1,original_unique),3),
    }


def main()->int:
    first=load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'))
    second=load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl'))
    canonical=load_jsonl(Path('research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl'))
    synthetic=[c for c in load_jsonl(Path('research/benchmark/v31/synthetic-description-stress/cases.jsonl')) if c.get('product')=='KV']
    if (len(first),len(second),len(canonical),len(synthetic))!=(35,20,617,12): raise RuntimeError('benchmark count drift')
    second_sha=hashlib.sha256(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl').read_bytes()).hexdigest()
    if second_sha!='3960fd217deb9d7346fd78d4f281a62b614ce927e18e4ed12cbebec08a898aa7': raise RuntimeError('second holdout drift')

    excluded=first+second; excluded_ids={mid for c in excluded for mid in ids_list(c.get('module_ids'))}; excluded_texts={norm(c['query']) for c in excluded}
    tbytes=fetch_training(); tsha=hashlib.sha256(tbytes).hexdigest()
    if tsha!=TRAINING_SHA: raise RuntimeError('training source drift')
    tobj=json.loads(tbytes); modules=(tobj.get('data') or tobj.get('moduler') or tobj.get('modules')) if isinstance(tobj,dict) else tobj

    registry=json.loads(Path('research/coverage/source-adapters.json').read_text()); pareto=json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    tbody=fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json'); taxsha=hashlib.sha256(tbody).hexdigest()
    if taxsha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(tbody).get('data',{}).get('concepts'); by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    ids=p80_skill_ids(pareto); docs,exact,coverage=build_docs(by_id,ids,modules,excluded_ids,excluded_texts)
    c0=BM25(docs['KV-C0'],exact); full=BM25(docs['KV-G1-single-desc'],exact)

    configs={'full-g1':{'ranker':full,'representation':{'kind':'unpruned validated representation'}}}
    for k in KS:
        pd,stats=prune_docs(docs['KV-C0'],docs['KV-G1-single-desc'],k); configs[f'pruned-{k}']={'ranker':BM25(pd,exact),'representation':stats}

    results={}
    for name,cfg in configs.items():
        g1=cfg['ranker']; results[name]={
            'representation':cfg['representation'],
            'first_holdout_posthoc':evaluate(first,c0,g1,exact,True),
            'second_holdout_posthoc':evaluate(second,c0,g1,exact,True),
            'canonical':evaluate(canonical,c0,g1,exact,False),
            'synthetic':evaluate(synthetic,c0,g1,exact,False),
        }
    result={
        'schema_version':1,'status':'development ablation; opened holdouts; no candidate promotion',
        'question':'Can build-time discriminative pruning improve or preserve KV-G1-4slot while shrinking enrichment text?',
        'selection_rule':'per-skill enrichment terms ranked by enrichment-document IDF * (1 + ln(tf)); retain each selected term once; canonical C0 untouched',
        'ks':list(KS),'taxonomy_sha256':taxsha,'training_sha256':tsha,'g1_coverage_after_both_holdouts_excluded':coverage,'results':results,
    }
    out=Path('artifacts/skill-g1-discriminative-pruning-v31.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    compact={name:{'representation':r['representation'],'first':{k:v for k,v in r['first_holdout_posthoc'].items() if k!='misses'},'second':{k:v for k,v in r['second_holdout_posthoc'].items() if k!='misses'},'canonical':{k:v for k,v in r['canonical'].items() if k!='misses'},'synthetic':{k:v for k,v in r['synthetic'].items() if k!='misses'}} for name,r in results.items()}
    print(json.dumps(compact,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
