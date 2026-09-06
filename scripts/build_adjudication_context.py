#!/usr/bin/env python3
"""Build read-only taxonomy context for pending Pareto adjudication rows.

This helper never labels rows. It surfaces exact/substring occupation labels,
alternative labels and job-title->occupation relations so a reviewer can make a
version-bound judgment without relying on the current ranker's suggestions.
"""
from __future__ import annotations

import argparse, hashlib, json, re, urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

UA='semantic-taxonomy-search-adjudication-context/0.1'

def norm(x: Any) -> str:
    return re.sub(r'\s+',' ',str(x or '')).strip().casefold()

def fetch(url: str) -> bytes:
    req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':UA})
    with urllib.request.urlopen(req,timeout=240) as r: return r.read()

def expected_hash(registry: dict[str,Any], adapter_id: str) -> str:
    xs=[a for a in registry['adapters'] if a.get('id')==adapter_id]
    if len(xs)!=1: raise RuntimeError(adapter_id)
    return str(xs[0]['source_sha256'])

def labels(v: Any) -> list[str]:
    if not isinstance(v,list): return []
    out=[]
    for x in v:
        if isinstance(x,str): out.append(x)
        elif isinstance(x,dict):
            y=x.get('label') or x.get('value') or x.get('preferred_label')
            if isinstance(y,str): out.append(y)
    return out

def relation_ids(c: dict[str,Any]) -> list[str]:
    out=[]
    for field in ('related','broader','narrower'):
        v=c.get(field)
        if not isinstance(v,list): continue
        for x in v:
            rid=x.get('id') if isinstance(x,dict) else x
            if rid: out.append(str(rid))
    return out

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--batch',required=True)
    ap.add_argument('--registry',default='research/coverage/source-adapters.json')
    ap.add_argument('--output',default='artifacts/adjudication-context-v31.json')
    args=ap.parse_args()
    batch=[json.loads(x) for x in Path(args.batch).read_text(encoding='utf-8').splitlines() if x.strip()]
    registry=json.loads(Path(args.registry).read_text(encoding='utf-8'))
    url='https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json'
    body=fetch(url); actual=hashlib.sha256(body).hexdigest(); expected=expected_hash(registry,'taxonomy-common-relations')
    if actual!=expected: raise RuntimeError(f'taxonomy drift {actual} != {expected}')
    doc=json.loads(body); concepts=doc.get('data',{}).get('concepts')
    if not isinstance(concepts,list): raise RuntimeError('no concepts')
    by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    occ=[c for c in concepts if isinstance(c,dict) and c.get('type')=='occupation-name']
    jobs=[c for c in concepts if isinstance(c,dict) and c.get('type')=='job-title']
    job_parents=defaultdict(set)
    for j in jobs:
        for rid in relation_ids(j):
            if by_id.get(rid,{}).get('type')=='occupation-name': job_parents[str(j['id'])].add(rid)

    rows=[]
    for r in batch:
        if r['source_pool']!='observed_unbound_query': continue
        q=norm(r['query'])
        if not q: continue
        occ_hits=[]
        for c in occ:
            pref=str(c.get('preferred_label') or '')
            alts=labels(c.get('alternative_labels'))
            surfaces=[pref,*alts]
            exact=[s for s in surfaces if norm(s)==q]
            contains=[s for s in surfaces if q in norm(s) or (norm(s) and norm(s) in q)]
            if exact or contains:
                occ_hits.append({'concept_id':str(c['id']),'preferred_label':pref,'exact_surfaces':exact,'contains_surfaces':contains[:10]})
        job_hits=[]
        for j in jobs:
            pref=str(j.get('preferred_label') or '')
            nq=norm(pref)
            if nq==q or q in nq or (nq and nq in q):
                parents=[{'concept_id':pid,'label':str(by_id[pid].get('preferred_label') or '')} for pid in sorted(job_parents[str(j['id'])])]
                job_hits.append({'job_title_id':str(j['id']),'preferred_label':pref,'exact':nq==q,'parent_occupations':parents})
        occ_hits.sort(key=lambda x:(not bool(x['exact_surfaces']), len(x['preferred_label']), x['preferred_label']))
        job_hits.sort(key=lambda x:(not x['exact'],len(x['preferred_label']),x['preferred_label']))
        rows.append({'source_id':r['source_id'],'query':r['query'],'observed_count':r['observed_count'],'occupation_surface_hits':occ_hits[:100],'job_title_surface_hits':job_hits[:100]})
    out={'schema_version':1,'taxonomy_version':31,'taxonomy_sha256':actual,'rows':rows,'authority_boundary':'context only; no relevance labels inferred'}
    p=Path(args.output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'rows':len(rows),'taxonomy_sha256':actual},indent=2))
    return 0
if __name__=='__main__': raise SystemExit(main())
