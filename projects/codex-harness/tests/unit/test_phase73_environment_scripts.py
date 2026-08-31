"""Focused tests for Phase 7.3 environment evidence helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from capture_phase73_environment import _version_probe, capture_host  # noqa: E402
from run_phase73_real_cycle import _cycle_status, _is_environment_error  # noqa: E402


def test_version_probe_reports_a_real_executable(tmp_path: Path) -> None:
    executable = tmp_path / "version-probe"
    executable.write_text("#!/bin/sh\necho probe 1.0\n", encoding="utf-8")
    executable.chmod(os.stat(executable).st_mode | 0o111)

    result = _version_probe(executable, ("--version",))

    assert result["status"] == "PASS"
    assert result["exit_code"] == 0


def test_version_probe_reports_missing_executable_without_raising(tmp_path: Path) -> None:
    result = _version_probe(tmp_path / "missing", ("--version",))

    assert result["status"] == "UNAVAILABLE"


def test_cycle_status_distinguishes_failure_and_environment_blocking() -> None:
    assert _cycle_status([]) == "BLOCKED_ENVIRONMENT"
    assert _cycle_status([{"status": "FAIL"}]) == "FAIL"
    assert _cycle_status([{"status": "BLOCKED_ENVIRONMENT"}]) == "BLOCKED_ENVIRONMENT"
    assert _cycle_status([{"status": "PASS_WITH_LIMITATIONS"}]) == "PASS_WITH_LIMITATIONS"
    assert _is_environment_error("host executable is unavailable") is True
    assert _is_environment_error("unexpected protocol assertion") is False


def test_host_capture_records_explicit_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "CODEX_EXECUTABLE",
        "/home/ricardo/.nvm/versions/node/v22.22.2/bin/codex",
    )
    monkeypatch.setenv(
        "NODE_EXECUTABLE",
        "/home/ricardo/.nvm/versions/node/v22.22.2/bin/node",
    )

    manifest = capture_host()

    preflight = manifest["preflight"]
    host = manifest["host"]
    assert isinstance(preflight, dict)
    assert isinstance(host, dict)
    probes = host["version_probes"]
    assert isinstance(probes, dict)
    codex_probe = probes["codex"]
    assert isinstance(codex_probe, dict)
    assert preflight["status"] == "RESOLVED_READ_ONLY_VERSION_PROBE"
    assert codex_probe["status"] == "PASS"
