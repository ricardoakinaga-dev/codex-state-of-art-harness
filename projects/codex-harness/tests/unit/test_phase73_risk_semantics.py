"""Contract tests for the Phase 7.3 explicit risk semantics."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from phase73_risk_semantics import (  # noqa: E402
    RiskSemanticError,
    semantic_counts,
    validate_count_consistency,
    validate_inventory_records,
)


def _record(
    *,
    branch_id: str,
    risk_level: str,
    materiality: str,
    closure_status: str,
    existing_evidence: tuple[str, ...] = ("evidence/test.json",),
) -> dict[str, object]:
    return {
        "branch_id": branch_id,
        "file": "src/example.py",
        "function": "example",
        "source_line": 10,
        "branch_target": "return value",
        "category": "PERSISTENCE",
        "risk_reason": "The branch protects a persisted invariant.",
        "materiality": materiality,
        "existing_evidence": list(existing_evidence),
        "closure_requirement": "Direct test or reviewable proof.",
        "closure_status": closure_status,
        "risk_level": risk_level,
    }


def test_counts_distinguish_closed_high_and_material_medium() -> None:
    records = [
        _record(
            branch_id="P7.3-BRANCH-HIGH",
            risk_level="high",
            materiality="MATERIAL_PROMOTION_RELEVANT",
            closure_status="UNREACHABLE_PROVEN",
        ),
        _record(
            branch_id="P7.3-BRANCH-MEDIUM",
            risk_level="medium",
            materiality="MATERIAL_PROMOTION_RELEVANT",
            closure_status="TESTED_PASS",
        ),
    ]

    counts = semantic_counts(records)

    assert counts["total"] == 2
    assert counts["high"] == 1
    assert counts["classified_high"] == 1
    assert counts["open_actionable_high"] == 0
    assert counts["promotion_blocking_high"] == 0
    assert counts["closed_high"] == 1
    assert counts["medium"] == 1
    assert counts["classified_medium"] == 1
    assert counts["material_medium"] == 1
    assert counts["open_actionable_medium"] == 0
    assert counts["promotion_blocking_medium"] == 0
    assert counts["closed_medium"] == 1


def test_non_material_acceptance_is_counted_as_accepted_residual() -> None:
    record = _record(
        branch_id="P7.3-BRANCH-DEFENSIVE",
        risk_level="medium",
        materiality="NON_MATERIAL_DEFENSIVE",
        closure_status="ACCEPTED_NON_MATERIAL",
    )

    counts = semantic_counts([record])

    assert counts["medium"] == 1
    assert counts["material_medium"] == 0
    assert counts["accepted_residual_medium"] == 1
    assert counts["open_actionable_medium"] == 0
    assert counts["promotion_blocking_medium"] == 0


def test_promotion_blocker_is_open_and_not_closed() -> None:
    record = _record(
        branch_id="P7.3-BRANCH-OPEN",
        risk_level="medium",
        materiality="MATERIAL_PROMOTION_RELEVANT",
        closure_status="OPEN_PROMOTION_BLOCKER",
    )

    counts = semantic_counts([record])

    assert counts["open_actionable_medium"] == 1
    assert counts["promotion_blocking_medium"] == 1
    assert counts["closed_medium"] == 0


def test_non_material_acceptance_requires_evidence() -> None:
    record = _record(
        branch_id="P7.3-BRANCH-MISSING-EVIDENCE",
        risk_level="medium",
        materiality="NON_MATERIAL_DEFENSIVE",
        closure_status="ACCEPTED_NON_MATERIAL",
        existing_evidence=(),
    )

    with pytest.raises(RiskSemanticError, match="existing_evidence"):
        validate_inventory_records([record])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("materiality", "UNKNOWN"),
        ("closure_status", "DEFERRED_BLOCKING_PROMOTION"),
        ("risk_level", "critical"),
    ],
)
def test_invalid_semantic_values_are_rejected(field: str, value: str) -> None:
    record = _record(
        branch_id=f"P7.3-BRANCH-INVALID-{field}",
        risk_level="medium",
        materiality="MATERIAL_PROMOTION_RELEVANT",
        closure_status="TESTED_PASS",
    )
    record[field] = value

    with pytest.raises(RiskSemanticError, match=field):
        validate_inventory_records([record])


def test_required_fields_and_unique_branch_ids_are_enforced() -> None:
    first = _record(
        branch_id="P7.3-BRANCH-DUPLICATE",
        risk_level="low",
        materiality="NON_MATERIAL_DEFENSIVE",
        closure_status="ACCEPTED_NON_MATERIAL",
    )
    second = dict(first)

    with pytest.raises(RiskSemanticError, match="branch_id"):
        validate_inventory_records([first, second])

    missing = dict(first)
    del missing["branch_target"]
    with pytest.raises(RiskSemanticError, match="branch_target"):
        validate_inventory_records([missing])


def test_all_promotion_surfaces_must_have_identical_semantic_counts() -> None:
    counts = {
        "total": 2,
        "high": 1,
        "medium": 1,
        "low": 0,
        "classified_high": 1,
        "classified_medium": 1,
        "classified_low": 0,
        "open_actionable_high": 0,
        "open_actionable_medium": 0,
        "promotion_blocking_high": 0,
        "promotion_blocking_medium": 0,
        "closed_high": 1,
        "closed_medium": 1,
        "material_medium": 1,
        "accepted_residual_medium": 0,
        "blocked_medium": 0,
    }

    validate_count_consistency(
        inventory=counts,
        risk_map=counts,
        readiness=counts,
        ledger=counts,
        report=counts,
    )

    mismatched_readiness = dict(counts)
    mismatched_readiness["medium"] = 2
    with pytest.raises(RiskSemanticError, match="readiness"):
        validate_count_consistency(
            inventory=counts,
            risk_map=counts,
            readiness=mismatched_readiness,
            ledger=counts,
            report=counts,
        )
