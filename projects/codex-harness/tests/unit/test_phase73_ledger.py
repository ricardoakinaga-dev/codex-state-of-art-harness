"""Tests for Phase 7.3 promotion ledger evidence binding."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from generate_phase73_ledger import build_ledger  # noqa: E402

from harness_kernel.boundary import (  # noqa: E402
    BoundaryCollisionError,
    BoundaryError,
    ProjectBoundary,
)
from harness_kernel.persistence import RunStore  # noqa: E402


def test_material_medium_ledger_entry_points_to_its_proof_matrix() -> None:
    inventory = {
        "branches": [
            {
                "branch_id": "P7.3-BRANCH-MATERIAL",
                "risk_level": "medium",
                "file": "src/example.py",
                "function": "example",
                "source_line": 10,
                "branch_target": 'raise BoundaryError("invalid")',
                "category": "PERSISTENCE",
                "risk_reason": "The branch protects a persisted invariant.",
                "materiality": "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE",
                "existing_evidence": ["evidence/phase-7.2/residual-risk-review.md"],
                "closure_requirement": "Preserve the persisted invariant.",
                "closure_status": "TESTED_PASS",
            }
        ]
    }
    ledger = build_ledger(
        inventory,
        {"preflight": {"status": "RESOLVED_READ_ONLY_VERSION_PROBE"}},
        {"scanners": {}},
        {"status": "PASS_WITH_LIMITATIONS"},
    )

    branch_entry = next(
        entry for entry in ledger["entries"] if entry["risk_id"] == "P7.3-BRANCH-MATERIAL"
    )
    assert "material-medium-proof.json" in branch_entry["evidence"]


def test_run_store_rechecks_same_value_after_exclusive_create_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = ProjectBoundary(tmp_path)
    store = RunStore(boundary)
    relative = ".harness/state/runs/RUN-RACE.json"
    value = {"run_id": "RUN-RACE", "status": "RUNNING"}
    real_create = ProjectBoundary.atomic_create_json

    def create_then_report_collision(
        current_boundary: ProjectBoundary,
        current_relative: str,
        current_value: object,
    ) -> Path:
        real_create(current_boundary, current_relative, current_value)  # type: ignore[arg-type]
        raise BoundaryCollisionError("simulated first-writer race")

    monkeypatch.setattr(ProjectBoundary, "atomic_create_json", create_then_report_collision)

    store._write_once_json(  # noqa: SLF001
        relative,
        value,
        corrupt_message="corrupt",
        collision_message="collision",
    )

    assert store.load_record("RUN-RACE") == value


def test_run_store_rejects_different_value_after_exclusive_create_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = ProjectBoundary(tmp_path)
    store = RunStore(boundary)
    relative = ".harness/state/runs/RUN-RACE-MISMATCH.json"
    value = {"run_id": "RUN-RACE-MISMATCH", "status": "RUNNING"}
    real_create = ProjectBoundary.atomic_create_json

    def create_different_value_then_report_collision(
        current_boundary: ProjectBoundary,
        current_relative: str,
        _current_value: object,
    ) -> Path:
        real_create(
            current_boundary,
            current_relative,
            {"run_id": "RUN-RACE-MISMATCH", "status": "COMPLETED"},
        )  # type: ignore[arg-type]
        raise BoundaryCollisionError("simulated first-writer race")

    monkeypatch.setattr(
        ProjectBoundary,
        "atomic_create_json",
        create_different_value_then_report_collision,
    )

    with pytest.raises(BoundaryError, match="collision"):
        store._write_once_json(  # noqa: SLF001
            relative,
            value,
            corrupt_message="corrupt",
            collision_message="collision",
        )
