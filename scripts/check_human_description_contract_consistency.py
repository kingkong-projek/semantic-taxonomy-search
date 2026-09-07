#!/usr/bin/env python3
"""Check that the structured human-study contract matches executable study guards."""
from __future__ import annotations

import json
from pathlib import Path

import verify_human_description_study as verifier

CONTRACT = Path('research/evaluation/v31/description-fallback-human-validation-contract.json')


def main() -> int:
    obj = json.loads(CONTRACT.read_text(encoding='utf-8'))
    if obj.get('schema_version') != 3:
        raise RuntimeError('human validation contract schema_version must be 3')
    if obj.get('study_id') != 'description-fallback-human-v1':
        raise RuntimeError('unexpected human validation study_id')
    if obj.get('status') != 'collection_ready_preregistration_not_frozen':
        raise RuntimeError('structured contract must reflect current no-data preregistration state')

    prereg = obj.get('preregistration')
    if not isinstance(prereg, dict):
        raise RuntimeError('contract preregistration section missing')
    if prereg.get('required_status') != verifier.PREREG_STATUS:
        raise RuntimeError('contract preregistration status differs from executable verifier')
    if prereg.get('frozen_file') != 'research/human/description-fallback-v1/preregistration.json':
        raise RuntimeError('contract preregistration path differs from repository guard')
    if prereg.get('must_precede_first_real_participant') is not True:
        raise RuntimeError('contract must freeze preregistration before first real participant')

    freeze = obj.get('freeze_binding')
    if not isinstance(freeze, dict):
        raise RuntimeError('contract freeze_binding section missing')
    if freeze.get('manifest_schema_version') != 2:
        raise RuntimeError('contract manifest schema differs from executable validator')
    required_hashes = set(freeze.get('required_sha256_bindings', []))
    expected_hashes = {'preregistration_sha256', 'elicitation_sha256', 'adjudication_sha256'}
    if required_hashes != expected_hashes:
        raise RuntimeError(f'contract freeze hash set differs: {required_hashes}')
    if freeze.get('frozen_before_retrieval') is not True:
        raise RuntimeError('contract must require freeze before retrieval')
    if freeze.get('freeze_tool') != 'scripts/freeze_human_description_study_manifest.py':
        raise RuntimeError('contract freeze tool path drift')
    if freeze.get('verification_tool') != 'scripts/verify_human_description_study.py':
        raise RuntimeError('contract verification tool path drift')
    if freeze.get('repository_stage_guard') != 'scripts/check_human_description_repository_state.py':
        raise RuntimeError('contract repository guard path drift')
    if freeze.get('manifest_overwrite') != 'forbidden':
        raise RuntimeError('contract must forbid manifest overwrite')

    elicitation = obj.get('elicitation', {})
    if elicitation.get('examples_in_primary_benchmark') is not False:
        raise RuntimeError('structured contract must keep primary benchmark example-free')
    if set(elicitation.get('entry_modes', [])) != {'observed-voluntary', 'observed-offered', 'study-prompted'}:
        raise RuntimeError('structured contract entry modes drift')

    outcomes = obj.get('outcomes', {})
    recognition_rule = outcomes.get('recognition_rule', '')
    if 'subset of fallback_top5_ids' not in recognition_rule:
        raise RuntimeError('structured contract recognition rule drift')

    print('human-description structured contract consistency: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
