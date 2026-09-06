#!/usr/bin/env python3
"""Measure AF labour-market-training manual mappings as a skill-discovery validation source.

This is source audit / benchmark construction only. The training text is never added to
retrieval documents by this script.
"""
from __future__ import annotations

import argparse, hashlib, json, re, urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

URL='https://data.arbetsformedlingen.se/utbildningar/mappings/mapping_labour-market-training.json'
UA='semantic-taxonomy-search-training-skill-audit/0.1'

def fetch(url: str) -> bytes:
    req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':UA})
    with urllib.request.urlopen(req,timeout=240) as r: return r.read()

def norm(x: Any) -> str: return re.sub(r'\s+',' ',str(x or '')).strip().casefold()

def p80_skill_ids(pareto: dict[str,Any]) -> list[str]:
    s=pareto['skill']; n=int(s['thresholds']['p80']['concept_count']); ids=[str(r['concept_id']) for r in s['ranked_p95'][:n]]
    if n!=316 or len(ids)!=316 or len(set(ids))!=316: raise RuntimeError('P80 skill membership drift')
    return ids

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json'); ap.add_argument('--output-dir',default='artifacts/training-skill-validation-v31'); args=ap.parse_args()
    pareto=json.loads(Path(args.pareto).read_text(encoding='utf-8')); p80=p80_skill_ids(pareto); p80set=set(p80); rank={cid:i+1 for i,cid in enumerate(p80)}
    body=fetch(URL); sha=hashlib.sha256(body).hexdigest(); data=json.loads(body)
    if isinstance(data,dict):
        modules=data.get('data') or data.get('moduler') or data.get('modules')
    else: modules=data
    if not isinstance(modules,list): raise RuntimeError(f'unexpected training mapping root: {type(data)}')
    all_skill_ids=set(); p80_covered=set(); candidate=[]; mapped_modules=0; nonempty_desc=0; p80_modules=0; p80_target_counts=Counter(); mapped_target_counts=Counter(); lexical_leak=0
    for idx,m in enumerate(modules):
        if not isinstance(m,dict): continue
        mapped=m.get('kompetenser_kopplade_till_modulen') or []
        if not isinstance(mapped,list): mapped=[]
        skills=[]
        for x in mapped:
            if isinstance(x,dict) and x.get('koncept_id'):
                cid=str(x['koncept_id']); label=str(x.get('kompetensnamn') or '')
                skills.append((cid,label)); all_skill_ids.add(cid)
        if skills: mapped_modules+=1
        desc=norm(m.get('modulbeskrivning'))
        if desc: nonempty_desc+=1
        pskills=[(cid,label) for cid,label in skills if cid in p80set]
        if not pskills or not desc: continue
        p80_modules+=1; p80_covered.update(cid for cid,_ in pskills); p80_target_counts[len(pskills)]+=1; mapped_target_counts[len(skills)]+=1
        leaked=[cid for cid,label in pskills if label and norm(label) in desc]
        lexical_leak+=int(bool(leaked))
        candidate.append({
            'source_index':idx,'module_name':str(m.get('modulnamn') or ''),'module_ids':m.get('modul_id') or [],'query_text':str(m.get('modulbeskrivning') or '').strip(),
            'mapped_skill_count':len(skills),'p80_mapped_skill_count':len(pskills),
            'p80_skills':[{'concept_id':cid,'label':label,'p80_rank':rank[cid]} for cid,label in sorted(pskills,key=lambda z:rank[z[0]])],
            'all_mapped_skill_ids':[cid for cid,_ in skills], 'direct_p80_label_in_description':bool(leaked),
        })
    candidate.sort(key=lambda r:(min(x['p80_rank'] for x in r['p80_skills']), r['p80_mapped_skill_count'], norm(r['module_name']), r['source_index']))
    clean=[r for r in candidate if 1<=r['p80_mapped_skill_count']<=5]
    report={
        'schema_version':1,'taxonomy_version':31,'source':{'url':URL,'sha256':sha,'license':'CC0','semantics':'manual mapping from learning outcomes identified in module descriptions to AF skill concepts; mapping establishes relatedness, not match strength'},
        'modules_total':len(modules),'modules_with_any_skill_mapping':mapped_modules,'modules_with_nonempty_description':nonempty_desc,
        'unique_mapped_skill_ids':len(all_skill_ids),'p80_skill_universe':316,'p80_skills_covered':len(p80_covered),'p80_skill_coverage_pct':round(100*len(p80_covered)/316,3),
        'modules_with_nonempty_description_and_p80_mapping':p80_modules,'clean_candidate_modules_1_to_5_p80_targets':len(clean),
        'modules_with_direct_p80_label_in_description':lexical_leak,'direct_label_leakage_pct':round(100*lexical_leak/p80_modules,3) if p80_modules else 0,
        'p80_target_count_distribution':{str(k):v for k,v in sorted(p80_target_counts.items())},'all_mapped_target_count_distribution_with_p80':{str(k):v for k,v in sorted(mapped_target_counts.items())},
        'authority_boundary':'module text + manual mappings may be benchmark truth; do not ingest module text into retrieval before baseline evaluation',
    }
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    with (out/'candidates.jsonl').open('w',encoding='utf-8') as f:
        for r in clean: f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
