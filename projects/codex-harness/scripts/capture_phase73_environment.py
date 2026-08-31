#!/usr/bin/env python3
"""Capture bounded Phase 7.3 host and scanner availability evidence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from harness_kernel.phase4_host import HostProtocolError, _resolve_host_binding
from harness_kernel.phase7_backend import package_fingerprint

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
SCANNERS = (
    "pip-audit",
    "bandit",
    "semgrep",
    "trivy",
    "safety",
    "osv-scanner",
    "grype",
    "syft",
    "gitleaks",
    "detect-secrets",
    "snyk",
    "cargo-audit",
)


def capture_host() -> dict[str, object]:
    """Capture immutable host paths, versions, hashes, and bounded capabilities."""

    manifest: dict[str, object] = {
        "schema_version": "P7.3-HOST-BOOTSTRAP-MANIFEST-1",
        "phase": "PHASE7.3",
        "captured_at": datetime.now().astimezone().isoformat(),
        "environment_class": "LOCAL_DEVELOPMENT",
        "working_directory": str(PROJECT_ROOT),
        "safe_path": SAFE_PATH,
        "environment_overrides": {
            "CODEX_EXECUTABLE": os.environ.get("CODEX_EXECUTABLE"),
            "NODE_EXECUTABLE": os.environ.get("NODE_EXECUTABLE"),
        },
        "capability_roots": {
            "project": str(PROJECT_ROOT),
            "source": str(PROJECT_ROOT / "src"),
            "tests": str(PROJECT_ROOT / "tests"),
            "pilot": str(PROJECT_ROOT / "pilots" / "backend-appointment-api"),
            "backend_package": str(
                PROJECT_ROOT / ".harness" / "capabilities" / "backend-engineering-vnext"
            ),
            "verifier_package": str(
                PROJECT_ROOT / ".harness" / "capabilities" / "verification-loop-vnext"
            ),
        },
        "execution_policy": {
            "config": "config/phase7-execution-policy.json",
            "mode": "CONTROLLED_REAL",
            "workspace": "disposable pilot copy",
            "network": "DENY",
            "shell": "DENY",
            "mcp": "DENY",
            "providers": "DENY",
            "credentials": "DENY",
            "installed_or_global_mutation": False,
        },
        "package_fingerprints": {
            "backend-engineering-vnext": package_fingerprint(
                PROJECT_ROOT / ".harness" / "capabilities" / "backend-engineering-vnext"
            ),
            "verification-loop-vnext": package_fingerprint(
                PROJECT_ROOT / ".harness" / "capabilities" / "verification-loop-vnext"
            ),
        },
        "preflight": {},
    }

    try:
        binding = _resolve_host_binding()
    except (HostProtocolError, OSError, RuntimeError) as exc:
        manifest["preflight"] = {
            "status": "BLOCKED_ENVIRONMENT",
            "classification": "HOST_PATH_UNRESOLVED_OR_ENVIRONMENT_CONFIG",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        return manifest

    command, executable, executable_digest, pinned_files, interpreter, interpreter_digest = binding
    manifest["host"] = {
        "executable": executable,
        "executable_digest": executable_digest,
        "interpreter": interpreter,
        "interpreter_digest": interpreter_digest,
        "command": list(command),
        "pinned_files": [{"path": path, "sha256": digest} for path, digest in pinned_files],
        "version_probes": {
            "codex": _version_probe(Path(executable), ("--version",)),
            "node": _version_probe(Path(interpreter), ("--version",))
            if interpreter is not None
            else {"status": "NOT_APPLICABLE"},
        },
    }
    manifest["preflight"] = {
        "status": "RESOLVED_READ_ONLY_VERSION_PROBE",
        "classification": "HOST_PATH_RESOLVED",
        "full_cycle": "scripts/run_phase73_real_cycle.py",
    }
    return manifest


def capture_scanners() -> dict[str, object]:
    """Record scanner availability without installing or contacting registries."""

    entries: dict[str, object] = {}
    for name in SCANNERS:
        path = shutil.which(name)
        if path is None:
            entries[name] = {"status": "UNAVAILABLE", "path": None}
            continue
        entries[name] = {
            "status": "AVAILABLE",
            "path": path,
            "version_probe": _version_probe(Path(path), ("--version",)),
        }
    available = sum(
        1
        for value in entries.values()
        if isinstance(value, Mapping) and value.get("status") == "AVAILABLE"
    )
    return {
        "schema_version": "P7.3-SECURITY-SCANNER-INVENTORY-1",
        "phase": "PHASE7.3",
        "captured_at": datetime.now().astimezone().isoformat(),
        "policy": {
            "installation_allowed": False,
            "network_allowed": False,
            "unavailable_is_pass": False,
        },
        "scanners": entries,
        "available_count": available,
        "unavailable_count": len(entries) - available,
    }


def _version_probe(path: Path | None, arguments: tuple[str, ...]) -> dict[str, object]:
    if path is None:
        return {"status": "NOT_APPLICABLE"}
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file() or path.is_symlink():
            return {"status": "UNAVAILABLE", "error": "not a regular executable"}
        completed = subprocess.run(
            [str(resolved), *arguments],
            cwd=PROJECT_ROOT,
            env={
                "PATH": SAFE_PATH,
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            shell=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "UNAVAILABLE", "error": type(exc).__name__}
    output = completed.stdout[:4096].decode("utf-8", errors="replace").strip()
    return {
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "output": output,
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-output", type=Path, required=True)
    parser.add_argument("--scanner-output", type=Path, required=True)
    args = parser.parse_args()
    _write_json(args.host_output, capture_host())
    _write_json(args.scanner_output, capture_scanners())
    print(
        json.dumps(
            {"host": str(args.host_output), "scanners": str(args.scanner_output)},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
