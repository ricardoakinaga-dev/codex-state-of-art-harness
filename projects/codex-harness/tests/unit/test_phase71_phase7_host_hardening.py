from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from test_phase7_host import PACKAGE_ROOT, _builder_request, _BuilderFakeAppServerClient

import harness_kernel.phase7_host as host
from harness_kernel.phase4_models import ExecutionMode, Phase4Budget
from harness_kernel.phase7_host import (
    HOST_READ_FILE_TOOL,
    BackendBuilderAppServerAdapter,
    BackendVerifierAppServerAdapter,
    BoundedBuilderHostTools,
    HostProtocolError,
    VerificationLoopVNextAppServerAdapter,
    WorkspaceWriteMode,
    _ScopedWorkspaceClient,
    build_backend_filesystem_policy,
)


def _write_policy(tmp_path: Path):
    app = tmp_path / "app"
    migrations = tmp_path / "migrations"
    app.mkdir(parents=True)
    migrations.mkdir()
    return build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(app, migrations),
        package_path=PACKAGE_ROOT,
    )


class _RecordingDelegate:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def call(self, method: str, params: dict[str, object], *, timeout_seconds: float):
        del timeout_seconds
        self.calls.append((method, params))
        return {"method": method}

    def notify(self, method: str, params: dict[str, object]) -> None:
        self.calls.append((method, params))

    def respond(self, request_id: object, result: dict[str, object]) -> None:
        self.calls.append((request_id, result))

    def stream(self, *, timeout_seconds: float, cancel_event=None):
        del timeout_seconds, cancel_event
        yield {"event": "ok"}

    def close(self) -> None:
        self.calls.append(("close", {}))


def test_builder_constructor_rejects_conflicting_and_invalid_bindings(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path)
    with pytest.raises(ValueError, match="disagree"):
        BackendBuilderAppServerAdapter(filesystem_policy=policy, policy=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="trusted_authorization"):
        BackendBuilderAppServerAdapter(trusted_authorization=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="clock"):
        BackendBuilderAppServerAdapter(clock=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="instruction_kernel"):
        BackendBuilderAppServerAdapter(instruction_kernel="")
    with pytest.raises(ValueError, match="instruction_kernel"):
        BackendBuilderAppServerAdapter(instruction_kernel="x" * (64 * 1024 + 1))
    with pytest.raises(ValueError, match="attempt limits"):
        BackendBuilderAppServerAdapter(max_builder_invocations=3)
    with pytest.raises(ValueError, match="attempt limits"):
        BackendBuilderAppServerAdapter(max_repairs=-1)


def test_builder_attempt_ledger_enforces_repair_and_tracking_limits(tmp_path: Path) -> None:
    request = _builder_request(tmp_path)
    adapter = BackendBuilderAppServerAdapter(max_builder_invocations=2, max_repairs=0)
    repair = replace(
        request,
        authorization=replace(
            request.authorization,
            iteration_budget={"repair_iterations": 1},
        ),
    )
    assert adapter._reserve_attempt(repair) == "BUILDER_REPAIR_BUDGET_EXHAUSTED"
    assert adapter._reserve_attempt(request) is None
    assert adapter._reserve_attempt(request) is None
    assert adapter._reserve_attempt(request) == "BUILDER_ATTEMPT_BUDGET_EXHAUSTED"

    adapter._attempts_by_run = {
        (f"task-{index}", f"run-{index}"): (0, 0) for index in range(host._MAX_TRACKED_BUILDER_RUNS)
    }
    new_authorization = replace(
        request.authorization,
        task_id="task-new",
        run_id="run-new",
    )
    exhausted = replace(
        request,
        authorization=new_authorization,
        context=replace(request.context, task_id="task-new"),
    )
    assert adapter._reserve_attempt(exhausted) == "BUILDER_ATTEMPT_TRACKING_EXHAUSTED"


