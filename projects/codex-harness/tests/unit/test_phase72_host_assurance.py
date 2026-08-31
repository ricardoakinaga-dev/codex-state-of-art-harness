from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from test_phase4_host import FakeAppServerClient, _request
from test_phase7_host import PACKAGE_ROOT, _builder_request, _BuilderFakeAppServerClient

import harness_kernel.phase4_host as phase4_host
import harness_kernel.phase7_host as phase7_host
from harness_kernel.phase4_host import (
    CodexAppServerAdapter,
    HostProtocolError,
    HostTimeoutError,
    _SubprocessClient,
)
from harness_kernel.phase4_models import (
    CapabilityInvocationRequest,
    ExecutionMode,
    InvocationResultStatus,
    Phase4Budget,
)
from harness_kernel.phase7_host import (
    HOST_LIST_FILES_TOOL,
    HOST_WRITE_FILE_TOOL,
    BackendBuilderAppServerAdapter,
    BackendVerifierAppServerAdapter,
    BoundedBuilderHostTools,
    WorkspaceFilesystemPolicy,
    WorkspaceWriteMode,
    build_backend_filesystem_policy,
    validate_file_change_event,
)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_pinned_host_files_reject_relative_and_symlinked_paths(tmp_path: Path) -> None:
    executable = tmp_path / "host"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    digest = _digest(executable)

    with pytest.raises(HostProtocolError, match="not absolute"):
        phase4_host._verify_pinned_files((("relative-host", digest),))

    link = tmp_path / "host-link"
    link.symlink_to(executable)
    with pytest.raises(HostProtocolError, match="resolved path"):
        phase4_host._verify_pinned_files(((str(link), digest),))


def test_resolved_executable_rejects_relative_configured_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_EXECUTABLE", "relative/codex")
    with pytest.raises(HostProtocolError, match="absolute path"):
        phase4_host._resolve_regular_executable("codex")


def test_pinned_descriptor_open_requires_secure_platform_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with monkeypatch.context() as context:
        context.delattr(phase4_host.os, "O_NOFOLLOW", raising=False)
        with pytest.raises(HostProtocolError, match="descriptor execution is unavailable"):
            phase4_host._open_pinned_files(())


def test_subprocess_client_rejects_unpinned_command_and_runs_auth_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    python_path = Path(sys.executable).resolve()
    python_digest = _digest(python_path)
    missing_pin = tmp_path / "missing-pin"
    missing_pin.write_text("#!/bin/sh\n", encoding="utf-8")
    missing_pin.chmod(0o755)
    with pytest.raises(HostProtocolError, match="not present in the process command"):
        _SubprocessClient(
            cwd=tmp_path,
            command=(str(python_path), "-c", "import sys; sys.stdin.read()"),
            pinned_files=(
                (str(python_path), python_digest),
                (str(missing_pin), _digest(missing_pin)),
            ),
            host_executable_path=str(python_path),
            host_executable_digest=python_digest,
        )

    copied = False

    def record_auth(_self: _SubprocessClient, runtime_codex_home: Path) -> None:
        nonlocal copied
        copied = runtime_codex_home.is_dir()

    monkeypatch.setattr(_SubprocessClient, "_copy_host_transport_authentication", record_auth)
    client = _SubprocessClient(
        cwd=tmp_path,
        command=(str(python_path), "-c", "import sys; sys.stdin.read()"),
        pinned_files=((str(python_path), python_digest),),
        host_executable_path=str(python_path),
        host_executable_digest=python_digest,
        allow_host_authentication=True,
    )
    try:
        assert copied is True
    finally:
        client.close()


