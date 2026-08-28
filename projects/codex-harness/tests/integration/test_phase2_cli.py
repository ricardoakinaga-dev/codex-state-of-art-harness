from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]


def invoke(*arguments: str, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "harness_kernel", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def payload(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(result.stdout)


def test_run_dry_run_and_json_surface_are_safe_and_explainable() -> None:
    result = invoke(
        "run", "Change one local label", "--dry-run", "--json", "--run-id", "RUN-CLI-P2"
    )

    assert result.returncode == 0
    data = payload(result)
    assert data["status"] == "DRY_RUN"
    assert data["executed"] is False
    assert data["route"]


def test_run_uses_only_explicit_local_provider_and_persists_inside_project() -> None:
    result = invoke(
        "run",
        "Change one local label",
        "--provider",
        "local.success",
        "--json",
        "--run-id",
        "RUN-CLI-P2-SUCCESS",
    )

    assert result.returncode == 0
    data = payload(result)
    assert data["status"] == "SUCCEEDED"
    assert data["provider"] == "local.success"
    assert (PROJECT_ROOT / ".harness/state/runs/RUN-CLI-P2-SUCCESS.json").is_file()


def test_run_rejects_unknown_provider_without_hidden_fallback() -> None:
    result = invoke(
        "run",
        "Change one local label",
        "--provider",
        "missing.provider",
        "--json",
        "--run-id",
        "RUN-CLI-P2-MISSING",
    )

    assert result.returncode == 1
    data = payload(result)
    assert data["status"] == "FAILED"
    assert data["failure_category"] == "CAPABILITY_UNAVAILABLE"
    assert data["provider"] == "missing.provider"


def test_quality_and_doctor_never_execute_a_provider() -> None:
    quality = invoke("quality", "--json")
    doctor = invoke("doctor", "--json")

    assert quality.returncode == 0
    assert doctor.returncode == 0
    assert payload(doctor)["capabilities_executed"] is False


def test_run_explain_is_a_non_executing_json_plan() -> None:
    result = invoke(
        "run",
        "Change one local label",
        "--explain",
        "--json",
        "--run-id",
        "RUN-CLI-P2-EXPLAIN",
    )

    assert result.returncode == 0
    data = payload(result)
    assert data["status"] == "DRY_RUN"
    assert data["executed"] is False
    assert data["explain"]["execution"]["will_execute"] is False
    assert data["explain"]["provider"]["local_only"] is True


def test_run_rejects_a_persistent_root_outside_the_current_project(tmp_path: Path) -> None:
    result = invoke(
        "run",
        "Change one local label",
        "--provider",
        "local.success",
        "--root",
        str(tmp_path),
        "--run-id",
        "RUN-CLI-OUTSIDE",
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "PATH_INVALID"
    assert not (tmp_path / ".harness").exists()


def test_run_requires_admitted_project_manifests_before_provider_execution(tmp_path: Path) -> None:
    project = tmp_path / "project"
    source = PROJECT_ROOT / ".harness"
    shutil.copytree(source, project / ".harness")
    manifest = project / ".harness" / "capabilities" / "harness-kernel" / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["display_name"] = "tampered manifest"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = invoke(
        "run",
        "Change one local label",
        "--provider",
        "local.success",
        "--root",
        str(project),
        "--run-id",
        "RUN-CLI-MANIFEST-DENY",
        cwd=project,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["code"] == "REGISTRY_INVALID"
    assert not (project / ".harness" / "state" / "runs" / "RUN-CLI-MANIFEST-DENY.json").exists()
