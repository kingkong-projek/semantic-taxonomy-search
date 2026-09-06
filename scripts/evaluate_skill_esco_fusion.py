#!/usr/bin/env python3
"""Evaluate minimal deterministic fusion of KV-C0 with separate ESCO candidate lanes.

Development ablation only. C0 rank 1 is always preserved. One or two of the remaining
top-5 positions may be offered to a single ESCO mapping lane before the rest are filled
from C0. Mapping types stay separate and ESCO identities are never emitted.
"""
from __future__ import annotations

import argparse, hashlib, json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import build_c0, p80_skill_ids, pct, positive_rank
from evaluate_skill_esco_candidate_lanes import relation_ids, canonical_text, positive_bm25_rank

CONFIGS = {
    "KV-C0": (None, 0),
    "KV-F1-exact-one-slot": ("exact_match", 1),
    "KV-F1-close-one-slot": ("close_match", 1),
    "KV-F1-narrow-one-slot": ("narrow_match", 1),
    "KV-F1-narrow-two-slot": ("narrow_match", 2),
}


def fuse(c0: list[str], lane: list[str], lane_slots: int) -> list[str]:
    if not c0:
        return lane[:5]
    if lane_slots <= 0:
        return c0[:5]
    out = [c0[0]]
    added = 0
    for sid in lane:
        if sid in out:
            continue
        out.append(sid)
        added += 1
        if added >= lane_slots:
            break
    for sid in c0[1:]:
        if sid not in out:
            out.append(sid)
        if len(out) >= 5:
            break
    return out[:5]


def summarize(cases: list[dict[str, Any]], c0_ranker: BM25, c0_exact: dict[str,set[str]], lane_ranker: BM25 | None, slots: int) -> tuple[dict[str,Any],list[dict[str,Any]]]:
    s=defaultdict(float); details=[]
    for case in cases:
        q=str(case['query']); target=str(case['target']['concept_id']); weight=int(case['target']['occurrence_proxy'])
        c0=positive_rank(c0_ranker,c0_exact,q)
        lane=positive_bm25_rank(lane_ranker,q) if lane_ranker is not None else []
        top5=fuse(c0,lane,slots)
        h1=bool(top5 and top5[0]==target); h5=target in top5
        s['cases']+=1; s['weight']+=weight; s['h1']+=int(h1); s['h5']+=int(h5); s['wh1']+=weight*int(h1); s['wh5']+=weight*int(h5)
        details.append({'id':case['id'],'target_id':target,'c0_hit5':target in c0[:5],'lane_hit5':target in lane[:5],'fused_hit5':h5,'fused_top5_ids':top5})
    return {
        'cases':int(s['cases']),'occurrence_proxy_weight':int(s['weight']),
        'top1_pct':pct(s['h1'],s['cases']),'weighted_top1_pct':pct(s['wh1'],s['weight']),
        'discovery_hit_at_5_pct':pct(s['h5'],s['cases']),'weighted_discovery_hit_at_5_pct':pct(s['wh5'],s['weight']),
    },details


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--version',default='31')
    ap.add_argument('--registry',default='research/coverage/source-adapters.json')
    ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json')
    ap.add_argument('--benchmark',default='research/benchmark/v31/training-skill-validation/cases.jsonl')
    ap.add_argument('--source-truth',default='research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl')
    ap.add_argument('--output',default='artifacts/skill-esco-fusion-v31.json')
    args=ap.parse_args()

    cases=load_jsonl(Path(args.benchmark)); primary=[c for c in cases if c.get('primary_descriptive_nonleaky')]; source_truth=load_jsonl(Path(args.source_truth))
    if len(cases)!=76 or len(primary)!=63 or len(source_truth)!=617: raise RuntimeError('benchmark count drift')
    registry=json.loads(Path(args.registry).read_text(encoding='utf-8')); pareto=json.loads(Path(args.pareto).read_text(encoding='utf-8')); version=str(args.version)
    url=f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json'
    body=fetch(url); sha=hashlib.sha256(body).hexdigest()
    if sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(body).get('data',{}).get('concepts')
    if not isinstance(concepts,list): raise RuntimeError('taxonomy missing concepts')
    by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    ids=p80_skill_ids(pareto); c0_ranker,c0_exact=build_c0(by_id,ids)

    lane_rankers={}
    for mapping in ('exact_match','close_match','narrow_match'):
        docs={}
        for sid in ids:
            tids=relation_ids(by_id[sid],mapping,by_id)
            text=' '.join(canonical_text(by_id[tid]) for tid in tids if canonical_text(by_id[tid]))
            if text: docs[sid]=tokens(text)
        lane_rankers[mapping]=BM25(docs,{sid:set() for sid in docs})

    benchmark={}; details={}; regression={}
    for name,(mapping,slots) in CONFIGS.items():
        lr=lane_rankers.get(mapping) if mapping else None
        all_s,all_d=summarize(cases,c0_ranker,c0_exact,lr,slots); prim_s,prim_d=summarize(primary,c0_ranker,c0_exact,lr,slots)
        benchmark[name]={'all_cases':all_s,'primary_descriptive_nonleaky':prim_s}; details[name]=prim_d
        # C0 rank1 is structurally preserved for every nonempty C0 result. Verify on frozen canonical suite.
        top1=hit5=0; failures=[]
        for case in source_truth:
            positive={str(x['concept_id']) for x in case['must']}; q=str(case['query']); c0=positive_rank(c0_ranker,c0_exact,q); lane=positive_bm25_rank(lr,q) if lr is not None else []; top5=fuse(c0,lane,slots)
            t1=bool(top5 and top5[0] in positive); h5=any(sid in positive for sid in top5); top1+=int(t1); hit5+=int(h5)
            if not t1 or not h5: failures.append({'id':case['id'],'top5':top5,'top1_ok':t1,'hit5':h5})
        regression[name]={'cases':617,'top1_pct':pct(top1,617),'discovery_hit_at_5_pct':pct(hit5,617),'failure_count':len(failures),'failures_first_20':failures[:20]}

    result={
        'schema_version':1,'taxonomy_version':int(version),'taxonomy_sha256':sha,
        'experiment_role':'development ablation; frozen training benchmark was opened before fusion design',
        'fusion_policy':'preserve C0 rank1; offer one or two remaining top-5 slots to exactly one typed ESCO lane; fill remainder from C0',
        'mapping_semantics_guard':'exact/close/narrow stay separate; broad excluded from fusion after weak candidate-lane rescue signal',
        'identity_boundary':'only AF v31 skill IDs are emitted; ESCO is retrieval evidence only',
        'runtime_implication':'deterministic static candidate fusion; all inputs are precompilable and no API or ML is required',
        'benchmark':benchmark,'source_truth_regression':regression,'cases_detail':details,
    }
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'benchmark':benchmark,'source_truth_regression':regression},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
