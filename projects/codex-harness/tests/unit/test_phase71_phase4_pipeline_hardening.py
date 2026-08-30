from __future__ import annotations

import hashlib
import json
import os
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

import pytest
from test_phase4_execution import FakeHost, _fixture
from test_phase4_host import _request

from harness_kernel import phase4_artifacts as artifacts_module
from harness_kernel import phase4_cli as cli_module
from harness_kernel import phase4_policy as policy_module
from harness_kernel import phase4_verification as verification_module
from harness_kernel.phase3_models import (
    CapabilityKind,
    CompatibilityStatus,
    PackageFile,
    ResolutionStatus,
    TrustLevel,
)
from harness_kernel.phase4_artifacts import (
    ArtifactCaptureError,
    capture_host_response,
    read_artifact_bytes,
    validate_artifact_path,
)
from harness_kernel.phase4_execution import InvocationEngine
from harness_kernel.phase4_models import (
    ArtifactType,
    ExecutionMode,
    FactStatus,
    HostInvocationResult,
    HostLoadObservation,
    InvocationResultStatus,
    Phase4Budget,
    ProtocolMessageObservation,
    digest_payload,
    invocation_receipt_digest,
    stable_digest_payload,
)
from harness_kernel.phase4_policy import (
    ExecutionPolicyRegistry,
    Phase4PolicyError,
    PilotRule,
    build_preflight,
    preflight_digest,
)

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_ZERO = "sha256:" + "0" * 64


def _host_result(
    status: InvocationResultStatus = InvocationResultStatus.SUCCESS,
    *,
    message: str | None = "PIPELINE_ARTIFACT",
    invocation_observed: bool = True,
    execution_observed: bool = True,
    error_code: str | None = None,
    host_executable_digest: str | None = None,
    host_executable_path: str | None = None,
    host_command: tuple[str, ...] = (),
    host_interpreter_digest: str | None = None,
    host_interpreter_path: str | None = None,
) -> HostInvocationResult:
    return HostInvocationResult(
        status=status,
        thread_id="thread-pipeline",
        session_id="session-pipeline",
        turn_id="turn-pipeline",
        host_version="fake-pipeline-host",
        events=(),
        final_message=message,
        load_observation=HostLoadObservation.UNOBSERVABLE,
        invocation_observed=invocation_observed,
        execution_observed=execution_observed,
        denied_approvals=0,
        cancellation_status="NOT_REQUESTED",
        error_code=error_code,
        started_at=1_700_000_000,
        completed_at=1_700_000_001,
        host_executable_path=host_executable_path,
        host_executable_digest=host_executable_digest,
        host_command=host_command,
        host_interpreter_path=host_interpreter_path,
        host_interpreter_digest=host_interpreter_digest,
    )


def _capture(tmp_path: Path, *, message: str = "PIPELINE_ARTIFACT"):
    request = _request(tmp_path)
    result = _host_result(message=message)
    record = capture_host_response(request, result, timestamp=1_700_000_010, max_bytes=128)
    assert record is not None
    return request, result, record


def _rule(record, **overrides: object) -> PilotRule:
    values: dict[str, object] = {
        "capability_id": record.capability_id,
        "version": record.version,
        "package_fingerprint": record.content_hash,
        "execution_approved": True,
        "allowed_modes": (
            ExecutionMode.DRY_RUN,
            ExecutionMode.PREPARE_ONLY,
            ExecutionMode.CONTROLLED_REAL,
        ),
        "host_executable_digest": _DIGEST_A,
        "host_interpreter_digest": _DIGEST_B,
        "reason": "bounded phase 7.1 pipeline fixture",
    }
    values.update(overrides)
    return PilotRule(**values)


def _policy_fixture(tmp_path: Path):
    record, inventory, resolution, _ = _fixture(tmp_path)
    return record, inventory, resolution, ExecutionPolicyRegistry((_rule(record),))


