"""Build the byte-bound Phase 7 closeout controls.

This project-local script creates only evidence controls. It does not execute
the pilot, invoke a host, mutate installed capabilities, or modify global
configuration. Closure JSON deliberately excludes itself and the other
closure controls from the source-entry digest to avoid circular hashes.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "backend-engineering-vnext"
CLOSEOUT_ROOT = PROJECT_ROOT / "evidence" / "phase-7" / "closeout"
WORKSPACE_SCOPE = PROJECT_ROOT.parent.parent
FINAL_GATE_PATH = PROJECT_ROOT / ".agent" / "gates" / "PHASE7-FINAL-FAIL-0001.json"

CLOSURE_CONTROL_FILES = frozenset(
    {
        "review-manifest.json",
        "review-attestation.json",
        "readiness.json",
        "gate.json",
        "final-report.md",
    }
)
SKIP_PARTS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})
SKIP_SUFFIXES = frozenset({".pyc", ".pyo"})


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _label(path: Path) -> str:
    resolved = path.resolve(strict=True)
    for scope in (PROJECT_ROOT, WORKSPACE_SCOPE):
        try:
            resolved.relative_to(scope)
        except ValueError:
            continue
        return Path(os.path.relpath(resolved, PROJECT_ROOT)).as_posix()
    raise RuntimeError(f"closeout input escapes the workspace scope: {path}")


def _entry(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"closeout input must be a regular non-symlink file: {path}")
    payload = path.read_bytes()
    return {"path": _label(path), "sha256": _sha256_bytes(payload), "bytes": len(payload)}


def _add_file(entries: dict[str, dict[str, Any]], path: Path) -> None:
    item = _entry(path)
    entries[item["path"]] = item


def _add_tree(entries: dict[str, dict[str, Any]], root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        _add_file(entries, path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def main() -> int:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from harness_kernel.phase7_backend import package_fingerprint

    package_digest = package_fingerprint(PACKAGE_ROOT)
    entries: dict[str, dict[str, Any]] = {}

    _add_tree(entries, PACKAGE_ROOT)
    _add_tree(entries, PROJECT_ROOT / "pilots" / "backend-appointment-api" / "app")
    _add_tree(entries, PROJECT_ROOT / "pilots" / "backend-appointment-api" / "migrations")
    for path in (
        PROJECT_ROOT / "pilots" / "backend-appointment-api" / "README.md",
        PROJECT_ROOT / "pilots" / "backend-appointment-api" / "pyproject.toml",
        PROJECT_ROOT / "pilots" / "backend-appointment-api" / "tests" / "test_pilot.py",
    ):
        _add_file(entries, path)
    _add_tree(entries, PROJECT_ROOT / "tests" / "evals" / "phase7")
    for relative in (
        "config/phase7-execution-policy.json",
        "scripts/build_phase7_closeout.py",
        "scripts/run_phase7_evals.py",
        "src/harness_kernel/phase4_host.py",
        "src/harness_kernel/phase4_policy.py",
        "src/harness_kernel/phase7_backend.py",
        "src/harness_kernel/phase7_host.py",
        "tests/unit/test_phase4_policy.py",
        "tests/unit/test_phase7_backend.py",
        "tests/unit/test_phase7_host.py",
        ".agent/plans/PHASE-7-backend-engineering-modernization.md",
        ".agent/gates/PHASE7-SCOPE-READY-0001.json",
        ".agent/gates/PHASE7-TECHNICALLY-SPECIFIED-0001.json",
        ".agent/gates/PHASE7-IMPLEMENTATION-READY-0001.json",
        "evidence/phase-7/P7-QB-1.md",
        "evidence/phase-7/README.md",
        "evidence/phase-7/current-backend-patterns-snapshot.json",
        "evidence/phase-7/current-capability-analysis.md",
        "evidence/phase-7/upstream-analysis.md",
        "evidence/phase-7/native-capability-gap-analysis.md",
        "evidence/phase-7/modernization-plan.md",
        "evidence/phase-7/architecture-contract-report.md",
        "evidence/phase-7/api-data-boundary-report.md",
        "evidence/phase-7/migration-safety-report.md",
        "evidence/phase-7/reliability-report.md",
        "evidence/phase-7/security-handoff-report.md",
        "evidence/phase-7/test-strategy-report.md",
        "evidence/phase-7/phase2-regression.md",
        "evidence/phase-7/phase3-regression.md",
        "evidence/phase-7/phase4-regression.md",
        "evidence/phase-7/phase5-regression.md",
        "evidence/phase-7/phase6-regression.md",
        "../../architecture/docs/adr/ADR-016-backend-engineering-vnext-modernization.md",
    ):
        _add_file(entries, PROJECT_ROOT / relative)
    _add_tree(entries, CLOSEOUT_ROOT)
    for name in CLOSURE_CONTROL_FILES:
        entries.pop(f"evidence/phase-7/closeout/{name}", None)

    ordered_entries = [entries[key] for key in sorted(entries)]
    entries_digest = _sha256_bytes(
        json.dumps(
            ordered_entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
    observed_at = _now()
    manifest: dict[str, Any] = {
        "schema_version": "P7-REVIEW-MANIFEST-1",
        "task_id": "PHASE7-001",
        "phase": "PHASE7",
        "status": "FAIL",
        "promotion": "NOT_PROMOTED",
        "observed_at": observed_at,
        "package": {
            "capability_id": "backend-engineering-vnext",
            "version": "0.1.0",
            "path": ".harness/capabilities/backend-engineering-vnext",
            "fingerprint": package_digest,
        },
        "authority": "CLOSEOUT_EVIDENCE_INTEGRATOR",
        "entry_policy": {
            "hash": "sha256 over exact bytes",
            "paths": (
                "project-relative, with approved architecture input paths "
                "retained as ../.. references"
            ),
            "symlinks": "rejected",
            "generated_caches": "excluded",
        },
        "entries": ordered_entries,
        "entry_count": len(ordered_entries),
        "entries_digest": entries_digest,
        "historical_exclusions": [
            "evidence/phase-7/vnext-package-report.md",
            "evidence/phase-7/promotion-decision.md",
            "evidence/phase-7/real-backend-pilot-report.md",
            "evidence/phase-7/verification-composition-report.md",
            "evidence/phase-7/composition-value-report.md",
            "evidence/phase-7/eval-report.md",
            "evidence/phase-7/benchmark-report.md",
            "evidence/phase-7/benchmark-summary.json",
            "evidence/phase-7/coverage-report.md",
            "evidence/phase-7/security-summary.md",
            "evidence/phase-7/evidence-binding-check.json",
            "evidence/phase-7/installed-mutation-check.json",
            "evidence/phase-7/* historical receipts and artifact claims outside closeout",
        ],
        "closure_controls_excluded_from_entries": sorted(CLOSURE_CONTROL_FILES),
        "required_gate_status": {
            "P7-01": "PASS",
            "P7-02_to_P7-20": "PASS_WITH_LIMITATIONS",
            "P7-21": "NOT_CLOSED_CURRENT_RECEIPT_MISSING",
            "P7-22": "NOT_CLOSED_CURRENT_RECEIPT_MISSING",
            "P7-23": "FAIL_NO_BUILDER_ARTIFACT",
            "P7-24": "FAIL_MISSING_BUILDER_HANDOFF",
            "P7-25": "FAIL_STRICT_REPAIR_ORDER_NOT_ESTABLISHED",
            "P7-26": "FAIL_NO_REBOUND_ARTIFACT_VERIFICATION",
            "P7-27": "PASS_WITH_LIMITATIONS",
            "P7-28": "PASS",
            "P7-29": "PASS_WITH_LIMITATIONS",
            "P7-30": "FAIL_EXACT_FINAL_REVIEW_UNRESOLVED",
            "P7-31": "PASS_WITH_LIMITATIONS",
        },
        "claim_policy": {
            "aaa_verified": False,
            "production_ready": False,
            "causal_improvement": False,
            "security_approval": False,
            "release_approval": False,
            "universal_superiority": False,
        },
    }
    manifest_path = CLOSEOUT_ROOT / "review-manifest.json"
    _write_json(manifest_path, manifest)
    manifest_digest = _sha256_file(manifest_path)

    attestation: dict[str, Any] = {
        "schema_version": "P7-REVIEW-ATTESTATION-1",
        "task_id": "PHASE7-001",
        "observed_at": observed_at,
        "attestation_type": "NON_CRYPTOGRAPHIC_EVIDENCE_ATTESTATION",
        "attestor": "CLOSEOUT_EVIDENCE_INTEGRATOR",
        "manifest_path": "evidence/phase-7/closeout/review-manifest.json",
        "manifest_digest": manifest_digest,
        "package_fingerprint": package_digest,
        "status": "FAIL",
        "promotion": "NOT_PROMOTED",
        "independent_review": {
            "capability": "PACKAGE_CANDIDATE_ONLY",
            "composition": "FAIL",
            "exact_post_repair_reapproval": "NOT_OBTAINED",
        },
        "attestation": (
            "The listed bytes and observations are the complete closeout boundary. "
            "Missing builder artifact, current builder receipts and exact post-repair "
            "independent reapproval prevent promotion."
        ),
        "claims_excluded": [
            "AAA_QUALITY",
            "HARNESS_AAA_VERIFIED",
            "production_readiness",
            "causal_improvement",
            "security_approval",
            "release_approval",
        ],
    }
    attestation_path = CLOSEOUT_ROOT / "review-attestation.json"
    _write_json(attestation_path, attestation)
    attestation_digest = _sha256_file(attestation_path)

    readiness: dict[str, Any] = {
        "schema_version": "P7-READINESS-1",
        "task_id": "PHASE7-001",
        "observed_at": observed_at,
        "manifest_digest": manifest_digest,
        "attestation_digest": attestation_digest,
        "candidate_support": "P7_LEVEL_A_CANDIDATE",
        "promotable_support": None,
        "status": "FAIL",
        "promotion": "NOT_PROMOTED",
        "levels": {
            "P7_LEVEL_A": {
                "candidate": True,
                "promoted": False,
                "reason": (
                    "Package contract and current catalog pass, but exact closeout "
                    "review is not a promotion authority."
                ),
            },
            "P7_LEVEL_B": {
                "candidate": False,
                "promoted": False,
                "reason": (
                    "No builder artifact/receipt and no complete builder-to-verifier handoff."
                ),
            },
            "P7_LEVEL_C": {
                "candidate": False,
                "promoted": False,
                "reason": (
                    "Strict independent critic, one repair and fresh rebound final "
                    "verification chain is incomplete."
                ),
            },
        },
        "blocking_facts": [
            "P7-23: no current builder artifact after two builder invocations and one repair",
            "P7-24: verifier semantic stop is BLOCKED/MISSING_REQUIRED_ARTIFACT",
            "P7-30: exact post-repair independent re-review is not available",
            "P7-31: no PHASE7-FROZEN marker is authorized for a failed gate",
        ],
        "observed_green": [
            "48/48 package scenarios with full known-bad guards",
            "26 pilot tests and 90% app-only coverage",
            "549 Harness tests and 81% combined line coverage",
            "current Phase 2–6 regression suites green",
            "Ruff and strict mypy green",
            "real verifier transport read-only with zero workspace delta",
        ],
        "aaa_verified": False,
    }
    readiness_path = CLOSEOUT_ROOT / "readiness.json"
    _write_json(readiness_path, readiness)
    readiness_digest = _sha256_file(readiness_path)

    gate: dict[str, Any] = {
        "schema_version": "P7-FINAL-GATE-1",
        "gate_id": "PHASE7-FINAL-FAIL-0001",
        "task_id": "PHASE7-001",
        "observed_at": observed_at,
        "status": "FAIL",
        "promotion": "NOT_PROMOTED",
        "candidate_support": "P7_LEVEL_A_CANDIDATE",
        "promoted_support": None,
        "package_fingerprint": package_digest,
        "manifest_digest": manifest_digest,
        "attestation_digest": attestation_digest,
        "readiness_digest": readiness_digest,
        "criteria": manifest["required_gate_status"],
        "blocking_facts": readiness["blocking_facts"],
        "decision": (
            "Close Phase 7 as FAIL/NOT_PROMOTED. Preserve the additive package and "
            "local pilot as a candidate for a separately authorized host-capability "
            "rerun; do not spend a third builder attempt or create a freeze marker."
        ),
        "claims_excluded": attestation["claims_excluded"],
    }
    gate_path = CLOSEOUT_ROOT / "gate.json"
    _write_json(gate_path, gate)
    FINAL_GATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_json(FINAL_GATE_PATH, gate)
    print(
        json.dumps(
            {
                "status": "FAIL",
                "promotion": "NOT_PROMOTED",
                "package_fingerprint": package_digest,
                "manifest_digest": manifest_digest,
                "attestation_digest": attestation_digest,
                "readiness_digest": readiness_digest,
                "entry_count": len(ordered_entries),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
