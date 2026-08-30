from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import harness_kernel.phase7_backend as backend
from harness_kernel.phase3_models import Phase3Limits, WalkResult
from harness_kernel.phase3_paths import PathSafetyError
from harness_kernel.phase7_backend import (
    BACKEND_CAPABILITY_ID,
    BackendEvidenceBindingReport,
    BackendPackageContractError,
    BackendPackageReport,
    WorkspaceDeltaReport,
    package_fingerprint,
    snapshot_workspace,
    validate_backend_evidence_binding,
    validate_backend_package,
    validate_workspace_delta,
)

PROJECT_ROOT = Path(__file__).parents[2]
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / BACKEND_CAPABILITY_ID
ZERO = "sha256:" + "0" * 64
ONE = "sha256:" + "1" * 64
TWO = "sha256:" + "2" * 64


def _has(errors: tuple[str, ...], expected: str) -> None:
    assert any(expected in error for error in errors), (expected, errors)


def _valid_evidence(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task_id": "TASK-P7-BOUNDARY-1",
        "package_fingerprint": ONE,
        "artifact_digest": TWO,
        "criteria_digest": ZERO,
        "freshness": "FRESH",
        "status": "VERIFIED",
        "authority": "VERIFIER",
        "self_approval": False,
        "observed_at": datetime.now(UTC).isoformat(),
        "evidence_digests": {"tests": ONE},
    }
    value.update(updates)
    return value


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("package_fingerprint", "invalid", "EVIDENCE_PACKAGE_FINGERPRINT_INVALID"),
        ("artifact_digest", "invalid", "EVIDENCE_ARTIFACT_DIGEST_INVALID"),
        ("criteria_digest", "invalid", "EVIDENCE_CRITERIA_DIGEST_INVALID"),
        ("expected_task_id", "", "EXPECTED_EVIDENCE_TASK_ID_INVALID"),
        (
            "expected_package_fingerprint",
            "invalid",
            "EXPECTED_EVIDENCE_PACKAGE_FINGERPRINT_INVALID",
        ),
        ("expected_artifact_digest", "invalid", "EXPECTED_EVIDENCE_ARTIFACT_DIGEST_INVALID"),
        ("expected_criteria_digest", "invalid", "EXPECTED_EVIDENCE_CRITERIA_DIGEST_INVALID"),
        ("expected_authority", 1, "EXPECTED_EVIDENCE_AUTHORITY_INVALID"),
    ],
)
def test_evidence_binding_rejects_invalid_claims_and_expected_identity(
    field: str, value: object, expected: str
) -> None:
    evidence = _valid_evidence(**({field: value} if not field.startswith("expected_") else {}))
    kwargs: dict[str, object] = {
        "expected_task_id": "TASK-P7-BOUNDARY-1",
        "expected_package_fingerprint": ONE,
        "expected_artifact_digest": TWO,
        "expected_criteria_digest": ZERO,
        "expected_authority": "VERIFIER",
    }
    if field.startswith("expected_"):
        kwargs[field] = value
    report = validate_backend_evidence_binding(evidence, **kwargs)  # type: ignore[arg-type]
    _has(report.blockers, expected)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("task_id", "OTHER", "EVIDENCE_TASK_ID_MISMATCH"),
        ("package_fingerprint", TWO, "EVIDENCE_PACKAGE_FINGERPRINT_MISMATCH"),
        ("artifact_digest", ONE, "EVIDENCE_ARTIFACT_DIGEST_MISMATCH"),
        ("criteria_digest", ONE, "EVIDENCE_CRITERIA_DIGEST_MISMATCH"),
        ("authority", "BUILDER", "EVIDENCE_AUTHORITY_MISMATCH"),
    ],
)
def test_evidence_binding_rejects_identity_mismatches(
    field: str, value: object, expected: str
) -> None:
    evidence = _valid_evidence(**{field: value})
    report = validate_backend_evidence_binding(
        evidence,
        expected_task_id="TASK-P7-BOUNDARY-1",
        expected_package_fingerprint=ONE,
        expected_artifact_digest=TWO,
        expected_criteria_digest=ZERO,
        expected_authority="VERIFIER",
    )
    _has(report.blockers, expected)


