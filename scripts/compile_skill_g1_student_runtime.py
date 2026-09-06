#!/usr/bin/env python3
"""Compile validated KV C0 + G1 4-slot fusion into static postings-only assets.

Evaluation-shape assets exclude both frozen natural-description holdouts from G1 retrieval
language. A separate production-shape size estimate includes all eligible source-attested
training language but is not used for relevance evaluation.
"""
from __future__ import annotations

import collections, gzip, hashlib, json, math
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids
from evaluate_skill_training_language_enrichment import TRAINING_SHA, fetch_training, ids_list, build_docs, rank
from evaluate_skill_training_language_fusion import fuse_preserve_c0_top1


def compile_docs(ids: list[str], docs: dict[str,list[str]], exact: dict[str,set[str]], name: str) -> dict[str,Any]:
    k1=1.2; b=0.75; lengths={cid:len(docs[cid]) for cid in ids}; avgdl=sum(lengths.values())/len(ids); tfs={cid:collections.Counter(docs[cid]) for cid in ids}; df=collections.Counter()
    for cid in ids: df.update(set(docs[cid]))
    n=len(ids); idf={term:math.log(1+(n-f+0.5)/(f+0.5)) for term,f in df.items()}; ordinal={cid:i for i,cid in enumerate(ids)}; postings={}
    for term in sorted(df):
        rows=[]
        for cid in ids:
            f=tfs[cid].get(term,0)
            if not f: continue
            dl=lengths[cid]; denom=f+k1*(1-b+b*dl/max(avgdl,1e-9)); rows.append([ordinal[cid],idf[term]*(f*(k1+1)/denom)])
        postings[term]=rows
    surfaces=collections.defaultdict(list)
    for cid in ids:
        for s in exact[cid]:
            if s: surfaces[s].append(ordinal[cid])
    return {'schema_version':1,'engine':'precomputed-bm25-postings','lane':name,'document_ids':ids,'postings':postings,'exact_surfaces':{s:sorted(v) for s,v in sorted(surfaces.items())},'runtime':'unique-token lookup + add precomputed contribution + exact boost + sort','runtime_dependencies':[]}

def compact(obj: Any) -> bytes: return (json.dumps(obj,ensure_ascii=False,separators=(',',':'),sort_keys=True)+'\n').encode()
def rank_compiled(asset: dict[str,Any], query: str) -> tuple[list[str],dict[str,int]]:
    ids=asset['document_ids']; scores=collections.defaultdict(float); uniq=sorted(set(tokens(query))); visited=matched=0
    for term in uniq:
        rows=asset['postings'].get(term)
        if not rows: continue
        matched+=1
        for ordinal,score in rows: scores[int(ordinal)]+=float(score); visited+=1
    nq=norm(query); ex=asset['exact_surfaces'].get(nq,[]) if nq else []
    for ordinal in ex: scores[int(ordinal)]+=1_000_000
    ranked=sorted(((score,ids[o]) for o,score in scores.items() if score>0),key=lambda r:(-r[0],r[1]))
    return [cid for _,cid in ranked],{'query_tokens_unique':len(uniq),'matched_terms':matched,'postings_visited':visited,'candidate_docs_scored':len(scores),'exact_surface_docs':len(ex)}

