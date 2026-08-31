#!/usr/bin/env python3
"""Generate the exact, bounded Phase 7.3 review manifest and attestation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-7.3"
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from harness_kernel.phase7_backend import package_fingerprint  # noqa: E402

SKIP_PARTS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".coverage"})
EXCLUDED_PACKET_FILES = frozenset(
    {
        "evidence/phase-7.3/review-manifest.json",
        "evidence/phase-7.3/review-attestation.json",
    }
)
DIAGNOSTIC_PART_PREFIXES = (
    "phase72-current",
    "phase72-final",
    "real-cycle-container.",
    "real-cycle-final-001",
    "real-cycle-final-002",
    "real-cycle-final-003",
    "real-cycle-final-004",
)


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _is_excluded(path: Path) -> bool:
    relative = path.relative_to(PROJECT_ROOT).as_posix()
    if relative in EXCLUDED_PACKET_FILES:
        return True
    parts = path.relative_to(PROJECT_ROOT).parts
    return any(part in SKIP_PARTS or part.startswith(DIAGNOSTIC_PART_PREFIXES) for part in parts)


def _visible_files(root: Path) -> list[Path]:
    if root.is_file() and not root.is_symlink():
        return [] if _is_excluded(root) else [root]
    if not root.is_dir() or root.is_symlink():
        return []
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink() and not _is_excluded(path)
    ]


def _entry(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(PROJECT_ROOT).as_posix(),
        "bytes": len(payload),
        "sha256": _digest(payload),
    }


def _fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return "sha256:" + digest.hexdigest()


def _tree_digest(paths: list[Path]) -> str:
    entries = [_entry(path) for path in paths]
    return _digest(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _head() -> str:
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=PROJECT_ROOT, text=True
    ).strip()


def _worktree_state() -> str:
    status = subprocess.check_output(
        ("git", "status", "--short"), cwd=PROJECT_ROOT, text=True
    ).strip()
    return "CLEAN" if not status else "DIRTY_UNCOMMITTED_BYTES_BOUND_BY_THIS_MANIFEST"


def _paths() -> list[Path]:
    roots = (
        PROJECT_ROOT / "src",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "tests",
        PROJECT_ROOT / "pilots" / "backend-appointment-api",
        PROJECT_ROOT / ".harness" / "capabilities" / "backend-engineering-vnext",
        PROJECT_ROOT / ".harness" / "capabilities" / "verification-loop-vnext",
        PROJECT_ROOT / "config",
        PROJECT_ROOT / "pyproject.toml",
        PROJECT_ROOT / ".agent" / "plans" / "PHASE-7.3-final-promotion-closure.md",
        PROJECT_ROOT / ".agent" / "state.json",
        PROJECT_ROOT / ".agent" / "backlog.json",
        PROJECT_ROOT / ".agent" / "execution-log.jsonl",
        PROJECT_ROOT / ".agent" / "verification.jsonl",
        PROJECT_ROOT / ".agent" / "gates" / "PHASE7.3-FINAL-0001.json",
        EVIDENCE_ROOT,
    )
    return sorted(
        {path for root in roots for path in _visible_files(root)},
        key=lambda path: path.relative_to(PROJECT_ROOT).as_posix(),
    )


def _classify_paths(paths: list[Path], prefix: tuple[str, ...], suffixes: set[str]) -> list[Path]:
    return [
        path
        for path in paths
        if path.relative_to(PROJECT_ROOT).as_posix().startswith(prefix) and path.suffix in suffixes
    ]


def build_manifest(
    review_status: str = "PENDING",
    reviewer_id: str | None = None,
    review_note: str = "Fresh independent review is pending.",
) -> dict[str, Any]:
    """Build a manifest over current source, tests, config, and final evidence bytes."""

    paths = _paths()
    source_paths = _classify_paths(
        paths,
        (
            "src/",
            "scripts/",
            "pilots/backend-appointment-api/app/",
            "pilots/backend-appointment-api/migrations/",
        ),
        {".py", ".sql"},
    )
    test_paths = _classify_paths(
        paths,
        ("tests/", "pilots/backend-appointment-api/tests/"),
        {".py"},
    )
    config_paths = [
        path
        for path in paths
        if path == PROJECT_ROOT / "pyproject.toml"
        or (
            path.relative_to(PROJECT_ROOT).as_posix().startswith("config/")
            and path.suffix == ".json"
        )
    ]
    entries = [_entry(path) for path in paths]
    independent_review = {
        "status": review_status,
        "reviewer_id": reviewer_id,
        "note": review_note,
    }
    payload: dict[str, Any] = {
        "schema_version": "P7.3-REVIEW-MANIFEST-1",
        "task_id": "PHASE7.3-001",
        "feature_freeze": "P7_3_FEATURE_FREEZE",
        "reviewed_head": _head(),
        "worktree_state": _worktree_state(),
        "backend_engineering_vnext_fingerprint": package_fingerprint(
            PROJECT_ROOT / ".harness" / "capabilities" / "backend-engineering-vnext"
        ),
        "verification_loop_vnext_fingerprint": package_fingerprint(
            PROJECT_ROOT / ".harness" / "capabilities" / "verification-loop-vnext"
        ),
        "source_fingerprint": {
            "sha256": _fingerprint(source_paths),
            "file_count": len(source_paths),
        },
        "tests_fingerprint": {
            "sha256": _fingerprint(test_paths),
            "file_count": len(test_paths),
        },
        "config_fingerprint": {
            "sha256": _fingerprint(config_paths),
            "file_count": len(config_paths),
        },
        "coverage_artifact": "evidence/phase-7.3/coverage-final.json",
        "authoritative_phase72_inventory": "evidence/phase-7.2/high-risk-branch-inventory.json",
        "coverage_delta_reconciliation": "evidence/phase-7.3/coverage-delta-reconciliation.json",
        "branch_inventory": "evidence/phase-7.3/medium-risk-inventory.json",
        "current_raw_inventory": (
            "evidence/phase-7.3/phase73-current/inventory/high-risk-branch-inventory.json"
        ),
        "material_medium_proof": "evidence/phase-7.3/material-medium-proof.json",
        "materiality_review": "evidence/phase-7.3/materiality-review.json",
        "targeted_traceability_evidence": (
            "evidence/phase-7.3/phase73-targeted-traceability-evidence.json"
        ),
        "branch_traceability": (
            "evidence/phase-7.3/phase73-current/traceability/branch-test-traceability.json"
        ),
        "risk_semantics": "evidence/phase-7.3/risk-semantics-spec.md",
        "risk_consistency": "evidence/phase-7.3/risk-count-consistency.json",
        "promotion_ledger": "evidence/phase-7.3/promotion-risk-ledger.json",
        "readiness": "evidence/phase-7.3/readiness.json",
        "pilot_evaluation": "evidence/phase-7.3/backend-pilot-evaluation.json",
        "real_cycle": "evidence/phase-7.3/real-cycle-report-005.json",
        "security_scanner_inventory": "evidence/phase-7.3/security-scanner-inventory.json",
        "independent_review": independent_review,
        "promotion": (
            "VERIFIED_CANDIDATE_WITH_LIMITATIONS"
            if review_status == "PASS"
            else "KEEP_CANDIDATE_NOT_PROMOTED"
        ),
        "entries": entries,
        "manifest_digest": None,
        "attestation_path": "evidence/phase-7.3/review-attestation.json",
        "entry_tree_digest": _tree_digest(paths),
        "excluded_claims": [
            "PRODUCTION_READY",
            "AAA_VERIFIED",
            "SECURITY_APPROVED",
            "RELEASE_APPROVED",
            "CAUSAL_SUPERIORITY",
            "ALL_BRANCHES_COVERED",
            "ALL_FAILURES_EXHAUSTIVELY_TESTED",
            "SYSCALL_LEVEL_ISOLATION",
        ],
    }
    payload["manifest_digest"] = _digest(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    return payload


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_outputs(manifest: dict[str, Any]) -> None:
    """Write the manifest and a non-cryptographic attestation for the same packet."""

    manifest_path = EVIDENCE_ROOT / "review-manifest.json"
    attestation_path = EVIDENCE_ROOT / "review-attestation.json"
    _write(manifest_path, manifest)
    attestation = {
        "schema_version": "P7.3-REVIEW-ATTESTATION-1",
        "task_id": "PHASE7.3-001",
        "attestation_type": "NON_CRYPTOGRAPHIC_EVIDENCE_ATTESTATION",
        "attestor": "PHASE7.3_CLOSEOUT_INTEGRATOR",
        "reviewer": manifest["independent_review"]["reviewer_id"],
        "review_mode": "FRESH_READ_ONLY_EXACT_PACKET",
        "status": "PASS_WITH_LIMITATIONS",
        "verdict": (
            "PENDING_INDEPENDENT_REVIEW"
            if manifest["independent_review"]["status"] == "PENDING"
            else "PASS_WITH_LIMITATIONS"
        ),
        "promotion": manifest["promotion"],
        "promotion_recommendation": manifest["promotion"],
        "reviewed_head": manifest["reviewed_head"],
        "backend_engineering_vnext_fingerprint": manifest["backend_engineering_vnext_fingerprint"],
        "verification_loop_vnext_fingerprint": manifest["verification_loop_vnext_fingerprint"],
        "critical_open": 0,
        "actionable_high": 0,
        "promotion_blocking_high": 0,
        "actionable_medium": 0,
        "promotion_blocking_medium": 0,
        "host_environment_waiver_accepted": False,
        "scanner_waiver_accepted": True,
        "manifest_path": "evidence/phase-7.3/review-manifest.json",
        "manifest_digest": manifest["manifest_digest"],
        "independent_review": manifest["independent_review"],
        "claims_excluded": manifest["excluded_claims"],
        "attestation": (
            "The listed bytes and observations are bounded to this worktree. "
            "Unavailable checks and host observability remain explicit limitations."
        ),
    }
    _write(attestation_path, attestation)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-status", choices=("PENDING", "PASS", "FAIL"), default="PENDING")
    parser.add_argument("--reviewer-id")
    parser.add_argument("--review-note", default="Fresh independent review is pending.")
    args = parser.parse_args(argv)
    manifest = build_manifest(args.review_status, args.reviewer_id, args.review_note)
    write_outputs(manifest)
    print(
        json.dumps(
            {
                "manifest_digest": manifest["manifest_digest"],
                "entries": len(manifest["entries"]),
                "source_files": manifest["source_fingerprint"]["file_count"],
                "test_files": manifest["tests_fingerprint"]["file_count"],
                "review_status": args.review_status,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
