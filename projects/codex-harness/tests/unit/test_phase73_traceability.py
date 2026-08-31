"""Tests for applying Phase 7.3 targeted behavioral evidence to traceability."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from generate_phase73_traceability import (  # noqa: E402
    TraceabilityEvidenceError,
    apply_phase73_evidence,
)


def _trace() -> dict[str, object]:
    return {
        "records": [
            {
                "branch_id": "P7.3-BRANCH-ONE",
                "risk_level": "medium",
                "mapping_strength": "NO_DIRECT_TEST_MAPPING",
                "test_result": "NO_DIRECT_RESULT",
                "tests": [],
                "coverage_result": "RESIDUAL_BRANCH_NOT_DIRECTLY_COVERED",
            }
        ]
    }


def _evidence() -> dict[str, object]:
    return {
        "records": [
            {
                "branch_id": "P7.3-BRANCH-ONE",
                "mapping_strength": "BEHAVIORAL_TARGETED_OR_REGRESSION",
                "test_result": "PASS",
                "evidence_note": (
                    "The test asserts the fail-closed contract at the residual target."
                ),
                "tests": [
                    {
                        "test_id": "P73-T-ONE",
                        "path": "tests/unit/test_phase73_material_assurance.py",
                        "nodeid": "tests/unit/test_phase73_material_assurance.py::test_one",
                        "result": "PASS",
                        "relation": "targeted behavioral evidence",
                    }
                ],
            }
        ]
    }


def test_applies_targeted_evidence_without_claiming_direct_arc_coverage() -> None:
    traceability = apply_phase73_evidence(_trace(), _evidence())

    record = traceability["records"][0]  # type: ignore[index]
    assert record["mapping_strength"] == "BEHAVIORAL_TARGETED_OR_REGRESSION"
    assert record["test_result"] == "PASS"
    assert record["coverage_result"] == "RESIDUAL_BRANCH_NOT_DIRECTLY_COVERED"
    assert record["phase73_evidence"] == [
        "The test asserts the fail-closed contract at the residual target."
    ]
    assert traceability["summary"]["mapping_strength_counts"] == {  # type: ignore[index]
        "BEHAVIORAL_TARGETED_OR_REGRESSION": 1
    }


def test_rejects_unknown_or_empty_behavioral_evidence() -> None:
    unknown = _evidence()
    unknown["records"][0]["branch_id"] = "P7.3-BRANCH-UNKNOWN"  # type: ignore[index]

    with pytest.raises(TraceabilityEvidenceError, match="unknown"):
        apply_phase73_evidence(_trace(), unknown)

    empty = _evidence()
    empty["records"][0]["tests"] = []  # type: ignore[index]
    with pytest.raises(TraceabilityEvidenceError, match="tests"):
        apply_phase73_evidence(_trace(), empty)
