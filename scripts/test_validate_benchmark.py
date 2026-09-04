#!/usr/bin/env python3
"""Contract tests for validate_benchmark.py; no network or third-party deps."""

from __future__ import annotations

import copy
import unittest

from validate_benchmark import validate_case


def evidence(provenance: str = "canonical", role: str = "destination_ground_truth") -> dict:
    return {"source": "fixture", "provenance": provenance, "role": role}


def base_case() -> dict:
    return {
        "id": "yv.exact.fixture",
        "taxonomy_version": 31,
        "product": "YV",
        "query": "Testtitel",
        "query_language": "sv",
        "query_origin": "canonical_label",
        "strata": ["yv_exact_job_title"],
        "expected_intent": "SINGLE",
        "must": [
            {
                "kind": "job-title",
                "concept_id": "job_fixture",
                "occupation_name_id": "occ_fixture",
            }
        ],
        "acceptable": [],
        "must_not": [],
        "source_evidence": [evidence()],
        "adjudication": {
            "status": "AUTO_HIGH_CONFIDENCE",
            "reviewer_count": 0,
            "agreement": "UNREVIEWED",
        },
    }


class BenchmarkContractTest(unittest.TestCase):
    def assert_valid(self, case: dict) -> None:
        self.assertEqual([], validate_case(case))

    def assert_invalid_with(self, case: dict, fragment: str) -> None:
        errors = validate_case(case)
        self.assertTrue(any(fragment in error for error in errors), errors)

    def test_exact_yv_job_title_requires_context_and_is_valid(self) -> None:
        self.assert_valid(base_case())

    def test_job_title_without_occupation_context_fails(self) -> None:
        case = base_case()
        del case["must"][0]["occupation_name_id"]
        self.assert_invalid_with(case, "occupation_name_id")

    def test_kv_cannot_emit_occupation(self) -> None:
        case = base_case()
        case.update({"id": "kv.fixture", "product": "KV"})
        case["must"] = [{"kind": "occupation-name", "concept_id": "occ_fixture"}]
        self.assert_invalid_with(case, "KV may contain only skill")

    def test_kv_skill_is_valid(self) -> None:
        case = base_case()
        case.update({
            "id": "kv.skill.fixture",
            "product": "KV",
            "query": "Testkompetens",
            "strata": ["exact_preferred_label"],
        })
        case["must"] = [{"kind": "skill", "concept_id": "skill_fixture"}]
        self.assert_valid(case)

    def test_ambiguous_query_requires_multiple_positive_identities(self) -> None:
        case = base_case()
        case.update({
            "id": "yv.ambiguous.fixture",
            "query_origin": "manual",
            "expected_intent": "AMBIGUOUS",
            "adjudication": {"status": "HUMAN_DOUBLE", "reviewer_count": 2, "agreement": "AGREED"},
            "source_evidence": [evidence("human_judgment")],
        })
        self.assert_invalid_with(case, "at least two positive identities")
        case["acceptable"] = [
            {"kind": "job-title", "concept_id": "job_fixture", "occupation_name_id": "occ_fixture_2"}
        ]
        self.assert_valid(case)

    def test_same_job_title_in_two_occupation_contexts_stays_two_identities(self) -> None:
        case = base_case()
        case.update({
            "id": "yv.context.fixture",
            "query_origin": "manual",
            "expected_intent": "AMBIGUOUS",
            "adjudication": {"status": "HUMAN_DOUBLE", "reviewer_count": 2, "agreement": "AGREED"},
            "source_evidence": [evidence("human_judgment")],
        })
        case["must"] = [
            {"kind": "job-title", "concept_id": "same_job", "occupation_name_id": "occ_a"},
            {"kind": "job-title", "concept_id": "same_job", "occupation_name_id": "occ_b"},
        ]
        self.assert_valid(case)

    def test_no_match_requires_empty_positive_sets_and_abstention(self) -> None:
        case = base_case()
        case.update({
            "id": "yv.no-match.fixture",
            "query_origin": "manual",
            "expected_intent": "NO_MATCH",
            "must": [],
            "source_evidence": [evidence("human_judgment")],
            "adjudication": {"status": "HUMAN_DOUBLE", "reviewer_count": 2, "agreement": "AGREED"},
        })
        self.assert_invalid_with(case, "allow_abstention=true")
        case["allow_abstention"] = True
        self.assert_valid(case)

    def test_model_enrichment_cannot_be_ground_truth(self) -> None:
        case = base_case()
        case["source_evidence"] = [evidence("model_derived")]
        self.assert_invalid_with(case, "cannot be destination ground truth")

    def test_observed_query_cannot_be_auto_labelled(self) -> None:
        case = base_case()
        case["query_origin"] = "observed_query"
        self.assert_invalid_with(case, "AUTO_HIGH_CONFIDENCE is limited")

    def test_human_adjudication_requires_explicit_human_truth(self) -> None:
        case = base_case()
        case["query_origin"] = "manual"
        case["adjudication"] = {"status": "HUMAN_SINGLE", "reviewer_count": 1, "agreement": "AGREED"}
        self.assert_invalid_with(case, "explicit human_judgment")
        case["source_evidence"] = [evidence("human_judgment")]
        self.assert_valid(case)

    def test_positive_and_negative_sets_are_disjoint(self) -> None:
        case = base_case()
        case["must_not"] = [copy.deepcopy(case["must"][0])]
        self.assert_invalid_with(case, "must and must_not must be disjoint")

    def test_must_count_cannot_exceed_top_k(self) -> None:
        case = base_case()
        case.update({
            "id": "yv.top-k.fixture",
            "query_origin": "manual",
            "expected_intent": "AMBIGUOUS",
            "top_k": 1,
            "source_evidence": [evidence("human_judgment")],
            "adjudication": {"status": "HUMAN_DOUBLE", "reviewer_count": 2, "agreement": "AGREED"},
        })
        case["must"] = [
            {"kind": "occupation-name", "concept_id": "occ_a"},
            {"kind": "occupation-name", "concept_id": "occ_b"},
        ]
        self.assert_invalid_with(case, "cannot exceed top_k")


if __name__ == "__main__":
    unittest.main()
