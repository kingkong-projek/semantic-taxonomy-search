#!/usr/bin/env python3
"""Check that the structured human-study contract matches executable study guards."""
from __future__ import annotations

import json
from pathlib import Path

import verify_human_description_study as verifier

CONTRACT = Path('research/evaluation/v31/description-fallback-human-validation-contract.json')


def main() -> int:
    obj = json.loads(CONTRACT.read_text(encoding='utf-8'))
    if obj.get('schema_version') != 4:
        raise RuntimeError('human validation contract schema_version must be 4')
    if obj.get('study_id') != 'description-fallback-human-v1':
        raise RuntimeError('unexpected human validation study_id')
    if obj.get('status') != 'skill_collection_ready_occupation_candidate_not_frozen':
        raise RuntimeError('structured contract must reflect the blocked occupation/full-universe candidate state')

    streams = obj.get('streams')
    if not isinstance(streams, dict):
        raise RuntimeError('contract streams section missing')
    occupation = streams.get('occupation')
    skill = streams.get('skill')
    if not isinstance(occupation, dict) or not isinstance(skill, dict):
        raise RuntimeError('contract must define occupation and skill streams')
    if occupation.get('collection_status') != 'blocked_until_full_universe_candidate_is_evaluated_and_frozen':
        raise RuntimeError('occupation collection must remain blocked until the full-universe candidate is frozen')
    if 'YV-description-full-v0' not in str(occupation.get('candidate', '')):
        raise RuntimeError('occupation stream must name the full-universe YV research candidate')
    if '2,105 active v31 occupation-name identities' not in str(occupation.get('demand_envelope', '')):
        raise RuntimeError('occupation capability universe must be all active v31 occupation-name identities')
    if 'P80 membership is a demand-priority stratum' not in str(occupation.get('demand_envelope', '')):
        raise RuntimeError('occupation P80 must be a demand stratum rather than a capability boundary')
    if skill.get('collection_status') != 'ready_once_preregistration_is_frozen':
        raise RuntimeError('skill collection status drift')

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
    if freeze.get('score_tool') != 'scripts/score_human_description_study.py':
        raise RuntimeError('contract score tool path drift')

    elicitation = obj.get('elicitation', {})
    if elicitation.get('examples_in_primary_benchmark') is not False:
        raise RuntimeError('structured contract must keep primary benchmark example-free')
    if set(elicitation.get('entry_modes', [])) != {'observed-voluntary', 'observed-offered', 'study-prompted'}:
        raise RuntimeError('structured contract entry modes drift')

    adjudication = obj.get('adjudication', {})
    if 'every valid active v31 occupation-name target' not in str(adjudication.get('stream_rule', '')):
        raise RuntimeError('occupation adjudication must treat the full active target universe as capability-eligible')

    outcomes = obj.get('outcomes', {})
    recognition_rule = outcomes.get('recognition_rule', '')
    if 'subset of fallback_top5_ids' not in recognition_rule:
        raise RuntimeError('structured contract recognition rule drift')

    capability = obj.get('primary_metrics', {}).get('capability', [])
    required_metric_markers = ('Top1 acceptable', 'mean reciprocal rank', 'unacceptable-prefix', 'candidate-list precision', 'Hit@5')
    capability_text = ' '.join(str(item) for item in capability)
    for marker in required_metric_markers:
        if marker not in capability_text:
            raise RuntimeError(f'structured contract missing rank-sensitive metric marker: {marker}')
    if 'secondary historical recall signals' not in capability_text:
        raise RuntimeError('structured contract must demote Hit@5 to secondary recall')

    print('human-description structured contract consistency: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
