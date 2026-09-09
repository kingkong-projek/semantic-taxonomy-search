#!/usr/bin/env python3
"""Package the frozen A593 YV ranker into the existing zero-backend browser format."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import build_yv_demo_asset as base
import evaluate_gemma_a149 as gemma

ENGINE_ID = "YV-A593-Gemma4-26B-sequence-expansion-v0"
TEACHER_PATH = Path("research/enrichment/v31/gemma4-yv-a593/phrases.jsonl")
EXPECTED_SHA = "7769db2124ef190d74964ddb9f97da1d67137dad9b51e9e534e4e9bd6a24f847"
EXPECTED_ROWS = 593
EXPECTED_PHRASES = 4744
EXPECTED_MODEL = "gemma-4-26b-a4b-it"


def load_frozen_teacher() -> dict[str, list[str]]:
    raw = TEACHER_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA:
        raise RuntimeError(f"frozen A593 teacher SHA drift: {digest}")
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != EXPECTED_ROWS:
        raise RuntimeError(f"frozen A593 row drift: {len(rows)}")
    teacher: dict[str, list[str]] = {}
    phrase_count = 0
    for row in rows:
        cid = str(row.get("concept_id") or "")
        phrases = [str(x).strip() for x in row.get("phrases") or [] if str(x).strip()]
        if not cid or cid in teacher:
            raise RuntimeError(f"invalid/duplicate A593 concept id: {cid}")
        if str(row.get("model") or "") != EXPECTED_MODEL:
            raise RuntimeError(f"A593 model drift for {cid}")
        if len(phrases) != 8:
            raise RuntimeError(f"A593 phrase-count drift for {cid}: {len(phrases)}")
        teacher[cid] = phrases
        phrase_count += len(phrases)
    if phrase_count != EXPECTED_PHRASES:
        raise RuntimeError(f"A593 total phrase drift: {phrase_count}")
    return teacher


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output", default="demo/assets/yv-c2.json")
    parser.add_argument("--parity-output", default="artifacts/yv-demo-parity-v1.json")
    known, _ = parser.parse_known_args()

    teacher = load_frozen_teacher()

    def build_a593_ranker(by_id, ids):
        invalid = sorted(set(teacher) - set(ids))
        if invalid:
            raise RuntimeError(f"A593 teacher contains identities outside active universe: {invalid[:5]}")
        return gemma.build_ranker(by_id, ids, teacher)

    base.build_c1_index = build_a593_ranker
    base.ENGINE_ID = ENGINE_ID
    rc = base.main()
    if rc != 0:
        return rc

    output = Path(known.output)
    asset = json.loads(output.read_text(encoding="utf-8"))
    asset["engine"] = ENGINE_ID
    asset["metadata"].update({
        "teacher_expanded_concepts": EXPECTED_ROWS,
        "teacher_phrases": EXPECTED_PHRASES,
        "teacher_jsonl_sha256": EXPECTED_SHA,
        "retrieval_contract": (
            "frozen A593 YV = canonical BM25 over all 2,105 active occupation-name identities, "
            "eight frozen Gemma teacher phrases appended to 593 identities, plus unchanged exact canonical/job-title routing; "
            "teacher phrases are semantic evidence only and are never exact surfaces; unpromoted language-diversity lanes excluded"
        ),
    })
    output.write_text(json.dumps(asset, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")

    parity_path = Path(known.parity_output)
    parity = json.loads(parity_path.read_text(encoding="utf-8"))
    parity["engine"] = ENGINE_ID
    parity_path.write_text(json.dumps(parity, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "engine": ENGINE_ID,
        "targets": asset["metadata"]["target_count"],
        "teacher_expanded_concepts": EXPECTED_ROWS,
        "teacher_phrases": EXPECTED_PHRASES,
        "teacher_jsonl_sha256": EXPECTED_SHA,
        "runtime_dependencies": asset["metadata"]["runtime_dependencies"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
