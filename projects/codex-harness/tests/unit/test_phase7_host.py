from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest

import harness_kernel.phase7_host as phase7_host
from harness_kernel.phase4_models import (
    CapabilityExecutionAuthorization,
    CapabilityInvocationRequest,
    ContextManifest,
    ExecutionMode,
    Phase4Budget,
    digest_payload,
)
from harness_kernel.phase7_backend import package_fingerprint
from harness_kernel.phase7_host import (
    HOST_LIST_FILES_TOOL,
    HOST_READ_FILE_TOOL,
    HOST_RUN_TESTS_TOOL,
    HOST_WRITE_FILE_TOOL,
    BackendBuilderAppServerAdapter,
    BackendVerifierAppServerAdapter,
    BoundedBuilderHostTools,
    HostProtocolError,
    HostTestObservation,
    VerificationLoopVNextAppServerAdapter,
    WorkspaceWriteMode,
    build_backend_filesystem_policy,
    run_fixed_pytest,
    validate_file_change_event,
)

PROJECT_ROOT = Path(__file__).parents[2]
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "backend-engineering-vnext"


class _BuilderFakeAppServerClient:
    def __init__(self, workspace: Path, *, outside_write: bool = False) -> None:
        self.workspace = workspace
        self.outside_write = outside_write
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call(
        self, method: str, params: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]:
        del timeout_seconds
        self.calls.append((method, params))
        if method == "initialize":
            return {"result": {"userAgent": "fake-codex"}}
        if method == "skills/list":
            return {"result": {"data": []}}
        if method == "thread/start":
            return {"result": {"thread": {"id": "thread-builder", "sessionId": "session"}}}
        if method == "turn/start":
            target = (
                self.workspace / "README.md"
                if self.outside_write
                else self.workspace / "app" / "builder_touch.py"
            )
            target.write_text("builder touch\n", encoding="utf-8")
            return {"result": {"turn": {"id": "turn-builder"}}}
        raise AssertionError(method)

    def notify(self, method: str, params: dict[str, object]) -> None:
        del method, params

    def respond(self, request_id: object, result: dict[str, object]) -> None:
        del request_id, result

    def stream(
        self, *, timeout_seconds: float, cancel_event: Event | None = None
    ) -> Iterator[dict[str, object]]:
        del timeout_seconds, cancel_event
        path = "README.md" if self.outside_write else "app/builder_touch.py"
        yield {
            "method": "item/fileChange",
            "params": {
                "threadId": "thread-builder",
                "turnId": "turn-builder",
                "item": {
                    "type": "fileChange",
                    "changes": [{"path": path}],
                },
            },
        }
        yield {
            "method": "item/completed",
            "params": {
                "threadId": "thread-builder",
                "turnId": "turn-builder",
                "item": {"type": "agentMessage", "text": "P7_BUILDER_DONE"},
            },
        }
        yield {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-builder",
                "turn": {"id": "turn-builder", "status": "completed"},
            },
        }

    def close(self) -> None:
        pass


