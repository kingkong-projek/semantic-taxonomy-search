#!/usr/bin/env python3
"""Compare the two smallest one-slot skill fusion candidates before fresh holdout.

Candidates are fixed from prior lane diagnostics:
- close_match ESCO lane (typed mapping, pinned taxonomy snapshot)
- KV calculated_skills context lane (pinned published selector)

Both preserve KV-C0 rank 1 and may occupy at most one of the remaining top-5 slots.
This is development selection only; the winner must be frozen before fresh holdout.
"""
from __future__ import annotations

import argparse, hashlib, json
from pathlib import Path

from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, tokens
from evaluate_skill_c0_training_validation import build_c0, p80_skill_ids, pct, positive_rank
from evaluate_skill_esco_candidate_lanes import relation_ids, canonical_text, positive_bm25_rank
from evaluate_skill_esco_fusion import fuse
from evaluate_skill_native_selector_candidate_lanes import layer_skill_ids


def summarize(cases, c0_ranker, c0_exact, lane_ranker):
    cases_n=weight=hit1=hit5=whit1=whit5=0
    details=[]
    for case in cases:
        q=str(case['query']); target=str(case['target']['concept_id']); w=int(case['target']['occurrence_proxy'])
        c0=positive_rank(c0_ranker,c0_exact,q); lane=positive_bm25_rank(lane_ranker,q); top5=fuse(c0,lane,1)
        h1=bool(top5 and top5[0]==target); h5=target in top5
        cases_n+=1; weight+=w; hit1+=int(h1); hit5+=int(h5); whit1+=w*int(h1); whit5+=w*int(h5)
        details.append({'id':case['id'],'target_id':target,'c0_hit5':target in c0[:5],'lane_hit5':target in lane[:5],'fused_hit5':h5,'top5_ids':top5})
    return {'cases':cases_n,'occurrence_proxy_weight':weight,'top1_pct':pct(hit1,cases_n),'weighted_top1_pct':pct(whit1,weight),'discovery_hit_at_5_pct':pct(hit5,cases_n),'weighted_discovery_hit_at_5_pct':pct(whit5,weight)},details


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--version',default='31'); ap.add_argument('--registry',default='research/coverage/source-adapters.json'); ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json'); ap.add_argument('--selector-aggregate',default='research/coverage/v31/selector-aggregate.json'); ap.add_argument('--benchmark',default='research/benchmark/v31/training-skill-validation/cases.jsonl'); ap.add_argument('--source-truth',default='research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl'); ap.add_argument('--output',default='artifacts/skill-simple-fusion-candidates-v31.json'); args=ap.parse_args()
    cases=load_jsonl(Path(args.benchmark)); primary=[c for c in cases if c.get('primary_descriptive_nonleaky')]; source_truth=load_jsonl(Path(args.source_truth))
    if len(cases)!=76 or len(primary)!=63 or len(source_truth)!=617: raise RuntimeError('benchmark count drift')
    registry=json.loads(Path(args.registry).read_text()); pareto=json.loads(Path(args.pareto).read_text()); selector=json.loads(Path(args.selector_aggregate).read_text()); version=str(args.version)
    tax_url=f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json'; tax_body=fetch(tax_url); tax_sha=hashlib.sha256(tax_body).hexdigest()
    if tax_sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(tax_body).get('data',{}).get('concepts');
    if not isinstance(concepts,list): raise RuntimeError('taxonomy missing concepts')
    by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}; ids=p80_skill_ids(pareto); skill_set=set(ids); c0_ranker,c0_exact=build_c0(by_id,ids)

    # Close ESCO lane.
    close_docs={}
    for sid in ids:
        tids=relation_ids(by_id[sid],'close_match',by_id); text=' '.join(canonical_text(by_id[t]) for t in tids if canonical_text(by_id[t]))
        if text: close_docs[sid]=tokens(text)
    close_ranker=BM25(close_docs,{sid:set() for sid in close_docs})

    # KV calculated context lane. Context labels/definitions only; emitted IDs remain skills.
    kv_meta=selector['kompetensvaljaren']; kv_body=fetch(str(kv_meta['source'])); kv_sha=hashlib.sha256(kv_body).hexdigest()
    if kv_sha!=str(kv_meta['source_sha256']): raise RuntimeError('KV selector source drift')
    kv_data=json.loads(kv_body).get('data');
    if not isinstance(kv_data,dict): raise RuntimeError('KV selector missing data')
    contexts={sid:set() for sid in ids}
    for cid,record in kv_data.items():
        if not isinstance(record,dict) or record.get('type') not in ('occupation-name','ssyk-level-4'): continue
        calc=layer_skill_ids(record,'calculated_skills') & skill_set
        for sid in calc: contexts[sid].add(str(cid))
    calc_docs={}
    for sid,cids in contexts.items():
        text=' '.join(canonical_text(by_id[cid]) for cid in sorted(cids) if cid in by_id and canonical_text(by_id[cid]))
        if text: calc_docs[sid]=tokens(text)
    calc_ranker=BM25(calc_docs,{sid:set() for sid in calc_docs})

    configs={'KV-F1-close-one-slot':close_ranker,'KV-F1-calculated-one-slot':calc_ranker}
    out={'schema_version':1,'taxonomy_version':31,'taxonomy_sha256':tax_sha,'kv_selector_sha256':kv_sha,'experiment_role':'final development candidate comparison before blinded holdout','fusion_policy':'preserve C0 rank1; one remaining top-5 slot to exactly one separate candidate lane','runtime_implication':'both candidates are deterministic and build-time compilable; no API or ML required','candidates':{},'source_truth_regression':{}}
    for name,ranker in configs.items():
        alls,_=summarize(cases,c0_ranker,c0_exact,ranker); prim,details=summarize(primary,c0_ranker,c0_exact,ranker); out['candidates'][name]={'all_cases':alls,'primary_descriptive_nonleaky':prim,'lane_document_count':len(ranker.documents),'cases_detail':details}
        top1=hit5=0; failures=[]
        for c in source_truth:
            positives={str(x['concept_id']) for x in c['must']}; q=str(c['query']); c0=positive_rank(c0_ranker,c0_exact,q); lane=positive_bm25_rank(ranker,q); top5=fuse(c0,lane,1); t1=bool(top5 and top5[0] in positives); h5=any(s in positives for s in top5); top1+=int(t1); hit5+=int(h5)
            if not t1 or not h5: failures.append({'id':c['id'],'top5':top5,'top1_ok':t1,'hit5':h5})
        out['source_truth_regression'][name]={'cases':617,'top1_pct':pct(top1,617),'discovery_hit_at_5_pct':pct(hit5,617),'failure_count':len(failures),'failures_first_20':failures[:20]}
    p=Path(args.output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n'); print(json.dumps({'candidates':out['candidates'],'source_truth_regression':out['source_truth_regression']},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
