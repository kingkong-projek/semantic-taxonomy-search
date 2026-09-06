#!/usr/bin/env python3
"""Evaluate frozen C2 unchanged on the blinded fresh natural-query holdout."""
from __future__ import annotations

import argparse, hashlib, json, re
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_c2_job_title_router import build_c1_index, pct, read_jsonl, relation_parent_ids
from evaluate_p80_lexical_ablation import expected_hash, fetch, norm
from evaluate_pareto_c1 import BOUNDARY_IDS, p80_ids, rank_c1

COUNT_RE=re.compile(r"Observed count in frozen source review pool: ([0-9]+)\.")

def observed_count(case: dict[str,Any]) -> int:
    m=COUNT_RE.search(str(case.get('notes') or ''))
    if not m: raise RuntimeError(f"case {case.get('id')} missing frozen observed count")
    return int(m.group(1))


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--version',default='31')
    ap.add_argument('--registry',default='research/coverage/source-adapters.json')
    ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json')
    ap.add_argument('--holdout',default='research/benchmark/v31/fresh-natural-holdout/benchmark.jsonl')
    ap.add_argument('--source-truth',default='research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl')
    ap.add_argument('--output',default='artifacts/c2-fresh-natural-holdout-v31.json')
    args=ap.parse_args()

    holdout=read_jsonl(Path(args.holdout)); source_truth=read_jsonl(Path(args.source_truth))
    if len(holdout)!=30 or len(source_truth)!=333: raise RuntimeError(f'benchmark count drift: {len(holdout)}/{len(source_truth)}')
    if not all('fresh ranks 51-80 judgment made before any C2 output was generated' in str(c.get('adjudication',{}).get('review_note','')) for c in holdout):
        raise RuntimeError('fresh holdout blinding marker missing')

    registry=json.loads(Path(args.registry).read_text(encoding='utf-8')); pareto=json.loads(Path(args.pareto).read_text(encoding='utf-8')); version=str(args.version)
    url=f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json'
    body=fetch(url); taxonomy_sha=hashlib.sha256(body).hexdigest()
    if taxonomy_sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(body).get('data',{}).get('concepts')
    if not isinstance(concepts,list): raise RuntimeError('taxonomy missing concepts')
    by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}

    c1_ids=sorted(set(p80_ids(pareto)) | BOUNDARY_IDS)
    ranker, exact_surfaces, surface_tokens=build_c1_index(by_id,c1_ids)
    occurrence={str(r['concept_id']):int(r['occurrences']) for r in pareto['occupation_name']['ranked_p95']}
    label_to_parent_ids: dict[str,set[str]]=defaultdict(set); label_to_job_ids: dict[str,set[str]]=defaultdict(set)
    for cid,c in by_id.items():
        if c.get('type')!='job-title': continue
        label=norm(c.get('preferred_label'))
        if not label: continue
        parents=relation_parent_ids(c,by_id)
        if parents:
            label_to_parent_ids[label].update(parents); label_to_job_ids[label].add(cid)
    def parent_sort_key(cid: str): return (-occurrence.get(cid,0),norm(by_id[cid].get('preferred_label')),cid)
    def rank_c2(query: str) -> tuple[list[str],dict[str,Any]]:
        c1_scored=rank_c1(ranker,query,exact_surfaces,surface_tokens); c1_ranked=[cid for cid,_,_ in c1_scored]
        nq=norm(query); exact_canonical=[cid for cid in c1_ranked if nq and nq in exact_surfaces[cid]]
        routed=sorted(label_to_parent_ids.get(nq,set()),key=parent_sort_key); merged=[]
        for cid in [*exact_canonical,*routed,*c1_ranked]:
            if cid not in merged: merged.append(cid)
        return merged,{'exact_active_job_title':bool(routed),'matching_job_title_ids':sorted(label_to_job_ids.get(nq,set())),'typed_parent_ids':routed}

    stats=defaultdict(float); by_intent: dict[str,dict[str,float]]=defaultdict(lambda:defaultdict(float)); rows=[]
    for case in holdout:
        count=observed_count(case); intent=str(case['expected_intent']); positive={str(x['concept_id']) for x in case['must']+case['acceptable']}
        ranked,meta=rank_c2(str(case['query'])); top5=ranked[:5]
        if intent=='NO_MATCH': success5=not ranked; top1_ok=not ranked
        else: success5=any(cid in positive for cid in top5); top1_ok=bool(ranked and ranked[0] in positive)
        stats['cases']+=1; stats['volume']+=count; stats['success5_cases']+=int(success5); stats['success5_volume']+=count*int(success5); stats['top1_cases']+=int(top1_ok); stats['top1_volume']+=count*int(top1_ok)
        if intent=='NO_MATCH': stats['no_match_cases']+=1; stats['no_match_volume']+=count; stats['no_match_abstain_cases']+=int(not ranked); stats['no_match_abstain_volume']+=count*int(not ranked)
        else: stats['positive_cases']+=1; stats['positive_volume']+=count; stats['positive_success5_cases']+=int(success5); stats['positive_success5_volume']+=count*int(success5)
        z=by_intent[intent]; z['cases']+=1; z['volume']+=count; z['success5_cases']+=int(success5); z['success5_volume']+=count*int(success5)
        rows.append({'id':case['id'],'query':case['query'],'intent':intent,'observed_count':count,'discovery_success_at_5':success5,'top1_success':top1_ok,'exact_job_title_route':meta['exact_active_job_title'],'top5_ids':top5})
    def intent_summary(z): return {'cases':int(z['cases']),'observed_volume':int(z['volume']),'discovery_success_at_5_pct':pct(z['success5_cases'],z['cases']),'volume_weighted_discovery_success_at_5_pct':pct(z['success5_volume'],z['volume'])}
    holdout_result={
        'cases':int(stats['cases']),'observed_volume':int(stats['volume']),
        'discovery_success_at_5_pct':pct(stats['success5_cases'],stats['cases']),
        'volume_weighted_discovery_success_at_5_pct':pct(stats['success5_volume'],stats['volume']),
        'positive_intent_discovery_success_at_5_pct':pct(stats['positive_success5_cases'],stats['positive_cases']),
        'positive_intent_volume_weighted_discovery_success_at_5_pct':pct(stats['positive_success5_volume'],stats['positive_volume']),
        'no_match_abstention_pct':pct(stats['no_match_abstain_cases'],stats['no_match_cases']),
        'no_match_volume_weighted_abstention_pct':pct(stats['no_match_abstain_volume'],stats['no_match_volume']),
        'top1_pct':pct(stats['top1_cases'],stats['cases']),'volume_weighted_top1_pct':pct(stats['top1_volume'],stats['volume']),
        'by_intent':{k:intent_summary(v) for k,v in sorted(by_intent.items())},'cases_detail':rows,
        'interpretation':'independent fresh natural-language holdout; judgments were frozen before C2 output was generated',
    }

    st_top1=st_hit5=0; misses=[]
    for case in source_truth:
        positive={str(x['concept_id']) for x in case['must']}; ranked,_=rank_c2(str(case['query']))
        top1=bool(ranked and ranked[0] in positive); hit5=any(cid in positive for cid in ranked[:5]); st_top1+=int(top1); st_hit5+=int(hit5)
        if not top1: misses.append({'id':case['id'],'query':case['query'],'top5':ranked[:5]})
    regression={'cases':333,'top1_pct':pct(st_top1,333),'discovery_hit_at_5_pct':pct(st_hit5,333),'top1_miss_count':len(misses),'top1_misses_first_20':misses[:20]}
    result={'schema_version':1,'taxonomy_version':31,'taxonomy_sha256':taxonomy_sha,'configuration':{'name':'C2','frozen_behavior':'C1 + exact active job-title preferred-label -> typed occupation-name parents','primary_metric':'Discovery Success@5 + NO_MATCH abstention'},'fresh_natural_holdout':holdout_result,'source_truth_regression':regression}
    p=Path(args.output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'fresh_natural_holdout':{k:v for k,v in holdout_result.items() if k!='cases_detail'},'source_truth_regression':regression},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
