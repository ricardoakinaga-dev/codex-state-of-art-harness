from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import harness_kernel.phase4_artifacts as artifact_module
import harness_kernel.phase7_backend as backend_module
from harness_kernel.phase3_paths import digest_bytes
from harness_kernel.phase4_artifacts import ArtifactCaptureError, validate_artifact_path
from harness_kernel.phase7_backend import (
    BackendPackageContractError,
    package_fingerprint,
    snapshot_workspace,
    validate_backend_manifest,
    validate_backend_package,
    validate_workspace_delta,
)

PROJECT_ROOT = Path(__file__).parents[2].resolve()
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "backend-engineering-vnext"


def _copy_package(tmp_path: Path) -> Path:
    package = tmp_path / "backend-package"
    shutil.copytree(PACKAGE_ROOT, package)
    return package


def test_backend_package_rejects_a_resolved_symlink_race(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    decisions = iter((False, True))
    monkeypatch.setattr(backend_module, "_has_symlink_component", lambda _path: next(decisions))

    with pytest.raises(BackendPackageContractError, match="resolves through a symlink"):
        backend_module._safe_package_path(package)


def test_backend_package_rejects_a_final_symlink_even_if_component_scan_misses_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(backend_module, "_has_symlink_component", lambda _path: False)

    with pytest.raises(BackendPackageContractError, match="package path is a symlink"):
        backend_module._safe_package_path(alias)


def test_backend_manifest_accepts_all_supported_path_inputs() -> None:
    manifest_path = PACKAGE_ROOT / "manifest.json"

    assert validate_backend_manifest(PACKAGE_ROOT) == ()
    assert validate_backend_manifest(manifest_path) == ()
    assert validate_backend_manifest(manifest_path, package_path=PACKAGE_ROOT) == ()


def test_backend_manifest_security_contract_rejects_write_capabilities() -> None:
    manifest = json.loads((PACKAGE_ROOT / "manifest.json").read_text(encoding="utf-8"))

    not_read_only = json.loads(json.dumps(manifest))
    not_read_only["security"]["read_only"] = False
    assert "manifest security.read_only must be true" in validate_backend_manifest(not_read_only)

    has_tools = json.loads(json.dumps(manifest))
    has_tools["security"]["allowed_tools"] = ["network"]
    assert "manifest security.allowed_tools must be empty" in validate_backend_manifest(has_tools)


def test_backend_package_rejects_a_fingerprint_mismatch() -> None:
    report = validate_backend_package(
        PACKAGE_ROOT,
        expected_fingerprint="sha256:" + "0" * 64,
    )

    assert report.ok is False
    assert "PACKAGE_FINGERPRINT_MISMATCH" in report.blockers


def test_backend_package_reads_declared_identity_digest() -> None:
    digest = "sha256:" + "a" * 64

    assert (
        backend_module._package_declared_digest({"identity": {"package_fingerprint": digest}})
        == digest
    )


def test_backend_package_reports_missing_skill_without_becoming_eligible(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "SKILL.md").unlink()
    fingerprint = package_fingerprint(package)

    report = validate_backend_package(
        package,
        expected_package_path=package,
        expected_fingerprint=fingerprint,
    )

    assert report.ok is False
    assert "SKILL_MISSING" in report.blockers


def test_backend_package_metadata_handles_manifest_without_composition(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("composition")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    fingerprint = package_fingerprint(package)

    report = validate_backend_package(
        package,
        expected_package_path=package,
        expected_fingerprint=fingerprint,
    )

    assert report.ok is False
    assert "manifest composition must be an object" in report.blockers


def test_backend_allowed_root_rejects_symlinked_root(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    pilot = workspace / "pilot"
    workspace.mkdir()
    pilot.mkdir()
    alias = tmp_path / "pilot-alias"
    alias.symlink_to(pilot, target_is_directory=True)

    report = validate_workspace_delta(workspace, {}, allowed_roots=(alias,))

    assert report.ok is False
    assert report.errors == ("allowed workspace root contains a symlink",)


def test_backend_declared_path_rejects_symlink_component(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    pilot = workspace / "pilot"
    workspace.mkdir()
    pilot.mkdir()
    alias = workspace / "pilot-alias"
    alias.symlink_to(pilot, target_is_directory=True)

    with pytest.raises(BackendPackageContractError, match="declared path contains a symlink"):
        backend_module._safe_declared_path(alias / "result.json", workspace=workspace)


def test_backend_workspace_delta_accepts_a_mapping_content_digest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    pilot = workspace / "pilot"
    pilot.mkdir(parents=True)
    target = pilot / "result.txt"
    target.write_text("stable", encoding="utf-8")
    before = dict(snapshot_workspace(workspace))
    before["pilot/result.txt"] = {"digest": digest_bytes(b"stable")}

    report = validate_workspace_delta(workspace, before, allowed_roots=(pilot,))

    assert report.ok is True
    assert report.changed_paths == ()
    assert report.unauthorized_paths == ()


def test_backend_workspace_rejects_nul_path_without_leaking_value_error(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(BackendPackageContractError):
        backend_module.snapshot_workspace(str(workspace) + "\x00invalid")


def test_artifact_symlink_component_scan_distinguishes_safe_and_unsafe_paths(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    alias = workspace / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)

    assert artifact_module._has_symlink_component(workspace / "missing") is False
    assert artifact_module._has_symlink_component(alias / "result.txt") is True


def test_artifact_open_rejects_a_non_directory_after_descriptor_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "artifacts"
    regular = tmp_path / "regular"
    target.mkdir(parents=True)
    workspace.mkdir(exist_ok=True)
    regular.write_text("not a directory", encoding="utf-8")

    monkeypatch.setattr(artifact_module.os, "fstat", lambda _fd: regular.stat())

    with pytest.raises(ArtifactCaptureError, match="artifact directory is unsafe"):
        artifact_module._open_confined_directory(target, workspace)


def test_artifact_open_closes_the_pinned_descriptor_on_an_os_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "artifacts"
    workspace.mkdir()
    target.mkdir()
    real_open = artifact_module.os.open
    calls = 0

    def fail_second_open(path: object, *args: object, **kwargs: object) -> int:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("simulated directory-open failure")
        return real_open(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(artifact_module.os, "open", fail_second_open)

    with pytest.raises(ArtifactCaptureError, match="cannot be opened safely"):
        artifact_module._open_confined_directory(target, workspace)
    assert calls == 2


def test_artifact_open_closes_descriptors_when_fstat_rejects_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "artifacts"
    workspace.mkdir()
    target.mkdir()
    real_close = artifact_module.os.close
    closed: list[int] = []

    def record_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(artifact_module.os, "close", record_close)
    monkeypatch.setattr(artifact_module.os, "fstat", lambda _fd: os.stat(__file__))

    with pytest.raises(ArtifactCaptureError, match="artifact directory is unsafe"):
        artifact_module._open_confined_directory(target, workspace)
    assert len(closed) == 2


def test_artifact_open_rejects_an_empty_relative_component(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fake_path = Mock()
    fake_path.parts = ("synthetic",)
    fake_path.is_absolute.return_value = True
    fake_path.is_relative_to.return_value = True
    fake_path.relative_to.return_value = SimpleNamespace(parts=("",))

    with pytest.raises(ArtifactCaptureError, match="empty component"):
        artifact_module._open_confined_directory(fake_path, workspace)


def test_artifact_paths_reject_nul_without_leaking_value_error(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(ArtifactCaptureError):
        validate_artifact_path(str(workspace / "bad\x00name"), workspace)
    with pytest.raises(ArtifactCaptureError):
        validate_artifact_path(workspace / "result.txt", str(workspace) + "\x00invalid")
