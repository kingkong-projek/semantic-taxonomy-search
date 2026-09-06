#!/usr/bin/env python3
"""Explain the single source-attested G1+T3 Hit@5 regression without changing retrieval."""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

from evaluate_kv_three_lane_fusion import fuse_quotas
from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, build_docs, fetch_training, ids_list, rank

CASE_ID='kv.training-skill-second-holdout.017'
TARGET='awjU_C3D_XEJ'


def term_contributions(r: BM25, query: str, cid: str) -> list[dict]:
    q=tokens(query); tf=r.tf[cid]; dl=r.lengths[cid]; rows=[]
    for term in sorted(set(q)):
        f=tf.get(term,0)
        if not f: continue
        idf=r.idf.get(term,0.0)
        denom=f+r.k1*(1.0-r.b+r.b*dl/max(r.avgdl,1e-9))
        val=idf*(f*(r.k1+1.0)/denom)
        rows.append({'term':term,'query_tf':q.count(term),'doc_tf':f,'idf':round(idf,6),'contribution':round(val,6)})
    rows.sort(key=lambda x:(-x['contribution'],x['term']))
    return rows


def main()->int:
    first=load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'))
    second=load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl'))
    case=next(c for c in second if c['id']==CASE_ID)
    if str(case['target']['concept_id'])!=TARGET: raise RuntimeError('target drift')
    excluded=first+second
    exids={mid for c in excluded for mid in ids_list(c.get('module_ids'))}; extexts={norm(c['query']) for c in excluded}

    registry=json.loads(Path('research/coverage/source-adapters.json').read_text()); pareto=json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text())
    tb=fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json')
    if hashlib.sha256(tb).hexdigest()!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(tb).get('data',{}).get('concepts') or []; by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    trb=fetch_training()
    if hashlib.sha256(trb).hexdigest()!=TRAINING_SHA: raise RuntimeError('training source drift')
    tr=json.loads(trb); modules=(tr.get('data') or tr.get('moduler') or tr.get('modules')) if isinstance(tr,dict) else tr
    ids=p80_skill_ids(pareto); docs,exact,coverage=build_docs(by_id,ids,modules,exids,extexts)

    teacher_rows=[]
    for p in (
      'research/enrichment/v31/model-teacher-kv-top100/phrases.jsonl',
      'research/enrichment/v31/model-teacher-kv-ranks101-200/phrases.jsonl',
      'research/enrichment/v31/model-teacher-kv-ranks201-300/phrases.jsonl'):
        teacher_rows.extend(load_jsonl(Path(p)))
    teacher_by_id={str(x['concept_id']):[str(p) for p in x['phrases']] for x in teacher_rows}
    tdocs={sid:[*docs['KV-G1-single-desc'][sid],*tokens(' '.join(teacher_by_id.get(sid,[])))] for sid in ids}
    c0=BM25(docs['KV-C0'],exact); g1=BM25(docs['KV-G1-single-desc'],exact); teacher=BM25(tdocs,exact)
    q=str(case['query']); a=rank(c0,exact,q); b=rank(g1,exact,q); t=rank(teacher,exact,q)
    baseline=fuse_quotas(a,b,t,4,0); candidate=fuse_quotas(a,b,t,1,3)
    inspect=[]
    seen=[]
    for cid in [*candidate[:5],TARGET,*baseline[:5],*t[:8],*b[:8]]:
        if cid not in seen: seen.append(cid)
    for cid in seen:
        c=by_id.get(cid,{})
        inspect.append({
          'concept_id':cid,'label':c.get('preferred_label'),'is_target':cid==TARGET,
          'positions':{
            'C0':a.index(cid)+1 if cid in a else None,
            'G1':b.index(cid)+1 if cid in b else None,
            'teacher':t.index(cid)+1 if cid in t else None,
            'baseline':baseline.index(cid)+1 if cid in baseline else None,
            'candidate':candidate.index(cid)+1 if cid in candidate else None,
          },
          'scores':{
            'C0':round(c0.score(tokens(q),cid),6),
            'G1':round(g1.score(tokens(q),cid),6),
            'teacher':round(teacher.score(tokens(q),cid),6),
          },
          'teacher_top_contributions':term_contributions(teacher,q,cid)[:12],
          'g1_top_contributions':term_contributions(g1,q,cid)[:12],
          'teacher_phrases':teacher_by_id.get(cid,[])
        })
    # Aggregate how much teacher top candidates derive from high-frequency Swedish function words.
    qterms=collections.Counter(tokens(q))
    result={
      'schema_version':1,'status':'diagnostic only; retrieval unchanged','case':case,'query_tokens':qterms,
      'rankings':{'C0_top10':a[:10],'G1_top10':b[:10],'teacher_top10':t[:10],'baseline_top10':baseline[:10],'candidate_top10':candidate[:10]},
      'inspection':inspect,'coverage':coverage
    }
    out=Path('artifacts/kv-g1-t3-ekonomistyrning-diagnostic.json'); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'case':CASE_ID,'target':case['target'],'baseline_rank':baseline.index(TARGET)+1,'candidate_rank':candidate.index(TARGET)+1,'candidate_top5':[(cid,by_id.get(cid,{}).get('preferred_label')) for cid in candidate[:5]],'teacher_top5':[(cid,by_id.get(cid,{}).get('preferred_label')) for cid in t[:5]],'inspection':inspect[:6]},ensure_ascii=False,indent=2,sort_keys=True))
    return 0

if __name__=='__main__': raise SystemExit(main())