def _cli_project(tmp_path: Path) -> Path:
    package = tmp_path / ".agents" / "skills" / "safe-pilot"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: safe-pilot\nversion: 0.1.0\n---\nReturn a bounded result.\n",
        encoding="utf-8",
    )
    from harness_kernel.phase3_host import CodexHostAdapter

    inventory = CodexHostAdapter(
        project_root=tmp_path,
        home_dir=tmp_path / "no-home",
        codex_home=tmp_path / "no-codex-home",
    ).discover_capabilities()
    record = next(item for item in inventory.capabilities if item.capability_id == "safe-pilot")
    config = tmp_path / "config"
    config.mkdir()
    (config / "phase4-execution-policy.json").write_text(
        json.dumps(
            {
                "schema_version": "P4-POLICY-1",
                "rules": [
                    {
                        "capability_id": record.capability_id,
                        "version": record.version,
                        "package_fingerprint": record.content_hash,
                        "execution_approved": True,
                        "allowed_modes": ["DRY_RUN", "PREPARE_ONLY", "CONTROLLED_REAL"],
                        "host_executable_digest": _DIGEST_A,
                        "host_interpreter_digest": _DIGEST_B,
                        "reason": "CLI pipeline fixture",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_capture_round_trip_records_atomic_artifact_and_receipt_binding(tmp_path: Path) -> None:
    request, result, record = _capture(tmp_path)

    artifact_path = Path(record.location)
    assert artifact_path.is_file()
    assert read_artifact_bytes(artifact_path, tmp_path) == b"PIPELINE_ARTIFACT"
    assert record.artifact_id == f"ART-{request.invocation_id}"
    assert record.producer_capability == request.skill_name
    assert record.invocation_id == request.invocation_id
    assert record.digest == "sha256:" + hashlib.sha256(b"PIPELINE_ARTIFACT").hexdigest()
    assert record.artifact_type is ArtifactType.HOST_RESPONSE
    assert record.provenance is FactStatus.HARNESS_OBSERVED
    assert record.size_bytes == len(result.final_message.encode("utf-8"))
    assert list(artifact_path.parent.glob("*.tmp")) == []


@pytest.mark.parametrize(
    ("message", "max_bytes", "expected_error"),
    (("too-large", 3, "exceeds artifact bound"), (None, 128, None)),
)
def test_capture_rejects_invalid_response_before_creating_artifact(
    tmp_path: Path, message: str | None, max_bytes: int, expected_error: str | None
) -> None:
    request = _request(tmp_path)
    if expected_error is None:
        assert (
            capture_host_response(
                request,
                _host_result(message=message),
                timestamp=1_700_000_010,
                max_bytes=max_bytes,
            )
            is None
        )
    else:
        with pytest.raises(ArtifactCaptureError, match=expected_error):
            capture_host_response(
                request,
                _host_result(message=message),
                timestamp=1_700_000_010,
                max_bytes=max_bytes,
            )
    assert not (tmp_path / ".harness").exists()


@pytest.mark.parametrize("max_bytes", (0, -1, True, 1.5))
def test_capture_rejects_invalid_byte_bound_without_side_effect(
    tmp_path: Path, max_bytes: object
) -> None:
    with pytest.raises(ArtifactCaptureError, match="byte bound is invalid"):
        capture_host_response(
            _request(tmp_path),
            _host_result(),
            timestamp=1_700_000_010,
            max_bytes=max_bytes,  # type: ignore[arg-type]
        )
    assert not (tmp_path / ".harness").exists()


def test_capture_detects_artifact_directory_replacement_after_atomic_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = artifacts_module._atomic_write_at
    artifact_dir = tmp_path / ".harness" / "phase4" / "artifacts"

    def replace_directory(directory_fd: int, name: str, content: bytes) -> None:
        original(directory_fd, name, content)
        preserved = artifact_dir.with_name("artifacts-preserved")
        artifact_dir.rename(preserved)
        artifact_dir.mkdir()

    monkeypatch.setattr(artifacts_module, "_atomic_write_at", replace_directory)

    with pytest.raises(ArtifactCaptureError, match="directory changed"):
        capture_host_response(
            _request(tmp_path),
            _host_result(),
            timestamp=1_700_000_010,
            max_bytes=128,
        )
    assert (tmp_path / ".harness" / "phase4" / "artifacts").is_dir()
    assert list((tmp_path / ".harness" / "phase4" / "artifacts-preserved").iterdir())


@pytest.mark.parametrize("name", ("", "../escape", "nested/name", "bad\x00name"))
def test_atomic_artifact_writer_rejects_unsafe_names_without_escape(
    tmp_path: Path, name: str
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(ArtifactCaptureError, match="filename is unsafe"):
            artifacts_module._atomic_write_at(descriptor, name, b"blocked")
    finally:
        os.close(descriptor)
    assert not (tmp_path / "escape").exists()


def test_atomic_artifact_writer_rejects_symlink_directory_and_hardlink_targets(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    symlink = tmp_path / "link.txt"
    symlink.symlink_to(outside)
    directory = tmp_path / "directory.txt"
    directory.mkdir()
    hardlink_source = tmp_path / "hardlink-source.txt"
    hardlink_source.write_text("original", encoding="utf-8")
    hardlink = tmp_path / "hardlink.txt"
    hardlink.hardlink_to(hardlink_source)

    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in (symlink.name, directory.name, hardlink.name):
            with pytest.raises(ArtifactCaptureError, match="unique regular file"):
                artifacts_module._atomic_write_at(descriptor, name, b"replacement")
    finally:
        os.close(descriptor)
    assert symlink.is_symlink()
    assert directory.is_dir()
    assert hardlink_source.read_text(encoding="utf-8") == "original"


def test_atomic_artifact_writer_rolls_back_temporary_file_after_zero_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    original_write = artifacts_module.os.write
    monkeypatch.setattr(artifacts_module.os, "write", lambda fd, data: 0)
    try:
        with pytest.raises(ArtifactCaptureError, match="could not be written"):
            artifacts_module._atomic_write_at(descriptor, "artifact.txt", b"payload")
    finally:
        os.close(descriptor)
        monkeypatch.setattr(artifacts_module.os, "write", original_write)
    assert not (tmp_path / "artifact.txt").exists()
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize(
    ("location", "message"),
    (
        ("relative.txt", "absolute"),
        ("/outside/artifact.txt", "escapes workspace"),
    ),
)
def test_validate_artifact_path_rejects_scope_and_relative_locations(
    tmp_path: Path, location: str, message: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(ArtifactCaptureError, match=message):
        validate_artifact_path(location, workspace)


def test_artifact_reader_rejects_missing_directory_hardlink_and_oversized_files(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    directory = workspace / "directory"
    directory.mkdir()
    regular = workspace / "regular.txt"
    regular.write_text("0123456789", encoding="utf-8")
    hardlink = workspace / "hardlink.txt"
    hardlink.hardlink_to(regular)

    with pytest.raises(ArtifactCaptureError, match="could not be read safely"):
        read_artifact_bytes(workspace / "missing.txt", workspace)
    with pytest.raises(ArtifactCaptureError, match="unique regular file"):
        read_artifact_bytes(directory, workspace)
    with pytest.raises(ArtifactCaptureError, match="unique regular file"):
        read_artifact_bytes(hardlink, workspace)
    bounded = workspace / "bounded.txt"
    bounded.write_text("0123456789", encoding="utf-8")
    with pytest.raises(ArtifactCaptureError, match="verification bound"):
        read_artifact_bytes(bounded, workspace, max_bytes=3)


def test_artifact_directory_security_requires_no_follow_and_directory_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.delattr(artifacts_module.os, "O_NOFOLLOW", raising=False)
    with pytest.raises(ArtifactCaptureError, match="cannot be secured"):
        artifacts_module._open_confined_directory(workspace / "artifacts", workspace)


def test_artifact_path_guards_reject_non_absolute_and_non_directory_parents(
    tmp_path: Path,
) -> None:
    with pytest.raises(ArtifactCaptureError, match="absolute"):
        artifacts_module._assert_directory_tree(Path("relative"), tmp_path)
    parent_file = tmp_path / "parent-file"
    parent_file.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ArtifactCaptureError, match="parent is not a directory"):
        artifacts_module._assert_directory_tree(tmp_path, parent_file / "child.txt")


def test_artifact_workspace_guards_handle_missing_file_symlink_and_noncanonical_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ArtifactCaptureError, match="absolute canonical"):
        artifacts_module._validated_workspace(Path("relative"))
    with pytest.raises(ArtifactCaptureError, match="absolute canonical"):
        artifacts_module._validated_workspace(tmp_path / ".." / tmp_path.name)
    with pytest.raises(ArtifactCaptureError, match="cannot be resolved"):
        artifacts_module._validated_workspace(tmp_path / "missing")
    file_path = tmp_path / "file"
    file_path.write_text("file", encoding="utf-8")
    with pytest.raises(ArtifactCaptureError, match="must be a directory"):
        artifacts_module._validated_workspace(file_path)
    outside = tmp_path.parent / "outside-artifact-workspace"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "workspace-link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArtifactCaptureError, match="contains a symlink"):
        artifacts_module._validated_workspace(link)

    original_resolve = Path.resolve

    def noncanonical_resolve(path: Path, *, strict: bool = False) -> Path:
        if path == tmp_path:
            return tmp_path / "canonical-alias"
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", noncanonical_resolve)
    with pytest.raises(ArtifactCaptureError, match="not canonical"):
        artifacts_module._validated_workspace(tmp_path)


def test_validate_artifact_path_translates_inspection_resolution_and_scope_races(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "artifact.txt"
    target.write_text("artifact", encoding="utf-8")
    original_lstat = Path.lstat

    calls = 0

    def inspection_failure(path: Path):
        nonlocal calls
        if path == target:
            calls += 1
            if calls == 2:
                raise OSError("inspection race")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", inspection_failure)
    with pytest.raises(ArtifactCaptureError, match="cannot be inspected"):
        validate_artifact_path(target, workspace)

    monkeypatch.setattr(Path, "lstat", original_lstat)
    original_resolve = Path.resolve

    def resolution_failure(path: Path, *, strict: bool = False) -> Path:
        if path == target:
            raise RuntimeError("resolution race")
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolution_failure)
    with pytest.raises(ArtifactCaptureError, match="cannot be resolved"):
        validate_artifact_path(target, workspace)

    outside = tmp_path / "outside-target"
    outside.mkdir()

    def resolution_escape(path: Path, *, strict: bool = False) -> Path:
        if path == target:
            return outside / "artifact.txt"
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolution_escape)
    with pytest.raises(ArtifactCaptureError, match="escapes workspace"):
        validate_artifact_path(target, workspace)


def test_validate_artifact_path_rejects_final_symlink_after_parent_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    target = workspace / "artifact.txt"
    target.symlink_to(outside)
    original_lstat = Path.lstat
    calls = 0

    def hide_symlink_on_parent_walk(path: Path):
        nonlocal calls
        if path == target:
            calls += 1
            if calls == 1:
                return original_lstat(outside)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", hide_symlink_on_parent_walk)
    with pytest.raises(ArtifactCaptureError, match="path is a symlink"):
        validate_artifact_path(target, workspace)


def test_confined_directory_guards_and_mkdir_safe_preserve_scope(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(ArtifactCaptureError, match="traversal"):
        artifacts_module._open_confined_directory(workspace / ".." / "escape", workspace)
    with pytest.raises(ArtifactCaptureError, match="escapes workspace"):
        artifacts_module._open_confined_directory(tmp_path / "outside", workspace)
    with pytest.raises(ArtifactCaptureError, match="escapes workspace"):
        artifacts_module._open_confined_directory(Path("relative"), workspace)
    created = workspace / "nested" / "artifacts"
    artifacts_module._mkdir_safe(created, workspace)
    assert created.is_dir()

    blocked = workspace / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ArtifactCaptureError, match="cannot be opened safely"):
        artifacts_module._open_confined_directory(blocked / "child", workspace)


def test_confined_directory_rolls_back_descriptor_when_fstat_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    original_fstat = artifacts_module.os.fstat

    def fail_fstat(descriptor: int):
        raise OSError("fstat race")

    monkeypatch.setattr(artifacts_module.os, "fstat", fail_fstat)
    with pytest.raises(ArtifactCaptureError, match="cannot be opened safely"):
        artifacts_module._open_confined_directory(workspace / "nested", workspace)
    monkeypatch.setattr(artifacts_module.os, "fstat", original_fstat)
    assert (workspace / "nested").is_dir()


def test_atomic_writer_stops_after_repeated_temporary_name_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    collision = tmp_path / ".artifact.txt.fixed.tmp"
    collision.write_bytes(b"reserved")

    class FixedUuid:
        hex = "fixed"

    monkeypatch.setattr(artifacts_module.uuid, "uuid4", lambda: FixedUuid())
    try:
        with pytest.raises(ArtifactCaptureError, match="temporary file could not be created"):
            artifacts_module._atomic_write_at(descriptor, "artifact.txt", b"payload")
    finally:
        os.close(descriptor)
    assert collision.read_bytes() == b"reserved"


def test_atomic_writer_translates_fsync_failure_and_removes_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    original_fsync = artifacts_module.os.fsync

    def fail_fsync(file_descriptor: int) -> None:
        raise OSError("fsync failure")

    monkeypatch.setattr(artifacts_module.os, "fsync", fail_fsync)
    try:
        with pytest.raises(ArtifactCaptureError, match="written atomically"):
            artifacts_module._atomic_write_at(descriptor, "artifact.txt", b"payload")
    finally:
        os.close(descriptor)
        monkeypatch.setattr(artifacts_module.os, "fsync", original_fsync)
    assert not (tmp_path / "artifact.txt").exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_capture_reports_artifact_directory_disappearance_after_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_dir = tmp_path / ".harness" / "phase4" / "artifacts"
    original_lstat = Path.lstat

    def disappear(path: Path):
        if path == artifact_dir:
            raise OSError("directory disappeared")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", disappear)
    with pytest.raises(ArtifactCaptureError, match="directory changed"):
        capture_host_response(
            _request(tmp_path),
            _host_result(),
            timestamp=1_700_000_010,
            max_bytes=128,
        )


def test_artifact_reader_rejects_invalid_bounds_before_path_access(tmp_path: Path) -> None:
    with pytest.raises(ArtifactCaptureError, match="byte bound is invalid"):
        read_artifact_bytes(tmp_path / "missing", tmp_path, max_bytes=0)


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        ({"schema_version": "P4-POLICY-2", "rules": []}, "unsupported"),
        ({"schema_version": "P4-POLICY-1", "rules": {}}, "must be a list"),
        (
            {"schema_version": "P4-POLICY-1", "rules": [], "extra": True},
            "unsupported top-level",
        ),
        ({"schema_version": "P4-POLICY-1", "rules": ["bad"]}, "rule must be an object"),
    ),
)
def test_policy_registry_rejects_unsupported_top_level_and_rule_shapes(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(Phase4PolicyError, match=message):
        ExecutionPolicyRegistry.from_mapping(payload)


def test_policy_registry_rejects_duplicate_identity_unknown_fields_and_bad_permissions() -> None:
    base = {
        "capability_id": "safe-pilot",
        "version": "0.1.0",
        "package_fingerprint": _DIGEST_A,
        "execution_approved": False,
        "reason": "inspection only",
    }
    duplicate = {"schema_version": "P4-POLICY-1", "rules": [base, dict(base)]}
    with pytest.raises(Phase4PolicyError, match="duplicate"):
        ExecutionPolicyRegistry.from_mapping(duplicate)
    unsupported = {"schema_version": "P4-POLICY-1", "rules": [{**base, "unknown": True}]}
    with pytest.raises(Phase4PolicyError, match="unsupported fields"):
        ExecutionPolicyRegistry.from_mapping(unsupported)
    bad_boolean = {
        "schema_version": "P4-POLICY-1",
        "rules": [{**base, "execution_approved": "false"}],
    }
    with pytest.raises(Phase4PolicyError, match="execution_approved"):
        ExecutionPolicyRegistry.from_mapping(bad_boolean)
    bad_mode = {
        "schema_version": "P4-POLICY-1",
        "rules": [{**base, "allowed_modes": ["NOT_A_MODE"]}],
    }
    with pytest.raises(ValueError, match="NOT_A_MODE"):
        ExecutionPolicyRegistry.from_mapping(bad_mode)


def test_policy_json_reader_rejects_nonfinite_deep_oversized_and_nonregular_inputs(
    tmp_path: Path,
) -> None:
    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"schema_version":"P4-POLICY-1","rules":[],"value":NaN}')
    with pytest.raises(Phase4PolicyError, match="cannot be read safely"):
        ExecutionPolicyRegistry.from_json(nonfinite)

    deep = tmp_path / "deep.json"
    depth = policy_module._MAX_POLICY_JSON_NESTING + 1
    deep.write_bytes(b"[" * depth + b"0" + b"]" * depth)
    with pytest.raises(Phase4PolicyError, match="nesting"):
        ExecutionPolicyRegistry.from_json(deep)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (policy_module._MAX_POLICY_BYTES + 1))
    with pytest.raises(Phase4PolicyError, match="exceeds its bound"):
        ExecutionPolicyRegistry.from_json(oversized)

    directory = tmp_path / "directory.json"
    directory.mkdir()
    with pytest.raises(Phase4PolicyError, match="unique regular file"):
        ExecutionPolicyRegistry.from_json(directory)

    symlink = tmp_path / "policy-link.json"
    symlink.symlink_to(nonfinite)
    with pytest.raises(Phase4PolicyError, match="cannot be read safely"):
        ExecutionPolicyRegistry.from_json(symlink)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"package_fingerprint": "bad"}, "package_fingerprint"),
        ({"version": "v1"}, "version"),
        ({"allowed_modes": (ExecutionMode.BLOCKED,)}, "BLOCKED"),
        ({"expected_artifact_types": ("NOPE",)}, "unsupported type"),
        ({"filesystem_mode": "WORKSPACE_WRITE"}, "requires"),
        ({"workspace_write_roots": ("../escape",)}, "safe relative"),
        ({"workspace_write_roots": ("/absolute",)}, "safe relative"),
        ({"reason": ""}, "reason"),
    ),
)
def test_pilot_rule_fail_closed_validation(kwargs: dict[str, object], message: str) -> None:
    values: dict[str, object] = {
        "capability_id": "safe-pilot",
        "version": "0.1.0",
        "package_fingerprint": _DIGEST_A,
    }
    values.update(kwargs)
    with pytest.raises(Phase4PolicyError, match=message):
        PilotRule(**values)


