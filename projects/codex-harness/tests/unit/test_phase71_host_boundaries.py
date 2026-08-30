from __future__ import annotations

import signal
import subprocess
from pathlib import Path
from threading import Event

import pytest
from test_phase7_host import PACKAGE_ROOT, _builder_request  # noqa: E402

import harness_kernel.phase7_host as host
from harness_kernel.phase7_host import (
    HOST_LIST_FILES_TOOL,
    HOST_READ_FILE_TOOL,
    HOST_RUN_TESTS_TOOL,
    HOST_WRITE_FILE_TOOL,
    BackendBuilderAppServerAdapter,
    BoundedBuilderHostTools,
    HostProtocolError,
    HostTestObservation,
    WorkspaceFilesystemPolicy,
    WorkspaceWriteMode,
    _ScopedWorkspaceClient,
    build_backend_filesystem_policy,
    validate_file_change_event,
)


def _policy(tmp_path: Path, *, write: bool = True) -> WorkspaceFilesystemPolicy:
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = tmp_path / "app"
    root.mkdir(exist_ok=True)
    return build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE if write else WorkspaceWriteMode.READ_ONLY,
        allowed_roots=(root,) if write else None,
    )


@pytest.mark.parametrize(
    ("exit_code", "output", "sandbox_mode", "expected"),
    [
        (-256, "", "sandbox", "test exit code"),
        (256, "", "sandbox", "test exit code"),
        (0, "\x00", "sandbox", "test output"),
        (0, "x" * (host._MAX_HOST_TOOL_OUTPUT_BYTES + 1), "sandbox", "output exceeds"),
        (0, "", "", "sandbox mode"),
    ],
)
def test_host_test_observation_is_bounded(
    exit_code: int, output: str, sandbox_mode: str, expected: str
) -> None:
    with pytest.raises(ValueError, match=expected):
        HostTestObservation(exit_code, output, sandbox_mode)


def test_fixed_test_command_is_fail_closed_and_builds_a_bounded_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    assert host._fixed_test_command(Path("relative")) is None
    monkeypatch.setattr(host, "_FIXED_TEST_SANDBOX", tmp_path / "missing-bwrap")
    assert host._fixed_test_command(tests) is None

    sandbox = tmp_path / "bwrap"
    sandbox.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(host, "_FIXED_TEST_SANDBOX", sandbox)
    command = host._fixed_test_command(tests)
    assert command is not None
    assert "--unshare-net" in command
    assert command[-1] == "/workspace/tests"

    (tests / "alias").symlink_to(tmp_path)
    assert host._fixed_test_command(tests) is None


class _NoOutputProcess:
    pid = 1
    returncode = 1
    stdout = None

    def poll(self):
        return self.returncode

    def wait(self, timeout: float | None = None):
        del timeout
        return self.returncode

    def kill(self):
        self.returncode = -signal.SIGKILL


def test_fixed_pytest_handles_start_and_pipe_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "tests"
    root.mkdir()
    monkeypatch.setattr(host, "_fixed_test_command", lambda _root: ["fake"])
    monkeypatch.setattr(
        subprocess, "Popen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("no"))
    )
    assert host.run_fixed_pytest(root).sandbox_mode == "UNAVAILABLE"
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: _NoOutputProcess())
    observation = host.run_fixed_pytest(root)
    assert observation.exit_code == 1
    assert "no output pipe" in observation.output


class _PipeProcess:
    pid = 2
    returncode = 0

    def __init__(self, chunks: list[bytes]) -> None:
        self.stdout = object()
        self._chunks = iter(chunks)
        self.killed = False

    def poll(self):
        return self.returncode if self.killed or not self._chunks else None

    def wait(self, timeout: float | None = None):
        del timeout
        self.killed = True
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -signal.SIGKILL


