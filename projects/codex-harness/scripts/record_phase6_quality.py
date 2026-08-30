#!/usr/bin/env python3
"""Run the Phase 6 quality gates and record their observed results."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _tree_digest(root: Path) -> str:
    repo_root = root.parents[1]
    paths: list[Path] = []
    for relative in (
        "src",
        "tests",
        ".harness/capabilities/verification-loop-vnext",
        "scripts",
        "config",
    ):
        paths.extend(
            path
            for path in (root / relative).rglob("*")
            if path.is_file()
            and not {"__pycache__", ".pytest_cache", ".ruff_cache"}.intersection(path.parts)
        )
    paths.append(
        repo_root / "architecture/docs/adr/ADR-015-verification-loop-vnext-modernization.md"
    )
    paths.append(root / "pyproject.toml")
    digest = hashlib.sha256()
    for path in sorted({path.resolve() for path in paths}):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = "../../" + path.relative_to(repo_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return _digest_bytes(digest.digest())


def _run(
    name: str,
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
    )
    stdout = bytes(completed.stdout)
    stderr = bytes(completed.stderr)
    return {
        "name": name,
        "argv": argv,
        "exit_code": completed.returncode,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "elapsed_ms": max(0, int((time.monotonic() - started) * 1000)),
        "stdout_digest": _digest_bytes(stdout),
        "stderr_digest": _digest_bytes(stderr),
        "stdout_tail": stdout.decode("utf-8", errors="replace")[-2_000:],
        "stderr_tail": stderr.decode("utf-8", errors="replace")[-2_000:],
    }


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evidence/phase-6/quality-receipt.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = _args()
    root = args.project_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    python = str(root / ".venv/bin/python")
    ruff = str(root / ".venv/bin/ruff")
    mypy = str(root / ".venv/bin/mypy")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = "src:tests/unit"
    source_before = _tree_digest(root)
    commands = [
        _run(
            "coverage_erase",
            [python, "-m", "coverage", "erase"],
            cwd=root,
        ),
        _run(
            "full_tests",
            [
                python,
                "-m",
                "coverage",
                "run",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
            ],
            cwd=root,
            env=environment,
        ),
        _run("ruff_format", [ruff, "format", "--check", "src", "tests", "scripts"], cwd=root),
        _run("ruff_check", [ruff, "check", "src", "tests", "scripts"], cwd=root),
        _run("mypy_strict", [mypy, "--strict", "src"], cwd=root),
        _run(
            "coverage_gate",
            [python, "-m", "coverage", "report", "--fail-under=80"],
            cwd=root,
        ),
        _run("git_diff_check", ["git", "diff", "--check"], cwd=root.parents[1]),
    ]
    source_after = _tree_digest(root)
    test_output = next(item for item in commands if item["name"] == "full_tests")
    coverage_output = next(item for item in commands if item["name"] == "coverage_gate")
    test_text = str(test_output["stdout_tail"])
    coverage_text = str(coverage_output["stdout_tail"])
    test_match = re.search(r"(?m)(\d+) passed(?:,| in|$)", test_text)
    coverage_matches = re.findall(r"(?m)^TOTAL\s+.*\s(\d+)%\s*$", coverage_text)
    tests_passed = int(test_match.group(1)) if test_match else None
    coverage_percent = float(coverage_matches[-1]) if coverage_matches else None
    coverage_data_path = root / ".coverage"
    coverage_data = coverage_data_path.read_bytes() if coverage_data_path.is_file() else b""
    coverage_data_present = coverage_data_path.is_file() and bool(coverage_data)
    all_passed = all(item["status"] == "PASS" for item in commands) and coverage_data_present
    status = "PASS" if all_passed and source_before == source_after else "FAIL"
    receipt = {
        "schema_version": "P6-QUALITY-RECEIPT-1",
        "status": status,
        "recorded_at": datetime.now(UTC).isoformat(),
        "project_root": root.name,
        "source_tree_digest_before": source_before,
        "source_tree_digest_after": source_after,
        "source_stable": source_before == source_after,
        "tests_passed": tests_passed,
        "coverage_percent": coverage_percent,
        "minimum_coverage_percent": 80.0,
        "coverage_mode": "statement",
        "coverage_collected_fresh": coverage_data_present
        and commands[0]["name"] == "coverage_erase"
        and commands[1]["name"] == "full_tests",
        "coverage_data_path": ".coverage",
        "coverage_data_bytes": len(coverage_data),
        "coverage_data_digest": _digest_bytes(coverage_data) if coverage_data else None,
        "commands": commands,
        "claims_are_command_derived": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"status": status, "tests_passed": tests_passed, "coverage_percent": coverage_percent}
        )
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
