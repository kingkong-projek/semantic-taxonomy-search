import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "scripts")

import run_p80_display_semantic_oracle_resumable as runner


class SemanticOracleResumableTest(unittest.TestCase):
    def make_cases(self):
        return [
            {
                "ad_id": "a1",
                "query_sha256": "1" * 64,
                "candidates": [
                    {"rank": 1, "concept_id": "c1"},
                    {"rank": 2, "concept_id": "c2"},
                    {"rank": 3, "concept_id": "c3"},
                    {"rank": 4, "concept_id": "c4"},
                    {"rank": 5, "concept_id": "c5"},
                ],
            },
            {
                "ad_id": "a2",
                "query_sha256": "2" * 64,
                "candidates": [
                    {"rank": 1, "concept_id": "d1"},
                    {"rank": 2, "concept_id": "d2"},
                    {"rank": 3, "concept_id": "d3"},
                    {"rank": 4, "concept_id": "d4"},
                    {"rank": 5, "concept_id": "d5"},
                ],
            },
        ]

    def test_checkpoint_roundtrip_keeps_only_complete_valid_cases(self):
        cases = self.make_cases()
        state = runner.blank_state(cases)
        key = runner.oracle.case_key(cases[0])
        state["judgments"][key] = {
            "c1": "keep", "c2": "drop", "c3": "uncertain", "c4": "drop", "c5": "keep"
        }
        state["judgments"][runner.oracle.case_key(cases[1])] = {"d1": "keep"}  # incomplete => rejected
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "checkpoint.json"
            runner.atomic_json(path, state)
            loaded = runner.load_state(path, cases)
        self.assertEqual(set(loaded["judgments"]), {key})

    def test_case_fingerprint_changes_when_retrieval_candidates_change(self):
        cases = self.make_cases()
        original = runner.case_fingerprint(cases)
        changed = json.loads(json.dumps(cases))
        changed[0]["candidates"][4]["concept_id"] = "other"
        self.assertNotEqual(original, runner.case_fingerprint(changed))

    def test_status_not_evaluable_until_all_cases_complete(self):
        cases = self.make_cases()
        state = runner.blank_state(cases)
        first = runner.oracle.case_key(cases[0])
        state["judgments"][first] = {
            "c1": "keep", "c2": "drop", "c3": "uncertain", "c4": "drop", "c5": "keep"
        }
        status = runner.status_payload(state, cases, phase="running")
        self.assertFalse(status["complete"])
        self.assertFalse(status["decision_gate_evaluable"])
        self.assertEqual(status["completed_cases"], 1)
        self.assertEqual(status["missing_cases"], 1)


if __name__ == "__main__":
    unittest.main()
