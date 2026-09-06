#!/usr/bin/env python3
"""Evaluate the smallest deterministic A/B/C retrieval ablation on frozen P80 truth.

A: preferred labels only
B: A + real canonical definitions
C: B + canonical alternative labels

This is intentionally a source-truth ingestion/retrieval test. It is not evidence for
natural paraphrase quality because benchmark definitions/alternative labels come from
the same canonical source used to build B/C representations.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
import urllib.request
from pathlib import Path
from typing import Any

UA = "semantic-taxonomy-search-p80-lexical-ablation/0.1"
TOKEN_RE = re.compile(r"[0-9A-Za-zÅÄÖåäöÉéÜü]+", re.UNICODE)
CONFIGS = ("A_labels", "B_plus_definitions", "C_plus_alternative_labels")


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def tokens(value: Any) -> list[str]:
    return [m.group(0).casefold() for m in TOKEN_RE.finditer(str(value or ""))]


def as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if value in (None, ""):
        return []
    text = str(value).strip()
    return [text] if text else []


def fetch(url: str, timeout: int = 240) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def expected_hash(registry: dict[str, Any], adapter_id: str) -> str:
    adapters = registry.get("adapters")
    if not isinstance(adapters, list):
        raise RuntimeError("source registry missing adapters")
    matches = [a for a in adapters if isinstance(a, dict) and a.get("id") == adapter_id]
    if len(matches) != 1:
        raise RuntimeError(f"expected one adapter {adapter_id!r}, got {len(matches)}")
    digest = matches[0].get("source_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise RuntimeError(f"adapter {adapter_id!r} has no accepted source_sha256")
    return digest


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise RuntimeError(f"non-object benchmark row in {path}")
                rows.append(row)
    return rows


class BM25:
    def __init__(self, documents: dict[str, list[str]], *, k1: float = 1.2, b: float = 0.75) -> None:
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.lengths = {cid: len(ts) for cid, ts in documents.items()}
        self.avgdl = sum(self.lengths.values()) / max(1, len(self.lengths))
        self.tf = {cid: collections.Counter(ts) for cid, ts in documents.items()}
        df: collections.Counter[str] = collections.Counter()
        for ts in documents.values():
            df.update(set(ts))
        n = len(documents)
        self.idf = {
            term: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def score(self, query_tokens: list[str], cid: str) -> float:
        tf = self.tf[cid]
        dl = self.lengths[cid]
        score = 0.0
        for term in set(query_tokens):
            f = tf.get(term, 0)
            if not f:
                continue
            idf = self.idf.get(term, 0.0)
            denom = f + self.k1 * (1.0 - self.b + self.b * dl / max(self.avgdl, 1e-9))
            score += idf * (f * (self.k1 + 1.0) / denom)
        return score

    def rank(self, query: str, labels: dict[str, str]) -> list[str]:
        q = tokens(query)
        scored = []
        nq = norm(query)
        for cid in self.documents:
            score = self.score(q, cid)
            # Preserve the privileged exact canonical-label path deterministically.
            if nq and nq == norm(labels[cid]):
                score += 1_000_000.0
            scored.append((score, cid))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [cid for _, cid in scored]


def dcg_binary(ranked: list[str], relevant: set[str], k: int) -> float:
    value = 0.0
    for i, cid in enumerate(ranked[:k], 1):
        if cid in relevant:
            value += 1.0 / math.log2(i + 1)
    return value


def evaluate(cases: list[dict[str, Any]], ranker: BM25, labels: dict[str, str]) -> dict[str, Any]:
    totals = collections.defaultdict(float)
    by_origin: dict[str, list[dict[str, float]]] = collections.defaultdict(list)
    by_stratum: dict[str, list[dict[str, float]]] = collections.defaultdict(list)
    misses: list[dict[str, Any]] = []

    for case in cases:
        relevant = {str(x["concept_id"]) for x in case["must"]}
        ranked = ranker.rank(str(case["query"]), labels)
        positions = [ranked.index(cid) + 1 for cid in relevant if cid in ranked]
        first = min(positions) if positions else len(ranked) + 1
        top1 = 1.0 if ranked and ranked[0] in relevant else 0.0
        recall10 = sum(1 for cid in ranked[:10] if cid in relevant) / max(1, len(relevant))
        mrr = 1.0 / first if first <= len(ranked) else 0.0
        ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(10, len(relevant)) + 1))
        ndcg10 = dcg_binary(ranked, relevant, 10) / ideal if ideal else 0.0
        row = {"top1": top1, "recall_at_10": recall10, "mrr": mrr, "ndcg_at_10": ndcg10}
        for key, value in row.items():
            totals[key] += value
        by_origin[str(case["query_origin"])].append(row)
        for stratum in case["strata"]:
            by_stratum[str(stratum)].append(row)
        if top1 < 1.0:
            misses.append({
                "id": case["id"],
                "query": case["query"],
                "query_origin": case["query_origin"],
                "expected": sorted(relevant),
                "top5": ranked[:5],
            })

    def aggregate(rows: list[dict[str, float]]) -> dict[str, float | int]:
        n = len(rows)
        result: dict[str, float | int] = {"cases": n}
        for key in ("top1", "recall_at_10", "mrr", "ndcg_at_10"):
            result[key] = round(sum(r[key] for r in rows) / max(1, n), 6)
        return result

    n = len(cases)
    return {
        "cases": n,
        "overall": {
            key: round(value / max(1, n), 6)
            for key, value in totals.items()
        },
        "by_query_origin": {key: aggregate(rows) for key, rows in sorted(by_origin.items())},
        "by_stratum": {key: aggregate(rows) for key, rows in sorted(by_stratum.items())},
        "top1_miss_count": len(misses),
        "top1_misses_first_50": misses[:50],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--benchmark-dir", default="research/benchmark/v31/p80-source-truth")
    ap.add_argument("--output", default="artifacts/p80-lexical-ablation-v31.json")
    args = ap.parse_args()

    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    benchmark_dir = Path(args.benchmark_dir)
    yv_cases = load_jsonl(benchmark_dir / "yv-p80-source-truth.jsonl")
    kv_cases = load_jsonl(benchmark_dir / "kv-p80-source-truth.jsonl")
    if len(yv_cases) != 333 or len(kv_cases) != 617:
        raise RuntimeError("frozen P80 benchmark count drift")

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    taxonomy_body = fetch(taxonomy_url)
    actual = hashlib.sha256(taxonomy_body).hexdigest()
    expected = expected_hash(registry, "taxonomy-common-relations")
    if actual != expected:
        raise RuntimeError(f"taxonomy source drift: expected {expected}, got {actual}")
    taxonomy = json.loads(taxonomy_body)
    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing data.concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    result: dict[str, Any] = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "benchmark": {
            "YV_cases": len(yv_cases),
            "KV_cases": len(kv_cases),
            "semantics": "source-truth P80 ingestion/retrieval benchmark; not natural-paraphrase proof",
        },
        "retrieval": {
            "algorithm": "deterministic BM25 over P80 target documents with explicit exact preferred-label dominance",
            "configs": {
                "A_labels": "preferred_label only",
                "B_plus_definitions": "A + canonical definition when non-empty/distinct from label",
                "C_plus_alternative_labels": "B + canonical alternative labels",
            },
        },
        "source": {"taxonomy_url": taxonomy_url, "taxonomy_sha256": actual},
        "products": {},
    }

    for product, cases, expected_kind in (("YV", yv_cases, "occupation-name"), ("KV", kv_cases, "skill")):
        target_ids = sorted({str(x["concept_id"]) for case in cases for x in case["must"]})
        expected_count = 159 if product == "YV" else 316
        if len(target_ids) != expected_count:
            raise RuntimeError(f"{product} target count drift: {len(target_ids)}")
        labels = {cid: str(by_id[cid].get("preferred_label") or "") for cid in target_ids}
        documents_by_config: dict[str, dict[str, list[str]]] = {key: {} for key in CONFIGS}
        for cid in target_ids:
            concept = by_id.get(cid)
            if not isinstance(concept, dict) or concept.get("type") != expected_kind:
                raise RuntimeError(f"invalid {product} target {cid}")
            label = labels[cid]
            definition = str(concept.get("definition") or "").strip()
            real_definition = definition if definition and norm(definition) != norm(label) else ""
            alternatives = [x for x in as_list(concept.get("alternative_labels")) if norm(x) != norm(label)]
            documents_by_config["A_labels"][cid] = tokens(label)
            documents_by_config["B_plus_definitions"][cid] = tokens(" ".join(x for x in (label, real_definition) if x))
            documents_by_config["C_plus_alternative_labels"][cid] = tokens(" ".join([label, real_definition, *alternatives]))

        product_result = {}
        for config in CONFIGS:
            ranker = BM25(documents_by_config[config])
            product_result[config] = evaluate(cases, ranker, labels)
        result["products"][product] = product_result

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for product in ("YV", "KV"):
        print(product)
        for config in CONFIGS:
            r = result["products"][product][config]
            print(config, r["overall"], "misses", r["top1_miss_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
