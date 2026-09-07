#!/usr/bin/env python3
"""Self-test the human study scorecard, especially Hit@5-vs-list-quality semantics."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import freeze_human_description_study_manifest as freezer
import score_human_description_study as scorer
import selftest_human_description_preregistration as prereg_fixture
import selftest_human_description_study as staged_fixture


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        elicitation_path, adjudication_path, _, outcomes_path, funnel_path = staged_fixture.build_valid_files(root)
        preregistration_path = root / 'preregistration.json'
        manifest_path = root / 'scorecard-frozen-manifest.json'
        preregistration_path.write_text(
            json.dumps(prereg_fixture.valid_preregistration(), indent=2) + '\n',
            encoding='utf-8',
        )

        # Construct the exact product-quality failure we want the scorecard to expose:
        # occupation target is present at rank 3, but two unacceptable results precede it.
        outcomes = [json.loads(line) for line in outcomes_path.read_text(encoding='utf-8').splitlines() if line.strip()]
        for row in outcomes:
            if row['case_id'] == 'case-occ':
                row['fallback_top5_ids'] = ['occ-noise-a', 'occ-noise-b', 'occ-1', 'occ-noise-c']
                row['participant_recognized_ids'] = ['occ-1']
                row['participant_selected_id'] = 'occ-1'
        staged_fixture.write_jsonl(outcomes_path, outcomes)

        freezer.freeze_manifest(
            preregistration_path,
            elicitation_path,
            adjudication_path,
            manifest_path,
        )
        result = scorer.score_study(
            preregistration_path,
            elicitation_path,
            adjudication_path,
            manifest_path,
            outcomes_path,
            funnel_path,
        )

        occ = result['streams']['occupation']
        assert occ['fallback']['cases'] == 1
        assert occ['fallback']['hit_at_5_secondary']['successes'] == 1
        assert occ['fallback']['top1_acceptable']['successes'] == 0
        assert occ['fallback']['hit_at_rank_3_or_worse']['successes'] == 1
        assert occ['fallback']['mean_first_acceptable_rank_hit_cases'] == 3.0
        assert occ['fallback']['mean_reciprocal_rank'] == 0.333333
        assert occ['fallback']['mean_unacceptable_prefix_count'] == 2.0
        assert occ['fallback']['mean_unacceptable_results_returned'] == 3.0
        assert occ['fallback']['mean_candidate_list_precision'] == 0.25
        assert occ['comparison']['fallback_hit5_rescues'] == 1
        assert occ['participant']['recognized_acceptable_fallback_candidate']['successes'] == 1
        assert occ['participant']['selected_acceptable_candidate']['successes'] == 1

        skill = result['streams']['skill']
        assert skill['fallback']['top1_acceptable']['successes'] == 1
        assert skill['fallback']['hit_at_5_secondary']['successes'] == 1
        assert skill['fallback']['mean_unacceptable_prefix_count'] == 0.0
        assert skill['participant']['fallback_hit_without_acceptable_recognition']['successes'] == 1

        funnel = result['need_prevalence_funnel']['streams']
        assert funnel['occupation']['submission_rate_given_open']['successes'] == 6
        assert funnel['occupation']['submission_rate_given_open']['total'] == 8
        assert funnel['occupation']['end_to_end_selection_rate']['successes'] == 4
        assert funnel['occupation']['end_to_end_selection_rate']['total'] == 20

        assert result['metric_contract']['secondary_historical_recall'] == 'hit_at_5_secondary'
        assert 'top1_acceptable' in result['metric_contract']['primary_product_quality']

    print('human-description rank-sensitive scorecard self-test: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
