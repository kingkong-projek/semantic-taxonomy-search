#!/usr/bin/env python3
"""Validate staged human-description study exports without running retrieval."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

EMAIL_RE = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I)
PHONE_RE = re.compile(r'(?<!\w)(?:\+46|0)[\s\-]?(?:\d[\s\-]?){7,10}(?!\w)')
ELICIT_FORBIDDEN = {
    'acceptable_targets', 'acceptable_canonical_ids', 'adjudication_status',
    'lexical_top5_ids', 'fallback_top5_ids', 'participant_recognized_ids',
    'participant_selected_id', 'retrieval_output', 'retrieval_rank'
}
ADJ_FORBIDDEN = {
    'lexical_top5_ids', 'fallback_top5_ids', 'participant_recognized_ids',
    'participant_selected_id', 'retrieval_output', 'retrieval_rank'
}
STATUSES = {'mapped', 'ambiguous', 'clarification-needed', 'unmappable', 'out-of-scope'}
STREAMS = {'occupation', 'skill'}
ENTRY_MODES = {'observed-voluntary', 'observed-offered', 'study-prompted'}
FUNNEL_COUNT_FIELDS = (
    'eligible_lexical_failure_exposures',
    'fallback_offers',
    'fallback_opens',
    'fallback_submissions',
    'fallback_selections',
    'none_selections',
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception as exc:
            raise RuntimeError(f'{path}:{i}: invalid JSON: {exc}') from exc
        if not isinstance(obj, dict):
            raise RuntimeError(f'{path}:{i}: record must be object')
        rows.append(obj)
    return rows


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def required(row: dict[str, Any], keys: set[str], where: str) -> None:
    missing = sorted(k for k in keys if k not in row)
    if missing:
        raise RuntimeError(f'{where}: missing {missing}')


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def unique_string_list(value: Any, where: str, max_len: int | None = None) -> list[str]:
    if not isinstance(value, list) or any(not nonempty_string(x) for x in value):
        raise RuntimeError(f'{where}: must be string list')
    if len(value) != len(set(value)):
        raise RuntimeError(f'{where}: must not contain duplicates')
    if max_len is not None and len(value) > max_len:
        raise RuntimeError(f'{where}: max length is {max_len}')
    return value


def ensure_unique(rows: list[dict[str, Any]], where: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(rows, 1):
        case_id = row.get('case_id')
        if not nonempty_string(case_id):
            raise RuntimeError(f'{where}:{i}: invalid case_id')
        if case_id in out:
            raise RuntimeError(f'{where}:{i}: duplicate case_id {case_id}')
        out[case_id] = row
    return out


def validate_elicitation(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    idx = ensure_unique(rows, 'elicitation')
    for case_id, row in idx.items():
        required(
            row,
            {'case_id', 'stream', 'participant_id', 'description_redacted', 'language', 'entry_mode'},
            f'elicitation:{case_id}',
        )
        if row['stream'] not in STREAMS:
            raise RuntimeError(f'elicitation:{case_id}: bad stream')
        if not nonempty_string(row['participant_id']):
            raise RuntimeError(f'elicitation:{case_id}: bad participant_id')
        if not nonempty_string(row['description_redacted']):
            raise RuntimeError(f'elicitation:{case_id}: empty description')
        if not nonempty_string(row['language']):
            raise RuntimeError(f'elicitation:{case_id}: bad language')
        if row['entry_mode'] not in ENTRY_MODES:
            raise RuntimeError(f'elicitation:{case_id}: bad entry_mode')
        for optional_bool in ('title_known', 'fallback_would_use'):
            if optional_bool in row and row[optional_bool] not in (True, False, None):
                raise RuntimeError(f'elicitation:{case_id}: {optional_bool} must be boolean or null')
        leaked = sorted(ELICIT_FORBIDDEN & set(row))
        if leaked:
            raise RuntimeError(f'elicitation:{case_id}: post-elicitation fields leaked {leaked}')
        for key in ('description_redacted', 'lexical_attempt_redacted'):
            if key not in row or row[key] is None:
                continue
            if not isinstance(row[key], str):
                raise RuntimeError(f'elicitation:{case_id}: {key} must be string or null')
            if EMAIL_RE.search(row[key]):
                raise RuntimeError(f'elicitation:{case_id}: obvious email address in {key}')
            if PHONE_RE.search(row[key]):
                raise RuntimeError(f'elicitation:{case_id}: possible phone number in {key}')
    return idx


def validate_targets(value: Any, where: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RuntimeError(f'{where}: acceptable_targets must be list')
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, target in enumerate(value, 1):
        if not isinstance(target, dict):
            raise RuntimeError(f'{where}: target {i} must be object')
        required(target, {'canonical_id', 'in_frozen_demand_envelope'}, f'{where}:target:{i}')
        canonical_id = target['canonical_id']
        if not nonempty_string(canonical_id):
            raise RuntimeError(f'{where}: target {i} has invalid canonical_id')
        if canonical_id in seen:
            raise RuntimeError(f'{where}: duplicate target {canonical_id}')
        seen.add(canonical_id)
        if target['in_frozen_demand_envelope'] not in (True, False):
            raise RuntimeError(f'{where}: target {canonical_id} envelope flag must be boolean')
        targets.append(target)
    return targets


def validate_adjudication(
    rows: list[dict[str, Any]], elicitation: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    idx = ensure_unique(rows, 'adjudication')
    if set(idx) != set(elicitation):
        raise RuntimeError(
            'adjudication case set differs from elicitation: '
            f'missing={sorted(set(elicitation) - set(idx))} extra={sorted(set(idx) - set(elicitation))}'
        )
    for case_id, row in idx.items():
        required(
            row,
            {'case_id', 'status', 'acceptable_targets', 'adjudicator_ids', 'retrieval_blind'},
            f'adjudication:{case_id}',
        )
        if row['status'] not in STATUSES:
            raise RuntimeError(f'adjudication:{case_id}: bad status')
        targets = validate_targets(row['acceptable_targets'], f'adjudication:{case_id}')
        stream = elicitation[case_id]['stream']
        if stream == 'occupation' and any(
            target['in_frozen_demand_envelope'] is not True for target in targets
        ):
            raise RuntimeError(
                f'adjudication:{case_id}: active v31 occupation-name targets are all inside the frozen occupation capability universe'
            )
        if row['status'] == 'mapped' and len(targets) != 1:
            raise RuntimeError(f'adjudication:{case_id}: mapped requires exactly one target')
        if row['status'] == 'ambiguous' and len(targets) < 2:
            raise RuntimeError(f'adjudication:{case_id}: ambiguous requires >=2 targets')
        if row['status'] in {'clarification-needed', 'unmappable', 'out-of-scope'} and targets:
            raise RuntimeError(f'adjudication:{case_id}: {row["status"]} must not invent targets')
        adjudicators = unique_string_list(row['adjudicator_ids'], f'adjudication:{case_id}:adjudicator_ids')
        if not adjudicators:
            raise RuntimeError(f'adjudication:{case_id}: adjudicator_ids must not be empty')
        if row['retrieval_blind'] is not True:
            raise RuntimeError(f'adjudication:{case_id}: retrieval_blind must be true')
        leaked = sorted(ADJ_FORBIDDEN & set(row))
        if leaked:
            raise RuntimeError(f'adjudication:{case_id}: outcome fields leaked {leaked}')
    return idx


def validate_manifest(
    path: Path,
    elicitation_path: Path,
    adjudication_path: Path,
    elicitation_count: int,
    adjudication_count: int,
) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj, dict):
        raise RuntimeError('manifest must be object')
    required(
        obj,
        {
            'schema_version', 'study_id', 'elicitation_sha256', 'adjudication_sha256',
            'elicitation_cases', 'adjudication_cases', 'frozen_before_retrieval'
        },
        'manifest',
    )
    if obj['schema_version'] != 2:
        raise RuntimeError('manifest schema_version must be 2')
    if not nonempty_string(obj['study_id']):
        raise RuntimeError('manifest study_id must be non-empty string')
    if obj['elicitation_sha256'] != sha(elicitation_path):
        raise RuntimeError('manifest elicitation hash mismatch')
    if obj['adjudication_sha256'] != sha(adjudication_path):
        raise RuntimeError('manifest adjudication hash mismatch')
    if int(obj['elicitation_cases']) != elicitation_count or int(obj['adjudication_cases']) != adjudication_count:
        raise RuntimeError('manifest case count mismatch')
    if obj['frozen_before_retrieval'] is not True:
        raise RuntimeError('manifest must assert frozen_before_retrieval=true')
    return obj


def validate_outcomes(
    rows: list[dict[str, Any]],
    elicitation: dict[str, dict[str, Any]],
    adjudication: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    idx = ensure_unique(rows, 'outcomes')
    if set(idx) != set(elicitation):
        raise RuntimeError(
            'outcome case set differs from elicitation: '
            f'missing={sorted(set(elicitation) - set(idx))} extra={sorted(set(idx) - set(elicitation))}'
        )
    if set(idx) != set(adjudication):
        raise RuntimeError('outcome case set differs from adjudication')
    for case_id, row in idx.items():
        required(
            row,
            {
                'case_id', 'lexical_top5_ids', 'fallback_top5_ids', 'participant_recognized_ids',
                'participant_selected_id', 'clarification_was_offered'
            },
            f'outcomes:{case_id}',
        )
        unique_string_list(row['lexical_top5_ids'], f'outcomes:{case_id}:lexical_top5_ids', 5)
        fallback = unique_string_list(row['fallback_top5_ids'], f'outcomes:{case_id}:fallback_top5_ids', 5)
        recognized = unique_string_list(
            row['participant_recognized_ids'], f'outcomes:{case_id}:participant_recognized_ids', 5
        )
        if not set(recognized).issubset(set(fallback)):
            raise RuntimeError(f'outcomes:{case_id}: recognized ids must be subset of fallback_top5_ids')
        selected = row['participant_selected_id']
        if selected is not None and not nonempty_string(selected):
            raise RuntimeError(f'outcomes:{case_id}: invalid selected id')
        if selected is not None and selected not in recognized:
            raise RuntimeError(f'outcomes:{case_id}: selected id must be participant-recognized')
        if row['clarification_was_offered'] not in (True, False):
            raise RuntimeError(f'outcomes:{case_id}: clarification flag must be boolean')
    return idx


def validate_funnel(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj, dict):
        raise RuntimeError('funnel must be object')
    required(obj, {'schema_version', 'measurement_window', 'lexical_failure_definition', 'cohorts'}, 'funnel')
    if obj['schema_version'] != 1:
        raise RuntimeError('funnel schema_version must be 1')
    window = obj['measurement_window']
    if not isinstance(window, dict):
        raise RuntimeError('funnel measurement_window must be object')
    required(window, {'start', 'end'}, 'funnel:measurement_window')
    if not nonempty_string(window['start']) or not nonempty_string(window['end']):
        raise RuntimeError('funnel measurement_window dates must be non-empty strings')
    if not nonempty_string(obj['lexical_failure_definition']):
        raise RuntimeError('funnel lexical_failure_definition must be non-empty string')
    cohorts = obj['cohorts']
    if not isinstance(cohorts, list) or not cohorts:
        raise RuntimeError('funnel cohorts must be non-empty list')
    seen_streams: set[str] = set()
    for i, cohort in enumerate(cohorts, 1):
        if not isinstance(cohort, dict):
            raise RuntimeError(f'funnel:cohort:{i}: must be object')
        required(cohort, {'stream', *FUNNEL_COUNT_FIELDS}, f'funnel:cohort:{i}')
        stream = cohort['stream']
        if stream not in STREAMS:
            raise RuntimeError(f'funnel:cohort:{i}: bad stream')
        if stream in seen_streams:
            raise RuntimeError(f'funnel: duplicate stream cohort {stream}')
        seen_streams.add(stream)
        for field in FUNNEL_COUNT_FIELDS:
            value = cohort[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeError(f'funnel:{stream}:{field}: must be non-negative integer')
        eligible = cohort['eligible_lexical_failure_exposures']
        offers = cohort['fallback_offers']
        opens = cohort['fallback_opens']
        submissions = cohort['fallback_submissions']
        selections = cohort['fallback_selections']
        none = cohort['none_selections']
        if not (eligible >= offers >= opens >= submissions >= selections):
            raise RuntimeError(f'funnel:{stream}: count ordering invariant violated')
        if none > submissions or selections + none > submissions:
            raise RuntimeError(f'funnel:{stream}: selection/none counts exceed submissions')
    return obj


def summarize(
    manifest: dict[str, Any],
    elicitation: dict[str, dict[str, Any]],
    adjudication: dict[str, dict[str, Any]],
    outcomes_present: bool,
    funnel: dict[str, Any] | None,
) -> dict[str, Any]:
    target_rows = [target for row in adjudication.values() for target in row['acceptable_targets']]
    mixed_envelope_ambiguous = sum(
        row['status'] == 'ambiguous'
        and {target['in_frozen_demand_envelope'] for target in row['acceptable_targets']} == {True, False}
        for row in adjudication.values()
    )
    result: dict[str, Any] = {
        'study_id': manifest['study_id'],
        'elicitation_cases': len(elicitation),
        'adjudication_cases': len(adjudication),
        'participants': len({row['participant_id'] for row in elicitation.values()}),
        'occupation_cases': sum(row['stream'] == 'occupation' for row in elicitation.values()),
        'skill_cases': sum(row['stream'] == 'skill' for row in elicitation.values()),
        'mapped_or_ambiguous': sum(row['status'] in {'mapped', 'ambiguous'} for row in adjudication.values()),
        'clarification_needed': sum(row['status'] == 'clarification-needed' for row in adjudication.values()),
        'adjudicated_targets': len(target_rows),
        'cases_with_in_envelope_target': sum(
            any(target['in_frozen_demand_envelope'] for target in row['acceptable_targets'])
            for row in adjudication.values()
        ),
        'mixed_envelope_ambiguous_cases': mixed_envelope_ambiguous,
        'outcomes_present': outcomes_present,
        'frozen_before_retrieval': True,
        'production_funnel_present': funnel is not None,
    }
    if funnel is not None:
        result['funnel_counts'] = {
            cohort['stream']: {field: cohort[field] for field in FUNNEL_COUNT_FIELDS}
            for cohort in funnel['cohorts']
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--elicitation', required=True, type=Path)
    parser.add_argument('--adjudication', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--outcomes', type=Path)
    parser.add_argument('--funnel', type=Path)
    args = parser.parse_args()

    elicitation_rows = load_jsonl(args.elicitation)
    elicitation = validate_elicitation(elicitation_rows)
    adjudication_rows = load_jsonl(args.adjudication)
    adjudication = validate_adjudication(adjudication_rows, elicitation)
    manifest = validate_manifest(
        args.manifest,
        args.elicitation,
        args.adjudication,
        len(elicitation_rows),
        len(adjudication_rows),
    )
    outcomes_present = False
    if args.outcomes:
        validate_outcomes(load_jsonl(args.outcomes), elicitation, adjudication)
        outcomes_present = True
    funnel = validate_funnel(args.funnel) if args.funnel else None

    print(
        json.dumps(
            summarize(manifest, elicitation, adjudication, outcomes_present, funnel),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
