#!/usr/bin/env python3
"""Test the cheapest richer KV semantic text: other human-mapped training modules.

The independent 35-case fresh holdout is excluded wholesale from retrieval evidence by
both module id and normalized description. The experiment then asks whether *other* AF
labour-market-training modules manually mapped to the same P80 skills provide useful
natural task/tool/method language.

No benchmark/synthetic query text is ingested. All emitted identities remain AF v31 skill
IDs. This is build-time enrichment and remains deployable through the same dumb postings
runtime if it wins.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_skill_c0_training_validation import p80_skill_ids, pct

TRAINING_URL = "https://data.arbetsformedlingen.se/utbildningar/mappings/mapping_labour-market-training.json"
TRAINING_SHA = "fea97867a1225e078d28ab9b0772f6a37f92b37c3c6c0d0e886ae65e9d79361c"
UA = "semantic-taxonomy-search-skill-training-enrichment/0.1"
CONFIGS = ("KV-C0", "KV-G1-single-desc", "KV-G1-single-name-desc", "KV-G1-all-desc")


def fetch_training() -> bytes:
    req = urllib.request.Request(TRAINING_URL, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=240) as response:
        return response.read()


def ids_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value]
    if value in (None, ""):
        return []
    return [str(value)]


def build_docs(
    by_id: dict[str, dict[str, Any]],
    skill_ids: list[str],
    modules: list[dict[str, Any]],
    excluded_module_ids: set[str],
    excluded_texts: set[str],
) -> tuple[dict[str, dict[str, list[str]]], dict[str, set[str]], dict[str, Any]]:
    canonical: dict[str, list[str]] = {}
    exact: dict[str, set[str]] = {}
    for sid in skill_ids:
        skill = by_id.get(sid)
        if not isinstance(skill, dict) or skill.get("type") != "skill":
            raise RuntimeError(f"invalid P80 skill {sid}")
        label = str(skill.get("preferred_label") or "").strip()
        definition = str(skill.get("definition") or "").strip()
        real_definition = definition if definition and norm(definition) != norm(label) else ""
        alternatives = [x for x in as_list(skill.get("alternative_labels")) if norm(x) != norm(label)]
        canonical[sid] = tokens(" ".join([label, real_definition, *alternatives]))
        exact[sid] = {norm(label), *[norm(x) for x in alternatives if norm(x)]}

    p80 = set(skill_ids)
    single_desc: dict[str, dict[str, str]] = defaultdict(dict)
    single_name_desc: dict[str, dict[str, str]] = defaultdict(dict)
    all_desc: dict[str, dict[str, str]] = defaultdict(dict)
    source_rows = accepted_rows = excluded_rows = 0
    for module in modules:
        if not isinstance(module, dict):
            continue
        source_rows += 1
        desc = str(module.get("modulbeskrivning") or "").strip()
        ndesc = norm(desc)
        if not ndesc:
            continue
        mids = ids_list(module.get("modul_id"))
        if any(mid in excluded_module_ids for mid in mids) or ndesc in excluded_texts:
            excluded_rows += 1
            continue
        mapped = []
        for item in module.get("kompetenser_kopplade_till_modulen") or []:
            if isinstance(item, dict) and item.get("koncept_id"):
                sid = str(item["koncept_id"])
                if sid in p80:
                    mapped.append(sid)
        mapped = sorted(set(mapped))
        if not mapped:
            continue
        accepted_rows += 1
        name = str(module.get("modulnamn") or "").strip()
        for sid in mapped:
            all_desc[sid].setdefault(ndesc, desc)
        if len(mapped) == 1:
            sid = mapped[0]
            single_desc[sid].setdefault(ndesc, desc)
            combined = " ".join(x for x in (name, desc) if x)
            single_name_desc[sid].setdefault(norm(combined), combined)

    docs: dict[str, dict[str, list[str]]] = {name: {} for name in CONFIGS}
    for sid in skill_ids:
        docs["KV-C0"][sid] = list(canonical[sid])
        docs["KV-G1-single-desc"][sid] = [*canonical[sid], *tokens(" ".join(single_desc[sid].values()))]
        docs["KV-G1-single-name-desc"][sid] = [*canonical[sid], *tokens(" ".join(single_name_desc[sid].values()))]
        docs["KV-G1-all-desc"][sid] = [*canonical[sid], *tokens(" ".join(all_desc[sid].values()))]

    def lane_stats(lane: dict[str, dict[str, str]]) -> dict[str, int]:
        return {
            "skills_with_enrichment": sum(bool(v) for v in lane.values()),
            "unique_descriptions": sum(len(v) for v in lane.values()),
            "enrichment_tokens": sum(len(tokens(" ".join(v.values()))) for v in lane.values()),
        }

    coverage = {
        "source_rows": source_rows,
        "accepted_nonholdout_rows_with_p80_skill": accepted_rows,
        "rows_excluded_by_fresh_holdout": excluded_rows,
        "fresh_holdout_module_ids_excluded": len(excluded_module_ids),
        "fresh_holdout_texts_excluded": len(excluded_texts),
        "single_desc": lane_stats(single_desc),
        "single_name_desc": lane_stats(single_name_desc),
        "all_desc": lane_stats(all_desc),
    }
    return docs, exact, coverage


def rank(ranker: BM25, exact: dict[str, set[str]], query: str) -> list[str]:
    q = tokens(query)
    nq = norm(query)
    scored = []
    for sid in ranker.documents:
        score = ranker.score(q, sid)
        if nq and nq in exact[sid]:
            score += 1_000_000.0
        if score > 0:
            scored.append((score, sid))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [sid for _, sid in scored]


def evaluate_target_cases(cases: list[dict[str, Any]], ranker: BM25, exact: dict[str, set[str]]) -> dict[str, Any]:
    total = hit1 = hit5 = hit10 = 0
    weight = wh1 = wh5 = wh10 = 0
    details = []
    for case in cases:
        target = str(case["target"]["concept_id"])
        w = int(case["target"].get("occurrence_proxy") or 0)
        ranked = rank(ranker, exact, str(case["query"]))
        h1 = bool(ranked and ranked[0] == target)
        h5 = target in ranked[:5]
        h10 = target in ranked[:10]
        total += 1; hit1 += int(h1); hit5 += int(h5); hit10 += int(h10)
        weight += w; wh1 += w * int(h1); wh5 += w * int(h5); wh10 += w * int(h10)
        details.append({"id": case["id"], "target_id": target, "top1": h1, "hit5": h5, "hit10": h10, "top5": ranked[:5]})
    return {
        "cases": total,
        "top1_pct": pct(hit1, total),
        "discovery_hit_at_5_pct": pct(hit5, total),
        "hit_at_10_pct": pct(hit10, total),
        "occurrence_proxy_weight": weight,
        "weighted_top1_pct": pct(wh1, weight),
        "weighted_discovery_hit_at_5_pct": pct(wh5, weight),
        "weighted_hit_at_10_pct": pct(wh10, weight),
        "details": details,
    }


def evaluate_canonical(cases: list[dict[str, Any]], ranker: BM25, exact: dict[str, set[str]]) -> dict[str, Any]:
    top1 = hit5 = 0
    misses = []
    for case in cases:
        relevant = {str(x["concept_id"]) for x in case["must"]}
        ranked = rank(ranker, exact, str(case["query"]))
        t1 = bool(ranked and ranked[0] in relevant)
        h5 = any(sid in relevant for sid in ranked[:5])
        top1 += int(t1); hit5 += int(h5)
        if not t1:
            misses.append({"id": case["id"], "query": case["query"], "expected": sorted(relevant), "top5": ranked[:5]})
    return {"cases": len(cases), "top1_pct": pct(top1, len(cases)), "discovery_hit_at_5_pct": pct(hit5, len(cases)), "top1_miss_count": len(misses), "top1_misses_first_20": misses[:20]}


def evaluate_synthetic(cases: list[dict[str, Any]], ranker: BM25, exact: dict[str, set[str]]) -> dict[str, Any]:
    hit1 = hit5 = hit10 = 0
    rows = []
    for case in cases:
        relevant = {str(x["concept_id"]) for x in case.get("must") or []}
        ranked = rank(ranker, exact, str(case["query"]))
        h1 = bool(ranked and ranked[0] in relevant); h5 = any(x in relevant for x in ranked[:5]); h10 = any(x in relevant for x in ranked[:10])
        hit1 += int(h1); hit5 += int(h5); hit10 += int(h10)
        rows.append({"id": case["id"], "top1": h1, "hit5": h5, "hit10": h10, "top5": ranked[:5]})
    return {"cases": len(cases), "top1_pct": pct(hit1, len(cases)), "discovery_hit_at_5_pct": pct(hit5, len(cases)), "hit_at_10_pct": pct(hit10, len(cases)), "details": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--holdout", default="research/benchmark/v31/training-skill-fresh-holdout/cases.jsonl")
    ap.add_argument("--canonical", default="research/benchmark/v31/p80-source-truth/kv-p80-source-truth.jsonl")
    ap.add_argument("--synthetic", default="research/benchmark/v31/synthetic-description-stress/cases.jsonl")
    ap.add_argument("--output", default="artifacts/skill-training-language-enrichment-v31.json")
    args = ap.parse_args()

    holdout = load_jsonl(Path(args.holdout))
    canonical = load_jsonl(Path(args.canonical))
    synthetic = [c for c in load_jsonl(Path(args.synthetic)) if c.get("product") == "KV"]
    if len(holdout) != 35 or len(canonical) != 617 or len(synthetic) != 12:
        raise RuntimeError(f"benchmark count drift: {len(holdout)}/{len(canonical)}/{len(synthetic)}")
    excluded_module_ids = {mid for case in holdout for mid in ids_list(case.get("module_ids"))}
    excluded_texts = {norm(case["query"]) for case in holdout}

    training_body = fetch_training()
    training_sha = hashlib.sha256(training_body).hexdigest()
    if training_sha != TRAINING_SHA:
        raise RuntimeError(f"training source drift: {training_sha} != {TRAINING_SHA}")
    training_json = json.loads(training_body)
    modules = (training_json.get("data") or training_json.get("moduler") or training_json.get("modules")) if isinstance(training_json, dict) else training_json
    if not isinstance(modules, list):
        raise RuntimeError("unexpected training mapping root")

    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    version = str(args.version)
    tax_url = f"https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    tax_body = fetch(tax_url)
    tax_sha = hashlib.sha256(tax_body).hexdigest()
    if tax_sha != expected_hash(registry, "taxonomy-common-relations"):
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(tax_body).get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    skill_ids = p80_skill_ids(pareto)

    docs, exact, coverage = build_docs(by_id, skill_ids, modules, excluded_module_ids, excluded_texts)
    results = {}
    for config in CONFIGS:
        ranker = BM25(docs[config], exact)
        results[config] = {
            "fresh_holdout": evaluate_target_cases(holdout, ranker, exact),
            "canonical_regression": evaluate_canonical(canonical, ranker, exact),
            "synthetic_stress": evaluate_synthetic(synthetic, ranker, exact),
        }

    result = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "taxonomy_sha256": tax_sha,
        "training_source": {"url": TRAINING_URL, "sha256": training_sha, "provenance": "manual_curated_mapping"},
        "holdout_exclusion": "all 35 fresh-holdout module ids and normalized descriptions are excluded from every enrichment lane before retrieval documents are built",
        "synthetic_ingested": False,
        "fresh_holdout_ingested": False,
        "configurations": {
            "KV-C0": "canonical P80 skill text only",
            "KV-G1-single-desc": "C0 + descriptions from non-holdout training modules that map to exactly one P80 skill",
            "KV-G1-single-name-desc": "same as G1-single plus module name",
            "KV-G1-all-desc": "C0 + descriptions from non-holdout training modules appended to every mapped P80 skill",
        },
        "coverage": coverage,
        "results": results,
        "runtime_implication": "all enrichment is static build-time text; a winning lane can be compiled to the same postings-only frontend student runtime",
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    compact = {cfg: {"fresh": r["fresh_holdout"], "canonical": r["canonical_regression"], "synthetic": r["synthetic_stress"]} for cfg, r in results.items()}
    for r in compact.values():
        r["fresh"].pop("details", None); r["synthetic"].pop("details", None); r["canonical"].pop("top1_misses_first_20", None)
    print(json.dumps({"coverage": coverage, "results": compact}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
