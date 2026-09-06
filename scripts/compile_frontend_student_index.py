#!/usr/bin/env python3
"""Compile C0 semantic retrieval into tiny static browser assets.

The runtime representation is deliberately dumb: each normalized term maps to postings
(doc ordinal, precomputed BM25 contribution). Query time only tokenizes, looks up postings,
sums contributions and applies exact-surface dominance. No taxonomy graph, model or API is
needed at runtime.

This compiler is build-time only. It pins taxonomy bytes through source-adapters.json and
uses the frozen P80 envelopes (159 occupation-name, 316 skill identities).
"""
from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluate_p80_lexical_ablation import as_list, expected_hash, fetch, norm, tokens


def p80_ids(pareto: dict[str, Any], key: str, expected_count: int) -> list[str]:
    section = pareto[key]
    count = int(section["thresholds"]["p80"]["concept_count"])
    ids = [str(row["concept_id"]) for row in section["ranked_p95"][:count]]
    if count != expected_count or len(ids) != expected_count or len(set(ids)) != expected_count:
        raise RuntimeError(f"{key} P80 membership drift: {count}/{len(ids)} expected {expected_count}")
    return ids


def build_asset(
    *,
    product: str,
    kind: str,
    ids: list[str],
    by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    docs: dict[str, list[str]] = {}
    exact_by_doc: dict[str, set[str]] = {}
    for cid in ids:
        concept = by_id.get(cid)
        if not isinstance(concept, dict) or concept.get("type") != kind:
            raise RuntimeError(f"invalid {product} target {cid}")
        label = str(concept.get("preferred_label") or "").strip()
        definition = str(concept.get("definition") or "").strip()
        real_definition = definition if definition and norm(definition) != norm(label) else ""
        alternatives = [x for x in as_list(concept.get("alternative_labels")) if norm(x) != norm(label)]
        docs[cid] = tokens(" ".join([label, real_definition, *alternatives]))
        exact_by_doc[cid] = {norm(label), *[norm(x) for x in alternatives if norm(x)]}

    lengths = {cid: len(ts) for cid, ts in docs.items()}
    avgdl = sum(lengths.values()) / max(1, len(lengths))
    term_freq = {cid: collections.Counter(ts) for cid, ts in docs.items()}
    df: collections.Counter[str] = collections.Counter()
    for ts in docs.values():
        df.update(set(ts))

    # Same constants as the frozen C0 BM25 baseline.
    import math
    k1 = 1.2
    b = 0.75
    n = len(ids)
    idf = {term: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    ordinal = {cid: i for i, cid in enumerate(ids)}
    postings: dict[str, list[list[int | float]]] = {}
    for term in sorted(df):
        rows: list[list[int | float]] = []
        term_idf = idf[term]
        for cid in ids:
            f = term_freq[cid].get(term, 0)
            if not f:
                continue
            dl = lengths[cid]
            denom = f + k1 * (1.0 - b + b * dl / max(avgdl, 1e-9))
            contribution = term_idf * (f * (k1 + 1.0) / denom)
            rows.append([ordinal[cid], contribution])
        postings[term] = rows

    exact: dict[str, list[int]] = collections.defaultdict(list)
    for cid in ids:
        for surface in exact_by_doc[cid]:
            if surface:
                exact[surface].append(ordinal[cid])
    exact = {surface: sorted(rows) for surface, rows in sorted(exact.items())}

    return {
        "schema_version": 1,
        "engine": "compiled-c0-bm25-student",
        "product": product,
        "target_kind": kind,
        "document_ids": ids,
        "postings": postings,
        "exact_surfaces": exact,
        "scoring": {
            "runtime": "sum precomputed posting contributions for unique query tokens; +1000000 for exact canonical surface; score<=0 omitted",
            "k1": k1,
            "b": b,
            "build_time_precomputed": ["document term frequencies", "document lengths", "average document length", "document frequencies", "idf", "per-posting BM25 contribution"],
        },
    }


def compact_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--out-dir", default="artifacts/frontend-student-index-v31")
    args = ap.parse_args()

    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    url = f"https://data.jobtechdev.se/taxonomy/version/{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    body = fetch(url)
    sha = hashlib.sha256(body).hexdigest()
    expected = expected_hash(registry, "taxonomy-common-relations")
    if sha != expected:
        raise RuntimeError(f"taxonomy source drift: {sha} != {expected}")
    concepts = json.loads(body).get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    specs = {
        "yv": ("YV", "occupation-name", p80_ids(pareto, "occupation_name", 159)),
        "kv": ("KV", "skill", p80_ids(pareto, "skill", 316)),
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "taxonomy_sha256": sha,
        "architecture": {
            "ordinary_selector_semantic_bytes": 0,
            "load_point": "only after user explicitly opens description fallback",
            "runtime_dependencies": [],
            "runtime_algorithm": "tokenize -> postings lookup -> add precomputed weights -> exact-surface boost -> sort",
            "sharding": "not introduced until measured asset size justifies it",
        },
        "assets": {},
    }

    for key, (product, kind, ids) in specs.items():
        asset = build_asset(product=product, kind=kind, ids=ids, by_id=by_id)
        data = compact_bytes(asset)
        path = out_dir / f"{key}-p80-c0-index.json"
        path.write_bytes(data)
        gz = gzip.compress(data, compresslevel=9, mtime=0)
        posting_count = sum(len(rows) for rows in asset["postings"].values())
        manifest["assets"][key] = {
            "file": path.name,
            "documents": len(asset["document_ids"]),
            "terms": len(asset["postings"]),
            "postings": posting_count,
            "exact_surfaces": len(asset["exact_surfaces"]),
            "raw_bytes": len(data),
            "gzip_9_bytes": len(gz),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    manifest_bytes = compact_bytes(manifest)
    (out_dir / "manifest.json").write_bytes(manifest_bytes)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
