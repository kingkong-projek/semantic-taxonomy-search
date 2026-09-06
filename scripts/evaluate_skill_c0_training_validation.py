#!/usr/bin/env python3
"""Evaluate unchanged KV C0 on source-attested natural training text -> P80 skill mappings.

C0 index uses ONLY JobTech Taxonomy v31 P80 skill preferred labels, real canonical
definitions and canonical alternative labels. Labour-market-training module text is query
input / benchmark truth only and is never added to retrieval documents.
"""
from __future__ import annotations

import argparse, hashlib, json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, load_jsonl, norm, tokens


def pct(n: float, d: float) -> float:
    return round(100.0*n/d,3) if d else 0.0


def p80_skill_ids(pareto: dict[str,Any]) -> list[str]:
    section=pareto['skill']; n=int(section['thresholds']['p80']['concept_count']); ids=[str(r['concept_id']) for r in section['ranked_p95'][:n]]
    if n!=316 or len(ids)!=316 or len(set(ids))!=316: raise RuntimeError('P80 skill membership drift')
    return ids


def build_c0(by_id: dict[str,dict[str,Any]], ids: list[str]) -> tuple[BM25,dict[str,set[str]]]:
    docs={}; exact={}
    for cid in ids:
        c=by_id.get(cid)
        if not isinstance(c,dict) or c.get('type')!='skill': raise RuntimeError(f'invalid P80 skill {cid}')
        label=str(c.get('preferred_label') or '').strip(); definition=str(c.get('definition') or '').strip()
        real_definition=definition if definition and norm(definition)!=norm(label) else ''
        alternatives=[x for x in as_list(c.get('alternative_labels')) if norm(x)!=norm(label)]
        docs[cid]=tokens(' '.join([label,real_definition,*alternatives]))
        exact[cid]={norm(label), *[norm(x) for x in alternatives if norm(x)]}
    return BM25(docs,exact),exact


