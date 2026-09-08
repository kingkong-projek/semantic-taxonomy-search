#!/usr/bin/env python3
"""A593 corpus-internal diagnostic: preserve raw tokens and add morphology features.

No opened 17/88 query is used here. Candidate is intentionally parameter-free:
for every raw Swedish token whose Snowball stem differs, append one namespaced
`__svstem_<stem>` feature. Raw tokens are never removed or reweighted.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from evaluate_gemma_a593_phrase_representation import (
    EXPECTED_PHRASES_PER_ROW,
    evaluate_flattened,
    false_positive_hubs,
    load_teacher,
    paired_changes,
    raw_tokens,
    stemmed_tokens,
    swedish_snowball_stem,
)


def raw_plus_stem_tokens(value: str) -> list[str]:
    raw = raw_tokens(value)
    extra = []
    for token in raw:
        stem = swedish_snowball_stem(token)
        if stem != token:
            extra.append(f"__svstem_{stem}")
    return [*raw, *extra]


def confusion_pairs(rows: list[dict], limit: int = 50) -> list[dict]:
    counts: collections.Counter[tuple[str, str, str, str]] = collections.Counter()
    for row in rows:
        if row["top1_concept_id"] == row["concept_id"]:
            continue
        counts[(
            row["concept_id"], row["label"], row["top1_concept_id"], row["top1_label"]
        )] += 1
    return [
        {
            "target_concept_id": target_id,
            "target_label": target_label,
            "wrong_top1_concept_id": wrong_id,
            "wrong_top1_label": wrong_label,
            "count": count,
        }
        for (target_id, target_label, wrong_id, wrong_label), count in counts.most_common(limit)
    ]


def strip_rows(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "rows"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--output", default="artifacts/a593-raw-plus-stem.json")
    args = ap.parse_args()

    cids, labels, phrases = load_teacher(Path(args.teacher))
    raw = evaluate_flattened(cids, labels, phrases, raw_tokens)
    snowball = evaluate_flattened(cids, labels, phrases, stemmed_tokens)
    raw_plus_stem = evaluate_flattened(cids, labels, phrases, raw_plus_stem_tokens)

    result = {
        "schema_version": 1,
        "status": "A593 corpus-internal morphology diagnostic; no opened evaluation queries used",
        "candidate": {
            "id": "YV-A593-raw-plus-namespaced-snowball-v0",
            "definition": (
                "preserve every raw token; for a token whose Swedish Snowball stem differs, "
                "append exactly one namespaced __svstem_<stem> feature; no weights or tuned parameters"
            ),
            "selection_boundary": "candidate definition frozen before any opened 17/88 replay",
        },
        "corpus": {
            "concepts": len(cids),
            "phrases": len(cids) * EXPECTED_PHRASES_PER_ROW,
            "cases": len(cids) * EXPECTED_PHRASES_PER_ROW,
            "folds": EXPECTED_PHRASES_PER_ROW,
            "holdout": "same frozen prompt-slot leave-one-out protocol as prior A593 representation diagnostic",
        },
        "variants": {
            "flattened_raw": strip_rows(raw),
            "flattened_snowball_sv": strip_rows(snowball),
            "flattened_raw_plus_namespaced_snowball": strip_rows(raw_plus_stem),
        },
        "paired_vs_flattened_raw": {
            "flattened_snowball_sv": paired_changes(raw["rows"], snowball["rows"]),
            "flattened_raw_plus_namespaced_snowball": paired_changes(raw["rows"], raw_plus_stem["rows"]),
        },
        "false_positive_hubs": {
            "flattened_raw": false_positive_hubs(raw["rows"]),
            "flattened_raw_plus_namespaced_snowball": false_positive_hubs(raw_plus_stem["rows"]),
        },
        "top_confusion_pairs": {
            "flattened_raw": confusion_pairs(raw["rows"]),
            "flattened_raw_plus_namespaced_snowball": confusion_pairs(raw_plus_stem["rows"]),
        },
        "interpretation_guard": (
            "All cases are model-authored from the frozen teacher corpus. This experiment may select "
            "representation mechanics and mine hard negatives, but cannot establish user accuracy."
        ),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "raw": result["variants"]["flattened_raw"]["overall"],
        "snowball": result["variants"]["flattened_snowball_sv"]["overall"],
        "raw_plus_stem": result["variants"]["flattened_raw_plus_namespaced_snowball"]["overall"],
        "paired_raw_plus_stem": result["paired_vs_flattened_raw"]["flattened_raw_plus_namespaced_snowball"],
        "top_confusions_raw_plus_stem": result["top_confusion_pairs"]["flattened_raw_plus_namespaced_snowball"][:15],
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
