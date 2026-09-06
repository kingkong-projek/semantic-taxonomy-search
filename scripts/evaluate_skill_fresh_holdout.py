#!/usr/bin/env python3
"""Evaluate frozen KV-C0 and the preselected minimal KV-F1 close-match fusion on the blind skill holdout.

The 35-case holdout was frozen before this evaluator existed. No holdout text is added to
retrieval documents. KV-F1 was selected on the separate 76-case development benchmark and
is unchanged here: preserve C0 rank 1, allow at most one close-match candidate into the
remaining top-5 slots, then fill from C0.
"""
from __future__ import annotations

import argparse, hashlib, json
from pathlib import Path

from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, tokens
from evaluate_skill_c0_training_validation import build_c0, p80_skill_ids, pct, positive_rank
from evaluate_skill_esco_candidate_lanes import canonical_text, positive_bm25_rank, relation_ids
from evaluate_skill_esco_fusion import fuse

EXPECTED_HOLDOUT_SHA = "79816eb2020b100bf8260b8f1807069288c30dbabd457bfffbfe3f49735c6675"


def summarize(cases, c0_ranker, c0_exact, close_ranker, *, use_fusion: bool):
    n=weight=hit1=hit5=hit10=whit1=whit5=whit10=0
    details=[]
    for case in cases:
        q=str(case['query']); target=str(case['target']['concept_id']); w=int(case['target']['occurrence_proxy'])
        c0=positive_rank(c0_ranker,c0_exact,q)
        lane=positive_bm25_rank(close_ranker,q)
        ranked=fuse(c0,lane,1) if use_fusion else c0
        h1=bool(ranked and ranked[0]==target); h5=target in ranked[:5]; h10=target in ranked[:10]
        n+=1; weight+=w; hit1+=int(h1); hit5+=int(h5); hit10+=int(h10)
        whit1+=w*int(h1); whit5+=w*int(h5); whit10+=w*int(h10)
        details.append({
            'id':case['id'],'target_id':target,'target_label':case['target']['label'],
            'c0_hit5':target in c0[:5],'close_lane_hit5':target in lane[:5],
            'result_hit5':h5,'result_top5_ids':ranked[:5],
        })
    return {
        'cases':n,'occurrence_proxy_weight':weight,
        'top1_pct':pct(hit1,n),'weighted_top1_pct':pct(whit1,weight),
        'discovery_hit_at_5_pct':pct(hit5,n),'weighted_discovery_hit_at_5_pct':pct(whit5,weight),
        'hit_at_10_pct':pct(hit10,n),'weighted_hit_at_10_pct':pct(whit10,weight),
    },details


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--version',default='31')
    ap.add_argument('--registry',default='research/coverage/source-adapters.json')
    ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json')
    ap.add_argument('--benchmark',default='research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl')
    ap.add_argument('--manifest',default='research/benchmark/v31/training-skill-fresh-holdout/manifest.json')
    ap.add_argument('--source-truth',default='research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl')
    ap.add_argument('--output',default='artifacts/skill-fresh-holdout-v31.json')
    args=ap.parse_args()

    bp=Path(args.benchmark); body=bp.read_bytes(); actual=hashlib.sha256(body).hexdigest()
    manifest=json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    if actual!=EXPECTED_HOLDOUT_SHA or manifest.get('benchmark_sha256')!=EXPECTED_HOLDOUT_SHA:
        raise RuntimeError(f'blind holdout drift: {actual}')
    cases=load_jsonl(bp); source_truth=load_jsonl(Path(args.source_truth))
    if len(cases)!=35 or len(source_truth)!=617: raise RuntimeError('benchmark count drift')
    if not all(c.get('authority_boundary','').startswith('frozen blind holdout truth') for c in cases):
        raise RuntimeError('holdout authority boundary drift')

    registry=json.loads(Path(args.registry).read_text(encoding='utf-8'))
    pareto=json.loads(Path(args.pareto).read_text(encoding='utf-8')); version=str(args.version)
    url=f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json'
    tax_body=fetch(url); tax_sha=hashlib.sha256(tax_body).hexdigest()
    if tax_sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(tax_body).get('data',{}).get('concepts')
    if not isinstance(concepts,list): raise RuntimeError('taxonomy missing concepts')
    by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    ids=p80_skill_ids(pareto); c0_ranker,c0_exact=build_c0(by_id,ids)

    close_docs={}
    for sid in ids:
        tids=relation_ids(by_id[sid],'close_match',by_id)
        text=' '.join(canonical_text(by_id[t]) for t in tids if canonical_text(by_id[t]))
        if text: close_docs[sid]=tokens(text)
    close_ranker=BM25(close_docs,{sid:set() for sid in close_docs})
    if len(close_docs)!=105: raise RuntimeError(f'close lane document drift: {len(close_docs)}')

    c0,c0_details=summarize(cases,c0_ranker,c0_exact,close_ranker,use_fusion=False)
    f1,f1_details=summarize(cases,c0_ranker,c0_exact,close_ranker,use_fusion=True)

    # Canonical regression for the frozen F1 policy.
    st_top1=st_hit5=0; failures=[]
    for case in source_truth:
        positives={str(x['concept_id']) for x in case['must']}; q=str(case['query'])
        c0r=positive_rank(c0_ranker,c0_exact,q); lane=positive_bm25_rank(close_ranker,q); ranked=fuse(c0r,lane,1)
        t1=bool(ranked and ranked[0] in positives); h5=any(cid in positives for cid in ranked[:5])
        st_top1+=int(t1); st_hit5+=int(h5)
        if not t1 or not h5: failures.append({'id':case['id'],'top5_ids':ranked[:5],'top1_ok':t1,'hit5':h5})
    regression={'cases':617,'top1_pct':pct(st_top1,617),'discovery_hit_at_5_pct':pct(st_hit5,617),'failure_count':len(failures),'failures_first_20':failures[:20]}

    out={
        'schema_version':1,'taxonomy_version':31,'taxonomy_sha256':tax_sha,
        'experiment_role':'independent validation; blind holdout frozen before evaluator and before KV-F1 sees these queries',
        'holdout':manifest,
        'configurations':{
            'KV-C0':c0,
            'KV-F1-close-one-slot':f1,
        },
        'delta':{
            'discovery_hit_at_5_percentage_points':round(f1['discovery_hit_at_5_pct']-c0['discovery_hit_at_5_pct'],3),
            'weighted_discovery_hit_at_5_percentage_points':round(f1['weighted_discovery_hit_at_5_pct']-c0['weighted_discovery_hit_at_5_pct'],3),
        },
        'source_truth_regression':regression,
        'runtime_implication':'both C0 and F1 are deterministic and fully build-time compilable; no API, ML, vectors or runtime model required',
        'cases_detail':{'KV-C0':c0_details,'KV-F1-close-one-slot':f1_details},
    }
    p=Path(args.output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'KV-C0':c0,'KV-F1-close-one-slot':f1,'delta':out['delta'],'source_truth_regression':regression},ensure_ascii=False,indent=2,sort_keys=True))
    return 0

if __name__=='__main__': raise SystemExit(main())
