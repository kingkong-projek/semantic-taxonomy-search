#!/usr/bin/env python3
"""Score a frozen human description study without reducing product quality to Hit@5.

The scorecard deliberately keeps occupation and skill separate. Hit@5 is retained for
historical comparability, but rank-sensitive and list-quality measures are first-class:
Top1, reciprocal rank, nDCG@5, first acceptable rank, unacceptable prefix burden and
candidate-list precision. This makes a result such as two irrelevant candidates followed
by the correct candidate at rank 3 visibly poor instead of merely counting it as a hit.

This script is decision plumbing, not a new benchmark. It refuses to score unless the
preregistration -> elicitation -> blind adjudication -> manifest binding validates.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import validate_human_description_study as base
import verify_human_description_study as verifier

Z95 = 1.959963984540054


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return round(float(numerator) / float(denominator), 6)


def wilson95(successes: int, total: int) -> list[float] | None:
    if total <= 0:
        return None
    p = successes / total
    z2 = Z95 * Z95
    denom = 1.0 + z2 / total
    centre = (p + z2 / (2.0 * total)) / denom
    margin = Z95 * math.sqrt((p * (1.0 - p) + z2 / (4.0 * total)) / total) / denom
    return [round(max(0.0, centre - margin), 6), round(min(1.0, centre + margin), 6)]


def proportion(successes: int, total: int) -> dict[str, Any]:
    return {
        'successes': int(successes),
        'total': int(total),
        'rate': ratio(successes, total),
        'wilson95': wilson95(successes, total),
    }


def first_relevant_rank(returned: list[str], relevant: set[str]) -> int | None:
    for index, cid in enumerate(returned, 1):
        if cid in relevant:
            return index
    return None


def dcg_at_5(returned: list[str], relevant: set[str]) -> float:
    value = 0.0
    for index, cid in enumerate(returned[:5], 1):
        if cid in relevant:
            value += 1.0 / math.log2(index + 1)
    return value


def ndcg_at_5(returned: list[str], relevant: set[str]) -> float:
    ideal_count = min(5, len(relevant))
    if ideal_count == 0:
        return 0.0
    ideal = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_count + 1))
    return dcg_at_5(returned, relevant) / ideal


def rank_metrics(returned: list[str], relevant: set[str]) -> dict[str, Any]:
    returned = returned[:5]
    first = first_relevant_rank(returned, relevant)
    relevant_returned = sum(cid in relevant for cid in returned)
    unacceptable_returned = len(returned) - relevant_returned
    # If there is no acceptable candidate in the list, the entire returned list is an
    # unacceptable prefix from the user's point of view.
    unacceptable_prefix = (first - 1) if first is not None else len(returned)
    return {
        'returned_count': len(returned),
        'acceptable_returned_count': relevant_returned,
        'unacceptable_returned_count': unacceptable_returned,
        'top1_acceptable': bool(returned and returned[0] in relevant),
        'hit_at_5': first is not None,
        'first_acceptable_rank': first,
        'reciprocal_rank': 0.0 if first is None else 1.0 / first,
        'recall_at_5': relevant_returned / max(1, len(relevant)),
        # Precision is intentionally over the candidates actually shown. A calibrated
        # retriever can improve this by returning fewer candidates instead of padding
        # a list with low-confidence neighbours.
        'candidate_list_precision': relevant_returned / len(returned) if returned else 0.0,
        'unacceptable_prefix_count': unacceptable_prefix,
        'ndcg_at_5': ndcg_at_5(returned, relevant),
    }


def aggregate_lane(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    top1 = sum(row['top1_acceptable'] for row in rows)
    hit5 = sum(row['hit_at_5'] for row in rows)
    hit_not_top1 = sum(row['hit_at_5'] and not row['top1_acceptable'] for row in rows)
    hit_rank3plus = sum((row['first_acceptable_rank'] or 99) >= 3 and row['hit_at_5'] for row in rows)
    misses_with_results = sum((not row['hit_at_5']) and row['returned_count'] > 0 for row in rows)
    return {
        'cases': total,
        'top1_acceptable': proportion(top1, total),
        # Historical recall-style signal only. Do not interpret as list quality.
        'hit_at_5_secondary': proportion(hit5, total),
        'hit_at_5_but_not_top1': proportion(hit_not_top1, total),
        'hit_at_rank_3_or_worse': proportion(hit_rank3plus, total),
        'miss_with_nonempty_list': proportion(misses_with_results, total),
        'mean_first_acceptable_rank_hit_cases': (
            round(sum(row['first_acceptable_rank'] for row in rows if row['first_acceptable_rank'] is not None) / hit5, 6)
            if hit5 else None
        ),
        'mean_reciprocal_rank': ratio(sum(row['reciprocal_rank'] for row in rows), total),
        'mean_ndcg_at_5': ratio(sum(row['ndcg_at_5'] for row in rows), total),
        'mean_recall_at_5': ratio(sum(row['recall_at_5'] for row in rows), total),
        'mean_candidate_list_precision': ratio(sum(row['candidate_list_precision'] for row in rows), total),
        'mean_unacceptable_prefix_count': ratio(sum(row['unacceptable_prefix_count'] for row in rows), total),
        'mean_unacceptable_results_returned': ratio(sum(row['unacceptable_returned_count'] for row in rows), total),
        'mean_results_returned': ratio(sum(row['returned_count'] for row in rows), total),
    }


def score_stream(
    stream: str,
    case_ids: list[str],
    elicitation: dict[str, dict[str, Any]],
    adjudication: dict[str, dict[str, Any]],
    outcomes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    statuses = Counter(str(adjudication[case_id]['status']) for case_id in case_ids)
    informative = [case_id for case_id in case_ids if adjudication[case_id]['status'] in {'mapped', 'ambiguous'}]

    relevant_by_case: dict[str, set[str]] = {}
    all_acceptable_by_case: dict[str, set[str]] = {}
    for case_id in informative:
        targets = adjudication[case_id]['acceptable_targets']
        all_acceptable_by_case[case_id] = {str(target['canonical_id']) for target in targets}
        relevant_by_case[case_id] = {
            str(target['canonical_id'])
            for target in targets
            if target['in_frozen_demand_envelope'] is True
        }

    capability_ids = [case_id for case_id in informative if relevant_by_case[case_id]]
    mapped_outside_envelope = [case_id for case_id in informative if not relevant_by_case[case_id]]

    lexical_rows: list[dict[str, Any]] = []
    fallback_rows: list[dict[str, Any]] = []
    detail: list[dict[str, Any]] = []
    rescues = regressions = fallback_top1_improvements = 0
    fallback_hit_no_acceptable_recognition = 0
    recognized_acceptable_cases = selected_acceptable_cases = selected_any_cases = 0

    for case_id in capability_ids:
        relevant = relevant_by_case[case_id]
        outcome = outcomes[case_id]
        lexical = rank_metrics(outcome['lexical_top5_ids'], relevant)
        fallback = rank_metrics(outcome['fallback_top5_ids'], relevant)
        lexical_rows.append(lexical)
        fallback_rows.append(fallback)

        rescues += int(fallback['hit_at_5'] and not lexical['hit_at_5'])
        regressions += int(lexical['hit_at_5'] and not fallback['hit_at_5'])
        fallback_top1_improvements += int(fallback['top1_acceptable'] and not lexical['top1_acceptable'])

        recognized = set(outcome['participant_recognized_ids'])
        recognized_acceptable = bool(recognized & relevant)
        selected = outcome['participant_selected_id']
        selected_acceptable = selected in relevant if selected is not None else False
        recognized_acceptable_cases += int(recognized_acceptable)
        selected_acceptable_cases += int(selected_acceptable)
        selected_any_cases += int(selected is not None)
        fallback_hit_no_acceptable_recognition += int(fallback['hit_at_5'] and not recognized_acceptable)

        detail.append({
            'case_id': case_id,
            'entry_mode': elicitation[case_id]['entry_mode'],
            'status': adjudication[case_id]['status'],
            'acceptable_in_envelope_ids': sorted(relevant),
            'lexical': lexical,
            'fallback': fallback,
            'participant_recognized_acceptable': recognized_acceptable,
            'participant_selected_acceptable': selected_acceptable,
        })

    negative_ids = [
        case_id for case_id in case_ids
        if adjudication[case_id]['status'] in {'clarification-needed', 'unmappable', 'out-of-scope'}
    ]
    lexical_negative_abstentions = sum(not outcomes[case_id]['lexical_top5_ids'] for case_id in negative_ids)
    fallback_negative_abstentions = sum(not outcomes[case_id]['fallback_top5_ids'] for case_id in negative_ids)
    clarification_ids = [case_id for case_id in case_ids if adjudication[case_id]['status'] == 'clarification-needed']
    clarification_offers = sum(outcomes[case_id]['clarification_was_offered'] for case_id in clarification_ids)

    return {
        'stream': stream,
        'cases': len(case_ids),
        'participants': len({elicitation[case_id]['participant_id'] for case_id in case_ids}),
        'status_counts': dict(sorted(statuses.items())),
        'informative_mapped_or_ambiguous_cases': len(informative),
        'capability_cases_with_in_envelope_target': len(capability_ids),
        'mapped_or_ambiguous_without_in_envelope_target': len(mapped_outside_envelope),
        'lexical': aggregate_lane(lexical_rows),
        'fallback': aggregate_lane(fallback_rows),
        'comparison': {
            'fallback_hit5_rescues': rescues,
            'fallback_hit5_regressions': regressions,
            'fallback_top1_improvements': fallback_top1_improvements,
        },
        'participant': {
            'recognized_acceptable_fallback_candidate': proportion(recognized_acceptable_cases, len(capability_ids)),
            'selected_acceptable_candidate': proportion(selected_acceptable_cases, len(capability_ids)),
            'selected_any_candidate': proportion(selected_any_cases, len(capability_ids)),
            'fallback_hit_without_acceptable_recognition': proportion(
                fallback_hit_no_acceptable_recognition, len(capability_ids)
            ),
        },
        'negative_or_unmappable_cases': {
            'cases': len(negative_ids),
            'lexical_abstention': proportion(lexical_negative_abstentions, len(negative_ids)),
            'fallback_abstention': proportion(fallback_negative_abstentions, len(negative_ids)),
            'clarification_needed_cases': len(clarification_ids),
            'clarification_offered': proportion(clarification_offers, len(clarification_ids)),
        },
        'case_detail': detail,
    }


def score_funnel(funnel: dict[str, Any] | None) -> dict[str, Any] | None:
    if funnel is None:
        return None
    out: dict[str, Any] = {
        'measurement_window': funnel['measurement_window'],
        'lexical_failure_definition': funnel['lexical_failure_definition'],
        'streams': {},
    }
    for cohort in funnel['cohorts']:
        stream = cohort['stream']
        eligible = cohort['eligible_lexical_failure_exposures']
        offers = cohort['fallback_offers']
        opens = cohort['fallback_opens']
        submissions = cohort['fallback_submissions']
        selections = cohort['fallback_selections']
        none = cohort['none_selections']
        out['streams'][stream] = {
            'counts': {key: int(cohort[key]) for key in base.FUNNEL_COUNT_FIELDS},
            'offer_rate': proportion(offers, eligible),
            'open_rate_given_offer': proportion(opens, offers),
            'submission_rate_given_open': proportion(submissions, opens),
            'selection_rate_given_submission': proportion(selections, submissions),
            'none_rate_given_submission': proportion(none, submissions),
            'end_to_end_selection_rate': proportion(selections, eligible),
        }
    return out


def score_study(
    preregistration_path: Path,
    elicitation_path: Path,
    adjudication_path: Path,
    manifest_path: Path,
    outcomes_path: Path,
    funnel_path: Path | None = None,
) -> dict[str, Any]:
    # This is the hard stage-order/freeze gate. Do not score loose files.
    verified = verifier.verify(
        preregistration_path,
        elicitation_path,
        adjudication_path,
        manifest_path,
        outcomes_path,
        funnel_path,
    )
    elicitation_rows = base.load_jsonl(elicitation_path)
    elicitation = base.validate_elicitation(elicitation_rows)
    adjudication = base.validate_adjudication(base.load_jsonl(adjudication_path), elicitation)
    outcomes = base.validate_outcomes(base.load_jsonl(outcomes_path), elicitation, adjudication)
    funnel = base.validate_funnel(funnel_path) if funnel_path is not None else None

    streams: dict[str, Any] = {}
    for stream in sorted(base.STREAMS):
        case_ids = sorted(case_id for case_id, row in elicitation.items() if row['stream'] == stream)
        streams[stream] = score_stream(stream, case_ids, elicitation, adjudication, outcomes)

    return {
        'schema_version': 1,
        'study_id': verified['study_id'],
        'preregistration_status': verified['preregistration_status'],
        'metric_contract': {
            'primary_product_quality': [
                'top1_acceptable',
                'mean_reciprocal_rank',
                'mean_ndcg_at_5',
                'mean_unacceptable_prefix_count',
                'mean_candidate_list_precision',
                'negative_case_fallback_abstention',
            ],
            'secondary_historical_recall': 'hit_at_5_secondary',
            'interpretation': (
                'Hit@5 alone is insufficient: an acceptable rank-3 result preceded by two '
                'unacceptable candidates remains a visibly poor list and is reported as such.'
            ),
        },
        'streams': streams,
        'need_prevalence_funnel': score_funnel(funnel),
        'reporting_guards': [
            'Do not pool occupation and skill into one accuracy number.',
            'Do not report prompted/recruited capability cases as production prevalence.',
            'Do not interpret Hit@5 as list quality or user trust.',
            'Fallback miss is not automatically proof that a higher model class is required.',
            'Wilson intervals quantify binomial sampling uncertainty, not recruitment representativeness.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--preregistration', required=True, type=Path)
    parser.add_argument('--elicitation', required=True, type=Path)
    parser.add_argument('--adjudication', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--outcomes', required=True, type=Path)
    parser.add_argument('--funnel', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    result = score_study(
        args.preregistration,
        args.elicitation,
        args.adjudication,
        args.manifest,
        args.outcomes,
        args.funnel,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding='utf-8')
    print(text, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
