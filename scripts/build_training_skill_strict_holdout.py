#!/usr/bin/env python3
"""Build a stricter source-attested KV holdout with exactly one mapped skill total.

No retrieval/model code. Excludes all module IDs and normalized query texts used by the
76-case development set and the first three natural holdouts. Eligible rows must map to
exactly one skill in the AF source, that skill must lie in the frozen P80 envelope, the
query must not directly contain the canonical label, and the text must be non-terse.
Select at most two deterministic rows per target in round-robin order.
"""
from __future__ import annotations

import argparse, hashlib, json, re, urllib.request
from collections import defaultdict, Counter
from pathlib import Path
from typing import Any

URL='https://data.arbetsformedlingen.se/utbildningar/mappings/mapping_labour-market-training.json'
PINNED_SHA='fea97867a1225e078d28ab9b0772f6a37f92b37c3c6c0d0e886ae65e9d79361c'
UA='semantic-taxonomy-search-strict-skill-holdout/0.1'
MAX_PER_SKILL=2


def fetch()->bytes:
    req=urllib.request.Request(URL,headers={'Accept':'application/json','User-Agent':UA})
    with urllib.request.urlopen(req,timeout=240) as r: return r.read()
def norm(x:Any)->str: return re.sub(r'\s+',' ',str(x or '')).strip().casefold()
def ids_list(v:Any)->list[str]:
    if isinstance(v,list): return [str(x) for x in v]
    return [] if v in (None,'') else [str(v)]
def terse(desc:str)->bool:
    n=norm(desc); return n.startswith('för innehåll, se') or n.startswith('undervisning i') or len(n)<60
