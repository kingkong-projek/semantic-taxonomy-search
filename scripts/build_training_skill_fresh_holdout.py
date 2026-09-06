#!/usr/bin/env python3
"""Build a fresh source-attested skill holdout from modules unused by development.

The builder has no retrieval/model dependency. It uses the same pinned AF manual mapping
source as the development benchmark, excludes every previously used module ID and exact
normalized query text, requires exactly one P80 target, and keeps only descriptive text
without direct target-label leakage. At most one unused module is selected per skill.
"""
from __future__ import annotations

import argparse, hashlib, json, re, urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

URL='https://data.arbetsformedlingen.se/utbildningar/mappings/mapping_labour-market-training.json'
PINNED_SHA='fea97867a1225e078d28ab9b0772f6a37f92b37c3c6c0d0e886ae65e9d79361c'
UA='semantic-taxonomy-search-training-skill-holdout/0.1'


def fetch()->bytes:
    req=urllib.request.Request(URL,headers={'Accept':'application/json','User-Agent':UA})
    with urllib.request.urlopen(req,timeout=240) as r: return r.read()

def norm(x:Any)->str: return re.sub(r'\s+',' ',str(x or '')).strip().casefold()

def terse(desc:str)->bool:
    n=norm(desc); return n.startswith('för innehåll, se') or n.startswith('undervisning i') or len(n)<30

def idset(value:Any)->set[str]:
    if value is None: return set()
    if isinstance(value,(list,tuple,set)): return {str(x) for x in value if x is not None and str(x)}
    return {str(value)} if str(value) else set()

def load_jsonl(path:Path)->list[dict[str,Any]]:
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json'); ap.add_argument('--development',default='research/benchmark/v31/training-skill-validation/cases.jsonl'); ap.add_argument('--output-dir',default='artifacts/training-skill-fresh-holdout-v31'); args=ap.parse_args()
    pareto=json.loads(Path(args.pareto).read_text(encoding='utf-8')); skill=pareto['skill']; n=int(skill['thresholds']['p80']['concept_count']); ranked=skill['ranked_p95'][:n]
    if n!=316: raise RuntimeError('P80 skill count drift')
    p80={str(r['concept_id']):{'rank':i+1,'occurrences':int(r['occurrences']),'label':str(r['label'])} for i,r in enumerate(ranked)}
    dev=load_jsonl(Path(args.development))
    if len(dev)!=76: raise RuntimeError(f'development count drift: {len(dev)}')
    used_queries={norm(c['query']) for c in dev}
    used_module_ids=set()
    for c in dev: used_module_ids |= idset(c.get('module_ids'))

    body=fetch(); sha=hashlib.sha256(body).hexdigest()
    if sha!=PINNED_SHA: raise RuntimeError(f'training mapping source drift: {sha}')
    data=json.loads(body); modules=(data.get('data') or data.get('moduler') or data.get('modules')) if isinstance(data,dict) else data
    if not isinstance(modules,list): raise RuntimeError('unexpected mapping root')
    grouped:dict[str,list[dict[str,Any]]]=defaultdict(list); rejected=defaultdict(int)
    for idx,m in enumerate(modules):
        if not isinstance(m,dict): continue
        desc=str(m.get('modulbeskrivning') or '').strip(); mids=idset(m.get('modul_id'))
        if not norm(desc): rejected['no_text']+=1; continue
        mapped=[]
        for x in (m.get('kompetenser_kopplade_till_modulen') or []):
            if isinstance(x,dict) and x.get('koncept_id'): mapped.append((str(x['koncept_id']),str(x.get('kompetensnamn') or '')))
        ptargets=[(cid,label) for cid,label in mapped if cid in p80]
        if len(ptargets)!=1: rejected['not_exactly_one_p80_target']+=1; continue
        cid,label=ptargets[0]
        if norm(desc) in used_queries: rejected['development_query_reuse']+=1; continue
        if mids & used_module_ids: rejected['development_module_id_overlap']+=1; continue
        leak=bool(label and norm(label) in norm(desc))
        if leak: rejected['direct_label_leakage']+=1; continue
        if terse(desc): rejected['terse_text']+=1; continue
        grouped[cid].append({'source_index':idx,'module_name':str(m.get('modulnamn') or ''),'module_ids':sorted(mids),'query_text':desc,'all_mapped_skill_ids':[x[0] for x in mapped]})

    def quality(r):
        d=r['query_text']; return (len(d)<60,len(d)>2500,abs(min(len(d),2500)-350),norm(r['module_name']),r['source_index'])
    chosen=[]
    for cid,rows in grouped.items():
        r=min(rows,key=quality); meta=p80[cid]
        chosen.append({**r,'target':{'concept_id':cid,'label':meta['label'],'p80_rank':meta['rank'],'occurrence_proxy':meta['occurrences']}})
    chosen.sort(key=lambda r:r['target']['p80_rank'])
    if len(chosen)<10: raise RuntimeError(f'fresh holdout too small: {len(chosen)}')
    if len({r['target']['concept_id'] for r in chosen})!=len(chosen): raise RuntimeError('duplicate target')
    if len({norm(r['query_text']) for r in chosen})!=len(chosen): raise RuntimeError('duplicate query')

    cases=[]
    for i,r in enumerate(chosen,1):
        cases.append({'id':f'kv.training-skill-holdout.{i:03d}','query':r['query_text'],'target':r['target'],'module_name':r['module_name'],'module_ids':r['module_ids'],'all_mapped_skill_ids':r['all_mapped_skill_ids'],'primary_descriptive_nonleaky':True,'direct_label_leakage':False,'terse_text':False,'source_evidence':{'source':URL,'sha256':PINNED_SHA,'provenance':'manual_curated_mapping','semantics':'AF manually identified learning outcomes in the module description and mapped them to one or more AF skill concepts; relation is asserted, match strength is not'},'authority_boundary':'frozen blind holdout truth; module text must never enter retrieval documents used to evaluate this holdout'})
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); text=''.join(json.dumps(c,ensure_ascii=False,sort_keys=True)+'\n' for c in cases); (out/'cases.jsonl').write_text(text,encoding='utf-8')
    manifest={'schema_version':1,'taxonomy_version':31,'source_url':URL,'source_sha256':PINNED_SHA,'selection':'one deterministic clean unused module per unique P80 skill; excludes all development module IDs and normalized query texts; exactly one P80 target; no direct label leakage; non-terse','cases':len(cases),'unique_p80_skills':len(cases),'development_cases_excluded':len(dev),'development_module_ids_excluded':len(used_module_ids),'benchmark_sha256':hashlib.sha256(text.encode()).hexdigest(),'primary_metric':'mapped-skill Discovery Hit@5; skill occurrence proxy used only for weighted reporting','authority_boundary':'manual mapping is frozen holdout truth; builder contains no retrieval/model code','rejected_counts':dict(sorted(rejected.items()))}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
