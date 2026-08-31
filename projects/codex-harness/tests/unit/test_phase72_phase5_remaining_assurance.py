from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from test_phase4_policy import _discovered_record
from test_phase5_cli_runtime import _preflight, _project

from harness_kernel import phase4_artifacts, phase4_policy, phase5_cli
from harness_kernel.phase4_evidence import EvidenceWriter
from harness_kernel.phase5_execution import BuilderResponse, _needs_repair, _result_status
from harness_kernel.phase5_models import Phase5Status, VisualCritique
from harness_kernel.phase5_paths import Phase5CliError, resolved_project_root, safe_project_path
from harness_kernel.phase5_pilot import (
    Phase5PilotInputError,
    _safe_components,
    load_task,
    resolve_task_path,
)

DIGEST = "sha256:" + "b" * 64


def test_confined_artifact_directory_closes_fd_on_typed_and_os_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "target"
    target.write_text("not a directory", encoding="utf-8")
    real_open = phase4_artifacts.os.open
    real_fstat = phase4_artifacts.os.fstat

    def typed_open(path, flags, *args, **kwargs):
        if path == workspace:
            return real_open(path, flags, *args, **kwargs)
        return real_open(target, os.O_RDONLY)

    monkeypatch.setattr(phase4_artifacts.os, "open", typed_open)
    monkeypatch.setattr(phase4_artifacts.os, "fstat", lambda fd: real_fstat(target_fd))
    target_fd = real_open(target, os.O_RDONLY)
    try:
        with pytest.raises(phase4_artifacts.ArtifactCaptureError, match="unsafe"):
            phase4_artifacts._open_confined_directory(workspace / "target" / "child", workspace)
    finally:
        os.close(target_fd)

    def os_error_open(path, flags, *args, **kwargs):
        if path == workspace:
            return real_open(path, flags, *args, **kwargs)
        raise OSError("simulated open failure")

    monkeypatch.setattr(phase4_artifacts.os, "open", os_error_open)
    with pytest.raises(phase4_artifacts.ArtifactCaptureError, match="opened safely"):
        phase4_artifacts._open_confined_directory(workspace / "target", workspace)


def test_confined_artifact_directory_preserves_preopen_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def typed_failure(*_args, **_kwargs):
        raise phase4_artifacts.ArtifactCaptureError("typed pre-open failure")

    monkeypatch.setattr(phase4_artifacts.os, "open", typed_failure)
    with pytest.raises(phase4_artifacts.ArtifactCaptureError, match="pre-open"):
        phase4_artifacts._open_confined_directory(workspace / "nested", workspace)

    def os_failure(*_args, **_kwargs):
        raise OSError("os pre-open failure")

    monkeypatch.setattr(phase4_artifacts.os, "open", os_failure)
    with pytest.raises(phase4_artifacts.ArtifactCaptureError, match="opened safely"):
        phase4_artifacts._open_confined_directory(workspace / "nested", workspace)


def test_phase5_project_and_task_paths_reject_unsafe_boundaries(tmp_path: Path) -> None:
    regular = tmp_path / "regular"
    regular.write_text("x", encoding="utf-8")
    with pytest.raises(Phase5CliError, match="directory"):
        resolved_project_root(regular)
    with pytest.raises(Phase5CliError, match="unsafe"):
        safe_project_path(tmp_path, Path("../escape"), "path")

    with pytest.raises(Phase5PilotInputError, match="absolute"):
        _safe_components(Path("relative.json"))
    with pytest.raises(Phase5PilotInputError, match="unsafe"):
        resolve_task_path("../escape", base=tmp_path, label="workspace")


def test_phase5_task_loader_rejects_artifact_root_outside_workspace(tmp_path: Path) -> None:
    project = _project(tmp_path)
    task_path = project / "tests/fixtures/phase5/design-pilot/task.json"
    payload = json.loads(task_path.read_text(encoding="utf-8"))
    payload["artifact_root"] = str(tmp_path / "outside-artifacts")
    task_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(Phase5PilotInputError, match="artifact_root"):
        load_task(task_path, project_root=project)


def test_phase5_execution_routes_blocked_critic_and_missing_evidence_to_blocked() -> None:
    critique = VisualCritique(
        benchmark_id="BENCH-P72",
        run_id="RUN-P72",
        inspection_id="INS-P72",
        artifact_digest=DIGEST,
        independence="INDEPENDENT",
        blinded=True,
        builder_rationale_withheld=True,
        self_score_withheld=True,
        packet_digest=DIGEST,
        verdict=Phase5Status.BLOCKED,
        overall_score=None,
        evidence_confidence="LOW",
        dimension_scores={},
        findings=(),
        top_corrections=(),
        evidence_missing=("browser",),
    )
    assert _needs_repair(critique) is False
    assert _result_status(None, None, artifact=None) is Phase5Status.BLOCKED


def test_phase5_cli_builder_records_bounded_exhaustion_after_invalid_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    preflight = _preflight(project)
    writer = EvidenceWriter(project / "evidence/phase-5/pilots/design-director")
    invalid = BuilderResponse(
        Phase5Status.PASS,
        "INV-P72-INVALID",
        json.dumps({"artifact_filename": "index.html", "artifact_html": "not html"}),
        True,
        "HOST_LOAD_UNOBSERVABLE",
    )
    calls = 0

    def fake_invoke(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return invalid

    monkeypatch.setattr(phase5_cli, "invoke_host_builder", fake_invoke)
    result = phase5_cli._run_builder(preflight, writer)
    assert result["status"] is Phase5Status.BLOCKED
    assert calls == 2
    receipt = json.loads(
        (
            project / "evidence/phase-5/pilots/design-director/builder-invocation-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["attempt_count"] == 2
    assert not (project / "evidence/phase-5/pilots/design-director/artifact-v1/index.html").exists()


def test_phase4_policy_skill_resolution_fails_closed_when_resolved_child_escapes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record, _inventory, _resolution = _discovered_record(tmp_path)

    class FakePath:
        def __init__(self, value: object, *, resolved: str | None = None) -> None:
            self.value = str(value)
            self.resolved = resolved

        def is_absolute(self) -> bool:
            return self.value.startswith("/")

        @property
        def parts(self) -> tuple[str, ...]:
            return ("SKILL.md",) if self.value == "SKILL.md" else ("package",)

        def __truediv__(self, other: object) -> FakePath:
            return FakePath("candidate", resolved="outside")

        def resolve(self, *, strict: bool) -> FakePath:
            return FakePath(self.resolved or self.value)

        def is_relative_to(self, _other: object) -> bool:
            return self.value != "outside"

        def is_file(self) -> bool:
            return True

    monkeypatch.setattr(phase4_policy, "Path", FakePath)
    monkeypatch.setattr(phase4_policy, "_has_symlink_component", lambda _path: False)
    skill_path, error = phase4_policy._safe_skill_path(record)
    assert skill_path is None
    assert error == "SKILL_SOURCE_ESCAPE"
