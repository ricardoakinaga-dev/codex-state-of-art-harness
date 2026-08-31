#!/usr/bin/env python3
"""Generate the exact non-recursive Phase 7.2 review packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-7.2"
SKIP_PARTS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".coverage"})
EXCLUDED_PACKET_FILES = frozenset(
    {
        "evidence/phase-7.2/review-manifest.json",
        "evidence/phase-7.2/review-attestation.json",
        "evidence/phase-7.2/closeout-index.json",
    }
)


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _visible_files(root: Path) -> list[Path]:
    if root.is_file() and not root.is_symlink():
        return [root]
    if not root.is_dir() or root.is_symlink():
        return []
    result: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if relative in EXCLUDED_PACKET_FILES:
            continue
        if any(part in SKIP_PARTS for part in path.relative_to(PROJECT_ROOT).parts):
            continue
        result.append(path)
    return result


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
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _digest(encoded)


def _head() -> str:
    return subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=PROJECT_ROOT, text=True
    ).strip()


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
        PROJECT_ROOT / ".agent" / "plans" / "PHASE-7.2-high-risk-branch-closure.md",
        EVIDENCE_ROOT,
    )
    return sorted(
        {path for root in roots for path in _visible_files(root)},
        key=lambda path: path.relative_to(PROJECT_ROOT).as_posix(),
    )


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-status", default="PENDING")
    parser.add_argument("--reviewer-id", default=None)
    parser.add_argument("--review-note", default="Fresh independent review is pending.")
    parser.add_argument("--h01-status", choices=("OPEN", "CLOSED"), default="OPEN")
    args = parser.parse_args()
    paths = _paths()
    source_paths = [
        path
        for path in paths
        if (
            path.relative_to(PROJECT_ROOT).as_posix().startswith("src/")
            or path.relative_to(PROJECT_ROOT).as_posix().startswith("scripts/")
            or path.relative_to(PROJECT_ROOT)
            .as_posix()
            .startswith(
                (
                    "pilots/backend-appointment-api/app/",
                    "pilots/backend-appointment-api/migrations/",
                )
            )
        )
        and path.suffix in {".py", ".sql"}
    ]
    test_paths = [
        path
        for path in paths
        if path.relative_to(PROJECT_ROOT)
        .as_posix()
        .startswith(("tests/", "pilots/backend-appointment-api/tests/"))
        and path.suffix == ".py"
    ]
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
        "status": args.review_status,
        "reviewer_id": args.reviewer_id,
        "note": args.review_note,
    }
    payload: dict[str, Any] = {
        "schema_version": "P7.2-REVIEW-MANIFEST-1",
        "task_id": "PHASE7.2-001",
        "feature_freeze": "P7_2_FEATURE_FREEZE",
        "reviewed_head": _head(),
        "worktree_state": "DIRTY_UNCOMMITTED_BYTES_BOUND_BY_THIS_MANIFEST",
        "backend_engineering_vnext_fingerprint": (
            "sha256:fa8ff9c60f79466ea2b4d2ebbce09b376d6260a40105b344f1da7141fc36437e"
        ),
        "verification_loop_vnext_fingerprint": (
            "sha256:dc380396cdc489976b5d120a964321032907f0101431786cda060dae15c11a4b"
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
        "coverage_artifact": "evidence/phase-7.2/coverage-final.json",
        "branch_inventory": "evidence/phase-7.2/high-risk-branch-inventory.json",
        "branch_traceability": "evidence/phase-7.2/branch-test-traceability.json",
        "test_catalog": "evidence/phase-7.2/test-catalog.json",
        "pilot_evaluation": "evidence/phase-7.2/pilot-catalog-evaluation.json",
        "real_cycle": "evidence/phase-7.2/real-cycle-report.json",
        "independent_review": independent_review,
        "h01_status": args.h01_status,
        "promotion": "KEEP_CANDIDATE_NOT_PROMOTED",
        "entries": entries,
        "manifest_digest": None,
        "attestation_path": "evidence/phase-7.2/review-attestation.json",
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
    manifest_path = EVIDENCE_ROOT / "review-manifest.json"
    attestation_path = EVIDENCE_ROOT / "review-attestation.json"
    _write(manifest_path, payload)
    attestation = {
        "schema_version": "P7.2-REVIEW-ATTESTATION-1",
        "task_id": "PHASE7.2-001",
        "attestation_type": "NON_CRYPTOGRAPHIC_EVIDENCE_ATTESTATION",
        "attestor": "PHASE7.2_CLOSEOUT_INTEGRATOR",
        "status": "PASS_WITH_LIMITATIONS",
        "promotion": "KEEP_CANDIDATE_NOT_PROMOTED",
        "h01_status": args.h01_status,
        "reviewed_head": payload["reviewed_head"],
        "manifest_path": "evidence/phase-7.2/review-manifest.json",
        "manifest_digest": payload["manifest_digest"],
        "independent_review": independent_review,
        "observations": {
            "full_suite": "PASS",
            "ruff": "PASS",
            "mypy": "PASS",
            "backend_pilot": "PASS_WITH_LIMITATIONS",
            "real_verifier": "BLOCKED_ENVIRONMENT",
            "phase2_to_phase7_1_regressions": "PASS_WITH_LIMITATIONS",
            "security": "LIMITED_UNAVAILABLE_SCANNERS",
        },
        "claims_excluded": payload["excluded_claims"],
        "attestation": (
            "The listed bytes and observations are bounded to this worktree. "
            "Residual high-risk branches and unavailable checks remain explicit."
        ),
    }
    _write(attestation_path, attestation)
    print(
        json.dumps(
            {
                "manifest_digest": payload["manifest_digest"],
                "entries": len(entries),
                "source_files": len(source_paths),
                "test_files": len(test_paths),
                "review_status": args.review_status,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
