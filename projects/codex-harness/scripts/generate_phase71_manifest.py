"""Generate the non-recursive Phase 7.1 review manifest and attestation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-7.1"
MANIFEST_PATH = EVIDENCE_ROOT / "review-manifest.json"
ATTESTATION_PATH = EVIDENCE_ROOT / "review-attestation.json"
CLOSEOUT_INDEX_PATH = EVIDENCE_ROOT / "closeout-index.json"
SKIP_PARTS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".coverage"})


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _visible_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if not root.is_dir() or root.is_symlink():
        return []
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and path not in {MANIFEST_PATH, ATTESTATION_PATH, CLOSEOUT_INDEX_PATH}
        and not any(part in SKIP_PARTS for part in path.relative_to(PROJECT_ROOT).parts)
    ]


def _entry(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(PROJECT_ROOT).as_posix(),
        "bytes": len(payload),
        "sha256": _digest(payload),
    }


def _tree_digest(paths: list[Path]) -> str:
    ordered = [_entry(path) for path in paths]
    return _digest(json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _fingerprint(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return "sha256:" + digest.hexdigest()


def _git_head() -> str:
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
        PROJECT_ROOT / ".agent" / "plans" / "PHASE-7.1-branch-hardening.md",
        PROJECT_ROOT / "evidence" / "phase-7",
        PROJECT_ROOT / "evidence" / "phase-7.1",
    )
    return sorted(
        {path for root in roots for path in _visible_files(root)},
        key=lambda item: item.relative_to(PROJECT_ROOT).as_posix(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-status", default="PENDING")
    parser.add_argument("--reviewer-id", default=None)
    parser.add_argument("--review-note", default="Independent review result is pending.")
    args = parser.parse_args()

    paths = _paths()
    promotion = (
        "KEEP_CANDIDATE_NOT_PROMOTED"
        if args.review_status == "FAIL"
        else "PENDING_INDEPENDENT_REVIEW"
    )
    source_paths = [
        path
        for path in paths
        if path.relative_to(PROJECT_ROOT)
        .as_posix()
        .startswith(
            (
                "src/",
                "scripts/",
                "pilots/backend-appointment-api/app/",
                "pilots/backend-appointment-api/migrations/",
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
    payload: dict[str, Any] = {
        "schema_version": "P7.1-REVIEW-MANIFEST-1",
        "task_id": "PHASE7.1-001",
        "feature_freeze": "P7_1_FEATURE_FREEZE",
        "reviewed_head": _git_head(),
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
        "coverage_artifact": "evidence/phase-7.1/coverage-final.json",
        "branch_inventory": "evidence/phase-7.1/branch-inventory.json",
        "independent_review": {
            "status": args.review_status,
            "reviewer_id": args.reviewer_id,
            "note": args.review_note,
        },
        "entries": entries,
        "manifest_digest": None,
        "attestation_path": "evidence/phase-7.1/review-attestation.json",
        "entry_tree_digest": _tree_digest(paths),
    }
    canonical = dict(payload)
    canonical["manifest_digest"] = None
    payload["manifest_digest"] = _digest(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    attestation = {
        "schema_version": "P7.1-REVIEW-ATTESTATION-1",
        "task_id": "PHASE7.1-001",
        "attestation_type": "NON_CRYPTOGRAPHIC_EVIDENCE_ATTESTATION",
        "attestor": "PHASE7.1_CLOSEOUT_INTEGRATOR",
        "status": "PASS_WITH_LIMITATIONS",
        "promotion": promotion,
        "manifest_path": "evidence/phase-7.1/review-manifest.json",
        "manifest_digest": payload["manifest_digest"],
        "independent_review": payload["independent_review"],
        "claims_excluded": [
            "PRODUCTION_READY",
            "AAA_VERIFIED",
            "SECURITY_APPROVED",
            "RELEASE_APPROVED",
            "CAUSAL_SUPERIORITY",
            "ALL_FAILURE_PATHS_EXHAUSTIVELY_TESTED",
        ],
        "attestation": (
            "The listed bytes and observations are bounded to this worktree and "
            "preserve unavailable checks as limitations."
        ),
    }
    ATTESTATION_PATH.write_text(
        json.dumps(attestation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "manifest_digest": payload["manifest_digest"],
                "entries": len(entries),
                "status": args.review_status,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
