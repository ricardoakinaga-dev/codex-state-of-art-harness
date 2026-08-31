"""Stage exact project-local capability copies for a bounded Phase 8.1 host run."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from harness_kernel.phase7_backend import package_fingerprint

FRONTEND_RELATIVE = Path(".harness/capabilities/frontend-engineering-vnext")
VERIFIER_RELATIVE = Path(".harness/capabilities/verification-loop-vnext")


def stage(project_root: Path, staging_root: Path, policy_path: Path) -> dict[str, object]:
    staging_root = staging_root.resolve()
    if staging_root.exists() and any(staging_root.iterdir()):
        raise ValueError("Phase 8.1 host staging root must be empty before staging")
    staging_root.mkdir(parents=True, exist_ok=True)

    frontend_source = project_root / FRONTEND_RELATIVE
    verifier_source = project_root / VERIFIER_RELATIVE
    frontend_destination = staging_root / ".agents/skills/frontend-engineering-vnext"
    verifier_destination = staging_root / ".agents/skills/verification-loop-vnext"
    shutil.copytree(frontend_source, frontend_destination)
    shutil.copytree(verifier_source, verifier_destination)
    policy_destination = staging_root / "config/phase8.1-execution-policy.json"
    policy_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(policy_path, policy_destination)

    frontend_source_fingerprint = package_fingerprint(frontend_source)
    frontend_staged_fingerprint = package_fingerprint(frontend_destination)
    verifier_source_fingerprint = package_fingerprint(verifier_source)
    verifier_staged_fingerprint = package_fingerprint(verifier_destination)
    report = {
        "schema_version": "P8.1-HOST-STAGING-1",
        "source_project": str(project_root),
        "staging_root": str(staging_root),
        "frontend_source": str(FRONTEND_RELATIVE),
        "frontend_staged": ".agents/skills/frontend-engineering-vnext",
        "frontend_source_fingerprint": frontend_source_fingerprint,
        "frontend_staged_fingerprint": frontend_staged_fingerprint,
        "frontend_exact_copy": frontend_source_fingerprint == frontend_staged_fingerprint,
        "verifier_source": str(VERIFIER_RELATIVE),
        "verifier_staged": ".agents/skills/verification-loop-vnext",
        "verifier_source_fingerprint": verifier_source_fingerprint,
        "verifier_staged_fingerprint": verifier_staged_fingerprint,
        "verifier_exact_copy": verifier_source_fingerprint == verifier_staged_fingerprint,
        "policy": "config/phase8.1-execution-policy.json",
        "host_skill_root": ".agents/skills",
        "network": "DENY",
        "filesystem": "READ_ONLY",
        "external_producer": False,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    project_root = arguments.project_root.resolve(strict=True)
    policy_path = arguments.policy.resolve(strict=True)
    staging_root = arguments.staging_root
    staging_root = staging_root if staging_root.is_absolute() else project_root / staging_root
    output = arguments.output
    output = output if output.is_absolute() else project_root / output
    report = stage(project_root, staging_root, policy_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["frontend_exact_copy"] and report["verifier_exact_copy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
