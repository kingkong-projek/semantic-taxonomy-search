#!/usr/bin/env python3
"""Measure D/E skill context as separate candidate-generation lanes.

D lanes use only the pinned taxonomy graph:
- broader `skill-headline` canonical text;
- related `ssyk-level-4` canonical text.

E lanes invert the pinned Kompetensväljaren context records separately for:
- essential + regulated skills;
- optional skills;
- calculated skills.

Context canonical text is retrieval evidence only. No lane is fused with KV-C0 here and
no context identity may become a selectable skill identity.
"""
from __future__ import annotations

import argparse, hashlib, json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import build_c0, p80_skill_ids, pct, positive_rank

LANES=(
    'graph_skill_headline',
    'graph_ssyk4',
    'kv_essential_regulated_context',
    'kv_optional_context',
    'kv_calculated_context',
)


def rel_ids(c:dict[str,Any], field:str, target_type:str, by_id:dict[str,dict[str,Any]])->list[str]:
    v=c.get(field)
    if not isinstance(v,list): return []
    out=[]
    for x in v:
        rid=str(x.get('id') if isinstance(x,dict) else x or '')
        if rid and by_id.get(rid,{}).get('type')==target_type: out.append(rid)
    return sorted(set(out))


def canonical_text(c:dict[str,Any])->str:
    label=str(c.get('preferred_label') or '').strip(); definition=str(c.get('definition') or '').strip()
    real=definition if definition and norm(definition)!=norm(label) else ''
    alts=[x for x in as_list(c.get('alternative_labels')) if norm(x)!=norm(label)]
    return ' '.join(x for x in [label,real,*alts] if x)


def layer_skill_ids(record:dict[str,Any], field:str)->set[str]:
    v=record.get(field) or {}
    if not isinstance(v,dict): raise RuntimeError(f'{field} is not an object')
    return {str(x) for x in v.values() if x}


