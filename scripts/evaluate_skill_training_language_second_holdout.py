#!/usr/bin/env python3
"""Independent validation of the predeclared G1 fusion policies on holdout #2.

Policies were selected/declaration-locked before the second holdout was evaluated:
- preserve C0 rank 1 + three G1-single-desc candidates;
- preserve C0 rank 1 + four G1-single-desc candidates.
C0 and full G1 are reported only as baseline/diagnostics.

Both first and second holdout module IDs/texts are removed from training-language retrieval
before building G1. No tuning or confidence threshold is chosen from this result.
"""
from __future__ import annotations

import argparse, hashlib, json
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm
from evaluate_skill_c0_training_validation import p80_skill_ids, pct
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, ids_list, build_docs, rank
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1

DECLARED = ('C0-top1+G1d-3slot','C0-top1+G1d-4slot')


def relevant(case: dict[str,Any]) -> set[str]:
    if isinstance(case.get('target'),dict) and case['target'].get('concept_id'): return {str(case['target']['concept_id'])}
    return {str(x['concept_id']) for x in (case.get('must') or []) if isinstance(x,dict) and x.get('concept_id')}

def evaluate(cases: list[dict[str,Any]], rankings: list[list[str]], weighted: bool=True) -> dict[str,Any]:
    h1=h5=h10=0; wtot=wh1=wh5=wh10=0; misses=[]
    for case, ranked in zip(cases,rankings,strict=True):
        rel=relevant(case); one=bool(ranked and ranked[0] in rel); five=any(x in rel for x in ranked[:5]); ten=any(x in rel for x in ranked[:10])
        h1+=int(one); h5+=int(five); h10+=int(ten)
        if weighted:
            w=int((case.get('target') or {}).get('occurrence_proxy') or 0); wtot+=w; wh1+=w*int(one); wh5+=w*int(five); wh10+=w*int(ten)
        if not five: misses.append({'id':case.get('id'),'query':case.get('query'),'expected':sorted(rel),'top5':ranked[:5]})
    out={'cases':len(cases),'top1_pct':pct(h1,len(cases)),'discovery_hit_at_5_pct':pct(h5,len(cases)),'hit_at_10_pct':pct(h10,len(cases)),'hit5_miss_count':len(misses),'hit5_misses':misses}
    if weighted: out.update({'occurrence_proxy_weight':wtot,'weighted_top1_pct':pct(wh1,wtot),'weighted_discovery_hit_at_5_pct':pct(wh5,wtot),'weighted_hit_at_10_pct':pct(wh10,wtot)})
    return out

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--version',default='31'); ap.add_argument('--registry',default='research/coverage/source-adapters.json'); ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json'); ap.add_argument('--second',default='research/benchmark/v31/training-skill-second-holdout/cases.jsonl'); ap.add_argument('--output',default='artifacts/skill-training-language-second-holdout-v31.json'); args=ap.parse_args()
    first=load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl')); second=load_jsonl(Path(args.second)); canonical=load_jsonl(Path('research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl'))
    if len(first)!=35 or len(second)!=20 or len(canonical)!=617: raise RuntimeError(f'benchmark count drift {len(first)}/{len(second)}/{len(canonical)}')
    manifest=json.loads(Path('research/benchmark/v31/training-skill-second-holdout/manifest.json').read_text())
    expected='3960fd217deb9d7346fd78d4f281a62b614ce927e18e4ed12cbebec08a898aa7'; actual=hashlib.sha256(Path(args.second).read_bytes()).hexdigest()
    if actual!=expected or manifest.get('benchmark_sha256')!=expected: raise RuntimeError('second holdout hash drift')
    excluded=first+second; excluded_ids={mid for c in excluded for mid in ids_list(c.get('module_ids'))}; excluded_texts={norm(c['query']) for c in excluded}
    tbytes=fetch_training(); tsha=hashlib.sha256(tbytes).hexdigest()
    if tsha!=TRAINING_SHA: raise RuntimeError('training source drift')
    tobj=json.loads(tbytes); modules=(tobj.get('data') or tobj.get('moduler') or tobj.get('modules')) if isinstance(tobj,dict) else tobj
    registry=json.loads(Path(args.registry).read_text()); pareto=json.loads(Path(args.pareto).read_text()); version=str(args.version)
    tbody=fetch(f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json'); sha=hashlib.sha256(tbody).hexdigest()
    if sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(tbody).get('data',{}).get('concepts'); by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    ids=p80_skill_ids(pareto); docs,exact,coverage=build_docs(by_id,ids,modules,excluded_ids,excluded_texts)
    c0=BM25(docs['KV-C0'],exact); g1=BM25(docs['KV-G1-single-desc'],exact)
    rankings={name:[] for name in ('C0','G1-single-desc',*DECLARED)}
    for case in second:
        q=str(case['query']); a=rank(c0,exact,q); b=rank(g1,exact,q); rankings['C0'].append(a); rankings['G1-single-desc'].append(b); rankings[DECLARED[0]].append(fuse_preserve_c0_top1(a,b,3)); rankings[DECLARED[1]].append(fuse_preserve_c0_top1(a,b,4))
    results={name:evaluate(second,rows,True) for name,rows in rankings.items()}
    # Safety regression is evaluated unchanged with both holdouts excluded from G1 evidence.
    canonical_results={name:None for name in rankings}
    for name in rankings:
        rs=[]
        for case in canonical:
            q=str(case['query']); a=rank(c0,exact,q); b=rank(g1,exact,q)
            if name=='C0': r=a
            elif name=='G1-single-desc': r=b
            elif name==DECLARED[0]: r=fuse_preserve_c0_top1(a,b,3)
            else: r=fuse_preserve_c0_top1(a,b,4)
            rs.append(r)
        canonical_results[name]=evaluate(canonical,rs,False)
    declared_order=sorted(DECLARED,key=lambda n:(-results[n]['discovery_hit_at_5_pct'],-results[n]['weighted_discovery_hit_at_5_pct'],-results[n]['hit_at_10_pct'],n))
    result={'schema_version':1,'status':'independent second-holdout validation','policy_freeze':'3-slot and 4-slot policies declared before second-holdout candidate outputs were generated','second_holdout_sha256':actual,'second_holdout_manifest':manifest,'training_sha256':tsha,'taxonomy_sha256':sha,'retrieval_exclusion':{'first_holdout_cases':35,'second_holdout_cases':20,'excluded_module_ids':len(excluded_ids),'excluded_normalized_texts':len(excluded_texts)},'coverage_after_exclusion':coverage,'declared_policies':list(DECLARED),'results':results,'canonical_regression':canonical_results,'declared_policy_order':declared_order,'identity_boundary':'only AF v31 skill IDs emitted; held-out training text is never retrieval evidence'}
    Path(args.output).parent.mkdir(parents=True,exist_ok=True); Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    compact={k:{kk:vv for kk,vv in v.items() if kk not in ('hit5_misses',)} for k,v in results.items()}; canon={k:{kk:vv for kk,vv in v.items() if kk not in ('hit5_misses',)} for k,v in canonical_results.items()}; print(json.dumps({'declared_policy_order':declared_order,'results':compact,'canonical':canon,'coverage_after_exclusion':coverage},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
