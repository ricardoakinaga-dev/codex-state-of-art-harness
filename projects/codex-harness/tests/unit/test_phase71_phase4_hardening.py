from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from test_phase4_execution import FakeHost, _fixture
from test_phase4_host import FakeAppServerClient, _request

from harness_kernel import phase4_execution as phase4_execution_module
from harness_kernel.phase4_execution import InvocationEngine, ReplayLedgerError
from harness_kernel.phase4_host import (
    CodexAppServerAdapter,
    HostProtocolError,
    HostTimeoutError,
    _SubprocessClient,
)
from harness_kernel.phase4_models import (
    HostInvocationResult,
    HostLoadObservation,
    InvocationLifecycle,
    InvocationResultStatus,
    Phase4Budget,
    PreparedInvocation,
)


def _prepare(
    tmp_path: Path,
    host: FakeHost,
    *,
    clock: Callable[[], int] | None = None,
    replay_ledger: Path | None = None,
) -> tuple[InvocationEngine, PreparedInvocation]:
    record, inventory, resolution, policy = _fixture(tmp_path)
    engine = InvocationEngine(host, clock=clock, replay_ledger=replay_ledger)
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P7.1-P4",
        run_id="RUN-P7.1-P4",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=phase4_execution_module.ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert prepared.request is not None
    return engine, prepared


def _host_result(
    status: InvocationResultStatus,
    *,
    invocation_observed: bool = True,
    execution_observed: bool = True,
    error_code: str | None = None,
    cancellation_status: str = "NOT_REQUESTED",
) -> HostInvocationResult:
    return HostInvocationResult(
        status=status,
        thread_id="thread-1",
        session_id="session-1",
        turn_id="turn-1",
        host_version="fake",
        events=(),
        final_message="PHASE4_SAFE_PILOT_ARTIFACT",
        load_observation=HostLoadObservation.UNOBSERVABLE,
        invocation_observed=invocation_observed,
        execution_observed=execution_observed,
        denied_approvals=0,
        cancellation_status=cancellation_status,
        error_code=error_code,
        started_at=1_700_000_000,
        completed_at=1_700_000_001,
        host_executable_path="/bin/codex-test",
        host_executable_digest="sha256:" + "a" * 64,
        host_command=("/bin/codex-test",),
        host_interpreter_path="/bin/node-test",
        host_interpreter_digest="sha256:" + "b" * 64,
    )


class _PreparationErrorHost(FakeHost):
    def prepare_invocation(self, request: object) -> dict[str, object]:
        raise RuntimeError("preparation failed")


class _UnsupportedPreparationHost(FakeHost):
    def prepare_invocation(self, request: object) -> dict[str, object]:
        return {"supported": False, "reason": "test host is unavailable"}


class _ValidationErrorHost(FakeHost):
    def validate_invocation(self, request: object) -> tuple[str, ...]:
        return ("SECURITY_HANDOFF_REQUIRED",)


class _RequestFailureHost(FakeHost):
    def request_invocation(self, request, *, budget, cancel_event=None):
        self.calls += 1
        raise RuntimeError("transport failed")


class _ObservationFailureHost(FakeHost):
    def observe_invocation(self, result: HostInvocationResult) -> HostInvocationResult:
        raise RuntimeError("observation failed")


def test_expired_authorization_blocks_before_host_and_closes_lifecycle(tmp_path: Path) -> None:
    clock_state = {"now": 1_700_000_000}
    host = FakeHost()
    engine, prepared = _prepare(tmp_path, host, clock=lambda: clock_state["now"])
    assert prepared.request is not None
    clock_state["now"] = prepared.request.authorization.expires_at

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.BLOCKED
    assert outcome.blockers == ("AUTHORIZATION_EXPIRED",)
    assert outcome.host_invoked is False
    assert outcome.host_result.error_code == "AUTHORIZATION_EXPIRED"
    assert outcome.receipt.lifecycle == (
        InvocationLifecycle.DISCOVERED,
        InvocationLifecycle.BLOCKED,
        InvocationLifecycle.CLOSED,
    )
    assert host.calls == 0


