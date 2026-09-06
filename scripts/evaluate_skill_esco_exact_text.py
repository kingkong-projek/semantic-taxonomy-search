#!/usr/bin/env python3
"""Evaluate the safest ESCO text lane for natural text -> P80 skill discovery.

Only taxonomy-v31 `exact_match` edges from AF `skill` identities to `esco-skill`
identities are admitted. ESCO preferred labels, real definitions and alternative labels
become retrieval token context. AF skill identity and exact lexical surfaces remain the
only emitted/selectable identities.

No broad/narrow/close ESCO mapping is collapsed into exact mapping in this experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids, pct


def relation_ids(concept: dict[str, Any], field: str) -> list[str]:
    value = concept.get(field)
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, dict) and item.get("id"):
            out.append(str(item["id"]))
        elif isinstance(item, str):
            out.append(item)
    return out


def canonical_parts(c: dict[str, Any]) -> tuple[str, str, list[str]]:
    label = str(c.get("preferred_label") or "").strip()
    definition = str(c.get("definition") or "").strip()
    real_definition = definition if definition and norm(definition) != norm(label) else ""
    alternatives = [x for x in as_list(c.get("alternative_labels")) if norm(x) != norm(label)]
    return label, real_definition, alternatives


def positive_rank(ranker: BM25, exact: dict[str, set[str]], query: str) -> list[str]:
    q = tokens(query); nq = norm(query); scored = []
    for sid in ranker.documents:
        score = ranker.score(q, sid)
        if nq and nq in exact[sid]:
            score += 1_000_000.0
        if score > 0.0:
            scored.append((score, sid))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [sid for _, sid in scored]


def summarize(cases: list[dict[str, Any]], ranker: BM25, exact: dict[str, set[str]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    s = defaultdict(float); details = []
    for case in cases:
        target = str(case["target"]["concept_id"])
        weight = int(case["target"]["occurrence_proxy"])
        ranked = positive_rank(ranker, exact, str(case["query"]))
        h1 = bool(ranked and ranked[0] == target); h5 = target in ranked[:5]; h10 = target in ranked[:10]
        s["cases"] += 1; s["weight"] += weight
        s["h1"] += int(h1); s["h5"] += int(h5); s["h10"] += int(h10)
        s["wh1"] += weight*int(h1); s["wh5"] += weight*int(h5); s["wh10"] += weight*int(h10)
        details.append({"id":case["id"],"target_id":target,"top1_success":h1,"discovery_hit_at_5":h5,"hit_at_10":h10,"top5_ids":ranked[:5]})
    return {
        "cases":int(s["cases"]),"occurrence_proxy_weight":int(s["weight"]),
        "top1_pct":pct(s["h1"],s["cases"]),"weighted_top1_pct":pct(s["wh1"],s["weight"]),
        "discovery_hit_at_5_pct":pct(s["h5"],s["cases"]),"weighted_discovery_hit_at_5_pct":pct(s["wh5"],s["weight"]),
        "hit_at_10_pct":pct(s["h10"],s["cases"]),"weighted_hit_at_10_pct":pct(s["wh10"],s["weight"]),
    }, details


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--benchmark", default="research/benchmark/v31/training-skill-validation/cases.jsonl")
    ap.add_argument("--source-truth", default="research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl")
    ap.add_argument("--output", default="artifacts/skill-esco-exact-text-v31.json")
    args = ap.parse_args()

    cases = load_jsonl(Path(args.benchmark)); source_truth = load_jsonl(Path(args.source_truth))
    primary = [c for c in cases if c.get("primary_descriptive_nonleaky")]
    if len(cases)!=76 or len(primary)!=63 or len(source_truth)!=617:
        raise RuntimeError("benchmark count drift")

    registry=json.loads(Path(args.registry).read_text(encoding="utf-8")); pareto=json.loads(Path(args.pareto).read_text(encoding="utf-8")); version=str(args.version)
    url=f"https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    body=fetch(url); sha=hashlib.sha256(body).hexdigest()
    if sha!=expected_hash(registry,"taxonomy-common-relations"): raise RuntimeError("taxonomy source drift")
    concepts=json.loads(body).get("data",{}).get("concepts")
    if not isinstance(concepts,list): raise RuntimeError("taxonomy missing concepts")
    by_id={str(c["id"]):c for c in concepts if isinstance(c,dict) and c.get("id")}

    ids=p80_skill_ids(pareto); c0_docs={}; d1_docs={}; exact={}; esco_by_skill={}; coverage=defaultdict(int)
    for sid in ids:
        c=by_id.get(sid)
        if not isinstance(c,dict) or c.get("type")!="skill": raise RuntimeError(f"invalid P80 skill {sid}")
        label,definition,alternatives=canonical_parts(c)
        canonical_text=" ".join([label,definition,*alternatives])
        c0_docs[sid]=tokens(canonical_text)
        exact[sid]={norm(label), *[norm(x) for x in alternatives if norm(x)]}

        esco_ids=[]; esco_text=[]
        for tid in relation_ids(c,"exact_match"):
            target=by_id.get(tid)
            if isinstance(target,dict) and target.get("type")=="esco-skill":
                esco_ids.append(tid)
                elabel,edef,ealts=canonical_parts(target)
                pieces=[elabel,edef,*ealts]
                if elabel: coverage["esco_targets_with_label"] += 1
                if edef: coverage["esco_targets_with_real_definition"] += 1
                if ealts: coverage["esco_targets_with_alternative_labels"] += 1
                esco_text.extend(x for x in pieces if x)
        esco_ids=sorted(set(esco_ids)); esco_by_skill[sid]=esco_ids
        if esco_ids:
            coverage["p80_skills_with_exact_esco"] += 1
            coverage["exact_esco_edges"] += len(esco_ids)
        d1_docs[sid]=tokens(" ".join([canonical_text,*esco_text]))
    coverage["p80_skills"]=len(ids)

    benchmark_targets={str(c["target"]["concept_id"]) for c in cases}; primary_targets={str(c["target"]["concept_id"]) for c in primary}
    coverage["benchmark_targets"]=len(benchmark_targets); coverage["benchmark_targets_with_exact_esco"]=sum(bool(esco_by_skill[s]) for s in benchmark_targets)
    coverage["primary_targets"]=len(primary_targets); coverage["primary_targets_with_exact_esco"]=sum(bool(esco_by_skill[s]) for s in primary_targets)

    configs={"KV-C0":BM25(c0_docs,exact),"KV-D1-exact-ESCO-text":BM25(d1_docs,exact)}
    benchmark_out={}; details_out={}; regression_out={}
    for name,ranker in configs.items():
        all_summary,details=summarize(cases,ranker,exact); primary_summary,_=summarize(primary,ranker,exact)
        benchmark_out[name]={"all_cases":all_summary,"primary_descriptive_nonleaky":primary_summary}; details_out[name]=details
        top1=hit5=0; misses=[]
        for case in source_truth:
            positive={str(x["concept_id"]) for x in case["must"]}; ranked=positive_rank(ranker,exact,str(case["query"])); t1=bool(ranked and ranked[0] in positive); h5=any(s in positive for s in ranked[:5]); top1+=int(t1); hit5+=int(h5)
            if not t1 or not h5: misses.append({"id":case["id"],"query":case["query"],"top5":ranked[:5],"top1_ok":t1,"hit5":h5})
        regression_out[name]={"cases":617,"top1_pct":pct(top1,617),"discovery_hit_at_5_pct":pct(hit5,617),"failure_count":len(misses),"failures_first_20":misses[:20]}

    result={
        "schema_version":1,"taxonomy_version":int(version),"taxonomy_sha256":sha,
        "experiment_role":"development ablation; benchmark already opened by KV-C0",
        "mapping_policy":"AF skill exact_match -> esco-skill only; broad/narrow/close excluded",
        "identity_boundary":"ESCO text is retrieval evidence only; emitted IDs remain AF v31 skill identities and ESCO strings are not exact AF surfaces",
        "runtime_implication":"all ESCO text comes from the already-pinned v31 snapshot and can be precompiled into a static data package",
        "coverage":dict(coverage),"benchmark":benchmark_out,"source_truth_regression":regression_out,"cases_detail":details_out,
    }
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"coverage":dict(coverage),"benchmark":benchmark_out,"source_truth_regression":regression_out},ensure_ascii=False,indent=2,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
