from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from test_phase4_execution import FakeHost, _fixture

from harness_kernel import phase4_execution as phase4_execution_module
from harness_kernel.phase4_execution import InvocationEngine, ReplayLedgerError
from harness_kernel.phase4_models import (
    AssuranceDecision,
    ExecutionMode,
    HostInvocationResult,
    HostLoadObservation,
    InvocationLifecycle,
    InvocationResultStatus,
    Phase4Budget,
)


def _prepare(
    tmp_path: Path,
    host: FakeHost | None = None,
    *,
    replay_ledger: Path | None = None,
    expected_fingerprint: str | None = None,
) -> tuple[InvocationEngine, object]:
    record, inventory, resolution, policy = _fixture(tmp_path)
    engine = InvocationEngine(host or FakeHost(), replay_ledger=replay_ledger)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P7.2-P4-ASSURANCE",
        run_id="RUN-P7.2-P4-ASSURANCE",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
        expected_fingerprint=expected_fingerprint,
    )
    return engine, prepared


def _host_result(
    status: InvocationResultStatus,
    *,
    final_message: str | None = "bounded",
) -> HostInvocationResult:
    return HostInvocationResult(
        status=status,
        thread_id="thread-1",
        session_id="session-1",
        turn_id="turn-1",
        host_version="fake",
        events=(),
        final_message=final_message,
        load_observation=HostLoadObservation.UNOBSERVABLE,
        invocation_observed=True,
        execution_observed=True,
        denied_approvals=0,
        cancellation_status="NOT_REQUESTED",
        error_code=None,
        started_at=1_700_000_000,
        completed_at=1_700_000_001,
        host_executable_path="/bin/codex-test",
        host_executable_digest="sha256:" + "a" * 64,
        host_command=("/bin/node-test", "/bin/codex-test"),
        host_interpreter_path="/bin/node-test",
        host_interpreter_digest="sha256:" + "b" * 64,
    )


def test_ledger_path_rejects_relative_override(tmp_path: Path) -> None:
    _engine, prepared = _prepare(tmp_path)
    assert prepared.request is not None

    with pytest.raises(ReplayLedgerError, match="absolute"):
        phase4_execution_module._ledger_path(prepared.request, "relative-ledger.json")


def test_ledger_lock_initializes_anchor_without_a_legacy_ledger(tmp_path: Path) -> None:
    path = tmp_path / ".harness" / "phase4" / "invocation-ledger.json"

    with phase4_execution_module._ledger_lock(path, workspace=tmp_path):
        pass

    anchor = tmp_path / phase4_execution_module._ledger_anchor_name(path, tmp_path)
    assert anchor.is_file()
    assert phase4_execution_module.json.loads(anchor.read_text())["ledger_initialized"] is False


def test_ledger_lock_upgrades_an_anchor_without_a_legacy_file(tmp_path: Path) -> None:
    path = tmp_path / ".harness" / "phase4" / "invocation-ledger.json"
    path.parent.mkdir(parents=True)
    metadata = path.parent.stat()
    anchor = tmp_path / phase4_execution_module._ledger_anchor_name(path, tmp_path)
    anchor.write_text(
        phase4_execution_module.json.dumps(
            {
                "schema_version": phase4_execution_module._LEDGER_ANCHOR_SCHEMA,
                "parent_dev": metadata.st_dev,
                "parent_ino": metadata.st_ino,
                "ledger_initialized": False,
                "ledger_token": None,
            }
        ),
        encoding="utf-8",
    )

    with phase4_execution_module._ledger_lock(path, workspace=tmp_path):
        pass

    assert phase4_execution_module.json.loads(anchor.read_text())["ledger_initialized"] is False


def test_ledger_lock_fails_closed_when_no_follow_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ledger.json"

    class NoopFcntl:
        LOCK_EX = 1
        LOCK_UN = 2

        @staticmethod
        def flock(_descriptor: int, _operation: int) -> None:
            return None

    monkeypatch.setattr(phase4_execution_module, "fcntl", NoopFcntl())
    monkeypatch.setattr(phase4_execution_module, "_open_workspace_descriptor", lambda _path: 101)
    monkeypatch.setattr(
        phase4_execution_module,
        "_open_ledger_parent",
        lambda _path, _workspace, *, workspace_fd: 102,
    )
    monkeypatch.setattr(
        phase4_execution_module,
        "_bind_ledger_parent",
        lambda *_args, **_kwargs: ("anchor", False, "a" * 32),
    )
    monkeypatch.delattr(phase4_execution_module.os, "O_NOFOLLOW", raising=False)

    with (
        pytest.raises(ReplayLedgerError, match="secured"),
        phase4_execution_module._ledger_lock(path, workspace=tmp_path),
    ):
        pass


