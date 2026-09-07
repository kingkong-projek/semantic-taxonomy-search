#!/usr/bin/env python3
"""Self-test preregistration and manifest binding for the human-description study."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import freeze_human_description_study_manifest as freezer
import selftest_human_description_study as staged_selftest
import verify_human_description_study as verifier


def expect_failure(label: str, fn) -> None:
    try:
        fn()
    except RuntimeError:
        return
    raise AssertionError(f'{label}: expected RuntimeError')


def valid_preregistration() -> dict:
    return {
        'schema_version': 1,
        'study_id': 'contract-selftest',
        'status': 'frozen-before-first-participant',
        'recruitment_source': 'contract self-test only',
        'sampling_mode': 'fixed schema fixture',
        'sample_size_or_stopping_rule': 'two schema cases only',
        'streams': {
            'occupation': {
                'enabled': True,
                'target_or_stopping_rule': 'one schema case',
                'language_strata': ['sv'],
                'sector_strata': [],
            },
            'skill': {
                'enabled': True,
                'target_or_stopping_rule': 'one schema case',
                'language_strata': ['sv'],
                'sector_strata': [],
            },
        },
        'inclusion_criteria': ['synthetic schema fixture only'],
        'exclusion_criteria': [],
        'elicitation': {
            'examples_allowed_in_primary_benchmark': False,
            'participant_instruction': 'research/human/description-fallback-v1/participant-instructions-sv.md',
        },
        'adjudication': {
            'instructions': 'research/human/description-fallback-v1/adjudicator-instructions.md',
            'reviewers_per_case': 1,
            'conflict_resolution': 'not applicable to schema self-test',
            'retrieval_blind': True,
            'cases_used_to_justify_higher_model_complexity_need_stronger_review': True,
        },
        'need_prevalence': {
            'production_funnel_enabled': False,
            'lexical_failure_definition': 'NOT_MEASURED_IN_THIS_STUDY',
            'raw_free_text_required': False,
        },
        'data_handling': {
            'approved_basis': 'synthetic schema fixture only',
            'repository_redaction_process': 'no human data exists in this self-test',
            'raw_identifiable_material_committed_to_repo': False,
        },
        'freeze': {
            'frozen_at': '2026-09-07T00:00:00Z',
            'frozen_by': 'contract-selftest',
        },
    }


def main() -> int:
    template_path = Path('research/human/description-fallback-v1/preregistration-template.json')
    expect_failure('template must not validate as frozen preregistration', lambda: verifier.validate_preregistration(template_path))

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        elicitation_path, adjudication_path, _, outcomes_path, funnel_path = staged_selftest.build_valid_files(root)
        preregistration_path = root / 'preregistration.json'
        manifest_path = root / 'manifest-frozen.json'
        preregistration_path.write_text(json.dumps(valid_preregistration(), indent=2) + '\n', encoding='utf-8')

        verifier.validate_preregistration(preregistration_path)
        manifest = freezer.freeze_manifest(
            preregistration_path,
            elicitation_path,
            adjudication_path,
            manifest_path,
        )
        assert manifest['preregistration_sha256']
        result = verifier.verify(
            preregistration_path,
            elicitation_path,
            adjudication_path,
            manifest_path,
            outcomes_path,
            funnel_path,
        )
        assert result['preregistration_status'] == 'frozen-before-first-participant'
        assert result['production_funnel_present'] is True

        expect_failure(
            'manifest must not be overwritten',
            lambda: freezer.freeze_manifest(
                preregistration_path,
                elicitation_path,
                adjudication_path,
                manifest_path,
            ),
        )

        tampered = valid_preregistration()
        tampered['sampling_mode'] = 'changed after freeze'
        preregistration_path.write_text(json.dumps(tampered, indent=2) + '\n', encoding='utf-8')
        expect_failure(
            'preregistration hash binding',
            lambda: verifier.verify(
                preregistration_path,
                elicitation_path,
                adjudication_path,
                manifest_path,
            ),
        )

    print('human-description preregistration binding self-test: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