def _builder_request(workspace: Path) -> CapabilityInvocationRequest:
    task = "Apply one bounded backend validation hardening change."
    criteria = ("only the declared pilot root changes", "return a bounded response")
    fingerprint = package_fingerprint(PACKAGE_ROOT)
    authorization = CapabilityExecutionAuthorization(
        authorization_id="AUTH-P7-HOST-1",
        task_id="TASK-P7-HOST-1",
        run_id="RUN-P7-HOST-1",
        capability_id="backend-engineering-vnext",
        capability_version="0.1.0",
        package_fingerprint=fingerprint,
        scope="PROJECT",
        requested_loading_level="L2_INSTRUCTION_KERNEL",
        requested_execution_mode=ExecutionMode.CONTROLLED_REAL,
        allowed_tools=(),
        allowed_side_effects=(),
        filesystem_policy={
            "workspace": str(workspace.resolve()),
            "mode": "WORKSPACE_WRITE",
            "allowed_roots": (
                str((workspace / "app").resolve()),
                str((workspace / "migrations").resolve()),
            ),
            "package_path": str(PACKAGE_ROOT),
            "package_write_allowed": False,
            "network": "DENY",
            "shell": "DENY",
            "mcp": "DENY",
            "providers": "DENY",
            "credentials": "DENY",
            "host_executable_digest": None,
            "host_interpreter_digest": None,
            "max_files": 256,
            "max_bytes": 16 * 1024 * 1024,
        },
        network_policy="DENY",
        shell_policy="DENY",
        provider_policy="DENY",
        mcp_policy="DENY",
        credential_policy="DENY",
        timeout_seconds=20,
        iteration_budget={"host_calls": 1, "tool_calls": 0},
        context_budget={"max_bytes": 32_000},
        artifact_policy={"types": ("HOST_RESPONSE", "FILE")},
        evidence_policy={"max_events": 40},
        issued_by="test",
        issued_at=int(time.time()) - 5,
        expires_at=int(time.time()) + 120,
        reason="bounded workspace-write host test",
        constraints=("no tools", "no external boundaries"),
    )
    context = ContextManifest(
        task_id=authorization.task_id,
        task_digest=digest_payload(task),
        capability_id=authorization.capability_id,
        package_fingerprint=fingerprint,
        skill_path=str(PACKAGE_ROOT / "SKILL.md"),
        sources=("HOST_MANAGED_SKILL",),
        selected_references=(),
        omitted_references=(),
        estimated_bytes=2_000,
        digest="sha256:" + "2" * 64,
        acceptance_criteria=criteria,
    )
    return CapabilityInvocationRequest(
        invocation_id="INV-P7-HOST-1",
        authorization=authorization,
        context=context,
        skill_name=authorization.capability_id,
        skill_path=context.skill_path,
        task=task,
        acceptance_criteria=criteria,
        workspace=str(workspace.resolve()),
        expected_artifacts=("HOST_RESPONSE", "FILE"),
        idempotency_key="idem-p7-host-1",
    )


def test_backend_filesystem_policy_is_read_only_by_default(tmp_path: Path) -> None:
    policy = build_backend_filesystem_policy(tmp_path)

    assert policy.mode is WorkspaceWriteMode.READ_ONLY
    assert policy.allowed_roots == (tmp_path.resolve(),)
    assert policy.package_write_allowed is False


def test_backend_filesystem_policy_requires_a_bounded_write_root(tmp_path: Path) -> None:
    pilot = tmp_path / "pilot"
    pilot.mkdir()

    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(pilot,),
        package_path=tmp_path / ".harness" / "capabilities" / "backend-engineering-vnext",
    )

    assert policy.mode is WorkspaceWriteMode.WORKSPACE_WRITE
    assert policy.allowed_roots == (pilot.resolve(),)
    assert policy.package_write_allowed is False
    assert policy.network == "DENY"
    assert policy.shell == "DENY"
    assert policy.mcp == "DENY"
    assert policy.providers == "DENY"
    assert policy.credentials == "DENY"


def test_fixed_pytest_isolates_host_credentials_network_and_workspace(tmp_path: Path) -> None:
    test_root = tmp_path / "tests"
    test_root.mkdir()
    host_home = str(Path.home())
    (test_root / "test_untrusted.py").write_text(
        f"""
from pathlib import Path
import socket
import subprocess
import sys


def test_untrusted_code_cannot_escape_host_boundaries():
    assert not Path({host_home!r}, ".codex", "auth.json").exists()
    assert not (Path.home() / ".codex" / "auth.json").exists()
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; assert not (Path.home() / '.codex' / 'auth.json').exists()",
        ],
        check=True,
        capture_output=True,
    )
    assert child.returncode == 0
    try:
        socket.create_connection(("198.51.100.1", 80), timeout=0.2)
    except OSError:
        pass
    else:
        raise AssertionError("network namespace unexpectedly reached an external address")
    try:
        (Path(__file__).parents[1] / "escape-marker").write_text("escape")
    except OSError:
        pass
    else:
        raise AssertionError("read-only workspace mount accepted an escape write")
""",
        encoding="utf-8",
    )

    observation = run_fixed_pytest(test_root)

    if observation.sandbox_mode == "UNAVAILABLE":
        pytest.skip("fixed test isolation requires the supported project virtualenv")
    assert observation.exit_code == 0, observation.output
    assert observation.sandbox_mode == "BWRAP_UNSHARED_NET_PID_READ_ONLY_WORKSPACE"
    assert not (tmp_path / "escape-marker").exists()


