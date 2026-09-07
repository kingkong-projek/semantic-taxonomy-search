#!/usr/bin/env python3
"""Opened YV description diagnostic for equal-weight reciprocal-rank fusion (RRF).

This follows the negative fixed-slot and single-document ablations. Canonical occupation
text, observed ad language and occupation-linked relevant-skill context remain independent
rankings. RRF combines only ranks, never source scores or authority. No lane weights are
tuned. k=60 is the primary standard-like configuration; k=10 is reported only as a
sensitivity check on this opened development material.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import zstandard as zstd

from evaluate_c2_job_title_router import build_c1_index, relation_parent_ids
from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, norm, tokens
from evaluate_pareto_c1 import rank_c1
from occupational_information_coverage import find_explicit_taxonomy_ids, record_map

OCC_INFO_URL = (
    "https://data.arbetsformedlingen.se/yrke/yrkesinformation/"
    "yrkesinformation-interimslosning.json"
)


def phrase_present(text: str, surface: str) -> bool:
    h=tokens(text); n=tokens(surface)
    if not n or len(n)>len(h): return False
    return any(h[i:i+len(n)]==n for i in range(len(h)-len(n)+1))


def positive_rank(ranker: BM25, query: str) -> list[str]:
    q=tokens(query)
    scored=[(cid,ranker.score(q,cid)) for cid in ranker.documents]
    scored=[x for x in scored if x[1]>0.0]
    scored.sort(key=lambda x:(-x[1],x[0]))
    return [cid for cid,_ in scored]


def rrf(lists: list[list[str]], k: int, canonical: list[str]) -> list[str]:
    score: dict[str,float]=defaultdict(float)
    for ranked in lists:
        for i,cid in enumerate(ranked,1):
            score[cid]+=1.0/(k+i)
    cpos={cid:i for i,cid in enumerate(canonical,1)}
    return sorted(score, key=lambda cid:(-score[cid], cpos.get(cid,10**9), cid))


def metrics(rows: list[dict[str,Any]], key: str) -> dict[str,Any]:
    n=len(rows)
    return {
        "cases":n,
        "top1":round(sum(r[key]["rank"]==1 for r in rows)/n,6),
        "hit_at_5":round(sum(isinstance(r[key]["rank"],int) and r[key]["rank"]<=5 for r in rows)/n,6),
        "mrr":round(sum(0.0 if r[key]["rank"] is None else 1.0/int(r[key]["rank"]) for r in rows)/n,6),
        "nonempty":round(sum(bool(r[key]["top5"]) for r in rows)/n,6),
    }


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--version",default="31")
    ap.add_argument("--registry",default="research/coverage/source-adapters.json")
    ap.add_argument("--output",default="artifacts/yv-rrf-fusion-v31.json")
    args=ap.parse_args(); version=str(args.version)
    registry=json.loads(Path(args.registry).read_text(encoding="utf-8"))

    taxonomy_url=("https://data.jobtechdev.se/taxonomy/version/"+version+"/query/concepts-and-common-relations/concepts-and-common-relations.json")
    ad_url=f"https://data.arbetsformedlingen.se/yrke/narliggande-yrken/v1/t{version}/relevans-nyckelord.json.zst"
    rel_url=f"https://data.arbetsformedlingen.se/yrke/relevanta-kompetenser/v1/relevanta-kompetenser-t{version}.json.zst"
    wires={
        "taxonomy":fetch(taxonomy_url),
        "occupational_information":fetch(OCC_INFO_URL),
        "ad_keywords":fetch(ad_url),
        "relevant_skills":fetch(rel_url),
    }
    expected={
        "taxonomy":expected_hash(registry,"taxonomy-common-relations"),
        "occupational_information":expected_hash(registry,"occupational-information"),
        "ad_keywords":expected_hash(registry,"ad-keyword-corpus"),
        "relevant_skills":expected_hash(registry,"relevant-skills"),
    }
    hashes={k:hashlib.sha256(v).hexdigest() for k,v in wires.items()}
    for k in hashes:
        if hashes[k]!=expected[k]: raise RuntimeError(f"{k} source drift: {hashes[k]}")

    taxonomy=json.loads(wires["taxonomy"])
    occ_info=json.loads(wires["occupational_information"])
    ad_doc=json.loads(zstd.ZstdDecompressor().decompress(wires["ad_keywords"]))
    rel_doc=json.loads(zstd.ZstdDecompressor().decompress(wires["relevant_skills"]))
    concepts=taxonomy.get("data",{}).get("concepts")
    if not isinstance(concepts,list): raise RuntimeError("taxonomy missing concepts")
    by_id={str(c["id"]):c for c in concepts if isinstance(c,dict) and c.get("id")}
    occ={cid for cid,c in by_id.items() if c.get("type")=="occupation-name"}
    skills={cid for cid,c in by_id.items() if c.get("type")=="skill"}
    if len(occ)!=2105 or len(skills)!=6752: raise RuntimeError("target universe drift")
    ids=sorted(occ)

    crank,cexact,csurf=build_c1_index(by_id,ids)

    ad_occ=ad_doc.get("data",{}).get("occupation_name")
    if not isinstance(ad_occ,dict) or set(ad_occ)-occ: raise RuntimeError("invalid ad data")
    ad_docs={cid:[] for cid in ids}; noexact={cid:set() for cid in ids}; terms=set()
    for cid,rec in ad_occ.items():
        kws=rec.get("keywords") if isinstance(rec,dict) else None
        if not isinstance(kws,dict): raise RuntimeError(f"invalid ad keywords {cid}")
        ts=[str(x) for x in kws]; terms.update(ts); ad_docs[cid]=tokens(" ".join(ts))
    if len(ad_occ)!=1051 or len(terms)!=11085: raise RuntimeError("ad coverage drift")
    arank=BM25(ad_docs,noexact)

    rel=rel_doc.get("data")
    if not isinstance(rel,dict) or set(rel)!=occ: raise RuntimeError("invalid relevant skills data")
    skill_docs={}; uniq=set()
    for cid in ids:
        items=rel[cid].get("relevant_skills") if isinstance(rel[cid],dict) else None
        if not isinstance(items,list): raise RuntimeError(f"invalid relevant skills {cid}")
        parts=[]; seen=set()
        for item in items:
            if not isinstance(item,dict) or not item.get("id"): continue
            sid=str(item["id"])
            if sid not in skills: raise RuntimeError(f"non-active skill {sid}")
            if sid in seen: continue
            seen.add(sid); uniq.add(sid); s=by_id[sid]
            label=str(s.get("preferred_label") or "").strip(); definition=str(s.get("definition") or "").strip()
            if label: parts.append(label)
            if definition and norm(definition)!=norm(label): parts.append(definition)
        skill_docs[cid]=tokens(" ".join(parts))
    if len(uniq)!=4685: raise RuntimeError("relevant skill coverage drift")
    srank=BM25(skill_docs,noexact)

    all_ids=set(by_id); records=record_map(occ_info.get("data")); meta=occ_info.get("metadata")
    ometa=meta.get("occupations") if isinstance(meta,dict) else None
    if not isinstance(ometa,list): raise RuntimeError("missing Yrkesinformation metadata")
    jt: dict[str,set[str]]=defaultdict(set)
    for c in by_id.values():
        if c.get("type")!="job-title": continue
        label=str(c.get("preferred_label") or "").strip()
        if not label: continue
        for parent in relation_parent_ids(c,by_id): jt[parent].add(label)

    rows=[]; excluded: dict[str,int]=defaultdict(int)
    for m in ometa:
        if not isinstance(m,dict): continue
        slug=str(m.get("slug") or ""); rec=records.get(slug)
        if not isinstance(rec,dict): excluded["missing_record"]+=1; continue
        explicit=find_explicit_taxonomy_ids(rec,all_ids)&occ
        if len(explicit)!=1: excluded["not_unique_explicit_active_occupation"]+=1; continue
        target=next(iter(explicit)); query=str(rec.get("work_task") or "").strip()
        if len(query)<40: excluded["work_task_too_short"]+=1; continue
        c=by_id[target]
        surfaces={str(c.get("preferred_label") or ""),*as_list(c.get("alternative_labels")),*jt.get(target,set())}
        if any(s and phrase_present(query,s) for s in surfaces): excluded["contains_target_or_job_title_surface"]+=1; continue

        csc=rank_c1(crank,query,cexact,csurf); cl=[cid for cid,_,_ in csc]
        al=positive_rank(arank,query); sl=positive_rank(srank,query)
        fused={
            "rrf60_ca":rrf([cl,al],60,cl),
            "rrf60_cs":rrf([cl,sl],60,cl),
            "rrf60_cas":rrf([cl,al,sl],60,cl),
            "rrf10_cas":rrf([cl,al,sl],10,cl),
        }
        row={
            "source_slug":slug,"target_id":target,"target_label":c.get("preferred_label"),"query":query,
            "canonical_rank":cl.index(target)+1 if target in cl else None,
            "ad_rank":al.index(target)+1 if target in al else None,
            "skill_rank":sl.index(target)+1 if target in sl else None,
        }
        for name,ranked in fused.items():
            row[name]={"rank":ranked.index(target)+1 if target in ranked else None,"top5":ranked[:5]}
        rows.append(row)
    if not rows: raise RuntimeError("no leak-free cases")

    result={
        "schema_version":1,"taxonomy_version":int(version),
        "status":"opened_source_attested_development_fusion_diagnostic_not_human_validation",
        "decision_question":"can fixed equal-weight rank fusion preserve independent evidence lanes without score calibration or tuned slot allocation",
        "primary_candidate":"rrf60_cas",
        "sensitivity_only":"rrf10_cas",
        "non_claims":["RRF ranks change source authority","opened cases are independent validation","k=10 is a promoted tuned parameter"],
        "source_sha256":hashes,"case_count":len(rows),
        "metrics":{name:metrics(rows,name) for name in ("rrf60_ca","rrf60_cs","rrf60_cas","rrf10_cas")},
        "excluded":dict(sorted(excluded.items())),"cases":rows,
    }
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"cases":len(rows),"metrics":result["metrics"],"output":str(out)},ensure_ascii=False,indent=2,sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