def test_ledger_lock_closes_workspace_when_parent_open_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_parent(*_args, **_kwargs):
        raise ReplayLedgerError("parent unavailable")

    monkeypatch.setattr(phase4_execution_module, "_open_ledger_parent", fail_parent)
    with (
        pytest.raises(ReplayLedgerError, match="parent unavailable"),
        phase4_execution_module._ledger_lock(tmp_path / "ledger.json", workspace=tmp_path),
    ):
        pass


def test_prepare_rejects_a_fingerprint_confirmation_mismatch(tmp_path: Path) -> None:
    engine, prepared = _prepare(tmp_path, expected_fingerprint="sha256:" + "f" * 64)

    assert prepared.request is None
    assert prepared.preflight.allowed is False
    assert "FINGERPRINT_CONFIRMATION_MISMATCH" in prepared.preflight.blockers
    outcome = engine.execute_prepared(prepared)
    assert outcome.status is InvocationResultStatus.BLOCKED


def test_partial_host_result_routes_to_partial_terminal_state(tmp_path: Path) -> None:
    host = FakeHost(result=_host_result(InvocationResultStatus.PARTIAL))
    engine, prepared = _prepare(tmp_path, host)

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.PARTIAL
    assert outcome.receipt.lifecycle[-2:] == (
        InvocationLifecycle.PARTIAL,
        InvocationLifecycle.CLOSED,
    )


def test_failed_host_result_routes_to_failed_terminal_state(tmp_path: Path) -> None:
    host = FakeHost(result=_host_result(InvocationResultStatus.FAILURE))
    engine, prepared = _prepare(tmp_path, host)

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.FAILURE
    assert outcome.receipt.lifecycle[-2:] == (
        InvocationLifecycle.FAILED,
        InvocationLifecycle.CLOSED,
    )


def test_reserve_replay_rejects_the_same_request_digest(tmp_path: Path) -> None:
    ledger = tmp_path / ".harness" / "phase4" / "invocation-ledger.json"
    engine, prepared = _prepare(tmp_path, replay_ledger=ledger)
    assert prepared.request is not None

    assert engine._reserve_replay(prepared.request) is None
    assert engine._reserve_replay(prepared.request) == "REPLAY_DETECTED"


def test_reserve_replay_rejects_same_invocation_id_with_a_changed_request(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / ".harness" / "phase4" / "invocation-ledger.json"
    engine, prepared = _prepare(tmp_path, replay_ledger=ledger)
    assert prepared.request is not None
    assert engine._reserve_replay(prepared.request) is None

    changed = prepared.request
    object.__setattr__(changed, "task", "tampered request")
    restarted = InvocationEngine(FakeHost(), replay_ledger=ledger)

    assert restarted._reserve_replay(changed) == "IDEMPOTENCY_KEY_REUSE"


def test_finalize_without_a_reservation_keeps_outcome_fail_closed(tmp_path: Path) -> None:
    ledger = tmp_path / ".harness" / "phase4" / "invocation-ledger.json"
    engine, prepared = _prepare(tmp_path, replay_ledger=ledger)
    outcome = engine._blocked_outcome(prepared, ("TEST_BLOCK",))
    assert prepared.request is not None

    finalized = engine._finalize_real_outcome(prepared.request, outcome)

    assert finalized is outcome


def test_capture_artifacts_does_not_invent_an_artifact_without_message(tmp_path: Path) -> None:
    engine, prepared = _prepare(tmp_path)
    assert prepared.request is not None
    result = _host_result(InvocationResultStatus.SUCCESS, final_message=None)

    assert engine._capture_artifacts(prepared.request, result, prepared.request.authorization) == ()


def test_assurance_blocks_explicit_blocked_status(tmp_path: Path) -> None:
    engine, _prepared = _prepare(tmp_path)
    verification = SimpleNamespace(status="FAILED", digest="sha256:" + "a" * 64)

    result = engine._assurance(
        _host_result(InvocationResultStatus.BLOCKED),
        verification,
        InvocationResultStatus.BLOCKED,
    )

    assert result.decision is AssuranceDecision.BLOCK


def test_receipt_digest_construction_mismatch_is_not_silently_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, prepared = _prepare(tmp_path)
    lifecycle = (
        InvocationLifecycle.DISCOVERED,
        InvocationLifecycle.BLOCKED,
        InvocationLifecycle.CLOSED,
    )
    result = phase4_execution_module._empty_host_result(
        InvocationResultStatus.BLOCKED, "TEST_BLOCK"
    )
    monkeypatch.setattr(
        phase4_execution_module,
        "invocation_receipt_digest",
        lambda _receipt: "sha256:" + "f" * 64,
    )

    with pytest.raises(RuntimeError, match="digest construction mismatch"):
        engine._receipt(
            prepared,
            status=InvocationResultStatus.BLOCKED,
            lifecycle=lifecycle,
            host_result=result,
            artifacts=(),
            verification=None,
        )
