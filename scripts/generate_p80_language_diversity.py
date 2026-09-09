#!/usr/bin/env python3
"""Expand the frozen source-bound language-diversity policy to missing P80 occupations.

This is a coverage experiment, not a new retrieval architecture. It reuses the frozen
A593 language-diversity prompts, temperatures and validation rules. Opened 17/88
queries are never loaded. All selection comes from the frozen P80 priority report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import generate_a593_language_diversity_falsifier as g

EXPECTED_P80 = 159
EXPECTED_EXISTING = 41
EXPECTED_MISSING = 118


def tolerant_extract_json(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("no candidates")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(
        str(part.get("text") or "")
        for part in parts
        if isinstance(part, dict) and not part.get("thought")
    ).strip()
    if not text:
        raise RuntimeError("no response text")
    value = json.loads(text)
    if isinstance(value, list):
        return {"items": value}
    if isinstance(value, dict):
        return value
    raise RuntimeError("response JSON must be object or array")


g.extract_json = tolerant_extract_json


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_unusable(row: dict[str, Any], taxonomy_sha: str, *, holdout: bool) -> dict[str, Any]:
    key = "queries" if holdout else "phrases"
    keys = g.HOLDOUT_KEYS if holdout else g.TRAIN_KEYS
    return {
        "concept_id": row["concept_id"],
        "label": row["evidence"]["canonical_label"],
        "model": g.MODEL,
        key: {name: None for name in keys},
        "provenance": "P80 source-bound language-diversity expansion; insufficient canonical source evidence; no model call",
        "selection_index": row["selection_index"],
        "selection_reason": row["selection_reason"],
        "source_evidence": row["evidence"],
        "taxonomy_sha256": taxonomy_sha,
        "usable": False,
        "validation": {"rejected": {"source_fourgram": 0, "title_surface": 0, "training_fourgram": 0}, "usable_count": 0},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--priority", default="research/evaluation/v31/p80-track2-priority-coverage.json")
    ap.add_argument("--training-output", default="research/training/v31/p80-language-diversity-training-v0.jsonl")
    ap.add_argument("--holdout-output", default="research/evaluation/v31/p80-language-diversity-holdout-v0.jsonl")
    ap.add_argument("--summary-output", default="research/evaluation/v31/p80-language-diversity-generation-v0.json")
    ap.add_argument("--batch-size", type=int, default=12)
    ap.add_argument("--requests-per-minute", type=float, default=6.0)
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required")

    priority = json.loads(Path(args.priority).read_text(encoding="utf-8"))
    p80 = priority.get("p80") or {}
    existing_rows = priority.get("existing_diversified_v0") or []
    missing_rows = priority.get("missing_diversified_v0") or []
    if (int(p80.get("occupation_count", -1)), len(existing_rows), len(missing_rows)) != (EXPECTED_P80, EXPECTED_EXISTING, EXPECTED_MISSING):
        raise RuntimeError("P80 priority population drift")
    existing_ids = {str(row["concept_id"]) for row in existing_rows}
    missing_ids = [str(row["concept_id"]) for row in missing_rows]
    if len(existing_ids) != EXPECTED_EXISTING or len(set(missing_ids)) != EXPECTED_MISSING or existing_ids & set(missing_ids):
        raise RuntimeError("P80 existing/missing partition invalid")

    taxonomy_wire = g.fetch_bytes(g.TAXONOMY_URL)
    taxonomy_sha = hashlib.sha256(taxonomy_wire).hexdigest()
    if taxonomy_sha != g.expected_taxonomy_hash():
        raise RuntimeError("taxonomy source drift")
    concepts = json.loads(taxonomy_wire).get("data", {}).get("concepts") or []
    by_id = {str(c["id"]): c for c in concepts if isinstance(c, dict) and c.get("id")}
    active_ids = {cid for cid, concept in by_id.items() if concept.get("type") == "occupation-name"}
    if len(active_ids) != 2105 or any(cid not in active_ids for cid in missing_ids):
        raise RuntimeError("active YV universe/P80 identity drift")

    selected: list[dict[str, Any]] = []
    for index, source_row in enumerate(missing_rows):
        cid = str(source_row["concept_id"])
        selected.append({
            "concept_id": cid,
            "selection_index": index,
            "selection_reason": "p80_missing_diversified_v0",
            "p80_rank": int(source_row["rank"]),
            "occurrences": int(source_row["occurrences"]),
            "evidence": g.source_evidence(by_id[cid]),
        })

    rich = [row for row in selected if g.evidence_rich(row["evidence"])]
    thin = [row for row in selected if not g.evidence_rich(row["evidence"])]
    train_by_id = {row["concept_id"]: make_unusable(row, taxonomy_sha, holdout=False) for row in thin}
    holdout_by_id = {row["concept_id"]: make_unusable(row, taxonomy_sha, holdout=True) for row in thin}
    usage = {"training": [], "holdout": []}

    min_interval = 60.0 / max(args.requests_per_minute, 0.1)
    last_call = 0.0

    def rate_wait() -> None:
        nonlocal last_call
        elapsed = time.monotonic() - last_call
        if last_call and elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        last_call = time.monotonic()

    for start in range(0, len(rich), args.batch_size):
        batch = rich[start : start + args.batch_size]
        rate_wait()
        train_raw, train_usage = g.call_json(api_key, g.training_prompt(batch), temperature=0.55)
        usage["training"].append(train_usage)
        parsed_train = g.parse_batch(train_raw, batch, "phrases", g.TRAIN_KEYS)
        accepted_training: dict[str, list[str]] = {}
        for row in batch:
            cid = row["concept_id"]
            accepted, validation = g.validate_texts(row, parsed_train[cid])
            usable_count = sum(isinstance(value, str) and bool(value.strip()) for value in accepted.values())
            train_by_id[cid] = {
                "concept_id": cid,
                "label": row["evidence"]["canonical_label"],
                "model": g.MODEL,
                "phrases": accepted,
                "provenance": "same frozen source-bound A593 language-diversity training policy; P80 missing-coverage expansion; no opened 17/88",
                "selection_index": row["selection_index"],
                "selection_reason": row["selection_reason"],
                "p80_rank": row["p80_rank"],
                "occurrences": row["occurrences"],
                "source_evidence": row["evidence"],
                "taxonomy_sha256": taxonomy_sha,
                "usable": usable_count >= 3,
                "validation": {**validation, "usable_count": usable_count},
            }
            accepted_training[cid] = [value for value in accepted.values() if isinstance(value, str) and value.strip()]

        rate_wait()
        hold_raw, hold_usage = g.call_json(api_key, g.holdout_prompt(batch), temperature=0.7)
        usage["holdout"].append(hold_usage)
        parsed_holdout = g.parse_batch(hold_raw, batch, "queries", g.HOLDOUT_KEYS)
        for row in batch:
            cid = row["concept_id"]
            accepted, validation = g.validate_texts(row, parsed_holdout[cid], training_texts=accepted_training[cid])
            usable_count = sum(isinstance(value, str) and bool(value.strip()) for value in accepted.values())
            holdout_by_id[cid] = {
                "concept_id": cid,
                "label": row["evidence"]["canonical_label"],
                "model": g.MODEL,
                "queries": accepted,
                "provenance": "separate source-bound holdout call using frozen A593 language-diversity holdout policy; no opened 17/88",
                "selection_index": row["selection_index"],
                "selection_reason": row["selection_reason"],
                "p80_rank": row["p80_rank"],
                "occurrences": row["occurrences"],
                "source_evidence": row["evidence"],
                "taxonomy_sha256": taxonomy_sha,
                "usable": usable_count >= 3,
                "validation": {**validation, "usable_count": usable_count},
            }

        train_rows = [train_by_id[row["concept_id"]] for row in selected if row["concept_id"] in train_by_id]
        hold_rows = [holdout_by_id[row["concept_id"]] for row in selected if row["concept_id"] in holdout_by_id]
        write_jsonl(Path(args.training_output), train_rows)
        write_jsonl(Path(args.holdout_output), hold_rows)
        print(f"checkpoint {len(train_rows)}/{EXPECTED_MISSING}", flush=True)

    train_rows = [train_by_id[row["concept_id"]] for row in selected]
    hold_rows = [holdout_by_id[row["concept_id"]] for row in selected]
    write_jsonl(Path(args.training_output), train_rows)
    write_jsonl(Path(args.holdout_output), hold_rows)
    jointly_usable = sum(bool(t["usable"] and h["usable"]) for t, h in zip(train_rows, hold_rows, strict=True))

    summary = {
        "id": "YV-P80-language-diversity-generation-v0",
        "model": g.MODEL,
        "taxonomy_sha256": taxonomy_sha,
        "p80_occupation_count": EXPECTED_P80,
        "existing_diversified_v0_count": EXPECTED_EXISTING,
        "requested_missing_concepts": EXPECTED_MISSING,
        "source_rich_missing_concepts": len(rich),
        "source_thin_missing_concepts": len(thin),
        "jointly_usable_new_concepts": jointly_usable,
        "selection": {
            "source": str(args.priority),
            "policy": "exact frozen P80 missing-diversified-v0 partition; no outcome-based selection",
            "opened_outcomes_used": False,
        },
        "generation": {
            "training_policy": "frozen A593 language-diversity training prompt and validation",
            "holdout_policy": "frozen A593 language-diversity separate holdout prompt and validation",
            "training_temperature": 0.55,
            "holdout_temperature": 0.7,
            "batch_size": args.batch_size,
            "requests_per_minute_cap": args.requests_per_minute,
            "opened_17_88_loaded": False,
            "old_a593_teacher_phrases_sent_to_model": False,
        },
        "training_sha256": file_sha(Path(args.training_output)),
        "holdout_sha256": file_sha(Path(args.holdout_output)),
        "usage_metadata": usage,
        "evidence_warning": "Synthetic/model-authored source-bound mechanism evidence only; human confirmation remains required.",
    }
    out = Path(args.summary_output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("requested_missing_concepts", "source_rich_missing_concepts", "source_thin_missing_concepts", "jointly_usable_new_concepts")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
