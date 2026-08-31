from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_phase4_execution import FakeHost
from test_phase4_host import _request
from test_phase71_phase4_hardening import _host_result, _prepare

from harness_kernel.phase4_models import (
    ArtifactRecord,
    ArtifactType,
    AssuranceResult,
    ExecutionMode,
    FactStatus,
    HostPreparation,
    InvocationLifecycle,
    InvocationResultStatus,
    Phase4Event,
    PreflightResult,
    ProtocolMessageObservation,
    public_data,
    stable_digest_payload,
)

VALID_DIGEST = "sha256:" + "a" * 64


def test_path_values_are_serialized_and_stably_digestable(tmp_path: Path) -> None:
    assert public_data(tmp_path / "report.json") == str(tmp_path / "report.json")
    assert stable_digest_payload({"path": tmp_path / "report.json"}, workspace=tmp_path)


def test_authorization_rejects_expired_bounds_and_invalid_mode(tmp_path: Path) -> None:
    authorization = _request(tmp_path).authorization

    with pytest.raises(ValueError, match="sha256 digest"):
        replace(authorization, package_fingerprint="not-a-digest")
    with pytest.raises(ValueError, match="time bounds"):
        replace(authorization, expires_at=authorization.issued_at)
    with pytest.raises(ValueError, match="requested_execution_mode"):
        replace(authorization, requested_execution_mode="CONTROLLED_REAL")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field",
    ("network_policy", "shell_policy", "provider_policy", "mcp_policy", "credential_policy"),
)
def test_authorization_rejects_unsupported_policy_values(tmp_path: Path, field: str) -> None:
    with pytest.raises(ValueError, match=field):
        replace(_request(tmp_path).authorization, **{field: "UNSUPPORTED"})


def test_invocation_request_rejects_non_absolute_paths(tmp_path: Path) -> None:
    request = _request(tmp_path)
    with pytest.raises(ValueError, match="must be absolute"):
        replace(request, workspace="relative")


@pytest.mark.parametrize(
    ("field", "message"),
    (
        ("skill_name", "skill name"),
        ("context_task_id", "context task"),
        ("context_capability_id", "context capability"),
        ("context_package_fingerprint", "context fingerprint"),
        ("skill_path", "context skill path"),
        ("context_task_digest", "context task digest"),
        ("acceptance_criteria", "acceptance criteria"),
    ),
)
def test_invocation_request_rejects_identity_and_context_mismatches(
    tmp_path: Path, field: str, message: str
) -> None:
    request = _request(tmp_path)
    with pytest.raises(ValueError, match=message):
        if field == "skill_name":
            replace(request, skill_name="other-skill")
        elif field == "skill_path":
            replace(request, skill_path="/fixture/other-SKILL.md")
        elif field == "acceptance_criteria":
            replace(request, acceptance_criteria=("different",))
        else:
            context_field = field.removeprefix("context_")
            context = replace(request.context, **{context_field: "sha256:" + "b" * 64})
            if context_field in {"task_id", "capability_id", "skill_path"}:
                context = replace(request.context, **{context_field: "other"})
            replace(request, context=context)