def test_transport_auth_copy_fails_closed_when_platform_or_home_is_not_secure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_home = tmp_path / "source-codex-home"
    runtime_home = tmp_path / "runtime-codex-home"
    source_home.mkdir()
    runtime_home.mkdir()
    (source_home / "auth.json").write_bytes(b"auth")
    monkeypatch.setenv("CODEX_HOME", str(source_home))

    with monkeypatch.context() as context:
        context.delattr(phase4_host.os, "O_NOFOLLOW", raising=False)
        _SubprocessClient._copy_host_transport_authentication(runtime_home)
    assert not (runtime_home / "auth.json").exists()

    original_fstat = phase4_host.os.fstat
    calls = 0

    def report_regular_for_home(fd: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        if calls == 1:
            metadata = (source_home / "auth.json").stat()
            return os.stat_result(tuple(metadata))
        return original_fstat(fd)

    monkeypatch.setattr(phase4_host.os, "fstat", report_regular_for_home)
    _SubprocessClient._copy_host_transport_authentication(runtime_home)
    assert not (runtime_home / "auth.json").exists()


def test_subprocess_stream_handles_pre_requested_cancel_and_deadline_races(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = object.__new__(_SubprocessClient)
    event = Event()
    event.set()
    assert next(client.stream(timeout_seconds=1, cancel_event=event)) == {
        "__phase4_cancel_requested__": True
    }

    client = object.__new__(_SubprocessClient)

    def fail_read(_timeout: float) -> dict[str, object]:
        raise HostTimeoutError("read")

    monkeypatch.setattr(client, "_read", fail_read)
    clock = iter((0.0, 0.1, 0.2, 2.0))
    monkeypatch.setattr(phase4_host.time, "monotonic", lambda: next(clock))
    with pytest.raises(HostTimeoutError, match="timed out"):
        next(client.stream(timeout_seconds=1))

    client = object.__new__(_SubprocessClient)
    monkeypatch.setattr(client, "_read", fail_read)
    clock = iter((0.0, 0.1, 2.0))
    monkeypatch.setattr(phase4_host.time, "monotonic", lambda: next(clock))
    with pytest.raises(HostTimeoutError, match="read"):
        next(client.stream(timeout_seconds=1))


def test_subprocess_read_records_mcp_protocol_observations(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Stdout:
        def fileno(self) -> int:
            return 7

    class _Process:
        stdout = _Stdout()

        @staticmethod
        def poll() -> None:
            return None

    client = object.__new__(_SubprocessClient)
    client._process = _Process()
    client._stdout_buffer = b""
    client.max_line_bytes = 10_000
    client._protocol_message_count = 0
    client._mcp_event_count = 0
    client._approval_request_count = 0
    client._protocol_observations = []
    payload = json.dumps({"jsonrpc": "2.0", "method": "mcpServer/event"}).encode() + b"\n"
    monkeypatch.setattr(phase4_host.select, "select", lambda *_args: ([_Stdout()], [], []))
    monkeypatch.setattr(phase4_host.os, "read", lambda _fd, _limit: payload)

    assert client._read(1) == {"jsonrpc": "2.0", "method": "mcpServer/event"}
    assert client.protocol_counts() == (1, 1, 0)


def test_adapter_validates_paths_and_host_fingerprints_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policies = SimpleNamespace(
        network_policy="DENY",
        shell_policy="DENY",
        mcp_policy="DENY",
        provider_policy="DENY",
        credential_policy="DENY",
        filesystem_policy={"mode": "READ_ONLY"},
        requested_execution_mode=ExecutionMode.CONTROLLED_REAL,
        host_executable_digest=None,
        host_interpreter_digest=None,
    )
    malformed = SimpleNamespace(
        workspace="relative-workspace",
        skill_path="relative-skill",
        context=SimpleNamespace(skill_path="/different-skill"),
        authorization=policies,
    )
    adapter = CodexAppServerAdapter(transport_factory=lambda: None)  # type: ignore[arg-type]
    errors = adapter.validate_invocation(malformed)  # type: ignore[arg-type]
    assert errors[:3] == (
        "WORKSPACE_MUST_BE_ABSOLUTE",
        "SKILL_PATH_MUST_BE_ABSOLUTE",
        "CONTEXT_SKILL_PATH_MISMATCH",
    )

    request = _request(tmp_path)
    binding = (
        ("/pinned/codex",),
        "/pinned/codex",
        "sha256:" + "c" * 64,
        (("/pinned/codex", "sha256:" + "c" * 64),),
        "/pinned/node",
        "sha256:" + "d" * 64,
    )
    adapter = CodexAppServerAdapter()
    monkeypatch.setattr(adapter, "_resolved_host_binding", lambda: binding)
    assert "HOST_EXECUTABLE_NOT_BOUND" in adapter.validate_invocation(request)

    wrong_executable = replace_authorization(request, executable="sha256:" + "e" * 64)
    assert "HOST_EXECUTABLE_FINGERPRINT_MISMATCH" in adapter.validate_invocation(wrong_executable)

    no_interpreter = replace_authorization(request, executable=binding[2])
    assert "HOST_INTERPRETER_NOT_BOUND" in adapter.validate_invocation(no_interpreter)

    wrong_interpreter = replace_authorization(
        no_interpreter,
        executable=binding[2],
        interpreter="sha256:" + "e" * 64,
    )
    assert "HOST_INTERPRETER_FINGERPRINT_MISMATCH" in adapter.validate_invocation(wrong_interpreter)

    no_interpreter_binding = (*binding[:5], None)
    monkeypatch.setattr(adapter, "_resolved_host_binding", lambda: no_interpreter_binding)
    assert "HOST_INTERPRETER_UNAVAILABLE" in adapter.validate_invocation(wrong_interpreter)


def replace_authorization(
    request: CapabilityInvocationRequest,
    *,
    executable: str | None = None,
    interpreter: str | None = None,
) -> CapabilityInvocationRequest:
    authorization = request.authorization
    policy = dict(authorization.filesystem_policy)
    policy["host_executable_digest"] = executable
    policy["host_interpreter_digest"] = interpreter
    return replace(
        request,
        authorization=replace(
            authorization,
            filesystem_policy=policy,
            host_executable_digest=executable,
            host_interpreter_digest=interpreter,
        ),
    )


def test_adapter_rejects_pre_requested_cancel_and_failed_turn(tmp_path: Path) -> None:
    client = FakeAppServerClient()
    adapter = CodexAppServerAdapter(transport_factory=lambda: client)
    cancel = Event()
    cancel.set()
    result = adapter.request_invocation(
        _request(tmp_path), budget=Phase4Budget(), cancel_event=cancel
    )
    assert result.status is InvocationResultStatus.CANCELLED
    assert result.error_code == "CANCELLATION_REQUESTED_BEFORE_HOST_START"
    assert client.calls == []

    client = FakeAppServerClient()

    def failed_turn(*, timeout_seconds: float, cancel_event: Event | None = None):
        del timeout_seconds, cancel_event
        yield {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "turn": {"id": "turn-1", "status": "failed"},
            },
        }

    client.stream = failed_turn  # type: ignore[method-assign]
    result = CodexAppServerAdapter(transport_factory=lambda: client).request_invocation(
        _request(tmp_path), budget=Phase4Budget()
    )
    assert result.status is InvocationResultStatus.FAILURE
    assert result.error_code == "HOST_TURN_NOT_COMPLETED"


def test_adapter_deadline_helpers_fail_without_budget_or_interrupt_attempt() -> None:
    with pytest.raises(HostTimeoutError, match="timed out"):
        CodexAppServerAdapter._remaining_timeout(0)
    client = FakeAppServerClient()
    assert (
        CodexAppServerAdapter._interrupt(
            client,
            "thread",
            "turn",
            timeout_seconds=0,
        )
        == "CANCELLATION_NOT_ATTEMPTED_DEADLINE_EXPIRED"
    )


def test_builder_write_rejects_zero_byte_progress_without_leaking_temp_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_root = tmp_path / "app"
    write_root.mkdir()
    policy = WorkspaceFilesystemPolicy(
        workspace=tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(write_root,),
    )
    tools = BoundedBuilderHostTools(policy)
    monkeypatch.setattr(phase7_host.os, "write", lambda _fd, _payload: 0)

    result = tools.dispatch(
        HOST_WRITE_FILE_TOOL,
        {"path": "app/output.txt", "content": "bounded"},
    )

    assert result.success is False
    assert result.payload["error"] == "FILE_WRITE_REJECTED"
    assert not (write_root / "output.txt").exists()
    assert not tuple(write_root.glob(".harness-write-*.tmp"))


def test_filesystem_helpers_reject_invalid_roots_and_bound_listing_and_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = tmp_path / "app"
    nested = app / "nested"
    app.mkdir()
    nested.mkdir()
    deeper = nested / "deeper"
    deeper.mkdir()
    (nested / "source.py").write_text("pass\n", encoding="utf-8")
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(app, nested),
    )
    tools = BoundedBuilderHostTools(policy)

    listed = tools.dispatch(HOST_LIST_FILES_TOOL, {})
    assert listed.success is True
    assert listed.payload["paths"] == ["app/nested/source.py"]

    many = tmp_path / "many"
    many.mkdir()
    for index in range(257):
        (many / f"file-{index}.txt").write_text("x", encoding="utf-8")
    limited = BoundedBuilderHostTools(
        build_backend_filesystem_policy(
            tmp_path,
            mode=WorkspaceWriteMode.WORKSPACE_WRITE,
            allowed_roots=(many,),
        )
    ).dispatch(HOST_LIST_FILES_TOOL, {})
    assert limited.payload["error"] == "FILE_LIST_LIMIT_EXCEEDED"

    assert tools.write_event_path({"path": "../escape", "content": "x"}) is None
    assert (
        tools.write_event_path(
            {"path": "app/large.py", "content": "x" * (phase7_host._MAX_HOST_FILE_BYTES + 1)}
        )
        is None
    )
    assert policy.allows_write("\x00") is False
    assert tools._candidate("app/nested/deeper", require_existing=True) is None

    regular_file = tmp_path / "regular"
    regular_file.write_text("file", encoding="utf-8")
    with pytest.raises(ValueError, match="absolute"):
        phase7_host._safe_workspace_path("relative-workspace")
    with pytest.raises(ValueError, match="workspace must be a directory"):
        phase7_host._safe_workspace_path(regular_file)
    with pytest.raises(ValueError, match="allowed root must be a directory"):
        phase7_host._safe_root_path(regular_file, tmp_path)
    with pytest.raises(ValueError, match="absolute"):
        phase7_host._safe_package_path("relative-package")
    with pytest.raises(ValueError, match="directory"):
        phase7_host._safe_package_path(regular_file)
    package_link = tmp_path / "package-link"
    package_link.symlink_to(app, target_is_directory=True)
    with monkeypatch.context() as context:
        context.setattr(phase7_host, "_has_symlink_component", lambda _path: False)
        with pytest.raises(ValueError, match="symlink"):
            phase7_host._safe_package_path(package_link)

    assert phase7_host._declared_roots(123) is None
    assert phase7_host._collect_paths(object()) == ()
    deep_value: object = {"path": "app/deep.py"}
    for _ in range(10):
        deep_value = [deep_value]
    assert phase7_host._collect_paths(deep_value) == ()
    declared = dict(policy.as_mapping())
    declared["package_path"] = 123
    assert phase7_host._filesystem_policy_matches(declared, policy) is False

    package = tmp_path / "package"
    package.mkdir()
    protected_policy = build_backend_filesystem_policy(tmp_path, package_path=package)
    assert protected_policy._protected(package) is True

    original_is_dir = Path.is_dir
    monkeypatch.setattr(
        Path,
        "is_dir",
        lambda value: False if str(value) == "/etc" else original_is_dir(value),
    )
    sandbox = tmp_path / "bwrap"
    sandbox.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(phase7_host, "_FIXED_TEST_SANDBOX", sandbox)
    fixed_tests = tmp_path / "fixed-tests"
    fixed_tests.mkdir()
    command = phase7_host._fixed_test_command(fixed_tests)
    assert command is not None
    assert "/etc" not in command


def test_builder_authority_and_package_binding_residuals_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "migrations").mkdir()
    request = _builder_request(tmp_path)
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(tmp_path / "app", tmp_path / "migrations"),
        package_path=PACKAGE_ROOT,
    )
    adapter = BackendBuilderAppServerAdapter(filesystem_policy=policy)

    tools_forbidden = replace(
        request,
        authorization=replace(request.authorization, allowed_tools=("unexpected",)),
    )
    assert "BUILDER_TOOLS_FORBIDDEN" in adapter.validate_invocation(tools_forbidden)
    side_effects_forbidden = replace(
        request,
        authorization=replace(request.authorization, allowed_side_effects=("write",)),
    )
    assert "BUILDER_SIDE_EFFECTS_FORBIDDEN" in adapter.validate_invocation(side_effects_forbidden)

    invalid_package_write = replace(
        request,
        authorization=replace(
            request.authorization,
            filesystem_policy={
                **request.authorization.filesystem_policy,
                "package_write_allowed": True,
            },
        ),
    )
    monkeypatch.setattr(adapter, "_policy_for_request", lambda _request: policy)
    assert "PACKAGE_WRITE_FORBIDDEN" in adapter._validate_filesystem_policy(invalid_package_write)

    expired = phase7_host._authorization_binding_errors(
        request,
        request.authorization,
        lambda: request.authorization.expires_at,
    )
    assert expired == ("AUTHORIZATION_EXPIRED",)

    no_package_policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(tmp_path / "app",),
    )
    no_package_request = replace(
        request,
        authorization=replace(
            request.authorization,
            filesystem_policy=no_package_policy.as_mapping(),
        ),
    )
    no_package_adapter = BackendBuilderAppServerAdapter(
        filesystem_policy=no_package_policy,
    )
    assert no_package_adapter._skill_is_discovered({}, no_package_request) is False

    with pytest.raises(ValueError, match="trusted_authorization"):
        phase7_host.VerificationLoopVNextAppServerAdapter(trusted_authorization=object())  # type: ignore[arg-type]

    package_results = iter((PACKAGE_ROOT, tmp_path / "different-package"))
    verifier = BackendVerifierAppServerAdapter(
        filesystem_policy=build_backend_filesystem_policy(tmp_path, package_path=PACKAGE_ROOT),
        project_root=tmp_path,
        package_path=PACKAGE_ROOT,
    )
    monkeypatch.setattr(phase7_host, "_safe_package_path", lambda _value: next(package_results))
    assert verifier._skill_is_discovered({}, request) is False


