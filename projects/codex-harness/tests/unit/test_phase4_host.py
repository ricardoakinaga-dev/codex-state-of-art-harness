from __future__ import annotations

import hashlib
import sys
from dataclasses import replace
from pathlib import Path

from harness_kernel.phase4_host import (
    CodexAppServerAdapter,
    HostProtocolError,
    HostTimeoutError,
    _resolve_host_binding,
    _SubprocessClient,
    _verify_pinned_files,
)
from harness_kernel.phase4_models import (
    CapabilityExecutionAuthorization,
    CapabilityInvocationRequest,
    ContextManifest,
    ExecutionMode,
    HostLoadObservation,
    Phase4Budget,
    ProtocolMessageObservation,
    digest_payload,
)


class FakeAppServerClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.notifications: list[dict[str, object]] = []
        self.responses: list[tuple[object, dict[str, object]]] = []

    def call(
        self, method: str, params: dict[str, object], *, timeout_seconds: int
    ) -> dict[str, object]:
        self.calls.append((method, params))
        if method == "initialize":
            return {"result": {"userAgent": "codex-cli 0.150.1", "platformOs": "linux"}}
        if method == "skills/list":
            return {
                "result": {
                    "data": [
                        {
                            "cwd": params["cwds"][0],
                            "errors": [],
                            "skills": [
                                {"name": "safe-pilot", "path": "/fixture/SKILL.md", "enabled": True}
                            ],
                        }
                    ]
                }
            }
        if method == "thread/start":
            return {"result": {"thread": {"id": "thread-1", "sessionId": "session-1"}}}
        if method == "turn/start":
            return {"result": {"turn": {"id": "turn-1"}}}
        if method == "turn/interrupt":
            return {"result": {}}
        raise AssertionError(method)

    def notify(self, method: str, params: dict[str, object]) -> None:
        self.notifications.append({"method": method, "params": params})

    def respond(self, request_id: object, result: dict[str, object]) -> None:
        self.responses.append((request_id, result))

    def stream(self, *, timeout_seconds: int, cancel_event=None):
        yield {
            "method": "item/completed",
            "params": {
                "item": {"type": "userMessage", "content": [{"type": "text"}, {"type": "skill"}]}
            },
        }
        yield {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "agentMessage",
                    "text": "PHASE4_SAFE_PILOT_ARTIFACT",
                    "phase": "final_answer",
                }
            },
        }
        yield {
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"}},
        }

    def close(self) -> None:
        pass


def _request(tmp_path: Path) -> CapabilityInvocationRequest:
    authorization = CapabilityExecutionAuthorization(
        authorization_id="AUTH-P4-1",
        task_id="TASK-P4-1",
        run_id="RUN-P4-1",
        capability_id="safe-pilot",
        capability_version="0.1.0",
        package_fingerprint="sha256:" + "1" * 64,
        scope="PROJECT",
        requested_loading_level="L2_INSTRUCTION_KERNEL",
        requested_execution_mode=ExecutionMode.CONTROLLED_REAL,
        allowed_tools=(),
        allowed_side_effects=(),
        filesystem_policy={"workspace": str(tmp_path), "mode": "READ_ONLY"},
        network_policy="DENY",
        shell_policy="DENY",
        provider_policy="DENY",
        mcp_policy="DENY",
        credential_policy="DENY",
        timeout_seconds=20,
        iteration_budget={"host_calls": 1, "verification": 1},
        context_budget={"max_bytes": 8_000},
        artifact_policy={"types": ["HOST_RESPONSE"]},
        evidence_policy={"max_events": 40},
        issued_by="test",
        issued_at=1_700_000_000,
        expires_at=1_700_000_020,
        reason="bounded test",
        constraints=("no tools",),
    )
    context = ContextManifest(
        task_id="TASK-P4-1",
        task_digest=digest_payload("Return one bounded response."),
        capability_id="safe-pilot",
        package_fingerprint=authorization.package_fingerprint,
        skill_path="/fixture/SKILL.md",
        sources=("HOST_MANAGED_SKILL",),
        selected_references=(),
        omitted_references=(),
        estimated_bytes=100,
        digest="sha256:" + "2" * 64,
        acceptance_criteria=("response is non-empty",),
    )
    return CapabilityInvocationRequest(
        invocation_id="INV-P4-1",
        authorization=authorization,
        context=context,
        skill_name="safe-pilot",
        skill_path="/fixture/SKILL.md",
        task="Return one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=str(tmp_path),
        expected_artifacts=("HOST_RESPONSE",),
        idempotency_key="idem-p4-1",
    )