@pytest.mark.parametrize(
    ("observed_at", "expected"),
    [
        (10**100, "EVIDENCE_TIMESTAMP_INVALID"),
        ("not-a-timestamp", "EVIDENCE_TIMESTAMP_INVALID"),
        ("2026-08-30T12:00:00", "EVIDENCE_TIMESTAMP_INVALID_OR_FUTURE"),
        (datetime.now(UTC).isoformat(), "EVIDENCE_TIMESTAMP_IN_FUTURE"),
    ],
)
def test_evidence_binding_rejects_invalid_future_and_naive_timestamps(
    observed_at: object, expected: str
) -> None:
    if expected == "EVIDENCE_TIMESTAMP_IN_FUTURE":
        observed_at = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
    report = validate_backend_evidence_binding(
        _valid_evidence(observed_at=observed_at),
        expected_task_id="TASK-P7-BOUNDARY-1",
        expected_package_fingerprint=ONE,
        expected_artifact_digest=TWO,
        expected_criteria_digest=ZERO,
        expected_authority="VERIFIER",
    )
    _has(report.blockers, expected)


def test_evidence_binding_rejects_stale_missing_and_invalid_catalog_entries() -> None:
    stale = validate_backend_evidence_binding(
        _valid_evidence(observed_at=1),
        expected_task_id="TASK-P7-BOUNDARY-1",
        expected_package_fingerprint=ONE,
        expected_artifact_digest=TWO,
        expected_criteria_digest=ZERO,
        expected_authority="VERIFIER",
        max_age_seconds=0,
    )
    _has(stale.blockers, "EVIDENCE_TIMESTAMP_STALE")

    missing = validate_backend_evidence_binding(
        _valid_evidence(observed_at=None, evidence_digests={}),
        expected_task_id="TASK-P7-BOUNDARY-1",
        expected_package_fingerprint=ONE,
        expected_artifact_digest=TWO,
        expected_criteria_digest=ZERO,
        expected_authority="VERIFIER",
        max_age_seconds=-1,
    )
    _has(missing.blockers, "EVIDENCE_TIMESTAMP_MISSING")
    _has(missing.blockers, "EVIDENCE_MAX_AGE_INVALID")
    _has(missing.blockers, "EVIDENCE_DIGESTS_MISSING")

    invalid = validate_backend_evidence_binding(
        _valid_evidence(evidence_digests={"": "invalid"}),
        expected_task_id="TASK-P7-BOUNDARY-1",
        expected_package_fingerprint=ONE,
        expected_artifact_digest=TWO,
        expected_criteria_digest=ZERO,
        expected_authority="VERIFIER",
    )
    _has(invalid.blockers, "EVIDENCE_DIGEST_ENTRY_INVALID")


def test_evidence_binding_report_rejects_invalid_constructor_values() -> None:
    cases = (
        ("ok", "not-bool", "ok must be boolean"),
        ("task_id", "", "task_id must be non-empty"),
        ("package_fingerprint", "invalid", "package_fingerprint must be a sha256 digest"),
        ("artifact_digest", "invalid", "artifact_digest must be a sha256 digest"),
        ("criteria_digest", "invalid", "criteria_digest must be a sha256 digest"),
        ("evidence_count", True, "evidence_count must be a non-negative integer"),
    )
    for field, value, expected in cases:
        kwargs: dict[str, object] = {
            "ok": True,
            "task_id": "task",
            "package_fingerprint": ONE,
            "artifact_digest": TWO,
            "criteria_digest": ZERO,
            "evidence_count": 1,
        }
        kwargs[field] = value
        with pytest.raises(ValueError, match=expected):
            BackendEvidenceBindingReport(**kwargs)  # type: ignore[arg-type]


def _minimal_package(
    path: Path, *, manifest: bytes | None = b"{}", skill: bytes | None = None
) -> None:
    path.mkdir()
    if manifest is not None:
        (path / "manifest.json").write_bytes(manifest)
    if skill is not None:
        (path / "SKILL.md").write_bytes(skill)