def test_builder_dynamic_write_observation_and_reservation_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = tmp_path / "app"
    app.mkdir()
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(app,),
    )
    adapter = phase7_host.BackendBuilderAppServerAdapter()
    tools = BoundedBuilderHostTools(policy)
    event_paths: set[str] = set()
    client = SimpleNamespace(responses=[])
    client.respond = lambda request_id, result: client.responses.append((request_id, result))
    events: list[object] = []
    calls = iter(
        (phase7_host._tool_ok({"bytes": 1}), phase7_host._tool_error("FILE_WRITE_REJECTED"))
    )
    original_dispatch = BoundedBuilderHostTools.dispatch

    def dispatch(host_tools, name, arguments):
        if name == HOST_WRITE_FILE_TOOL:
            return next(calls)
        return original_dispatch(host_tools, name, arguments)

    monkeypatch.setattr(BoundedBuilderHostTools, "dispatch", dispatch)
    tokens = (
        adapter._event_paths_context.set(event_paths),
        adapter._host_tools_context.set(tools),
        adapter._dynamic_call_ids_context.set(set()),
        adapter._dynamic_item_ids_context.set(set()),
    )
    try:

        def message(call_id: str) -> dict[str, object]:
            return {
                "id": call_id,
                "method": "item/tool/call",
                "params": {
                    "threadId": "thread",
                    "turnId": "turn",
                    "callId": call_id,
                    "tool": HOST_WRITE_FILE_TOOL,
                    "namespace": None,
                    "arguments": {"path": "app/output.py", "content": "x"},
                },
            }

        assert adapter._handle_host_request(
            message("call-observation"),
            client,
            events,
            Phase4Budget(timeout_seconds=1, max_host_events=8),
        ) == (True, "HOST_TOOL_WRITE_OBSERVATION_MISSING")
        assert event_paths == set()
        assert adapter._handle_host_request(
            message("call-failure"),
            client,
            events,
            Phase4Budget(timeout_seconds=1, max_host_events=8),
        ) == (True, "FILE_WRITE_REJECTED")
        assert event_paths == set()
    finally:
        for variable, token in zip(
            (
                adapter._dynamic_item_ids_context,
                adapter._dynamic_call_ids_context,
                adapter._host_tools_context,
                adapter._event_paths_context,
            ),
            reversed(tokens),
            strict=True,
        ):
            variable.reset(token)

    assert adapter._release_write_event_path(None, True) is None