def test_pilot_rule_normalizes_collections_without_mutating_input() -> None:
    tools = ["reader", "reader"]
    rule = PilotRule(
        capability_id="safe-pilot",
        version="0.1.0",
        package_fingerprint=_DIGEST_A,
        allowed_tools=tools,
        filesystem_mode="WORKSPACE_WRITE",
        workspace_write_roots=("out", "out"),
    )
    tools.append("writer")
    assert rule.allowed_tools == ("reader",)
    assert rule.workspace_write_roots == ("out",)
    assert rule.filesystem_mode == "WORKSPACE_WRITE"


def test_workspace_and_skill_path_validation_fail_closed_for_scope_symlink_and_missing(
    tmp_path: Path,
) -> None:
    record, inventory, _, _ = _policy_fixture(tmp_path)
    assert policy_module._workspace_root(inventory, tmp_path)[0] == tmp_path.resolve()
    assert (
        policy_module._workspace_root(inventory, Path("relative"))[1]
        == "WORKSPACE_MUST_BE_ABSOLUTE"
    )
    missing = tmp_path / "missing-workspace"
    assert policy_module._workspace_root(inventory, missing)[1] == "WORKSPACE_MISSING"
    not_dir = tmp_path / "not-dir"
    not_dir.write_text("file", encoding="utf-8")
    assert policy_module._workspace_root(inventory, not_dir)[1] == "WORKSPACE_NOT_DIRECTORY"
    outside = tmp_path.parent / "outside-workspace"
    outside.mkdir(exist_ok=True)
    assert policy_module._workspace_root(inventory, outside)[1] == "WORKSPACE_OUTSIDE_PROJECT"
    link = tmp_path / "workspace-link"
    link.symlink_to(outside, target_is_directory=True)
    assert policy_module._workspace_root(inventory, link)[1] == "WORKSPACE_SYMLINK"
    assert policy_module._workspace_root(replace(inventory, roots=()), tmp_path)[1] == (
        "PROJECT_ROOT_UNAVAILABLE"
    )

    assert (
        policy_module._safe_skill_path(replace(record, skill_md=None))[1] == "SKILL_SOURCE_MISSING"
    )
    assert policy_module._safe_skill_path(replace(record, skill_md="../SKILL.md"))[1] == (
        "SKILL_SOURCE_ESCAPE"
    )
    relative_record = replace(record)
    object.__setattr__(relative_record, "path", "relative")
    assert policy_module._safe_skill_path(relative_record)[1] == "SKILL_SOURCE_ESCAPE"
    missing_package = replace(record, path=str(tmp_path / "missing-package"))
    assert policy_module._safe_skill_path(missing_package)[1] == "SKILL_SOURCE_UNAVAILABLE"
    skill_dir = Path(record.path) / "skill-dir"
    skill_dir.mkdir()
    assert policy_module._safe_skill_path(replace(record, skill_md="skill-dir"))[1] == (
        "SKILL_SOURCE_MISSING"
    )
    outside_skill = tmp_path / "outside-skill.md"
    outside_skill.write_text("outside", encoding="utf-8")
    (Path(record.path) / "skill-link.md").symlink_to(outside_skill)
    assert policy_module._safe_skill_path(replace(record, skill_md="skill-link.md"))[1] == (
        "SKILL_SOURCE_SYMLINK"
    )
    path, error = policy_module._safe_skill_path(record)
    assert error is None
    assert path == Path(record.path).resolve() / "SKILL.md"