def load_jsonl(path:Path)->list[dict[str,Any]]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json')
    ap.add_argument('--development',default='research/benchmark/v31/training-skill-validation/cases.jsonl')
    ap.add_argument('--first',default='research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl')
    ap.add_argument('--second',default='research/benchmark/v31/training-skill-second-holdout/cases.jsonl')
    ap.add_argument('--third',default='research/benchmark/v31/training-skill-third-holdout/cases.jsonl')
    ap.add_argument('--output-dir',default='artifacts/training-skill-strict-holdout-v31')
    args=ap.parse_args()

    dev=load_jsonl(Path(args.development)); first=load_jsonl(Path(args.first)); second=load_jsonl(Path(args.second)); third=load_jsonl(Path(args.third))
    if (len(dev),len(first),len(second),len(third))!=(76,35,20,26): raise RuntimeError('prior benchmark count drift')
    prior=dev+first+second+third
    excluded_ids={mid for c in prior for mid in ids_list(c.get('module_ids'))}; excluded_texts={norm(c['query']) for c in prior}

    pareto=json.loads(Path(args.pareto).read_text()); sec=pareto['skill']; n=int(sec['thresholds']['p80']['concept_count']); ranked=sec['ranked_p95'][:n]
    if n!=316: raise RuntimeError('P80 count drift')
    p80={str(r['concept_id']):{'rank':i+1,'occurrences':int(r['occurrences']),'label':str(r['label'])} for i,r in enumerate(ranked)}

    body=fetch(); sha=hashlib.sha256(body).hexdigest()
    if sha!=PINNED_SHA: raise RuntimeError(f'source drift {sha}')
    obj=json.loads(body); modules=(obj.get('data') or obj.get('moduler') or obj.get('modules')) if isinstance(obj,dict) else obj
    if not isinstance(modules,list): raise RuntimeError('unexpected source root')

    grouped:dict[str,list[dict[str,Any]]]=defaultdict(list); reject=defaultdict(int)
    for idx,m in enumerate(modules):
        if not isinstance(m,dict): continue
        desc=str(m.get('modulbeskrivning') or '').strip(); ndesc=norm(desc); mids=ids_list(m.get('modul_id'))
        if not ndesc: reject['empty']+=1; continue
        if any(mid in excluded_ids for mid in mids) or ndesc in excluded_texts: reject['prior_use']+=1; continue
        mapped=[]
        for x in m.get('kompetenser_kopplade_till_modulen') or []:
            if isinstance(x,dict) and x.get('koncept_id'):
                mapped.append((str(x['koncept_id']),str(x.get('kompetensnamn') or '')))
        unique_all=sorted({cid for cid,_ in mapped})
        if len(unique_all)!=1: reject['not_exactly_one_total_mapped_skill']+=1; continue
        cid=unique_all[0]
        if cid not in p80: reject['single_skill_outside_p80']+=1; continue
        label=p80[cid]['label']
        if norm(label) and norm(label) in ndesc: reject['direct_label_leakage']+=1; continue
        if terse(desc): reject['terse']+=1; continue
        grouped[cid].append({'source_index':idx,'module_name':str(m.get('modulnamn') or ''),'module_ids':mids,'query':desc,'source_skill_label':next((lab for x,lab in mapped if x==cid),'')})

    def quality(r:dict[str,Any]):
        d=r['query']; return (len(d)>1800,abs(min(len(d),1800)-450),norm(r['module_name']),r['source_index'])
    for rows in grouped.values(): rows.sort(key=quality)
    ordered=sorted(grouped,key=lambda cid:(p80[cid]['rank'],cid)); selected=[]
    for round_idx in range(MAX_PER_SKILL):
        for cid in ordered:
            if round_idx<len(grouped[cid]): selected.append((cid,grouped[cid][round_idx],round_idx+1))

    cases=[]
    for i,(cid,row,within) in enumerate(selected,1):
        meta=p80[cid]
        cases.append({
            'id':f'kv.training-skill-strict-holdout.{i:03d}','query':row['query'],
            'target':{'concept_id':cid,'label':meta['label'],'p80_rank':meta['rank'],'occurrence_proxy':meta['occurrences']},
            'module_name':row['module_name'],'module_ids':row['module_ids'],'all_mapped_skill_ids':[cid],'source_skill_label':row['source_skill_label'],'within_skill_holdout_index':within,
            'primary_descriptive_nonleaky':True,'direct_label_leakage':False,'terse_text':False,
            'source_evidence':{'source':URL,'sha256':PINNED_SHA,'provenance':'manual_curated_mapping','semantics':'AF source row maps this module to exactly one skill in total, and that skill lies in the frozen P80 envelope'},
            'authority_boundary':'frozen strict holdout truth; mapping remains fallible evidence and every material error must still be manually adjudicated; query text and module ids must be excluded from retrieval evidence before evaluation'
        })
    text=''.join(json.dumps(c,ensure_ascii=False,sort_keys=True)+'\n' for c in cases); counts=Counter(c['target']['concept_id'] for c in cases)
    manifest={
        'schema_version':1,'taxonomy_version':31,'source_url':URL,'source_sha256':PINNED_SHA,
        'selection':'all prior development/three-holdout module IDs and normalized query texts excluded; exactly one mapped skill total; target in P80; no direct label leakage; non-terse; deterministic quality ordering; round-robin at most two rows per target',
        'cases':len(cases),'unique_p80_skills':len(counts),'max_cases_per_skill':max(counts.values()) if counts else 0,'skills_with_two_cases':sum(v==2 for v in counts.values()),
        'prior_cases_excluded':{'development':len(dev),'first':len(first),'second':len(second),'third':len(third),'total':len(prior)},
        'excluded_prior_module_ids':len(excluded_ids),'excluded_prior_query_texts':len(excluded_texts),'rejected_counts':dict(sorted(reject.items())),
        'benchmark_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'primary_metric':'mapped-skill Discovery Hit@5; query-level numerator/N plus Wilson interval; paired comparisons where applicable',
        'retrieval_blinding':'builder contains no retrieval/model code; no candidate output is consulted during selection',
        'ground_truth_note':'exactly one AF mapping materially reduces multi-intent label noise but does not make the annotation infallible; manually adjudicate all material errors',
        'statistics_note':'queries may cluster by target skill; report unique target count and paired discordance; occurrence proxy is descriptive only'
    }
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); (out/'cases.jsonl').write_text(text,encoding='utf-8'); (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
