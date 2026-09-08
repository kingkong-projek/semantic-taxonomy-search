#!/usr/bin/env python3
"""Mine A593 hard-negative/confusion evidence from teacher phrases only.

The audit is deliberately mechanical and uses no opened 17/88 queries. It replays the
raw flattened 8-fold prompt-slot holdout and describes the most frequent wrong-Top1
pairs so later work can distinguish genuine ambiguity, teacher boundary collapse and
retrieval hubs without tuning on evaluation cases.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from evaluate_gemma_a593_phrase_representation import (
    evaluate_flattened,
    load_teacher,
    raw_tokens,
)


def token_set(values: list[str]) -> set[str]:
    return {token for value in values for token in raw_tokens(value)}


def norm_phrase(value: str) -> str:
    return " ".join(raw_tokens(value))


def jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return 0.0 if not union else len(a & b) / len(union)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--output", default="artifacts/a593-confusion-audit.json")
    ap.add_argument("--limit", type=int, default=75)
    args = ap.parse_args()

    cids, labels, phrases = load_teacher(Path(args.teacher))
    raw = evaluate_flattened(cids, labels, phrases, raw_tokens)

    directed: collections.Counter[tuple[str, str]] = collections.Counter()
    hub: collections.Counter[str] = collections.Counter()
    for row in raw["rows"]:
        target = row["concept_id"]
        wrong = row["top1_concept_id"]
        if target == wrong:
            continue
        directed[(target, wrong)] += 1
        hub[wrong] += 1

    pairs = []
    for (target, wrong), count in directed.most_common(args.limit):
        reverse = directed.get((wrong, target), 0)
        target_norm = [norm_phrase(p) for p in phrases[target]]
        wrong_norm = [norm_phrase(p) for p in phrases[wrong]]
        target_set = set(target_norm)
        wrong_set = set(wrong_norm)
        exact_shared = sorted(target_set & wrong_set)
        same_slot = [
            i for i, (left, right) in enumerate(zip(target_norm, wrong_norm, strict=True))
            if left == right
        ]
        target_tokens = token_set(phrases[target])
        wrong_tokens = token_set(phrases[wrong])
        unique_target = sorted(target_tokens - wrong_tokens)
        unique_wrong = sorted(wrong_tokens - target_tokens)
        pairs.append({
            "target_concept_id": target,
            "target_label": labels[target],
            "wrong_top1_concept_id": wrong,
            "wrong_top1_label": labels[wrong],
            "wrong_top1_count": count,
            "reverse_wrong_top1_count": reverse,
            "mutual_confusion": reverse > 0,
            "wrong_concept_global_false_top1_hub_count": hub[wrong],
            "exact_shared_phrase_count": len(exact_shared),
            "exact_shared_phrases": exact_shared,
            "same_prompt_slot_exact_phrase_count": len(same_slot),
            "same_prompt_slots": same_slot,
            "teacher_token_jaccard": round(jaccard(target_tokens, wrong_tokens), 6),
            "target_unique_tokens": unique_target,
            "wrong_unique_tokens": unique_wrong,
            "target_phrases": phrases[target],
            "wrong_phrases": phrases[wrong],
        })

    result = {
        "schema_version": 1,
        "status": "A593 corpus-internal confusion audit; no opened evaluation queries used",
        "corpus": {
            "concepts": len(cids),
            "teacher_phrases": sum(len(v) for v in phrases.values()),
            "holdout_cases": len(raw["rows"]),
        },
        "raw_holdout_overall": raw["overall"],
        "false_top1_hubs": [
            {"concept_id": cid, "label": labels[cid], "false_top1_count": count}
            for cid, count in hub.most_common(50)
        ],
        "top_directed_confusion_pairs": pairs,
        "mechanical_interpretation": {
            "mutual_confusion": "both concepts are observed as wrong Top1 for the other in independent prompt-slot holdouts",
            "exact_shared_phrase": "teacher emitted literally the same normalized description for both identities",
            "teacher_token_jaccard": "union-token overlap across all eight teacher phrases; descriptive only, not a thresholded decision",
        },
        "guard": (
            "Do not label a pair as true user ambiguity or tune production behavior from these model-authored cases alone. "
            "Use them as hard-negative/teacher-quality evidence; opened 17/88 queries remain excluded from mining."
        ),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "raw_holdout": result["raw_holdout_overall"],
        "top_hubs": result["false_top1_hubs"][:10],
        "top_pairs": [
            {
                "target": row["target_label"],
                "wrong": row["wrong_top1_label"],
                "count": row["wrong_top1_count"],
                "reverse": row["reverse_wrong_top1_count"],
                "shared_phrases": row["exact_shared_phrase_count"],
                "token_jaccard": row["teacher_token_jaccard"],
            }
            for row in pairs[:20]
        ],
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