def test_estimated_context_selects_then_omits_references_and_digest_is_recomputed(
    tmp_path: Path,
) -> None:
    record, inventory, resolution, policy = _policy_fixture(tmp_path)
    files = (
        PackageFile("SKILL.md", 4, _DIGEST_A.removeprefix("sha256:")),
        PackageFile("ref-a.md", 6, _DIGEST_B.removeprefix("sha256:")),
        PackageFile("ref-b.md", 6, _DIGEST_ZERO.removeprefix("sha256:")),
    )
    decorated = replace(record, files=files, references=("ref-a.md", "ref-b.md"))
    estimated, selected, omitted = policy_module._estimated_context(
        decorated, Phase4Budget(max_context_bytes=10)
    )
    assert (estimated, selected, omitted) == (10, ("ref-a.md",), ("ref-b.md",))

    preflight = build_preflight(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-PIPELINE-DIGEST",
        run_id="RUN-PIPELINE-DIGEST",
        task="Return one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.PREPARE_ONLY,
        budget=Phase4Budget(),
        now=1_700_000_000,
    )
    assert preflight_digest(preflight) == preflight.digest
    assert preflight.authorization is not None
    assert preflight.context is not None


@pytest.mark.parametrize(
    ("task", "criteria", "mode", "expected"),
    (
        ("", ("response is non-empty",), ExecutionMode.PREPARE_ONLY, "TASK_INVALID"),
        ("ok", (), ExecutionMode.PREPARE_ONLY, "ACCEPTANCE_CRITERIA_INVALID"),
        (
            "send password:secret",
            ("response is non-empty",),
            ExecutionMode.PREPARE_ONLY,
            "CREDENTIAL_INPUT_FORBIDDEN",
        ),
        ("ok", ("marker:\x00",), ExecutionMode.PREPARE_ONLY, "ACCEPTANCE_CRITERIA_INVALID"),
        ("ok", ("response is non-empty",), ExecutionMode.BLOCKED, "EXECUTION_MODE_BLOCKED"),
    ),
)
def test_preflight_rejects_invalid_input_before_authorization(
    tmp_path: Path,
    task: str,
    criteria: tuple[str, ...],
    mode: ExecutionMode,
    expected: str,
) -> None:
    record, inventory, resolution, policy = _policy_fixture(tmp_path)
    result = build_preflight(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-PIPELINE-INPUT",
        run_id="RUN-PIPELINE-INPUT",
        task=task,
        acceptance_criteria=criteria,
        workspace=tmp_path,
        mode=mode,
        budget=Phase4Budget(),
    )
    assert result.allowed is False
    assert expected in result.blockers
    assert result.authorization is None
    assert result.context is None


