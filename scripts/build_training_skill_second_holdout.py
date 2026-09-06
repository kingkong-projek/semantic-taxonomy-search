#!/usr/bin/env python3
"""Build a second source-attested KV natural-description holdout with zero retrieval code.

Selection is frozen from the pinned AF labour-market-training mapping. Every module id and
normalized description used by either the original development benchmark or first fresh
holdout is excluded. We then choose at most one clean, non-leaky, non-terse module per
remaining unique P80 skill where the module has exactly one P80 target.
"""
from __future__ import annotations

import argparse, hashlib, json, re, urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

URL='https://data.arbetsformedlingen.se/utbildningar/mappings/mapping_labour-market-training.json'
PINNED_SHA='fea97867a1225e078d28ab9b0772f6a37f92b37c3c6c0d0e886ae65e9d79361c'
UA='semantic-taxonomy-search-second-skill-holdout/0.1'

def fetch() -> bytes:
    req=urllib.request.Request(URL,headers={'Accept':'application/json','User-Agent':UA})
    with urllib.request.urlopen(req,timeout=240) as r: return r.read()

def norm(x: Any) -> str: return re.sub(r'\s+',' ',str(x or '')).strip().casefold()
def ids_list(v: Any) -> list[str]:
    if isinstance(v,list): return [str(x) for x in v]
    return [] if v in (None,'') else [str(v)]
def terse(desc: str) -> bool:
    n=norm(desc); return n.startswith('för innehåll, se') or n.startswith('undervisning i') or len(n)<60

def load_jsonl(path: Path) -> list[dict[str,Any]]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json'); ap.add_argument('--development',default='research/benchmark/v31/training-skill-validation/cases.jsonl'); ap.add_argument('--first-holdout',default='research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'); ap.add_argument('--output-dir',default='artifacts/training-skill-second-holdout-v31'); args=ap.parse_args()
    development=load_jsonl(Path(args.development)); first=load_jsonl(Path(args.first_holdout))
    if len(development)!=76 or len(first)!=35: raise RuntimeError('prior benchmark count drift')
    excluded_ids={mid for c in development+first for mid in ids_list(c.get('module_ids'))}
    excluded_texts={norm(c['query']) for c in development+first}
    pareto=json.loads(Path(args.pareto).read_text(encoding='utf-8')); sec=pareto['skill']; n=int(sec['thresholds']['p80']['concept_count']); ranked=sec['ranked_p95'][:n]
    if n!=316: raise RuntimeError('P80 count drift')
    p80={str(r['concept_id']):{'rank':i+1,'occurrences':int(r['occurrences']),'label':str(r['label'])} for i,r in enumerate(ranked)}
    body=fetch(); sha=hashlib.sha256(body).hexdigest()
    if sha!=PINNED_SHA: raise RuntimeError(f'source drift {sha}')
    obj=json.loads(body); modules=(obj.get('data') or obj.get('moduler') or obj.get('modules')) if isinstance(obj,dict) else obj
    if not isinstance(modules,list): raise RuntimeError('unexpected source root')
    grouped: dict[str,list[dict[str,Any]]]=defaultdict(list); reject=defaultdict(int)
    for idx,m in enumerate(modules):
        if not isinstance(m,dict): continue
        desc=str(m.get('modulbeskrivning') or '').strip(); ndesc=norm(desc); mids=ids_list(m.get('modul_id'))
        if not ndesc: reject['empty']+=1; continue
        if any(mid in excluded_ids for mid in mids) or ndesc in excluded_texts: reject['prior_use']+=1; continue
        mapped=[]
        for x in m.get('kompetenser_kopplade_till_modulen') or []:
            if isinstance(x,dict) and x.get('koncept_id'): mapped.append((str(x['koncept_id']),str(x.get('kompetensnamn') or '')))
        targets=[(cid,label) for cid,label in mapped if cid in p80]
        unique_targets=sorted({cid for cid,_ in targets})
        if len(unique_targets)!=1: reject['not_exactly_one_p80_target']+=1; continue
        cid=unique_targets[0]; label=p80[cid]['label']
        leak=bool(norm(label) and norm(label) in ndesc)
        if leak: reject['direct_label_leakage']+=1; continue
        if terse(desc): reject['terse']+=1; continue
        grouped[cid].append({'source_index':idx,'module_name':str(m.get('modulnamn') or ''),'module_ids':mids,'query':desc,'all_mapped_skill_ids':sorted({x[0] for x in mapped})})
    def quality(r: dict[str,Any]):
        d=r['query']; return (len(d)>1800,abs(min(len(d),1800)-450),norm(r['module_name']),r['source_index'])
    chosen=[]
    for cid,rows in grouped.items():
        row=min(rows,key=quality); meta=p80[cid]
        chosen.append({**row,'target':{'concept_id':cid,'label':meta['label'],'p80_rank':meta['rank'],'occurrence_proxy':meta['occurrences']}})
    chosen.sort(key=lambda r:(r['target']['p80_rank'],norm(r['module_name']),r['source_index']))
    if len(chosen)<20: raise RuntimeError(f'too few second-holdout cases: {len(chosen)}')
    cases=[]
    for i,r in enumerate(chosen,1):
        cases.append({'id':f'kv.training-skill-second-holdout.{i:03d}','query':r['query'],'target':r['target'],'module_name':r['module_name'],'module_ids':r['module_ids'],'all_mapped_skill_ids':r['all_mapped_skill_ids'],'primary_descriptive_nonleaky':True,'direct_label_leakage':False,'terse_text':False,'source_evidence':{'source':URL,'sha256':PINNED_SHA,'provenance':'manual_curated_mapping','semantics':'AF manually mapped learning outcomes in this module to skill concepts; exactly one mapped target lies in the frozen P80 skill envelope'},'authority_boundary':'frozen second holdout truth; this query text and its module IDs must be excluded from retrieval evidence before evaluation'})
    text=''.join(json.dumps(c,ensure_ascii=False,sort_keys=True)+'\n' for c in cases)
    manifest={'schema_version':1,'taxonomy_version':31,'source_url':URL,'source_sha256':PINNED_SHA,'selection':'one deterministic clean unused module per unique P80 skill after excluding every module id/text from the 76-case development benchmark and first 35-case holdout; exactly one P80 target; no direct label leakage; non-terse','cases':len(cases),'unique_p80_skills':len(cases),'prior_development_cases_excluded':len(development),'prior_first_holdout_cases_excluded':len(first),'excluded_prior_module_ids':len(excluded_ids),'excluded_prior_query_texts':len(excluded_texts),'rejected_counts':dict(sorted(reject.items())),'benchmark_sha256':hashlib.sha256(text.encode()).hexdigest(),'primary_metric':'mapped-skill Discovery Hit@5; occurrence proxy only secondary','retrieval_blinding':'builder contains no retrieval/model code; no candidate output is consulted during selection'}
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); (out/'cases.jsonl').write_text(text,encoding='utf-8'); (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
