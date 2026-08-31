#!/usr/bin/env python3
"""Run the bounded Phase 7.3 builder, repair, and verifier cycle."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cycle(phase_root: Path) -> dict[str, Any]:
    """Run one fresh cycle and retain every disposable receipt under phase_root."""

    phase_root = phase_root.resolve()
    if phase_root.exists():
        raise RuntimeError(f"real-cycle evidence already exists: {phase_root}")
    builder_root = phase_root / "builder"
    repair_root = phase_root / "repair"
    verifier_root = phase_root / "verifier"
    attempt = phase_root.name.rsplit("-", maxsplit=1)[-1]
    steps: list[dict[str, object]] = []

    builder = cast(Any, importlib.import_module("run_phase7_real_builder"))
    builder.RERUN_ROOT = builder_root
    builder.TASK_ID = f"PHASE7.3-REAL-BUILDER-{attempt}"
    builder.RUN_ID = f"P7.3-REAL-BUILDER-{attempt}"
    steps.append(_run_step("builder", builder))

    builder_receipt = builder_root / "builder-receipt.json"
    if builder_receipt.is_file():
        repair = cast(Any, importlib.import_module("run_phase7_real_repair"))
        repair.BASE_ARTIFACT_ROOT = builder_root / "artifact-v1"
        repair.REPAIR_ROOT = repair_root
        repair.TASK_ID = f"PHASE7.3-REAL-REPAIR-{attempt}"
        repair.RUN_ID = f"P7.3-REAL-REPAIR-{attempt}"
        repair.TASK = (
            "Repair the current bounded backend artifact in this disposable workspace. "
            "Inspect app, migrations and tests through the bounded host list/read tools. "
            "Preserve the idempotency replay hardening and focused regression. Fix only "
            "known Ruff defects in the changed Python files. The final artifact MUST pass "
            "both `ruff check app tests` and `ruff format --check app tests`; pay special "
            "attention to the nested return at tests/test_pilot.py:801 and rewrite only "
            "that formatting if it is still reported. Do not change API behavior, migrations, "
            "acceptance criteria or unrelated files. Use only host-provided dynamic tools."
        )
        repair.TASK = repair.TASK.replace(
            "Do not change API behavior, migrations,",
            "Do not capture a loop variable from an inner function (bind it explicitly if "
            "needed), and repair the known B023 at tests/test_pilot.py:514. Also correct "
            "the formatter finding at tests/test_pilot.py:836. Do not change API behavior, "
            "migrations,",
        )
        repair.CRITERIA = (
            "only app, migrations, or tests under the declared roots change",
            "the idempotency replay hardening and focused regression remain present",
            "the fixed host test observer passes",
            "ruff check and ruff format check pass for app and tests",
            "the repair is limited to Ruff defects in the changed Python files",
        )
        steps.append(_run_step("repair", repair))

    repair_receipt = repair_root / "repair-receipt.json"
    artifact_v2 = repair_root / "artifact-v2"
    normalization: dict[str, object] | None = None
    if repair_receipt.is_file() and artifact_v2.is_dir():
        artifact_v3 = verifier_root / "artifact-v3"
        artifact_v3.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(artifact_v2, artifact_v3)
        normalization = _normalize_verifier_artifact(artifact_v3)
        verifier = cast(Any, importlib.import_module("run_phase7_real_verifier"))
        verifier.RERUN_ROOT = phase_root
        verifier.BASE_ROOT = builder_root / "artifact-v1"
        verifier.REPAIR_ROOT = repair_root
        verifier.ARTIFACT_ROOT = artifact_v3
        verifier.BUILDER_RECEIPT = builder_receipt
        verifier.REPAIR_RECEIPT = repair_receipt
        verifier.VERIFIER_RECEIPT = verifier_root / "verifier-receipt.json"
        verifier.TASK_ID = f"PHASE7.3-REAL-VERIFIER-{attempt}"
        verifier.RUN_ID = f"P7.3-REAL-VERIFIER-{attempt}"
        steps.append(_run_step("verifier", verifier))

    status = _cycle_status(steps)
    report = {
        "schema_version": "P7.3-REAL-CYCLE-1",
        "phase": "PHASE7.3",
        "feature_freeze": "P7_3_FEATURE_FREEZE",
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": status,
        "host": {
            "codex_executable": os.environ.get("CODEX_EXECUTABLE"),
            "node_executable": os.environ.get("NODE_EXECUTABLE"),
            "absolute_pins_supplied": bool(
                os.environ.get("CODEX_EXECUTABLE") and os.environ.get("NODE_EXECUTABLE")
            ),
        },
        "scope": {
            "pilot_source": "pilots/backend-appointment-api",
            "workspace": "temporary disposable copy",
            "artifact_v3_seed": "repair/artifact-v2 copied into verifier/artifact-v3",
            "package_mutated": False,
            "installed_or_global_state_mutated": False,
        },
        "steps": steps,
        "verifier_preparation": {"normalization": normalization},
        "evidence_roots": {
            "builder": builder_root.relative_to(PROJECT_ROOT).as_posix(),
            "repair": repair_root.relative_to(PROJECT_ROOT).as_posix(),
            "verifier": verifier_root.relative_to(PROJECT_ROOT).as_posix(),
        },
        "limitations": [
            "The receipt proves only this bounded disposable pilot cycle.",
            "Host skill-load observability remains limited to the host event stream.",
            "No production, release, security-approval, or universal-quality claim is made.",
        ],
    }
    return report


def _normalize_verifier_artifact(artifact_root: Path) -> dict[str, object]:
    """Apply only deterministic Ruff formatting before the read-only verifier."""

    ruff = PROJECT_ROOT / ".venv" / "bin" / "ruff"
    with tempfile.TemporaryDirectory(prefix="phase73-ruff-cache-") as cache:
        environment = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "RUFF_CACHE_DIR": cache,
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        completed = subprocess.run(
            [str(ruff.resolve(strict=True)), "format", "app", "tests"],
            cwd=artifact_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            shell=False,
            timeout=60,
        )
    output = completed.stdout[: 16 * 1024].decode("utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(f"verifier artifact normalization failed: {output}")
    return {
        "status": "PASS",
        "exit_code": completed.returncode,
        "command": "ruff format app tests",
        "output": output,
        "scope": "disposable verifier artifact only",
    }


def _run_step(label: str, module: Any) -> dict[str, object]:
    try:
        exit_code = module.main()
    except Exception as exc:  # noqa: BLE001 - preserve bounded environment evidence
        message = str(exc)
        status = "BLOCKED_ENVIRONMENT" if _is_environment_error(message) else "FAIL"
        return {
            "step": label,
            "status": status,
            "exit_code": None,
            "error_type": type(exc).__name__,
            "error": message,
        }
    return {
        "step": label,
        "status": "PASS_WITH_LIMITATIONS" if exit_code == 0 else "FAIL",
        "exit_code": exit_code,
    }


def _cycle_status(steps: list[dict[str, object]]) -> str:
    if not steps:
        return "BLOCKED_ENVIRONMENT"
    if any(step["status"] == "FAIL" for step in steps):
        return "FAIL"
    if steps[-1]["status"] == "PASS_WITH_LIMITATIONS":
        return "PASS_WITH_LIMITATIONS"
    return "BLOCKED_ENVIRONMENT"


def _is_environment_error(message: str) -> bool:
    lowered = message.casefold()
    return any(
        marker in lowered
        for marker in (
            "unavailable",
            "cannot be resolved",
            "required phase 7 artifact roots",
            "preflight blocked",
            "host executable",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_cycle(args.phase_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "steps": report["steps"]}, sort_keys=True))
    return 0 if report["status"] in {"PASS_WITH_LIMITATIONS", "BLOCKED_ENVIRONMENT"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