@pytest.mark.parametrize(
    ("record_change", "resolution_change", "expected"),
    (
        ({"status": "REJECTED"}, None, "CAPABILITY_STATUS_BLOCKED"),
        ({"kind": CapabilityKind.INVALID}, None, "CAPABILITY_KIND_BLOCKED"),
        ({"trust": "REJECTED"}, None, "CAPABILITY_TRUST_OR_COMPATIBILITY_BLOCKED"),
        ({"compatibility": "INCOMPATIBLE"}, None, "CAPABILITY_TRUST_OR_COMPATIBILITY_BLOCKED"),
        ({}, ResolutionStatus.MISSING, "CAPABILITY_NOT_RESOLVED"),
    ),
)
def test_preflight_preserves_resolution_scope_and_trust_blockers(
    tmp_path: Path,
    record_change: dict[str, object],
    resolution_change: ResolutionStatus | None,
    expected: str,
) -> None:
    record, inventory, resolution, policy = _policy_fixture(tmp_path)
    if record_change.get("status") == "REJECTED":
        record = replace(record, status=record.status.__class__.REJECTED)
    elif record_change.get("kind") is CapabilityKind.INVALID:
        record = replace(record, kind=CapabilityKind.INVALID)
    elif record_change.get("trust") == "REJECTED":
        record = replace(record, trust=replace(record.trust, level=TrustLevel.REJECTED))
    elif record_change.get("compatibility") == "INCOMPATIBLE":
        record = replace(
            record,
            compatibility=replace(record.compatibility, status=CompatibilityStatus.INCOMPATIBLE),
        )
    if resolution_change is not None:
        resolution = replace(resolution, status=resolution_change)

    result = build_preflight(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-PIPELINE-BLOCKERS",
        run_id="RUN-PIPELINE-BLOCKERS",
        task="Return one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.PREPARE_ONLY,
        budget=Phase4Budget(),
    )
    assert result.allowed is False
    assert expected in result.blockers
    assert result.authorization is None
    assert result.context is None


