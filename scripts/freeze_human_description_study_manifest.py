#!/usr/bin/env python3
"""Create the retrieval-freeze manifest after preregistration and blind adjudication."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import validate_human_description_study as base
import verify_human_description_study as verify


def freeze_manifest(
    preregistration_path: Path,
    elicitation_path: Path,
    adjudication_path: Path,
    output_path: Path,
) -> dict:
    preregistration = verify.validate_preregistration(preregistration_path)
    elicitation_rows = base.load_jsonl(elicitation_path)
    elicitation = base.validate_elicitation(elicitation_rows)
    adjudication_rows = base.load_jsonl(adjudication_path)
    base.validate_adjudication(adjudication_rows, elicitation)
    if output_path.exists():
        raise RuntimeError(f'refusing to overwrite existing manifest: {output_path}')
    manifest = {
        'schema_version': 2,
        'study_id': preregistration['study_id'],
        'preregistration_sha256': base.sha(preregistration_path),
        'elicitation_sha256': base.sha(elicitation_path),
        'adjudication_sha256': base.sha(adjudication_path),
        'elicitation_cases': len(elicitation_rows),
        'adjudication_cases': len(adjudication_rows),
        'frozen_before_retrieval': True,
    }
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--preregistration', required=True, type=Path)
    parser.add_argument('--elicitation', required=True, type=Path)
    parser.add_argument('--adjudication', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    manifest = freeze_manifest(
        args.preregistration,
        args.elicitation,
        args.adjudication,
        args.output,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