def test_builder_reservation_rejects_unplanned_paths_and_event_path_overflow(
    tmp_path: Path,
) -> None:
    app = tmp_path / "app"
    app.mkdir()
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(app,),
    )
    adapter = BackendBuilderAppServerAdapter()
    tools = BoundedBuilderHostTools(policy)
    event_paths: set[str] = set()
    policy_token = adapter._policy_context.set(policy)
    event_token = adapter._event_paths_context.set(event_paths)
    try:
        assert adapter._reserve_write_event_path(
            tools,
            {"path": "../escape", "content": "x"},
        ) == (None, False, None)
        overflow = {
            "method": "item/fileChange",
            "params": {
                "item": {
                    "type": "fileChange",
                    "changes": [{"path": f"app/change-{i}.py"} for i in range(64)],
                }
            },
        }
        event_paths.add("app/existing.py")
        assert adapter._is_forbidden_host_action(overflow) is True
    finally:
        adapter._event_paths_context.reset(event_token)
        adapter._policy_context.reset(policy_token)

    adapter._release_write_event_path("app/file.py", True)


def test_builder_event_path_validation_and_delta_observation_are_bounded(
    tmp_path: Path,
) -> None:
    app = tmp_path / "app"
    app.mkdir()
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(app,),
    )
    with pytest.raises(HostProtocolError, match="invalid"):
        validate_file_change_event(
            {
                "method": "item/fileChange",
                "params": {"item": {"type": "fileChange", "changes": [{"path": "\x00"}]}},
            },
            policy,
        )

    adapter = BackendBuilderAppServerAdapter()
    tools = BoundedBuilderHostTools(policy)
    token = adapter._event_paths_context.set({f"app/existing-{i}.py" for i in range(64)})
    try:
        assert adapter._reserve_write_event_path(
            tools,
            {"path": "app/new.py", "content": "x"},
        ) == ("app/new.py", False, "HOST_TOOL_WRITE_BUDGET_EXCEEDED")
    finally:
        adapter._event_paths_context.reset(token)

    assert phase7_host._collect_paths({1: "not-a-path"}) == ()
    nested = {"changes": [{"path": "app/new.py"}]}
    assert phase7_host._collect_paths([nested]) == ("app/new.py",)


