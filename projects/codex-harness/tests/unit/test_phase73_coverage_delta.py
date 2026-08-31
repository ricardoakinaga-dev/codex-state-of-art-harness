"""Tests for the explicit Phase 7.3 coverage-set reconciliation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from generate_phase73_coverage_delta import (  # noqa: E402
    CoverageDeltaError,
    build_delta,
)


def _branch(branch_id: str, risk_level: str = "medium") -> dict[str, object]:
    return {
        "branch_id": branch_id,
        "risk_level": risk_level,
        "file": "src/example.py",
        "function": "example",
        "source_line": 10,
        "target": "return value",
    }


def test_delta_records_exact_removed_and_added_identities() -> None:
    delta = build_delta(
        {"branches": [_branch("P7.2-REMOVED", "low"), _branch("P7.2-SAME")]},
        {"branches": [_branch("P7.2-SAME"), _branch("P7.2-ADDED", "high")]},
        coverage_artifact="evidence/phase-7.3/coverage-final.json",
    )

    assert delta["counts"] == {
        "authoritative": {"high": 0, "medium": 1, "low": 1, "total": 2},
        "current": {"high": 1, "medium": 1, "low": 0, "total": 2},
        "removed": 1,
        "added": 1,
    }
    assert delta["removed_from_authoritative"] == [
        {
            "branch_id": "P7.2-REMOVED",
            "status": "COVERED_BY_FINAL_FRESH_COVERAGE",
            "identity": ["src/example.py", "example", 10, "return value"],
            "evidence": ["evidence/phase-7.3/coverage-final.json"],
        }
    ]
    assert delta["added_to_authoritative"][0]["status"] == "NEW_RESIDUAL_IN_FINAL_FRESH_COVERAGE"


def test_delta_rejects_duplicate_branch_identity() -> None:
    with pytest.raises(CoverageDeltaError, match="duplicate"):
        build_delta(
            {"branches": [_branch("P7.2-DUPLICATE"), _branch("P7.2-DUPLICATE")]},
            {"branches": []},
            coverage_artifact="coverage.json",
        )