def test_host_preparation_exception_is_a_fail_closed_block(tmp_path: Path) -> None:
    host = _PreparationErrorHost()
    engine, prepared = _prepare(tmp_path, host)

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.BLOCKED
    assert outcome.blockers == ("HOST_PREPARATION_FAILURE",)
    assert outcome.host_result.status is InvocationResultStatus.BLOCKED
    assert outcome.host_result.error_code == "HOST_PREPARATION_FAILURE"
    assert outcome.host_invoked is False
    assert host.calls == 0


def test_unsupported_host_preparation_does_not_fall_through_to_execution(
    tmp_path: Path,
) -> None:
    host = _UnsupportedPreparationHost()
    engine, prepared = _prepare(tmp_path, host)

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.BLOCKED
    assert outcome.blockers == ("HOST_INVOCATION_UNSUPPORTED",)
    assert outcome.host_result.error_code == "HOST_INVOCATION_UNSUPPORTED"
    assert outcome.host_invoked is False
    assert host.calls == 0


def test_host_validation_error_is_preserved_without_request_side_effect(
    tmp_path: Path,
) -> None:
    host = _ValidationErrorHost()
    engine, prepared = _prepare(tmp_path, host)

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.BLOCKED
    assert outcome.blockers == ("SECURITY_HANDOFF_REQUIRED",)
    assert outcome.host_result.error_code == "SECURITY_HANDOFF_REQUIRED"
    assert outcome.host_invoked is False
    assert host.calls == 0


def test_host_request_failure_records_failure_without_claiming_execution(
    tmp_path: Path,
) -> None:
    host = _RequestFailureHost()
    engine, prepared = _prepare(tmp_path, host)

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.FAILURE
    assert outcome.blockers == ("HOST_ADAPTER_FAILURE",)
    assert outcome.host_result.status is InvocationResultStatus.FAILURE
    assert outcome.host_result.error_code == "HOST_ADAPTER_FAILURE"
    assert outcome.host_result.invocation_observed is False
    assert outcome.host_invoked is False
    assert outcome.receipt.lifecycle[-2:] == (
        InvocationLifecycle.FAILED,
        InvocationLifecycle.CLOSED,
    )
    assert host.calls == 1


def test_host_result_observation_failure_discards_untrusted_result(
    tmp_path: Path,
) -> None:
    host = _ObservationFailureHost()
    engine, prepared = _prepare(tmp_path, host)

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.FAILURE
    assert outcome.blockers == ("HOST_RESULT_OBSERVATION_FAILURE",)
    assert outcome.host_result.error_code == "HOST_RESULT_OBSERVATION_FAILURE"
    assert outcome.host_result.invocation_observed is False
    assert outcome.host_result.final_message is None
    assert outcome.artifacts == ()
    assert host.calls == 1


@pytest.mark.parametrize(
    ("status", "lifecycle_state", "error_code"),
    (
        (
            InvocationResultStatus.TIMED_OUT,
            InvocationLifecycle.TIMED_OUT,
            "HOST_INVOCATION_TIMEOUT",
        ),
        (
            InvocationResultStatus.CANCELLED,
            InvocationLifecycle.CANCELLED,
            "CANCELLATION_REQUESTED",
        ),
    ),
)
def test_unobserved_terminal_host_result_never_becomes_success(
    tmp_path: Path,
    status: InvocationResultStatus,
    lifecycle_state: InvocationLifecycle,
    error_code: str,
) -> None:
    host = FakeHost(
        result=_host_result(
            status,
            invocation_observed=False,
            execution_observed=False,
            error_code=error_code,
        )
    )
    engine, prepared = _prepare(tmp_path, host)

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is status
    assert outcome.blockers == (error_code,)
    assert outcome.host_invoked is False
    assert outcome.verification is None
    assert outcome.artifacts == ()
    assert lifecycle_state in outcome.receipt.lifecycle
    assert outcome.receipt.lifecycle[-1] is InvocationLifecycle.CLOSED


