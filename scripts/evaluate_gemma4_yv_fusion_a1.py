#!/usr/bin/env python3
"""Opened A1 probe: preserve canonical rank 1, admit one Gemma teacher candidate."""
from __future__ import annotations

import argparse, hashlib, json
from collections import defaultdict
from pathlib import Path

from evaluate_gemma4_yv_expansion_a0 import (
    OCC_INFO_URL, TAXONOMY_URL, audit, family_rank, load_teacher, metrics, pos,
    strict_cases, teacher_rank,
)
from evaluate_c2_job_title_router import build_c1_index
from evaluate_p80_lexical_ablation import BM25, expected_hash, fetch, load_jsonl, tokens
from evaluate_pareto_c1 import rank_c1


def canonical_rank(v, query):
    ranker, exact, surface_tokens = v
    return [cid for cid, _, _ in rank_c1(ranker, query, exact, surface_tokens)]


def fuse(canonical, teacher):
    out = []
    if canonical: out.append(canonical[0])
    if teacher and teacher[0] not in out: out.append(teacher[0])
    for cid in canonical[1:]:
        if cid not in out: out.append(cid)
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--teacher", required=True)
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--source-truth", default="research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl")
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--output", default="artifacts/gemma4-yv-fusion-a1-v31.json"); a = ap.parse_args()

    registry = json.loads(Path(a.registry).read_text()); tw = fetch(TAXONOMY_URL)
    if hashlib.sha256(tw).hexdigest() != expected_hash(registry, "taxonomy-common-relations"): raise RuntimeError("taxonomy drift")
    concepts = json.loads(tw).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if c.get("id")}; ids = sorted(cid for cid,c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != 2105: raise RuntimeError("occupation universe drift")
    _, clean, quality = audit(load_teacher(Path(a.teacher)), by_id)
    canonical = build_c1_index(by_id, ids)
    teacher = BM25({cid: tokens(" ".join(ps)) for cid,ps in clean.items() if ps}, {cid:set() for cid,ps in clean.items() if ps})

    def rankings(q):
        c = canonical_rank(canonical, q); t = teacher_rank(teacher, q)
        return c, t, fuse(c, t)

    ow = fetch(OCC_INFO_URL)
    if hashlib.sha256(ow).hexdigest() != expected_hash(registry, "occupational-information"): raise RuntimeError("occupational-info drift")
    strict = strict_cases(json.loads(ow), by_id, ids); sr = {"canonical":[], "a1":[]}
    for case in strict:
        c, _, f = rankings(case["query"]); sr["canonical"].append(pos(c,{case["target"]})); sr["a1"].append(pos(f,{case["target"]}))

    guard = {"canonical":[], "a1":[]}; changes = 0
    source = load_jsonl(Path(a.source_truth))
    if len(source) != 333: raise RuntimeError("333 guard drift")
    for case in source:
        targets = {str(x["concept_id"]) for x in [*(case.get("must") or []), *(case.get("acceptable") or [])]}
        c, _, f = rankings(str(case["query"])); cr, fr = pos(c,targets), pos(f,targets)
        guard["canonical"].append(cr); guard["a1"].append(fr); changes += cr != fr
    gm = {name: metrics(r) for name,r in guard.items()}
    if gm["a1"]["top1"] != 333: raise RuntimeError("A1 violated canonical rank-1 guard")

    labels = {cid:str(by_id[cid].get("preferred_label") or cid) for cid in ids}; teacher_labels = {cid:labels[cid] for cid in teacher.documents}
    stress = json.loads(Path(a.stress).read_text()).get("yv") or []
    sums = {"canonical":defaultdict(lambda:{"target_cases":0,"top1":0,"hit5":0,"hit20":0}), "a1":defaultdict(lambda:{"target_cases":0,"top1":0,"hit5":0,"hit20":0})}
    negatives = []
    for case in stress:
        q = str(case["query"]); c,t,f = rankings(q); exp = [str(x) for x in case.get("expect") or []]
        if exp:
            for name, ranked in (("canonical",c),("a1",f)):
                r = family_rank(ranked,labels,exp); s=sums[name][str(case["category"])]
                s["target_cases"]+=1; s["top1"]+=r==1; s["hit5"]+=r is not None and r<=5; s["hit20"]+=r is not None and r<=20
        if case.get("should_abstain") or (case.get("should_clarify") and not exp):
            negatives.append({"id":case["id"],"category":case["category"],"query":q,"teacher_positive_match":bool(t),"teacher_top_label":teacher_labels.get(t[0]) if t else None})

    result = {
        "schema_version":1,"status":"opened architecture diagnostic; no runtime promotion","taxonomy_version":31,
        "candidate":"A1: canonical rank1 -> one filtered Gemma-teacher BM25 candidate -> remaining canonical order",
        "rationale":"smallest provenance-separated fusion; protects existing canonical top1 by construction; no parameter sweep",
        "quality_audit":quality,
        "strict_source_attested_17":{"canonical":metrics(sr["canonical"]),"a1":metrics(sr["a1"])},
        "canonical_source_truth_333":{"canonical":gm["canonical"],"a1":gm["a1"],"rank_changes":changes},
        "opened_stress_54":{"warning":"architecture diagnosis only; not tuning or accuracy evidence","canonical":dict(sums["canonical"]),"a1":dict(sums["a1"]),"negative_or_empty_clarify_teacher_behavior":negatives},
        "decision_rule":"A1 may survive only as an architecture candidate if it adds material description reach without canonical regression; promotion still requires new independent stream-separated evidence and abstention work."
    }
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
