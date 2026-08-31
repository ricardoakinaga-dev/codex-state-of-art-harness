"""Tests for the branch-local Phase 7.3 materiality review artifact."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from generate_phase73_materiality_review import (  # noqa: E402
    MaterialityReviewError,
    build_review,
    validate_review,
)


def _branch(
    branch_id: str,
    *,
    risk_level: str,
    materiality: str,
    closure_status: str,
) -> dict[str, object]:
    return {
        "branch_id": branch_id,
        "risk_level": risk_level,
        "file": "src/harness_kernel/example.py",
        "function": "example",
        "source_line": 10,
        "target_line": 11,
        "condition": "if invalid:",
        "branch_target": 'raise ValueError("invalid")',
        "category": "OTHER",
        "risk_reason": "The branch requires an explicit semantic review.",
        "materiality": materiality,
        "closure_status": closure_status,
        "existing_evidence": ["evidence/phase-7.2/README.md"],
        "closure_requirement": "Preserve the bounded contract.",
    }


def _fixture() -> tuple[dict[str, object], dict[str, object]]:
    nonmaterial = _branch(
        "P7.3-BRANCH-NONMATERIAL",
        risk_level="medium",
        materiality="NON_MATERIAL_DEFENSIVE",
        closure_status="ACCEPTED_NON_MATERIAL",
    )
    material = _branch(
        "P7.3-BRANCH-MATERIAL",
        risk_level="medium",
        materiality="MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE",
        closure_status="TESTED_PASS",
    )
    high = _branch(
        "P7.3-BRANCH-HIGH",
        risk_level="high",
        materiality="MATERIAL_PROMOTION_RELEVANT",
        closure_status="OPEN_PROMOTION_BLOCKER",
    )
    inventory = {"branches": [nonmaterial, material, high]}
    decisions = {
        "decisions": {
            branch["branch_id"]: {
                "materiality": branch["materiality"],
                "closure_status": branch["closure_status"],
                "decision_reason": (
                    f"{branch['branch_id']} was assessed against its exact source branch."
                ),
                "existing_evidence": branch["existing_evidence"],
            }
            for branch in (nonmaterial, material, high)
        }
    }
    return inventory, decisions


def test_review_records_exact_context_and_nonmaterial_exclusion_controls() -> None:
    inventory, decisions = _fixture()

    review = build_review(inventory, decisions)

    records = {item["branch_id"]: item for item in review["records"]}  # type: ignore[index]
    nonmaterial = records["P7.3-BRANCH-NONMATERIAL"]
    assert nonmaterial["source_context"] == {
        "condition": "if invalid:",
        "file": "src/harness_kernel/example.py",
        "function": "example",
        "source_line": 10,
        "target": 'raise ValueError("invalid")',
        "target_line": 11,
    }
    evidence = nonmaterial["materiality_evidence"]
    assert evidence["classification"] == "NON_MATERIAL_DEFENSIVE"
    assert set(evidence["excluded_effects"]) == {
        "authority",
        "evidence_integrity",
        "external_io",
        "filesystem",
        "persistence",
        "side_effect",
    }
    assert "P7.3-BRANCH-NONMATERIAL" in evidence["branch_local_reason"]
    assert review["summary"] == {
        "high": 1,
        "medium": 2,
        "records": 3,
        "accepted_nonmaterial": 1,
        "promotion_relevant": 2,
    }


def test_review_rejects_nonmaterial_evidence_without_every_excluded_effect() -> None:
    inventory, decisions = _fixture()
    review = build_review(inventory, decisions)
    records = review["records"]
    assert isinstance(records, list)
    nonmaterial = next(item for item in records if item["materiality"] == "NON_MATERIAL_DEFENSIVE")
    evidence = nonmaterial["materiality_evidence"]
    assert isinstance(evidence, dict)
    evidence["excluded_effects"] = ["side_effect"]

    with pytest.raises(MaterialityReviewError, match="excluded_effects"):
        validate_review(review)


def test_review_rejects_decision_and_inventory_materiality_drift() -> None:
    inventory, decisions = _fixture()
    decisions_value = decisions["decisions"]
    assert isinstance(decisions_value, dict)
    decisions_value["P7.3-BRANCH-MATERIAL"]["closure_status"] = "ACCEPTED_NON_MATERIAL"

    with pytest.raises(MaterialityReviewError, match="does not match inventory"):
        build_review(inventory, decisions)
