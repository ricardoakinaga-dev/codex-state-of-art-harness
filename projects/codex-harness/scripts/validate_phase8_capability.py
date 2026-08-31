"""Validate the Phase 8 frontend capability package and emit a bound receipt."""

from __future__ import annotations

import argparse
import json
import re
from hashlib import sha256
from pathlib import Path

from harness_kernel.phase7_backend import package_fingerprint

PACKAGE_RELATIVE = Path(".harness/capabilities/frontend-engineering-vnext")
REQUIRED_FILES = (
    "SKILL.md",
    "manifest.json",
    "package-metadata.json",
    "profiles.json",
    "composition-contract.json",
    "scripts/deterministic-procedures.json",
    "evals/scenarios.json",
    "benchmarks/benchmark-fixtures.json",
)
FORBIDDEN_CLAIMS = (
    "PRODUCTION_READY",
    "AAA_VERIFIED",
    "PIXEL_PERFECT",
    "SECURITY_APPROVED",
    "ACCESSIBILITY_CERTIFIED",
    "ALL_BROWSERS_VERIFIED",
    "ALL_VIEWPORTS_VERIFIED",
)
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def _check(name: str, condition: bool, details: str) -> dict[str, object]:
    return {"name": name, "status": "PASS" if condition else "FAIL", "details": details}


def validate(project_root: Path) -> dict[str, object]:
    package = project_root / PACKAGE_RELATIVE
    checks: list[dict[str, object]] = []
    manifest = _json(package / "manifest.json")
    metadata = _json(package / "package-metadata.json")
    procedures = _json(package / "scripts/deterministic-procedures.json")
    scenarios = _json(package / "evals/scenarios.json")["scenarios"]
    benchmark = _json(package / "benchmarks/benchmark-fixtures.json")
    skill = (package / "SKILL.md").read_text(encoding="utf-8")

    required = list(REQUIRED_FILES) + list(metadata["files"]["references"])
    checks.append(
        _check(
            "required_package_files",
            all((package / relative).is_file() for relative in required),
            f"{len(required)} declared files checked",
        )
    )
    checks.append(
        _check(
            "native_specialist_identity",
            manifest.get("capability_id") == "frontend-engineering-vnext"
            and manifest.get("type") == "SPECIALIST"
            and manifest.get("role") == "SPECIALIST"
            and manifest.get("primary_type") == "SPECIALIST"
            and manifest.get("status") == "CANDIDATE",
            "project-local candidate specialist identity",
        )
    )
    execution_policy = manifest.get("execution_policy", {})
    security = manifest.get("security", {})
    checks.append(
        _check(
            "execution_boundary",
            execution_policy.get("shell") == "deny"
            and execution_policy.get("network") == "deny"
            and execution_policy.get("providers") == "deny"
            and execution_policy.get("credentials") == "deny"
            and execution_policy.get("workspace_write") == "host_bounded"
            and manifest.get("metadata_only") is True,
            "shell/network/provider/credential denial and metadata-only package",
        )
    )
    checks.append(
        _check(
            "security_handoff",
            security.get("provider", {}).get("allowed") is False
            and security.get("credential", {}).get("allowed") is False
            and security.get("network", {}).get("allowed") is False,
            "security authority remains a separate handoff",
        )
    )
    checks.append(
        _check(
            "declarative_procedures",
            procedures.get("metadata_only") is True
            and procedures.get("read_only") is True
            and procedures.get("shell") == "deny"
            and procedures.get("network") == "deny"
            and all(item.get("max_attempts") == 1 for item in procedures.get("procedures", [])),
            f"{len(procedures.get('procedures', []))} bounded procedure declarations",
        )
    )
    routes = {item.get("expected_route") for item in scenarios}
    checks.append(
        _check(
            "eval_coverage",
            50 <= len(scenarios) <= 75
            and {"SELECTED", "OMITTED", "BLOCKED", "FALLBACK"} <= routes
            and sum(bool(item.get("negative")) for item in scenarios) >= 12
            and sum(bool(item.get("false_pass_guard")) for item in scenarios) >= 8,
            f"{len(scenarios)} scenarios; routes={sorted(routes)}",
        )
    )
    required_viewports = {(1440, 900), (1024, 768), (768, 1024), (390, 844)}
    actual_viewports = {(item.get("width"), item.get("height")) for item in benchmark["viewports"]}
    checks.append(
        _check(
            "benchmark_viewports",
            actual_viewports == required_viewports,
            f"viewports={sorted(actual_viewports)}",
        )
    )
    checks.append(
        _check(
            "claim_boundary",
            not any(claim in skill for claim in FORBIDDEN_CLAIMS),
            "unsupported promotion and certification claims absent from SKILL.md",
        )
    )
    content_hash = package_fingerprint(package)
    checks.append(
        _check(
            "content_fingerprint",
            bool(SHA256_PATTERN.fullmatch(content_hash)),
            content_hash,
        )
    )
    failed = [item for item in checks if item["status"] != "PASS"]
    return {
        "schema_version": "P8-CAPABILITY-VALIDATION-1",
        "capability_id": manifest.get("capability_id"),
        "version": manifest.get("version"),
        "package_fingerprint": content_hash,
        "manifest_digest": _digest(package / "manifest.json"),
        "skill_bytes": (package / "SKILL.md").stat().st_size,
        "reference_count": len(metadata["files"]["references"]),
        "procedure_count": len(procedures.get("procedures", [])),
        "eval_count": len(scenarios),
        "checks": checks,
        "status": "PASS" if not failed else "FAIL",
        "failed_checks": [item["name"] for item in failed],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = validate(arguments.project_root.resolve(strict=True))
    output = arguments.output
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