def _validate_tmp_package(path: Path, **kwargs: object) -> BackendPackageReport:
    fingerprint = package_fingerprint(path)
    return validate_backend_package(
        path,
        expected_package_path=path,
        expected_fingerprint=fingerprint,
        **kwargs,
    )  # type: ignore[arg-type]


def test_package_path_authentication_rejects_all_basic_aliases(tmp_path: Path) -> None:
    package = tmp_path / "package"
    _minimal_package(package)
    with pytest.raises(BackendPackageContractError, match="absolute"):
        backend._safe_package_path("relative")
    with pytest.raises(BackendPackageContractError, match="traversal"):
        backend._safe_package_path(tmp_path / ".." / package.name)
    with pytest.raises(BackendPackageContractError, match="missing"):
        backend._safe_package_path(tmp_path / "missing")
    regular = tmp_path / "regular"
    regular.write_text("not a directory", encoding="utf-8")
    with pytest.raises(BackendPackageContractError, match="not a directory"):
        backend._safe_package_path(regular)
    alias = tmp_path / "alias"
    alias.symlink_to(package, target_is_directory=True)
    with pytest.raises(BackendPackageContractError, match="symlink"):
        backend._safe_package_path(alias)


def test_package_files_fail_closed_on_walk_entries_and_observation_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    limits = Phase3Limits()

    monkeypatch.setattr(
        backend, "bounded_walk", lambda *_args: (_ for _ in ()).throw(PathSafetyError("walk"))
    )
    with pytest.raises(BackendPackageContractError, match="walked safely"):
        backend._package_files(package, limits)

    monkeypatch.setattr(backend, "bounded_walk", lambda *_args: WalkResult(("a",), errors=("bad",)))
    with pytest.raises(BackendPackageContractError, match="unsafe entry"):
        backend._package_files(package, limits)
    monkeypatch.setattr(
        backend, "bounded_walk", lambda *_args: WalkResult(("a",), unsafe_paths=("a",))
    )
    with pytest.raises(BackendPackageContractError, match="symlink or alias"):
        backend._package_files(package, limits)
    monkeypatch.setattr(backend, "bounded_walk", lambda *_args: WalkResult(()))
    with pytest.raises(BackendPackageContractError, match="no files"):
        backend._package_files(package, limits)
    monkeypatch.setattr(
        backend,
        "bounded_walk",
        lambda *_args: WalkResult(tuple(f"file-{index}" for index in range(257))),
    )
    with pytest.raises(BackendPackageContractError, match="file count"):
        backend._package_files(package, limits)

    monkeypatch.setattr(backend, "bounded_walk", lambda *_args: WalkResult(("a",)))
    monkeypatch.setattr(
        backend,
        "bounded_file_metadata",
        lambda *_args: (
            max(limits.max_skill_bytes, limits.max_manifest_bytes, limits.max_reference_bytes) + 1,
            False,
        ),
    )
    with pytest.raises(BackendPackageContractError, match="exceeds its bound"):
        backend._package_files(package, limits)

    monkeypatch.setattr(
        backend,
        "bounded_file_metadata",
        lambda *_args: (_ for _ in ()).throw(PathSafetyError("metadata")),
    )
    with pytest.raises(BackendPackageContractError, match="file is unsafe"):
        backend._package_files(package, limits)

    values = iter(((1, False), (2, False)))
    monkeypatch.setattr(backend, "bounded_file_metadata", lambda *_args: next(values))
    monkeypatch.setattr(backend, "read_bounded_file", lambda *_args, **_kwargs: b"x")
    with pytest.raises(BackendPackageContractError, match="changed during inspection"):
        backend._package_files(package, limits)