def test_codex_app_server_adapter_sends_typed_skill_input_and_observes_turn(
    tmp_path: Path,
) -> None:
    client = FakeAppServerClient()
    adapter = CodexAppServerAdapter(transport_factory=lambda: client)

    result = adapter.request_invocation(_request(tmp_path), budget=Phase4Budget())

    methods = [method for method, _ in client.calls]
    assert methods == ["initialize", "skills/list", "thread/start", "turn/start"]
    turn_params = next(params for method, params in client.calls if method == "turn/start")
    assert {item["type"] for item in turn_params["input"]} == {"text", "skill"}
    assert result.invocation_observed is True
    assert result.final_message == "PHASE4_SAFE_PILOT_ARTIFACT"
    assert result.load_observation is HostLoadObservation.UNOBSERVABLE
    assert result.protocol_message_count == len(result.events)
    assert result.mcp_event_count == 0
    assert result.approval_request_count == 0
    assert result.events[-1].thread_id == "thread-1"
    assert result.events[-1].turn_id == "turn-1"


def test_codex_app_server_adapter_fails_closed_on_forbidden_tool_event(tmp_path: Path) -> None:
    client = FakeAppServerClient()

    def stream_with_tool(*, timeout_seconds: int, cancel_event=None):
        yield {
            "method": "item/commandExecution/completed",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "item": {"id": "item-1", "type": "commandExecution", "status": "completed"},
            },
        }

    client.stream = stream_with_tool  # type: ignore[method-assign]
    result = CodexAppServerAdapter(transport_factory=lambda: client).request_invocation(
        _request(tmp_path), budget=Phase4Budget()
    )

    assert result.status.value == "FAILURE"
    assert result.error_code == "HOST_TOOL_BUDGET_EXCEEDED"
    assert result.execution_observed is False


def test_codex_app_server_adapter_denies_approval_requests(tmp_path: Path) -> None:
    client = FakeAppServerClient()
    original_stream = client.stream

    def stream_with_approval(*, timeout_seconds: int, cancel_event=None):
        yield {
            "id": "approval-1",
            "method": "item/commandExecution/requestApproval",
            "params": {"itemId": "item-1", "command": "echo unsafe"},
        }
        yield from original_stream(timeout_seconds=timeout_seconds, cancel_event=cancel_event)

    client.stream = stream_with_approval  # type: ignore[method-assign]
    adapter = CodexAppServerAdapter(transport_factory=lambda: client)

    result = adapter.request_invocation(_request(tmp_path), budget=Phase4Budget())

    assert client.responses == [("approval-1", {"decision": "decline"})]
    assert result.denied_approvals == 1
    assert result.approval_request_count == 1
    assert result.status.value == "PARTIAL"


def test_protocol_counters_cover_messages_consumed_before_event_stream(tmp_path: Path) -> None:
    client = FakeAppServerClient()
    client.protocol_counts = lambda: (11, 0, 1)  # type: ignore[attr-defined]

    result = CodexAppServerAdapter(transport_factory=lambda: client).request_invocation(
        _request(tmp_path), budget=Phase4Budget()
    )

    assert result.protocol_message_count == 11
    assert result.approval_request_count == 1
    assert result.denied_approvals == 1
    assert result.status.value == "PARTIAL"


