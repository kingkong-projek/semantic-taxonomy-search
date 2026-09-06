#!/usr/bin/env python3
"""Measure when current KV occupation context falls back to global popular skills.

Mirrors the empty-query path in HybridSearchEngine.getPrioritizedList(): an
occupation context is useful only if the occupation contributes regulated,
essential, optional or calculated skills, or its SSYK4 contributes related skills.
If that combined group is empty, current KV falls back to base.mostCommonSkills.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

KV_URL = "https://data.arbetsformedlingen.se/kompetens/kompetensvaljaren/v1/kompetensvaljaren-t31.json"
KV_SHA = "da83f26bf316971caa407364d8feae6f791203bff5758e674cace3d919e4b524"
CATEGORIES = ("regulated_skills", "essential_skills", "optional_skills", "calculated_skills")


def ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, str)]
    if isinstance(value, dict):
        return [x for x in value.values() if isinstance(x, str)]
    return []


def fetch() -> tuple[bytes, dict[str, Any]]:
    req=urllib.request.Request(KV_URL,headers={"Accept":"application/json","User-Agent":"semantic-taxonomy-search-kv-context-audit/1"})
    with urllib.request.urlopen(req,timeout=180) as r:
        body=r.read()
    sha=hashlib.sha256(body).hexdigest()
    if sha != KV_SHA:
        raise RuntimeError(f"KV source drift: {sha}")
    return body,json.loads(body)


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--pareto",default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--output",default="artifacts/kv-context-fallback-audit-v31.json")
    a=ap.parse_args()
    body,doc=fetch(); raw=doc.get("data") or {}
    occurrence={}
    p=Path(a.pareto)
    if p.exists():
        pareto=json.loads(p.read_text(encoding="utf-8"))
        for row in pareto.get("occupation_name",{}).get("ranked_p95",[]):
            if row.get("concept_id"):
                occurrence[str(row["concept_id"])]=int(row.get("occurrences") or 0)

    global_ids=ids((doc.get("metadata") or {}).get("most_common_skills"))
    # label lookup from every skill-bearing map
    skill_labels={}
    for node in raw.values():
        if not isinstance(node,dict): continue
        for key in (*CATEGORIES,"related_skills"):
            value=node.get(key)
            if isinstance(value,dict):
                for label,sid in value.items():
                    if isinstance(label,str) and isinstance(sid,str): skill_labels[sid]=label
        if node.get("type") is None and not node.get("preferred_label"):
            for label,sid in node.items():
                if isinstance(label,str) and isinstance(sid,str): skill_labels[sid]=label

    rows=[]
    for oid,node in raw.items():
        if not isinstance(node,dict) or node.get("type")!="occupation-name": continue
        ssyk4=str(node.get("ssyk-level-4-id") or "")
        ssyk=raw.get(ssyk4) if ssyk4 else None
        category_ids={k:ids(node.get(k)) for k in CATEGORIES}
        related=ids(ssyk.get("related_skills")) if isinstance(ssyk,dict) else []
        combined=[]; seen=set()
        for k in CATEGORIES:
            for sid in category_ids[k]:
                if sid not in seen: seen.add(sid); combined.append(sid)
        for sid in related:
            if sid not in seen: seen.add(sid); combined.append(sid)
        rows.append({
            "occupation_id":oid,
            "label":str(node.get("preferred_label") or ""),
            "ssyk4_id":ssyk4 or None,
            "counts":{**{k:len(v) for k,v in category_ids.items()},"ssyk_related":len(related),"unique_prioritized":len(combined)},
            "would_fallback_to_global_most_common":len(combined)==0,
            "occurrence_proxy":occurrence.get(oid,0),
            "first_context_skills":[{"id":sid,"label":skill_labels.get(sid)} for sid in combined[:10]],
        })

    fallback=[r for r in rows if r["would_fallback_to_global_most_common"]]
    nonfallback=[r for r in rows if not r["would_fallback_to_global_most_common"]]
    represented=[r for r in rows if r["occurrence_proxy"]>0]
    represented_fallback=[r for r in represented if r["would_fallback_to_global_most_common"]]
    occ_total=sum(r["occurrence_proxy"] for r in represented)
    occ_fallback=sum(r["occurrence_proxy"] for r in represented_fallback)
    by_id={r["occupation_id"]:r for r in rows}
    focus_ids={
        "kock_a_la_carte":"JbJw_as4_S93",
        "kock_storhushall":"Vg3d_Azf_p5Y",
        "projektledare_offentlig":"r47H_2uB_RDF",
        "projektledare_logistik":"SauB_4Gt_FTk",
        "projektledare_bygg":"pTTz_5DC_itW",
        "projektledare_el":"1jm3_XFQ_TdJ",
        "projektledare_it":"z5AM_ayf_WcL",
        "underskoterska_hemtjanst":"bSEB_VKd_Ub3",
        "underskoterska_vard":"PQkQ_Dmk_ZF8",
    }
    result={
        "schema_version":1,
        "taxonomy_version":31,
        "source":{"url":KV_URL,"sha256":hashlib.sha256(body).hexdigest()},
        "current_kv_rule":"empty occupation/SSYK contextual group => getPrioritizedList('', limit) => global mostCommonSkills",
        "global_most_common_top10":[{"id":sid,"label":skill_labels.get(sid)} for sid in global_ids[:10]],
        "occupation_context_coverage":{
            "occupation_rows":len(rows),
            "context_specific_nonempty":len(nonfallback),
            "context_specific_nonempty_pct":round(100*len(nonfallback)/len(rows),3) if rows else 0,
            "fallback_to_global":len(fallback),
            "fallback_to_global_pct":round(100*len(fallback)/len(rows),3) if rows else 0,
            "historical_proxy_represented_occupations":len(represented),
            "historical_proxy_represented_fallback":len(represented_fallback),
            "historical_proxy_occurrence_mass":occ_total,
            "historical_proxy_fallback_mass":occ_fallback,
            "historical_proxy_fallback_mass_pct":round(100*occ_fallback/occ_total,3) if occ_total else 0,
        },
        "focus":{name:by_id.get(cid) for name,cid in focus_ids.items()},
        "highest_occurrence_fallbacks":sorted(fallback,key=lambda r:(-r["occurrence_proxy"],r["label"]))[:50],
        "rows":rows,
    }
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"coverage":result["occupation_context_coverage"],"global_top10":result["global_most_common_top10"],"focus":result["focus"],"top_fallbacks":result["highest_occurrence_fallbacks"][:20]},ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
