"""Capture fresh Phase 3 inspection and compatibility evidence for Phase 8."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _run(project_root: Path, workspace: Path, arguments: list[str]) -> dict[str, object]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(project_root / "src")
    command = [
        sys.executable,
        "-m",
        "harness_kernel.phase3_cli",
        "--project-root",
        str(project_root),
        "--workspace-root",
        str(workspace),
        "--json",
        *arguments,
    ]
    result = subprocess.run(
        command,
        cwd=project_root,
        env=environment,
        text=True,
        capture_output=True,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {
            "status": "ERROR",
            "returncode": result.returncode,
            "stdout": result.stdout[-2_000:],
            "stderr": result.stderr[-2_000:],
        }
    if isinstance(payload, dict):
        payload["command_returncode"] = result.returncode
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("evidence/phase-8"))
    arguments = parser.parse_args()
    project_root = arguments.project_root.resolve(strict=True)
    workspace = arguments.workspace or project_root / "evidence/phase-8/pilots/frontend-engineering"
    workspace = workspace if workspace.is_absolute() else project_root / workspace
    output_dir = arguments.output_dir
    output_dir = output_dir if output_dir.is_absolute() else project_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    inspection = _run(
        project_root,
        workspace.resolve(strict=True),
        ["capabilities", "inspect", "frontend-engineering-vnext", "--explain"],
    )
    compatibility = _run(
        project_root,
        workspace.resolve(strict=True),
        ["capabilities", "compatibility"],
    )
    (output_dir / "phase3-discovery.json").write_text(
        json.dumps(inspection, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "phase3-compatibility.json").write_text(
        json.dumps(compatibility, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"inspection": inspection, "compatibility": compatibility},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    successful = (
        inspection.get("command_returncode") == 0
        and compatibility.get("command_returncode") == 0
    )
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
