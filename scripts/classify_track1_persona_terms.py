#!/usr/bin/env python3
"""Classify exploratory persona terms at the Track-1 / Track-2 boundary.

The classifier deliberately does not perform semantic similarity. It asks only:
- is the query itself an active canonical preferred/alternative/hidden label?;
- does the query literally contain one of those authoritative surfaces?;
- is the query itself a literal substring of a longer authoritative surface, as
  current lexical selectors already support for inputs such as ``YKB``?

That is enough to separate already-attested lexical/compositional reachability from
cases for which canonical vocabulary alone supplies no literal bridge. The final
class is only a candidate for Track 2: absence of literal evidence does not prove
that embeddings or any other semantic model are required.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from deprecated_compatibility_coverage import as_strings, graphql

CASES = [
    {"id": "persona.frontend-developer", "product": "YV", "query": "frontend developer", "types": ["occupation-name", "job-title"]},
    {"id": "persona.projektkoordinator", "product": "YV", "query": "projektkoordinator", "types": ["occupation-name", "job-title"]},
    {"id": "persona.kora-motviktstruck", "product": "KV", "query": "köra motviktstruck", "types": ["skill"]},
    {"id": "persona.svetsa-rostfritt", "product": "KV", "query": "svetsa rostfritt", "types": ["skill"]},
    {"id": "persona.ta-blodprov", "product": "KV", "query": "ta blodprov", "types": ["skill"]},
    {"id": "persona.sjukskoterskelegitimation", "product": "KV", "query": "sjuksköterskelegitimation", "types": ["skill"]},
    {"id": "control.ykb", "product": "KV", "query": "YKB", "types": ["skill"]},
]


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).casefold().strip()
    return re.sub(r"\s+", " ", text)


def token_count(value: str) -> int:
    return len(re.findall(r"[0-9a-zåäö+#]+", norm(value)))


def fetch_active(version: str, ctype: str) -> list[dict[str, Any]]:
    query = f'''query PersonaVocabularyBoundary {{
      concepts(type: "{ctype}", version: "{version}", include_deprecated: false, limit: 50000) {{
        id preferred_label type deprecated alternative_labels hidden_labels
      }}
    }}'''
    _, doc, _ = graphql(query)
    rows = (doc.get("data") or {}).get("concepts")
    if not isinstance(rows, list):
        raise RuntimeError(f"GraphQL missing concepts for {ctype}")
    return [r for r in rows if isinstance(r, dict) and r.get("id") and r.get("deprecated") is not True]


def surfaces(concept: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    preferred = str(concept.get("preferred_label") or "").strip()
    if preferred:
        out.append({"surface": preferred, "kind": "preferred_label"})
    for field, kind in (("alternative_labels", "alternative_label"), ("hidden_labels", "hidden_label")):
        for value in as_strings(concept.get(field)):
            out.append({"surface": value, "kind": kind})
    seen = set()
    unique = []
    for row in out:
        key = (norm(row["surface"]), row["kind"])
        if not key[0] or key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="31")
    ap.add_argument("--output", default="artifacts/track1-persona-vocabulary-boundary-v31.json")
    args = ap.parse_args()

    concepts_by_type = {ctype: fetch_active(str(args.version), ctype) for ctype in ("occupation-name", "job-title", "skill")}
    result_cases = []

    for case in CASES:
        nq = norm(case["query"])
        exact = []
        query_contains_surface = []
        surface_contains_query = []
        for ctype in case["types"]:
            for concept in concepts_by_type[ctype]:
                for row in surfaces(concept):
                    ns = norm(row["surface"])
                    item = {
                        "concept_id": str(concept["id"]),
                        "concept_type": str(concept.get("type") or ctype),
                        "preferred_label": concept.get("preferred_label"),
                        "matched_surface": row["surface"],
                        "surface_kind": row["kind"],
                    }
                    if ns == nq:
                        exact.append(item)
                    elif len(ns) >= 4 and ns in nq and token_count(ns) >= 1:
                        query_contains_surface.append(item)
                    elif len(nq) >= 3 and nq in ns and token_count(nq) >= 1:
                        surface_contains_query.append(item)

        def uniq(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            seen = set()
            out = []
            for r in rows:
                key = (r["concept_id"], norm(r["matched_surface"]), r["surface_kind"])
                if key not in seen:
                    seen.add(key)
                    out.append(r)
            return out

        exact = uniq(exact)
        query_contains_surface = uniq(query_contains_surface)
        surface_contains_query = uniq(surface_contains_query)
        if exact:
            boundary = "TRACK1_AUTHORITATIVE_EXACT_SURFACE"
        elif query_contains_surface or surface_contains_query:
            boundary = "TRACK1_LEXICAL_COMPOSITION_CANDIDATE"
        else:
            boundary = "TRACK2_MEANING_INFERENCE_CANDIDATE"

        result_cases.append({
            **{k: v for k, v in case.items() if k != "types"},
            "normalized_query": nq,
            "boundary_class": boundary,
            "exact_authoritative_surfaces": exact,
            "query_contains_authoritative_surfaces": query_contains_surface,
            "authoritative_surfaces_containing_query": surface_contains_query,
            "note": "absence of exact or bidirectional literal containment does not prove a semantic mapping or model is required; it only means current canonical vocabulary supplies no direct literal bridge",
        })

    result = {
        "schema_version": 2,
        "taxonomy_version": int(args.version),
        "track": "1-current-yv-kv-findability",
        "method": "exact plus bidirectional literal containment over active preferred/alternative/hidden taxonomy surfaces only; no semantic similarity",
        "cases": result_cases,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
