"""Bounded artifact verification and assurance inputs for Phase 4."""

from __future__ import annotations

import hashlib

from .phase4_artifacts import ArtifactCaptureError, read_artifact_bytes
from .phase4_models import (
    ArtifactRecord,
    CapabilityInvocationRequest,
    HostInvocationResult,
    InvocationReceipt,
    InvocationResultStatus,
    VerificationResult,
    digest_payload,
    invocation_receipt_digest,
    stable_digest_payload,
)


def verify_host_result(
    request: CapabilityInvocationRequest,
    result: HostInvocationResult,
    artifacts: tuple[ArtifactRecord, ...],
    *,
    evidence_refs: tuple[str, ...],
) -> VerificationResult:
    checks: list[str] = []
    failures: list[str] = []
    request_digest = stable_digest_payload(request, workspace=request.workspace)
    checks.append("REQUEST_DIGEST_BOUND")
    if result.status is InvocationResultStatus.SUCCESS:
        checks.append("HOST_RESULT_COMPLETED")
        if result.execution_observed:
            checks.append("HOST_EXECUTION_OBSERVED")
        else:
            failures.append("host execution completion was not observed")
    elif result.status is InvocationResultStatus.PARTIAL:
        checks.append("HOST_RESULT_PARTIAL")
        failures.append("host result is partial")
    elif result.status is InvocationResultStatus.TIMED_OUT:
        failures.append("host result timed out")
    elif result.status is InvocationResultStatus.CANCELLED:
        failures.append("host result was cancelled")
    else:
        failures.append(f"host result status is {result.status.value}")

    if result.final_message:
        checks.append("HOST_RESPONSE_NON_EMPTY")
    else:
        failures.append("host response is empty")
    if len(artifacts) == 1:
        checks.append("ONE_ARTIFACT_CAPTURED")
    else:
        failures.append("exactly one host-response artifact is required")
    for artifact in artifacts:
        try:
            data = read_artifact_bytes(artifact.location, request.workspace)
        except (ArtifactCaptureError, OSError):
            failures.append("artifact path is unavailable or outside workspace")
            continue
        if hashlib.sha256(data).hexdigest() != artifact.digest.removeprefix("sha256:"):
            failures.append("artifact digest mismatch")
        else:
            checks.append(f"ARTIFACT_INTEGRITY:{artifact.artifact_id}")
        if len(data) != artifact.size_bytes:
            failures.append("artifact size mismatch")
        expected_types = set(request.expected_artifacts)
        if expected_types and artifact.artifact_type.value not in expected_types:
            failures.append("artifact type is not authorized for this invocation")
        else:
            checks.append(f"ARTIFACT_TYPE:{artifact.artifact_type.value}")
        if artifact.producer_capability != request.skill_name:
            failures.append("artifact producer does not match invocation capability")
        if artifact.invocation_id != request.invocation_id:
            failures.append("artifact invocation binding does not match receipt")

    expected_host_digest = request.authorization.host_executable_digest
    if expected_host_digest is not None:
        if result.host_executable_digest != expected_host_digest:
            failures.append("host executable fingerprint is not authorization-bound")
        elif (
            result.host_executable_path is None
            or not result.host_command
            or result.host_executable_path not in result.host_command
        ):
            failures.append("host executable provenance is missing")
        else:
            checks.append("HOST_EXECUTABLE_PROVENANCE_BOUND")
    expected_interpreter_digest = request.authorization.host_interpreter_digest
    if expected_interpreter_digest is not None:
        if result.host_interpreter_digest != expected_interpreter_digest:
            failures.append("host interpreter fingerprint is not authorization-bound")
        elif result.host_interpreter_path is None:
            failures.append("host interpreter provenance is missing")
        else:
            checks.append("HOST_INTERPRETER_PROVENANCE_BOUND")

    for criterion in request.acceptance_criteria:
        normalized = criterion.lower()
        if "non-empty" in normalized or "nonempty" in normalized:
            if result.final_message:
                checks.append(f"ACCEPTANCE:{criterion}")
            else:
                failures.append(f"acceptance failed: {criterion}")
        elif normalized.startswith("marker:"):
            marker = criterion.split(":", 1)[1].strip()
            if marker and result.final_message and marker in result.final_message:
                checks.append(f"ACCEPTANCE:{criterion}")
            else:
                failures.append(f"acceptance failed: {criterion}")
        else:
            checks.append(f"ACCEPTANCE_NOT_AUTOMATICALLY_EVALUATED:{criterion}")
            failures.append(f"acceptance requires human or capability review: {criterion}")

    expected_receipt_ref = f"receipt://{request.invocation_id}"
    if expected_receipt_ref not in evidence_refs:
        failures.append("verification receipt reference is not correlated")
    else:
        checks.append("RECEIPT_REFERENCE_CORRELATED")
    if not evidence_refs:
        failures.append("verification evidence refs are missing")
    else:
        checks.append("EVIDENCE_REFERENCES_PRESENT")
    status = "VERIFIED" if not failures else "FAILED"
    reason = (
        "all bounded artifact and acceptance checks passed" if not failures else "; ".join(failures)
    )
    digest = digest_payload(
        {
            "status": status,
            "acceptance_criteria": request.acceptance_criteria,
            "artifact_refs": tuple(item.artifact_id for item in artifacts),
            "evidence_refs": evidence_refs,
            "checks": tuple(checks),
            "reason": reason,
            "request_digest": request_digest,
            "host_executable_digest": result.host_executable_digest,
            "host_interpreter_digest": result.host_interpreter_digest,
        }
    )
    return VerificationResult(
        status=status,
        acceptance_criteria=request.acceptance_criteria,
        artifact_refs=tuple(item.artifact_id for item in artifacts),
        evidence_refs=evidence_refs,
        checks=tuple(checks),
        reason=reason,
        request_digest=request_digest,
        host_executable_digest=result.host_executable_digest,
        host_interpreter_digest=result.host_interpreter_digest,
        digest=digest,
    )


