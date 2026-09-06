#!/usr/bin/env python3
"""Measure typed ESCO text coverage only for the three validated KV-G1 residual targets.

Diagnostic only: no ranking/fusion is changed. Mapping semantics remain separate.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any
from evaluate_p80_lexical_ablation import as_list, expected_hash, fetch, load_jsonl, norm, tokens

TARGET_IDS={
 'VQxj_dHG_UCE':'Kabelinstallationer',
 'iu18_YyQ_hmh':'Städmaterial',
 'kvLG_4uo_M5p':'Produktionsplanering, tillverkning',
}
MAPPINGS=('exact_match','close_match','broad_match','narrow_match')

def relation_ids(c:dict[str,Any], field:str, by_id:dict[str,dict[str,Any]])->list[str]:
 v=c.get(field); out=[]
 if isinstance(v,list):
  for item in v:
   rid=str(item.get('id') if isinstance(item,dict) else item or '')
   if rid and by_id.get(rid,{}).get('type')=='esco-skill': out.append(rid)
 return sorted(set(out))

def text(c:dict[str,Any])->str:
 label=str(c.get('preferred_label') or '').strip(); definition=str(c.get('definition') or '').strip()
 if norm(definition)==norm(label): definition=''
 alts=[str(x) for x in as_list(c.get('alternative_labels')) if norm(x)!=norm(label)]
 return ' '.join(x for x in [label,definition,*alts] if x)

def main()->int:
 cases=load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl'))
 case_by_target={str(c['target']['concept_id']):c for c in cases}
 if set(TARGET_IDS)-set(case_by_target): raise RuntimeError('residual target drift')
 registry=json.loads(Path('research/coverage/source-adapters.json').read_text())
 url='https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json'
 body=fetch(url); sha=hashlib.sha256(body).hexdigest()
 if sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
 concepts=json.loads(body).get('data',{}).get('concepts'); by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
 rows=[]
 for sid,label in TARGET_IDS.items():
  q=str(case_by_target[sid]['query']); qt=set(tokens(q)); mappings={}
  for m in MAPPINGS:
   targets=[]
   for tid in relation_ids(by_id[sid],m,by_id):
    t=by_id[tid]; tx=text(t); tt=set(tokens(tx)); shared=sorted(qt & tt)
    targets.append({'esco_id':tid,'label':str(t.get('preferred_label') or ''),'definition':str(t.get('definition') or ''),'alternative_labels':[str(x) for x in as_list(t.get('alternative_labels'))],'shared_query_tokens':shared,'shared_unique_tokens':len(shared),'text':tx})
   mappings[m]=targets
  rows.append({'target_id':sid,'target_label':label,'query':q,'mappings':mappings})
 result={'schema_version':1,'role':'coverage diagnostic only; no ESCO ranking or fusion','taxonomy_version':31,'taxonomy_sha256':sha,'mapping_semantics_guard':'exact/close/broad/narrow remain distinct','cases':rows}
 p=Path('artifacts/skill-g1-residual-esco-v31.json'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
 summary=[]
 for r in rows:
  summary.append({'target':r['target_label'],'mapping_counts':{m:len(r['mappings'][m]) for m in MAPPINGS},'max_shared_tokens':{m:max((x['shared_unique_tokens'] for x in r['mappings'][m]),default=0) for m in MAPPINGS},'mapped_labels':{m:[x['label'] for x in r['mappings'][m]] for m in MAPPINGS}})
 print(json.dumps(summary,ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