def test_fixed_pytest_timeout_is_bounded_and_terminates_the_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_root = tmp_path / "tests"
    test_root.mkdir()

    class TimeoutProcess:
        pid = 11
        stdout = object()
        returncode: int | None = None

        def terminate(self) -> None:
            self.returncode = -15

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            if self.returncode is None:
                self.returncode = -15
            return self.returncode

        def kill(self) -> None:
            self.returncode = -9

    class EmptySelector:
        def __init__(self) -> None:
            self.closed = False

        def register(self, *_args) -> None:
            return None

        def get_map(self):
            return {} if self.closed else {1: object()}

        def select(self, _timeout: float):
            return []

        def close(self) -> None:
            self.closed = True

    process = TimeoutProcess()
    monkeypatch.setattr(host, "_fixed_test_command", lambda _root: ["fake"])
    monkeypatch.setattr(host.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(host.selectors, "DefaultSelector", EmptySelector)
    clock_values = iter((0.0, 61.0))
    monkeypatch.setattr(host.time, "monotonic", lambda: next(clock_values))

    observation = host.run_fixed_pytest(test_root)

    assert observation.exit_code == 124
    assert "timed out" in observation.output


def test_builder_write_retries_bounded_temporary_name_collisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = tmp_path / "app"
    app.mkdir()
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(app,),
    )
    (app / ".harness-write-fixed.tmp").write_text("collision", encoding="utf-8")

    class FixedUuid:
        hex = "fixed"

    monkeypatch.setattr(host, "uuid4", lambda: FixedUuid())
    result = BoundedBuilderHostTools(policy)._write(
        {"path": "app/new.py", "content": "never written"}
    )

    assert result.success is False
    assert result.payload["error"] == "TEMPORARY_FILE_UNAVAILABLE"
    assert not (app / "new.py").exists()


def test_builder_package_discovery_and_policy_validation_fail_closed(tmp_path: Path) -> None:
    request = _builder_request(tmp_path)
    policy = _write_policy(tmp_path)
    adapter = BackendBuilderAppServerAdapter(
        filesystem_policy=policy,
        trusted_authorization=request.authorization,
        project_root=tmp_path,
    )

    other = replace(
        request,
        skill_name="other",
        authorization=replace(request.authorization, capability_id="other"),
        context=replace(request.context, capability_id="other"),
    )
    assert adapter._skill_is_discovered({}, other) is False
    wrong_path = str(PACKAGE_ROOT / "README.md")
    wrong_path_request = replace(
        request,
        skill_path=wrong_path,
        context=replace(request.context, skill_path=wrong_path),
    )
    assert adapter._skill_is_discovered({}, wrong_path_request) is False
    assert adapter._skill_is_discovered({}, request) is True

    invalid_mode = replace(
        request,
        authorization=replace(
            request.authorization,
            requested_execution_mode=ExecutionMode.DRY_RUN,
        ),
    )
    errors = adapter._validate_filesystem_policy(invalid_mode)
    assert "BUILDER_REQUIRES_CONTROLLED_REAL" in errors

    invalid_policy = replace(
        request,
        authorization=replace(
            request.authorization,
            filesystem_policy={
                **request.authorization.filesystem_policy,
                "package_write_allowed": True,
            },
        ),
    )
    assert "PACKAGE_WRITE_FORBIDDEN" in adapter.validate_invocation(invalid_policy)

    package = tmp_path / "package"
    package.mkdir()
    inside_package = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(package,),
        package_path=package,
    )
    inside_adapter = BackendBuilderAppServerAdapter(filesystem_policy=inside_package)
    inside_request = replace(
        request,
        workspace=str(tmp_path),
        authorization=replace(
            request.authorization,
            filesystem_policy=inside_package.as_mapping(),
        ),
    )
    assert "PACKAGE_MUST_BE_OUTSIDE_WRITE_WORKSPACE" in inside_adapter._validate_filesystem_policy(
        inside_request
    )


