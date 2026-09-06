#!/usr/bin/env python3
"""Post-hoc development probe for model-authored build-time KV enrichment.

The teacher phrases were authored after the KV-100 miss review. Therefore this experiment
can answer only whether the teacher/student mechanism has enough signal to pursue. It is
not confirmatory evidence and must not replace the previously validated G1 candidate
without a fresh frozen holdout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluate_model_authored_kv_100 import metric
from evaluate_p80_lexical_ablation import BM25, load_jsonl, norm, tokens
from evaluate_skill_training_language_enrichment import build_docs, fetch_training, TRAINING_SHA, fetch, expected_hash
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1
from evaluate_skill_c0_training_validation import p80_skill_ids
import hashlib


def evaluate(cases: list[dict[str, Any]], rows: list[list[str]]) -> dict[str, Any]:
    h1 = h5 = h10 = 0
    detail = []
    for case, ranked in zip(cases, rows, strict=True):
        tid = str(case['target']['concept_id'])
        try:
            pos = ranked.index(tid) + 1
        except ValueError:
            pos = None
        h1 += int(pos == 1)
        h5 += int(pos is not None and pos <= 5)
        h10 += int(pos is not None and pos <= 10)
        detail.append({'id':case['id'],'target':case['target'],'rank':pos,'top5':ranked[:5]})
    return {'top1':metric(h1,len(cases)),'hit_at_5':metric(h5,len(cases)),'hit_at_10':metric(h10,len(cases)),'details':detail}


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--version',default='31')
    ap.add_argument('--registry',default='research/coverage/source-adapters.json')
    ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json')
    ap.add_argument('--cases',default='research/benchmark/v31/model-authored-kv-100/cases.jsonl')
    ap.add_argument('--teacher',default='research/enrichment/v31/model-teacher-kv-top100/phrases.jsonl')
    ap.add_argument('--output',default='artifacts/model-teacher-kv-top100-v31.json')
    args=ap.parse_args()

    cases=load_jsonl(Path(args.cases)); teacher=load_jsonl(Path(args.teacher))
    if len(cases)!=100 or len(teacher)!=100: raise RuntimeError(f'count drift {len(cases)}/{len(teacher)}')
    query_norms={norm(str(c['query'])) for c in cases}
    if len(query_norms)!=100: raise RuntimeError('duplicate eval query')
    teacher_ids=[str(x['concept_id']) for x in teacher]
    case_ids=[str(x['target']['concept_id']) for x in cases]
    if teacher_ids != case_ids: raise RuntimeError('teacher target order/identity drift')
    for row in teacher:
        phrases=row.get('phrases') or []
        if len(phrases)!=3: raise RuntimeError(f"teacher phrase count for {row.get('concept_id')}")
        for phrase in phrases:
            if norm(str(phrase)) in query_norms: raise RuntimeError('exact eval-query leakage into teacher phrase')

    pareto=json.loads(Path(args.pareto).read_text()); registry=json.loads(Path(args.registry).read_text()); version=str(args.version)
    t_body=fetch(f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json')
    tsha=hashlib.sha256(t_body).hexdigest()
    if tsha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(t_body).get('data',{}).get('concepts') or []
    by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    tr_body=fetch_training(); trsha=hashlib.sha256(tr_body).hexdigest()
    if trsha!=TRAINING_SHA: raise RuntimeError('training source drift')
    tr=json.loads(tr_body); modules=(tr.get('data') or tr.get('moduler') or tr.get('modules')) if isinstance(tr,dict) else tr
    ids=p80_skill_ids(pareto)
    docs,exact,coverage=build_docs(by_id,ids,modules,set(),set())
    teacher_by_id={str(x['concept_id']):[str(p) for p in x['phrases']] for x in teacher}
    tdocs={sid:[*docs['KV-G1-single-desc'][sid], *tokens(' '.join(teacher_by_id.get(sid,[])))] for sid in ids}
    c0=BM25(docs['KV-C0'],exact); g1=BM25(docs['KV-G1-single-desc'],exact); t1=BM25(tdocs,exact)

    def ranked(ranker: BM25, q: str) -> list[str]:
        from evaluate_skill_training_language_enrichment import rank
        return rank(ranker,exact,q)

    rs={'C0':[],'G1':[],'T1-teacher':[],'C0-top1+G1-4slot':[],'C0-top1+T1-4slot':[]}
    for c in cases:
        q=str(c['query']); a=ranked(c0,q); b=ranked(g1,q); t=ranked(t1,q)
        rs['C0'].append(a); rs['G1'].append(b); rs['T1-teacher'].append(t)
        rs['C0-top1+G1-4slot'].append(fuse_preserve_c0_top1(a,b,4))
        rs['C0-top1+T1-4slot'].append(fuse_preserve_c0_top1(a,t,4))
    results={name:evaluate(cases,rows) for name,rows in rs.items()}
    base=results['C0-top1+G1-4slot']['details']; teach=results['C0-top1+T1-4slot']['details']
    rescues=[]; regressions=[]
    for case,b,t in zip(cases,base,teach,strict=True):
        bh=b['rank'] is not None and b['rank']<=5; th=t['rank'] is not None and t['rank']<=5
        if th and not bh: rescues.append({'id':case['id'],'target':case['target'],'query':case['query'],'baseline_rank':b['rank'],'teacher_rank':t['rank']})
        if bh and not th: regressions.append({'id':case['id'],'target':case['target'],'query':case['query'],'baseline_rank':b['rank'],'teacher_rank':t['rank']})
    result={'schema_version':1,'status':'post-hoc development probe after KV-100 miss review; not independent validation','evidence_class':'synthetic_model_teacher_posthoc_development','teacher_rows':len(teacher),'teacher_phrases':sum(len(x['phrases']) for x in teacher),'coverage':coverage,'results':results,'hit5_rescues_vs_g1_fusion':rescues,'hit5_regressions_vs_g1_fusion':regressions,'next_gate':'If signal is material and regression bounded, freeze mechanism before authoring/evaluating a fresh disjoint target/query set. Do not promote from this score alone.'}
    Path(args.output).parent.mkdir(parents=True,exist_ok=True); Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    compact={name:{k:v for k,v in r.items() if k!='details'} for name,r in results.items()}
    print(json.dumps({'results':compact,'rescues':len(rescues),'regressions':len(regressions),'rescue_ids':[x['id'] for x in rescues],'regression_ids':[x['id'] for x in regressions]},ensure_ascii=False,indent=2,sort_keys=True))
    return 0

if __name__=='__main__': raise SystemExit(main())