def validate_receipt_binding(
    receipt: InvocationReceipt,
    request: CapabilityInvocationRequest,
    result: HostInvocationResult,
    artifacts: tuple[ArtifactRecord, ...],
    verification: VerificationResult,
    *,
    expected_status: InvocationResultStatus,
) -> tuple[str, ...]:
    """Validate the receipt after all result and artifact facts exist."""

    failures: list[str] = []
    if receipt.invocation_id != request.invocation_id:
        failures.append("receipt invocation binding mismatch")
    if receipt.mode is not request.authorization.requested_execution_mode:
        failures.append("receipt mode binding mismatch")
    if receipt.status is not expected_status:
        failures.append("receipt status binding mismatch")
    if receipt.capability_id != request.skill_name:
        failures.append("receipt capability binding mismatch")
    if receipt.capability_version != request.authorization.capability_version:
        failures.append("receipt version binding mismatch")
    if receipt.package_fingerprint != request.authorization.package_fingerprint:
        failures.append("receipt fingerprint binding mismatch")
    if receipt.authorization_id != request.authorization.authorization_id:
        failures.append("receipt authorization ID mismatch")
    expected_authorization_digest = stable_digest_payload(
        request.authorization,
        workspace=request.workspace,
    )
    if receipt.authorization_digest != expected_authorization_digest:
        failures.append("receipt authorization digest mismatch")
    if receipt.context_digest != request.context.digest:
        failures.append("receipt context digest mismatch")
    expected_request_digest = stable_digest_payload(request, workspace=request.workspace)
    if receipt.request_digest != expected_request_digest:
        failures.append("receipt request digest mismatch")
    if verification.request_digest != expected_request_digest:
        failures.append("verification request digest mismatch")
    if receipt.host_invoked != result.invocation_observed:
        failures.append("receipt host invocation observation mismatch")
    if receipt.host_load_observation is not result.load_observation:
        failures.append("receipt host load observation mismatch")
    if receipt.host_event_count != len(result.events):
        failures.append("receipt host event count mismatch")
    if receipt.host_event_digest != digest_payload(result.events):
        failures.append("receipt host event digest mismatch")
    expected_host_digest = request.authorization.host_executable_digest
    if expected_host_digest is not None:
        if result.host_executable_digest != expected_host_digest:
            failures.append("receipt host executable fingerprint mismatch")
        if result.host_executable_path is None or not result.host_command:
            failures.append("receipt host executable provenance is missing")
    if receipt.host_executable_path != result.host_executable_path:
        failures.append("receipt host executable path mismatch")
    if receipt.host_executable_digest != result.host_executable_digest:
        failures.append("receipt host executable digest mismatch")
    if receipt.host_command != result.host_command:
        failures.append("receipt host command mismatch")
    if verification.host_executable_digest != result.host_executable_digest:
        failures.append("verification host executable digest mismatch")
    expected_interpreter_digest = request.authorization.host_interpreter_digest
    if expected_interpreter_digest is not None:
        if result.host_interpreter_digest != expected_interpreter_digest:
            failures.append("receipt host interpreter fingerprint mismatch")
        if result.host_interpreter_path is None:
            failures.append("receipt host interpreter provenance is missing")
    if receipt.host_interpreter_path != result.host_interpreter_path:
        failures.append("receipt host interpreter path mismatch")
    if receipt.host_interpreter_digest != result.host_interpreter_digest:
        failures.append("receipt host interpreter digest mismatch")
    if verification.host_interpreter_digest != result.host_interpreter_digest:
        failures.append("verification host interpreter digest mismatch")
    if result.protocol_messages and len(result.protocol_messages) != result.protocol_message_count:
        failures.append("receipt protocol observation count mismatch")
    if receipt.result_digest != digest_payload(result):
        failures.append("receipt result digest mismatch")
    expected_artifact_refs = tuple(item.artifact_id for item in artifacts)
    if receipt.artifact_refs != expected_artifact_refs:
        failures.append("receipt artifact references mismatch")
    if receipt.verification_refs != (verification.digest,):
        failures.append("receipt verification references mismatch")
    if invocation_receipt_digest(receipt) != receipt.receipt_digest:
        failures.append("receipt self-digest mismatch")
    return tuple(failures)