def test_fixed_pytest_reports_output_bound_and_process_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "tests"
    root.mkdir()
    process = _PipeProcess([b"x" * (host._MAX_HOST_TOOL_OUTPUT_BYTES + 1)])
    monkeypatch.setattr(host, "_fixed_test_command", lambda _root: ["fake"])
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(host.os, "read", lambda _fd, _size: next(process._chunks, b""))
    monkeypatch.setattr(host.selectors.DefaultSelector, "register", lambda self, *args: None)
    monkeypatch.setattr(
        host.selectors.DefaultSelector,
        "get_map",
        lambda self: {1: object()} if not process.killed else {},
    )
    monkeypatch.setattr(
        host.selectors.DefaultSelector,
        "select",
        lambda self, _timeout: [(type("Key", (), {"fd": 1, "fileobj": object()})(), None)],
    )
    monkeypatch.setattr(host.selectors.DefaultSelector, "unregister", lambda self, _file: None)
    observation = host.run_fixed_pytest(root)
    assert observation.exit_code == 124
    assert len(observation.output.encode("utf-8")) <= host._MAX_HOST_TOOL_OUTPUT_BYTES


def test_bounded_tool_constructor_and_schema_branches(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    with pytest.raises(ValueError, match="policy"):
        BoundedBuilderHostTools(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="callable"):
        BoundedBuilderHostTools(policy, test_runner=object())  # type: ignore[arg-type]
    (tmp_path / "outside").mkdir()
    with pytest.raises(ValueError, match="test root"):
        BoundedBuilderHostTools(policy, test_root=tmp_path / "outside")
    with pytest.raises(ValueError, match="requires a test root"):
        BoundedBuilderHostTools(policy, test_runner=lambda _root: None)
    tools = BoundedBuilderHostTools(policy)
    assert HOST_RUN_TESTS_TOOL not in [item["name"] for item in tools.specs()]
    runner_tools = BoundedBuilderHostTools(
        policy, test_root=tmp_path / "app", test_runner=lambda _root: HostTestObservation(0, "ok")
    )
    assert HOST_RUN_TESTS_TOOL in [item["name"] for item in runner_tools.specs()]
    assert tools._arguments(None, ()) is None
    assert tools._arguments({"extra": True}, ()) is None
    assert tools._arguments({1: True}, (1,)) is None  # type: ignore[dict-item]


def test_bounded_tool_candidate_rejects_all_unsafe_shapes(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    tools = BoundedBuilderHostTools(policy)
    for raw in (None, "", "x" * 4097, "https://example.test", "../escape"):
        assert tools._candidate(raw, require_existing=False) is None
    assert tools._candidate("app", require_existing=False) is None
    target = tmp_path / "outside"
    target.write_text("outside", encoding="utf-8")
    (tmp_path / "app" / "link").symlink_to(target)
    assert tools._candidate("app/link", require_existing=False) is None
    assert tools._candidate("app/missing.py", require_existing=True) is None
    assert tools._candidate("/etc/passwd", require_existing=True) is None
    assert tools._candidate("app/missing.py", require_existing=False) is not None


def test_bounded_tool_read_write_and_event_validation_fail_closed(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    tools = BoundedBuilderHostTools(policy)
    assert tools._read({"path": "../x"}).payload["error"] == "PATH_NOT_ALLOWED"
    (tmp_path / "app" / "source.py").write_text("print('ok')\n", encoding="utf-8")
    read = tools._read({"path": "app/source.py"})
    assert read.success is True
    assert read.payload["bytes"] > 0
    (tmp_path / "app" / "binary.py").write_bytes(b"\xff")
    assert tools._read({"path": "app/binary.py"}).payload["error"] == "FILE_READ_REJECTED"
    assert (
        tools._write({"path": "app/a.py", "content": "\x00"}).payload["error"] == "CONTENT_INVALID"
    )
    assert (
        tools._write(
            {"path": "app/a.py", "content": "x" * (host._MAX_HOST_FILE_BYTES + 1)}
        ).payload["error"]
        == "CONTENT_TOO_LARGE"
    )
    assert tools._write({"path": "../a.py", "content": "x"}).payload["error"] == "PATH_NOT_ALLOWED"
    write = tools._write({"path": "app/a.py", "content": "answer = 42\n"})
    assert write.success is True
    assert (tmp_path / "app" / "a.py").read_text(encoding="utf-8") == "answer = 42\n"
    assert tools.write_event_path({"path": "app/a.py", "content": "ok"}) == "app/a.py"
    assert tools.write_event_path({"path": "app/a.py", "content": "\x00"}) is None
    assert tools.write_event_path({"path": "app/a.py", "content": "\udcff"}) is None


def test_bounded_tool_handles_non_regular_targets_and_write_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _policy(tmp_path)
    tools = BoundedBuilderHostTools(policy)
    directory = tmp_path / "app" / "directory"
    directory.mkdir()
    assert (
        tools._write({"path": "app/directory", "content": "x"}).payload["error"]
        == "TARGET_NOT_REGULAR"
    )
    monkeypatch.setattr(
        BoundedBuilderHostTools,
        "_directory_fd",
        lambda _self, *_args: (_ for _ in ()).throw(OSError("open")),
    )
    assert (
        tools._write({"path": "app/error.py", "content": "x"}).payload["error"]
        == "FILE_WRITE_REJECTED"
    )

    class _BadDescriptor:
        def __init__(self) -> None:
            self.closed = False

    descriptor = _BadDescriptor()
    monkeypatch.setattr(host.os, "read", lambda *_args: (_ for _ in ()).throw(OSError("read")))
    with pytest.raises(OSError):
        tools._read_descriptor(descriptor)  # type: ignore[arg-type]


def test_bounded_tool_list_and_test_observer_paths(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    app = tmp_path / "app"
    (app / "source.py").write_text("ok", encoding="utf-8")
    (app / ".pytest_cache").mkdir()
    (app / ".pytest_cache" / "ignored").write_text("x", encoding="utf-8")
    (app / "link").symlink_to(app / "source.py")
    tools = BoundedBuilderHostTools(policy)
    listed = tools._list()
    assert listed.success is True
    assert listed.payload["paths"] == ["app/source.py"]
    no_runner = tools._tests()
    assert no_runner.payload["error"] == "TEST_RUNNER_UNAVAILABLE"

    failing = BoundedBuilderHostTools(
        policy,
        test_root=app,
        test_runner=lambda _root: (_ for _ in ()).throw(RuntimeError("failed")),
    )
    assert failing._tests().payload["error"] == "TEST_RUNNER_FAILED"
    invalid = BoundedBuilderHostTools(policy, test_root=app, test_runner=lambda _root: object())
    assert invalid._tests().payload["error"] == "TEST_RUNNER_RESULT_INVALID"
    observed = BoundedBuilderHostTools(
        policy,
        test_root=app,
        test_runner=lambda _root: HostTestObservation(1, "failure"),
    )
    result = observed._tests()
    assert result.success is True
    assert result.payload["status"] == "FAIL"

    assert tools.dispatch(HOST_LIST_FILES_TOOL, {}).success is True
    assert tools.dispatch(HOST_READ_FILE_TOOL, {"path": "app/source.py"}).success is True
    assert (
        tools.dispatch(HOST_WRITE_FILE_TOOL, {"path": "app/new.py", "content": "new"}).success
        is True
    )
    assert tools.dispatch(HOST_RUN_TESTS_TOOL, {}).payload["error"] == "TEST_RUNNER_UNAVAILABLE"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ({}, "not a file-change"),
        ({"method": "item/file_change", "params": {}}, "no declared path"),
        (
            {
                "method": "command/file_change/execute",
                "params": {"item": {"changes": [{"path": "app/a.py"}]}},
            },
            "host action",
        ),
        (
            {
                "method": "item/file_change",
                "params": {"item": {"type": "fileChange", "changes": [{"path": "../a.py"}]}},
            },
            "traversal",
        ),
        (
            {
                "method": "item/file_change",
                "params": {"item": {"type": "fileChange", "changes": [{"path": "https://x"}]}},
            },
            "local",
        ),
    ],
)
def test_file_change_events_reject_invalid_shapes(tmp_path: Path, message, expected: str) -> None:
    with pytest.raises(HostProtocolError, match=expected):
        validate_file_change_event(message, _policy(tmp_path))


def test_file_change_event_accepts_nested_paths_and_relative_pilot_paths(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    message = {
        "method": "item/file-change",
        "params": {
            "item": {
                "type": "fileChange",
                "changes": [{"path": "app/a.py"}, {"file_path": "app/a.py"}],
            }
        },
    }
    assert validate_file_change_event(message, policy) == ("app/a.py",)

    relative_policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(tmp_path / "app",),
    )
    assert validate_file_change_event(
        {"method": "file_change", "params": {"item": {"path": "a.py"}}}, relative_policy
    ) == ("app/a.py",)


def test_workspace_policy_properties_and_boundaries(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    assert policy.workspace_root == tmp_path.resolve()
    assert policy.write_enabled is True
    assert policy.read_only is False
    assert policy.allowed_write_roots == ((tmp_path / "app").resolve(),)
    assert policy.allows_write("app/new.py") is True
    assert policy.allows_write("../escape") is False
    assert policy.can_write("app/new.py") is True
    assert policy.can_write(".agent/state.json") is False
    assert policy.as_mapping()["package_write_allowed"] is False
    read_only = _policy(tmp_path / "readonly", write=False)
    assert read_only.write_enabled is False
    assert read_only.allowed_write_roots == ()
    assert read_only.allows_write("anything") is False

    with pytest.raises(ValueError, match="mode"):
        build_backend_filesystem_policy(tmp_path, mode="unknown")
    with pytest.raises(ValueError, match="explicit"):
        build_backend_filesystem_policy(tmp_path, mode=WorkspaceWriteMode.WORKSPACE_WRITE)
    with pytest.raises(ValueError, match="whole workspace"):
        build_backend_filesystem_policy(
            tmp_path, mode=WorkspaceWriteMode.WORKSPACE_WRITE, allowed_roots=(tmp_path,)
        )
    with pytest.raises(ValueError, match="positive"):
        build_backend_filesystem_policy(tmp_path, max_files=0)


def test_authorization_and_filesystem_policy_matching_reject_invalid_declarations(
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
    adapter = BackendBuilderAppServerAdapter(
        filesystem_policy=policy,
        trusted_authorization=request.authorization,
        project_root=tmp_path,
        clock=lambda: float(request.authorization.issued_at + 1),
    )
    assert host._authorization_binding_errors(request, None, time_fn := (lambda: 0)) == (
        "AUTHORIZATION_NOT_BOUND",
    )
    del time_fn
    future = request.authorization
    future_request = request.__class__(
        invocation_id=request.invocation_id,
        authorization=future,
        context=request.context,
        skill_name=request.skill_name,
        skill_path=request.skill_path,
        task=request.task,
        acceptance_criteria=request.acceptance_criteria,
        workspace=request.workspace,
        expected_artifacts=request.expected_artifacts,
        idempotency_key=request.idempotency_key,
    )
    assert host._authorization_binding_errors(future_request, request.authorization, lambda: 0) == (
        "AUTHORIZATION_NOT_YET_VALID",
    )
    declared = dict(request.authorization.filesystem_policy)
    declared.pop("workspace")
    assert host._filesystem_policy_matches(declared, policy) is False
    declared = dict(request.authorization.filesystem_policy)
    declared["allowed_roots"] = "bad"
    assert host._filesystem_policy_matches(declared, policy) is False
    declared = dict(request.authorization.filesystem_policy)
    declared["mode"] = "unknown"
    assert host._filesystem_policy_matches(declared, policy) is False
    assert adapter._validate_filesystem_policy(request) == ()


def test_dynamic_request_validation_and_event_reservation(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    adapter = BackendBuilderAppServerAdapter(filesystem_policy=policy)
    assert adapter._dynamic_tool_fields({"params": {}}) is None
    assert (
        adapter._dynamic_tool_fields(
            {"params": {"tool": "x", "callId": "y", "arguments": {}, "namespace": "bad"}}
        )
        is None
    )
    assert adapter._dynamic_tool_fields(
        {"params": {"tool": "x", "callId": "y", "arguments": {}, "namespace": None}}
    ) == ("x", "y", {})
    assert adapter._is_dynamic_tool_request({"method": "item/tool/call", "id": "x"}) is True
    assert adapter._is_dynamic_tool_request({"method": "other", "id": "x"}) is False
    assert adapter._dynamic_tool_response(host._tool_ok({"value": "ok"}))["success"] is True
    large = host._tool_ok({"content": "x" * host._MAX_HOST_TOOL_OUTPUT_BYTES})
    assert adapter._dynamic_tool_response(large)["success"] is False

    tools = BoundedBuilderHostTools(policy)
    event_token = adapter._event_paths_context.set(set())
    try:
        planned, reserved, error = adapter._reserve_write_event_path(
            tools, {"path": "app/new.py", "content": "x"}
        )
        assert (planned, reserved, error) == ("app/new.py", True, None)
        assert adapter._reserve_write_event_path(tools, {"path": "app/new.py", "content": "x"}) == (
            "app/new.py",
            False,
            None,
        )
        adapter._release_write_event_path(planned, reserved)
        assert adapter._event_paths_context.get() == set()
    finally:
        adapter._event_paths_context.reset(event_token)


class _RecordingDelegate:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call(self, method: str, params: dict[str, object], *, timeout_seconds: float):
        self.calls.append((method, params))
        return {"method": method}

    def notify(self, method: str, params: dict[str, object]) -> None:
        self.calls.append((method, params))

    def respond(self, request_id: object, result: dict[str, object]) -> None:
        self.calls.append((str(request_id), result))

    def stream(self, *, timeout_seconds: float, cancel_event: Event | None = None):
        del timeout_seconds, cancel_event
        yield {"event": "ok"}

    def close(self) -> None:
        self.calls.append(("close", {}))


def test_scoped_workspace_client_rewrites_only_declared_methods(tmp_path: Path) -> None:
    delegate = _RecordingDelegate()
    client = _ScopedWorkspaceClient(delegate, (tmp_path / "app",), skill_discovery_root=tmp_path)
    client.call("thread/start", {}, timeout_seconds=1)
    client.call("skills/list", {}, timeout_seconds=1)
    client.call("other", {}, timeout_seconds=1)
    assert delegate.calls[0][1]["runtimeWorkspaceRoots"] == [str(tmp_path / "app")]
    assert delegate.calls[1][1]["cwds"] == [str(tmp_path)]
    assert list(client.stream(timeout_seconds=1)) == [{"event": "ok"}]
    client.close()


def test_dynamic_completion_and_file_change_host_action_classification(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    adapter = BackendBuilderAppServerAdapter()
    policy_token = adapter._policy_context.set(policy)
    event_token = adapter._event_paths_context.set(set())
    calls_token = adapter._dynamic_call_ids_context.set({"call-1"})
    items_token = adapter._dynamic_item_ids_context.set({"item-1"})
    try:
        started = {
            "method": "item/started",
            "params": {"item": {"type": "dynamic_tool_call", "id": "item-1"}},
        }
        completed = {
            "method": "item/completed",
            "params": {"item": {"type": "dynamic-tool-call", "callId": "call-1"}},
        }
        assert adapter._is_dynamic_tool_completion(started) is True
        assert adapter._is_dynamic_tool_completion(completed) is True
        assert adapter._is_forbidden_host_action(started) is False
        assert adapter._is_forbidden_host_action({"method": "shell/run"}) is True
        event = adapter._event_from_message(
            {
                "method": "item/file_change",
                "params": {"item": {"type": "fileChange", "path": "app/x.py"}},
            },
            sequence=0,
            detail="changed",
        )
        assert event.event_class == "WORKSPACE_FILE_CHANGE"
    finally:
        adapter._dynamic_item_ids_context.reset(items_token)
        adapter._dynamic_call_ids_context.reset(calls_token)
        adapter._event_paths_context.reset(event_token)
        adapter._policy_context.reset(policy_token)
