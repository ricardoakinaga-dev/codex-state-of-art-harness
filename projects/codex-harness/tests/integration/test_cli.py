from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from harness_kernel.cli import _manifest_source_hash
from harness_kernel.models import CapabilityManifest, TelemetryEventType
from harness_kernel.serialization import from_dict, to_dict
from harness_kernel.telemetry import create_event

PROJECT_ROOT = Path(__file__).parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
CONFIG_FIXTURE = PROJECT_ROOT / ".harness" / "config" / "kernel.json"
MANIFEST_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "golden" / "capability-manifest.json"
INVALID_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "negative" / "invalid-task-profile.json"


def copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(PROJECT_ROOT / ".harness", project / ".harness")
    shutil.copytree(WORKSPACE_ROOT / "architecture", project / "architecture")
    return project


def invoke(
    *arguments: str,
    cwd: Path = PROJECT_ROOT,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(SOURCE_ROOT), environment.get("PYTHONPATH")) if item
    )
    return subprocess.run(
        [sys.executable, "-m", "harness_kernel", *arguments],
        cwd=cwd,
        env=environment,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def report(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(result.stdout)


def test_help_exposes_the_bounded_local_execution_surface() -> None:
    result = invoke("--help")

    assert result.returncode == 0
    assert "validate" in result.stdout
    assert "doctor" in result.stdout
    assert "health" in result.stdout
    assert "run" in result.stdout
    assert "quality" in result.stdout


def test_validate_accepts_a_contract_fixture_without_execution() -> None:
    result = invoke("validate", str(MANIFEST_FIXTURE))

    assert result.returncode == 0
    payload = report(result)
    assert payload["status"] == "PASS"
    assert payload["valid"] is True
    assert payload["record_type"] == "CapabilityManifest"
    assert payload["document_schema"] == "CM-1"


def test_validate_accepts_the_project_kernel_config() -> None:
    result = invoke("validate", str(CONFIG_FIXTURE))

    assert result.returncode == 0
    payload = report(result)
    assert payload["status"] == "PASS"
    assert payload["record_type"] == "KernelConfig"
    assert payload["document_schema"] == "HK-1"


def test_validate_reports_invalid_contract_without_echoing_input_values() -> None:
    result = invoke("validate", str(INVALID_FIXTURE))

    assert result.returncode == 1
    payload = report(result)
    assert payload["status"] == "FAIL"
    assert payload["valid"] is False
    assert "not an id" not in result.stdout
    assert "NOT_A_DOMAIN" not in result.stdout


def test_validate_supports_bounded_stdin_and_text_output() -> None:
    document = MANIFEST_FIXTURE.read_text(encoding="utf-8")

    result = invoke("validate", "-", "--format", "text", stdin=document)

    assert result.returncode == 0
    assert result.stdout.startswith("PASS validate:")
    assert "CapabilityManifest" in result.stdout


def test_validate_rejects_oversized_input_with_a_generic_error(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{}" + b" " * (4 * 1024 * 1024))

    result = invoke("validate", str(oversized), "--root", str(tmp_path))

    assert result.returncode == 2
    assert "SIZE_LIMIT_EXCEEDED" in result.stdout
    assert str(oversized) not in result.stdout


def test_validate_rejects_traversal_paths_without_echoing_the_path() -> None:
    result = invoke("validate", "../outside.json")

    assert result.returncode == 2
    assert "PATH" in result.stdout
    assert "outside.json" not in result.stdout


def test_validate_rejects_absolute_paths_outside_the_project_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    result = invoke("validate", str(outside))

    assert result.returncode == 2
    assert "PATH" in result.stdout
    assert str(outside) not in result.stdout


def test_json_payload_never_imports_or_executes_a_value(tmp_path: Path) -> None:
    marker = tmp_path / "executed.txt"
    payload = {
        "schema_version": f"__import__('pathlib').Path({marker!r}).write_text('executed')",
        "payload": "not executable",
    }
    source = tmp_path / "payload.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    result = invoke("validate", str(source), "--root", str(tmp_path))

    assert result.returncode == 1
    assert not marker.exists()
    assert "write_text" not in result.stdout


def test_doctor_is_deterministic_and_reports_no_capability_execution() -> None:
    first = invoke("doctor")
    second = invoke("doctor")

    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout
    payload = report(first)
    assert payload["status"] == "PASS"
    assert payload["capabilities_executed"] is False
    assert any(
        check["id"] == "CAPABILITY_EXECUTION" and check["status"] == "NOT_RUN"
        for check in payload["checks"]  # type: ignore[union-attr]
    )


def test_health_alias_uses_the_same_read_only_checks() -> None:
    result = invoke("health")

    assert result.returncode == 0
    payload = report(result)
    assert payload["command"] == "health"
    assert payload["status"] == "PASS"
    assert payload["capabilities_executed"] is False


def test_doctor_does_not_import_python_files_in_the_local_capability_tree(
    tmp_path: Path,
) -> None:
    project = copy_project(tmp_path)
    marker = project / "imported.txt"
    malicious = project / ".harness" / "capabilities" / "malicious.py"
    malicious.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('imported')\n",
        encoding="utf-8",
    )

    result = invoke("doctor", "--root", str(project))

    assert result.returncode == 0
    assert not marker.exists()
    assert report(result)["capabilities_executed"] is False


def test_registry_list_and_inspect_are_read_only() -> None:
    listed = invoke("registry", "list")
    inspected = invoke("registry", "inspect", "harness-kernel")

    assert listed.returncode == 0
    assert inspected.returncode == 0
    assert report(listed)["count"] == 1
    assert report(inspected)["valid"] is True
    assert report(inspected)["usable"] is True
    assert report(inspected)["manifest"]["capability_id"] == "harness-kernel"


def test_registry_rejects_divergent_canonical_and_registry_manifests(tmp_path: Path) -> None:
    project = copy_project(tmp_path)
    package_manifest = project / ".harness" / "capabilities" / "harness-kernel" / "manifest.json"
    payload = json.loads(package_manifest.read_text(encoding="utf-8"))
    payload["display_name"] = "Divergent Harness Kernel"
    package_manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = invoke("registry", "--root", str(project), "list")

    assert result.returncode == 1
    response = report(result)
    assert response["status"] == "FAIL"
    assert any(item["code"] == "MANIFEST_DIVERGENCE" for item in response["findings"])
    assert str(project) not in result.stdout


def test_registry_rejects_a_local_source_hash_mismatch(tmp_path: Path) -> None:
    project = copy_project(tmp_path)
    source = project / ".harness" / "capabilities" / "harness-kernel" / "README.md"
    source.write_text(source.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    result = invoke("registry", "--root", str(project), "list")

    assert result.returncode == 1
    response = report(result)
    assert any(item["code"] == "SOURCE_HASH_MISMATCH" for item in response["findings"])


def test_registry_rejects_a_project_scope_mismatch(tmp_path: Path) -> None:
    project = copy_project(tmp_path)
    config = project / ".harness" / "config" / "kernel.json"
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["project_id"] = "another-project"
    config.write_text(json.dumps(payload), encoding="utf-8")

    result = invoke("registry", "--root", str(project), "list")

    assert result.returncode == 1
    response = report(result)
    assert any(item["code"] == "PROJECT_SCOPE_MISMATCH" for item in response["findings"])


def test_registry_inspect_does_not_report_rejected_manifest_as_usable(tmp_path: Path) -> None:
    project = copy_project(tmp_path)
    for relative in (
        ".harness/capabilities/harness-kernel/manifest.json",
        ".harness/registry/manifests/harness-kernel.json",
    ):
        manifest = project / relative
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["status"] = "REJECTED"
        candidate = from_dict(payload, CapabilityManifest)
        payload["provenance"]["source_hash"] = _manifest_source_hash(candidate, project)
        manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = invoke("registry", "--root", str(project), "inspect", "harness-kernel")

    assert result.returncode == 1
    response = report(result)
    assert response["status"] == "FAIL"
    assert response["valid"] is True
    assert response["usable"] is False


def test_registry_rejects_an_excessive_manifest_file_count(tmp_path: Path) -> None:
    project = copy_project(tmp_path)
    manifest_directory = project / ".harness" / "registry" / "manifests"
    for index in range(257):
        (manifest_directory / f"manifest-{index}.json").write_text("{}", encoding="utf-8")

    result = invoke("registry", "--root", str(project), "list")

    assert result.returncode == 2
    assert "REGISTRY_SIZE_LIMIT" in result.stdout
    assert str(project) not in result.stdout


def test_profile_and_route_use_contract_data_without_execution() -> None:
    profiled = invoke(
        "profile",
        "Validate a local manifest",
        "--task-id",
        "TASK-CLI-1",
        "--run-id",
        "RUN-CLI-1",
    )
    routed = invoke(
        "route", str(PROJECT_ROOT / "tests" / "fixtures" / "golden" / "task-profile.json")
    )

    assert profiled.returncode == 0
    assert routed.returncode == 0
    assert report(profiled)["record_type"] == "TaskProfile"
    assert report(routed)["record_type"] == "RouteDecision"
    assert report(routed)["executed"] is False


def test_route_rejects_an_oversized_objective_without_echoing_it() -> None:
    objective = "x" * 10_001

    result = invoke("route", "--objective", objective)

    assert result.returncode == 2
    assert "SIZE_LIMIT_EXCEEDED" in result.stdout
    assert objective not in result.stdout


def test_profile_rejects_invalid_identifiers_without_echoing_them() -> None:
    result = invoke(
        "profile",
        "Validate a local manifest",
        "--task-id",
        "../outside",
        "--run-id",
        "RUN-OK",
    )

    assert result.returncode == 2
    assert "INVALID_INPUT" in result.stdout
    assert "../outside" not in result.stdout


def test_registry_honors_configured_manifest_directory(tmp_path: Path) -> None:
    project = copy_project(tmp_path)
    config = project / ".harness" / "config" / "kernel.json"
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["registry"]["manifest_dir"] = ".harness/registry/not-the-registry"
    config.write_text(json.dumps(payload), encoding="utf-8")

    result = invoke("registry", "--root", str(project), "list")

    assert result.returncode == 2
    assert "REGISTRY_UNAVAILABLE" in result.stdout
    assert str(project) not in result.stdout


def test_state_command_reports_project_control_state() -> None:
    result = invoke("state")

    assert result.returncode == 0
    payload = report(result)
    assert payload["status"] == "PASS"
    assert payload["state"]["project"] == "Codex State of Art Harness"


def test_telemetry_validate_accepts_a_single_event_log(tmp_path: Path) -> None:
    event = create_event(
        event_id="EVT-CLI-1",
        event_sequence=1,
        timestamp="2026-08-28T12:00:00Z",
        task_id="TASK-CLI-1",
        run_id="RUN-CLI-1",
        event_type=TelemetryEventType.TASK_RECEIVED,
    )
    source = tmp_path / "telemetry.json"
    source.write_text(json.dumps({"events": [to_dict(event)]}), encoding="utf-8")

    result = invoke("telemetry", "--root", str(tmp_path), "validate", str(source))

    assert result.returncode == 0
    assert report(result)["valid"] is True


def test_telemetry_validate_rejects_an_excessive_event_count(tmp_path: Path) -> None:
    event = create_event(
        event_id="EVT-CLI-2",
        event_sequence=1,
        timestamp="2026-08-28T12:00:00Z",
        task_id="TASK-CLI-1",
        run_id="RUN-CLI-1",
        event_type=TelemetryEventType.TASK_RECEIVED,
    )
    source = tmp_path / "telemetry.json"
    source.write_text(
        json.dumps({"events": [to_dict(event)] * 1_025}),
        encoding="utf-8",
    )

    result = invoke("telemetry", "--root", str(tmp_path), "validate", str(source))

    assert result.returncode == 2
    assert "TELEMETRY_SIZE_LIMIT" in result.stdout
    assert str(source) not in result.stdout


def test_validate_rejects_unknown_and_traversal_configuration_fields(tmp_path: Path) -> None:
    config = json.loads(CONFIG_FIXTURE.read_text(encoding="utf-8"))
    config["unexpected"] = "ignored?"
    config["paths"]["state_dir"] = "../outside"
    source = tmp_path / "unsafe-config.json"
    source.write_text(json.dumps(config), encoding="utf-8")

    result = invoke("validate", str(source), "--root", str(tmp_path))

    assert result.returncode == 1
    payload = report(result)
    assert payload["valid"] is False
    codes = {finding["code"] for finding in payload["findings"]}  # type: ignore[union-attr]
    assert "UNKNOWN_FIELD" in codes
    assert "INVALID_REFERENCE" in codes


def test_validate_rejects_excessive_json_depth(tmp_path: Path) -> None:
    source = tmp_path / "deep.json"
    source.write_text("[" * 65 + "0" + "]" * 65, encoding="utf-8")

    result = invoke("validate", str(source), "--root", str(tmp_path))

    assert result.returncode == 2
    assert "DEPTH_LIMIT_EXCEEDED" in result.stdout