def test_observed_partial_result_is_not_promoted_to_success(tmp_path: Path) -> None:
    host = FakeHost(
        result=_host_result(
            InvocationResultStatus.PARTIAL,
            invocation_observed=True,
            execution_observed=True,
            error_code="HOST_RESULT_PARTIAL",
        )
    )
    engine, prepared = _prepare(tmp_path, host)

    outcome = engine.execute_prepared(prepared)

    assert outcome.status is InvocationResultStatus.PARTIAL
    assert outcome.receipt.lifecycle[-2:] == (
        InvocationLifecycle.PARTIAL,
        InvocationLifecycle.CLOSED,
    )
    assert outcome.verification is not None
    assert outcome.verification.status == "FAILED"
    assert "HOST_RESULT_PARTIAL" in outcome.verification.checks
    assert outcome.assurance is not None
    assert outcome.assurance.decision.value == "STOP"
    assert outcome.host_invoked is True


def test_terminal_ledger_write_failure_leaves_reservation_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = tmp_path / ".harness" / "phase4" / "invocation-ledger.json"
    host = FakeHost()
    engine, prepared = _prepare(tmp_path, host, replay_ledger=ledger)
    original_write = phase4_execution_module._write_ledger
    write_count = 0

    def fail_terminal_write(
        path: Path,
        entries: Mapping[str, Mapping[str, object]],
        *,
        directory_fd: int,
        ledger_token: str,
    ) -> None:
        nonlocal write_count
        write_count += 1
        if write_count == 2:
            raise ReplayLedgerError("simulated terminal persistence failure")
        original_write(path, entries, directory_fd=directory_fd, ledger_token=ledger_token)

    monkeypatch.setattr(phase4_execution_module, "_write_ledger", fail_terminal_write)

    first = engine.execute_prepared(prepared)

    assert first.status is InvocationResultStatus.SUCCESS
    assert write_count == 2
    entry = json.loads(ledger.read_text(encoding="utf-8"))["entries"][
        prepared.request.invocation_id
    ]
    assert entry["status"] == "RESERVED_FOR_CONTROLLED_REAL"
    assert "closed_at" not in entry

    replay_host = FakeHost()
    replay = InvocationEngine(replay_host, replay_ledger=ledger).execute_prepared(prepared)

    assert replay.status is InvocationResultStatus.BLOCKED
    assert replay.blockers == ("REPLAY_DETECTED",)
    assert replay_host.calls == 0


@pytest.mark.parametrize(
    ("policy_field", "policy_value", "error_code"),
    (
        ("network_policy", "ALLOW", "NETWORK_POLICY_UNSUPPORTED"),
        ("shell_policy", "ALLOW", "SHELL_POLICY_UNSUPPORTED"),
        ("mcp_policy", "ALLOW", "MCP_POLICY_UNSUPPORTED"),
        ("provider_policy", "ALLOW", "PROVIDER_POLICY_UNSUPPORTED"),
        ("credential_policy", "ALLOW", "CREDENTIAL_POLICY_UNSUPPORTED"),
    ),
)
def test_host_denies_unsupported_authorization_policy_before_transport(
    tmp_path: Path,
    policy_field: str,
    policy_value: str,
    error_code: str,
) -> None:
    request = _request(tmp_path)
    authorization = replace(request.authorization, **{policy_field: policy_value})
    invalid_request = replace(request, authorization=authorization)
    factory_calls = 0

    def transport_factory() -> FakeAppServerClient:
        nonlocal factory_calls
        factory_calls += 1
        return FakeAppServerClient()

    result = CodexAppServerAdapter(transport_factory=transport_factory).request_invocation(
        invalid_request,
        budget=Phase4Budget(),
    )

    assert result.status is InvocationResultStatus.BLOCKED
    assert result.error_code == error_code
    assert result.events == ()
    assert result.invocation_observed is False
    assert factory_calls == 0


