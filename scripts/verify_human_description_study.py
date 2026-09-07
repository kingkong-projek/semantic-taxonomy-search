#!/usr/bin/env python3
"""Verify a frozen human-description study, including preregistration binding."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import validate_human_description_study as base

PREREG_STATUS = 'frozen-before-first-participant'
PREREG_SCHEMA_VERSION = 2
PLACEHOLDER_MARKERS = ('REPLACE', 'UNFROZEN_TEMPLATE')
COMMIT_RE = re.compile(r'^[0-9a-f]{40}$')
EXPECTED_CANDIDATES = {
    'occupation': {
        'candidate_id': 'YV-description-full-v0-canonical-router',
        'definition_file': 'research/evaluation/v31/yv-full-universe-description-baseline.json',
    },
    'skill': {
        'candidate_id': 'KV-G1+T3',
        'definition_file': 'research/evaluation/v31/kv-g1-t3-simple-boundary.json',
    },
}


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_strings(child)


def _string_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise RuntimeError(f'{where}: must be a list of non-empty strings')
    return value


def _validate_retrieval_freeze(value: Any, streams: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError('preregistration retrieval_freeze must be object')
    base.required(value, {'repository_commit', 'candidates'}, 'preregistration:retrieval_freeze')
    repository_commit = value['repository_commit']
    if not isinstance(repository_commit, str) or COMMIT_RE.fullmatch(repository_commit) is None:
        raise RuntimeError('preregistration retrieval_freeze repository_commit must be a 40-character lowercase hex commit')
    candidates = value['candidates']
    if not isinstance(candidates, dict) or set(candidates) != base.STREAMS:
        raise RuntimeError('preregistration retrieval_freeze candidates must contain exactly occupation and skill')
    for stream in sorted(base.STREAMS):
        candidate = candidates[stream]
        if not isinstance(candidate, dict):
            raise RuntimeError(f'preregistration retrieval candidate {stream} must be object')
        base.required(candidate, {'candidate_id', 'definition_file'}, f'preregistration:retrieval_candidate:{stream}')
        if not base.nonempty_string(candidate['candidate_id']) or not base.nonempty_string(candidate['definition_file']):
            raise RuntimeError(f'preregistration retrieval candidate {stream} fields must be non-empty strings')
        expected = EXPECTED_CANDIDATES[stream]
        if streams[stream].get('enabled') is True and candidate != expected:
            raise RuntimeError(
                f'preregistration retrieval candidate {stream} differs from the frozen simple boundary: {candidate}'
            )
        definition_path = Path(candidate['definition_file'])
        if definition_path.is_absolute() or '..' in definition_path.parts:
            raise RuntimeError(f'preregistration retrieval candidate {stream} definition_file must be repository-relative')
    return value


def validate_preregistration(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj, dict):
        raise RuntimeError('preregistration must be object')
    base.required(
        obj,
        {
            'schema_version', 'study_id', 'status', 'recruitment_source', 'sampling_mode',
            'sample_size_or_stopping_rule', 'streams', 'retrieval_freeze', 'inclusion_criteria',
            'exclusion_criteria', 'elicitation', 'adjudication', 'need_prevalence', 'data_handling',
            'freeze'
        },
        'preregistration',
    )
    if obj['schema_version'] != PREREG_SCHEMA_VERSION:
        raise RuntimeError(f'preregistration schema_version must be {PREREG_SCHEMA_VERSION}')
    if obj['status'] != PREREG_STATUS:
        raise RuntimeError(f'preregistration status must be {PREREG_STATUS}')
    for field in ('study_id', 'recruitment_source', 'sampling_mode', 'sample_size_or_stopping_rule'):
        if not base.nonempty_string(obj[field]):
            raise RuntimeError(f'preregistration {field} must be non-empty string')
    for text in _walk_strings(obj):
        if any(marker in text for marker in PLACEHOLDER_MARKERS):
            raise RuntimeError('preregistration still contains template placeholder')

    streams = obj['streams']
    if not isinstance(streams, dict) or set(streams) != base.STREAMS:
        raise RuntimeError('preregistration streams must contain exactly occupation and skill')
    if not any(isinstance(row, dict) and row.get('enabled') is True for row in streams.values()):
        raise RuntimeError('preregistration must enable at least one stream')
    for stream, row in streams.items():
        if not isinstance(row, dict):
            raise RuntimeError(f'preregistration stream {stream} must be object')
        base.required(row, {'enabled', 'target_or_stopping_rule', 'language_strata', 'sector_strata'}, f'preregistration:{stream}')
        if row['enabled'] not in (True, False):
            raise RuntimeError(f'preregistration:{stream}: enabled must be boolean')
        if row['enabled'] is True and not base.nonempty_string(row['target_or_stopping_rule']):
            raise RuntimeError(f'preregistration:{stream}: enabled stream needs target_or_stopping_rule')
        if not isinstance(row['language_strata'], list) or not isinstance(row['sector_strata'], list):
            raise RuntimeError(f'preregistration:{stream}: strata must be lists')

    _validate_retrieval_freeze(obj['retrieval_freeze'], streams)

    _string_list(obj['inclusion_criteria'], 'preregistration:inclusion_criteria') if obj['inclusion_criteria'] else None
    _string_list(obj['exclusion_criteria'], 'preregistration:exclusion_criteria') if obj['exclusion_criteria'] else None

    elicitation = obj['elicitation']
    if not isinstance(elicitation, dict):
        raise RuntimeError('preregistration elicitation must be object')
    base.required(elicitation, {'examples_allowed_in_primary_benchmark', 'participant_instruction'}, 'preregistration:elicitation')
    if elicitation['examples_allowed_in_primary_benchmark'] is not False:
        raise RuntimeError('primary benchmark must keep examples disabled')
    if not base.nonempty_string(elicitation['participant_instruction']):
        raise RuntimeError('preregistration participant_instruction must be non-empty')

    adjudication = obj['adjudication']
    if not isinstance(adjudication, dict):
        raise RuntimeError('preregistration adjudication must be object')
    base.required(
        adjudication,
        {'instructions', 'reviewers_per_case', 'conflict_resolution', 'retrieval_blind', 'cases_used_to_justify_higher_model_complexity_need_stronger_review'},
        'preregistration:adjudication',
    )
    reviewers = adjudication['reviewers_per_case']
    if isinstance(reviewers, bool) or not isinstance(reviewers, int) or reviewers < 1:
        raise RuntimeError('preregistration reviewers_per_case must be integer >=1')
    if adjudication['retrieval_blind'] is not True:
        raise RuntimeError('preregistration adjudication must be retrieval blind')
    if not base.nonempty_string(adjudication['conflict_resolution']):
        raise RuntimeError('preregistration conflict_resolution must be non-empty')

    need = obj['need_prevalence']
    if not isinstance(need, dict):
        raise RuntimeError('preregistration need_prevalence must be object')
    base.required(need, {'production_funnel_enabled', 'lexical_failure_definition', 'raw_free_text_required'}, 'preregistration:need_prevalence')
    if need['production_funnel_enabled'] not in (True, False):
        raise RuntimeError('preregistration production_funnel_enabled must be boolean')
    if not base.nonempty_string(need['lexical_failure_definition']):
        raise RuntimeError('preregistration lexical_failure_definition must be non-empty')
    if need['production_funnel_enabled'] is True and need['lexical_failure_definition'] == 'NOT_MEASURED_IN_THIS_STUDY':
        raise RuntimeError('enabled production funnel needs a prefrozen lexical failure definition')
    if need['raw_free_text_required'] is not False:
        raise RuntimeError('need/prevalence funnel must not require raw free text')

    handling = obj['data_handling']
    if not isinstance(handling, dict):
        raise RuntimeError('preregistration data_handling must be object')
    base.required(handling, {'approved_basis', 'repository_redaction_process', 'raw_identifiable_material_committed_to_repo'}, 'preregistration:data_handling')
    if not base.nonempty_string(handling['approved_basis']) or not base.nonempty_string(handling['repository_redaction_process']):
        raise RuntimeError('preregistration data handling basis/redaction process must be non-empty')
    if handling['raw_identifiable_material_committed_to_repo'] is not False:
        raise RuntimeError('raw identifiable material must not be committed to repo')

    freeze = obj['freeze']
    if not isinstance(freeze, dict):
        raise RuntimeError('preregistration freeze must be object')
    base.required(freeze, {'frozen_at', 'frozen_by'}, 'preregistration:freeze')
    if not base.nonempty_string(freeze['frozen_at']) or not base.nonempty_string(freeze['frozen_by']):
        raise RuntimeError('preregistration freeze metadata must be set')
    return obj


def verify_bound_manifest(
    manifest_path: Path,
    preregistration_path: Path,
    preregistration: dict[str, Any],
    elicitation_path: Path,
    adjudication_path: Path,
    elicitation_count: int,
    adjudication_count: int,
) -> dict[str, Any]:
    manifest = base.validate_manifest(
        manifest_path,
        elicitation_path,
        adjudication_path,
        elicitation_count,
        adjudication_count,
    )
    if manifest.get('preregistration_sha256') != base.sha(preregistration_path):
        raise RuntimeError('manifest preregistration hash mismatch')
    if manifest['study_id'] != preregistration['study_id']:
        raise RuntimeError('manifest study_id differs from preregistration')
    return manifest


def verify(
    preregistration_path: Path,
    elicitation_path: Path,
    adjudication_path: Path,
    manifest_path: Path,
    outcomes_path: Path | None = None,
    funnel_path: Path | None = None,
) -> dict[str, Any]:
    preregistration = validate_preregistration(preregistration_path)
    elicitation_rows = base.load_jsonl(elicitation_path)
    elicitation = base.validate_elicitation(elicitation_rows)
    adjudication_rows = base.load_jsonl(adjudication_path)
    adjudication = base.validate_adjudication(adjudication_rows, elicitation)
    manifest = verify_bound_manifest(
        manifest_path,
        preregistration_path,
        preregistration,
        elicitation_path,
        adjudication_path,
        len(elicitation_rows),
        len(adjudication_rows),
    )
    outcomes_present = False
    if outcomes_path is not None:
        base.validate_outcomes(base.load_jsonl(outcomes_path), elicitation, adjudication)
        outcomes_present = True
    funnel = base.validate_funnel(funnel_path) if funnel_path is not None else None
    result = base.summarize(manifest, elicitation, adjudication, outcomes_present, funnel)
    result['preregistration_sha256'] = base.sha(preregistration_path)
    result['preregistration_status'] = preregistration['status']
    result['retrieval_repository_commit'] = preregistration['retrieval_freeze']['repository_commit']
    result['retrieval_candidates'] = preregistration['retrieval_freeze']['candidates']
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--preregistration', required=True, type=Path)
    parser.add_argument('--elicitation', required=True, type=Path)
    parser.add_argument('--adjudication', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--outcomes', type=Path)
    parser.add_argument('--funnel', type=Path)
    args = parser.parse_args()
    result = verify(
        args.preregistration,
        args.elicitation,
        args.adjudication,
        args.manifest,
        args.outcomes,
        args.funnel,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