def test_preflight_blocks_missing_policy_workspace_skill_and_context_budget(
    tmp_path: Path,
) -> None:
    record, inventory, resolution, policy = _policy_fixture(tmp_path)
    no_policy = build_preflight(
        record,
        inventory,
        resolution,
        ExecutionPolicyRegistry(()),
        task_id="TASK-PIPELINE-NOPOLICY",
        run_id="RUN-PIPELINE-NOPOLICY",
        task="Return one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.PREPARE_ONLY,
        budget=Phase4Budget(),
    )
    assert "BLOCKED_EXECUTION_POLICY" in no_policy.blockers

    no_workspace = build_preflight(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-PIPELINE-NOWORKSPACE",
        run_id="RUN-PIPELINE-NOWORKSPACE",
        task="Return one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path / "missing",
        mode=ExecutionMode.PREPARE_ONLY,
        budget=Phase4Budget(),
    )
    assert "WORKSPACE_MISSING" in no_workspace.blockers

    no_skill = build_preflight(
        replace(record, skill_md=None),
        inventory,
        resolution,
        policy,
        task_id="TASK-PIPELINE-NOSKILL",
        run_id="RUN-PIPELINE-NOSKILL",
        task="Return one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.PREPARE_ONLY,
        budget=Phase4Budget(),
    )
    assert "SKILL_SOURCE_MISSING" in no_skill.blockers

    budget = build_preflight(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-PIPELINE-BUDGET",
        run_id="RUN-PIPELINE-BUDGET",
        task="Return one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.PREPARE_ONLY,
        budget=Phase4Budget(max_context_bytes=1),
    )
    assert "CONTEXT_BUDGET_EXCEEDED" in budget.blockers
    assert budget.authorization is None


def test_controlled_preflight_blocks_unsupported_capabilities_and_fingerprint_bindings(
    tmp_path: Path,
) -> None:
    record, inventory, resolution, _ = _policy_fixture(tmp_path)
    decorated = replace(
        record,
        dependencies=("dependency-x",),
        scripts=("SKILL.md",),
        manifest=replace(record.manifest, tools=("tool-x",), providers=("provider-x",)),
    )
    permissive = ExecutionPolicyRegistry(
        (
            _rule(
                record,
                allowed_tools=("tool-x",),
                allowed_providers=("provider-x",),
                allowed_side_effects=("write",),
                allow_network=True,
                allow_shell=True,
                allow_mcp=True,
                allow_credentials=True,
            ),
        )
    )
    blocked = build_preflight(
        decorated,
        inventory,
        resolution,
        permissive,
        task_id="TASK-PIPELINE-UNSUPPORTED",
        run_id="RUN-PIPELINE-UNSUPPORTED",
        task="Return one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert blocked.allowed is False
    assert {
        "FORBIDDEN_SCRIPT",
        "DEPENDENCY_NOT_INDEPENDENTLY_APPROVED",
        "HOST_TOOL_POLICY_UNSUPPORTED",
        "HOST_PROVIDER_POLICY_UNSUPPORTED",
        "HOST_SIDE_EFFECT_POLICY_UNSUPPORTED",
        "HOST_NETWORK_POLICY_UNSUPPORTED",
        "HOST_SHELL_POLICY_UNSUPPORTED",
        "HOST_MCP_POLICY_UNSUPPORTED",
        "HOST_CREDENTIAL_POLICY_UNSUPPORTED",
    }.issubset(blocked.blockers)

    missing_bindings = ExecutionPolicyRegistry(
        (
            _rule(
                record,
                host_executable_digest=None,
                host_interpreter_digest=None,
            ),
        )
    )
    result = build_preflight(
        record,
        inventory,
        resolution,
        missing_bindings,
        task_id="TASK-PIPELINE-BINDINGS",
        run_id="RUN-PIPELINE-BINDINGS",
        task="Return one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    assert "HOST_EXECUTABLE_NOT_BOUND" in result.blockers
    assert "HOST_INTERPRETER_NOT_BOUND" in result.blockers


def test_verification_success_binds_artifact_acceptance_and_evidence(tmp_path: Path) -> None:
    request, result, artifact = _capture(tmp_path)
    verified = verification_module.verify_host_result(
        request,
        result,
        (artifact,),
        evidence_refs=(f"receipt://{request.invocation_id}", "event://1"),
    )
    assert verified.status == "VERIFIED"
    assert verified.artifact_refs == (artifact.artifact_id,)
    assert "REQUEST_DIGEST_BOUND" in verified.checks
    assert "ARTIFACT_INTEGRITY:" + artifact.artifact_id in verified.checks
    assert "RECEIPT_REFERENCE_CORRELATED" in verified.checks
    assert verified.digest == digest_payload(
        {
            "status": verified.status,
            "acceptance_criteria": verified.acceptance_criteria,
            "artifact_refs": verified.artifact_refs,
            "evidence_refs": verified.evidence_refs,
            "checks": verified.checks,
            "reason": verified.reason,
            "request_digest": verified.request_digest,
            "host_executable_digest": verified.host_executable_digest,
            "host_interpreter_digest": verified.host_interpreter_digest,
        }
    )


@pytest.mark.parametrize(
    ("status", "execution_observed", "error_fragment"),
    (
        (InvocationResultStatus.SUCCESS, False, "completion was not observed"),
        (InvocationResultStatus.PARTIAL, True, "host result is partial"),
        (InvocationResultStatus.TIMED_OUT, False, "timed out"),
        (InvocationResultStatus.CANCELLED, False, "cancelled"),
        (InvocationResultStatus.UNKNOWN, False, "status is UNKNOWN"),
    ),
)
def test_verification_stops_on_terminal_or_unobserved_host_results(
    tmp_path: Path,
    status: InvocationResultStatus,
    execution_observed: bool,
    error_fragment: str,
) -> None:
    request, _, artifact = _capture(tmp_path)
    result = _host_result(
        status,
        execution_observed=execution_observed,
        error_code=status.value,
    )
    verified = verification_module.verify_host_result(
        request,
        result,
        (artifact,),
        evidence_refs=(f"receipt://{request.invocation_id}",),
    )
    assert verified.status == "FAILED"
    assert error_fragment in verified.reason
    assert verified.artifact_refs == (artifact.artifact_id,)


def test_verification_reports_missing_invalid_and_mismatched_artifacts(tmp_path: Path) -> None:
    request, result, artifact = _capture(tmp_path)
    wrong = replace(
        artifact,
        location=str(tmp_path / "missing-artifact.txt"),
        digest=_DIGEST_ZERO,
        size_bytes=999,
        artifact_type=ArtifactType.FILE,
        producer_capability="other-capability",
        invocation_id="other-invocation",
    )
    failed = verification_module.verify_host_result(
        request,
        result,
        (wrong,),
        evidence_refs=("event://not-a-receipt",),
    )
    assert failed.status == "FAILED"
    assert "unavailable or outside workspace" in failed.reason
    assert "receipt reference is not correlated" in failed.reason

    tampered = replace(artifact, digest=_DIGEST_ZERO, size_bytes=999)
    failed = verification_module.verify_host_result(
        request,
        result,
        (tampered, artifact),
        evidence_refs=(),
    )
    assert failed.status == "FAILED"
    assert "exactly one host-response artifact" in failed.reason
    assert "artifact digest mismatch" in failed.reason
    assert "artifact size mismatch" in failed.reason
    assert "verification evidence refs are missing" in failed.reason


def test_verification_requires_host_provenance_and_acceptance_markers(tmp_path: Path) -> None:
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
    request = replace(request, authorization=authorization)
    result = _host_result(
        host_executable_digest=_DIGEST_A,
        host_executable_path="/bin/codex",
        host_command=("/bin/codex",),
        host_interpreter_digest=_DIGEST_B,
        host_interpreter_path="/bin/python",
    )
    object.__setattr__(result, "host_interpreter_path", None)
    artifact = capture_host_response(request, result, timestamp=1_700_000_010, max_bytes=128)
    assert artifact is not None
    request = replace(
        request,
        acceptance_criteria=("marker: MUST_HAVE", "review by operator"),
        context=replace(
            request.context,
            acceptance_criteria=("marker: MUST_HAVE", "review by operator"),
        ),
    )
    failed = verification_module.verify_host_result(
        request,
        result,
        (artifact,),
        evidence_refs=(f"receipt://{request.invocation_id}",),
    )
    assert failed.status == "FAILED"
    assert "interpreter provenance is missing" in failed.reason
    assert "acceptance failed: marker: MUST_HAVE" in failed.reason
    assert "acceptance requires human or capability review" in failed.reason


def _successful_outcome(tmp_path: Path):
    record, inventory, resolution, policy = _fixture(tmp_path)
    engine = InvocationEngine(FakeHost())
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-PIPELINE-RECEIPT",
        run_id="RUN-PIPELINE-RECEIPT",
        task="Return a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(),
    )
    outcome = engine.execute_prepared(prepared)
    assert outcome.status is InvocationResultStatus.SUCCESS
    assert prepared.request is not None
    assert outcome.verification is not None
    assert outcome.host_result is not None
    return outcome, prepared.request


def test_receipt_binding_accepts_complete_pipeline_receipt(tmp_path: Path) -> None:
    outcome, request = _successful_outcome(tmp_path)
    assert outcome.verification is not None
    assert outcome.host_result is not None
    assert (
        verification_module.validate_receipt_binding(
            outcome.receipt,
            request,
            outcome.host_result,
            outcome.artifacts,
            outcome.verification,
            expected_status=InvocationResultStatus.SUCCESS,
        )
        == ()
    )
    assert invocation_receipt_digest(outcome.receipt) == outcome.receipt.receipt_digest


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    (
        ("invocation_id", "other", "invocation binding"),
        ("mode", ExecutionMode.PREPARE_ONLY, "mode binding"),
        ("status", InvocationResultStatus.FAILURE, "status binding"),
        ("capability_id", "other", "capability binding"),
        ("capability_version", "9.9.9", "version binding"),
        ("package_fingerprint", _DIGEST_ZERO, "fingerprint binding"),
        ("authorization_id", "AUTH-OTHER", "authorization ID"),
        ("authorization_digest", _DIGEST_ZERO, "authorization digest"),
        ("context_digest", _DIGEST_ZERO, "context digest"),
        ("request_digest", _DIGEST_ZERO, "request digest"),
        ("host_invoked", False, "invocation observation"),
        ("host_event_count", 99, "event count"),
        ("host_event_digest", _DIGEST_ZERO, "event digest"),
        ("result_digest", _DIGEST_ZERO, "result digest"),
        ("artifact_refs", (), "artifact references"),
        ("verification_refs", (), "verification references"),
        ("receipt_digest", _DIGEST_ZERO, "self-digest"),
    ),
)
def test_receipt_binding_rejects_tampered_binding_fields(
    tmp_path: Path, field: str, value: object, fragment: str
) -> None:
    outcome, request = _successful_outcome(tmp_path)
    assert outcome.verification is not None
    assert outcome.host_result is not None
    tampered = replace(outcome.receipt, **{field: value})
    failures = verification_module.validate_receipt_binding(
        tampered,
        request,
        outcome.host_result,
        outcome.artifacts,
        outcome.verification,
        expected_status=InvocationResultStatus.SUCCESS,
    )
    assert any(fragment in failure for failure in failures)


