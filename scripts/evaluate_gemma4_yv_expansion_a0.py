#!/usr/bin/env python3
"""Opened A0 probe: Gemma-4 sequence-level YV doc2query expansion."""
from __future__ import annotations

import argparse, hashlib, json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from evaluate_c2_job_title_router import build_c1_index, relation_parent_ids
from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, load_jsonl, norm, tokens
from evaluate_pareto_c1 import rank_c1
from occupational_information_coverage import find_explicit_taxonomy_ids, record_map

TAXONOMY_URL = "https://data.jobtechdev.se/taxonomy/version/31/query/concepts-and-common-relations/concepts-and-common-relations.json"
OCC_INFO_URL = "https://data.arbetsformedlingen.se/yrke/yrkesinformation/yrkesinformation-interimslosning.json"
TEACHER_SHA = "1a6e26840480d0cd6ffce23e3214d026cefa202397f4e84115e9fe2ac1e1045b"
BANNED = ("gubbe", "gubbar", "tjej", "tjejer", "pamp", "kärring", "snubbe", "snubbar")


def present(text: str, surface: str) -> bool:
    h, n = tokens(text), tokens(surface)
    return bool(n) and len(n) <= len(h) and any(h[i:i+len(n)] == n for i in range(len(h)-len(n)+1))


def parts(c: dict[str, Any]) -> tuple[list[str], set[str]]:
    label = str(c.get("preferred_label") or "").strip()
    definition = str(c.get("definition") or "").strip()
    definition = definition if definition and norm(definition) != norm(label) else ""
    alts = [x for x in as_list(c.get("alternative_labels")) if norm(x) != norm(label)]
    return [x for x in [label, definition, *alts] if x], {norm(x) for x in [label, *alts] if norm(x)}


def load_teacher(path: Path) -> list[dict[str, Any]]:
    wire = path.read_bytes()
    if hashlib.sha256(wire).hexdigest() != TEACHER_SHA:
        raise RuntimeError("teacher corpus SHA drift")
    rows = [json.loads(x) for x in wire.decode().splitlines() if x.strip()]
    if len(rows) != 149 or len({str(r["concept_id"]) for r in rows}) != 149:
        raise RuntimeError("teacher row/identity drift")
    if any(len(r.get("phrases") or []) != 8 for r in rows):
        raise RuntimeError("teacher phrase-count drift")
    return rows


def audit(rows: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]):
    raw, clean = {}, {}
    global_phrases: Counter[str] = Counter()
    stats: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cid = str(row["concept_id"]); c = by_id.get(cid)
        if not c or c.get("type") != "occupation-name":
            raise RuntimeError(f"bad teacher target {cid}")
        phrases = [str(x).strip() for x in row["phrases"]]; raw[cid] = phrases
        _, surfaces = parts(c); seen = set(); kept = []
        for slot, phrase in enumerate(phrases, 1):
            np = norm(phrase); global_phrases[np] += 1; reasons = []
            if len(tokens(phrase)) <= 2: stats["short_le_2_tokens"] += 1
            if np in seen: reasons.append("within_concept_duplicate")
            seen.add(np)
            leaks = [s for s in surfaces if present(phrase, s)]
            if leaks: reasons.append("canonical_or_alt_surface_leak")
            pt = tokens(phrase); bad = [b for b in BANNED if any(b in t for t in pt)]
            if bad: reasons.append("stereotyped_colloquialism")
            for reason in set(reasons):
                stats[reason] += 1
                if len(examples[reason]) < 20:
                    examples[reason].append({"label": c.get("preferred_label"), "slot": slot, "phrase": phrase})
            if not reasons: kept.append(phrase)
        clean[cid] = kept
    dups = [(p, n) for p, n in global_phrases.items() if n > 1]
    return raw, clean, {
        "concepts": len(rows), "phrases": sum(len(x) for x in raw.values()),
        "filtered_phrases": sum(len(x) for x in clean.values()),
        "short_le_2_tokens": stats["short_le_2_tokens"],
        "global_exact_duplicate_values": len(dups),
        "global_exact_duplicate_extra_occurrences": sum(n-1 for _, n in dups),
        "within_concept_duplicate_extra_occurrences": stats["within_concept_duplicate"],
        "canonical_or_alt_surface_leaks": stats["canonical_or_alt_surface_leak"],
        "stereotyped_colloquialisms": stats["stereotyped_colloquialism"],
        "examples": dict(examples),
        "filter_policy": "query-independent: drop within-concept duplicates, target preferred/alternative-label leaks, and frozen stereotyped colloquial stems only; keep short/noisy phrases",
    }