def test_builder_parameter_branches_return_bounded_fallbacks(tmp_path: Path, monkeypatch) -> None:
    request = _builder_request(tmp_path)
    adapter = BackendBuilderAppServerAdapter(instruction_kernel="kernel")
    assert "dynamicTools" not in adapter._thread_params(request)
    assert adapter._with_instruction_kernel({"input": "not-a-list"}) == {"input": "not-a-list"}
    assert "runtimeWorkspaceRoots" in adapter._turn_params(request, "thread")
    plain = BackendBuilderAppServerAdapter()
    assert plain._with_instruction_kernel({"input": []}) == {"input": []}

    monkeypatch.setattr(
        adapter, "_host_tools_for_policy", lambda _policy: (_ for _ in ()).throw(ValueError("bad"))
    )
    policy = _write_policy(tmp_path)
    token = adapter._policy_context.set(policy)
    try:
        assert "dynamicTools" not in adapter._thread_params(request)
    finally:
        adapter._policy_context.reset(token)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ({"params": {"tool": "", "callId": "id", "arguments": {}, "namespace": None}}, None),
        ({"params": {"tool": "x", "callId": "", "arguments": {}, "namespace": None}}, None),
        ({"params": {"tool": "x", "callId": "id", "arguments": [], "namespace": None}}, None),
        ({"params": {"tool": "x", "callId": "id", "arguments": {}, "namespace": "mcp"}}, None),
        ({"params": {"tool": "x" * 257, "callId": "id", "arguments": {}, "namespace": None}}, None),
        ({"params": {"tool": "x", "callId": "id" * 257, "arguments": {}, "namespace": None}}, None),
        (
            {
                "params": {
                    "tool": "x",
                    "callId": "id",
                    "arguments": {"path": "a"},
                    "namespace": None,
                }
            },
            ("x", "id", {"path": "a"}),
        ),
    ],
)
def test_dynamic_tool_field_validation_is_strict(message, expected) -> None:
    assert BackendBuilderAppServerAdapter._dynamic_tool_fields(message) == expected


def test_dynamic_completion_and_message_matching_cover_missing_contexts(tmp_path: Path) -> None:
    adapter = BackendBuilderAppServerAdapter()
    completion = {
        "method": "item/completed",
        "params": {"item": {"type": "dynamicToolCall", "id": "x"}},
    }
    assert adapter._is_dynamic_tool_completion(completion) is False
    calls_token = adapter._dynamic_call_ids_context.set(set())
    items_token = adapter._dynamic_item_ids_context.set(set())
    try:
        assert adapter._is_dynamic_tool_completion({"method": "other", "params": {}}) is False
        assert (
            adapter._is_dynamic_tool_completion(
                {"method": "item/completed", "params": {"item": {"type": "other"}}}
            )
            is False
        )
        assert adapter._is_dynamic_tool_completion(completion) is False
        assert (
            adapter._is_dynamic_tool_completion(
                {
                    "method": "item/started",
                    "params": {"item": {"type": "dynamicToolCall", "id": "new"}},
                }
            )
            is True
        )
        assert adapter._is_dynamic_tool_completion(completion) is False
    finally:
        adapter._dynamic_item_ids_context.reset(items_token)
        adapter._dynamic_call_ids_context.reset(calls_token)

    message = {
        "method": "item/tool/call",
        "id": "request",
        "params": {"threadId": "t", "turnId": "u"},
    }
    assert adapter._message_matches_invocation(message, "t", "u") is True
    assert adapter._message_matches_invocation(message, "other", "u") is False
    assert (
        adapter._message_matches_invocation({"method": "item/file_change", "params": {}}, "t", "u")
        is False
    )


def test_dynamic_host_request_rejects_invalid_ids_budgets_and_contexts(tmp_path: Path) -> None:
    adapter = BackendBuilderAppServerAdapter()
    delegate = _RecordingDelegate()
    message = {
        "id": True,
        "method": "item/tool/call",
        "params": {
            "tool": HOST_READ_FILE_TOOL,
            "callId": "call",
            "arguments": {},
            "namespace": None,
        },
    }
    handled, error = adapter._handle_host_request(
        message, delegate, [], Phase4Budget(timeout_seconds=1, max_host_events=4)
    )
    assert (handled, error) == (True, "DYNAMIC_TOOL_REQUEST_ID_INVALID")

    budget_message = {**message, "id": "budget"}
    handled, error = adapter._handle_host_request(
        budget_message, delegate, [object()] * 4, Phase4Budget(timeout_seconds=1, max_host_events=4)
    )
    assert (handled, error) == (True, "HOST_EVENT_BUDGET_EXCEEDED")

    invalid_message = {
        "id": "invalid",
        "method": "item/tool/call",
        "params": {"tool": HOST_READ_FILE_TOOL},
    }
    events: list[object] = []
    handled, error = adapter._handle_host_request(
        invalid_message, delegate, events, Phase4Budget(timeout_seconds=1, max_host_events=4)
    )  # type: ignore[arg-type]
    assert (handled, error) == (True, "DYNAMIC_TOOL_REQUEST_INVALID")
    assert delegate.calls

    context_message = {
        "id": "context",
        "method": "item/tool/call",
        "params": {
            "tool": HOST_READ_FILE_TOOL,
            "callId": "new",
            "arguments": {},
            "namespace": None,
        },
    }
    calls_token = adapter._dynamic_call_ids_context.set(None)
    try:
        handled, error = adapter._handle_host_request(
            context_message, delegate, [], Phase4Budget(timeout_seconds=1, max_host_events=4)
        )
    finally:
        adapter._dynamic_call_ids_context.reset(calls_token)
    assert (handled, error) == (True, "HOST_TOOL_CONTEXT_MISSING")


