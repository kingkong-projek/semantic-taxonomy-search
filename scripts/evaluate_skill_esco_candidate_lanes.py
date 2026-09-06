#!/usr/bin/env python3
"""Measure ESCO mapping types as separate candidate-generation lanes for P80 skill discovery.

No ESCO text is appended to KV-C0 documents. Each mapping type gets its own BM25 index
containing only canonical text of the mapped `esco-skill` nodes, keyed back to the AF v31
skill identity. The experiment asks one narrow question: can an ESCO lane recover frozen
KV-C0 misses in its own top 5?

No fusion is implemented here. Mapping types remain separate and ESCO identity is never
emitted as a product destination.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import build_c0, p80_skill_ids, pct, positive_rank

MAPPINGS = ("exact_match", "close_match", "broad_match", "narrow_match")


def relation_ids(c: dict[str, Any], field: str, by_id: dict[str, dict[str, Any]]) -> list[str]:
    value=c.get(field)
    if not isinstance(value,list): return []
    out=[]
    for item in value:
        rid=str(item.get('id') if isinstance(item,dict) else item or '')
        if rid and by_id.get(rid,{}).get('type')=='esco-skill': out.append(rid)
    return sorted(set(out))


def canonical_text(c: dict[str, Any]) -> str:
    label=str(c.get('preferred_label') or '').strip(); definition=str(c.get('definition') or '').strip()
    real_definition=definition if definition and norm(definition)!=norm(label) else ''
    alternatives=[x for x in as_list(c.get('alternative_labels')) if norm(x)!=norm(label)]
    return ' '.join(x for x in [label,real_definition,*alternatives] if x)


def positive_bm25_rank(ranker: BM25, query: str) -> list[str]:
    q=tokens(query); scored=[]
    for sid in ranker.documents:
        score=ranker.score(q,sid)
        if score>0.0: scored.append((score,sid))
    scored.sort(key=lambda x:(-x[0],x[1])); return [sid for _,sid in scored]


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--version',default='31')
    ap.add_argument('--registry',default='research/coverage/source-adapters.json')
    ap.add_argument('--pareto',default='research/coverage/v31/pareto-demand-aggregate.json')
    ap.add_argument('--benchmark',default='research/benchmark/v31/training-skill-validation/cases.jsonl')
    ap.add_argument('--output',default='artifacts/skill-esco-candidate-lanes-v31.json')
    args=ap.parse_args()

    cases=load_jsonl(Path(args.benchmark)); primary=[c for c in cases if c.get('primary_descriptive_nonleaky')]
    if len(cases)!=76 or len(primary)!=63: raise RuntimeError('benchmark count drift')
    registry=json.loads(Path(args.registry).read_text(encoding='utf-8')); pareto=json.loads(Path(args.pareto).read_text(encoding='utf-8')); version=str(args.version)
    url=f'https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json'
    body=fetch(url); sha=hashlib.sha256(body).hexdigest()
    if sha!=expected_hash(registry,'taxonomy-common-relations'): raise RuntimeError('taxonomy source drift')
    concepts=json.loads(body).get('data',{}).get('concepts')
    if not isinstance(concepts,list): raise RuntimeError('taxonomy missing concepts')
    by_id={str(c['id']):c for c in concepts if isinstance(c,dict) and c.get('id')}
    skill_ids=p80_skill_ids(pareto); c0_ranker,c0_exact=build_c0(by_id,skill_ids)

    lane_docs: dict[str,dict[str,list[str]]]={m:{} for m in MAPPINGS}; coverage={}
    mapping_ids: dict[str,dict[str,list[str]]]={m:{} for m in MAPPINGS}
    for m in MAPPINGS:
        edge_count=0
        for sid in skill_ids:
            tids=relation_ids(by_id[sid],m,by_id); mapping_ids[m][sid]=tids; edge_count+=len(tids)
            text=' '.join(canonical_text(by_id[tid]) for tid in tids if canonical_text(by_id[tid]))
            if text: lane_docs[m][sid]=tokens(text)
        coverage[m]={'p80_skills_with_text':len(lane_docs[m]),'edges':edge_count}

    lane_rankers={m:BM25(docs,{sid:set() for sid in docs}) for m,docs in lane_docs.items()}
    c0_rows=[]
    for case in primary:
        target=str(case['target']['concept_id']); weight=int(case['target']['occurrence_proxy']); ranked=positive_rank(c0_ranker,c0_exact,str(case['query']))
        c0_rows.append({'id':case['id'],'target_id':target,'weight':weight,'c0_hit5':target in ranked[:5]})
    c0_by_id={r['id']:r for r in c0_rows}; misses=[r for r in c0_rows if not r['c0_hit5']]
    if len(misses)!=34: raise RuntimeError(f'expected 34 C0 misses, got {len(misses)}')

    results={}; details={}
    for m,ranker in lane_rankers.items():
        s=defaultdict(float); rows=[]
        for case in primary:
            target=str(case['target']['concept_id']); weight=int(case['target']['occurrence_proxy']); ranked=positive_bm25_rank(ranker,str(case['query'])); lane_hit=target in ranked[:5]; c0_hit=c0_by_id[case['id']]['c0_hit5']; rescue=(not c0_hit) and lane_hit; oracle=c0_hit or lane_hit
            s['cases']+=1; s['weight']+=weight; s['lane_hit']+=int(lane_hit); s['lane_weight']+=weight*int(lane_hit); s['oracle']+=int(oracle); s['oracle_weight']+=weight*int(oracle)
            if not c0_hit:
                s['misses']+=1; s['miss_weight']+=weight; s['rescued']+=int(rescue); s['rescued_weight']+=weight*int(rescue)
            rows.append({'id':case['id'],'target_id':target,'target_has_mapping':bool(mapping_ids[m][target]),'mapped_esco_count':len(mapping_ids[m][target]),'c0_hit5':c0_hit,'lane_hit5':lane_hit,'rescues_c0_miss':rescue,'lane_top5_ids':ranked[:5]})
        results[m]={
            'cases':int(s['cases']),'lane_hit_at_5_pct':pct(s['lane_hit'],s['cases']),'weighted_lane_hit_at_5_pct':pct(s['lane_weight'],s['weight']),
            'c0_misses':int(s['misses']),'c0_misses_rescued_at_5':int(s['rescued']),'c0_miss_rescue_pct':pct(s['rescued'],s['misses']),'weighted_c0_miss_rescue_pct':pct(s['rescued_weight'],s['miss_weight']),
            'c0_or_lane_oracle_hit_at_5_pct':pct(s['oracle'],s['cases']),'weighted_c0_or_lane_oracle_hit_at_5_pct':pct(s['oracle_weight'],s['weight']),
        }
        details[m]=rows

    result={
        'schema_version':1,'taxonomy_version':int(version),'taxonomy_sha256':sha,
        'role':'candidate-lane diagnostic only; no fusion and no document expansion',
        'identity_boundary':'lane documents contain ESCO text but are keyed/emitted only as AF v31 P80 skill identities',
        'mapping_semantics_guard':'exact/close/broad/narrow evaluated separately; no mapping-type union',
        'runtime_implication':'all lane data is derivable from the pinned snapshot and can be compiled into a static frontend data package',
        'c0_primary':{'cases':63,'hit_at_5_cases':29,'discovery_hit_at_5_pct':46.032,'c0_misses':34},
        'coverage':coverage,'lanes':results,'cases_detail':details,
    }
    p=Path(args.output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'coverage':coverage,'lanes':results},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