def test_invocation_request_rejects_host_digest_bindings_and_authorized_types(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    with pytest.raises(ValueError, match="host executable digest"):
        replace(
            request,
            authorization=replace(request.authorization, host_executable_digest=VALID_DIGEST),
        )
    with pytest.raises(ValueError, match="host interpreter digest"):
        replace(
            request,
            authorization=replace(request.authorization, host_interpreter_digest=VALID_DIGEST),
        )
    with pytest.raises(ValueError, match="artifact types"):
        replace(request, expected_artifacts=("FILE",))
    filesystem_policy = dict(request.authorization.filesystem_policy)
    filesystem_policy["workspace"] = str(tmp_path / "different-workspace")
    with pytest.raises(ValueError, match="workspace does not match"):
        replace(
            request,
            authorization=replace(
                request.authorization,
                filesystem_policy=filesystem_policy,
            ),
        )


def test_host_result_rejects_inconsistent_provenance_and_protocol_counts() -> None:
    valid = _host_result(InvocationResultStatus.SUCCESS)
    with pytest.raises(ValueError, match="host_executable_digest requires"):
        replace(valid, host_executable_path=None, host_executable_digest=VALID_DIGEST)
    with pytest.raises(ValueError, match="host_interpreter_path must be absolute"):
        replace(valid, host_interpreter_path="relative")
    with pytest.raises(ValueError, match="host_interpreter_digest requires"):
        replace(valid, host_interpreter_path=None, host_interpreter_digest=VALID_DIGEST)
    with pytest.raises(ValueError, match="mcp_event_count"):
        replace(valid, protocol_message_count=0, mcp_event_count=1)
    observation = ProtocolMessageObservation(
        sequence=0,
        method="mcpServer/call",
        message_kind="notification",
        has_id=False,
        has_error=False,
    )
    with pytest.raises(ValueError, match="mcp_event_count does not match"):
        replace(
            valid,
            protocol_message_count=1,
            mcp_event_count=0,
            protocol_messages=(observation,),
        )


def test_host_result_rejects_relative_executable_path() -> None:
    with pytest.raises(ValueError, match="host_executable_path must be absolute"):
        replace(_host_result(InvocationResultStatus.SUCCESS), host_executable_path="relative")


def test_receipt_rejects_relative_interpreter_path(tmp_path: Path) -> None:
    engine, prepared = _prepare(tmp_path, FakeHost())
    receipt = engine.execute_prepared(prepared).receipt
    with pytest.raises(ValueError, match="host_interpreter_path must be absolute"):
        replace(receipt, host_interpreter_path="relative")


def test_preflight_and_prepared_invocation_require_consistent_bindings(tmp_path: Path) -> None:
    request = _request(tmp_path)
    with pytest.raises(ValueError, match="allowed preflight cannot contain blockers"):
        PreflightResult(
            allowed=True,
            mode=request.authorization.requested_execution_mode,
            blockers=("blocked",),
            warnings=(),
            authorization=request.authorization,
            context=request.context,
            digest=VALID_DIGEST,
        )
    with pytest.raises(ValueError, match="requires authorization"):
        PreflightResult(
            allowed=True,
            mode=request.authorization.requested_execution_mode,
            blockers=(),
            warnings=(),
            authorization=None,
            context=None,
            digest=VALID_DIGEST,
        )

    engine, prepared = _prepare(tmp_path, FakeHost())
    assert engine is not None
    with pytest.raises(ValueError, match="prepared mode"):
        replace(prepared, mode=ExecutionMode.DRY_RUN)
    with pytest.raises(ValueError, match="requires an invocation request"):
        replace(prepared, request=None)
    blocked_preflight = PreflightResult(
        allowed=False,
        mode=prepared.preflight.mode,
        blockers=("blocked",),
        warnings=(),
        authorization=None,
        context=None,
        digest=VALID_DIGEST,
    )
    with pytest.raises(ValueError, match="cannot carry"):
        replace(prepared, preflight=blocked_preflight)


def test_prepared_invocation_rejects_request_authorization_context_and_mode_drift(
    tmp_path: Path,
) -> None:
    _, prepared = _prepare(tmp_path, FakeHost())
    assert prepared.request is not None
    request = prepared.request
    changed_authorization = replace(request.authorization, authorization_id="OTHER-AUTH")
    changed_request = replace(request, authorization=changed_authorization)
    with pytest.raises(ValueError, match="authorization is not bound"):
        replace(prepared, request=changed_request)

    changed_context = replace(request.context, digest="sha256:" + "b" * 64)
    changed_request = replace(request, context=changed_context)
    with pytest.raises(ValueError, match="context is not bound"):
        replace(prepared, request=changed_request)

    changed_authorization = replace(
        request.authorization,
        requested_execution_mode=ExecutionMode.DRY_RUN,
    )
    changed_request = replace(request, authorization=changed_authorization)
    changed_preflight = replace(prepared.preflight, authorization=changed_authorization)
    with pytest.raises(ValueError, match="mode is not bound"):
        replace(prepared, request=changed_request, preflight=changed_preflight)

    malformed_preflight = SimpleNamespace(
        allowed=True,
        blockers=(),
        warnings=(),
        authorization=None,
        context=request.context,
        mode=prepared.mode,
        digest=VALID_DIGEST,
    )
    with pytest.raises(ValueError, match="missing authorization"):
        replace(prepared, preflight=malformed_preflight)


def test_artifact_record_rejects_untrusted_enum_values() -> None:
    valid = ArtifactRecord(
        artifact_id="ART-1",
        producer_capability="safe-pilot",
        invocation_id="INV-1",
        location="/tmp/artifact.txt",
        digest=VALID_DIGEST,
        artifact_type=ArtifactType.FILE,
        timestamp=1,
        provenance=FactStatus.HOST_OBSERVED,
        dependencies=(),
        evidence_state="CURRENT",
        size_bytes=1,
    )
    with pytest.raises(ValueError, match="artifact_type"):
        replace(valid, artifact_type="FILE")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="provenance"):
        replace(valid, provenance="HOST_OBSERVED")  # type: ignore[arg-type]


