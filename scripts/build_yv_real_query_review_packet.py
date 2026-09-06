#!/usr/bin/env python3
"""Prepare a small human-review packet from high-volume unbound YV queries.

The queries are public behavioral observations. They have no selected-ID ground truth.
The current simple C configuration is used only to show reviewer candidates; those
candidates are never auto-promoted to truth.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluate_p80_lexical_ablation import BM25, as_list, expected_hash, fetch, norm, tokens


def p80_ids(pareto: dict, expected_count: int = 159) -> list[str]:
    section = pareto["occupation_name"]
    count = int(section["thresholds"]["p80"]["concept_count"])
    if count != expected_count:
        raise RuntimeError(f"unexpected YV P80 count {count}")
    ranked = section["ranked_p95"]
    ids = [str(row["concept_id"]) for row in ranked[:count]]
    if len(ids) != expected_count or len(set(ids)) != expected_count:
        raise RuntimeError("invalid YV P80 membership")
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--query-aggregate", default="research/coverage/v31/yv-query-language-aggregate.json")
    ap.add_argument("--output-dir", default="artifacts/yv-real-query-review-v31")
    args = ap.parse_args()

    if not 20 <= args.limit <= 100:
        raise RuntimeError("review packet limit must stay in [20,100]")
    version = str(args.version)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    queries = json.loads(Path(args.query_aggregate).read_text(encoding="utf-8"))

    top = queries.get("exact_text_binding", {}).get("unbound", {}).get("top_terms")
    if not isinstance(top, list) or len(top) < args.limit:
        raise RuntimeError(f"need at least {args.limit} frozen high-volume unbound terms")
    selected = top[: args.limit]
    if any(not isinstance(row, dict) or not row.get("query") or int(row.get("count") or 0) <= 0 for row in selected):
        raise RuntimeError("invalid frozen unbound query row")

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    body = fetch(taxonomy_url)
    import hashlib
    actual = hashlib.sha256(body).hexdigest()
    expected = expected_hash(registry, "taxonomy-common-relations")
    if actual != expected:
        raise RuntimeError(f"taxonomy source drift: expected {expected}, got {actual}")
    taxonomy = json.loads(body)
    concepts = taxonomy.get("data", {}).get("concepts")
    if not isinstance(concepts, list):
        raise RuntimeError("taxonomy missing concepts")
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}

    target_ids = p80_ids(pareto)
    documents: dict[str, list[str]] = {}
    exact_surfaces: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    for cid in target_ids:
        concept = by_id.get(cid)
        if not isinstance(concept, dict) or concept.get("type") != "occupation-name":
            raise RuntimeError(f"invalid P80 occupation {cid}")
        label = str(concept.get("preferred_label") or "").strip()
        definition = str(concept.get("definition") or "").strip()
        real_definition = definition if definition and norm(definition) != norm(label) else ""
        alternatives = [x for x in as_list(concept.get("alternative_labels")) if norm(x) != norm(label)]
        documents[cid] = tokens(" ".join([label, real_definition, *alternatives]))
        exact_surfaces[cid] = {norm(label), *[norm(x) for x in alternatives]}
        labels[cid] = label

    ranker = BM25(documents, exact_surfaces)
    total_corpus = int(queries["query_corpus"]["total_query_volume"])
    unbound_volume = int(queries["exact_text_binding"]["unbound"]["query_volume"])
    cumulative = 0
    rows = []
    for rank, source_row in enumerate(selected, 1):
        query = str(source_row["query"])
        count = int(source_row["count"])
        cumulative += count
        ranked = ranker.rank(query)[:5]
        rows.append({
            "id": f"yv.observed-review.{rank:03d}",
            "taxonomy_version": int(version),
            "query": query,
            "observed_count": count,
            "observed_rank_within_frozen_unbound_top_terms": rank,
            "cumulative_selected_count": cumulative,
            "share_of_all_frozen_query_volume_pct": round(100 * count / total_corpus, 4),
            "source": {
                "kind": "behavioral_query_frequency",
                "provenance": "behavioral",
                "generator_commit": queries["generator_source_commit"],
                "query_corpus_sha256": queries["query_corpus"]["zip_sha256"],
                "semantics": "observed free-text query plus aggregate frequency; no selected taxonomy ID",
            },
            "candidate_context": {
                "configuration": "C: P80 occupation preferred label + real definition + canonical alternative labels, deterministic BM25",
                "scope": "159 P80 occupation-name destinations only",
                "top5": [
                    {"rank": i, "kind": "occupation-name", "concept_id": cid, "label": labels[cid]}
                    for i, cid in enumerate(ranked, 1)
                ],
                "warning": "Candidate list is reviewer convenience only. It is not destination truth and may omit a correct P90/P95/tail occupation or a legitimate NO_MATCH outcome.",
            },
            "adjudication": {
                "status": "PENDING_HUMAN_REVIEW",
                "expected_intent": None,
                "must": [],
                "acceptable": [],
                "must_not": [],
                "review_note": "",
            },
        })

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "review-packet.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    manifest = {
        "schema_version": 1,
        "taxonomy_version": int(version),
        "status": "PENDING_HUMAN_REVIEW",
        "queries": len(rows),
        "selection_rule": f"top {args.limit} highest-frequency terms from frozen unbound YV query-language top_terms; no semantic filtering",
        "selected_query_volume": cumulative,
        "selected_share_of_all_frozen_query_volume_pct": round(100 * cumulative / total_corpus, 3),
        "selected_share_of_unbound_query_volume_pct": round(100 * cumulative / unbound_volume, 3),
        "authority_boundary": "Observed query frequency and C-ranked candidates are not labels. Human/domain review is required for SINGLE/AMBIGUOUS/NO_MATCH and MUST/ACCEPTABLE/MUST_NOT judgments.",
        "sources": {
            "query_aggregate": args.query_aggregate,
            "query_corpus_sha256": queries["query_corpus"]["zip_sha256"],
            "taxonomy_sha256": actual,
            "pareto": args.pareto,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# YV high-volume observed-query review packet",
        "",
        f"**Status:** PENDING HUMAN REVIEW — {len(rows)} queries",
        "",
        f"These queries represent **{manifest['selected_share_of_all_frozen_query_volume_pct']}% of all frozen query volume** and **{manifest['selected_share_of_unbound_query_volume_pct']}% of unbound volume**.",
        "",
        "No row has an automatic destination label. The five candidates are only the current simple P80 configuration's suggestions.",
        "",
        "| rank | query | observed count | current top candidate |",
        "|---:|---|---:|---|",
    ]
    for row in rows:
        top1 = row["candidate_context"]["top5"][0]
        lines.append(f"| {row['observed_rank_within_frozen_unbound_top_terms']} | `{row['query']}` | {row['observed_count']:,} | {top1['label']} |")
    (out / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
