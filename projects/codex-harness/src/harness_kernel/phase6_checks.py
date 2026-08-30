"""Deterministic, read-only procedure adapters for Phase 6."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path
from urllib.parse import urlparse

from .phase3_paths import PathSafetyError, bounded_file_metadata, read_bounded_file
from .phase6_models import (
    ArtifactRef,
    Evidence,
    EvidenceKind,
    FreshnessStatus,
    ProcedureResult,
    ProcedureSpec,
    VerificationInput,
    VerificationStatus,
)
from .phase6_policy import Phase6PolicyError, validate_procedure_policy


def read_confined_bytes(
    path: str | Path, workspace: str | Path, *, max_bytes: int
) -> tuple[Path, bytes]:
    """Read one regular file with descriptor-relative confinement and bounds."""

    from .phase5_artifacts import ArtifactCaptureError, validate_artifact_path

    try:
        workspace_path = Path(workspace).resolve(strict=True)
        workspace_metadata = workspace_path.lstat()
        if not stat.S_ISDIR(workspace_metadata.st_mode):
            raise Phase6CheckError("workspace is not a directory")
        expected_base_identity = (workspace_metadata.st_dev, workspace_metadata.st_ino)
        safe_path = Path(validate_artifact_path(path, workspace))
        relative = safe_path.relative_to(workspace_path)
        content = read_bounded_file(
            workspace_path,
            relative.as_posix(),
            max_bytes=max_bytes,
            expected_base_identity=expected_base_identity,
        )
    except ArtifactCaptureError as exc:
        raise Phase6CheckError("artifact path is unsafe or outside the workspace") from exc
    except (OSError, PathSafetyError, ValueError) as exc:
        raise Phase6CheckError("artifact cannot be read safely") from exc
    return safe_path, content


def confined_file_exists(path: str | Path, workspace: str | Path) -> bool:
    """Check regular-file existence through the same confined descriptor boundary."""

    from .phase5_artifacts import ArtifactCaptureError, validate_artifact_path

    try:
        workspace_path = Path(workspace).resolve(strict=True)
        workspace_metadata = workspace_path.lstat()
        if not stat.S_ISDIR(workspace_metadata.st_mode):
            return False
        expected_base_identity = (workspace_metadata.st_dev, workspace_metadata.st_ino)
        safe_path = Path(validate_artifact_path(path, workspace))
        relative = safe_path.relative_to(workspace_path)
        bounded_file_metadata(
            workspace_path,
            relative.as_posix(),
            expected_base_identity=expected_base_identity,
        )
    except (ArtifactCaptureError, OSError, PathSafetyError, ValueError):
        return False
    return True


class Phase6CheckError(ValueError):
    """Raised when a deterministic check cannot be safely prepared."""


_FORBIDDEN_CHECKS = frozenset({"shell", "network", "subprocess", "mcp", "write", "mutate"})
_SUPPORTED_CHECKS = frozenset(
    {
        "file_digest",
        "artifact_integrity",
        "path_exists",
        "text_contains",
        "text_absent",
        "json_object",
        "browser_capture",
    }
)
_CAPTURE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_CAPTURE_BYTES = 512 * 1024
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _is_loopback_url(value: object) -> bool:
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and hostname in _LOOPBACK_HOSTS
        and parsed.username is None
        and parsed.password is None
        and port is not None
    )


def _reject_non_finite_json(value: str) -> object:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def validate_procedure_spec(
    procedure: ProcedureSpec, verification_input: VerificationInput
) -> tuple[str, ...]:
    check = procedure.check.casefold()
    if check not in _SUPPORTED_CHECKS:
        raise Phase6CheckError("procedure check is not in the allowlisted vocabulary")
    if check in _FORBIDDEN_CHECKS or any(
        word in check for word in ("shell", "network", "subprocess", "credential")
    ):
        raise Phase6CheckError("shell, network, subprocess and credential checks are forbidden")
    try:
        return validate_procedure_policy(procedure, verification_input)
    except Phase6PolicyError as exc:
        raise Phase6CheckError(str(exc)) from exc


def _spec_for(criterion_id: str, procedure_id: str, check: str = "FILE_DIGEST") -> ProcedureSpec:
    return ProcedureSpec(
        procedure_id=procedure_id,
        criterion_id=criterion_id,
        description=f"read-only {check} check",
        check=check,
    )


def _result(
    spec: ProcedureSpec,
    status: VerificationStatus,
    verification_input: VerificationInput,
    *,
    evidence: tuple[Evidence, ...] = (),
    observation: str = "",
    error: str | None = None,
) -> ProcedureResult:
    return ProcedureResult(
        spec=spec,
        status=status,
        executed=True,
        evidence=evidence,
        attempts=1,
        observed_at=verification_input.observed_at,
        observation=observation,
        error=error,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
        verifier_id=verification_input.capability_id,
    )


def _evidence(
    verification_input: VerificationInput,
    *,
    criterion_id: str,
    artifact: ArtifactRef,
    kind: EvidenceKind,
    observation: str,
) -> Evidence:
    return Evidence(
        evidence_id=f"{criterion_id}-EVIDENCE",
        criterion_id=criterion_id,
        digest="",
        artifact_refs=(artifact.artifact_id,),
        artifact_digest=artifact.digest,
        package_digest=verification_input.package_digest,
        observed_at=verification_input.observed_at,
        freshness=FreshnessStatus.FRESH,
        kind=kind,
        path=artifact.path,
        observation=observation,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
    )


def _artifact(verification_input: VerificationInput, artifact_id: str) -> ArtifactRef | None:
    return next(
        (item for item in verification_input.artifact_refs if item.artifact_id == artifact_id), None
    )


def check_artifact(
    verification_input: VerificationInput,
    artifact_id: str,
    *,
    criterion_id: str | None = None,
) -> ProcedureResult:
    """Compare one declared artifact with its digest without writing to it."""

    artifact = _artifact(verification_input, artifact_id)
    selected_criterion = criterion_id or verification_input.required_criteria[0]
    if artifact is None:
        spec = _spec_for(selected_criterion, f"CHECK-{artifact_id}")
        return _result(
            spec,
            VerificationStatus.BLOCKED,
            verification_input,
            error="artifact is not declared by the verification input",
        )
    spec = _spec_for(selected_criterion, f"CHECK-{artifact_id}")
    validate_procedure_spec(spec, verification_input)
    try:
        _, content = read_confined_bytes(
            artifact.path,
            verification_input.workspace,
            max_bytes=verification_input.budgets.max_report_bytes,
        )
    except Phase6CheckError as exc:
        return _result(spec, VerificationStatus.BLOCKED, verification_input, error=str(exc))
    actual_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    observation = f"artifact {artifact.artifact_id} digest observed as {actual_digest}"
    evidence = _evidence(
        verification_input,
        criterion_id=selected_criterion,
        artifact=artifact,
        kind=EvidenceKind.ARTIFACT,
        observation=observation,
    )
    status = (
        VerificationStatus.PASS if actual_digest == artifact.digest else VerificationStatus.FAIL
    )
    error = (
        None
        if status is VerificationStatus.PASS
        else "artifact digest does not match the declared digest"
    )
    return _result(
        spec,
        status,
        verification_input,
        evidence=(evidence,),
        observation=observation,
        error=error,
    )


def _parameter(spec: ProcedureSpec, name: str) -> object:
    return spec.parameters.get(name)


def _target_artifact(
    verification_input: VerificationInput, spec: ProcedureSpec
) -> ArtifactRef | None:
    selected = _parameter(spec, "artifact_id")
    if selected is not None and not isinstance(selected, str):
        raise Phase6CheckError("artifact_id procedure parameter must be a string")
    artifact_id = selected or (
        verification_input.artifact_refs[0].artifact_id
        if verification_input.artifact_refs
        else None
    )
    return _artifact(verification_input, artifact_id) if artifact_id else None


def _read_artifact(
    verification_input: VerificationInput, spec: ProcedureSpec
) -> tuple[ArtifactRef, bytes] | None:
    artifact = _target_artifact(verification_input, spec)
    if artifact is None:
        return None
    try:
        _, content = read_confined_bytes(
            artifact.path,
            verification_input.workspace,
            max_bytes=verification_input.budgets.max_report_bytes,
        )
    except Phase6CheckError:
        return None
    actual_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    if actual_digest != artifact.digest:
        return None
    return artifact, content


def _read_declared_file(
    path_value: object,
    workspace: str,
    *,
    expected_digest: object,
    expected_bytes: object,
    max_bytes: int = _MAX_CAPTURE_BYTES,
) -> tuple[Path, bytes] | None:
    """Re-open a declared file and verify its path, size and digest at read time."""

    if (
        not isinstance(path_value, str)
        or not Path(path_value).is_absolute()
        or not isinstance(expected_digest, str)
        or _CAPTURE_DIGEST.fullmatch(expected_digest) is None
        or not isinstance(expected_bytes, int)
        or isinstance(expected_bytes, bool)
        or expected_bytes < 1
        or expected_bytes > max_bytes
    ):
        return None
    try:
        safe_path, content = read_confined_bytes(path_value, workspace, max_bytes=max_bytes)
    except Phase6CheckError:
        return None
    actual_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    if len(content) != expected_bytes or actual_digest != expected_digest:
        return None
    return safe_path, content


def run_deterministic_procedure(
    verification_input: VerificationInput, procedure: ProcedureSpec
) -> ProcedureResult:
    """Run only the small, declarative standard-library check vocabulary."""

    validate_procedure_spec(procedure, verification_input)
    check = procedure.check.casefold()
    if check in {"file_digest", "artifact_integrity"}:
        artifact = _target_artifact(verification_input, procedure)
        if artifact is None:
            return _result(
                procedure,
                VerificationStatus.BLOCKED,
                verification_input,
                error="declared artifact is missing",
            )
        result = check_artifact(
            verification_input,
            artifact.artifact_id,
            criterion_id=procedure.criterion_id,
        )
        expected = _parameter(procedure, "expected_digest")
        if expected is not None and expected != artifact.digest:
            return _result(
                procedure,
                VerificationStatus.FAIL,
                verification_input,
                evidence=result.evidence,
                error="procedure expected digest differs from the declared artifact",
            )
        return ProcedureResult(
            procedure_id=procedure.procedure_id,
            criterion_id=procedure.criterion_id,
            status=result.status,
            executed=result.executed,
            evidence=result.evidence,
            attempts=result.attempts,
            observed_at=result.observed_at,
            observation=result.observation,
            error=result.error,
            spec=procedure,
            run_id=result.run_id,
            task_id=result.task_id,
            input_digest=result.input_digest,
            verifier_id=result.verifier_id,
        )
    if check == "path_exists":
        target = _target_artifact(verification_input, procedure)
        if target is None:
            return _result(
                procedure,
                VerificationStatus.BLOCKED,
                verification_input,
                error="declared artifact is missing",
            )
        exists = _read_artifact(verification_input, procedure) is not None
        evidence = (
            (
                _evidence(
                    verification_input,
                    criterion_id=procedure.criterion_id,
                    artifact=target,
                    kind=EvidenceKind.ARTIFACT,
                    observation=f"artifact path exists: {exists}",
                ),
            )
            if exists
            else ()
        )
        return _result(
            procedure,
            VerificationStatus.PASS if exists else VerificationStatus.FAIL,
            verification_input,
            evidence=evidence,
            observation=f"artifact path exists: {exists}",
            error=None if exists else "artifact path is missing",
        )
    if check == "text_contains":
        target_and_content = _read_artifact(verification_input, procedure)
        needle = _parameter(procedure, "text")
        if not isinstance(needle, str) or not needle:
            raise Phase6CheckError("text_contains requires a non-empty text parameter")
        if target_and_content is None:
            return _result(
                procedure,
                VerificationStatus.BLOCKED,
                verification_input,
                error="declared artifact is missing",
            )
        target, content = target_and_content
        found = needle.encode("utf-8") in content
        evidence = (
            (
                _evidence(
                    verification_input,
                    criterion_id=procedure.criterion_id,
                    artifact=target,
                    kind=EvidenceKind.TEST,
                    observation=f"declared text present: {found}",
                ),
            )
            if found
            else ()
        )
        return _result(
            procedure,
            VerificationStatus.PASS if found else VerificationStatus.FAIL,
            verification_input,
            evidence=evidence,
            observation=f"declared text present: {found}",
            error=None if found else "declared text is absent",
        )
    if check == "text_absent":
        target_and_content = _read_artifact(verification_input, procedure)
        needle = _parameter(procedure, "text")
        if not isinstance(needle, str) or not needle:
            raise Phase6CheckError("text_absent requires a non-empty text parameter")
        if target_and_content is None:
            return _result(
                procedure,
                VerificationStatus.BLOCKED,
                verification_input,
                error="declared artifact is missing",
            )
        target, content = target_and_content
        found = needle.encode("utf-8") in content
        absent = not found
        absence_evidence: Evidence = _evidence(
            verification_input,
            criterion_id=procedure.criterion_id,
            artifact=target,
            kind=EvidenceKind.TEST,
            observation=f"declared text absent: {absent}",
        )
        return _result(
            procedure,
            VerificationStatus.PASS if absent else VerificationStatus.FAIL,
            verification_input,
            evidence=(absence_evidence,),
            observation=f"declared text absent: {absent}",
            error=None if absent else "forbidden text is present",
        )
    if check == "json_object":
        target_and_content = _read_artifact(verification_input, procedure)
        if target_and_content is None:
            return _result(
                procedure,
                VerificationStatus.BLOCKED,
                verification_input,
                error="declared artifact is missing",
            )
        target, content = target_and_content
        try:
            parsed = json.loads(content.decode("utf-8"), parse_constant=_reject_non_finite_json)
        except (UnicodeDecodeError, RecursionError, ValueError):
            parsed = None
        valid = isinstance(parsed, dict)
        evidence = (
            (
                _evidence(
                    verification_input,
                    criterion_id=procedure.criterion_id,
                    artifact=target,
                    kind=EvidenceKind.TEST,
                    observation=f"JSON object observed: {valid}",
                ),
            )
            if valid
            else ()
        )
        return _result(
            procedure,
            VerificationStatus.PASS if valid else VerificationStatus.FAIL,
            verification_input,
            evidence=evidence,
            observation=f"JSON object observed: {valid}",
            error=None if valid else "artifact is not a JSON object",
        )
    if check == "browser_capture":
        target_and_content = _read_artifact(verification_input, procedure)
        if target_and_content is None:
            return _result(
                procedure,
                VerificationStatus.BLOCKED,
                verification_input,
                error="browser capture manifest is missing",
            )
        target, content = target_and_content
        try:
            payload = json.loads(content.decode("utf-8"), parse_constant=_reject_non_finite_json)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError):
            payload = None
        artifact_map = {item.artifact_id: item for item in verification_input.artifact_refs}
        source_id = _parameter(procedure, "source_artifact_id")
        desktop_id = _parameter(procedure, "desktop_artifact_id")
        mobile_id = _parameter(procedure, "mobile_artifact_id")
        source = artifact_map.get(source_id) if isinstance(source_id, str) else None
        desktop = artifact_map.get(desktop_id) if isinstance(desktop_id, str) else None
        mobile = artifact_map.get(mobile_id) if isinstance(mobile_id, str) else None
        if source is None or desktop is None or mobile is None:
            return _result(
                procedure,
                VerificationStatus.BLOCKED,
                verification_input,
                error="browser capture artifact references are incomplete",
            )
        valid = (
            isinstance(payload, dict)
            and payload.get("schema_version") == "P6-BROWSER-CAPTURE-1"
            and payload.get("task_id") == _parameter(procedure, "task_id")
            and payload.get("run_id") == _parameter(procedure, "run_id")
            and payload.get("criteria_digest") == _parameter(procedure, "criteria_digest")
            and payload.get("artifact_id") == source.artifact_id
            and payload.get("artifact_version") == source.version
            and _parameter(procedure, "expected_digest") == target.digest
            and _parameter(procedure, "source_artifact_digest") == source.digest
            and _parameter(procedure, "desktop_digest") == desktop.digest
            and _parameter(procedure, "mobile_digest") == mobile.digest
            and _is_loopback_url(payload.get("url"))
        )
        browser_payload = payload.get("browser") if isinstance(payload, dict) else None
        if valid:
            valid = (
                isinstance(browser_payload, dict)
                and browser_payload.get("url") == payload.get("url")
                and browser_payload.get("task_id") == payload.get("task_id")
                and browser_payload.get("run_id") == payload.get("run_id")
                and browser_payload.get("criteria_digest") == payload.get("criteria_digest")
                and browser_payload.get("artifact_id") == payload.get("artifact_id")
                and browser_payload.get("artifact_version") == payload.get("artifact_version")
                and _is_loopback_url(browser_payload.get("url"))
            )
        source_payload = payload.get("source") if isinstance(payload, dict) else None
        if valid:
            valid = (
                isinstance(source_payload, dict)
                and source_payload.get("digest") == source.digest
                and source_payload.get("bytes") == source.size_bytes
                and source_payload.get("served_digest") == source.digest
                and source_payload.get("served_bytes") == source.size_bytes
                and source_payload.get("served_matches_declared") is True
            )
        if valid:
            source_file = _read_declared_file(
                source_payload.get("path") if isinstance(source_payload, dict) else None,
                verification_input.workspace,
                expected_digest=source_payload.get("digest")
                if isinstance(source_payload, dict)
                else None,
                expected_bytes=source_payload.get("bytes")
                if isinstance(source_payload, dict)
                else None,
            )
            valid = (
                source_file is not None
                and source_file[0] == Path(source.path).resolve()
                and source_payload.get("path") == source.path
                if isinstance(source_payload, dict)
                else False
            )
        captures = payload.get("captures") if isinstance(payload, dict) else None
        if valid:
            capture_records: dict[str, Path] = {}
            if not isinstance(captures, list) or not 0 < len(captures) <= 16:
                valid = False
            else:
                for item in captures:
                    if not isinstance(item, dict):
                        valid = False
                        break
                    capture = _read_declared_file(
                        item.get("path"),
                        verification_input.workspace,
                        expected_digest=item.get("digest"),
                        expected_bytes=item.get("bytes"),
                    )
                    if capture is None:
                        valid = False
                        break
                    digest = item.get("digest")
                    if not isinstance(digest, str) or digest in capture_records:
                        valid = False
                        break
                    capture_records[digest] = capture[0]
            if valid:
                for artifact in (desktop, mobile):
                    artifact_file = _read_declared_file(
                        artifact.path,
                        verification_input.workspace,
                        expected_digest=artifact.digest,
                        expected_bytes=artifact.size_bytes,
                    )
                    if (
                        artifact_file is None
                        or capture_records.get(artifact.digest) != artifact_file[0]
                    ):
                        valid = False
                        break
        observation = f"browser capture source and render digests bound: {valid}"
        evidence = (
            (
                _evidence(
                    verification_input,
                    criterion_id=procedure.criterion_id,
                    artifact=target,
                    kind=EvidenceKind.RENDER,
                    observation=observation,
                ),
            )
            if valid
            else ()
        )
        return _result(
            procedure,
            VerificationStatus.PASS if valid else VerificationStatus.FAIL,
            verification_input,
            evidence=evidence,
            observation=observation,
            error=None if valid else "browser capture manifest is not bound",
        )
    return _result(
        procedure,
        VerificationStatus.NOT_RUN,
        verification_input,
        error="procedure check is not in the deterministic standard-library vocabulary",
    )


def make_procedure_result(
    procedure: ProcedureSpec,
    verification_input: VerificationInput,
    *,
    status: VerificationStatus,
    evidence: tuple[Evidence, ...] = (),
) -> ProcedureResult:
    """Construct a bounded result for an externally supplied deterministic observation."""

    validate_procedure_spec(procedure, verification_input)
    return _result(procedure, status, verification_input, evidence=evidence)


execute_procedure = run_deterministic_procedure
run_procedure = run_deterministic_procedure
