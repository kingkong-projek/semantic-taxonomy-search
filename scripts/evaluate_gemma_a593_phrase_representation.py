#!/usr/bin/env python3
"""Corpus-internal A593 representation diagnostic.

Uses only the frozen 593-concept Gemma teacher corpus. No opened 17/88 queries
participate.

Each of the eight prompt slots is held out in turn for every concept. The held-out
phrase is used as the query and the other seven phrases are the retrieval corpus.
This yields 8 * 593 = 4,744 leakage-free, model-authored architecture cases.

Variants:
- flattened_raw: seven remaining phrases concatenated into one BM25 document/concept.
- phrase_max_raw: seven remaining phrases kept as mini-documents; concept score is the
  best single phrase score.
- flattened_snowball_sv: same as flattened_raw after deterministic Swedish Snowball
  stemming.

This is architecture/training evidence, not independent user-accuracy evidence.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import re
import statistics
from pathlib import Path
from typing import Callable

TOKEN_RE = re.compile(r"[0-9A-Za-zÅÄÖåäöÉéÜü]+", re.UNICODE)
EXPECTED_ROWS = 593
EXPECTED_PHRASES_PER_ROW = 8
SLOT_NAMES = (
    "explicit_task_1",
    "explicit_task_2",
    "colloquial_1",
    "colloquial_2",
    "indirect_distinguishing",
    "telegram_noisy",
    "tool_method_responsibility",
    "cautious_boundary",
)

# Swedish Snowball stemmer, following the public Snowball algorithm.
_VOWELS = set("aeiouyåäö")
_S_ENDING = set("bcdfghjklmnoprtvy")
_STEP1 = (
    "heterna", "hetens", "heter", "heten", "anden", "arnas", "ernas", "ornas",
    "andes", "andet", "arens", "arna", "erna", "orna", "ande", "arne", "aste",
    "aren", "ades", "erns", "ade", "are", "ern", "ens", "het", "ast", "ad",
    "en", "ar", "er", "or", "as", "es", "at", "a", "e", "s",
)
_STEP2 = ("dd", "gd", "nn", "dt", "gt", "kt", "tt")
_STEP3 = ("fullt", "löst", "els", "lig", "ig")


def raw_tokens(value: str) -> list[str]:
    return [m.group(0).casefold() for m in TOKEN_RE.finditer(value)]


def swedish_snowball_stem(word: str) -> str:
    word = word.casefold()
    r1_start = len(word)
    for i in range(1, len(word)):
        if word[i] not in _VOWELS and word[i - 1] in _VOWELS:
            r1_start = max(i + 1, 3)
            break

    r1 = word[r1_start:]
    for suffix in _STEP1:
        if r1.endswith(suffix):
            if suffix == "s":
                if len(word) >= 2 and word[-2] in _S_ENDING:
                    word = word[:-1]
            else:
                word = word[:-len(suffix)]
            break

    r1 = word[r1_start:] if r1_start <= len(word) else ""
    for suffix in _STEP2:
        if r1.endswith(suffix):
            word = word[:-1]
            break

    r1 = word[r1_start:] if r1_start <= len(word) else ""
    for suffix in _STEP3:
        if r1.endswith(suffix):
            if suffix in ("els", "lig", "ig"):
                word = word[:-len(suffix)]
            else:
                word = word[:-1]
            break
    return word


def stemmed_tokens(value: str) -> list[str]:
    return [swedish_snowball_stem(token) for token in raw_tokens(value)]


class BM25:
    def __init__(self, documents: dict[str, list[str]], *, k1: float = 1.2, b: float = 0.75) -> None:
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.lengths = {doc_id: len(ts) for doc_id, ts in documents.items()}
        self.avgdl = sum(self.lengths.values()) / max(1, len(self.lengths))
        self.tf = {doc_id: collections.Counter(ts) for doc_id, ts in documents.items()}
        df: collections.Counter[str] = collections.Counter()
        for ts in documents.values():
            df.update(set(ts))
        n = len(documents)
        self.idf = {
            term: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def score(self, query_tokens: list[str], doc_id: str) -> float:
        tf = self.tf[doc_id]
        dl = self.lengths[doc_id]
        total = 0.0
        for term in set(query_tokens):
            f = tf.get(term, 0)
            if not f:
                continue
            idf = self.idf.get(term, 0.0)
            denom = f + self.k1 * (1.0 - self.b + self.b * dl / max(self.avgdl, 1e-9))
            total += idf * (f * (self.k1 + 1.0) / denom)
        return total


def load_teacher(path: Path) -> tuple[list[str], dict[str, str], dict[str, list[str]]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != EXPECTED_ROWS:
        raise RuntimeError(f"teacher row drift: {len(rows)} != {EXPECTED_ROWS}")
    labels: dict[str, str] = {}
    phrases: dict[str, list[str]] = {}
    for row in rows:
        cid = str(row.get("concept_id") or "")
        label = str(row.get("label") or "")
        values = [str(x).strip() for x in row.get("phrases") or [] if str(x).strip()]
        if not cid or cid in phrases:
            raise RuntimeError(f"missing/duplicate concept id: {cid!r}")
        if len(values) != EXPECTED_PHRASES_PER_ROW:
            raise RuntimeError(f"phrase count drift for {cid}: {len(values)}")
        labels[cid] = label
        phrases[cid] = values
    return sorted(phrases), labels, phrases


def summarize_ranks(ranks: list[int]) -> dict[str, int | float]:
    ordered = sorted(ranks)
    n = len(ranks)
    p90 = ordered[max(0, math.ceil(0.90 * n) - 1)]
    return {
        "cases": n,
        "top1_count": sum(rank == 1 for rank in ranks),
        "top1_rate": round(sum(rank == 1 for rank in ranks) / n, 6),
        "hit_at_5_count": sum(rank <= 5 for rank in ranks),
        "hit_at_5_rate": round(sum(rank <= 5 for rank in ranks) / n, 6),
        "mrr": round(sum(1.0 / rank for rank in ranks) / n, 6),
        "median_rank": statistics.median(ranks),
        "p90_rank": p90,
    }


def evaluate_flattened(
    cids: list[str],
    labels: dict[str, str],
    phrases: dict[str, list[str]],
    tokenizer: Callable[[str], list[str]],
) -> dict:
    all_rows: list[dict] = []
    per_slot: dict[str, dict] = {}
    for holdout in range(EXPECTED_PHRASES_PER_ROW):
        documents = {
            cid: tokenizer(" ".join(p for i, p in enumerate(phrases[cid]) if i != holdout))
            for cid in cids
        }
        ranker = BM25(documents)
        slot_rows = []
        for cid in cids:
            query = phrases[cid][holdout]
            query_tokens = tokenizer(query)
            scored = [(ranker.score(query_tokens, candidate), candidate) for candidate in cids]
            scored.sort(key=lambda item: (-item[0], item[1]))
            ranked = [candidate for _, candidate in scored]
            rank = ranked.index(cid) + 1
            row = {
                "slot": holdout,
                "slot_name": SLOT_NAMES[holdout],
                "concept_id": cid,
                "label": labels[cid],
                "query": query,
                "rank": rank,
                "top1_concept_id": ranked[0],
                "top1_label": labels[ranked[0]],
            }
            slot_rows.append(row)
            all_rows.append(row)
        per_slot[SLOT_NAMES[holdout]] = summarize_ranks([row["rank"] for row in slot_rows])
    return {
        "overall": summarize_ranks([row["rank"] for row in all_rows]),
        "by_slot": per_slot,
        "rows": all_rows,
    }


def evaluate_phrase_max(
    cids: list[str],
    labels: dict[str, str],
    phrases: dict[str, list[str]],
    tokenizer: Callable[[str], list[str]],
) -> dict:
    all_rows: list[dict] = []
    per_slot: dict[str, dict] = {}
    for holdout in range(EXPECTED_PHRASES_PER_ROW):
        documents: dict[str, list[str]] = {}
        owner: dict[str, str] = {}
        for cid in cids:
            for i, phrase in enumerate(phrases[cid]):
                if i == holdout:
                    continue
                doc_id = f"{cid}#{i}"
                documents[doc_id] = tokenizer(phrase)
                owner[doc_id] = cid
        ranker = BM25(documents)
        slot_rows = []
        for cid in cids:
            query = phrases[cid][holdout]
            query_tokens = tokenizer(query)
            best = {candidate: 0.0 for candidate in cids}
            for doc_id in documents:
                score = ranker.score(query_tokens, doc_id)
                candidate = owner[doc_id]
                if score > best[candidate]:
                    best[candidate] = score
            ranked = sorted(cids, key=lambda candidate: (-best[candidate], candidate))
            rank = ranked.index(cid) + 1
            row = {
                "slot": holdout,
                "slot_name": SLOT_NAMES[holdout],
                "concept_id": cid,
                "label": labels[cid],
                "query": query,
                "rank": rank,
                "top1_concept_id": ranked[0],
                "top1_label": labels[ranked[0]],
            }
            slot_rows.append(row)
            all_rows.append(row)
        per_slot[SLOT_NAMES[holdout]] = summarize_ranks([row["rank"] for row in slot_rows])
    return {
        "overall": summarize_ranks([row["rank"] for row in all_rows]),
        "by_slot": per_slot,
        "rows": all_rows,
    }


def paired_changes(before: list[dict], after: list[dict]) -> dict[str, int]:
    keys_before = [(row["slot"], row["concept_id"]) for row in before]
    keys_after = [(row["slot"], row["concept_id"]) for row in after]
    if keys_before != keys_after:
        raise RuntimeError("paired row order drift")
    return {
        "rank_improved": sum(a["rank"] < b["rank"] for b, a in zip(before, after, strict=True)),
        "rank_same": sum(a["rank"] == b["rank"] for b, a in zip(before, after, strict=True)),
        "rank_worsened": sum(a["rank"] > b["rank"] for b, a in zip(before, after, strict=True)),
        "hit5_gain": sum(b["rank"] > 5 and a["rank"] <= 5 for b, a in zip(before, after, strict=True)),
        "hit5_loss": sum(b["rank"] <= 5 and a["rank"] > 5 for b, a in zip(before, after, strict=True)),
        "top1_gain": sum(b["rank"] != 1 and a["rank"] == 1 for b, a in zip(before, after, strict=True)),
        "top1_loss": sum(b["rank"] == 1 and a["rank"] != 1 for b, a in zip(before, after, strict=True)),
    }


def false_positive_hubs(rows: list[dict], limit: int = 25) -> list[dict]:
    counts: collections.Counter[tuple[str, str]] = collections.Counter(
        (row["top1_concept_id"], row["top1_label"])
        for row in rows
        if row["top1_concept_id"] != row["concept_id"]
    )
    return [
        {"concept_id": cid, "label": label, "false_top1_count": count}
        for (cid, label), count in counts.most_common(limit)
    ]


def strip_rows(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "rows"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", required=True)
    ap.add_argument("--output", default="artifacts/a593-phrase-representation.json")
    args = ap.parse_args()

    cids, labels, phrases = load_teacher(Path(args.teacher))

    flattened_raw = evaluate_flattened(cids, labels, phrases, raw_tokens)
    phrase_max_raw = evaluate_phrase_max(cids, labels, phrases, raw_tokens)
    flattened_snowball = evaluate_flattened(cids, labels, phrases, stemmed_tokens)

    result = {
        "schema_version": 1,
        "status": "A593 corpus-internal architecture diagnostic; no opened evaluation queries used",
        "corpus": {
            "concepts": len(cids),
            "phrases": len(cids) * EXPECTED_PHRASES_PER_ROW,
            "folds": EXPECTED_PHRASES_PER_ROW,
            "cases": len(cids) * EXPECTED_PHRASES_PER_ROW,
            "holdout": "for fold i, phrase slot i is removed from every concept and used as the query",
        },
        "variants": {
            "flattened_raw": strip_rows(flattened_raw),
            "phrase_max_raw": strip_rows(phrase_max_raw),
            "flattened_snowball_sv": strip_rows(flattened_snowball),
        },
        "paired_vs_flattened_raw": {
            "phrase_max_raw": paired_changes(flattened_raw["rows"], phrase_max_raw["rows"]),
            "flattened_snowball_sv": paired_changes(flattened_raw["rows"], flattened_snowball["rows"]),
        },
        "false_positive_hubs": {
            "flattened_raw": false_positive_hubs(flattened_raw["rows"]),
            "flattened_snowball_sv": false_positive_hubs(flattened_snowball["rows"]),
        },
        "interpretation_guard": (
            "These 4,744 cases are model-authored and share the frozen teacher prompt distribution. "
            "They can compare representation mechanics and mine confusions, but they are not independent "
            "user accuracy evidence and must not be mixed with the opened 17/88 suites for tuning."
        ),
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "flattened_raw": result["variants"]["flattened_raw"]["overall"],
        "phrase_max_raw": result["variants"]["phrase_max_raw"]["overall"],
        "flattened_snowball_sv": result["variants"]["flattened_snowball_sv"]["overall"],
        "paired": result["paired_vs_flattened_raw"],
        "top_hubs_raw": result["false_positive_hubs"]["flattened_raw"][:10],
        "output": str(out),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