def test_protocol_mcp_counter_fails_closed_even_when_event_was_not_streamed(
    tmp_path: Path,
) -> None:
    client = FakeAppServerClient()
    client.protocol_counts = lambda: (11, 1, 0)  # type: ignore[attr-defined]

    result = CodexAppServerAdapter(transport_factory=lambda: client).request_invocation(
        _request(tmp_path), budget=Phase4Budget()
    )

    assert result.status.value == "FAILURE"
    assert result.error_code == "MCP_EVENT_OBSERVED"
    assert result.mcp_event_count == 1


def test_protocol_transcript_is_retained_when_client_provides_it(tmp_path: Path) -> None:
    client = FakeAppServerClient()
    client.protocol_counts = lambda: (3, 0, 0)  # type: ignore[attr-defined]
    client.protocol_observations = lambda: tuple(  # type: ignore[attr-defined]
        ProtocolMessageObservation(
            sequence=index,
            method=method,
            message_kind="notification",
            has_id=False,
            has_error=False,
        )
        for index, method in enumerate(("item/completed", "item/completed", "turn/completed"))
    )

    result = CodexAppServerAdapter(transport_factory=lambda: client).request_invocation(
        _request(tmp_path), budget=Phase4Budget()
    )

    assert result.status.value == "SUCCESS"
    assert len(result.protocol_messages) == 3
    assert result.protocol_messages[-1].method == "turn/completed"


def test_codex_app_server_adapter_rejects_cross_turn_events(tmp_path: Path) -> None:
    client = FakeAppServerClient()

    def divergent_stream(*, timeout_seconds: int, cancel_event=None):
        yield {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-1",
                "turn": {"id": "another-turn", "status": "completed"},
            },
        }

    client.stream = divergent_stream  # type: ignore[method-assign]
    result = CodexAppServerAdapter(transport_factory=lambda: client).request_invocation(
        _request(tmp_path), budget=Phase4Budget()
    )

    assert result.status.value == "FAILURE"
    assert result.error_code == "HOST_EVENT_CORRELATION_MISMATCH"
    assert result.execution_observed is False
    assert result.events[-1].event_class == "CORRELATION_REJECTED"


def test_codex_app_server_adapter_timeout_is_terminal_without_extra_interrupt_budget(
    tmp_path: Path,
) -> None:
    client = FakeAppServerClient()

    def timed_out_stream(*, timeout_seconds: int, cancel_event=None):
        raise HostTimeoutError("deadline")
        yield  # pragma: no cover

    client.stream = timed_out_stream  # type: ignore[method-assign]
    result = CodexAppServerAdapter(transport_factory=lambda: client).request_invocation(
        _request(tmp_path), budget=Phase4Budget()
    )

    assert result.status.value == "TIMED_OUT"
    assert result.cancellation_status == "CANCELLATION_NOT_ATTEMPTED_DEADLINE_EXPIRED"
    assert [method for method, _ in client.calls] == [
        "initialize",
        "skills/list",
        "thread/start",
        "turn/start",
    ]


def test_public_cancel_requests_interrupt_for_active_session(tmp_path: Path) -> None:
    client = FakeAppServerClient()
    adapter = CodexAppServerAdapter(transport_factory=lambda: client)
    request = _request(tmp_path)
    adapter._active_sessions[request.invocation_id] = (client, "thread-1", "turn-1")

    status = adapter.cancel_invocation(request)

    assert status == "HOST_INTERRUPT_REQUESTED"
    assert client.notifications[-1] == {
        "method": "turn/interrupt",
        "params": {"threadId": "thread-1", "turnId": "turn-1"},
    }