def test_fixed_pytest_requires_the_supported_virtualenv(tmp_path: Path, monkeypatch) -> None:
    test_root = tmp_path / "tests"
    test_root.mkdir()
    monkeypatch.setattr(phase7_host.sys, "prefix", "/usr")
    monkeypatch.setattr(phase7_host.sys, "base_prefix", "/usr")

    observation = phase7_host.run_fixed_pytest(test_root)

    assert observation.exit_code == 1
    assert observation.sandbox_mode == "UNAVAILABLE"


def test_backend_filesystem_policy_rejects_control_plane_roots(tmp_path: Path) -> None:
    agent_root = tmp_path / ".agent"
    capability_root = tmp_path / ".harness" / "capabilities"
    agent_root.mkdir()
    capability_root.mkdir(parents=True)

    with pytest.raises(ValueError, match="protected"):
        build_backend_filesystem_policy(
            tmp_path,
            mode=WorkspaceWriteMode.WORKSPACE_WRITE,
            allowed_roots=(agent_root,),
        )
    with pytest.raises(ValueError, match="protected"):
        build_backend_filesystem_policy(
            tmp_path,
            mode=WorkspaceWriteMode.WORKSPACE_WRITE,
            allowed_roots=(capability_root,),
        )


def test_backend_adapters_expose_distinct_sandbox_contracts() -> None:
    builder = BackendBuilderAppServerAdapter()
    verifier = BackendVerifierAppServerAdapter()
    composition_verifier = VerificationLoopVNextAppServerAdapter(instruction_kernel="kernel")

    assert builder.thread_sandbox == "workspace-write"
    assert builder.turn_sandbox == {"type": "workspaceWrite", "networkAccess": False}
    assert verifier.thread_sandbox == "read-only"
    assert verifier.turn_sandbox == {"type": "readOnly", "networkAccess": False}
    assert composition_verifier.thread_sandbox == "read-only"
    assert composition_verifier.turn_sandbox == {"type": "readOnly", "networkAccess": False}


def test_builder_rejects_command_event_disguised_as_file_change(tmp_path: Path) -> None:
    pilot = tmp_path / "app"
    pilot.mkdir()
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(pilot,),
    )
    adapter = BackendBuilderAppServerAdapter()
    message = {
        "method": "command/file_change/execute",
        "params": {"item": {"type": "fileChange", "changes": [{"path": "app/main.py"}]}},
    }

    with pytest.raises(HostProtocolError):
        validate_file_change_event(message, policy)
    policy_token = adapter._policy_context.set(policy)
    event_token = adapter._event_paths_context.set(set())
    try:
        assert adapter._is_forbidden_host_action(message) is True
    finally:
        adapter._event_paths_context.reset(event_token)
        adapter._policy_context.reset(policy_token)