def positive_lane_rank(ranker:BM25, query:str)->list[str]:
    q=tokens(query); scored=[]
    for sid in ranker.documents:
        score=ranker.score(q,sid)
        if score>0: scored.append((score,sid))
    scored.sort(key=lambda x:(-x[0],x[1])); return [sid for _,sid in scored]


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--version',default='31')
    ap.add_argument('--registry',default='research/coverage/source-adapters.json')
    ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json')
    ap.add_argument('--selector-aggregate',default='research/coverage/v31/selector-aggregate.json')
    ap.add_argument('--benchmark',default='research/benchmark/v31/training-skill-validation/cases.jsonl')
    ap.add_argument('--output',default='artifacts/skill-native-selector-candidate-lanes-v31.json')
    args=ap.parse_args()

    cases=load_jsonl(Path(args.benchmark)); primary=[c for c in cases if c.get('primary_descriptive_nonleaky')]
    if len(cases)!=76 or len(primary)!=63: raise RuntimeError('benchmark count drift')
    registry=json.loads(Path(args.registry).read_text(encoding='utf-8')); pareto=json.loads(Path(args.pareto).read_text(encoding='utf-8')); selector=json.loads(Path(args.selector_aggregate).read_text(encoding='utf-8')); version=str(args.version)

    tax_url=f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json'
    tax_body=fetch(tax_url); tax_sha=hashlib.sha256(tax_body).hexdigest()
    if tax_sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(tax_body).get('data',{}).get('concepts')
    if not isinstance(concepts,list): raise RuntimeError('taxonomy missing concepts')
    by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    skill_ids=p80_skill_ids(pareto); skill_set=set(skill_ids); c0_ranker,c0_exact=build_c0(by_id,skill_ids)

    kv_meta=selector['kompetensvaljaren']; kv_url=str(kv_meta['source']); kv_body=fetch(kv_url); kv_sha=hashlib.sha256(kv_body).hexdigest()
    if kv_sha!=str(kv_meta['source_sha256']): raise RuntimeError('KV selector source drift')
    kv_data=json.loads(kv_body).get('data')
    if not isinstance(kv_data,dict): raise RuntimeError('KV selector missing data')

    context_by_skill={lane:defaultdict(set) for lane in LANES}
    for sid in skill_ids:
        c=by_id[sid]
        context_by_skill['graph_skill_headline'][sid].update(rel_ids(c,'broader','skill-headline',by_id))
        context_by_skill['graph_ssyk4'][sid].update(rel_ids(c,'related','ssyk-level-4',by_id))

    for context_id,record in kv_data.items():
        if not isinstance(record,dict): continue
        ctype=record.get('type')
        if ctype not in ('occupation-name','ssyk-level-4'): continue
        cid=str(context_id)
        if by_id.get(cid,{}).get('type')!=ctype: raise RuntimeError(f'bad KV context {cid}/{ctype}')
        essential=layer_skill_ids(record,'essential_skills') | layer_skill_ids(record,'regulated_skills')
        optional=layer_skill_ids(record,'optional_skills'); calculated=layer_skill_ids(record,'calculated_skills')
        for sid in essential & skill_set: context_by_skill['kv_essential_regulated_context'][sid].add(cid)
        for sid in optional & skill_set: context_by_skill['kv_optional_context'][sid].add(cid)
        for sid in calculated & skill_set: context_by_skill['kv_calculated_context'][sid].add(cid)

    lane_docs={}; coverage={}
    for lane in LANES:
        docs={}; edges=0; type_counts=defaultdict(int)
        for sid in skill_ids:
            ids=sorted(context_by_skill[lane].get(sid,set())); edges+=len(ids)
            text=[]
            for cid in ids:
                c=by_id[cid]; type_counts[str(c.get('type'))]+=1; ct=canonical_text(c)
                if ct: text.append(ct)
            if text: docs[sid]=tokens(' '.join(text))
        lane_docs[lane]=docs
        coverage[lane]={'p80_skills_with_text':len(docs),'context_edges':edges,'context_edge_types':dict(sorted(type_counts.items()))}

    rankers={lane:BM25(docs,{sid:set() for sid in docs}) for lane,docs in lane_docs.items()}
    c0={}
    for case in primary:
        target=str(case['target']['concept_id']); weight=int(case['target']['occurrence_proxy']); ranked=positive_rank(c0_ranker,c0_exact,str(case['query']))
        c0[case['id']]={'target':target,'weight':weight,'hit5':target in ranked[:5]}
    if sum(not x['hit5'] for x in c0.values())!=34: raise RuntimeError('C0 miss drift')

    results={}; details={}
    for lane,ranker in rankers.items():
        s=defaultdict(float); rows=[]
        for case in primary:
            base=c0[case['id']]; target=base['target']; weight=base['weight']; ranked=positive_lane_rank(ranker,str(case['query'])); hit=target in ranked[:5]; rescue=(not base['hit5']) and hit; oracle=base['hit5'] or hit
            s['cases']+=1; s['weight']+=weight; s['hit']+=int(hit); s['whit']+=weight*int(hit); s['oracle']+=int(oracle); s['woracle']+=weight*int(oracle)
            if not base['hit5']:
                s['miss']+=1; s['missw']+=weight; s['rescue']+=int(rescue); s['wrescue']+=weight*int(rescue)
            rows.append({'id':case['id'],'target_id':target,'target_context_count':len(context_by_skill[lane].get(target,set())),'c0_hit5':base['hit5'],'lane_hit5':hit,'rescues_c0_miss':rescue,'lane_top5_ids':ranked[:5]})
        results[lane]={
            'cases':int(s['cases']),'lane_hit_at_5_pct':pct(s['hit'],s['cases']),'weighted_lane_hit_at_5_pct':pct(s['whit'],s['weight']),
            'c0_misses':int(s['miss']),'c0_misses_rescued_at_5':int(s['rescue']),'c0_miss_rescue_pct':pct(s['rescue'],s['miss']),'weighted_c0_miss_rescue_pct':pct(s['wrescue'],s['missw']),
            'c0_or_lane_oracle_hit_at_5_pct':pct(s['oracle'],s['cases']),'weighted_c0_or_lane_oracle_hit_at_5_pct':pct(s['woracle'],s['weight']),
        }; details[lane]=rows

    result={
        'schema_version':1,'taxonomy_version':int(version),'taxonomy_sha256':tax_sha,'kv_selector_sha256':kv_sha,
        'role':'D/E candidate-lane diagnostic only; no fusion and no C0 document expansion',
        'identity_boundary':'context text generates AF v31 skill candidates only; occupation, SSYK and skill-headline context identities are never emitted as skill identities',
        'provenance_boundary':'graph lanes and KV essential/regulated/optional/calculated selector layers remain separate',
        'runtime_implication':'all tested evidence is pinned and build-time compilable into static frontend data',
        'c0_primary':{'cases':63,'hit_at_5_cases':29,'discovery_hit_at_5_pct':46.032,'c0_misses':34},
        'coverage':coverage,'lanes':results,'cases_detail':details,
    }
    p=Path(args.output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'coverage':coverage,'lanes':results},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
