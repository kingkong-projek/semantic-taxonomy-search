#!/usr/bin/env python3
"""Generate the next deterministic batch of Gemma YV teacher language.

This extends the frozen A-sequence corpus without looking at opened evaluation outcomes.
Ordering is exactly the existing Pareto-ranked occupation list used by the first pilot;
`--start-index` selects a contiguous slice. Prompt/model/API behavior is imported from
`generate_gemma4_yv_teacher_pilot.py` so the teacher contract stays unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import generate_gemma4_yv_teacher_pilot as pilot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pareto", default="research/coverage/v31/pareto-demand-aggregate.json")
    ap.add_argument("--output", default="artifacts/gemma4-yv-teacher-batch.jsonl")
    ap.add_argument("--summary", default="artifacts/gemma4-yv-teacher-batch-summary.json")
    ap.add_argument("--start-index", type=int, required=True)
    ap.add_argument("--cases", type=int, required=True)
    ap.add_argument("--requests-per-minute", type=float, default=3.0)
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    if args.start_index < 0:
        raise RuntimeError("--start-index must be >= 0")
    if not (1 <= args.cases <= 1000):
        raise RuntimeError("--cases must be between 1 and 1000")
    if not (0.2 <= args.requests_per_minute <= 6.0):
        raise RuntimeError("RPM must stay between 0.2 and 6.0")

    taxonomy = pilot.fetch_json(pilot.TAXONOMY_URL)
    concepts = taxonomy.get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    pareto = json.loads(Path(args.pareto).read_text(encoding="utf-8"))
    ranked = pareto.get("occupation_name", {}).get("ranked_p95") or []

    ordered: list[dict[str, Any]] = []
    for row in ranked:
        concept = by_id.get(str(row.get("concept_id") or ""))
        if concept and concept.get("type") == "occupation-name":
            ordered.append(concept)

    end_index = args.start_index + args.cases
    selected = ordered[args.start_index:end_index]
    if len(selected) != args.cases:
        raise RuntimeError(
            f"requested slice {args.start_index}:{end_index}, but only {len(ordered)} ordered occupations exist"
        )

    out = Path(args.output)
    summary_path = Path(args.summary)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    interval = 60.0 / args.requests_per_minute
    rows: list[dict[str, Any]] = []
    failed: list[dict[str, str | int]] = []
    started = time.time()

    for local_index, concept in enumerate(selected):
        if local_index:
            time.sleep(interval)
        source_index = args.start_index + local_index
        label = str(concept.get("preferred_label") or "").strip()
        print(
            f"Gemma teacher source-index {source_index} "
            f"({local_index + 1}/{len(selected)}): {label}",
            flush=True,
        )
        try:
            phrases, usage = pilot.call_gemma(api_key, pilot.prompt_for(concept))
        except RuntimeError as exc:
            failed.append(
                {
                    "source_index": source_index,
                    "concept_id": str(concept["id"]),
                    "label": label,
                    "error": str(exc),
                }
            )
            print(f"skipping {label} after retries: {exc}", flush=True)
            continue

        rows.append(
            {
                "source_index": source_index,
                "concept_id": str(concept["id"]),
                "label": label,
                "model": pilot.MODEL,
                "phrases": phrases,
                "usage_metadata": usage,
                "provenance": (
                    "Gemma 4 generateContent JSON-MIME teacher; public taxonomy input only; "
                    "contiguous frozen-order A corpus batch"
                ),
            }
        )
        # Checkpoint after every successful concept so a partial run remains recoverable.
        out.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    raw = out.read_bytes() if out.exists() else b""
    summary = {
        "status": "exploratory teacher corpus generation only",
        "model": pilot.MODEL,
        "teacher_contract": "same prompt/model/temperature/API behavior as frozen 150-case pilot",
        "selection": {
            "ordering": "pareto-demand-aggregate occupation_name.ranked_p95, active occupation-name only",
            "start_index_zero_based": args.start_index,
            "requested_cases": args.cases,
            "end_index_exclusive": end_index,
        },
        "successful_cases": len(rows),
        "failed_cases": len(failed),
        "failures": failed,
        "requests_per_minute_cap": args.requests_per_minute,
        "elapsed_seconds": round(time.time() - started, 3),
        "output": str(out),
        "output_sha256": hashlib.sha256(raw).hexdigest(),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
