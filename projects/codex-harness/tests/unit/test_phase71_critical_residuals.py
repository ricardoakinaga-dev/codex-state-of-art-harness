from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from test_contracts import profile
from test_phase4_execution import FakeHost, _fixture

from harness_kernel import cli, phase3_loader, phase4_execution, phase6_stop
from harness_kernel.boundary import BoundaryError, ProjectBoundary
from harness_kernel.classification import classify_task
from harness_kernel.phase4_execution import InvocationEngine, ReplayLedgerError
from harness_kernel.phase4_models import ExecutionMode, Phase4Budget
from harness_kernel.phase5_pilot import Phase5PilotInputError, load_task
from harness_kernel.serialization import to_dict


def test_stop_unique_deduplicates_invalid_values_without_changing_input() -> None:
    values = ("missing", "missing", "", 1)  # type: ignore[tuple-item]

    assert phase6_stop._unique(values) == ("missing",)
    assert values == ("missing", "missing", "", 1)


def test_loader_bounded_unique_enforces_limit_and_deduplicates() -> None:
    assert phase3_loader._bounded_unique(("a", "a", "b"), limit=3, label="refs") == (
        "a",
        "b",
    )

    with pytest.raises(phase3_loader.LoaderError, match="refs count bound exceeded"):
        phase3_loader._bounded_unique(("a", "b", "c"), limit=2, label="refs")


def test_cli_config_rejects_unsupported_schema_version() -> None:
    result = cli._config_result({"schema_version": "HK-UNKNOWN"})

    assert not result.is_valid
    assert any(finding.code is cli.ValidationCode.INVALID_VERSION for finding in result.findings)


def test_classification_accepts_a_serialized_task_profile_mapping() -> None:
    serialized = to_dict(profile())

    result = classify_task(serialized)

    assert result.task_id == "TASK-1"
    assert result.objective == "validate a contract"


def test_classification_accepts_a_plain_mapping_without_profile_schema() -> None:
    result = classify_task(
        {"objective": "validate a local contract", "requested_outcome": "report"},
        task_id="TASK-P7.1-MAPPING",
        run_id="RUN-P7.1-MAPPING",
    )

    assert result.objective == "validate a local contract"
    assert result.requested_outcome == "report"


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": "wrong", "entries": {}},
        {
            "schema_version": "P4-LEDGER-1",
            "entries": {"INV-1": {"idempotency_key": 1, "request_digest": "sha256:x"}},
        },
    ],
)
def test_replay_ledger_rejects_invalid_schema_and_entry_binding(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    ledger = tmp_path / "invocation-ledger.json"
    ledger.write_text(json.dumps(payload), encoding="utf-8")
    directory_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        with pytest.raises(ReplayLedgerError):
            phase4_execution._load_ledger(ledger, directory_fd=directory_fd)
    finally:
        os.close(directory_fd)


def test_replay_reservation_rejects_duplicate_idempotency_key_from_persisted_entry(
    tmp_path: Path,
) -> None:
    record, inventory, resolution, policy = _fixture(tmp_path)
    ledger = tmp_path / ".harness" / "phase4" / "invocation-ledger.json"
    engine = InvocationEngine(FakeHost(), replay_ledger=ledger)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P7.1-REPLAY-RESIDUAL",
        run_id="RUN-P7.1-REPLAY-RESIDUAL",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert prepared.request is not None
    assert engine._reserve_replay(prepared.request) is None
    engine._used_real_invocations.clear()
    second = replace(
        prepared.request,
        invocation_id="INV-P7.1-SECOND",
        idempotency_key="IDEM-P7.1-SECOND",
    )

    assert engine._reserve_replay(second) is None
    engine._used_real_invocations.clear()
    third = replace(second, invocation_id="INV-P7.1-THIRD")

    assert engine._reserve_replay(third) == "REPLAY_DETECTED"


def test_replay_ledger_anchor_rejects_invalid_schema(tmp_path: Path) -> None:
    anchor = tmp_path / "anchor.json"
    anchor.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")
    directory_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        with pytest.raises(ReplayLedgerError, match="anchor schema is invalid"):
            phase4_execution._load_ledger_anchor(directory_fd, anchor.name)
    finally:
        os.close(directory_fd)


def test_project_boundary_atomic_write_rejects_non_bytes_and_oversize(tmp_path: Path) -> None:
    boundary = ProjectBoundary(tmp_path, max_file_bytes=3)

    with pytest.raises(BoundaryError, match="bytes"):
        boundary.atomic_write_bytes("output.bin", "not-bytes")  # type: ignore[arg-type]
    with pytest.raises(BoundaryError, match="size limit"):
        boundary.atomic_write_bytes("output.bin", b"toolong")
    assert not (tmp_path / "output.bin").exists()


def test_phase5_task_loader_rejects_unsupported_schema_before_processing(tmp_path: Path) -> None:
    task_path = tmp_path / "task.json"
    task_path.write_text(json.dumps({"schema_version": "P5-TASK-UNKNOWN"}), encoding="utf-8")

    with pytest.raises(Phase5PilotInputError, match="unsupported Phase 5 task schema"):
        load_task(task_path, project_root=tmp_path)
