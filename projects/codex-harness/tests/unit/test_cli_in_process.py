from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import harness_kernel.cli as cli
from harness_kernel.models import TelemetryEventType
from harness_kernel.serialization import to_dict
from harness_kernel.telemetry import create_event

PROJECT_ROOT = Path(__file__).parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
MANIFEST_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "golden" / "capability-manifest.json"
CONFIG_FIXTURE = PROJECT_ROOT / ".harness" / "config" / "kernel.json"


def _copy_project(tmp_path: Path, *, include_agent: bool = True) -> Path:
    project = tmp_path / "project"
    shutil.copytree(PROJECT_ROOT / ".harness", project / ".harness")
    shutil.copytree(WORKSPACE_ROOT / "architecture", project / "architecture")
    if include_agent:
        shutil.copytree(PROJECT_ROOT / ".agent", project / ".agent")
    return project


def _json_output(capsys) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def test_main_without_a_command_prints_help(capsys) -> None:
    assert cli.main([]) == 0
    output = capsys.readouterr().out
    assert "validate" in output
    assert "run" in output


def test_validate_dispatches_file_stdin_and_config_contracts(monkeypatch, capsys) -> None:
    monkeypatch.chdir(PROJECT_ROOT)

    assert cli.main(["validate", str(MANIFEST_FIXTURE)]) == 0
    manifest = _json_output(capsys)
    assert manifest["record_type"] == "CapabilityManifest"

    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(MANIFEST_FIXTURE.read_text()))
    assert cli.main(["validate", "-", "--format", "text"]) == 0
    assert capsys.readouterr().out.startswith("PASS validate:")

    assert cli.main(["validate", str(CONFIG_FIXTURE)]) == 0
    config = _json_output(capsys)
    assert config["record_type"] == "KernelConfig"


def test_validate_rejects_bad_json_duplicate_keys_and_nonfinite_values(
    tmp_path: Path, capsys
) -> None:
    bad_json = tmp_path / "bad.json"
    bad_json.write_text('{"schema_version":"CM-1", "schema_version":"CM-1"}')
    assert cli.main(["validate", str(bad_json), "--root", str(tmp_path)]) == 2
    assert _json_output(capsys)["code"] == "DUPLICATE_KEY"

    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"schema_version":"CM-1", "value":NaN}')
    assert cli.main(["validate", str(nonfinite), "--root", str(tmp_path)]) == 2
    assert _json_output(capsys)["code"] == "INVALID_JSON"


def test_validate_reports_unknown_schema_and_invalid_contract(capsys, tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps({"schema_version": "UNKNOWN"}))
    assert cli.main(["validate", str(unknown), "--root", str(tmp_path)]) == 1
    unknown_payload = _json_output(capsys)
    assert unknown_payload["status"] == "FAIL"
    assert unknown_payload["findings"][0]["code"] == "INVALID_VERSION"

    invalid = PROJECT_ROOT / "tests" / "fixtures" / "negative" / "invalid-task-profile.json"
    assert cli.main(["validate", str(invalid)]) == 1
    invalid_payload = _json_output(capsys)
    assert invalid_payload["status"] == "FAIL"


def test_doctor_health_quality_and_state_dispatches(monkeypatch, capsys) -> None:
    monkeypatch.chdir(PROJECT_ROOT)

    assert cli.main(["doctor", "--format", "text"]) == 0
    assert capsys.readouterr().out.startswith("PASS doctor:")

    assert cli.main(["health", "--json"]) == 0
    health = _json_output(capsys)
    assert health["command"] == "health"
    assert health["capabilities_executed"] is False

    assert cli.main(["quality", "--format", "text"]) == 0
    assert capsys.readouterr().out.startswith("PASS quality:")

    assert cli.main(["state"]) == 0
    state = _json_output(capsys)
    assert state["state"]["project"] == "Codex State of Art Harness"


def test_registry_profile_and_route_dispatches(monkeypatch, capsys) -> None:
    monkeypatch.chdir(PROJECT_ROOT)

    assert cli.main(["registry", "list"]) == 0
    listed = _json_output(capsys)
    assert listed["count"] == 1

    assert cli.main(["registry", "inspect", "harness-kernel", "--format", "text"]) == 0
    assert capsys.readouterr().out.startswith("PASS registry inspect:")

    assert cli.main(["profile", "Validate a local manifest", "--format", "text"]) == 0
    assert capsys.readouterr().out.startswith("PASS profile:")

    assert cli.main(["route", "--objective", "Validate a local manifest"]) == 0
    route = _json_output(capsys)
    assert route["executed"] is False

    profile = PROJECT_ROOT / "tests" / "fixtures" / "golden" / "task-profile.json"
    assert cli.main(["route", str(profile)]) == 0
    assert _json_output(capsys)["record_type"] == "RouteDecision"


