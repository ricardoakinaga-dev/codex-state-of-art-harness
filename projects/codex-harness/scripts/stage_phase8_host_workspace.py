"""Stage an exact copy of the vNext package into an official skill root for the pilot."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from harness_kernel.phase7_backend import package_fingerprint

PACKAGE_RELATIVE = Path(".harness/capabilities/frontend-engineering-vnext")
VERIFIER_PACKAGE_RELATIVE = Path(".harness/capabilities/verification-loop-vnext")
SKILL_NAME = "frontend-engineering-vnext"
VERIFIER_NAME = "verification-loop-vnext"


def stage(project_root: Path, pilot_root: Path) -> dict[str, object]:
    source = project_root / PACKAGE_RELATIVE
    destination = pilot_root / ".agents/skills" / SKILL_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    policy_source = project_root / "config/phase8-execution-policy.json"
    policy_destination = pilot_root / "config/phase8-execution-policy.json"
    policy_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(policy_source, policy_destination)
    source_fingerprint = package_fingerprint(source)
    staged_fingerprint = package_fingerprint(destination)
    verifier_source = project_root / VERIFIER_PACKAGE_RELATIVE
    verifier_destination = pilot_root / ".agents/skills" / VERIFIER_NAME
    shutil.copytree(verifier_source, verifier_destination, dirs_exist_ok=True)
    verifier_source_fingerprint = package_fingerprint(verifier_source)
    verifier_staged_fingerprint = package_fingerprint(verifier_destination)
    report = {
        "schema_version": "P8-HOST-STAGING-1",
        "source_package": str(PACKAGE_RELATIVE),
        "staged_package": str(destination.relative_to(pilot_root)),
        "source_fingerprint": source_fingerprint,
        "staged_fingerprint": staged_fingerprint,
        "exact_copy": source_fingerprint == staged_fingerprint,
        "verifier_source_package": str(VERIFIER_PACKAGE_RELATIVE),
        "verifier_staged_package": str(verifier_destination.relative_to(pilot_root)),
        "verifier_source_fingerprint": verifier_source_fingerprint,
        "verifier_staged_fingerprint": verifier_staged_fingerprint,
        "verifier_exact_copy": verifier_source_fingerprint == verifier_staged_fingerprint,
        "policy": str(policy_destination.relative_to(pilot_root)),
        "host_skill_root": ".agents/skills",
        "network": "DENY",
        "filesystem": "READ_ONLY",
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--pilot-root",
        type=Path,
        default=Path("evidence/phase-8/pilots/frontend-engineering"),
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    project_root = arguments.project_root.resolve(strict=True)
    pilot_root = arguments.pilot_root
    pilot_root = pilot_root if pilot_root.is_absolute() else project_root / pilot_root
    report = stage(project_root, pilot_root.resolve(strict=True))
    if arguments.output is not None:
        output = arguments.output
        output = output if output.is_absolute() else project_root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if report["exact_copy"] and report["verifier_exact_copy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
