#!/usr/bin/env python3
"""Validate staged human-description study exports without running retrieval."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

EMAIL_RE=re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',re.I)
PHONE_RE=re.compile(r'(?<!\w)(?:\+46|0)[\s\-]?(?:\d[\s\-]?){7,10}(?!\w)')
ELICIT_FORBIDDEN={
    'acceptable_canonical_ids','adjudication_status','lexical_top5_ids','fallback_top5_ids',
    'participant_recognized_ids','participant_selected_id','retrieval_output','retrieval_rank'
}
ADJ_FORBIDDEN={
    'lexical_top5_ids','fallback_top5_ids','participant_recognized_ids','participant_selected_id',
    'retrieval_output','retrieval_rank'
}
STATUSES={'mapped','ambiguous','clarification-needed','unmappable','out-of-scope'}
STREAMS={'occupation','skill'}


def load_jsonl(path:Path)->list[dict[str,Any]]:
    rows=[]
    for i,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip(): continue
        try: obj=json.loads(line)
        except Exception as e: raise RuntimeError(f'{path}:{i}: invalid JSON: {e}') from e
        if not isinstance(obj,dict): raise RuntimeError(f'{path}:{i}: record must be object')
        rows.append(obj)
    return rows


def sha(path:Path)->str: return hashlib.sha256(path.read_bytes()).hexdigest()

def required(row:dict[str,Any],keys:set[str],where:str)->None:
    missing=sorted(k for k in keys if k not in row)
    if missing: raise RuntimeError(f'{where}: missing {missing}')

def nonempty_string(v:Any)->bool: return isinstance(v,str) and bool(v.strip())

def ensure_unique(rows:list[dict[str,Any]],where:str)->dict[str,dict[str,Any]]:
    out={}
    for i,row in enumerate(rows,1):
        cid=row.get('case_id')
        if not nonempty_string(cid): raise RuntimeError(f'{where}:{i}: invalid case_id')
        if cid in out: raise RuntimeError(f'{where}:{i}: duplicate case_id {cid}')
        out[cid]=row
    return out


def validate_elicitation(rows:list[dict[str,Any]])->dict[str,dict[str,Any]]:
    idx=ensure_unique(rows,'elicitation')
    participants=set()
    for cid,row in idx.items():
        required(row,{'case_id','stream','participant_id','description_redacted','language'},f'elicitation:{cid}')
        if row['stream'] not in STREAMS: raise RuntimeError(f'elicitation:{cid}: bad stream')
        if not nonempty_string(row['participant_id']): raise RuntimeError(f'elicitation:{cid}: bad participant_id')
        if not nonempty_string(row['description_redacted']): raise RuntimeError(f'elicitation:{cid}: empty description')
        if not nonempty_string(row['language']): raise RuntimeError(f'elicitation:{cid}: bad language')
        leaked=sorted(ELICIT_FORBIDDEN & set(row))
        if leaked: raise RuntimeError(f'elicitation:{cid}: post-elicitation fields leaked {leaked}')
        text=str(row['description_redacted'])
        if EMAIL_RE.search(text): raise RuntimeError(f'elicitation:{cid}: obvious email address in repository-bound text')
        if PHONE_RE.search(text): raise RuntimeError(f'elicitation:{cid}: possible phone number in repository-bound text')
        participants.add(row['participant_id'])
    return idx


def validate_adjudication(rows:list[dict[str,Any]],elic:dict[str,dict[str,Any]])->dict[str,dict[str,Any]]:
    idx=ensure_unique(rows,'adjudication')
    if set(idx)!=set(elic):
        raise RuntimeError(f'adjudication case set differs from elicitation: missing={sorted(set(elic)-set(idx))} extra={sorted(set(idx)-set(elic))}')
    for cid,row in idx.items():
        required(row,{'case_id','status','acceptable_canonical_ids','in_frozen_demand_envelope','adjudicator_ids','retrieval_blind'},f'adjudication:{cid}')
        if row['status'] not in STATUSES: raise RuntimeError(f'adjudication:{cid}: bad status')
        ids=row['acceptable_canonical_ids']
        if not isinstance(ids,list) or any(not nonempty_string(x) for x in ids) or len(ids)!=len(set(ids)):
            raise RuntimeError(f'adjudication:{cid}: acceptable_canonical_ids must be unique string list')
        if row['status']=='mapped' and len(ids)<1: raise RuntimeError(f'adjudication:{cid}: mapped needs target')
        if row['status']=='ambiguous' and len(ids)<2: raise RuntimeError(f'adjudication:{cid}: ambiguous needs >=2 targets')
        if row['status'] in {'clarification-needed','unmappable','out-of-scope'} and ids:
            raise RuntimeError(f'adjudication:{cid}: {row["status"]} must not invent target ids')
        env=row['in_frozen_demand_envelope']
        if env not in (True,False,None): raise RuntimeError(f'adjudication:{cid}: invalid envelope flag')
        if not ids and env is not None: raise RuntimeError(f'adjudication:{cid}: envelope must be null without target')
        aids=row['adjudicator_ids']
        if not isinstance(aids,list) or not aids or any(not nonempty_string(x) for x in aids):
            raise RuntimeError(f'adjudication:{cid}: invalid adjudicator_ids')
        if row['retrieval_blind'] is not True: raise RuntimeError(f'adjudication:{cid}: retrieval_blind must be true')
        leaked=sorted(ADJ_FORBIDDEN & set(row))
        if leaked: raise RuntimeError(f'adjudication:{cid}: outcome fields leaked {leaked}')
    return idx


def validate_manifest(path:Path,elic_path:Path,adj_path:Path,elic_n:int,adj_n:int)->dict[str,Any]:
    obj=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj,dict): raise RuntimeError('manifest must be object')
    required(obj,{'schema_version','study_id','elicitation_sha256','adjudication_sha256','elicitation_cases','adjudication_cases','frozen_before_retrieval'},'manifest')
    if obj['elicitation_sha256']!=sha(elic_path): raise RuntimeError('manifest elicitation hash mismatch')
    if obj['adjudication_sha256']!=sha(adj_path): raise RuntimeError('manifest adjudication hash mismatch')
    if int(obj['elicitation_cases'])!=elic_n or int(obj['adjudication_cases'])!=adj_n: raise RuntimeError('manifest case count mismatch')
    if obj['frozen_before_retrieval'] is not True: raise RuntimeError('manifest must assert frozen_before_retrieval=true')
    return obj


def validate_outcomes(rows:list[dict[str,Any]],elic:dict[str,dict[str,Any]],adj:dict[str,dict[str,Any]])->dict[str,dict[str,Any]]:
    idx=ensure_unique(rows,'outcomes')
    if set(idx)!=set(elic):
        raise RuntimeError(f'outcome case set differs from elicitation: missing={sorted(set(elic)-set(idx))} extra={sorted(set(idx)-set(elic))}')
    for cid,row in idx.items():
        required(row,{'case_id','lexical_top5_ids','fallback_top5_ids','participant_recognized_ids','participant_selected_id','clarification_was_offered'},f'outcomes:{cid}')
        for key in ('lexical_top5_ids','fallback_top5_ids','participant_recognized_ids'):
            ids=row[key]
            if not isinstance(ids,list) or len(ids)>5 or any(not nonempty_string(x) for x in ids) or len(ids)!=len(set(ids)):
                raise RuntimeError(f'outcomes:{cid}: {key} must be unique string list max5')
        selected=row['participant_selected_id']
        if selected is not None and not nonempty_string(selected): raise RuntimeError(f'outcomes:{cid}: invalid selected id')
        if selected is not None and selected not in row['participant_recognized_ids']:
            raise RuntimeError(f'outcomes:{cid}: selected id must be participant-recognized')
        if row['clarification_was_offered'] not in (True,False): raise RuntimeError(f'outcomes:{cid}: clarification flag must be boolean')
    return idx


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--elicitation',required=True,type=Path)
    ap.add_argument('--adjudication',required=True,type=Path)
    ap.add_argument('--manifest',required=True,type=Path)
    ap.add_argument('--outcomes',type=Path)
    args=ap.parse_args()
    elic_rows=load_jsonl(args.elicitation); elic=validate_elicitation(elic_rows)
    adj_rows=load_jsonl(args.adjudication); adj=validate_adjudication(adj_rows,elic)
    manifest=validate_manifest(args.manifest,args.elicitation,args.adjudication,len(elic_rows),len(adj_rows))
    outcomes=None
    if args.outcomes:
        outcomes=validate_outcomes(load_jsonl(args.outcomes),elic,adj)
    result={
        'study_id':manifest['study_id'],'elicitation_cases':len(elic),'adjudication_cases':len(adj),
        'participants':len({r['participant_id'] for r in elic.values()}),
        'occupation_cases':sum(r['stream']=='occupation' for r in elic.values()),
        'skill_cases':sum(r['stream']=='skill' for r in elic.values()),
        'mapped_or_ambiguous':sum(r['status'] in {'mapped','ambiguous'} for r in adj.values()),
        'clarification_needed':sum(r['status']=='clarification-needed' for r in adj.values()),
        'outcomes_present':outcomes is not None,
        'frozen_before_retrieval':True
    }
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