def test_composition_verifier_injects_loaded_kernel_without_typed_skill(tmp_path: Path) -> None:
    request = _builder_request(tmp_path)
    adapter = VerificationLoopVNextAppServerAdapter(instruction_kernel="loaded-kernel")

    params = adapter._turn_params(request, "thread-verifier")

    input_items = params["input"]
    assert isinstance(input_items, list)
    assert not any(isinstance(item, dict) and item.get("type") == "skill" for item in input_items)
    assert any(
        isinstance(item, dict)
        and item.get("type") == "text"
        and "loaded-kernel" in item.get("text", "")
        for item in input_items
    )
    assert params["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}


def test_builder_invocation_uses_authenticated_package_and_bounded_workspace_write(
    tmp_path: Path,
) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "migrations").mkdir()
    client = _BuilderFakeAppServerClient(tmp_path)
    request = _builder_request(tmp_path)
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(tmp_path / "app", tmp_path / "migrations"),
        package_path=PACKAGE_ROOT,
    )
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

    assert result.status.value == "SUCCESS"
    assert result.execution_observed is True
    assert result.final_message == "P7_BUILDER_DONE"
    assert adapter.last_workspace_delta is not None
    assert adapter.last_workspace_delta.ok is True
    assert adapter.last_workspace_delta.changed_paths == ("app/builder_touch.py",)
    thread_params = next(params for method, params in client.calls if method == "thread/start")
    turn_params = next(params for method, params in client.calls if method == "turn/start")
    assert thread_params["sandbox"] == "workspace-write"
    assert turn_params["sandboxPolicy"] == {
        "type": "workspaceWrite",
        "networkAccess": False,
        "allowedRoots": [
            str((tmp_path / "app").resolve()),
            str((tmp_path / "migrations").resolve()),
        ],
    }
    assert turn_params["runtimeWorkspaceRoots"] == [
        str((tmp_path / "app").resolve()),
        str((tmp_path / "migrations").resolve()),
    ]


def test_bounded_builder_tools_expose_only_host_owned_operations(tmp_path: Path) -> None:
    app = tmp_path / "app"
    tests = tmp_path / "tests"
    app.mkdir()
    tests.mkdir()
    source = app / "existing.py"
    source.write_text("answer = 41\n", encoding="utf-8")
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(app, tests),
    )
    tools = BoundedBuilderHostTools(
        policy,
        test_root=tests,
        test_runner=lambda root: HostTestObservation(0, f"tested {root.name}"),
    )

    assert [item["name"] for item in tools.specs()] == [
        HOST_LIST_FILES_TOOL,
        HOST_READ_FILE_TOOL,
        HOST_WRITE_FILE_TOOL,
        HOST_RUN_TESTS_TOOL,
    ]
    read = tools.dispatch(HOST_READ_FILE_TOOL, {"path": "app/existing.py"})
    assert read.success is True
    assert read.payload["path"] == "app/existing.py"
    assert read.payload["content"] == "answer = 41\n"

    write = tools.dispatch(
        HOST_WRITE_FILE_TOOL,
        {"path": "app/generated.py", "content": "answer = 42\n"},
    )
    assert write.success is True
    assert (app / "generated.py").read_text(encoding="utf-8") == "answer = 42\n"

    listed = tools.dispatch(HOST_LIST_FILES_TOOL, {})
    assert listed.success is True
    assert listed.payload["paths"] == ["app/existing.py", "app/generated.py"]

    tested = tools.dispatch(HOST_RUN_TESTS_TOOL, {})
    assert tested.success is True
    assert tested.payload["exit_code"] == 0


def test_bounded_builder_tools_reject_unsafe_paths_and_arguments(tmp_path: Path) -> None:
    app = tmp_path / "app"
    outside = tmp_path / "outside.py"
    app.mkdir()
    outside.write_text("secret\n", encoding="utf-8")
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(app,),
    )
    tools = BoundedBuilderHostTools(policy)

    for arguments in (
        {"path": "../outside.py"},
        {"path": str(outside)},
        {"path": "app/missing.py", "extra": True},
        {"path": "app/"},
    ):
        result = tools.dispatch(HOST_READ_FILE_TOOL, arguments)
        assert result.success is False

    assert tools.dispatch("unregistered_tool", {}).success is False
    assert tools.dispatch(HOST_WRITE_FILE_TOOL, {"path": "app/a.py"}).success is False
    assert tools.dispatch(HOST_RUN_TESTS_TOOL, {}).success is False


def test_bounded_builder_tools_reject_symlink_targets(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    (app / "link.py").symlink_to(outside)
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(app,),
    )
    tools = BoundedBuilderHostTools(policy)

    assert tools.dispatch(HOST_READ_FILE_TOOL, {"path": "app/link.py"}).success is False
    assert (
        tools.dispatch(
            HOST_WRITE_FILE_TOOL,
            {"path": "app/link.py", "content": "replacement\n"},
        ).success
        is False
    )
    assert outside.read_text(encoding="utf-8") == "outside\n"


