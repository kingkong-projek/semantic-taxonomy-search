#!/usr/bin/env python3
"""Build label/definition context for manual adjudication of third-holdout KV errors.

Diagnostic only. Re-runs the frozen G1 + 4-gram retrieval unchanged, selects only cases where
validated G1 misses or the two lanes disagree, and exposes canonical/source labels needed to
judge whether the benchmark annotation is actually inferable from the text.
"""
from __future__ import annotations

import hashlib, json
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, ids_list, build_docs, rank
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1
from evaluate_skill_g1_subword_third_holdout import grams, rank_grams


def text_field(c:dict[str,Any], *names:str)->str|None:
    for name in names:
        v=c.get(name)
        if isinstance(v,str) and v.strip(): return v.strip()
    return None

def concept_summary(by_id:dict[str,dict[str,Any]], cid:str)->dict[str,Any]:
    c=by_id.get(cid,{})
    return {
        'concept_id':cid,
        'preferred_label':text_field(c,'preferred_label','label'),
        'definition':text_field(c,'definition'),
        'alternative_labels':c.get('alternative_labels') if isinstance(c.get('alternative_labels'),list) else [],
    }

def source_labels(modules:list[Any], module_ids:set[str])->dict[str,str]:
    out={}
    for m in modules:
        if not isinstance(m,dict): continue
        mids=set(ids_list(m.get('modul_id')))
        if not (mids & module_ids): continue
        for x in m.get('kompetenser_kopplade_till_modulen') or []:
            if isinstance(x,dict) and x.get('koncept_id'):
                out[str(x['koncept_id'])]=str(x.get('kompetensnamn') or '')
    return out

def main()->int:
    first=load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'))
    second=load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl'))
    third=load_jsonl(Path('research/benchmark/v31/training-skill-third-holdout/cases.jsonl'))
    excluded=first+second+third
    exids={mid for c in excluded for mid in ids_list(c.get('module_ids'))}; extexts={norm(c['query']) for c in excluded}

    tb=fetch_training(); tsha=hashlib.sha256(tb).hexdigest()
    if tsha!=TRAINING_SHA: raise RuntimeError('training source drift')
    tj=json.loads(tb); modules=(tj.get('data') or tj.get('moduler') or tj.get('modules')) if isinstance(tj,dict) else tj
    registry=json.loads(Path('research/coverage/source-adapters.json').read_text()); pareto=json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    body=fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json'); sha=hashlib.sha256(body).hexdigest()
    if sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(body).get('data',{}).get('concepts'); by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    ids=p80_skill_ids(pareto); docs,exact,_=build_docs(by_id,ids,modules,exids,extexts)
    c0=BM25(docs['KV-C0'],exact); g1=BM25(docs['KV-G1-single-desc'],exact); sub=BM25({sid:grams(ts) for sid,ts in docs['KV-G1-single-desc'].items()},{sid:set() for sid in docs['KV-G1-single-desc']})

    rows=[]
    for c in third:
        q=str(c['query']); target=str(c['target']['concept_id'])
        base=fuse_preserve_c0_top1(rank(c0,exact,q),rank(g1,exact,q),4); sr=rank_grams(sub,q)
        bh=target in base[:5]; sh=target in sr[:5]
        if bh and sh: continue
        if bh==sh and bh: continue
        mids=set(ids_list(c.get('module_ids'))); labels=source_labels(modules,mids)
        rows.append({
            'id':c['id'],'module_name':c.get('module_name'),'query':q,
            'target':concept_summary(by_id,target),
            'source_mapped_skills':[{'concept_id':sid,'source_label':labels.get(sid),'canonical':concept_summary(by_id,sid)} for sid in c.get('all_mapped_skill_ids',[])],
            'validated_base_hit5':bh,'subword_hit5':sh,
            'validated_base_top5':[concept_summary(by_id,x) for x in base[:5]],
            'subword_top5':[concept_summary(by_id,x) for x in sr[:5]],
            'adjudication_instruction':'Judge target inferability from query, not from module title alone. Mapping is evidence, not ground truth. Record strong / plausible-multi-intent / weak-or-uninferable and rationale.'
        })
    result={'schema_version':1,'status':'manual-adjudication input only; no metric/policy change','taxonomy_sha256':sha,'training_sha256':tsha,'review_case_count':len(rows),'cases':rows}
    out=Path('artifacts/skill-g1-third-review-context-v31.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'review_case_count':len(rows),'ids':[r['id'] for r in rows]},ensure_ascii=False,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