def test_builder_stops_when_workspace_mutation_has_no_corresponding_event(
    tmp_path: Path,
) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "migrations").mkdir()
    request = _builder_request(tmp_path)
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(tmp_path / "app", tmp_path / "migrations"),
        package_path=PACKAGE_ROOT,
    )

    class NoEventClient(_BuilderFakeAppServerClient):
        def stream(self, *, timeout_seconds: float, cancel_event=None):
            del timeout_seconds, cancel_event
            yield {
                "method": "item/completed",
                "params": {
                    "threadId": "thread-builder",
                    "turnId": "turn-builder",
                    "item": {"type": "agentMessage", "text": "done"},
                },
            }
            yield {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-builder",
                    "turn": {"id": "turn-builder", "status": "completed"},
                },
            }

    client = NoEventClient(tmp_path)
    adapter = BackendBuilderAppServerAdapter(
        transport_factory=lambda: client,
        filesystem_policy=policy,
        trusted_authorization=request.authorization,
        project_root=tmp_path,
    )
    result = adapter.request_invocation(
        request,
        budget=Phase4Budget(timeout_seconds=5, max_host_events=20),
    )

    assert result.status is InvocationResultStatus.FAILURE
    assert result.error_code == "WORKSPACE_CHANGE_EVENT_MISSING"
    assert (tmp_path / "app" / "builder_touch.py").exists()


