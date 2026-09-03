"""P8.1-FINDING-H-HOST-COMPOSITION-001 host-boundary contracts."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness_kernel import phase81_host
from harness_kernel.phase3_resolution import ResolutionEngine
from harness_kernel.phase4_execution import InvocationEngine
from harness_kernel.phase4_models import (
    CapabilityExecutionAuthorization,
    ExecutionMode,
    Phase4Budget,
)
from harness_kernel.phase4_policy import ExecutionPolicyRegistry
from harness_kernel.phase6_host import discover_vnext_package
from harness_kernel.phase7_backend import package_fingerprint
from harness_kernel.phase7_host import (
    BackendBuilderAppServerAdapter,
    WorkspaceWriteMode,
    build_backend_filesystem_policy,
)
from harness_kernel.phase81_host import (
    FRONTEND_CAPABILITY_ID,
    VERIFIER_CAPABILITY_ID,
    FrontendBuilderAppServerAdapter,
    Phase81VerifierAppServerAdapter,
)

PROJECT_ROOT = Path(__file__).parents[3]
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / FRONTEND_CAPABILITY_ID
VERIFIER_PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / VERIFIER_CAPABILITY_ID


def _request():
    workspace = PROJECT_ROOT / "evidence" / "phase-8.1" / "fixture" / "frontend"
    snapshot = discover_vnext_package(PROJECT_ROOT, capability_id=FRONTEND_CAPABILITY_ID)
    assert snapshot.record is not None
    policy_payload = json.loads(
        (PROJECT_ROOT / "config" / "phase8.1-execution-policy.json").read_text(encoding="utf-8")
    )
    policy = ExecutionPolicyRegistry.from_mapping(policy_payload)
    resolution = ResolutionEngine().resolve(snapshot.inventory, FRONTEND_CAPABILITY_ID)
    prepared = InvocationEngine(
        FrontendBuilderAppServerAdapter(transport_factory=lambda: object())  # type: ignore[arg-type]
    ).prepare(
        snapshot.record,
        snapshot.inventory,
        resolution,
        policy,
        task_id="PHASE8.1-TEST",
        run_id="P81-COMPOSE-TEST",
        task="Add only a nonvisual composition marker.",
        acceptance_criteria=("only app/index.html changes",),
        workspace=workspace,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert prepared.request is not None
    return prepared.request


def test_frontend_adapter_keeps_typed_skill_and_bounded_write_root() -> None:
    request = _request()
    workspace = Path(request.workspace)
    policy = build_backend_filesystem_policy(
        workspace,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(workspace / "app",),
        package_path=PACKAGE_ROOT,
    )
    adapter = FrontendBuilderAppServerAdapter(
        transport_factory=lambda: object(),  # type: ignore[arg-type]
        filesystem_policy=policy,
        project_root=PROJECT_ROOT,
        trusted_authorization=request.authorization,
    )

    token = adapter._policy_context.set(policy)
    try:
        thread = adapter._thread_params(request)
        turn = adapter._turn_params(request, "thread-p81")
    finally:
        adapter._policy_context.reset(token)

    assert thread["sandbox"] == "workspace-write"
    assert turn["sandboxPolicy"] == {
        "type": "workspaceWrite",
        "networkAccess": False,
        "allowedRoots": [str((workspace / "app").resolve())],
    }
    assert turn["runtimeWorkspaceRoots"] == [str((workspace / "app").resolve())]
    assert {item.get("type") for item in turn["input"]} >= {"text", "skill"}
    skill = next(item for item in turn["input"] if item.get("type") == "skill")
    assert skill == {
        "type": "skill",
        "name": FRONTEND_CAPABILITY_ID,
        "path": str(PACKAGE_ROOT / "SKILL.md"),
    }


def test_frontend_adapter_authenticates_exact_package_outside_write_root() -> None:
    request = _request()
    workspace = Path(request.workspace)
    policy = build_backend_filesystem_policy(
        workspace,
        mode=WorkspaceWriteMode.WORKSPACE_WRITE,
        allowed_roots=(workspace / "app",),
        package_path=PACKAGE_ROOT,
    )
    adapter = FrontendBuilderAppServerAdapter(
        transport_factory=lambda: object(),  # type: ignore[arg-type]
        filesystem_policy=policy,
        project_root=PROJECT_ROOT,
        trusted_authorization=request.authorization,
    )

    assert adapter._skill_is_discovered({}, request) is True
    assert adapter.validate_invocation(request) == ()


def _verifier_adapter_and_request(tmp_path: Path):
    workspace = tmp_path.resolve()
    fingerprint = package_fingerprint(VERIFIER_PACKAGE_ROOT)
    raw_policy = {
        "workspace": str(workspace),
        "mode": "READ_ONLY",
        "allowed_roots": (),
        "package_path": str(VERIFIER_PACKAGE_ROOT),
        "package_write_allowed": False,
        "network": "DENY",
        "shell": "DENY",
        "mcp": "DENY",
        "providers": "DENY",
        "credentials": "DENY",
    }
    authorization = CapabilityExecutionAuthorization(
        authorization_id="AUTH-P81-VERIFIER-TEST",
        task_id="TASK-P81-VERIFIER-TEST",
        run_id="RUN-P81-VERIFIER-TEST",
        capability_id=VERIFIER_CAPABILITY_ID,
        capability_version="0.1.0",
        package_fingerprint=fingerprint,
        scope="PROJECT",
        requested_loading_level="L2_INSTRUCTION_KERNEL",
        requested_execution_mode=ExecutionMode.CONTROLLED_REAL,
        allowed_tools=(),
        allowed_side_effects=(),
        filesystem_policy=raw_policy,
        network_policy="DENY",
        shell_policy="DENY",
        provider_policy="DENY",
        mcp_policy="DENY",
        credential_policy="DENY",
        timeout_seconds=20,
        iteration_budget={"host_calls": 1, "tool_calls": 0},
        context_budget={"max_bytes": 32_000},
        artifact_policy={"types": ("HOST_RESPONSE",)},
        evidence_policy={"max_events": 128},
        issued_by="test",
        issued_at=int(time.time()) - 5,
        expires_at=int(time.time()) + 120,
        reason="bounded read-only verifier adapter test",
        constraints=("read-only",),
    )
    request = SimpleNamespace(
        workspace=str(workspace),
        skill_name=VERIFIER_CAPABILITY_ID,
        skill_path=str(VERIFIER_PACKAGE_ROOT / "SKILL.md"),
        authorization=authorization,
    )
    policy = build_backend_filesystem_policy(
        workspace,
        mode=WorkspaceWriteMode.READ_ONLY,
        allowed_roots=(workspace,),
        package_path=VERIFIER_PACKAGE_ROOT,
    )
    adapter = Phase81VerifierAppServerAdapter(
        transport_factory=lambda: object(),  # type: ignore[arg-type]
        filesystem_policy=policy,
        project_root=PROJECT_ROOT,
        trusted_authorization=authorization,
    )
    return adapter, request


def test_verifier_adapter_authenticates_exact_read_only_package(tmp_path: Path) -> None:
    adapter, request = _verifier_adapter_and_request(tmp_path)

    assert adapter._skill_is_discovered({}, request) is True
    assert adapter._policy_for_request(request).allowed_roots == (tmp_path.resolve(),)
    assert adapter._thread_sandbox(request) == "read-only"
    assert adapter._turn_sandbox_policy(request) == {
        "type": "readOnly",
        "networkAccess": False,
    }


def test_verifier_adapter_rejects_authorization_that_exposes_write_roots(
    tmp_path: Path,
) -> None:
    adapter, request = _verifier_adapter_and_request(tmp_path)
    request.authorization = replace(
        request.authorization,
        filesystem_policy={
            **request.authorization.filesystem_policy,
            "allowed_roots": (str(tmp_path),),
        },
    )

    with pytest.raises(ValueError, match="authorization-bound"):
        adapter._policy_for_request(request)


def test_verifier_adapter_rejects_wrong_skill_identity(tmp_path: Path) -> None:
    adapter, request = _verifier_adapter_and_request(tmp_path)
    request.skill_name = FRONTEND_CAPABILITY_ID

    assert adapter._skill_is_discovered({}, request) is False


def test_verifier_invocation_preserves_a_clean_read_only_delta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, request = _verifier_adapter_and_request(tmp_path)
    monkeypatch.setattr(
        BackendBuilderAppServerAdapter,
        "request_invocation",
        lambda self, request, **kwargs: self._blocked_result("STUB_RESULT"),
    )

    result = adapter.request_invocation(request, budget=Phase4Budget())

    assert result.error_code == "STUB_RESULT"
    assert adapter.last_workspace_delta is not None
    assert adapter.last_workspace_delta.ok is True


def test_verifier_invocation_blocks_when_snapshot_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, request = _verifier_adapter_and_request(tmp_path)
    monkeypatch.setattr(
        phase81_host,
        "snapshot_workspace",
        lambda workspace: (_ for _ in ()).throw(OSError("snapshot unavailable")),
    )

    result = adapter.request_invocation(request, budget=Phase4Budget())

    assert result.error_code == "WORKSPACE_SNAPSHOT_UNAVAILABLE"


@pytest.mark.parametrize(
    ("delta", "expected"),
    (
        (OSError("delta unavailable"), "VERIFIER_WORKSPACE_DELTA_UNAVAILABLE"),
        (SimpleNamespace(ok=False), "VERIFIER_MUTATION_OBSERVED"),
    ),
)
def test_verifier_invocation_fails_when_post_delta_is_not_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    delta: object,
    expected: str,
) -> None:
    adapter, request = _verifier_adapter_and_request(tmp_path)
    monkeypatch.setattr(
        BackendBuilderAppServerAdapter,
        "request_invocation",
        lambda self, request, **kwargs: self._blocked_result("STUB_RESULT"),
    )

    def validate(*args, **kwargs):
        if isinstance(delta, BaseException):
            raise delta
        return delta

    monkeypatch.setattr(phase81_host, "validate_workspace_delta", validate)

    result = adapter.request_invocation(request, budget=Phase4Budget())

    assert result.error_code == expected
    assert result.execution_observed is False
