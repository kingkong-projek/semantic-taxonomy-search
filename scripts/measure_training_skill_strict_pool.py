#!/usr/bin/env python3
"""Measure the full strict single-skill AF training-language pool without retrieval.

A strict row has exactly one mapped skill total, target in P80, no direct canonical-label
leakage and non-terse description text. Reports full pool, overlap with already-used natural
benchmarks, and remaining unused pool. No query text is emitted.
"""
from __future__ import annotations

import hashlib, json, re, urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

URL='https://data.arbetsformedlingen.se/utbildningar/mappings/mapping_labour-market-training.json'
PINNED_SHA='fea97867a1225e078d28ab9b0772f6a37f92b37c3c6c0d0e886ae65e9d79361c'
UA='semantic-taxonomy-search-strict-pool/0.1'


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
    pareto=json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text()); sec=pareto['skill']; n=int(sec['thresholds']['p80']['concept_count']); ranked=sec['ranked_p95'][:n]
    if n!=316: raise RuntimeError('P80 drift')
    p80={str(r['concept_id']):str(r['label']) for r in ranked}
    prior_paths=[
        'research/benchmark/v31/training-skill-validation/cases.jsonl',
        'research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl',
        'research/benchmark/v31/training-skill-second-holdout/cases.jsonl',
        'research/benchmark/v31/training-skill-third-holdout/cases.jsonl',
    ]
    prior=[c for p in prior_paths for c in load_jsonl(Path(p))]
    prior_ids={mid for c in prior for mid in ids_list(c.get('module_ids'))}; prior_texts={norm(c['query']) for c in prior}

    body=fetch(); sha=hashlib.sha256(body).hexdigest()
    if sha!=PINNED_SHA: raise RuntimeError(f'source drift {sha}')
    obj=json.loads(body); modules=(obj.get('data') or obj.get('moduler') or obj.get('modules')) if isinstance(obj,dict) else obj
    if not isinstance(modules,list): raise RuntimeError('unexpected root')

    eligible=[]; reject=Counter()
    for idx,m in enumerate(modules):
        if not isinstance(m,dict): continue
        desc=str(m.get('modulbeskrivning') or '').strip(); ndesc=norm(desc); mids=ids_list(m.get('modul_id'))
        if not ndesc: reject['empty']+=1; continue
        mapped=[]
        for x in m.get('kompetenser_kopplade_till_modulen') or []:
            if isinstance(x,dict) and x.get('koncept_id'): mapped.append(str(x['koncept_id']))
        unique=sorted(set(mapped))
        if len(unique)!=1: reject['not_exactly_one_total_mapped_skill']+=1; continue
        cid=unique[0]
        if cid not in p80: reject['single_skill_outside_p80']+=1; continue
        if norm(p80[cid]) and norm(p80[cid]) in ndesc: reject['direct_label_leakage']+=1; continue
        if terse(desc): reject['terse']+=1; continue
        used=bool(set(mids)&prior_ids or ndesc in prior_texts)
        eligible.append({'cid':cid,'used':used,'normalized_text':ndesc,'module_ids':mids})

    # Collapse exact normalized-description duplicates so repeated module IDs don't inflate sample size.
    dedup={}
    for r in eligible:
        key=(r['cid'],r['normalized_text'])
        if key not in dedup: dedup[key]=r
        else:
            dedup[key]['used']=dedup[key]['used'] or r['used']
            dedup[key]['module_ids']=sorted(set(dedup[key]['module_ids'])|set(r['module_ids']))
    rows=list(dedup.values())
    by_skill=Counter(r['cid'] for r in rows); used=[r for r in rows if r['used']]; unused=[r for r in rows if not r['used']]
    used_skills=set(r['cid'] for r in used); unused_skills=set(r['cid'] for r in unused)
    result={
        'schema_version':1,'taxonomy_version':31,'source_url':URL,'source_sha256':sha,'p80_skills':316,
        'strict_definition':'exactly one mapped skill total; target in P80; no direct canonical-label leakage; non-terse; normalized description deduplicated within target',
        'full_pool':{'rows':len(rows),'unique_skills':len(by_skill),'rows_per_skill':dict(sorted(Counter(by_skill.values()).items())),'max_rows_for_one_skill':max(by_skill.values()) if by_skill else 0},
        'already_used_by_prior_benchmarks':{'rows':len(used),'unique_skills':len(used_skills)},
        'unused_after_prior_benchmarks':{'rows':len(unused),'unique_skills':len(unused_skills)},
        'prior_benchmark_cases':len(prior),'prior_module_ids':len(prior_ids),'prior_normalized_texts':len(prior_texts),
        'rejected_counts':dict(sorted(reject.items())),
        'interpretation':'If full strict pool is materially larger than unused pool, grouped/leave-query-out sensitivity can reuse prior source rows only as development evidence; new confirmatory validation requires another source or human adjudication.'
    }
    out=Path('artifacts/training-skill-strict-pool-v31.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