def positive_rank(ranker: BM25, exact: dict[str,set[str]], query: str) -> list[str]:
    q=tokens(query); nq=norm(query); scored=[]
    for cid in ranker.documents:
        score=ranker.score(q,cid)
        if nq and nq in exact[cid]: score+=1_000_000.0
        if score>0.0: scored.append((score,cid))
    scored.sort(key=lambda x:(-x[0],x[1])); return [cid for _,cid in scored]


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--version',default='31')
    ap.add_argument('--registry',default='research/coverage/source-adapters.json')
    ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json')
    ap.add_argument('--benchmark',default='research/benchmark/v31/training-skill-validation/cases.jsonl')
    ap.add_argument('--benchmark-manifest',default='research/benchmark/v31/training-skill-validation/manifest.json')
    ap.add_argument('--source-truth',default='research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl')
    ap.add_argument('--output',default='artifacts/skill-c0-training-validation-v31.json')
    args=ap.parse_args()

    cases=load_jsonl(Path(args.benchmark)); source_truth=load_jsonl(Path(args.source_truth)); manifest=json.loads(Path(args.benchmark_manifest).read_text(encoding='utf-8'))
    if len(cases)!=76 or len(source_truth)!=617 or manifest['primary_descriptive_nonleaky_cases']!=63: raise RuntimeError('benchmark count drift')
    if not all(c.get('authority_boundary')=='benchmark truth only; module text must not be added to retrieval documents before baseline evaluation' for c in cases): raise RuntimeError('benchmark authority boundary drift')

    registry=json.loads(Path(args.registry).read_text(encoding='utf-8')); pareto=json.loads(Path(args.pareto).read_text(encoding='utf-8')); version=str(args.version)
    url=f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json'
    body=fetch(url); taxonomy_sha=hashlib.sha256(body).hexdigest(); expected=expected_hash(registry,'taxonomy-common-relations')
    if taxonomy_sha!=expected: raise RuntimeError(f'taxonomy source drift {taxonomy_sha} != {expected}')
    concepts=json.loads(body).get('data',{}).get('concepts')
    if not isinstance(concepts,list): raise RuntimeError('taxonomy missing concepts')
    by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    ids=p80_skill_ids(pareto); ranker,exact=build_c0(by_id,ids)

    stats=defaultdict(float); primary_stats=defaultdict(float); groups: dict[str,dict[str,float]]=defaultdict(lambda:defaultdict(float)); details=[]
    for case in cases:
        query=str(case['query']); target=str(case['target']['concept_id']); weight=int(case['target']['occurrence_proxy']); ranked=positive_rank(ranker,exact,query); top5=ranked[:5]; top10=ranked[:10]
        hit1=bool(ranked and ranked[0]==target); hit5=target in top5; hit10=target in top10; abstain=not ranked; primary=bool(case['primary_descriptive_nonleaky'])
        for s in (stats, primary_stats if primary else None):
            if s is None: continue
            s['cases']+=1; s['weight']+=weight; s['hit1']+=int(hit1); s['hit5']+=int(hit5); s['hit10']+=int(hit10); s['weighted_hit1']+=weight*int(hit1); s['weighted_hit5']+=weight*int(hit5); s['weighted_hit10']+=weight*int(hit10); s['abstain']+=int(abstain); s['weighted_abstain']+=weight*int(abstain)
        key='primary_descriptive_nonleaky' if primary else 'diagnostic_leaky_or_terse'; g=groups[key]; g['cases']+=1; g['hit5']+=int(hit5); g['weight']+=weight; g['weighted_hit5']+=weight*int(hit5)
        details.append({'id':case['id'],'module_name':case['module_name'],'target':case['target'],'primary_descriptive_nonleaky':primary,'direct_label_leakage':case['direct_label_leakage'],'terse_text':case['terse_text'],'positive_evidence':not abstain,'top1_success':hit1,'discovery_hit_at_5':hit5,'hit_at_10':hit10,'top5_ids':top5,'top10_ids':top10})
    def summary(s): return {'cases':int(s['cases']),'occurrence_proxy_weight':int(s['weight']),'top1_pct':pct(s['hit1'],s['cases']),'weighted_top1_pct':pct(s['weighted_hit1'],s['weight']),'discovery_hit_at_5_pct':pct(s['hit5'],s['cases']),'weighted_discovery_hit_at_5_pct':pct(s['weighted_hit5'],s['weight']),'hit_at_10_pct':pct(s['hit10'],s['cases']),'weighted_hit_at_10_pct':pct(s['weighted_hit10'],s['weight']),'zero_positive_evidence_cases':int(s['abstain']),'weighted_zero_positive_evidence_pct':pct(s['weighted_abstain'],s['weight'])}
    group_out={k:{'cases':int(v['cases']),'discovery_hit_at_5_pct':pct(v['hit5'],v['cases']),'weighted_discovery_hit_at_5_pct':pct(v['weighted_hit5'],v['weight'])} for k,v in sorted(groups.items())}

    # Regression: unchanged C0 must still solve its frozen 617-case canonical KV suite.
    st_top1=st_hit5=0; misses=[]
    for case in source_truth:
        positive={str(x['concept_id']) for x in case['must']}; ranked=positive_rank(ranker,exact,str(case['query'])); t1=bool(ranked and ranked[0] in positive); h5=any(cid in positive for cid in ranked[:5]); st_top1+=int(t1); st_hit5+=int(h5)
        if not t1: misses.append({'id':case['id'],'query':case['query'],'expected':sorted(positive),'top5':ranked[:5]})
    regression={'cases':617,'top1_pct':pct(st_top1,617),'discovery_hit_at_5_pct':pct(st_hit5,617),'top1_miss_count':len(misses),'top1_misses_first_20':misses[:20]}

    result={'schema_version':1,'taxonomy_version':31,'taxonomy_sha256':taxonomy_sha,'configuration':{'name':'KV-C0','algorithm':'deterministic BM25 with exact canonical surface dominance','retrieval_documents':'P80 skill preferred labels + real canonical definitions + canonical alternative labels only','training_text_ingested':False,'primary_metric':'Discovery Hit@5 on primary descriptive/nonleaky manual-mapping cases'},'benchmark':manifest,'all_cases':summary(stats),'primary_descriptive_nonleaky':summary(primary_stats),'by_group':group_out,'source_truth_regression':regression,'cases_detail':details}
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'all_cases':result['all_cases'],'primary_descriptive_nonleaky':result['primary_descriptive_nonleaky'],'by_group':group_out,'source_truth_regression':regression},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
