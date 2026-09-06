#!/usr/bin/env python3
"""Evaluate prefrozen model-teacher KV enrichment on disjoint P80 ranks 101-200.

The teacher phrase file was committed before the evaluation query file. This script is the
first retrieval code allowed to inspect that pair. Evidence remains synthetic/model-authored,
not observed-user or canonical semantic truth.
"""
from __future__ import annotations

import argparse, hashlib, json
from pathlib import Path
from typing import Any

from evaluate_model_authored_kv_100 import metric
from evaluate_p80_lexical_ablation import BM25, load_jsonl, norm, tokens
from evaluate_skill_training_language_enrichment import build_docs, fetch_training, TRAINING_SHA, fetch, expected_hash, rank
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1
from evaluate_skill_c0_training_validation import p80_skill_ids


def evaluate(cases: list[dict[str, Any]], rows: list[list[str]]) -> dict[str, Any]:
    h1 = h5 = h10 = 0
    detail = []
    for case, ranked in zip(cases, rows, strict=True):
        tid = str(case['target']['concept_id'])
        try:
            pos = ranked.index(tid) + 1
        except ValueError:
            pos = None
        h1 += int(pos == 1); h5 += int(pos is not None and pos <= 5); h10 += int(pos is not None and pos <= 10)
        detail.append({'id':case['id'],'target':case['target'],'rank':pos,'top5':ranked[:5]})
    return {'top1':metric(h1,len(cases)),'hit_at_5':metric(h5,len(cases)),'hit_at_10':metric(h10,len(cases)),'details':detail}