class _DynamicBuilderFakeAppServerClient(_BuilderFakeAppServerClient):
    def __init__(self, workspace: Path, tool: str, arguments: dict[str, object]) -> None:
        super().__init__(workspace)
        self.tool = tool
        self.arguments = arguments
        self.responses: list[tuple[object, dict[str, object]]] = []

    def call(
        self, method: str, params: dict[str, object], *, timeout_seconds: float
    ) -> dict[str, object]:
        del timeout_seconds
        if method == "initialize":
            response = {"result": {"userAgent": "fake-codex"}}
        elif method == "skills/list":
            response = {"result": {"data": []}}
        elif method == "thread/start":
            response = {"result": {"thread": {"id": "thread-builder", "sessionId": "session"}}}
        elif method == "turn/start":
            response = {"result": {"turn": {"id": "turn-builder"}}}
        else:
            raise AssertionError(method)
        if method == "thread/start":
            assert params["dynamicTools"]
        return response

    def respond(self, request_id: object, result: dict[str, object]) -> None:
        self.responses.append((request_id, result))

    def stream(
        self, *, timeout_seconds: float, cancel_event: Event | None = None
    ) -> Iterator[dict[str, object]]:
        del timeout_seconds, cancel_event
        yield {
            "method": "item/started",
            "params": {
                "threadId": "thread-builder",
                "turnId": "turn-builder",
                "item": {"type": "dynamicToolCall", "id": "call-1"},
            },
        }
        yield {
            "id": "dynamic-request-1",
            "method": "item/tool/call",
            "params": {
                "threadId": "thread-builder",
                "turnId": "turn-builder",
                "callId": "call-1",
                "tool": self.tool,
                "namespace": None,
                "arguments": self.arguments,
            },
        }
        yield {
            "method": "item/completed",
            "params": {
                "threadId": "thread-builder",
                "turnId": "turn-builder",
                "item": {"type": "dynamicToolCall", "id": "call-1"},
            },
        }
        yield {
            "method": "item/completed",
            "params": {
                "threadId": "thread-builder",
                "turnId": "turn-builder",
                "item": {"type": "agentMessage", "text": "P7_BUILDER_DONE"},
            },
        }
        yield {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-builder",
                "turn": {"id": "turn-builder", "status": "completed"},
            },
        }


def test_builder_handles_official_dynamic_tool_call_and_records_response(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "migrations").mkdir()
    request = _builder_request(tmp_path)
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(tmp_path / "app", tmp_path / "migrations"),
        package_path=PACKAGE_ROOT,
    )
    client = _DynamicBuilderFakeAppServerClient(
        tmp_path,
        HOST_WRITE_FILE_TOOL,
        {"path": "app/dynamic.py", "content": "created = True\n"},
    )
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

    assert result.status.value == "SUCCESS"
    assert (tmp_path / "app" / "dynamic.py").read_text(encoding="utf-8") == "created = True\n"
    assert client.responses[0][0] == "dynamic-request-1"
    response = client.responses[0][1]
    assert response["success"] is True
    content = response["contentItems"][0]["text"]
    assert json.loads(content)["path"] == "app/dynamic.py"
    assert any(event.event_class == "BOUNDED_HOST_TOOL_CALL" for event in result.events)


