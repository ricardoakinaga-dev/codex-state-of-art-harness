from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from test_phase4_host import _request
from test_phase71_phase4_pipeline_hardening import (
    _DIGEST_A,
    _DIGEST_B,
    _DIGEST_ZERO,
    _capture,
    _host_result,
    _successful_outcome,
)

from harness_kernel import phase4_verification as verification_module
from harness_kernel.phase4_artifacts import capture_host_response
from harness_kernel.phase4_models import (
    ArtifactType,
    HostLoadObservation,
    InvocationResultStatus,
)


def _request_with_host_bindings(tmp_path: Path):
    request = _request(tmp_path)
    authorization = replace(
        request.authorization,
        host_executable_digest=_DIGEST_A,
        host_interpreter_digest=_DIGEST_B,
        filesystem_policy={
            **request.authorization.filesystem_policy,
            "host_executable_digest": _DIGEST_A,
            "host_interpreter_digest": _DIGEST_B,
        },
    )
    return replace(request, authorization=authorization)


def test_verification_rejects_empty_response_and_failed_acceptance_checks(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    criteria = ("response is non-empty", "marker: MUST_HAVE", "marker:")
    request = replace(
        request,
        acceptance_criteria=criteria,
        context=replace(request.context, acceptance_criteria=criteria),
    )
    result = _host_result(message="present")
    artifact = capture_host_response(request, result, timestamp=1_700_000_010, max_bytes=128)
    assert artifact is not None

    failed = verification_module.verify_host_result(
        request,
        replace(result, final_message=None),
        (artifact,),
        evidence_refs=(f"receipt://{request.invocation_id}",),
    )

    assert failed.status == "FAILED"
    assert "host response is empty" in failed.reason
    assert "acceptance failed: response is non-empty" in failed.reason
    assert "acceptance failed: marker: MUST_HAVE" in failed.reason
    assert "acceptance failed: marker:" in failed.reason


def test_verification_accepts_marker_and_rejects_artifact_identity_fields(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    criteria = ("marker: PRESENT",)
    request = replace(
        request,
        acceptance_criteria=criteria,
        context=replace(request.context, acceptance_criteria=criteria),
    )
    result = _host_result(message="PRESENT")
    artifact = capture_host_response(request, result, timestamp=1_700_000_010, max_bytes=128)
    assert artifact is not None

    failed = verification_module.verify_host_result(
        request,
        result,
        (
            replace(
                artifact,
                artifact_type=ArtifactType.FILE,
                producer_capability="other-capability",
                invocation_id="INV-OTHER",
            ),
        ),
        evidence_refs=(f"receipt://{request.invocation_id}",),
    )

    assert failed.status == "FAILED"
    assert "ARTIFACT_TYPE:FILE" not in failed.checks
    assert "artifact type is not authorized" in failed.reason
    assert "artifact producer does not match" in failed.reason
    assert "artifact invocation binding does not match" in failed.reason


def test_verification_requires_authorized_executable_and_interpreter_provenance(
    tmp_path: Path,
) -> None:
    request = _request_with_host_bindings(tmp_path)
    result = _host_result(
        host_executable_digest=_DIGEST_A,
        host_executable_path="/bin/codex",
        host_command=("/bin/codex",),
        host_interpreter_digest=_DIGEST_B,
        host_interpreter_path="/bin/python",
    )
    artifact = capture_host_response(request, result, timestamp=1_700_000_010, max_bytes=128)
    assert artifact is not None

    executable_failed = verification_module.verify_host_result(
        request,
        replace(result, host_executable_digest=_DIGEST_ZERO),
        (artifact,),
        evidence_refs=(f"receipt://{request.invocation_id}",),
    )
    assert "host executable fingerprint is not authorization-bound" in executable_failed.reason

    missing_executable = replace(result)
    object.__setattr__(missing_executable, "host_executable_path", None)
    object.__setattr__(missing_executable, "host_command", ())
    executable_provenance_failed = verification_module.verify_host_result(
        request,
        missing_executable,
        (artifact,),
        evidence_refs=(f"receipt://{request.invocation_id}",),
    )
    assert "host executable provenance is missing" in executable_provenance_failed.reason

    interpreter_failed = verification_module.verify_host_result(
        request,
        replace(result, host_interpreter_digest=_DIGEST_ZERO),
        (artifact,),
        evidence_refs=(f"receipt://{request.invocation_id}",),
    )
    assert "host interpreter fingerprint is not authorization-bound" in interpreter_failed.reason

    missing_interpreter = replace(result)
    object.__setattr__(missing_interpreter, "host_interpreter_path", None)
    interpreter_provenance_failed = verification_module.verify_host_result(
        request,
        missing_interpreter,
        (artifact,),
        evidence_refs=(f"receipt://{request.invocation_id}",),
    )
    assert "host interpreter provenance is missing" in interpreter_provenance_failed.reason


def test_receipt_binding_rejects_digest_observation_and_provenance_drift(
    tmp_path: Path,
) -> None:
    outcome, request = _successful_outcome(tmp_path)
    assert outcome.verification is not None
    assert outcome.host_result is not None

    request_digest_drift = replace(outcome.verification, request_digest=_DIGEST_ZERO)
    failures = verification_module.validate_receipt_binding(
        outcome.receipt,
        request,
        outcome.host_result,
        outcome.artifacts,
        request_digest_drift,
        expected_status=InvocationResultStatus.SUCCESS,
    )
    assert "verification request digest mismatch" in failures

    load_drift = replace(outcome.host_result, load_observation=HostLoadObservation.PARTIAL)
    failures = verification_module.validate_receipt_binding(
        outcome.receipt,
        request,
        load_drift,
        outcome.artifacts,
        outcome.verification,
        expected_status=InvocationResultStatus.SUCCESS,
    )
    assert "receipt host load observation mismatch" in failures

    executable_missing = replace(outcome.host_result)
    object.__setattr__(executable_missing, "host_executable_path", None)
    object.__setattr__(executable_missing, "host_command", ())
    failures = verification_module.validate_receipt_binding(
        outcome.receipt,
        request,
        executable_missing,
        outcome.artifacts,
        outcome.verification,
        expected_status=InvocationResultStatus.SUCCESS,
    )
    assert "receipt host executable provenance is missing" in failures

    interpreter_drift = replace(
        outcome.host_result,
        host_interpreter_digest=_DIGEST_ZERO,
    )
    failures = verification_module.validate_receipt_binding(
        outcome.receipt,
        request,
        interpreter_drift,
        outcome.artifacts,
        outcome.verification,
        expected_status=InvocationResultStatus.SUCCESS,
    )
    assert "receipt host interpreter fingerprint mismatch" in failures

    interpreter_missing = replace(outcome.host_result)
    object.__setattr__(interpreter_missing, "host_interpreter_path", None)
    failures = verification_module.validate_receipt_binding(
        outcome.receipt,
        request,
        interpreter_missing,
        outcome.artifacts,
        outcome.verification,
        expected_status=InvocationResultStatus.SUCCESS,
    )
    assert "receipt host interpreter provenance is missing" in failures

    tampered_receipt = replace(
        outcome.receipt,
        host_interpreter_path="/bin/other-python",
        host_interpreter_digest=_DIGEST_ZERO,
    )
    tampered_verification = replace(
        outcome.verification,
        host_interpreter_digest=_DIGEST_ZERO,
    )
    failures = verification_module.validate_receipt_binding(
        tampered_receipt,
        request,
        outcome.host_result,
        outcome.artifacts,
        tampered_verification,
        expected_status=InvocationResultStatus.SUCCESS,
    )
    assert "receipt host interpreter path mismatch" in failures
    assert "receipt host interpreter digest mismatch" in failures
    assert "verification host interpreter digest mismatch" in failures

    unbound_authorization = replace(
        request.authorization,
        host_executable_digest=None,
        host_interpreter_digest=None,
        filesystem_policy={
            **request.authorization.filesystem_policy,
            "host_executable_digest": None,
            "host_interpreter_digest": None,
        },
    )
    unbound_request = replace(request, authorization=unbound_authorization)
    failures = verification_module.validate_receipt_binding(
        outcome.receipt,
        unbound_request,
        outcome.host_result,
        outcome.artifacts,
        outcome.verification,
        expected_status=InvocationResultStatus.SUCCESS,
    )
    assert "receipt host executable path mismatch" not in failures

    protocol_drift = replace(outcome.host_result)
    object.__setattr__(protocol_drift, "protocol_messages", (object(),))
    object.__setattr__(protocol_drift, "protocol_message_count", 2)
    failures = verification_module.validate_receipt_binding(
        outcome.receipt,
        request,
        protocol_drift,
        outcome.artifacts,
        outcome.verification,
        expected_status=InvocationResultStatus.SUCCESS,
    )
    assert "receipt protocol observation count mismatch" in failures


def test_verification_missing_artifact_path_remains_failed_without_false_integrity(
    tmp_path: Path,
) -> None:
    request, result, artifact = _capture(tmp_path)
    missing = replace(artifact, location=str(tmp_path / "missing.json"))

    failed = verification_module.verify_host_result(
        request,
        result,
        (missing,),
        evidence_refs=(f"receipt://{request.invocation_id}",),
    )

    assert failed.status == "FAILED"
    assert "artifact path is unavailable or outside workspace" in failed.reason
    assert f"ARTIFACT_INTEGRITY:{artifact.artifact_id}" not in failed.checks