def test_receipt_binding_rejects_provenance_and_protocol_count_tampering(tmp_path: Path) -> None:
    outcome, request = _successful_outcome(tmp_path)
    assert outcome.verification is not None
    assert outcome.host_result is not None
    result = replace(
        outcome.host_result,
        host_command=("/bin/other",),
        host_executable_path="/bin/other",
        host_executable_digest=_DIGEST_ZERO,
    )
    failures = verification_module.validate_receipt_binding(
        outcome.receipt,
        request,
        result,
        outcome.artifacts,
        outcome.verification,
        expected_status=InvocationResultStatus.SUCCESS,
    )
    assert "receipt host executable fingerprint mismatch" in failures
    assert "receipt host executable path mismatch" in failures
    assert "receipt host command mismatch" in failures
    assert "verification host executable digest mismatch" in failures

    transcript = ProtocolMessageObservation(
        sequence=0,
        method="turn/completed",
        message_kind="notification",
        has_id=False,
        has_error=False,
    )
    transcript_result = replace(
        outcome.host_result,
        protocol_message_count=1,
        protocol_messages=(transcript,),
    )
    protocol_receipt = replace(outcome.receipt, host_event_count=1)
    protocol_failures = verification_module.validate_receipt_binding(
        protocol_receipt,
        request,
        transcript_result,
        outcome.artifacts,
        outcome.verification,
        expected_status=InvocationResultStatus.SUCCESS,
    )
    assert "receipt host event count mismatch" in protocol_failures


def _cli_args(project_root: Path, **overrides: object) -> Namespace:
    values: dict[str, object] = {
        "project_root": project_root,
        "json_output": True,
        "capability": "safe-pilot",
        "task": "Return one bounded response.",
        "acceptance": ["response is non-empty"],
        "dry_run": True,
        "prepare_only": False,
        "controlled_real": False,
        "workspace": None,
        "policy": None,
        "confirm_fingerprint": None,
        "timeout": 60,
        "evidence_dir": None,
        "explain": False,
    }
    values.update(overrides)
    return Namespace(**values)