def test_builder_rejects_write_before_dispatch_when_event_path_budget_is_full(
    tmp_path: Path,
) -> None:
    app = tmp_path / "app"
    app.mkdir()
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(app,),
        package_path=PACKAGE_ROOT,
    )
    adapter = BackendBuilderAppServerAdapter()
    client = _DynamicBuilderFakeAppServerClient(
        tmp_path,
        HOST_WRITE_FILE_TOOL,
        {"path": "app/blocked.py", "content": "must not be written\n"},
    )
    message = {
        "id": "dynamic-request-budget",
        "method": "item/tool/call",
        "params": {
            "threadId": "thread-builder",
            "turnId": "turn-builder",
            "callId": "call-budget",
            "tool": HOST_WRITE_FILE_TOOL,
            "namespace": None,
            "arguments": client.arguments,
        },
    }
    policy_token = adapter._policy_context.set(policy)
    event_token = adapter._event_paths_context.set(
        {f"app/existing-{index}.py" for index in range(64)}
    )
    tools_token = adapter._host_tools_context.set(BoundedBuilderHostTools(policy))
    calls_token = adapter._dynamic_call_ids_context.set(set())
    try:
        handled, error = adapter._handle_host_request(
            message,
            client,
            [],
            Phase4Budget(timeout_seconds=5, max_host_events=20),
        )
    finally:
        adapter._dynamic_call_ids_context.reset(calls_token)
        adapter._host_tools_context.reset(tools_token)
        adapter._event_paths_context.reset(event_token)
        adapter._policy_context.reset(policy_token)

    assert handled is True
    assert error == "HOST_TOOL_WRITE_BUDGET_EXCEEDED"
    assert not (app / "blocked.py").exists()


def test_builder_rolls_back_reservation_after_write_observation_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = tmp_path / "app"
    app.mkdir()
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(app,),
        package_path=PACKAGE_ROOT,
    )
    adapter = BackendBuilderAppServerAdapter()
    client = _DynamicBuilderFakeAppServerClient(
        tmp_path,
        HOST_WRITE_FILE_TOOL,
        {"path": "app/actual.py", "content": "created = True\n"},
    )
    message = {
        "id": "dynamic-request-mismatch",
        "method": "item/tool/call",
        "params": {
            "threadId": "thread-builder",
            "turnId": "turn-builder",
            "callId": "call-mismatch",
            "tool": HOST_WRITE_FILE_TOOL,
            "namespace": None,
            "arguments": client.arguments,
        },
    }
    original_dispatch = BoundedBuilderHostTools.dispatch

    def mismatched_dispatch(
        host_tools: BoundedBuilderHostTools,
        name: object,
        arguments: object,
    ) -> object:
        result = original_dispatch(host_tools, name, arguments)
        if name == HOST_WRITE_FILE_TOOL and result.success:
            return phase7_host._BoundedHostToolResult(
                True,
                {"path": "app/reported.py", "bytes": result.payload["bytes"]},
            )
        return result

    monkeypatch.setattr(BoundedBuilderHostTools, "dispatch", mismatched_dispatch)
    event_paths: set[str] = set()
    policy_token = adapter._policy_context.set(policy)
    event_token = adapter._event_paths_context.set(event_paths)
    tools_token = adapter._host_tools_context.set(BoundedBuilderHostTools(policy))
    calls_token = adapter._dynamic_call_ids_context.set(set())
    try:
        handled, error = adapter._handle_host_request(
            message,
            client,
            [],
            Phase4Budget(timeout_seconds=5, max_host_events=20),
        )
    finally:
        adapter._dynamic_call_ids_context.reset(calls_token)
        adapter._host_tools_context.reset(tools_token)
        adapter._event_paths_context.reset(event_token)
        adapter._policy_context.reset(policy_token)

    assert handled is True
    assert error == "HOST_TOOL_WRITE_OBSERVATION_MISMATCH"
    assert (app / "actual.py").exists()
    assert event_paths == set()


def test_builder_fails_closed_on_unknown_dynamic_tool(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "migrations").mkdir()
    request = _builder_request(tmp_path)
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(tmp_path / "app", tmp_path / "migrations"),
        package_path=PACKAGE_ROOT,
    )
    client = _DynamicBuilderFakeAppServerClient(tmp_path, "not-allowed", {})
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

    assert result.status.value == "FAILURE"
    assert result.error_code == "UNAUTHORIZED_DYNAMIC_TOOL"
    assert client.responses[0][1]["success"] is False


