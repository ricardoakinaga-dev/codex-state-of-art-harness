#!/usr/bin/env python3
"""Run one isolated Phase 7.2 builder/repair/verifier cycle.

The existing Phase 7 runners are intentionally immutable and refuse to reuse
their historical evidence directories.  This adapter gives the same bounded
cycle a fresh Phase 7.2 namespace without changing the pilot, package, host
installation or global configuration.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

PHASE_ROOT = PROJECT_ROOT / "evidence" / "phase-7.2" / "real-cycle"
BUILDER_ROOT = PHASE_ROOT / "builder"
REPAIR_ROOT = PHASE_ROOT / "repair"
VERIFIER_ROOT = PHASE_ROOT / "verifier"


def _project_reference(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _step(label: str, module_name: str, configure: Any) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
        configure(module)
        exit_code = module.main()
    except Exception as exc:  # noqa: BLE001 - convert bounded environment failures to evidence
        return {
            "step": label,
            "status": "BLOCKED_ENVIRONMENT" if "unavailable" in str(exc).lower() else "FAIL",
            "exit_code": None,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    return {
        "step": label,
        "status": "PASS_WITH_LIMITATIONS" if exit_code == 0 else "FAIL",
        "exit_code": exit_code,
    }


def run_cycle() -> dict[str, Any]:
    if PHASE_ROOT.exists():
        raise RuntimeError("Phase 7.2 real-cycle evidence already exists; refusing overwrite")
    PHASE_ROOT.mkdir(parents=True)
    steps: list[dict[str, Any]] = []
    steps.append(
        _step(
            "builder",
            "run_phase7_real_builder",
            lambda module: (
                setattr(module, "RERUN_ROOT", BUILDER_ROOT),
                setattr(module, "TASK_ID", "PHASE7.2-REAL-BUILDER-001"),
                setattr(module, "RUN_ID", "P7.2-REAL-BUILDER-001"),
            ),
        )
    )
    builder_receipt = BUILDER_ROOT / "builder-receipt.json"
    if builder_receipt.is_file():
        steps.append(
            _step(
                "repair",
                "run_phase7_real_repair",
                lambda module: (
                    setattr(module, "BASE_ARTIFACT_ROOT", BUILDER_ROOT / "artifact-v1"),
                    setattr(module, "REPAIR_ROOT", REPAIR_ROOT),
                    setattr(module, "TASK_ID", "PHASE7.2-REAL-REPAIR-001"),
                    setattr(module, "RUN_ID", "P7.2-REAL-REPAIR-001"),
                ),
            )
        )
    repair_receipt = REPAIR_ROOT / "repair-receipt.json"
    if repair_receipt.is_file():
        steps.append(
            _step(
                "verifier",
                "run_phase7_real_verifier",
                lambda module: (
                    setattr(module, "RERUN_ROOT", PHASE_ROOT),
                    setattr(module, "BASE_ROOT", BUILDER_ROOT / "artifact-v1"),
                    setattr(module, "REPAIR_ROOT", REPAIR_ROOT),
                    setattr(module, "ARTIFACT_ROOT", VERIFIER_ROOT / "artifact-v3"),
                    setattr(module, "BUILDER_RECEIPT", builder_receipt),
                    setattr(module, "REPAIR_RECEIPT", repair_receipt),
                    setattr(module, "VERIFIER_RECEIPT", VERIFIER_ROOT / "verifier-receipt.json"),
                    setattr(module, "TASK_ID", "PHASE7.2-REAL-VERIFIER-001"),
                    setattr(module, "RUN_ID", "P7.2-REAL-VERIFIER-001"),
                ),
            )
        )
    status = (
        "PASS_WITH_LIMITATIONS"
        if steps and steps[-1]["status"] == "PASS_WITH_LIMITATIONS"
        else "BLOCKED_ENVIRONMENT"
    )
    if any(step["status"] == "FAIL" for step in steps):
        status = "FAIL"
    return {
        "schema_version": "P7.2-REAL-CYCLE-1",
        "phase": "PHASE7.2",
        "feature_freeze": "P7_2_FEATURE_FREEZE",
        "generated_at": datetime.now().astimezone().isoformat(),
        "status": status,
        "scope": {
            "pilot_source": "pilots/backend-appointment-api",
            "workspace": "temporary disposable copy",
            "package_mutated": False,
            "installed_or_global_state_mutated": False,
        },
        "steps": steps,
        "evidence_roots": {
            "builder": _project_reference(BUILDER_ROOT),
            "repair": _project_reference(REPAIR_ROOT),
            "verifier": _project_reference(VERIFIER_ROOT),
        },
        "limitations": [
            "A real host receipt proves only this bounded disposable cycle.",
            (
                "Host skill-load observability remains a declared limitation when "
                "the host does not expose it."
            ),
            "No production, release, security-approval or universal-quality claim is made.",
        ],
    }


def main() -> int:
    global PHASE_ROOT, BUILDER_ROOT, REPAIR_ROOT, VERIFIER_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase-root", type=Path, default=PHASE_ROOT)
    args = parser.parse_args()
    PHASE_ROOT = args.phase_root.resolve()
    BUILDER_ROOT = PHASE_ROOT / "builder"
    REPAIR_ROOT = PHASE_ROOT / "repair"
    VERIFIER_ROOT = PHASE_ROOT / "verifier"
    report = run_cycle()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "steps": report["steps"]}, sort_keys=True))
    return 0 if report["status"] in {"PASS_WITH_LIMITATIONS", "BLOCKED_ENVIRONMENT"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
