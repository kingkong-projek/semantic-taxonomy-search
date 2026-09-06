#!/usr/bin/env python3
"""Freeze blinded model judgments for fresh natural-query ranks 51-80.

C2 output must not be present in the input. The only retrieval context allowed here is
canonical taxonomy surface/job-title relation context prepared before C2 evaluation.
"""
from __future__ import annotations

import argparse, hashlib, json
from collections import Counter
from pathlib import Path
from typing import Any

JUDGMENTS: dict[str, dict[str, Any]] = {
    "enhetschef": {"intent":"AMBIGUOUS","acceptable":["9rvw_tBz_kFG","CnYS_d4N_CZJ","ZKKT_4bd_Sxs","Noad_FWq_mY2","zR5y_K7c_TNp"],"rationale":"The generic title 'enhetschef' denotes several canonical unit-manager occupations differentiated by domain; no single destination is justified."},
    "lärare i grundskolan": {"intent":"AMBIGUOUS","acceptable":["VZoJ_4oe_xyR","PecC_mHt_1Cj","743P_CSD_tF8","wypk_7S7_snv","rgsj_poi_koz"],"rationale":"The generic phrase 'lärare i grundskolan' spans several grade-level teacher occupations and can also reasonably cover the canonical mother-tongue teacher role; discovery should expose multiple relevant school-teacher identities."},
    "kommunikatör": {"intent":"SINGLE","must":["aRp4_qjZ_tPV"],"rationale":"The direct canonical occupation 'Informatör/Kommunikatör' is the strongest justified destination for the bare occupation term 'kommunikatör'; specialized communicator roles require extra wording."},
    "hr": {"intent":"AMBIGUOUS","acceptable":["U1NY_V1H_nSQ","1aZz_LY7_QYN","ofiS_5F2_YmV","TMQA_DYj_srP","1d3z_y59_2Hm","ds7X_mdp_bPc","s28Q_sya_S2b","23nR_PXa_9br"],"rationale":"The bare domain abbreviation 'hr' is not one occupation; it plausibly denotes several canonical HR roles, so discovery should present multiple HR occupations rather than force one."},
    "utredare": {"intent":"AMBIGUOUS","acceptable":["r66d_XpS_6bt","1Cjx_ooE_HT9","aY7W_GJ6_o62","7YaM_bPu_c1T","YkcC_EmP_nA5","Mo1Z_7W8_Mu8","YG1s_tUg_jWJ"],"rationale":"The generic title 'utredare' is shared across several canonical investigative/analyst occupations and sectors; no single occupation is justified without context."},
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--batch',required=True); ap.add_argument('--context',required=True); ap.add_argument('--output-dir',required=True)
    args=ap.parse_args(); batch=read_jsonl(Path(args.batch)); context=json.loads(Path(args.context).read_text(encoding='utf-8'))
    if len(batch)!=30 or [int(r['observed_rank_within_unbound_population']) for r in batch]!=list(range(51,81)):
        raise RuntimeError('fresh holdout must be exactly ranks 51-80')
    if any('candidate_context' in r or 'top5' in r for r in batch): raise RuntimeError('retrieval leakage in blinded batch')
    if len(context.get('rows',[]))!=30: raise RuntimeError('taxonomy context row drift')
    cm={r['source_id']:r for r in context['rows']}
    labels: dict[str,str]={}
    for c in context['rows']:
        for x in c.get('occupation_surface_hits',[]): labels[str(x['concept_id'])]=str(x['preferred_label'])
        for j in c.get('job_title_surface_hits',[]):
            for p in j.get('parent_occupations',[]): labels[str(p['concept_id'])]=str(p['label'])
    def ident(cid: str) -> dict[str,str]:
        if cid not in labels: raise RuntimeError(f'judged identity missing from pre-C2 taxonomy context: {cid}')
        return {'concept_id':cid,'kind':'occupation-name','label':labels[cid]}
    cases=[]; counts=Counter(); total=0
    for i,row in enumerate(batch,1):
        q=str(row['query']); key=q.casefold(); j=JUDGMENTS.get(key)
        if j is None:
            rationale=("The query is a work-mode/distance concept, not an occupation expression; occupation retrieval should abstain." if key=='distans' else "The query is a Swedish place/region name, not an occupation expression; occupation retrieval should abstain.")
            j={'intent':'NO_MATCH','rationale':rationale}
        intent=str(j['intent']); counts[intent]+=1; count=int(row['observed_count']); total+=count
        must=[ident(x) for x in j.get('must',[])]; acceptable=[ident(x) for x in j.get('acceptable',[])]
        if intent=='SINGLE' and not must: raise RuntimeError(q)
        if intent=='AMBIGUOUS' and not acceptable: raise RuntimeError(q)
        case={
            'acceptable':acceptable,
            'adjudication':{'agreement':'UNREVIEWED','review_note':'confidence=HIGH; fresh ranks 51-80 judgment made before any C2 output was generated','reviewer_count':0,'status':'MODEL_ADJUDICATED'},
            'allow_abstention':intent=='NO_MATCH','expected_intent':intent,'id':f'yv.fresh-holdout.{i:03d}','must':must,'must_not':[],
            'notes':f"Observed count in frozen source review pool: {count}. Unbound query rank: {row['observed_rank_within_unbound_population']}. Model-judgment confidence: HIGH.",
            'product':'YV','query':q,'query_language':'sv','query_origin':'observed_query','rationale':j['rationale'],
            'source_evidence':[
                {'note':'Observed free-text plus aggregate frequency; no selected-ID ground truth.','provenance':'behavioral','role':'query_origin','source':'Pinned Yrkesväljaren/Platsbanken observed-query corpus'},
                {'note':j['rationale'],'provenance':'model_judgment','role':'destination_ground_truth','source':'GPT-5.6 Sol fresh-holdout model adjudication 2026-09-06'},
            ],
            'strata':(['hard_negative','no_valid_match','fresh_natural_holdout'] if intent=='NO_MATCH' else ['broad_or_underspecified','fresh_natural_holdout'] if intent=='AMBIGUOUS' else ['colloquial','fresh_natural_holdout']),
            'taxonomy_version':31,'top_k':10,
        }
        if intent!='NO_MATCH':
            case['source_evidence'] += [
                {'note':'Judged identities were selected only from taxonomy-only context produced before C2 evaluation.','provenance':'canonical','role':'context_only','source':'JobTech Taxonomy v31'},
                {'note':'Occupation-name identities are admitted by the YV reference profile; YV does not define generic-engine scope.','provenance':'behavioral','role':'product_admission','source':'Published Yrkesväljaren v31'},
            ]
        cases.append(case)
    if counts != Counter({'NO_MATCH':25,'AMBIGUOUS':4,'SINGLE':1}): raise RuntimeError(f'intent count drift: {counts}')
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    text=''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in cases)
    (out/'benchmark.jsonl').write_text(text,encoding='utf-8')
    manifest={'schema_version':1,'taxonomy_version':31,'status':'MODEL_ADJUDICATED_BLINDED_TO_C2','selection':'unbound observed-query ranks 51-80 by frozen aggregate frequency','cases':30,'observed_volume':total,'intent_counts':dict(counts),'retrieval_blinding':'No C2 output was generated or inspected before these judgments were finalized.','source_context':'taxonomy-only context from JobTech Taxonomy v31','benchmark_sha256':hashlib.sha256(text.encode()).hexdigest()}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