def test_builder_enforces_attempt_budget_across_invocations(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "migrations").mkdir()
    client = _BuilderFakeAppServerClient(tmp_path)
    request = _builder_request(tmp_path)
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(tmp_path / "app", tmp_path / "migrations"),
        package_path=PACKAGE_ROOT,
    )
    adapter = BackendBuilderAppServerAdapter(
        transport_factory=lambda: client,
        filesystem_policy=policy,
        trusted_authorization=request.authorization,
        project_root=tmp_path,
    )
    budget = Phase4Budget(timeout_seconds=5, max_host_events=20)

    first = adapter.request_invocation(request, budget=budget)
    second = adapter.request_invocation(request, budget=budget)
    third = adapter.request_invocation(request, budget=budget)

    assert first.status.value == "SUCCESS"
    assert second.status.value == "SUCCESS"
    assert third.status.value == "BLOCKED"
    assert third.error_code == "BUILDER_ATTEMPT_BUDGET_EXHAUSTED"
    assert len([method for method, _ in client.calls if method == "initialize"]) == 2


def test_builder_invocation_fails_closed_on_undeclared_workspace_mutation(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "migrations").mkdir()
    client = _BuilderFakeAppServerClient(tmp_path, outside_write=True)
    request = _builder_request(tmp_path)
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(tmp_path / "app", tmp_path / "migrations"),
        package_path=PACKAGE_ROOT,
    )
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

    assert result.status.value == "FAILURE"
    assert result.error_code == "WORKSPACE_DELTA_UNAUTHORIZED"
    assert adapter.last_workspace_delta is not None
    assert adapter.last_workspace_delta.ok is False
    assert adapter.last_workspace_delta.unauthorized_paths == ("README.md",)


def test_builder_requires_host_bound_policy_and_authorization(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "migrations").mkdir()
    client = _BuilderFakeAppServerClient(tmp_path)
    adapter = BackendBuilderAppServerAdapter(transport_factory=lambda: client)

    result = adapter.request_invocation(
        _builder_request(tmp_path),
        budget=Phase4Budget(timeout_seconds=5, max_host_events=20),
    )

    assert result.status.value == "BLOCKED"
    assert result.error_code in {"AUTHORIZATION_NOT_BOUND", "FILESYSTEM_POLICY_NOT_BOUND"}
    assert client.calls == []


def test_builder_rejects_forged_authorization_even_when_request_is_well_formed(
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
    client = _BuilderFakeAppServerClient(tmp_path)
    adapter = BackendBuilderAppServerAdapter(
        transport_factory=lambda: client,
        filesystem_policy=policy,
        trusted_authorization=request.authorization,
        project_root=tmp_path,
    )
    forged_authorization = replace(
        request.authorization,
        authorization_id="AUTH-P7-FORGED",
        issued_by="forged-issuer",
    )
    forged_request = replace(request, authorization=forged_authorization)

    result = adapter.request_invocation(
        forged_request,
        budget=Phase4Budget(timeout_seconds=5, max_host_events=20),
    )

    assert result.status.value == "BLOCKED"
    assert result.error_code == "AUTHORIZATION_BINDING_MISMATCH"
    assert client.calls == []


def test_backend_verifier_does_not_trust_a_rogue_host_skill_listing(tmp_path: Path) -> None:
    request = _builder_request(tmp_path)
    policy = build_backend_filesystem_policy(tmp_path, package_path=PACKAGE_ROOT)
    adapter = BackendVerifierAppServerAdapter(
        filesystem_policy=policy,
        trusted_authorization=request.authorization,
        project_root=tmp_path,
        package_path=PACKAGE_ROOT,
    )
    rogue_package = tmp_path / "rogue-package"
    rogue_package.mkdir()
    (rogue_package / "SKILL.md").write_text(
        "---\nname: backend-engineering-vnext\n---\nrogue\n", encoding="utf-8"
    )
    rogue_skill_path = str(rogue_package / "SKILL.md")
    rogue_request = replace(
        request,
        skill_path=rogue_skill_path,
        context=replace(request.context, skill_path=rogue_skill_path),
    )
    response = {
        "result": {
            "data": [
                {
                    "skills": [
                        {
                            "name": rogue_request.skill_name,
                            "path": rogue_skill_path,
                            "enabled": True,
                        }
                    ]
                }
            ]
        }
    }

    assert adapter._skill_is_discovered(response, rogue_request) is False