def main() -> int:
    registry=json.loads(Path('research/coverage/source-adapters.json').read_text()); pareto=json.loads(Path('research/coverage/v31/pareto-demand-aggregate.json').read_text()); first=load_jsonl(Path('research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl')); second=load_jsonl(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl')); canonical=load_jsonl(Path('research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl')); synthetic=[c for c in load_jsonl(Path('research/benchmark/v31/synthetic-description-stress/cases.jsonl')) if c.get('product')=='KV']
    if (len(first),len(second),len(canonical),len(synthetic))!=(35,20,617,12): raise RuntimeError('benchmark count drift')
    expected_holdout='3960fd217deb9d7346fd78d4f281a62b614ce927e18e4ed12cbebec08a898aa7'
    if hashlib.sha256(Path('research/benchmark/v31/training-skill-second-holdout/cases.jsonl').read_bytes()).hexdigest()!=expected_holdout: raise RuntimeError('holdout drift')
    tbytes=fetch_training(); tsha=hashlib.sha256(tbytes).hexdigest()
    if tsha!=TRAINING_SHA: raise RuntimeError('training drift')
    tobj=json.loads(tbytes); modules=(tobj.get('data') or tobj.get('moduler') or tobj.get('modules')) if isinstance(tobj,dict) else tobj
    tbody=fetch('https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json'); taxsha=hashlib.sha256(tbody).hexdigest()
    if taxsha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy drift')
    concepts=json.loads(tbody).get('data',{}).get('concepts'); by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}; ids=p80_skill_ids(pareto)
    held=first+second; exids={mid for c in held for mid in ids_list(c.get('module_ids'))}; extexts={norm(c['query']) for c in held}
    docs,exact,coverage=build_docs(by_id,ids,modules,exids,extexts); full_docs,full_exact,full_coverage=build_docs(by_id,ids,modules,set(),set())
    assets={'c0':compile_docs(ids,docs['KV-C0'],exact,'KV-C0'),'g1':compile_docs(ids,docs['KV-G1-single-desc'],exact,'KV-G1-single-desc')}; full_g1=compile_docs(ids,full_docs['KV-G1-single-desc'],full_exact,'KV-G1-single-desc-production-shape')
    out=Path('artifacts/skill-g1-student-runtime-v31'); out.mkdir(parents=True,exist_ok=True); sizes={}
    for key,a in assets.items():
        data=compact(a); (out/f'{key}.json').write_bytes(data); sizes[key]={'raw_bytes':len(data),'gzip9_bytes':len(gzip.compress(data,9,mtime=0)),'terms':len(a['postings']),'postings':sum(len(x) for x in a['postings'].values()),'sha256':hashlib.sha256(data).hexdigest()}
    full_data=compact(full_g1); sizes['g1_production_shape']={'raw_bytes':len(full_data),'gzip9_bytes':len(gzip.compress(full_data,9,mtime=0)),'terms':len(full_g1['postings']),'postings':sum(len(x) for x in full_g1['postings'].values()),'sha256':hashlib.sha256(full_data).hexdigest()}
    vectors=[]; parity=0; op_totals=collections.Counter()
    c0ref=BM25(docs['KV-C0'],exact); g1ref=BM25(docs['KV-G1-single-desc'],exact)
    for suite,cases in [('canonical',canonical),('second_holdout',second),('synthetic',synthetic)]:
        for case in cases:
            q=str(case['query']); cr,co=rank_compiled(assets['c0'],q); gr,go=rank_compiled(assets['g1'],q); ref=fuse_preserve_c0_top1(rank(c0ref,exact,q),rank(g1ref,exact,q),4); got=fuse_preserve_c0_top1(cr,gr,4)
            if got[:10]!=ref[:10]: raise RuntimeError(f'compiled fusion parity {case.get("id")}')
            parity+=1
            for prefix,ops in [('c0',co),('g1',go)]:
                for k,v in ops.items(): op_totals[f'{prefix}_{k}']+=v
            vectors.append({'suite':suite,'id':case.get('id'),'query':q,'expected_top10':got[:10],'c0_ops':co,'g1_ops':go})
    manifest={'schema_version':1,'candidate':'KV-G1-4slot','policy':'preserve C0 rank1; then take up to four unique G1-single-desc candidates; fill tail from C0','validation_shape_excludes':{'first_holdout_cases':35,'second_holdout_cases':20,'module_ids':len(exids),'texts':len(extexts)},'coverage_validation_shape':coverage,'coverage_production_shape':full_coverage,'asset_sizes':sizes,'combined_validation_gzip9_bytes':sizes['c0']['gzip9_bytes']+sizes['g1']['gzip9_bytes'],'combined_production_shape_gzip9_bytes':sizes['c0']['gzip9_bytes']+sizes['g1_production_shape']['gzip9_bytes'],'parity_cases':parity,'parity_failures':0,'mean_operations':{k:round(v/parity,3) for k,v in sorted(op_totals.items())},'runtime_dependencies':[],'ordinary_selector_semantic_bytes':0,'load_point':'only after description fallback is opened','taxonomy_sha256':taxsha,'training_sha256':tsha}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n'); (out/'runtime-vectors.json').write_text(json.dumps({'schema_version':1,'cases':vectors},ensure_ascii=False,separators=(',',':'),sort_keys=True)+'\n'); print(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