def augmented(by_id, ids, extra):
    docs, exact, stoks = {}, {}, {}
    for cid in ids:
        base, surfaces = parts(by_id[cid]); docs[cid] = tokens(" ".join([*base, *extra.get(cid, [])]))
        exact[cid] = surfaces; stoks[cid] = {t for s in surfaces for t in tokens(s)}
    return BM25(docs, exact), exact, stoks


def rank(v, q):
    r, e, s = v
    return [cid for cid, _, _ in rank_c1(r, q, e, s)]


def pos(ranked, targets):
    vals = [ranked.index(cid)+1 for cid in targets if cid in ranked]
    return min(vals) if vals else None


def metrics(rs):
    n = len(rs)
    return {"cases": n, "top1": sum(r == 1 for r in rs), "hit_at_5": sum(r is not None and r <= 5 for r in rs),
            "mrr": round(sum(0 if r is None else 1/r for r in rs)/n, 6) if n else 0.0}


def strict_cases(source, by_id, occ_ids):
    active, all_ids = set(occ_ids), set(by_id); records = record_map(source.get("data"))
    meta = source.get("metadata", {}).get("occupations"); jt = defaultdict(set)
    if not isinstance(meta, list): raise RuntimeError("Yrkesinformation metadata drift")
    for c in by_id.values():
        if c.get("type") == "job-title":
            label = str(c.get("preferred_label") or "").strip()
            for parent in relation_parent_ids(c, by_id): jt[parent].add(label)
    out = []
    for m in meta:
        rec = records.get(str(m.get("slug") or "")) if isinstance(m, dict) else None
        if not isinstance(rec, dict): continue
        explicit = find_explicit_taxonomy_ids(rec, all_ids) & active
        if len(explicit) != 1: continue
        target = next(iter(explicit)); q = str(rec.get("work_task") or "").strip()
        if len(q) < 40: continue
        c = by_id[target]; surfaces = {str(c.get("preferred_label") or ""), *as_list(c.get("alternative_labels")), *jt[target]}
        if any(s and present(q, s) for s in surfaces): continue
        out.append({"id": str(m.get("slug") or ""), "query": q, "target": target})
    if len(out) != 17: raise RuntimeError(f"strict case drift {len(out)}")
    return out