def test_dynamic_host_request_duplicate_and_failed_tool_release_reservation(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    policy = build_backend_filesystem_policy(
        tmp_path,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(app,),
    )
    adapter = BackendBuilderAppServerAdapter()
    delegate = _RecordingDelegate()
    host_tools = BoundedBuilderHostTools(policy)
    message = {
        "id": "request",
        "method": "item/tool/call",
        "params": {
            "tool": HOST_READ_FILE_TOOL,
            "callId": "same",
            "arguments": {"path": "app/missing.py"},
            "namespace": None,
        },
    }
    tokens = [
        adapter._event_paths_context.set(set()),
        adapter._host_tools_context.set(host_tools),
        adapter._dynamic_call_ids_context.set(set()),
        adapter._dynamic_item_ids_context.set(set()),
    ]
    try:
        assert adapter._handle_host_request(
            message, delegate, [], Phase4Budget(timeout_seconds=1, max_host_events=4)
        ) == (True, "PATH_NOT_ALLOWED")
        assert adapter._handle_host_request(
            message, delegate, [], Phase4Budget(timeout_seconds=1, max_host_events=4)
        ) == (True, "DUPLICATE_DYNAMIC_TOOL_CALL")
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


def test_verifier_and_composition_constructor_guards_and_skill_fallbacks(tmp_path: Path) -> None:
    request = _builder_request(tmp_path)
    policy = build_backend_filesystem_policy(tmp_path, package_path=PACKAGE_ROOT)
    with pytest.raises(ValueError, match="disagree"):
        BackendVerifierAppServerAdapter(filesystem_policy=policy, policy=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="trusted_authorization"):
        BackendVerifierAppServerAdapter(trusted_authorization=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="clock"):
        BackendVerifierAppServerAdapter(clock=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="read-only"):
        BackendVerifierAppServerAdapter(
            filesystem_policy=_write_policy(tmp_path),
        )._policy_for_request(request)

    verifier = BackendVerifierAppServerAdapter(
        filesystem_policy=policy,
        trusted_authorization=request.authorization,
        project_root=tmp_path,
        package_path=PACKAGE_ROOT,
    )
    other = replace(
        request,
        skill_name="other",
        authorization=replace(request.authorization, capability_id="other"),
        context=replace(request.context, capability_id="other"),
    )
    assert verifier._skill_is_discovered({}, other) is False
    wrong_path = str(PACKAGE_ROOT / "README.md")
    wrong_path_request = replace(
        request,
        skill_path=wrong_path,
        context=replace(request.context, skill_path=wrong_path),
    )
    assert verifier._skill_is_discovered({}, wrong_path_request) is False
    missing_path = str(tmp_path / "missing" / "SKILL.md")
    missing_path_request = replace(
        request,
        skill_path=missing_path,
        context=replace(request.context, skill_path=missing_path),
    )
    assert verifier._skill_is_discovered({}, missing_path_request) is False
    verifier_policy = build_backend_filesystem_policy(tmp_path, package_path=PACKAGE_ROOT)
    verifier_authorization = replace(
        request.authorization,
        filesystem_policy=verifier_policy.as_mapping(),
    )
    verifier_request = replace(request, authorization=verifier_authorization)
    verifier = BackendVerifierAppServerAdapter(
        filesystem_policy=verifier_policy,
        trusted_authorization=verifier_authorization,
        project_root=tmp_path,
        package_path=PACKAGE_ROOT,
    )
    assert verifier._validate_filesystem_policy(verifier_request) == ()

    with pytest.raises(ValueError, match="instruction_kernel"):
        VerificationLoopVNextAppServerAdapter(instruction_kernel="")
    with pytest.raises(ValueError, match="clock"):
        VerificationLoopVNextAppServerAdapter(clock=object())  # type: ignore[arg-type]


def test_scoped_client_delegates_attributes_and_preserves_non_special_calls(tmp_path: Path) -> None:
    delegate = _RecordingDelegate()
    client = _ScopedWorkspaceClient(delegate, (tmp_path,), None)
    client.call("other", {"value": 1}, timeout_seconds=1)
    assert delegate.calls[0] == ("other", {"value": 1})
    assert client.__getattr__("calls") == delegate.calls


def test_write_event_and_completion_events_reject_scope_without_context(tmp_path: Path) -> None:
    policy = _write_policy(tmp_path)
    adapter = BackendBuilderAppServerAdapter()
    assert adapter._reserve_write_event_path(
        BoundedBuilderHostTools(policy), {"path": "app/a.py", "content": "x"}
    ) == (
        None,
        False,
        "HOST_TOOL_WRITE_OBSERVATION_MISSING",
    )
    assert adapter._is_forbidden_host_action({"method": "item/file_change", "params": {}}) is True
    with pytest.raises(HostProtocolError):
        host.validate_file_change_event(
            {"method": "item/file_change", "params": {"item": {}}},
            policy,
        )


class _ReadOnlyVerifierClient(_BuilderFakeAppServerClient):
    def call(self, method: str, params: dict[str, object], *, timeout_seconds: float):
        if method == "turn/start":
            self.calls.append((method, params))
            return {"result": {"turn": {"id": "turn-builder"}}}
        return super().call(method, params, timeout_seconds=timeout_seconds)

    def stream(self, *, timeout_seconds: float, cancel_event=None):
        del timeout_seconds, cancel_event
        yield {
            "method": "item/completed",
            "params": {
                "threadId": "thread-builder",
                "turnId": "turn-builder",
                "item": {"type": "agentMessage", "text": "READ_ONLY_DONE"},
            },
        }
        yield {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-builder",
                "turn": {"id": "turn-builder", "status": "completed"},
            },
        }