def test_transport_auth_copy_handles_relative_nonregular_stable_and_write_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_relative = tmp_path / "runtime-relative"
    runtime_relative.mkdir()
    monkeypatch.setenv("CODEX_HOME", "relative-codex-home")
    _SubprocessClient._copy_host_transport_authentication(runtime_relative)
    assert not (runtime_relative / "auth.json").exists()

    source_home = tmp_path / "source-codex-home"
    source_home.mkdir()
    runtime_nonregular = tmp_path / "runtime-nonregular"
    runtime_nonregular.mkdir()
    (source_home / "auth.json").mkdir()
    monkeypatch.setenv("CODEX_HOME", str(source_home))
    _SubprocessClient._copy_host_transport_authentication(runtime_nonregular)
    assert not (runtime_nonregular / "auth.json").exists()

    (source_home / "auth.json").rmdir()
    (source_home / "auth.json").write_bytes(b"transport-auth")
    runtime_copy = tmp_path / "runtime-copy"
    runtime_copy.mkdir()
    _SubprocessClient._copy_host_transport_authentication(runtime_copy)
    assert (runtime_copy / "auth.json").read_bytes() == b"transport-auth"

    runtime_zero = tmp_path / "runtime-zero"
    runtime_zero.mkdir()
    with monkeypatch.context() as context:
        context.setattr(phase4_host.os, "write", lambda _fd, _payload: 0)
        with pytest.raises(HostProtocolError, match="cannot be copied safely"):
            _SubprocessClient._copy_host_transport_authentication(runtime_zero)
    assert not (runtime_zero / "auth.json").exists()

    runtime_fsync = tmp_path / "runtime-fsync"
    runtime_fsync.mkdir()
    monkeypatch.setattr(
        phase4_host.os,
        "fsync",
        lambda _fd: (_ for _ in ()).throw(OSError("fsync")),
    )
    with pytest.raises(HostProtocolError, match="cannot be copied safely"):
        _SubprocessClient._copy_host_transport_authentication(runtime_fsync)
    assert not (runtime_fsync / "auth.json").exists()