def test_model_contracts_reject_invalid_enums_at_each_boundary(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="decision"):
        AssuranceResult(
            decision="PASS",  # type: ignore[arg-type]
            reason="bounded",
            limitations=(),
            verification_digest=None,
        )
    with pytest.raises(ValueError, match="supported"):
        HostPreparation(supported="yes", reason="bounded")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="reason"):
        HostPreparation(supported=True, reason="")
    with pytest.raises(ValueError, match="fact_status"):
        Phase4Event(
            sequence=0,
            method="turn/completed",
            fact_status="HOST_OBSERVED",  # type: ignore[arg-type]
            event_class="terminal",
        )
    with pytest.raises(ValueError, match="message_kind"):
        ProtocolMessageObservation(
            sequence=0,
            method=None,
            message_kind="invalid",
            has_id=False,
            has_error=False,
        )
    request = _request(tmp_path)
    with pytest.raises(ValueError, match="mode"):
        PreflightResult(
            allowed=False,
            mode="CONTROLLED_REAL",  # type: ignore[arg-type]
            blockers=("blocked",),
            warnings=(),
            authorization=None,
            context=None,
            digest=VALID_DIGEST,
        )
    assert request.skill_name == "safe-pilot"


def test_execution_outcome_rejects_invalid_mode_and_status(tmp_path: Path) -> None:
    engine, prepared = _prepare(tmp_path, FakeHost())
    outcome = engine.execute_prepared(prepared)
    with pytest.raises(ValueError, match="mode"):
        replace(outcome, mode="CONTROLLED_REAL")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="status"):
        replace(outcome, status="SUCCESS")  # type: ignore[arg-type]


def test_receipt_rejects_invalid_lifecycle_and_host_provenance(tmp_path: Path) -> None:
    engine, prepared = _prepare(tmp_path, FakeHost())
    outcome = engine.execute_prepared(prepared)
    receipt = outcome.receipt
    with pytest.raises(ValueError, match="numeric fields"):
        replace(receipt, closed_at=receipt.created_at - 1)
    with pytest.raises(ValueError, match="begin at"):
        replace(receipt, lifecycle=())
    with pytest.raises(ValueError, match="end at"):
        replace(receipt, lifecycle=(InvocationLifecycle.DISCOVERED,))
    with pytest.raises(ValueError, match="invalid state"):
        replace(
            receipt,
            lifecycle=(InvocationLifecycle.DISCOVERED, "INVALID", InvocationLifecycle.CLOSED),
        )
    with pytest.raises(ValueError, match="host_executable_path must be absolute"):
        replace(receipt, host_executable_path="relative")
    with pytest.raises(ValueError, match="host_executable_digest requires"):
        replace(receipt, host_executable_path=None, host_executable_digest=VALID_DIGEST)
