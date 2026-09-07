#!/usr/bin/env python3
"""Contract self-tests for staged human-description study validation.

Fixtures are synthetic schema fixtures created only in a temporary directory.
They are never benchmark/user evidence.
"""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import validate_human_description_study as validator


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def expect_failure(label: str, fn) -> None:
    try:
        fn()
    except RuntimeError:
        return
    raise AssertionError(f'{label}: expected RuntimeError')


def build_valid_files(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    elicitation = [
        {
            'case_id': 'case-occ',
            'stream': 'occupation',
            'participant_id': 'p-001',
            'description_redacted': 'Jag planerar arbete, följer upp leveranser och samordnar flera delar.',
            'language': 'sv',
            'entry_mode': 'study-prompted',
            'title_known': None,
            'fallback_would_use': True,
        },
        {
            'case_id': 'case-skill',
            'stream': 'skill',
            'participant_id': 'p-002',
            'description_redacted': 'Jag sammanfogar metall och kontrollerar fogens kvalitet efter arbetet.',
            'language': 'sv',
            'entry_mode': 'observed-offered',
        },
    ]
    adjudication = [
        {
            'case_id': 'case-occ',
            'status': 'mapped',
            'acceptable_targets': [
                {'canonical_id': 'occ-1', 'in_frozen_demand_envelope': True}
            ],
            'adjudicator_ids': ['a-1'],
            'retrieval_blind': True,
        },
        {
            'case_id': 'case-skill',
            'status': 'ambiguous',
            'acceptable_targets': [
                {'canonical_id': 'skill-in', 'in_frozen_demand_envelope': True},
                {'canonical_id': 'skill-out', 'in_frozen_demand_envelope': False},
            ],
            'adjudicator_ids': ['a-2'],
            'retrieval_blind': True,
        },
    ]
    outcomes = [
        {
            'case_id': 'case-occ',
            'lexical_top5_ids': [],
            'fallback_top5_ids': ['occ-1', 'occ-2'],
            'participant_recognized_ids': ['occ-1'],
            'participant_selected_id': 'occ-1',
            'clarification_was_offered': False,
        },
        {
            'case_id': 'case-skill',
            'lexical_top5_ids': ['skill-other'],
            'fallback_top5_ids': ['skill-in', 'skill-x'],
            'participant_recognized_ids': [],
            'participant_selected_id': None,
            'clarification_was_offered': False,
        },
    ]
    funnel = {
        'schema_version': 1,
        'measurement_window': {'start': '2026-09-01', 'end': '2026-09-07'},
        'lexical_failure_definition': 'contract self-test definition only',
        'cohorts': [
            {
                'stream': 'occupation',
                'eligible_lexical_failure_exposures': 20,
                'fallback_offers': 20,
                'fallback_opens': 8,
                'fallback_submissions': 6,
                'fallback_selections': 4,
                'none_selections': 1,
            },
            {
                'stream': 'skill',
                'eligible_lexical_failure_exposures': 10,
                'fallback_offers': 9,
                'fallback_opens': 5,
                'fallback_submissions': 4,
                'fallback_selections': 2,
                'none_selections': 2,
            },
        ],
    }

    elicitation_path = root / 'elicitation.jsonl'
    adjudication_path = root / 'adjudication.jsonl'
    outcomes_path = root / 'outcomes.jsonl'
    manifest_path = root / 'manifest.json'
    funnel_path = root / 'need-funnel.json'
    write_jsonl(elicitation_path, elicitation)
    write_jsonl(adjudication_path, adjudication)
    write_jsonl(outcomes_path, outcomes)
    funnel_path.write_text(json.dumps(funnel, indent=2) + '\n', encoding='utf-8')
    manifest_path.write_text(
        json.dumps(
            {
                'schema_version': 2,
                'study_id': 'contract-selftest',
                'elicitation_sha256': validator.sha(elicitation_path),
                'adjudication_sha256': validator.sha(adjudication_path),
                'elicitation_cases': len(elicitation),
                'adjudication_cases': len(adjudication),
                'frozen_before_retrieval': True,
            },
            indent=2,
        ) + '\n',
        encoding='utf-8',
    )
    return elicitation_path, adjudication_path, manifest_path, outcomes_path, funnel_path


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        elicitation_path, adjudication_path, manifest_path, outcomes_path, funnel_path = build_valid_files(root)

        elicitation_rows = validator.load_jsonl(elicitation_path)
        elicitation = validator.validate_elicitation(elicitation_rows)
        adjudication_rows = validator.load_jsonl(adjudication_path)
        adjudication = validator.validate_adjudication(adjudication_rows, elicitation)
        manifest = validator.validate_manifest(
            manifest_path,
            elicitation_path,
            adjudication_path,
            len(elicitation_rows),
            len(adjudication_rows),
        )
        validator.validate_outcomes(validator.load_jsonl(outcomes_path), elicitation, adjudication)
        funnel = validator.validate_funnel(funnel_path)
        summary = validator.summarize(manifest, elicitation, adjudication, True, funnel)
        assert summary['mixed_envelope_ambiguous_cases'] == 1
        assert summary['cases_with_in_envelope_target'] == 2
        assert summary['adjudicated_targets'] == 3
        assert summary['production_funnel_present'] is True
        assert summary['funnel_counts']['occupation']['fallback_submissions'] == 6

        pii_rows = copy.deepcopy(elicitation_rows)
        pii_rows[0]['description_redacted'] = 'Kontakta test@example.com om arbetet.'
        expect_failure('email pii guard', lambda: validator.validate_elicitation(pii_rows))

        leaked_rows = copy.deepcopy(elicitation_rows)
        leaked_rows[0]['fallback_top5_ids'] = ['occ-1']
        expect_failure('stage leakage', lambda: validator.validate_elicitation(leaked_rows))

        bad_mapped = copy.deepcopy(adjudication_rows)
        bad_mapped[0]['acceptable_targets'].append(
            {'canonical_id': 'occ-2', 'in_frozen_demand_envelope': False}
        )
        expect_failure('mapped exactly one target', lambda: validator.validate_adjudication(bad_mapped, elicitation))

        bad_occ_envelope = copy.deepcopy(adjudication_rows)
        bad_occ_envelope[0]['acceptable_targets'][0]['in_frozen_demand_envelope'] = False
        expect_failure(
            'occupation full-universe envelope',
            lambda: validator.validate_adjudication(bad_occ_envelope, elicitation),
        )

        bad_outcomes = validator.load_jsonl(outcomes_path)
        bad_outcomes[0]['participant_recognized_ids'] = ['not-in-fallback']
        expect_failure(
            'recognized subset',
            lambda: validator.validate_outcomes(bad_outcomes, elicitation, adjudication),
        )

        bad_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        bad_manifest['elicitation_sha256'] = '0' * 64
        bad_manifest_path = root / 'bad-manifest.json'
        bad_manifest_path.write_text(json.dumps(bad_manifest), encoding='utf-8')
        expect_failure(
            'hash freeze',
            lambda: validator.validate_manifest(
                bad_manifest_path,
                elicitation_path,
                adjudication_path,
                len(elicitation_rows),
                len(adjudication_rows),
            ),
        )

        bad_funnel = json.loads(funnel_path.read_text(encoding='utf-8'))
        bad_funnel['cohorts'][0]['fallback_opens'] = 21
        bad_funnel_path = root / 'bad-funnel.json'
        bad_funnel_path.write_text(json.dumps(bad_funnel), encoding='utf-8')
        expect_failure('funnel ordering', lambda: validator.validate_funnel(bad_funnel_path))

    print('human-description study contract self-test: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
