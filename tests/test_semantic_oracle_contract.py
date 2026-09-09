import hashlib
import json
import sys
import unittest

sys.path.insert(0, "scripts")

import evaluate_p80_display_semantic_oracle as oracle


class SemanticOracleContractTest(unittest.TestCase):
    def setUp(self):
        self.by_id = {
            f"c{i}": {
                "preferred_label": f"Yrke {i}",
                "alternative_labels": [f"Alt {i}"],
                "definition": f"Definition för yrke {i} med källbunden arbetsbeskrivning.",
            }
            for i in range(1, 6)
        }
        self.phrase_map = {f"c{i}": [f"arbetsuppgift {i}"] for i in range(1, 6)}
        self.case = {
            "ad_id": "ad-1",
            "query_sha256": "0123456789abcdef" * 4,
            "query": "jag gör ett konkret arbete",
            "concept_id": "c4",  # structured target: must never be serialized to teacher
            "ssyk_code_2012": "9999",  # must never be serialized to teacher
            "candidates": [
                {"concept_id": "c1", "rank": 1},
                {"concept_id": "c2", "rank": 2},
                {"concept_id": "c3", "rank": 3},
                {"concept_id": "c4", "rank": 4},
                {"concept_id": "c5", "rank": 5},
            ],
        }

    def test_teacher_payload_has_no_rank_target_or_ssyk_fields(self):
        payload = oracle.shuffled_payload(self.case, self.by_id, self.phrase_map)
        wire = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertNotIn('"rank"', wire)
        self.assertNotIn('"concept_id": "c4", "query"', wire)  # target is not a case-level label
        self.assertNotIn("ssyk", wire.casefold())
        self.assertEqual(set(payload), {"case_key", "query", "candidates"})
        for candidate in payload["candidates"]:
            self.assertEqual(set(candidate), {"concept_id", "evidence"})

    def test_candidate_order_is_deterministic_hash_order_not_rank_order(self):
        payload = oracle.shuffled_payload(self.case, self.by_id, self.phrase_map)
        key = oracle.case_key(self.case)
        expected = sorted(
            [f"c{i}" for i in range(1, 6)],
            key=lambda cid: hashlib.sha256(
                f"{oracle.PROMPT_VERSION}:{key}:{cid}".encode()
            ).hexdigest(),
        )
        observed = [c["concept_id"] for c in payload["candidates"]]
        self.assertEqual(observed, expected)

    def test_display_contract_keeps_rank1_and_only_drops_lower_confident_drop(self):
        self.assertTrue(oracle.display_keep({"rank": 1, "verdict": "drop"}))
        self.assertTrue(oracle.display_keep({"rank": 4, "verdict": "keep"}))
        self.assertTrue(oracle.display_keep({"rank": 4, "verdict": "uncertain"}))
        self.assertFalse(oracle.display_keep({"rank": 4, "verdict": "drop"}))

    def test_array_and_object_json_envelopes_are_equivalent(self):
        item = {"case_key": "x", "judgments": []}
        def payload(text):
            return {"candidates": [{"content": {"parts": [{"text": text}]}}]}
        self.assertEqual(
            oracle._tolerant_extract_json(payload(json.dumps([item]))),
            {"items": [item]},
        )
        self.assertEqual(
            oracle._tolerant_extract_json(payload(json.dumps({"items": [item]}))),
            {"items": [item]},
        )


if __name__ == "__main__":
    unittest.main()