def test_transport_auth_copy_rejects_home_type_and_source_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_home = tmp_path / "source-codex-home"
    source_home.mkdir()
    auth = source_home / "auth.json"
    auth.write_bytes(b"auth")
    monkeypatch.setenv("CODEX_HOME", str(source_home))

    runtime_type = tmp_path / "runtime-type"
    runtime_type.mkdir()
    file_metadata = auth.stat()
    monkeypatch.setattr(phase4_host.os, "fstat", lambda _fd: file_metadata)
    _SubprocessClient._copy_host_transport_authentication(runtime_type)
    assert not (runtime_type / "auth.json").exists()

    runtime_race = tmp_path / "runtime-race"
    runtime_race.mkdir()
    before = auth.stat()
    calls = 0

    def changing_fstat(fd: int):
        nonlocal calls
        calls += 1
        if calls == 1:
            return source_home.stat()
        if calls == 2:
            return before
        return SimpleNamespace(
            st_dev=before.st_dev,
            st_ino=before.st_ino,
            st_size=before.st_size,
            st_mtime_ns=before.st_mtime_ns + 1,
            st_mode=before.st_mode,
        )

    monkeypatch.setattr(phase4_host.os, "fstat", changing_fstat)
    with pytest.raises(HostProtocolError, match="changed during safe copy"):
        _SubprocessClient._copy_host_transport_authentication(runtime_race)
    assert not (runtime_race / "auth.json").exists()


def test_transport_auth_cleanup_guards_cover_pre_copy_and_post_copy_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_home = tmp_path / "source-codex-home"
    source_home.mkdir()
    (source_home / "auth.json").write_bytes(b"auth")
    monkeypatch.setenv("CODEX_HOME", str(source_home))
    original_open = phase4_host.os.open

    runtime_protocol = tmp_path / "runtime-protocol"
    runtime_protocol.mkdir()
    open_calls = 0

    def reject_destination(*args, **kwargs):
        nonlocal open_calls
        open_calls += 1
        if open_calls == 3:
            raise HostProtocolError("destination rejected")
        return original_open(*args, **kwargs)

    monkeypatch.setattr(phase4_host.os, "open", reject_destination)
    with pytest.raises(HostProtocolError, match="destination rejected"):
        _SubprocessClient._copy_host_transport_authentication(runtime_protocol)
    assert not (runtime_protocol / "auth.json").exists()

    runtime_oserror = tmp_path / "runtime-oserror"
    runtime_oserror.mkdir()
    open_calls = 0

    def reject_destination_oserror(*args, **kwargs):
        nonlocal open_calls
        open_calls += 1
        if open_calls == 3:
            raise OSError("destination unavailable")
        return original_open(*args, **kwargs)

    monkeypatch.setattr(phase4_host.os, "open", reject_destination_oserror)
    with pytest.raises(HostProtocolError, match="cannot be copied safely"):
        _SubprocessClient._copy_host_transport_authentication(runtime_oserror)
    assert not (runtime_oserror / "auth.json").exists()

    runtime_fake_fds = tmp_path / "runtime-fake-fds"
    runtime_fake_fds.mkdir()
    home_metadata = source_home.stat()
    auth_metadata = (source_home / "auth.json").stat()
    fstat_calls = 0

    def fake_fstat(_fd: int):
        nonlocal fstat_calls
        fstat_calls += 1
        return home_metadata if fstat_calls == 1 else auth_metadata

    monkeypatch.setattr(phase4_host.os, "open", lambda *args, **kwargs: None)
    monkeypatch.setattr(phase4_host.os, "fstat", fake_fstat)
    monkeypatch.setattr(phase4_host.os, "read", lambda *_args: b"")
    monkeypatch.setattr(phase4_host.os, "fsync", lambda _fd: None)
    monkeypatch.setattr(phase4_host.os, "close", lambda _fd: None)
    _SubprocessClient._copy_host_transport_authentication(runtime_fake_fds)


def test_subprocess_call_and_host_binding_accept_the_safe_positive_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = object.__new__(_SubprocessClient)
    client._next_id = 1
    sent: list[dict[str, object]] = []
    client._send = lambda payload: sent.append(dict(payload))
    client._read = lambda _timeout: {"id": 1, "result": {}}
    assert client.call("initialize", {}, timeout_seconds=1) == {"id": 1, "result": {}}
    assert sent[0]["method"] == "initialize"

    request = _request(tmp_path)
    binding = (
        ("/pinned/codex",),
        "/pinned/codex",
        "sha256:" + "c" * 64,
        (("/pinned/codex", "sha256:" + "c" * 64),),
        "/pinned/node",
        "sha256:" + "d" * 64,
    )
    adapter = CodexAppServerAdapter()
    monkeypatch.setattr(adapter, "_resolved_host_binding", lambda: binding)
    matching = replace_authorization(
        request,
        executable=binding[2],
        interpreter=binding[5],
    )
    errors = adapter.validate_invocation(matching)
    assert "HOST_INTERPRETER_FINGERPRINT_MISMATCH" not in errors