def compare(base: dict[str, Any], candidate: dict[str, Any], cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rescues=[]; regressions=[]
    for case,b,t in zip(cases,base['details'],candidate['details'],strict=True):
        bh=b['rank'] is not None and b['rank']<=5; th=t['rank'] is not None and t['rank']<=5
        row={'id':case['id'],'target':case['target'],'query':case['query'],'baseline_rank':b['rank'],'teacher_rank':t['rank']}
        if th and not bh: rescues.append(row)
        if bh and not th: regressions.append(row)
    return rescues,regressions


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--version',default='31')
    ap.add_argument('--registry',default='research/coverage/source-adapters.json')
    ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json')
    ap.add_argument('--cases',default='research/benchmark/v31/model-authored-kv-ranks101-200/cases.jsonl')
    ap.add_argument('--teacher',default='research/enrichment/v31/model-teacher-kv-ranks101-200/phrases.jsonl')
    ap.add_argument('--prior-cases',default='research/benchmark/v31/model-authored-kv-100/cases.jsonl')
    ap.add_argument('--canonical',default='research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl')
    ap.add_argument('--output',default='artifacts/model-teacher-kv-ranks101-200-v31.json')
    args=ap.parse_args()

    cases=load_jsonl(Path(args.cases)); teacher=load_jsonl(Path(args.teacher)); prior=load_jsonl(Path(args.prior_cases)); canonical=load_jsonl(Path(args.canonical))
    if (len(cases),len(teacher),len(prior),len(canonical))!=(100,100,100,617): raise RuntimeError('benchmark count drift')

    case_ranks=[int(c['target']['p80_rank']) for c in cases]; teacher_ranks=[int(t['rank']) for t in teacher]
    if case_ranks!=list(range(101,201)) or teacher_ranks!=list(range(101,201)): raise RuntimeError('rank slice drift')
    case_ids=[str(c['target']['concept_id']) for c in cases]; teacher_ids=[str(t['concept_id']) for t in teacher]; prior_ids={str(c['target']['concept_id']) for c in prior}
    if case_ids!=teacher_ids: raise RuntimeError('teacher/query target order drift')
    if set(case_ids)&prior_ids: raise RuntimeError('target overlap with prior top100')

    new_queries=[norm(c['query']) for c in cases]; old_queries=[norm(c['query']) for c in prior]
    if len(set(new_queries))!=100: raise RuntimeError('duplicate new query')
    if set(new_queries)&set(old_queries): raise RuntimeError('query overlap with prior top100')
    all_query_norms=set(new_queries)|set(old_queries); phrase_norms=[]
    for row in teacher:
        phrases=row.get('phrases') or []
        if len(phrases)!=3: raise RuntimeError(f"teacher phrase count {row.get('concept_id')}")
        phrase_norms.extend(norm(p) for p in phrases)
    if len(set(phrase_norms))!=300: raise RuntimeError('duplicate teacher phrase')
    if set(phrase_norms)&all_query_norms: raise RuntimeError('exact query leakage into teacher phrase')

    pareto=json.loads(Path(args.pareto).read_text()); expected_slice=pareto['skill']['ranked_p95'][100:200]
    expected_ids=[str(r['concept_id']) for r in expected_slice]
    if expected_ids!=case_ids: raise RuntimeError('P80 rank identity drift')

    registry=json.loads(Path(args.registry).read_text()); version=str(args.version)
    t_body=fetch(f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json'); tsha=hashlib.sha256(t_body).hexdigest()
    if tsha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(t_body).get('data',{}).get('concepts') or []; by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    tr_body=fetch_training(); trsha=hashlib.sha256(tr_body).hexdigest()
    if trsha!=TRAINING_SHA: raise RuntimeError('training source drift')
    tr=json.loads(tr_body); modules=(tr.get('data') or tr.get('moduler') or tr.get('modules')) if isinstance(tr,dict) else tr
    ids=p80_skill_ids(pareto); docs,exact,coverage=build_docs(by_id,ids,modules,set(),set())
    teacher_by_id={str(x['concept_id']):[str(p) for p in x['phrases']] for x in teacher}
    tdocs={sid:[*docs['KV-G1-single-desc'][sid],*tokens(' '.join(teacher_by_id.get(sid,[])))] for sid in ids}
    c0=BM25(docs['KV-C0'],exact); g1=BM25(docs['KV-G1-single-desc'],exact); t1=BM25(tdocs,exact)

    def run(suite: list[dict[str,Any]]) -> dict[str,dict[str,Any]]:
        rs={name:[] for name in ('C0','G1','T2-teacher','C0-top1+G1-4slot','C0-top1+T2-4slot')}
        for c in suite:
            q=str(c['query']); a=rank(c0,exact,q); b=rank(g1,exact,q); t=rank(t1,exact,q)
            rs['C0'].append(a); rs['G1'].append(b); rs['T2-teacher'].append(t)
            rs['C0-top1+G1-4slot'].append(fuse_preserve_c0_top1(a,b,4)); rs['C0-top1+T2-4slot'].append(fuse_preserve_c0_top1(a,t,4))
        return {name:evaluate(suite,rows) for name,rows in rs.items()}

    new_results=run(cases); prior_results=run(prior)
    new_rescues,new_regressions=compare(new_results['C0-top1+G1-4slot'],new_results['C0-top1+T2-4slot'],cases)
    old_rescues,old_regressions=compare(prior_results['C0-top1+G1-4slot'],prior_results['C0-top1+T2-4slot'],prior)

    canonical_top1=canonical_hit5=0
    for c in canonical:
        rel={str(x['concept_id']) for x in c['must']}; a=rank(c0,exact,str(c['query'])); t=rank(t1,exact,str(c['query'])); fused=fuse_preserve_c0_top1(a,t,4)
        canonical_top1+=int(bool(fused and fused[0] in rel)); canonical_hit5+=int(any(x in rel for x in fused[:5]))

    direct_full_label_mentions=sum(bool(norm(c['target']['label']) and norm(c['target']['label']) in norm(c['query'])) for c in cases)
    result={
      'schema_version':1,
      'status':'prefrozen synthetic teacher/query validation; teacher committed before query authoring and no retrieval inspected either side before freeze',
      'evidence_class':'synthetic_model_teacher_prefrozen_validation',
      'teacher_freeze_commit':'7e256c137223e60bede01b921e1ed8b7987e6c19',
      'query_freeze_commit':'1e2a811d2830acb2f29ba05bce28806a46ec099b',
      'disjointness':{'new_cases':100,'prior_cases':100,'target_overlap':0,'exact_query_overlap':0,'exact_teacher_query_overlap':0,'teacher_phrases':300,'direct_full_label_mentions':direct_full_label_mentions},
      'coverage':coverage,
      'new_ranks101_200':new_results,
      'prior_top100_regression_suite':prior_results,
      'new_hit5_rescues_vs_g1_fusion':new_rescues,
      'new_hit5_regressions_vs_g1_fusion':new_regressions,
      'prior_hit5_rescues_vs_g1_fusion':old_rescues,
      'prior_hit5_regressions_vs_g1_fusion':old_regressions,
      'canonical_regression':{'cases':len(canonical),'top1':metric(canonical_top1,len(canonical)),'hit_at_5':metric(canonical_hit5,len(canonical))},
      'interpretation_boundary':'This can test generalization across a temporally prefrozen synthetic target/query split and cross-target regression. It is not independent human/user evidence and cannot by itself promote model-authored phrases to production truth.'
    }
    Path(args.output).parent.mkdir(parents=True,exist_ok=True); Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    def compact(x): return {k:v for k,v in x.items() if k!='details'}
    print(json.dumps({
      'disjointness':result['disjointness'],
      'new':{k:compact(v) for k,v in new_results.items()},
      'prior':{k:compact(v) for k,v in prior_results.items()},
      'new_rescues':len(new_rescues),'new_regressions':len(new_regressions),
      'prior_rescues':len(old_rescues),'prior_regressions':len(old_regressions),
      'canonical':result['canonical_regression']
    },ensure_ascii=False,indent=2,sort_keys=True))
    return 0


if __name__=='__main__': raise SystemExit(main())