def test_validate_package_reports_identity_and_catalog_failures(tmp_path: Path) -> None:
    package = tmp_path / "package"
    _minimal_package(package, manifest=None, skill=b"---\nname: other\n---\n")
    fingerprint = package_fingerprint(package)
    report = validate_backend_package(
        package,
        expected_package_path=object(),  # type: ignore[arg-type]
        expected_fingerprint="invalid",
    )
    _has(report.blockers, "EXPECTED_PACKAGE_PATH_INVALID")
    _has(report.blockers, "EXPECTED_PACKAGE_FINGERPRINT_INVALID")
    _has(report.blockers, "MANIFEST_MISSING")

    other = tmp_path / "other"
    other.mkdir()
    report = validate_backend_package(
        package,
        expected_package_path=other,
        expected_fingerprint=fingerprint,
    )
    _has(report.blockers, "PACKAGE_PATH_IDENTITY_MISMATCH")

    malformed = tmp_path / "malformed"
    _minimal_package(malformed, manifest=b"not-json")
    report = _validate_tmp_package(malformed)
    _has(report.blockers, "invalid JSON")


def test_validate_package_reports_skill_digest_and_executable_failures(tmp_path: Path) -> None:
    package = tmp_path / "package"
    _minimal_package(
        package,
        manifest=json.dumps({"package_fingerprint": ONE}).encode(),
        skill=b"---\nname: wrong\nversion: 9.0.0\nprimary_type: TOOL\n---\n",
    )
    executable = package / "run.sh"
    executable.write_text("echo unsafe\n", encoding="utf-8")
    executable.chmod(executable.stat().st_mode | 0o111)
    report = _validate_tmp_package(package)
    _has(report.blockers, "PACKAGE_FINGERPRINT_DECLARATION_MISMATCH")
    _has(report.blockers, "SKILL_IDENTITY_MISMATCH")
    _has(report.blockers, "SKILL_VERSION_MISMATCH")
    _has(report.blockers, "SKILL_PRIMARY_TYPE_MISMATCH")
    _has(report.blockers, "EVAL_CATALOG_MISSING")
    _has(report.blockers, "BENCHMARK_CATALOG_MISSING")
    _has(report.blockers, "EXECUTABLE_PACKAGE_ENTRY")

    invalid_skill = tmp_path / "invalid-skill"
    _minimal_package(invalid_skill, manifest=b"{}", skill=b"\xff")
    report = _validate_tmp_package(invalid_skill)
    _has(report.blockers, "SKILL_INVALID")


def test_dataclass_reports_reject_invalid_values() -> None:
    package_kwargs: dict[str, object] = {
        "ok": True,
        "capability_id": "id",
        "version": "0.1.0",
        "primary_type": "SPECIALIST",
        "role": "SPECIALIST",
        "scenario_count": 1,
        "package_fingerprint": ONE,
        "forbidden_boundaries": (),
    }
    for field, value, expected in (
        ("ok", "yes", "ok must be boolean"),
        ("package_fingerprint", "bad", "package_fingerprint must be a sha256 digest"),
        ("manifest_fingerprint", "bad", "manifest_fingerprint must be a sha256 digest"),
        ("scenario_count", True, "scenario_count must be a non-negative integer"),
        ("benchmark_count", True, "benchmark_count must be a non-negative integer"),
    ):
        kwargs = dict(package_kwargs)
        kwargs[field] = value
        with pytest.raises(ValueError, match=expected):
            BackendPackageReport(**kwargs)  # type: ignore[arg-type]

    delta_kwargs: dict[str, object] = {
        "ok": True,
        "changed_paths": (),
        "unauthorized_paths": (),
    }
    for field, value, expected in (
        ("ok", "yes", "ok must be boolean"),
        ("changed_paths", ("\x00",), "contains an invalid"),
        ("digest", "bad", "digest must be a sha256 digest"),
    ):
        kwargs = dict(delta_kwargs)
        kwargs[field] = value
        with pytest.raises(ValueError, match=expected):
            WorkspaceDeltaReport(**kwargs)  # type: ignore[arg-type]


