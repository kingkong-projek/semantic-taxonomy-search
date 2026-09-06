#!/usr/bin/env python3
"""Build a source-attested natural-language skill validation benchmark.

One module description is selected per unique P80 skill where AF's manually curated
labour-market-training mapping contains exactly one P80 target. The text is benchmark
input only and is never added to retrieval documents here.
"""
from __future__ import annotations

import argparse, hashlib, json, re, urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

URL='https://data.arbetsformedlingen.se/utbildningar/mappings/mapping_labour-market-training.json'
PINNED_SHA='fea97867a1225e078d28ab9b0772f6a37f92b37c3c6c0d0e886ae65e9d79361c'
UA='semantic-taxonomy-search-training-skill-benchmark/0.1'

def fetch() -> bytes:
    req=urllib.request.Request(URL,headers={'Accept':'application/json','User-Agent':UA})
    with urllib.request.urlopen(req,timeout=240) as r: return r.read()

def norm(x: Any) -> str: return re.sub(r'\s+',' ',str(x or '')).strip().casefold()

def terse(desc: str) -> bool:
    n=norm(desc); return n.startswith('för innehåll, se') or n.startswith('undervisning i') or len(n)<30

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json'); ap.add_argument('--output-dir',default='artifacts/training-skill-benchmark-v31'); args=ap.parse_args()
    pareto=json.loads(Path(args.pareto).read_text(encoding='utf-8')); skill=pareto['skill']; n=int(skill['thresholds']['p80']['concept_count']); ranked=skill['ranked_p95'][:n]
    if n!=316: raise RuntimeError('P80 skill count drift')
    p80={str(r['concept_id']):{'rank':i+1,'occurrences':int(r['occurrences']),'label':str(r['label'])} for i,r in enumerate(ranked)}
    body=fetch(); sha=hashlib.sha256(body).hexdigest()
    if sha!=PINNED_SHA: raise RuntimeError(f'training mapping source drift: {sha}')
    data=json.loads(body); modules=(data.get('data') or data.get('moduler') or data.get('modules')) if isinstance(data,dict) else data
    if not isinstance(modules,list): raise RuntimeError('unexpected mapping root')
    grouped: dict[str,list[dict[str,Any]]]=defaultdict(list)
    for idx,m in enumerate(modules):
        if not isinstance(m,dict): continue
        desc=str(m.get('modulbeskrivning') or '').strip()
        if not norm(desc): continue
        mapped=[]
        for x in (m.get('kompetenser_kopplade_till_modulen') or []):
            if isinstance(x,dict) and x.get('koncept_id'): mapped.append((str(x['koncept_id']),str(x.get('kompetensnamn') or '')))
        ptargets=[(cid,label) for cid,label in mapped if cid in p80]
        if len(ptargets)!=1: continue
        cid,label=ptargets[0]; leak=bool(label and norm(label) in norm(desc))
        grouped[cid].append({'source_index':idx,'module_name':str(m.get('modulnamn') or ''),'module_ids':m.get('modul_id') or [],'query_text':desc,'all_mapped_skill_ids':[x[0] for x in mapped],'direct_label_leakage':leak,'terse_text':terse(desc)})
    def quality(r):
        d=r['query_text']; return (r['direct_label_leakage'],r['terse_text'],len(d)<60,len(d)>2500,abs(min(len(d),2500)-350),norm(r['module_name']),r['source_index'])
    chosen=[]
    for cid,rs in grouped.items():
        row=min(rs,key=quality); meta=p80[cid]
        chosen.append({**row,'target':{'concept_id':cid,'label':meta['label'],'p80_rank':meta['rank'],'occurrence_proxy':meta['occurrences']}})
    chosen.sort(key=lambda r:r['target']['p80_rank'])
    if len(chosen)!=76: raise RuntimeError(f'unique single-P80 skill count drift: {len(chosen)}')
    cases=[]
    for i,r in enumerate(chosen,1):
        primary=not r['direct_label_leakage'] and not r['terse_text']
        cases.append({
            'id':f'kv.training-skill.{i:03d}','query':r['query_text'],'target':r['target'],'module_name':r['module_name'],'module_ids':r['module_ids'],'all_mapped_skill_ids':r['all_mapped_skill_ids'],
            'primary_descriptive_nonleaky':primary,'direct_label_leakage':r['direct_label_leakage'],'terse_text':r['terse_text'],
            'source_evidence':{'source':URL,'sha256':PINNED_SHA,'provenance':'manual_curated_mapping','semantics':'AF manually identified learning outcomes in the module description and mapped them to one or more AF skill concepts; relation is asserted, match strength is not'},
            'authority_boundary':'benchmark truth only; module text must not be added to retrieval documents before baseline evaluation',
        })
    primary=[c for c in cases if c['primary_descriptive_nonleaky']]
    if len(primary)!=63: raise RuntimeError(f'primary descriptive/nonleaky count drift: {len(primary)}')
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); text=''.join(json.dumps(c,ensure_ascii=False,sort_keys=True)+'\n' for c in cases); (out/'cases.jsonl').write_text(text,encoding='utf-8')
    manifest={'schema_version':1,'taxonomy_version':31,'source_url':URL,'source_sha256':PINNED_SHA,'selection':'one deterministic module per unique skill among modules with exactly one P80 mapped skill','cases':76,'unique_p80_skills':76,'primary_descriptive_nonleaky_cases':63,'direct_label_leak_cases':sum(c['direct_label_leakage'] for c in cases),'terse_cases':sum(c['terse_text'] for c in cases),'benchmark_sha256':hashlib.sha256(text.encode()).hexdigest(),'primary_metric':'mapped-skill Discovery Hit@5; skill occurrence proxy used only for weighted reporting','authority_boundary':'manual mapping is validation truth; training text is not retrieval evidence in baseline'}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