def family_rank(ranked, labels, expected):
    needles = [norm(x) for x in expected if norm(x)]
    for i, cid in enumerate(ranked, 1):
        if any(n in norm(labels[cid]) for n in needles): return i
    return None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--teacher", required=True)
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--source-truth", default="research/benchmark/v31/p80-source-truth/yv-p80-source-truth.jsonl")
    ap.add_argument("--stress", default="research/evaluation/v31/opened-live-semantic-stress-v1.json")
    ap.add_argument("--output", default="artifacts/gemma4-yv-expansion-a0-v31.json"); a = ap.parse_args()
    registry = json.loads(Path(a.registry).read_text()); tw = fetch(TAXONOMY_URL)
    if hashlib.sha256(tw).hexdigest() != expected_hash(registry, "taxonomy-common-relations"): raise RuntimeError("taxonomy drift")
    concepts = json.loads(tw).get("data", {}).get("concepts") or []; by_id = {str(c["id"]): c for c in concepts if c.get("id")}
    ids = sorted(cid for cid, c in by_id.items() if c.get("type") == "occupation-name")
    if len(ids) != 2105: raise RuntimeError("occupation universe drift")
    raw, clean, quality = audit(load_teacher(Path(a.teacher)), by_id)
    variants = {"canonical": build_c1_index(by_id, ids), "raw_concat": augmented(by_id, ids, raw), "filtered_concat": augmented(by_id, ids, clean)}
    teacher = BM25({cid: tokens(" ".join(ps)) for cid, ps in clean.items() if ps}, {cid: set() for cid, ps in clean.items() if ps})

    ow = fetch(OCC_INFO_URL)
    if hashlib.sha256(ow).hexdigest() != expected_hash(registry, "occupational-information"): raise RuntimeError("occupational-info drift")
    strict = strict_cases(json.loads(ow), by_id, ids); strict_ranks = {name: [] for name in variants}; oracle17 = 0; covered17 = 0
    for c in strict:
        for name, v in variants.items(): strict_ranks[name].append(pos(rank(v, c["query"]), {c["target"]}))
        tr = pos(teacher.rank(c["query"]), {c["target"]}) if c["target"] in teacher.documents else None
        covered17 += c["target"] in teacher.documents
        br = strict_ranks["canonical"][-1]; oracle17 += (br is not None and br <= 5) or (tr is not None and tr <= 5)

    source = load_jsonl(Path(a.source_truth)); guard = {name: [] for name in variants}; changes = Counter()
    if len(source) != 333: raise RuntimeError("333 guard drift")
    for c in source:
        targets = {str(x["concept_id"]) for x in [*(c.get("must") or []), *(c.get("acceptable") or [])]}
        per = {name: pos(rank(v, str(c["query"])), targets) for name, v in variants.items()}
        for name, r in per.items(): guard[name].append(r)
        for name in ("raw_concat", "filtered_concat"): changes[name] += per[name] != per["canonical"]

    stress = json.loads(Path(a.stress).read_text()).get("yv") or []; labels = {cid: str(by_id[cid].get("preferred_label") or cid) for cid in ids}
    sm = {name: defaultdict(lambda: {"target_cases": 0, "top1": 0, "hit5": 0, "hit20": 0}) for name in variants}
    oracle = defaultdict(lambda: {"target_cases": 0, "hit5": 0})
    teacher_labels = {cid: labels[cid] for cid in teacher.documents}
    for c in stress:
        exp = [str(x) for x in c.get("expect") or []]
        if not exp: continue
        cat = str(c["category"]); per = {}
        for name, v in variants.items():
            r = family_rank(rank(v, str(c["query"])), labels, exp); per[name] = r; s = sm[name][cat]
            s["target_cases"] += 1; s["top1"] += r == 1; s["hit5"] += r is not None and r <= 5; s["hit20"] += r is not None and r <= 20
        tr = family_rank(teacher.rank(str(c["query"])), teacher_labels, exp)
        o = oracle[cat]; o["target_cases"] += 1; o["hit5"] += (per["canonical"] is not None and per["canonical"] <= 5) or (tr is not None and tr <= 5)

    result = {"schema_version": 1, "status": "opened architecture diagnostic; no runtime promotion", "taxonomy_version": 31,
              "decision_question": "does frozen Gemma-4 sequence-level language improve the simplest sparse YV doc2query representation",
              "teacher": {"model": "gemma-4-26b-a4b-it", "workflow_run_id": 34189574629, "artifact_id": 10042936282, "sha256": TEACHER_SHA},
              "quality_audit": quality,
              "strict_source_attested_17": {"metrics": {n: metrics(r) for n, r in strict_ranks.items()}, "teacher_covered_cases": covered17, "canonical_plus_teacher_oracle_hit5": oracle17},
              "canonical_source_truth_333": {"metrics": {n: metrics(r) for n, r in guard.items()}, "rank_changes_from_canonical": dict(changes)},
              "opened_stress_54": {"warning": "architecture diagnosis only; not tuning or accuracy evidence", "variants": {n: dict(v) for n, v in sm.items()}, "canonical_plus_filtered_teacher_oracle": dict(oracle)},
              "rules": ["teacher generated before evaluator", "evaluation queries never enter generation/filtering/index", "do not tune on opened results", "oracle is complementarity only"]}
    out = Path(a.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)+"\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
