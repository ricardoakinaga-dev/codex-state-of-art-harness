from __future__ import annotations

import json
import shutil
from pathlib import Path

from harness_kernel.phase5_cli import main
from harness_kernel.phase5_pilot import load_task


def _copy_fixture_project(tmp_path: Path) -> Path:
    source_root = Path(__file__).parents[1]
    project = tmp_path / "project"
    task_source = source_root / "fixtures/phase5/design-pilot/task.json"
    policy_source = Path(__file__).parents[2] / "config/phase5-composition-policy.json"
    task_target = project / "tests/fixtures/phase5/design-pilot/task.json"
    workspace = project / "tests/fixtures/phase5/design-pilot/workspace/artifacts"
    task_target.parent.mkdir(parents=True)
    workspace.mkdir(parents=True)
    (project / "config").mkdir()
    shutil.copyfile(task_source, task_target)
    shutil.copyfile(policy_source, project / "config/phase5-composition-policy.json")
    return project


def test_task_loader_resolves_only_the_fixture_workspace(tmp_path: Path) -> None:
    project = _copy_fixture_project(tmp_path)
    task_path = project / "tests/fixtures/phase5/design-pilot/task.json"
    task = load_task(task_path, project_root=project)
    assert Path(task.workspace) == task_path.parent / "workspace"
    assert Path(task.artifact_root) == task_path.parent / "workspace/artifacts"
    assert task.criteria.render_viewports == ((1440, 900), (390, 844))


def test_cli_dry_preflight_writes_blocked_handoffs_without_host_invocation(
    tmp_path: Path, capsys
) -> None:
    project = _copy_fixture_project(tmp_path)
    result = main(["--project-root", str(project), "pilot", "--json"])
    assert result == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED"
    assert "REAL_MODE_CONFIRMATION_REQUIRED" in payload["route"]["blockers"]
    evidence = project / "evidence/phase-5/pilots/design-director"
    assert (evidence / "task.json").is_file()
    assert (evidence / "eligibility.json").is_file()
    receipt = json.loads((evidence / "builder-invocation-receipt.json").read_text())
    assert receipt["attempt_count"] == 0


def test_cli_requires_the_exact_package_fingerprint_before_real_mode(
    tmp_path: Path, capsys
) -> None:
    project = _copy_fixture_project(tmp_path)
    result = main(
        [
            "--project-root",
            str(project),
            "pilot",
            "--controlled-real",
            "--confirm-fingerprint",
            "sha256:" + "0" * 64,
            "--json",
        ]
    )
    assert result == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED"
    assert "FINGERPRINT_CONFIRMATION_MISMATCH" in payload["route"]["blockers"]
    assert (
        json.loads(
            (
                project / "evidence/phase-5/pilots/design-director/builder-invocation-receipt.json"
            ).read_text()
        )["attempt_count"]
        == 0
    )