def test_transport_binding_and_subprocess_protocol_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "host"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    digest = _digest(executable)
    with pytest.raises(HostProtocolError, match="fingerprint changed"):
        phase4_host._open_pinned_files(((str(executable), "sha256:" + "0" * 64),))
    with pytest.raises(HostProtocolError, match="fingerprint changed"):
        phase4_host._verify_pinned_files(((str(executable), "sha256:" + "0" * 64),))
    assert phase4_host._verify_pinned_files(((str(executable), digest),)) is None

    monkeypatch.setenv("CODEX_EXECUTABLE", str(sys.executable))
    resolved, resolved_digest = phase4_host._resolve_regular_executable("codex")
    assert resolved == Path(sys.executable).resolve()
    assert resolved_digest.startswith("sha256:")
    with pytest.raises(ValueError, match="boolean"):
        CodexAppServerAdapter(host_authentication=1)  # type: ignore[arg-type]

    client = object.__new__(_SubprocessClient)
    client._process = SimpleNamespace(stdout=object())
    with pytest.raises(HostTimeoutError, match="timed out"):
        client._read(0)
    with pytest.raises(HostTimeoutError, match="timed out"):
        client.call("initialize", {}, timeout_seconds=0)

    client = object.__new__(_SubprocessClient)
    client._process = SimpleNamespace(stdout=SimpleNamespace(fileno=lambda: 7), poll=lambda: None)
    client._stdout_buffer = b""
    client.max_line_bytes = 10_000
    client._protocol_message_count = 0
    client._mcp_event_count = 0
    client._approval_request_count = 0
    client._protocol_observations = []
    payload = b'{"jsonrpc":"2.0","result":{}}\n'
    monkeypatch.setattr(
        phase4_host.select, "select", lambda *_args: ([client._process.stdout], [], [])
    )
    monkeypatch.setattr(phase4_host.os, "read", lambda _fd, _limit: payload)
    assert client._read(1) == {"jsonrpc": "2.0", "result": {}}
    assert client.protocol_counts() == (1, 0, 0)


def test_adapter_policy_cancellation_protocol_and_active_session_guards(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    adapter = CodexAppServerAdapter(transport_factory=lambda: FakeAppServerClient())
    for field in (
        "network_policy",
        "shell_policy",
        "mcp_policy",
        "provider_policy",
        "credential_policy",
    ):
        authorization = replace(request.authorization, **{field: "ALLOW"})
        invalid = replace(request, authorization=authorization)
        assert adapter.validate_invocation(invalid)

    client = FakeAppServerClient()
    adapter = CodexAppServerAdapter(transport_factory=lambda: client)
    assert adapter.cancel_invocation(request) == "CANCELLATION_REQUIRES_ACTIVE_SESSION"
    adapter._active_sessions[request.invocation_id] = (client, "thread", "turn")
    assert adapter.cancel_invocation(request) == "HOST_INTERRUPT_REQUESTED"
    failing_client = FakeAppServerClient()
    failing_client.notify = lambda *_args, **_kwargs: (_ for _ in ()).throw(HostProtocolError("no"))  # type: ignore[method-assign]
    adapter._active_sessions[request.invocation_id] = (failing_client, "thread", "turn")
    assert adapter.cancel_invocation(request) == "CANCELLATION_REQUEST_FAILED"
    assert adapter._interrupt(client, "thread", "turn", timeout_seconds=1) == (
        "HOST_INTERRUPT_ACKNOWLEDGED"
    )

    cancelling_client = FakeAppServerClient()

    def cancelled_stream(*, timeout_seconds: float, cancel_event=None):
        del timeout_seconds, cancel_event
        yield {"__phase4_cancel_requested__": True}

    cancelling_client.stream = cancelled_stream  # type: ignore[method-assign]
    cancelled = CodexAppServerAdapter(
        transport_factory=lambda: cancelling_client
    ).request_invocation(
        request,
        budget=Phase4Budget(timeout_seconds=5),
    )
    assert cancelled.status is InvocationResultStatus.CANCELLED
    assert cancelled.cancellation_status == "HOST_INTERRUPT_ACKNOWLEDGED"

    mcp_client = FakeAppServerClient()
    mcp_client.protocol_counts = lambda: (1, 1, 0)  # type: ignore[attr-defined]
    mcp_result = CodexAppServerAdapter(transport_factory=lambda: mcp_client).request_invocation(
        request,
        budget=Phase4Budget(timeout_seconds=5),
    )
    assert mcp_result.status is InvocationResultStatus.FAILURE
    assert mcp_result.error_code == "MCP_EVENT_OBSERVED"