def test_workspace_guards_reject_aliases_and_protected_roots(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(BackendPackageContractError, match="workspace must be absolute"):
        backend._safe_workspace("relative")
    with pytest.raises(BackendPackageContractError, match="unavailable"):
        backend._safe_workspace(tmp_path / "missing")
    regular = tmp_path / "regular"
    regular.write_text("file", encoding="utf-8")
    with pytest.raises(BackendPackageContractError, match="regular directory"):
        backend._safe_workspace(regular)
    alias = tmp_path / "workspace-alias"
    alias.symlink_to(workspace, target_is_directory=True)
    with pytest.raises(BackendPackageContractError, match="symlink"):
        backend._safe_workspace(alias)

    for root, message in (
        ("relative", "absolute"),
        (tmp_path / "missing", "unavailable"),
        (regular, "directory"),
    ):
        with pytest.raises(BackendPackageContractError, match=message):
            backend._safe_allowed_root(root, workspace)
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(BackendPackageContractError, match="escapes"):
        backend._safe_allowed_root(outside, workspace)
    agent = workspace / ".agent"
    agent.mkdir()
    with pytest.raises(BackendPackageContractError, match="protected"):
        backend._safe_allowed_root(agent, workspace)
    capabilities = workspace / ".harness" / "capabilities"
    capabilities.mkdir(parents=True)
    with pytest.raises(BackendPackageContractError, match="protected"):
        backend._safe_allowed_root(capabilities, workspace)


def test_declared_paths_and_before_values_are_normalized_fail_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(BackendPackageContractError, match="absolute"):
        backend._safe_declared_path("relative")
    with pytest.raises(BackendPackageContractError, match="traversal"):
        backend._safe_declared_path("../escape", workspace=workspace)
    normal = backend._safe_declared_path("app/output.py", workspace=workspace)
    assert normal == workspace / "app/output.py"

    payload = b"content"
    digest = backend.digest_bytes(payload)
    assert backend._before_matches(payload, payload, digest) is True
    assert backend._before_matches(b"other", payload, digest) is False
    assert backend._before_matches("content", payload, digest) is True
    assert backend._before_matches(digest, payload, digest) is True
    assert backend._before_matches("other", payload, digest) is False
    assert backend._before_matches({"sha256": digest}, payload, digest) is True
    assert backend._before_matches({"digest": "other"}, payload, digest) is False
    assert backend._before_matches(1, payload, digest) is False


def test_snapshot_and_delta_validate_bounds_and_digest_forms(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(BackendPackageContractError, match="max_files"):
        snapshot_workspace(workspace, max_files=0)
    with pytest.raises(BackendPackageContractError, match="max_files"):
        snapshot_workspace(workspace, max_files=True)  # type: ignore[arg-type]
    with pytest.raises(BackendPackageContractError, match="max_bytes"):
        snapshot_workspace(workspace, max_bytes=0)

    (workspace / "app").mkdir()
    target = workspace / "app" / "file.txt"
    target.write_text("v1", encoding="utf-8")
    before = snapshot_workspace(workspace)
    target.write_text("v2", encoding="utf-8")
    report = validate_workspace_delta(
        workspace, {"app/file.txt": {"digest": "other"}}, allowed_roots=(workspace / "app",)
    )
    assert report.ok is True
    assert report.changed_paths == ("app", "app/file.txt")
    report = validate_workspace_delta(workspace, before, allowed_roots=(workspace / "app",))
    assert report.ok is True
    assert report.changed_paths == ("app/file.txt",)

    invalid = validate_workspace_delta(workspace, object())  # type: ignore[arg-type]
    assert invalid.ok is False
    _has(invalid.errors, "snapshot must be a mapping")
    too_large = validate_workspace_delta(workspace, {"x": "x"}, max_files=0)
    assert too_large.ok is False


def test_snapshot_rejects_symlink_entries_and_delta_protected_package(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = tmp_path / "outside"
    target.write_text("outside", encoding="utf-8")
    (workspace / "link").symlink_to(target)
    with pytest.raises(BackendPackageContractError, match="unsafe entries"):
        snapshot_workspace(workspace)

    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "app").mkdir()
    (clean / "app" / "file.py").write_text("v1", encoding="utf-8")
    before = snapshot_workspace(clean)
    (clean / "app" / "file.py").write_text("v2", encoding="utf-8")
    report = validate_workspace_delta(
        clean,
        before,
        allowed_roots=(clean / "app",),
        package_path=clean / "app" / "file.py",
    )
    assert report.ok is False
    assert report.unauthorized_paths == ("app/file.py",)