def test_host_denies_unsupported_filesystem_mode_before_transport(tmp_path: Path) -> None:
    request = _request(tmp_path)
    authorization = replace(
        request.authorization,
        filesystem_policy={**request.authorization.filesystem_policy, "mode": "WORKSPACE_WRITE"},
    )
    invalid_request = replace(request, authorization=authorization)
    factory_calls = 0

    def transport_factory() -> FakeAppServerClient:
        nonlocal factory_calls
        factory_calls += 1
        return FakeAppServerClient()

    result = CodexAppServerAdapter(transport_factory=transport_factory).request_invocation(
        invalid_request,
        budget=Phase4Budget(),
    )

    assert result.status is InvocationResultStatus.BLOCKED
    assert result.error_code == "FILESYSTEM_MODE_UNSUPPORTED"
    assert result.events == ()
    assert factory_calls == 0


def test_host_cancellation_after_turn_start_requires_interrupt_ack(tmp_path: Path) -> None:
    client = FakeAppServerClient()

    def cancelled_stream(*, timeout_seconds: float, cancel_event: Event | None = None):
        yield {"__phase4_cancel_requested__": True}

    client.stream = cancelled_stream  # type: ignore[method-assign]
    adapter = CodexAppServerAdapter(transport_factory=lambda: client)
    request = _request(tmp_path)

    result = adapter.request_invocation(request, budget=Phase4Budget())

    assert result.status is InvocationResultStatus.CANCELLED
    assert result.error_code is None
    assert result.cancellation_status == "HOST_INTERRUPT_ACKNOWLEDGED"
    assert result.invocation_observed is True
    assert result.execution_observed is False
    assert [method for method, _ in client.calls] == [
        "initialize",
        "skills/list",
        "thread/start",
        "turn/start",
        "turn/interrupt",
    ]
    assert result.events[0].event_class == "HOST_INVOCATION_ACKNOWLEDGED"
    assert request.invocation_id not in adapter._active_sessions


