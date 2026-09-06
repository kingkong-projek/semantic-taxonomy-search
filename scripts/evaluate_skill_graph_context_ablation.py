#!/usr/bin/env python3
"""Evaluate the smallest typed graph-context additions for natural text -> P80 skill discovery.

Configurations:
- KV-C0: canonical P80 skill text only.
- KV-C1e: C0 + preferred labels of occupations that mark the skill essential or regulated.
- KV-C1all: C0 + preferred labels of occupations that mark the skill essential, regulated or optional.

Occupation context is retrieval-only typed evidence. It is token evidence, never an exact
skill surface, and benchmark training text is never ingested into retrieval documents.
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

CONFIGS = ("KV-C0", "KV-C1e", "KV-C1all")


def build_docs(
    by_id: dict[str, dict[str, Any]],
    skill_ids: list[str],
    essential_occ: dict[str, set[str]],
    all_occ: dict[str, set[str]],
) -> tuple[dict[str, dict[str, list[str]]], dict[str, set[str]], dict[str, Any]]:
    docs: dict[str, dict[str, list[str]]] = {name: {} for name in CONFIGS}
    exact: dict[str, set[str]] = {}
    coverage = defaultdict(int)
    for sid in skill_ids:
        skill = by_id.get(sid)
        if not isinstance(skill, dict) or skill.get("type") != "skill":
            raise RuntimeError(f"invalid P80 skill {sid}")
        label = str(skill.get("preferred_label") or "").strip()
        definition = str(skill.get("definition") or "").strip()
        real_definition = definition if definition and norm(definition) != norm(label) else ""
        alternatives = [x for x in as_list(skill.get("alternative_labels")) if norm(x) != norm(label)]
        canonical = tokens(" ".join([label, real_definition, *alternatives]))
        exact[sid] = {norm(label), *[norm(x) for x in alternatives if norm(x)]}

        def occ_labels(ids: set[str]) -> list[str]:
            out = []
            for oid in sorted(ids):
                occ = by_id.get(oid)
                if isinstance(occ, dict) and occ.get("type") == "occupation-name":
                    value = str(occ.get("preferred_label") or "").strip()
                    if value:
                        out.append(value)
            return sorted(set(out), key=lambda x: (norm(x), x))

        e_labels = occ_labels(essential_occ.get(sid, set()))
        all_labels = occ_labels(all_occ.get(sid, set()))
        if e_labels:
            coverage["p80_with_essential_regulated_context"] += 1
        if all_labels:
            coverage["p80_with_any_context"] += 1
        coverage["essential_regulated_occ_edges"] += len(e_labels)
        coverage["all_occ_edges"] += len(all_labels)
        docs["KV-C0"][sid] = list(canonical)
        docs["KV-C1e"][sid] = [*canonical, *tokens(" ".join(e_labels))]
        docs["KV-C1all"][sid] = [*canonical, *tokens(" ".join(all_labels))]
    coverage["p80_skills"] = len(skill_ids)
    return docs, exact, dict(coverage)


def positive_rank(ranker: BM25, exact: dict[str, set[str]], query: str) -> list[str]:
    q = tokens(query)
    nq = norm(query)
    scored: list[tuple[float, str]] = []
    for sid in ranker.documents:
        score = ranker.score(q, sid)
        if nq and nq in exact[sid]:
            score += 1_000_000.0
        if score > 0.0:
            scored.append((score, sid))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [sid for _, sid in scored]


def summarize_cases(cases: list[dict[str, Any]], ranker: BM25, exact: dict[str, set[str]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    s = defaultdict(float)
    details = []
    for case in cases:
        target = str(case["target"]["concept_id"])
        weight = int(case["target"]["occurrence_proxy"])
        ranked = positive_rank(ranker, exact, str(case["query"]))
        h1 = bool(ranked and ranked[0] == target)
        h5 = target in ranked[:5]
        h10 = target in ranked[:10]
        s["cases"] += 1; s["weight"] += weight
        s["h1"] += int(h1); s["h5"] += int(h5); s["h10"] += int(h10)
        s["wh1"] += weight * int(h1); s["wh5"] += weight * int(h5); s["wh10"] += weight * int(h10)
        details.append({
            "id": case["id"], "target_id": target,
            "primary_descriptive_nonleaky": bool(case["primary_descriptive_nonleaky"]),
            "top1_success": h1, "discovery_hit_at_5": h5, "hit_at_10": h10,
            "top5_ids": ranked[:5],
        })
    return {
        "cases": int(s["cases"]), "occurrence_proxy_weight": int(s["weight"]),
        "top1_pct": pct(s["h1"], s["cases"]), "weighted_top1_pct": pct(s["wh1"], s["weight"]),
        "discovery_hit_at_5_pct": pct(s["h5"], s["cases"]), "weighted_discovery_hit_at_5_pct": pct(s["wh5"], s["weight"]),
        "hit_at_10_pct": pct(s["h10"], s["cases"]), "weighted_hit_at_10_pct": pct(s["wh10"], s["weight"]),
    }, details


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--relation-aggregate", default="research/coverage/v31/native-occupation-skill-aggregate.json")
    ap.add_argument("--benchmark", default="research/benchmark/v31/training-skill-validation/cases.jsonl")
    ap.add_argument("--source-truth", default="research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl")
    ap.add_argument("--output", default="artifacts/skill-graph-context-ablation-v31.json")
    args = ap.parse_args()

    version = str(args.version)
    cases = load_jsonl(Path(args.benchmark))
    source_truth = load_jsonl(Path(args.source_truth))
    if len(cases) != 76 or len(source_truth) != 617:
        raise RuntimeError(f"benchmark count drift {len(cases)}/{len(source_truth)}")
    primary = [c for c in cases if c.get("primary_descriptive_nonleaky")]
    if len(primary) != 63:
        raise RuntimeError(f"primary slice drift {len(primary)}")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    rel_agg = json.loads(Path(args.relation_aggregate).read_text(encoding="utf-8"))

    tax_url = f"https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    tax_body = fetch(tax_url)
    tax_sha = hashlib.sha256(tax_body).hexdigest()
    if tax_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(tax_body).get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    kv_source = rel_agg["sources"]["kompetensvaljaren"]
    kv_url = str(kv_source["url"])
    kv_body = fetch(kv_url)
    kv_sha = hashlib.sha256(kv_body).hexdigest()
    if kv_sha != str(kv_source["sha256"]):
        raise RuntimeError(f"KV relation source drift {kv_sha} != {kv_source['sha256']}")
    kv = json.loads(kv_body)
    data = kv.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("KV relation source missing data")

    essential_occ: dict[str, set[str]] = defaultdict(set)
    optional_occ: dict[str, set[str]] = defaultdict(set)
    for oid, record in data.items():
        if not isinstance(record, dict) or record.get("type") != "occupation-name":
            continue
        if by_id.get(str(oid), {}).get("type") != "occupation-name":
            raise RuntimeError(f"invalid KV occupation {oid}")
        for field in ("essential_skills", "regulated_skills"):
            mapping = record.get(field) or {}
            if not isinstance(mapping, dict):
                raise RuntimeError(f"{field} not object for {oid}")
            for sid in mapping.values():
                if sid:
                    essential_occ[str(sid)].add(str(oid))
        mapping = record.get("optional_skills") or {}
        if not isinstance(mapping, dict):
            raise RuntimeError(f"optional_skills not object for {oid}")
        for sid in mapping.values():
            if sid:
                optional_occ[str(sid)].add(str(oid))

    all_occ: dict[str, set[str]] = defaultdict(set)
    for sid in set(essential_occ) | set(optional_occ):
        all_occ[sid] = set(essential_occ.get(sid, set())) | set(optional_occ.get(sid, set()))

    skill_ids = p80_skill_ids(pareto)
    docs, exact, context_coverage = build_docs(by_id, skill_ids, essential_occ, all_occ)
    benchmark_out = {}
    regression_out = {}
    details_out = {}
    for name in CONFIGS:
        ranker = BM25(docs[name], exact)
        all_summary, details = summarize_cases(cases, ranker, exact)
        primary_summary, _ = summarize_cases(primary, ranker, exact)
        benchmark_out[name] = {"all_cases": all_summary, "primary_descriptive_nonleaky": primary_summary}
        details_out[name] = details

        top1 = hit5 = 0
        misses = []
        for case in source_truth:
            positive = {str(x["concept_id"]) for x in case["must"]}
            ranked = positive_rank(ranker, exact, str(case["query"]))
            t1 = bool(ranked and ranked[0] in positive)
            h5 = any(sid in positive for sid in ranked[:5])
            top1 += int(t1); hit5 += int(h5)
            if not t1:
                misses.append({"id": case["id"], "query": case["query"], "top5": ranked[:5]})
        regression_out[name] = {
            "cases": 617, "top1_pct": pct(top1, 617), "discovery_hit_at_5_pct": pct(hit5, 617),
            "top1_miss_count": len(misses), "top1_misses_first_20": misses[:20],
        }

    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "taxonomy_sha256": tax_sha,
        "kv_relation_source_sha256": kv_sha,
        "experiment_role": "development ablation; benchmark was opened by KV-C0 before these graph-context variants were evaluated",
        "authority_boundary": "training module text is benchmark/query truth only and is never retrieval vocabulary; occupation labels come only from typed KV/native occupation-skill relations",
        "configurations": {
            "KV-C0": "canonical P80 skill preferred label + real definition + canonical alternatives",
            "KV-C1e": "KV-C0 + preferred labels of typed essential/regulated occupations as BM25 token context; not exact skill surfaces",
            "KV-C1all": "KV-C1e + preferred labels of typed optional occupations as BM25 token context; not exact skill surfaces",
        },
        "context_coverage": context_coverage,
        "benchmark": benchmark_out,
        "source_truth_regression": regression_out,
        "cases_detail": details_out,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"context_coverage": context_coverage, "benchmark": benchmark_out, "source_truth_regression": regression_out}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