def test_registry_and_route_report_safe_errors(tmp_path: Path, capsys) -> None:
    project = _copy_project(tmp_path, include_agent=False)
    manifest_dir = project / ".harness" / "registry" / "manifests"
    for index in range(257):
        (manifest_dir / f"extra-{index}.json").write_text("{}")
    assert cli.main(["registry", "--root", str(project), "list"]) == 2
    assert _json_output(capsys)["code"] == "REGISTRY_SIZE_LIMIT"

    assert cli.main(["route", "--root", str(project)]) == 2
    assert _json_output(capsys)["code"] == "INVALID_INPUT"

    assert (
        cli.main(["registry", "--root", str(tmp_path / "missing"), "inspect", "harness-kernel"])
        == 2
    )
    assert _json_output(capsys)["code"] == "PATH_INVALID"


def test_telemetry_validate_accepts_stdin_and_rejects_bad_events(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    event = create_event(
        event_id="EVT-INPROC-1",
        event_sequence=1,
        timestamp="2026-08-28T12:00:00Z",
        task_id="TASK-INPROC",
        run_id="RUN-INPROC",
        event_type=TelemetryEventType.TASK_RECEIVED,
    )
    document = json.dumps({"events": [to_dict(event)]})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(document))
    assert cli.main(["telemetry", "validate", "-", "--format", "text"]) == 0
    assert capsys.readouterr().out.startswith("PASS telemetry validate:")

    bad = tmp_path / "bad-telemetry.json"
    bad.write_text(json.dumps({"events": [{"schema_version": "TE-1"}]}))
    assert cli.main(["telemetry", "--root", str(tmp_path), "validate", str(bad)]) == 1
    assert _json_output(capsys)["code"] == "INVALID_TELEMETRY"


def test_run_dispatches_dry_run_explain_success_cancel_and_stop(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)

    assert (
        cli.main(["run", "Change one local label", "--dry-run", "--run-id", "RUN-INPROC-DRY"]) == 0
    )
    dry_run = _json_output(capsys)
    assert dry_run["status"] == "DRY_RUN"
    assert dry_run["executed"] is False

    assert (
        cli.main(
            [
                "run",
                "Change one local label",
                "--explain",
                "--json",
                "--run-id",
                "RUN-INPROC-EXPLAIN",
            ]
        )
        == 0
    )
    explain = _json_output(capsys)
    assert explain["explain"]["execution"]["will_execute"] is False

    assert (
        cli.main(
            [
                "run",
                "Change one local label",
                "--provider",
                "local.success",
                "--run-id",
                "RUN-INPROC-SUCCESS",
            ]
        )
        == 0
    )
    success = _json_output(capsys)
    assert success["status"] == "SUCCEEDED"
    assert success["executed"] is True

    assert (
        cli.main(["run", "Change one local label", "--cancelled", "--run-id", "RUN-INPROC-CANCEL"])
        == 1
    )
    cancelled = _json_output(capsys)
    assert cancelled["status"] == "CANCELLED"

    assert (
        cli.main(
            ["run", "Change one local label", "--stop-before-run", "--run-id", "RUN-INPROC-STOP"]
        )
        == 1
    )
    stopped = _json_output(capsys)
    assert stopped["executed"] is False


def test_run_reports_provider_config_and_timeout_errors(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)

    assert (
        cli.main(
            [
                "run",
                "Change one local label",
                "--provider",
                "missing.provider",
                "--run-id",
                "RUN-INPROC-MISSING",
            ]
        )
        == 1
    )
    missing = _json_output(capsys)
    assert missing["failure_category"] == "CAPABILITY_UNAVAILABLE"

    assert (
        cli.main(
            [
                "run",
                "Change one local label",
                "--timeout-ms",
                "6000",
                "--run-id",
                "RUN-INPROC-TIMEOUT",
            ]
        )
        == 2
    )
    assert _json_output(capsys)["code"] == "TIMEOUT_LIMIT"

    config_path = project / ".harness" / "config" / "kernel.json"
    config = json.loads(config_path.read_text())
    config["execution"]["allow_shell"] = True
    config_path.write_text(json.dumps(config))
    assert cli.main(["run", "Change one local label", "--run-id", "RUN-INPROC-SHELL"]) == 2
    assert _json_output(capsys)["code"] == "SANDBOX_POLICY"


def test_run_rejects_invalid_persistent_root_without_writing(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    outside = tmp_path / "outside"
    outside.mkdir()
    assert (
        cli.main(
            [
                "run",
                "Change one local label",
                "--provider",
                "local.success",
                "--root",
                str(outside),
                "--run-id",
                "RUN-INPROC-OUTSIDE",
            ]
        )
        == 2
    )
    payload = _json_output(capsys)
    assert payload["code"] == "PATH_INVALID"
    assert not (outside / ".harness").exists()