def test_host_binding_uses_absolute_interpreter_and_script_pins(
    tmp_path: Path, monkeypatch
) -> None:
    codex = tmp_path / "codex.js"
    node = tmp_path / "node"
    codex.write_text("#!/usr/bin/env node\nconsole.log('codex')\n", encoding="utf-8")
    node.write_text("#!/bin/sh\n", encoding="utf-8")
    codex.chmod(0o755)
    node.chmod(0o755)

    def which(program: str) -> str:
        return str(codex if program == "codex" else node)

    monkeypatch.setattr("harness_kernel.phase4_host.shutil.which", which)

    (
        command,
        executable_path,
        executable_digest,
        pinned_files,
        interpreter_path,
        interpreter_digest,
    ) = _resolve_host_binding()

    assert command[:2] == (str(node), str(codex))
    assert executable_path == str(codex)
    assert executable_digest == "sha256:" + hashlib.sha256(codex.read_bytes()).hexdigest()
    assert interpreter_path == str(node)
    assert interpreter_digest == "sha256:" + hashlib.sha256(node.read_bytes()).hexdigest()
    assert pinned_files == (
        (str(codex), executable_digest),
        (str(node), "sha256:" + hashlib.sha256(node.read_bytes()).hexdigest()),
    )


def test_host_binding_rejects_a_changed_pinned_file(tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    expected = "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest()
    executable.write_text("#!/bin/sh\necho changed\n", encoding="utf-8")

    try:
        _verify_pinned_files(((str(executable), expected),))
    except HostProtocolError as error:
        assert "fingerprint" in str(error)
    else:
        raise AssertionError("changed host executable was accepted")


def test_controlled_real_validation_requires_the_bound_host_digest(tmp_path: Path) -> None:
    request = _request(tmp_path)
    adapter = CodexAppServerAdapter()

    assert "HOST_EXECUTABLE_NOT_BOUND" in adapter.validate_invocation(request)

    _, _, digest, _, _interpreter_path, interpreter_digest = _resolve_host_binding()
    filesystem_policy = {
        **request.authorization.filesystem_policy,
        "host_executable_digest": digest,
        "host_interpreter_digest": interpreter_digest,
    }
    authorization = replace(
        request.authorization,
        filesystem_policy=filesystem_policy,
        host_executable_digest=digest,
        host_interpreter_digest=interpreter_digest,
    )
    bound_request = replace(request, authorization=authorization)

    assert adapter.validate_invocation(bound_request) == ()


def test_subprocess_client_bounds_and_summarizes_jsonl_protocol(tmp_path: Path) -> None:
    server = tmp_path / "server.py"
    server.write_text(
        """import json
import sys
for raw in sys.stdin:
    message = json.loads(raw)
    method = message.get("method")
    if method == "initialize":
        print(
            json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {}}),
            flush=True,
        )
    elif method == "turn/start":
        print(
            json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"ok": True}}),
            flush=True,
        )
        print(
            json.dumps({"jsonrpc": "2.0", "method": "turn/progress", "params": {}}),
            flush=True,
        )
""",
        encoding="utf-8",
    )
    server.chmod(0o755)
    python_path = Path(sys.executable).resolve()
    python_digest = "sha256:" + hashlib.sha256(python_path.read_bytes()).hexdigest()
    server_digest = "sha256:" + hashlib.sha256(server.read_bytes()).hexdigest()
    client = _SubprocessClient(
        cwd=tmp_path,
        command=(str(python_path), str(server)),
        pinned_files=((str(python_path), python_digest), (str(server), server_digest)),
        host_executable_path=str(server),
        host_executable_digest=server_digest,
    )

    try:
        assert client.call("initialize", {}, timeout_seconds=1)["result"] == {}
        client.notify("initialized", {})
        assert client.call("turn/start", {}, timeout_seconds=1)["result"] == {"ok": True}
        assert next(client.stream(timeout_seconds=1))["method"] == "turn/progress"
        assert client.protocol_counts() == (3, 0, 0)
        observations = client.protocol_observations()
        assert [item.message_kind for item in observations] == [
            "response",
            "response",
            "notification",
        ]
        assert observations[-1].method == "turn/progress"
    finally:
        client.close()
