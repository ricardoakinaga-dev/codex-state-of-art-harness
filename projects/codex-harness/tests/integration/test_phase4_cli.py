from __future__ import annotations

import json
from pathlib import Path

import harness_kernel.phase4_cli as phase4_cli
from harness_kernel.phase3_host import CodexHostAdapter
from harness_kernel.phase4_cli import main
from harness_kernel.phase4_models import ExecutionMode, public_data
from harness_kernel.phase4_policy import ExecutionPolicyRegistry, PilotRule


def _project_with_policy(tmp_path: Path) -> Path:
    package = tmp_path / ".agents" / "skills" / "safe-pilot"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: safe-pilot\nversion: 0.1.0\n---\nReturn a bounded result.\n",
        encoding="utf-8",
    )
    adapter = CodexHostAdapter(
        project_root=tmp_path,
        home_dir=tmp_path / "no-home",
        codex_home=tmp_path / "no-codex-home",
    )
    record = next(
        item
        for item in adapter.discover_capabilities().capabilities
        if item.capability_id == "safe-pilot"
    )
    config = tmp_path / "config"
    config.mkdir()
    policy = ExecutionPolicyRegistry(
        (
            PilotRule(
                capability_id=record.capability_id,
                version=record.version,
                package_fingerprint=record.content_hash,
                host_executable_digest="sha256:" + "a" * 64,
                host_interpreter_digest="sha256:" + "b" * 64,
                execution_approved=True,
                allowed_modes=(
                    ExecutionMode.DRY_RUN,
                    ExecutionMode.PREPARE_ONLY,
                    ExecutionMode.CONTROLLED_REAL,
                ),
                reason="fixture",
            ),
        )
    )
    (config / "phase4-execution-policy.json").write_text(
        json.dumps(public_data(policy.to_dict()), indent=2), encoding="utf-8"
    )
    return tmp_path


def test_cli_dry_run_is_explicit_and_machine_readable(tmp_path: Path, capsys) -> None:
    project = _project_with_policy(tmp_path)

    exit_code = main(
        [
            "--project-root",
            str(project),
            "invoke",
            "safe-pilot",
            "--task",
            "Return one bounded response.",
            "--dry-run",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["mode"] == "DRY_RUN"
    assert output["host_invoked"] is False


def test_cli_returns_failure_exit_code_for_non_success_terminal_statuses(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        phase4_cli,
        "_run_invoke",
        lambda arguments: {
            "schema_version": "P4-OUTCOME-1",
            "mode": "CONTROLLED_REAL",
            "status": "FAILURE",
            "host_invoked": True,
        },
    )

    exit_code = phase4_cli.main(
        [
            "invoke",
            "safe-pilot",
            "--task",
            "Return one bounded response.",
            "--controlled-real",
            "--json",
        ]
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().out)["status"] == "FAILURE"


def test_cli_real_mode_without_fingerprint_confirmation_is_blocked(tmp_path: Path, capsys) -> None:
    project = _project_with_policy(tmp_path)

    exit_code = main(
        [
            "--project-root",
            str(project),
            "invoke",
            "safe-pilot",
            "--task",
            "Return one bounded response.",
            "--controlled-real",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert output["status"] == "BLOCKED"
    assert "FINGERPRINT_CONFIRMATION_REQUIRED" in output["blockers"]
    assert output["host_invoked"] is False
