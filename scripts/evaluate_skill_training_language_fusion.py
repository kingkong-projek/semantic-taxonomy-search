#!/usr/bin/env python3
"""Fuse the strong G1 human-training-language lane without giving it blanket authority.

Development-only ablation: the first 35-case fresh holdout has already been opened by G1.
We use it only to choose a small deterministic policy that must later face a new unopened
holdout.
"""
from __future__ import annotations

import argparse, hashlib, json
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm
from evaluate_skill_c0_training_validation import p80_skill_ids, pct
from evaluate_skill_training_language_enrichment import (
    TRAINING_SHA, fetch_training, ids_list, build_docs, rank,
)


def fuse_preserve_c0_top1(c0: list[str], g1: list[str], slots: int) -> list[str]:
    if not c0:
        return list(g1)
    out = [c0[0]]
    for sid in g1:
        if sid not in out:
            out.append(sid)
            if len(out) >= 1 + slots:
                break
    for sid in c0[1:]:
        if sid not in out:
            out.append(sid)
    return out


def fuse_exact_guard(c0: list[str], g1: list[str], exact: dict[str, set[str]], query: str) -> list[str]:
    nq = norm(query)
    if nq and any(nq in surfaces for surfaces in exact.values()):
        return list(c0)
    return list(g1)


def relevant(case: dict[str, Any]) -> set[str]:
    if isinstance(case.get('target'), dict) and case['target'].get('concept_id'):
        return {str(case['target']['concept_id'])}
    return {str(x['concept_id']) for x in (case.get('must') or []) if isinstance(x, dict) and x.get('concept_id')}


def eval_rows(cases: list[dict[str, Any]], rankings: list[list[str]], *, weighted: bool) -> dict[str, Any]:
    h1=h5=h10=0; total_weight=wh1=wh5=wh10=0
    for case, ranked in zip(cases, rankings, strict=True):
        rel = relevant(case)
        one = bool(ranked and ranked[0] in rel)
        five = any(x in rel for x in ranked[:5])
        ten = any(x in rel for x in ranked[:10])
        h1 += int(one); h5 += int(five); h10 += int(ten)
        if weighted:
            w = int((case.get('target') or {}).get('occurrence_proxy') or 0)
            total_weight += w; wh1 += w*int(one); wh5 += w*int(five); wh10 += w*int(ten)
    out = {
        'cases': len(cases), 'top1_pct': pct(h1,len(cases)),
        'discovery_hit_at_5_pct': pct(h5,len(cases)), 'hit_at_10_pct': pct(h10,len(cases)),
    }
    if weighted:
        out.update({'occurrence_proxy_weight':total_weight,'weighted_top1_pct':pct(wh1,total_weight),'weighted_discovery_hit_at_5_pct':pct(wh5,total_weight),'weighted_hit_at_10_pct':pct(wh10,total_weight)})
    return out


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--version',default='31'); ap.add_argument('--registry',default='research/coverage/source-adapters.json'); ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json'); ap.add_argument('--output',default='artifacts/skill-training-language-fusion-v31.json'); args=ap.parse_args()
    holdout=load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl'))
    canonical=load_jsonl(Path('research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl'))
    synthetic=[c for c in load_jsonl(Path('research/benchmark/v31/synthetic-description-stress/cases.jsonl')) if c.get('product')=='KV']
    if (len(holdout),len(canonical),len(synthetic)) != (35,617,12): raise RuntimeError('benchmark count drift')
    excluded_module_ids={mid for c in holdout for mid in ids_list(c.get('module_ids'))}; excluded_texts={norm(c['query']) for c in holdout}
    training_body=fetch_training(); tsha=hashlib.sha256(training_body).hexdigest()
    if tsha!=TRAINING_SHA: raise RuntimeError('training source drift')
    tj=json.loads(training_body); modules=(tj.get('data') or tj.get('moduler') or tj.get('modules')) if isinstance(tj,dict) else tj
    if not isinstance(modules,list): raise RuntimeError('unexpected training root')
    registry=json.loads(Path(args.registry).read_text()); pareto=json.loads(Path(args.pareto).read_text()); version=str(args.version)
    body=fetch(f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json'); sha=hashlib.sha256(body).hexdigest()
    if sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(body).get('data',{}).get('concepts'); by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    ids=p80_skill_ids(pareto); docs,exact,coverage=build_docs(by_id,ids,modules,excluded_module_ids,excluded_texts)
    c0=BM25(docs['KV-C0'],exact); g1d=BM25(docs['KV-G1-single-desc'],exact); g1n=BM25(docs['KV-G1-single-name-desc'],exact)

    suites={'fresh_holdout':(holdout,True),'canonical_source_truth':(canonical,False),'synthetic_stress':(synthetic,False)}
    configurations=['C0','G1-single-desc','G1-single-name-desc','C0-top1+G1d-1slot','C0-top1+G1d-2slot','C0-top1+G1d-3slot','C0-top1+G1d-4slot','exact-guard+G1d','exact-guard+G1name']
    results={name:{} for name in configurations}
    for suite,(cases,weighted) in suites.items():
        ranks={name:[] for name in configurations}
        for case in cases:
            q=str(case['query']); a=rank(c0,exact,q); b=rank(g1d,exact,q); n=rank(g1n,exact,q)
            ranks['C0'].append(a); ranks['G1-single-desc'].append(b); ranks['G1-single-name-desc'].append(n)
            for slots in (1,2,3,4): ranks[f'C0-top1+G1d-{slots}slot'].append(fuse_preserve_c0_top1(a,b,slots))
            ranks['exact-guard+G1d'].append(fuse_exact_guard(a,b,exact,q)); ranks['exact-guard+G1name'].append(fuse_exact_guard(a,n,exact,q))
        for name in configurations: results[name][suite]=eval_rows(cases,ranks[name],weighted=weighted)

    decision_order=sorted(configurations,key=lambda name:(-results[name]['fresh_holdout']['discovery_hit_at_5_pct'], -results[name]['canonical_source_truth']['top1_pct'], -results[name]['synthetic_stress']['discovery_hit_at_5_pct'], name))
    result={'schema_version':1,'experiment_role':'development ablation; first fresh holdout already opened by G1 before this fusion choice','taxonomy_version':31,'taxonomy_sha256':sha,'training_sha256':tsha,'coverage':coverage,'fusion_semantics':{'C0-top1+G1d-Nslot':'preserve C0 rank 1, then admit up to N unique G1-single-desc candidates before filling from C0','exact-guard+G1':'if query exactly matches any canonical preferred/alternative surface keep C0; otherwise use G1 lane'},'results':results,'development_order':decision_order,'next_gate':'freeze a second unopened source-attested natural-description holdout before promoting any fusion','identity_boundary':'only AF v31 skill IDs emitted; training text is retrieval evidence only'}
    Path(args.output).parent.mkdir(parents=True,exist_ok=True); Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'development_order':decision_order,'results':results},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