def test_cli_helpers_preserve_modes_scope_and_human_diagnostics(tmp_path: Path) -> None:
    assert cli_module._mode(_cli_args(tmp_path, dry_run=True)) is ExecutionMode.DRY_RUN
    assert (
        cli_module._mode(_cli_args(tmp_path, dry_run=False, prepare_only=True))
        is ExecutionMode.PREPARE_ONLY
    )
    assert (
        cli_module._mode(_cli_args(tmp_path, dry_run=False, controlled_real=True))
        is ExecutionMode.CONTROLLED_REAL
    )
    assert (
        cli_module._mode(
            _cli_args(tmp_path, dry_run=False, prepare_only=False, controlled_real=False)
        )
        is ExecutionMode.BLOCKED
    )
    assert cli_module._sequence(["x"]) == ("x",)
    assert cli_module._sequence("not-a-sequence") == ()
    human = cli_module._human_output(
        {
            "mode": "PREPARE_ONLY",
            "status": "BLOCKED",
            "host_invoked": False,
            "blockers": ["SCOPE_BLOCKED"],
            "limitations": ["evidence incomplete"],
        }
    )
    assert "NO HOST EXECUTION" in human
    assert "SCOPE_BLOCKED" in human
    assert "evidence incomplete" in human

    nested = tmp_path / "nested"
    nested.mkdir()
    assert cli_module._project_path(tmp_path, nested, "nested") == nested.resolve()
    with pytest.raises(ValueError, match="inside project root"):
        cli_module._project_path(tmp_path, tmp_path.parent, "outside")
    link = tmp_path / "link"
    link.symlink_to(nested, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        cli_module._project_path(tmp_path, link, "link")
    with pytest.raises(ValueError, match="unavailable"):
        cli_module._project_path(tmp_path, tmp_path / "missing", "missing")


@pytest.mark.parametrize(
    ("workspace_name", "expected"),
    (
        ("missing", "WORKSPACE_UNAVAILABLE"),
        ("outside", "WORKSPACE_OUTSIDE_PROJECT"),
        ("file", "WORKSPACE_NOT_DIRECTORY"),
        ("link", "WORKSPACE_SYMLINK"),
    ),
)
def test_cli_run_invoke_returns_blocked_payload_for_invalid_workspace(
    tmp_path: Path, workspace_name: str, expected: str
) -> None:
    project = _cli_project(tmp_path)
    outside = project.parent / "outside-cli"
    outside.mkdir(exist_ok=True)
    (project / "outside").mkdir(exist_ok=True)
    (project / "file").write_text("not a directory", encoding="utf-8")
    (project / "link").symlink_to(outside, target_is_directory=True)
    candidates = {
        "missing": project / "missing",
        "outside": outside,
        "file": project / "file",
        "link": project / "link",
    }
    payload = cli_module._run_invoke(_cli_args(project, workspace=candidates[workspace_name]))
    assert payload["status"] == InvocationResultStatus.BLOCKED.value
    assert expected in payload["blockers"]
    assert payload["host_invoked"] is False


def test_cli_run_invoke_blocks_timeout_missing_capability_and_invalid_evidence_scope(
    tmp_path: Path,
) -> None:
    project = _cli_project(tmp_path)
    timeout = cli_module._run_invoke(_cli_args(project, timeout=0))
    assert timeout["blockers"] == ["TIMEOUT_INVALID"]
    assert timeout["host_invoked"] is False

    missing = cli_module._run_invoke(_cli_args(project, capability="missing-capability"))
    assert missing["blockers"] == ["CAPABILITY_NOT_RESOLVED"]
    assert missing["host_invoked"] is False

    outside_evidence = project.parent / "evidence-outside"
    outside_evidence.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match="inside project root"):
        cli_module._run_invoke(_cli_args(project, evidence_dir=outside_evidence))


def test_cli_load_policy_and_main_convert_unrepresentable_requests_to_blocked_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _cli_project(tmp_path)
    original_project_path = cli_module._project_path
    monkeypatch.setattr(
        cli_module,
        "_project_path",
        lambda project_root, candidate, label: project_root / "missing-policy.json",
    )
    missing = cli_module._load_policy(project, project / "missing-policy.json")
    assert missing.rules == ()
    monkeypatch.setattr(cli_module, "_project_path", original_project_path)
    invalid = project / "invalid-policy.json"
    invalid.write_text("[]", encoding="utf-8")
    with pytest.raises(Phase4PolicyError):
        cli_module._load_policy(project, invalid)

    monkeypatch.setattr(
        cli_module,
        "_run_invoke",
        lambda arguments: (_ for _ in ()).throw(ValueError("bad request")),
    )
    exit_code = cli_module.main(
        [
            "invoke",
            "safe-pilot",
            "--task",
            "Return one bounded response.",
            "--dry-run",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "BLOCKED"
    assert payload["host_invoked"] is False
    assert payload["message"] == "Phase 4 request could not be represented safely"


def test_preflight_digest_changes_when_authorization_or_context_binding_changes(
    tmp_path: Path,
) -> None:
    record, inventory, resolution, policy = _policy_fixture(tmp_path)
    preflight = build_preflight(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-PIPELINE-DIGEST-2",
        run_id="RUN-PIPELINE-DIGEST-2",
        task="Return one bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.PREPARE_ONLY,
        budget=Phase4Budget(),
        now=1_700_000_000,
    )
    assert preflight.allowed
    assert preflight.authorization is not None
    assert preflight.context is not None
    altered_auth = replace(preflight.authorization, reason="changed reason")
    altered_context = replace(preflight.context, acceptance_criteria=("marker: x",))
    assert (
        policy_module._compute_preflight_digest(
            allowed=True,
            mode=preflight.mode,
            blockers=preflight.blockers,
            warnings=preflight.warnings,
            authorization=altered_auth,
            context=preflight.context,
            workspace=tmp_path,
        )
        != preflight.digest
    )
    assert (
        policy_module._compute_preflight_digest(
            allowed=True,
            mode=preflight.mode,
            blockers=preflight.blockers,
            warnings=preflight.warnings,
            authorization=preflight.authorization,
            context=altered_context,
            workspace=tmp_path,
        )
        != preflight.digest
    )
    assert stable_digest_payload(preflight.authorization, workspace=tmp_path)