def test_host_cancellation_without_interrupt_ack_is_unknown_not_success(
    tmp_path: Path,
) -> None:
    client = FakeAppServerClient()
    original_call = client.call

    def unavailable_interrupt(
        method: str,
        params: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        if method == "turn/interrupt":
            raise HostTimeoutError("interrupt deadline")
        return original_call(method, params, timeout_seconds=timeout_seconds)

    def cancelled_stream(*, timeout_seconds: float, cancel_event: Event | None = None):
        yield {"__phase4_cancel_requested__": True}

    client.call = unavailable_interrupt  # type: ignore[method-assign]
    client.stream = cancelled_stream  # type: ignore[method-assign]
    adapter = CodexAppServerAdapter(transport_factory=lambda: client)

    result = adapter.request_invocation(_request(tmp_path), budget=Phase4Budget())

    assert result.status is InvocationResultStatus.UNKNOWN
    assert result.error_code == "CANCELLATION_UNSUPPORTED_BY_HOST"
    assert result.cancellation_status == "CANCELLATION_UNSUPPORTED_BY_HOST"
    assert result.invocation_observed is True
    assert result.execution_observed is False
    assert result.events[0].event_class == "HOST_INVOCATION_ACKNOWLEDGED"


def test_missing_skill_is_blocked_before_thread_creation(tmp_path: Path) -> None:
    client = FakeAppServerClient()
    original_call = client.call

    def no_skill_call(
        method: str,
        params: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        if method == "skills/list":
            client.calls.append((method, params))
            return {"result": {"data": [{"cwd": params["cwds"][0], "skills": []}]}}
        return original_call(method, params, timeout_seconds=timeout_seconds)

    client.call = no_skill_call  # type: ignore[method-assign]
    adapter = CodexAppServerAdapter(transport_factory=lambda: client)

    result = adapter.request_invocation(_request(tmp_path), budget=Phase4Budget())

    assert result.status is InvocationResultStatus.BLOCKED
    assert result.error_code == "SKILL_NOT_DISCOVERED"
    assert result.host_version == "codex-cli 0.150.1"
    assert result.invocation_observed is False
    assert result.events == ()
    assert [method for method, _ in client.calls] == ["initialize", "skills/list"]


@pytest.mark.parametrize(
    ("missing_method", "response"),
    (
        ("thread/start", {"result": {"thread": {"sessionId": "session-1"}}}),
        ("turn/start", {"result": {"turn": {"status": "started"}}}),
    ),
)
def test_missing_host_identifier_is_a_typed_failure_and_closes_transport(
    tmp_path: Path,
    missing_method: str,
    response: dict[str, object],
) -> None:
    client = FakeAppServerClient()
    original_call = client.call

    def missing_identifier_call(
        method: str,
        params: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        if method == missing_method:
            client.calls.append((method, params))
            return response
        return original_call(method, params, timeout_seconds=timeout_seconds)

    client.call = missing_identifier_call  # type: ignore[method-assign]
    adapter = CodexAppServerAdapter(transport_factory=lambda: client)

    result = adapter.request_invocation(_request(tmp_path), budget=Phase4Budget())

    expected_methods = ["initialize", "skills/list"]
    if missing_method == "turn/start":
        expected_methods.append("thread/start")
    expected_methods.append(missing_method)
    assert result.status is InvocationResultStatus.FAILURE
    assert result.error_code == "HOSTPROTOCOLERROR"
    assert result.invocation_observed is False
    assert result.execution_observed is False
    assert result.events == ()
    assert [method for method, _ in client.calls] == expected_methods
    assert adapter._active_sessions == {}


def test_invalid_protocol_observation_is_rejected_and_session_is_cleaned(
    tmp_path: Path,
) -> None:
    client = FakeAppServerClient()
    client.protocol_counts = lambda: (0, 0, 0)  # type: ignore[attr-defined]
    client.protocol_observations = lambda: (object(),)  # type: ignore[attr-defined]
    adapter = CodexAppServerAdapter(transport_factory=lambda: client)

    with pytest.raises(ValueError, match="invalid record"):
        adapter.request_invocation(_request(tmp_path), budget=Phase4Budget())

    assert adapter._active_sessions == {}


def test_invalid_protocol_counter_resets_counts_and_cannot_report_success(
    tmp_path: Path,
) -> None:
    client = FakeAppServerClient()
    client.protocol_counts = lambda: ("invalid", 0, 0)  # type: ignore[attr-defined]
    adapter = CodexAppServerAdapter(transport_factory=lambda: client)

    result = adapter.request_invocation(_request(tmp_path), budget=Phase4Budget())

    assert result.status is InvocationResultStatus.FAILURE
    assert result.error_code == "HOST_PROTOCOL_COUNTER_INVALID"
    assert result.protocol_message_count == 0
    assert result.mcp_event_count == 0
    assert result.approval_request_count == 0


def test_subprocess_client_rejects_zero_timeout_without_protocol_side_effect(
    tmp_path: Path,
) -> None:
    python_path = Path(sys.executable).resolve()
    python_digest = "sha256:" + hashlib.sha256(python_path.read_bytes()).hexdigest()
    client = _SubprocessClient(
        cwd=tmp_path,
        command=(str(python_path), "-c", "import time; time.sleep(1)"),
        pinned_files=((str(python_path), python_digest),),
        host_executable_path=str(python_path),
        host_executable_digest=python_digest,
    )

    try:
        with pytest.raises(HostTimeoutError, match="timed out"):
            client.call("initialize", {}, timeout_seconds=0)
        with pytest.raises(HostTimeoutError, match="timed out"):
            client._read(0)
        assert client.protocol_counts() == (0, 0, 0)
    finally:
        client.close()


def test_invalid_pinned_path_is_rejected_before_subprocess_creation(tmp_path: Path) -> None:
    missing = tmp_path / "missing-host"

    with pytest.raises(HostProtocolError, match="cannot be resolved"):
        _SubprocessClient(
            cwd=tmp_path,
            command=(str(missing),),
            pinned_files=((str(missing), "sha256:" + "0" * 64),),
            host_executable_path=str(missing),
            host_executable_digest="sha256:" + "0" * 64,
        )