class _MutatingVerifierClient(_ReadOnlyVerifierClient):
    def call(self, method: str, params: dict[str, object], *, timeout_seconds: float):
        if method == "turn/start":
            (self.workspace / "app" / "unexpected.py").write_text("mutation\n", encoding="utf-8")
        return super().call(method, params, timeout_seconds=timeout_seconds)


def _verifier_request(tmp_path: Path):
    request = _builder_request(tmp_path)
    policy = build_backend_filesystem_policy(tmp_path, package_path=PACKAGE_ROOT)
    authorization = replace(
        request.authorization,
        filesystem_policy=policy.as_mapping(),
    )
    return replace(request, authorization=authorization), policy


def test_verifier_invocation_records_read_only_success_and_detects_mutation(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "migrations").mkdir()
    request, policy = _verifier_request(tmp_path)
    client = _ReadOnlyVerifierClient(tmp_path)
    adapter = BackendVerifierAppServerAdapter(
        transport_factory=lambda: client,
        filesystem_policy=policy,
        trusted_authorization=request.authorization,
        project_root=tmp_path,
        package_path=PACKAGE_ROOT,
    )

    success = adapter.request_invocation(
        request,
        budget=Phase4Budget(timeout_seconds=5, max_host_events=20),
    )
    assert success.status.value == "SUCCESS"
    assert success.execution_observed is True
    assert adapter.last_workspace_delta is not None
    assert adapter.last_workspace_delta.ok is True

    mutating_client = _MutatingVerifierClient(tmp_path)
    mutating_adapter = BackendVerifierAppServerAdapter(
        transport_factory=lambda: mutating_client,
        filesystem_policy=policy,
        trusted_authorization=request.authorization,
        project_root=tmp_path,
        package_path=PACKAGE_ROOT,
    )
    mutation = mutating_adapter.request_invocation(
        request,
        budget=Phase4Budget(timeout_seconds=5, max_host_events=20),
    )
    assert mutation.status.value == "FAILURE"
    assert mutation.error_code == "VERIFIER_MUTATION_OBSERVED"
    assert mutation.execution_observed is False
