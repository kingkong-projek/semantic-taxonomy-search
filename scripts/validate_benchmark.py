#!/usr/bin/env python3
"""Validate semantic-search benchmark JSONL cases.

The JSON Schema documents shape. This validator adds the cross-field product,
identity and provenance invariants that JSON Schema alone cannot express well.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PRODUCTS = {"YV", "KV"}
INTENTS = {"SINGLE", "AMBIGUOUS", "NO_MATCH"}
QUERY_ORIGINS = {
    "manual", "canonical_label", "canonical_definition", "alternative_label",
    "observed_query", "ad_text", "legacy_label", "synthetic",
}
ADJUDICATION = {"AUTO_HIGH_CONFIDENCE", "MODEL_ADJUDICATED", "HUMAN_SINGLE", "HUMAN_DOUBLE", "PENDING"}
PROVENANCE = {
    "canonical", "canonical_history", "curated_relation", "derived_af",
    "behavioral", "corpus_derived", "model_derived", "model_judgment",
    "synthetic", "human_judgment",
}
EVIDENCE_ROLES = {"query_origin", "destination_ground_truth", "product_admission", "context_only", "hard_negative"}
GROUND_TRUTH_PROVENANCE = {"canonical", "curated_relation", "human_judgment", "model_judgment"}
REQUIRED = {
    "id", "taxonomy_version", "product", "query", "query_language", "query_origin",
    "strata", "expected_intent", "must", "acceptable", "must_not",
    "source_evidence", "adjudication",
}


def identity_key(identity: dict[str, Any]) -> tuple[str, ...]:
    kind = str(identity.get("kind") or "")
    concept_id = str(identity.get("concept_id") or "")
    if kind == "job-title":
        return kind, concept_id, str(identity.get("occupation_name_id") or "")
    return kind, concept_id


def require_string(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: must be a non-empty string")


def validate_identity(identity: Any, product: str, path: str, errors: list[str]) -> None:
    if not isinstance(identity, dict):
        errors.append(f"{path}: identity must be an object")
        return
    kind = identity.get("kind")
    if kind not in {"occupation-name", "job-title", "skill"}:
        errors.append(f"{path}.kind: unsupported identity kind {kind!r}")
        return
    require_string(identity.get("concept_id"), f"{path}.concept_id", errors)
    if product == "YV" and kind not in {"occupation-name", "job-title"}:
        errors.append(f"{path}: YV may contain only occupation-name/job-title destinations")
    if product == "KV" and kind != "skill":
        errors.append(f"{path}: KV may contain only skill destinations")
    if kind == "job-title":
        require_string(identity.get("occupation_name_id"), f"{path}.occupation_name_id", errors)
    elif "occupation_name_id" in identity:
        errors.append(f"{path}: occupation_name_id is valid only for job-title identities")


def validate_evidence(evidence: Any, path: str, errors: list[str]) -> None:
    if not isinstance(evidence, dict):
        errors.append(f"{path}: evidence must be an object")
        return
    require_string(evidence.get("source"), f"{path}.source", errors)
    provenance = evidence.get("provenance")
    role = evidence.get("role")
    if provenance not in PROVENANCE:
        errors.append(f"{path}.provenance: unsupported value {provenance!r}")
    if role not in EVIDENCE_ROLES:
        errors.append(f"{path}.role: unsupported value {role!r}")
    if role == "destination_ground_truth" and provenance not in GROUND_TRUTH_PROVENANCE:
        errors.append(
            f"{path}: {provenance!r} cannot be destination ground truth; "
            "use canonical/curated_relation, explicit human_judgment, or explicit model_judgment"
        )
    if role == "product_admission" and provenance != "behavioral":
        errors.append(
            f"{path}: product_admission must preserve the published product/read-model provenance as behavioral"
        )


def validate_case(case: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(case, dict):
        return ["case: must be an object"]

    missing = sorted(REQUIRED - set(case))
    if missing:
        errors.append("missing required fields: " + ", ".join(missing))

    require_string(case.get("id"), "id", errors)
    version = case.get("taxonomy_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        errors.append("taxonomy_version: must be a positive integer")

    product = case.get("product")
    if product not in PRODUCTS:
        errors.append(f"product: must be one of {sorted(PRODUCTS)}")
        product = ""
    require_string(case.get("query"), "query", errors)
    require_string(case.get("query_language"), "query_language", errors)
    if case.get("query_origin") not in QUERY_ORIGINS:
        errors.append(f"query_origin: unsupported value {case.get('query_origin')!r}")

    strata = case.get("strata")
    if not isinstance(strata, list) or not strata:
        errors.append("strata: must be a non-empty array")
    elif len(set(map(str, strata))) != len(strata):
        errors.append("strata: values must be unique")

    intent = case.get("expected_intent")
    if intent not in INTENTS:
        errors.append(f"expected_intent: must be one of {sorted(INTENTS)}")

    buckets: dict[str, list[Any]] = {}
    for bucket in ("must", "acceptable", "must_not"):
        values = case.get(bucket)
        if not isinstance(values, list):
            errors.append(f"{bucket}: must be an array")
            buckets[bucket] = []
            continue
        buckets[bucket] = values
        seen: set[tuple[str, ...]] = set()
        for index, identity in enumerate(values):
            validate_identity(identity, product, f"{bucket}[{index}]", errors)
            if isinstance(identity, dict):
                key = identity_key(identity)
                if key in seen:
                    errors.append(f"{bucket}: duplicate identity {key}")
                seen.add(key)

    keys = {
        name: {identity_key(value) for value in values if isinstance(value, dict)}
        for name, values in buckets.items()
    }
    if keys["must"] & keys["acceptable"]:
        errors.append("must and acceptable must be disjoint")
    if keys["must"] & keys["must_not"]:
        errors.append("must and must_not must be disjoint")
    if keys["acceptable"] & keys["must_not"]:
        errors.append("acceptable and must_not must be disjoint")

    positive_count = len(keys["must"] | keys["acceptable"])
    if intent == "SINGLE" and len(keys["must"]) != 1:
        errors.append("SINGLE intent requires exactly one MUST identity")
    elif intent == "AMBIGUOUS" and positive_count < 2:
        errors.append("AMBIGUOUS intent requires at least two positive identities")
    elif intent == "NO_MATCH":
        if positive_count:
            errors.append("NO_MATCH intent requires empty MUST and ACCEPTABLE")
        if case.get("allow_abstention") is not True:
            errors.append("NO_MATCH intent requires allow_abstention=true")

    top_k = case.get("top_k", 10)
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 100:
        errors.append("top_k: must be an integer in [1, 100]")
    elif len(keys["must"]) > top_k:
        errors.append("number of MUST identities cannot exceed top_k")

    evidence = case.get("source_evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("source_evidence: must be a non-empty array")
        evidence = []
    for index, item in enumerate(evidence):
        validate_evidence(item, f"source_evidence[{index}]", errors)

    adjudication = case.get("adjudication")
    status = None
    if not isinstance(adjudication, dict):
        errors.append("adjudication: must be an object")
    else:
        status = adjudication.get("status")
        if status not in ADJUDICATION:
            errors.append(f"adjudication.status: unsupported value {status!r}")
        reviewers = adjudication.get("reviewer_count", 0)
        if not isinstance(reviewers, int) or isinstance(reviewers, bool) or reviewers < 0:
            errors.append("adjudication.reviewer_count: must be a non-negative integer")
            reviewers = 0
        if status == "HUMAN_SINGLE" and reviewers < 1:
            errors.append("HUMAN_SINGLE requires reviewer_count >= 1")
        if status == "HUMAN_DOUBLE" and reviewers < 2:
            errors.append("HUMAN_DOUBLE requires reviewer_count >= 2")
        if status == "MODEL_ADJUDICATED" and reviewers != 0:
            errors.append("MODEL_ADJUDICATED uses reviewer_count=0; the model is recorded through provenance, not as a human reviewer")

    has_human_truth = any(
        isinstance(item, dict)
        and item.get("role") == "destination_ground_truth"
        and item.get("provenance") == "human_judgment"
        for item in evidence
    )
    has_model_truth = any(
        isinstance(item, dict)
        and item.get("role") == "destination_ground_truth"
        and item.get("provenance") == "model_judgment"
        for item in evidence
    )
    has_source_truth = any(
        isinstance(item, dict)
        and item.get("role") == "destination_ground_truth"
        and item.get("provenance") in {"canonical", "curated_relation"}
        for item in evidence
    )
    has_product_admission = any(
        isinstance(item, dict)
        and item.get("role") == "product_admission"
        and item.get("provenance") == "behavioral"
        for item in evidence
    )

    if status in {"HUMAN_SINGLE", "HUMAN_DOUBLE"} and not has_human_truth:
        errors.append(f"{status} requires explicit human_judgment destination_ground_truth evidence")
    if status == "MODEL_ADJUDICATED" and not has_model_truth:
        errors.append("MODEL_ADJUDICATED requires explicit model_judgment destination_ground_truth evidence")
    if status == "AUTO_HIGH_CONFIDENCE":
        if case.get("query_origin") not in {"canonical_label", "canonical_definition", "alternative_label"}:
            errors.append("AUTO_HIGH_CONFIDENCE is limited to canonical labels, canonical definitions and alternative-label query origins")
        if not has_source_truth:
            errors.append("AUTO_HIGH_CONFIDENCE requires canonical/curated destination_ground_truth evidence")
    if status != "PENDING" and intent != "NO_MATCH" and not (has_human_truth or has_model_truth or has_source_truth):
        errors.append("scored positive case requires auditable source, human, or model judgment destination_ground_truth evidence")
    if product == "YV" and status != "PENDING" and positive_count > 0 and not has_product_admission:
        errors.append("scored positive YV case requires explicit behavioral product_admission evidence")

    return errors


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{line_number}: invalid JSON: {exc}")
                continue
            case_id = case.get("id") if isinstance(case, dict) else None
            if isinstance(case_id, str):
                if case_id in seen_ids:
                    errors.append(f"{path}:{line_number}: duplicate case id {case_id!r}")
                seen_ids.add(case_id)
            for error in validate_case(case):
                errors.append(f"{path}:{line_number}: {error}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    errors = [error for path in args.paths for error in validate_file(path)]
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"validated {len(args.paths)} benchmark file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
