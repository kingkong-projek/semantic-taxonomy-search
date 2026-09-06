#!/usr/bin/env python3
"""Prepare a small human-review packet from high-volume unbound YV queries.

The queries are public behavioral observations. They have no selected-ID ground truth.
The current simple C configuration is used only to show reviewer candidates; those
candidates are never auto-promoted to truth. Zero lexical evidence yields abstention,
not an arbitrary nearest candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
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


def top_unbound_from_generator(source_dir: Path, version: str, expected_zip_sha256: str, limit: int) -> tuple[list[dict], dict]:
    zip_path = source_dir / "data/sokningar-platsbanken.json.zip"
    zip_bytes = zip_path.read_bytes()
    actual_zip_sha = hashlib.sha256(zip_bytes).hexdigest()
    if actual_zip_sha != expected_zip_sha256:
        raise RuntimeError(f"query corpus hash drift: expected {expected_zip_sha256}, got {actual_zip_sha}")
    with zipfile.ZipFile(zip_path) as zf:
        names = [name for name in zf.namelist() if name.endswith(".json")]
        if len(names) != 1:
            raise RuntimeError(f"expected one JSON in query ZIP, got {names}")
        corpus = json.load(zf.open(names[0]))
    terms = corpus.get("search_terms")
    if not isinstance(terms, dict):
        raise RuntimeError("query corpus missing search_terms")
    terms = {str(query): int(count) for query, count in terms.items()}
    if sum(terms.values()) != int(corpus.get("total_search_terms") or -1):
        raise RuntimeError("query corpus total mismatch")

    yv = json.loads((source_dir / f"output/v1/yrkesvaljaren-t{version}.json").read_text(encoding="utf-8"))
    yv_rows = yv.get("data")
    if not isinstance(yv_rows, list):
        raise RuntimeError("pinned YV output missing data")
    admitted_labels = {
        str(row["preferred_label"]).casefold()
        for row in yv_rows
        if isinstance(row, dict) and row.get("preferred_label")
    }
    many = json.loads((source_dir / f"data/jobbtitlar-mappad-till-för-många-yb-t{version}.json").read_text(encoding="utf-8"))
    redundant = json.loads((source_dir / f"data/jobbtitlar-del-av-yb-t{version}.json").read_text(encoding="utf-8"))
    excluded_labels = {str(x).casefold() for x in many} | {str(x).casefold() for x in redundant}

    unbound = [
        {"query": query, "count": count}
        for query, count in terms.items()
        if query.casefold() not in admitted_labels and query.casefold() not in excluded_labels
    ]
    unbound.sort(key=lambda row: (-row["count"], row["query"]))
    if len(unbound) < limit:
        raise RuntimeError(f"only {len(unbound)} unbound terms available")
    return unbound[:limit], {
        "distinct_terms": len(terms),
        "total_query_volume": sum(terms.values()),
        "unbound_distinct_terms": len(unbound),
        "unbound_query_volume": sum(row["count"] for row in unbound),
        "start_date": corpus.get("start_date"),
        "end_date": corpus.get("end_date"),
        "zip_sha256": actual_zip_sha,
    }


def positive_rank(ranker: BM25, query: str, exact_surfaces: dict[str, set[str]]) -> list[tuple[str, float]]:
    query_tokens = tokens(query)
    normalized = norm(query)
    scored: list[tuple[str, float]] = []
    for cid in ranker.documents:
        score = ranker.score(query_tokens, cid)
        if normalized and normalized in exact_surfaces[cid]:
            score += 1_000_000.0
        if score > 0.0:
            scored.append((cid, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--source-dir", required=True, help="Pinned Yrkesväljaren generator checkout")
    ap.add_argument("--registry", default="research/coverage/source-adapters.json")
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--query-aggregate", default="research/coverage/v31/yv-query-language-aggregate.json")
    ap.add_argument("--output-dir", default="artifacts/yv-real-query-review-v31")
    args = ap.parse_args()

    if not 20 <= args.limit <= 100:
        raise RuntimeError("review packet limit must stay in [20,100]")
    version = str(args.version)
    source_dir = Path(args.source_dir)
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    queries = json.loads(Path(args.query_aggregate).read_text(encoding="utf-8"))
    source_commit = (source_dir / "SOURCE_COMMIT.txt").read_text(encoding="utf-8").strip()
    if source_commit != queries["generator_source_commit"]:
        raise RuntimeError(f"generator commit mismatch: {source_commit}")

    selected, corpus_stats = top_unbound_from_generator(
        source_dir, version, str(queries["query_corpus"]["zip_sha256"]), args.limit
    )
    if corpus_stats["total_query_volume"] != int(queries["query_corpus"]["total_query_volume"]):
        raise RuntimeError("frozen query total drift")
    if corpus_stats["unbound_distinct_terms"] != int(queries["exact_text_binding"]["unbound"]["distinct_terms"]):
        raise RuntimeError("frozen unbound distinct-term count drift")
    if corpus_stats["unbound_query_volume"] != int(queries["exact_text_binding"]["unbound"]["query_volume"]):
        raise RuntimeError("frozen unbound query-volume drift")

    taxonomy_url = (
        "https://data.jobtechdev.se/taxonomy/version/"
        f"{version}/query/concepts-and-common-relations/concepts-and-common-relations.json"
    )
    body = fetch(taxonomy_url)
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
    total_corpus = corpus_stats["total_query_volume"]
    unbound_volume = corpus_stats["unbound_query_volume"]
    cumulative = 0
    rows = []
    no_evidence_count = 0
    no_evidence_volume = 0
    for rank, source_row in enumerate(selected, 1):
        query = str(source_row["query"])
        count = int(source_row["count"])
        cumulative += count
        scored = positive_rank(ranker, query, exact_surfaces)[:5]
        if not scored:
            no_evidence_count += 1
            no_evidence_volume += count
        rows.append({
            "id": f"yv.observed-review.{rank:03d}",
            "taxonomy_version": int(version),
            "query": query,
            "observed_count": count,
            "observed_rank_within_unbound_population": rank,
            "cumulative_selected_count": cumulative,
            "share_of_all_frozen_query_volume_pct": round(100 * count / total_corpus, 4),
            "source": {
                "kind": "behavioral_query_frequency",
                "provenance": "behavioral",
                "generator_commit": source_commit,
                "query_corpus_sha256": corpus_stats["zip_sha256"],
                "semantics": "observed free-text query plus aggregate frequency; no selected taxonomy ID",
            },
            "candidate_context": {
                "configuration": "C: P80 occupation preferred label + real definition + canonical alternative labels, deterministic BM25",
                "scope": "159 P80 occupation-name destinations only",
                "positive_lexical_evidence": bool(scored),
                "simple_configuration_would_abstain": not bool(scored),
                "top5": [
                    {"rank": i, "kind": "occupation-name", "concept_id": cid, "label": labels[cid], "score": round(score, 6)}
                    for i, (cid, score) in enumerate(scored, 1)
                ],
                "warning": "Candidate list is reviewer convenience only. Zero evidence yields no candidate. Positive candidates are still not destination truth and may omit a correct P90/P95/tail occupation or a legitimate NO_MATCH outcome.",
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
        "schema_version": 3,
        "taxonomy_version": int(version),
        "status": "PENDING_HUMAN_REVIEW",
        "queries": len(rows),
        "selection_rule": f"top {args.limit} highest-frequency unbound terms recomputed from pinned Yrkesväljaren query corpus; no semantic filtering",
        "selected_query_volume": cumulative,
        "selected_share_of_all_frozen_query_volume_pct": round(100 * cumulative / total_corpus, 3),
        "selected_share_of_unbound_query_volume_pct": round(100 * cumulative / unbound_volume, 3),
        "simple_C_zero_evidence_queries": no_evidence_count,
        "simple_C_zero_evidence_query_volume": no_evidence_volume,
        "simple_C_zero_evidence_share_of_selected_volume_pct": round(100 * no_evidence_volume / cumulative, 3),
        "authority_boundary": "Observed query frequency and C-ranked candidates are not labels. Zero lexical evidence explicitly abstains. Human/domain review is required for SINGLE/AMBIGUOUS/NO_MATCH and MUST/ACCEPTABLE/MUST_NOT judgments.",
        "sources": {
            "generator_commit": source_commit,
            "query_aggregate": args.query_aggregate,
            "query_corpus_sha256": corpus_stats["zip_sha256"],
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
        f"The current simple C configuration has **zero lexical evidence for {no_evidence_count}/{len(rows)} queries**, representing **{manifest['simple_C_zero_evidence_share_of_selected_volume_pct']}%** of this packet's volume; those rows abstain instead of returning an arbitrary nearest occupation.",
        "",
        "No row has an automatic destination label. Positive candidates are only the current simple P80 configuration's suggestions.",
        "",
        "| rank | query | observed count | simple C |",
        "|---:|---|---:|---|",
    ]
    for row in rows:
        candidates = row["candidate_context"]["top5"]
        current = candidates[0]["label"] if candidates else "ABSTAIN — no lexical evidence"
        lines.append(f"| {row['observed_rank_within_unbound_population']} | `{row['query']}` | {row['observed_count']:,} | {current} |")
    (out / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
