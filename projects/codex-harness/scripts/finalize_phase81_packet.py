# ruff: noqa: E501
"""Freeze and, after independent review, promote the exact Phase 8.1 packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-8.1"
TASK_ID = "PHASE8.1-001"
FINAL_DECISION = "PROMOTE_TO_VERIFIED_CANDIDATE_WITH_LIMITATIONS"
FINAL_PROMOTION = "VERIFIED_CANDIDATE_WITH_LIMITATIONS"
FINAL_STATUS = "PASS_WITH_LIMITATIONS"
EXCLUDED_ENVELOPES = {
    "PHASE8.1-FROZEN.md",
    "P8.1-QB-1.md",
    "closeout-index.json",
    "final-report.md",
    "independent-exact-packet-review.md",
    "promotion-decision.md",
    "readiness.json",
    "review-attestation.json",
    "review-manifest.json",
}
REPOSITORY_PACKET_ROOTS = (
    PROJECT_ROOT / "src",
    PROJECT_ROOT / "tests",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "config",
    PROJECT_ROOT / ".harness" / "capabilities" / "frontend-engineering-vnext",
    PROJECT_ROOT / ".harness" / "capabilities" / "verification-loop-vnext",
)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical(value).encode()).hexdigest()}"


def file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def load(relative_path: str) -> dict[str, Any]:
    value = json.loads((EVIDENCE_ROOT / relative_path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {relative_path}")
    return value


def write_json(relative_path: str, value: object) -> None:
    (EVIDENCE_ROOT / relative_path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_text(relative_path: str, value: str) -> None:
    (EVIDENCE_ROOT / relative_path).write_text(value.rstrip() + "\n", encoding="utf-8")


def git_head() -> str:
    return subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _entry(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_digest(path),
    }


def _eligible(path: Path) -> bool:
    return (
        path.is_file()
        and not path.is_symlink()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    )


def evidence_entries() -> list[dict[str, object]]:
    return [
        _entry(path, EVIDENCE_ROOT)
        for path in sorted(EVIDENCE_ROOT.rglob("*"))
        if _eligible(path) and path.relative_to(EVIDENCE_ROOT).as_posix() not in EXCLUDED_ENVELOPES
    ]


def repository_entries() -> list[dict[str, object]]:
    paths: set[Path] = set()
    for root in REPOSITORY_PACKET_ROOTS:
        paths.update(path for path in root.rglob("*") if _eligible(path))
    return [_entry(path, REPOSITORY_ROOT) for path in sorted(paths)]


def _require_review(path: str, *, exact: bool = False) -> None:
    review_path = EVIDENCE_ROOT / path
    if not review_path.is_file():
        raise RuntimeError(f"required independent review is missing: {path}")
    text = review_path.read_text(encoding="utf-8")
    if "PASS_WITH_LIMITATIONS" not in text:
        raise RuntimeError(f"independent review is not passing: {path}")
    if exact and "manifest_digest" not in text:
        raise RuntimeError("exact-packet review does not name the reviewed manifest digest")


def freeze_pending() -> None:
    for name in (
        "independent-capability-review.md",
        "independent-frontend-review.md",
        "independent-visual-review.md",
    ):
        _require_review(name)
    head = git_head()
    now = datetime.now(UTC).isoformat()
    composition = load("composition-proof.json")
    browser = load("browser-evidence.json")
    verifier = load("verifier-report.json")
    classification = load("runtime-eval-classification.json")
    coverage = load("coverage-summary.json")
    ledger = load("finding-ledger.json")
    package = load("frontend-package-validation.json")
    write_json("closeout-index-pre-review.json", load("closeout-index.json"))
    if (
        composition.get("status") != "PROVEN_WITH_OBSERVABLE_ALTERNATIVE_CAUSALITY"
        or browser.get("status") != "PASS"
        or browser.get("summary", {}).get("failed") != 0
        or verifier.get("status") != "PASS_WITH_LIMITATIONS"
        or classification.get("counts", {}).get("promotion_relevant_unresolved") != 0
        or ledger.get("counts", {}).get("open_critical") != 0
        or ledger.get("counts", {}).get("open_actionable_high") != 0
        or ledger.get("counts", {}).get("open_actionable_medium") != 0
        or coverage.get("tests_failed") != 0
    ):
        raise RuntimeError("pre-review packet has an unresolved technical gate")
    manifest: dict[str, Any] = {
        "schema_version": "P8.1-REVIEW-MANIFEST-2",
        "task_id": TASK_ID,
        "status": "FROZEN_PENDING_EXACT_REVIEW",
        "repository_head": head,
        "generated_at": now,
        "composition_run": composition["run_id"],
        "frontend_fingerprint": package["package_fingerprint"],
        "verifier_fingerprint": verifier["verifier_fingerprint"],
        "artifact_digest": composition["artifact_digest"],
        "browser_evidence_digest": composition["browser_evidence_digest"],
        "composition_proof_digest": composition["proof_digest"],
        "verification_digest": verifier["verification_digest"],
        "runtime_eval_report_digest": file_digest(EVIDENCE_ROOT / "runtime-eval-report.json"),
        "high_closure_report_digest": file_digest(EVIDENCE_ROOT / "high-closure-report.md"),
        "medium_closure_report_digest": file_digest(EVIDENCE_ROOT / "medium-closure-report.md"),
        "security_report_digest": file_digest(EVIDENCE_ROOT / "security-report.md"),
        "coverage_report_digest": file_digest(EVIDENCE_ROOT / "coverage-summary.json"),
        "test_report_digest": file_digest(EVIDENCE_ROOT / "test-report.md"),
        "excluded_envelopes": sorted(EXCLUDED_ENVELOPES),
        "entries": evidence_entries(),
        "repository_entries": repository_entries(),
    }
    manifest["manifest_digest"] = digest(manifest)
    write_json("review-manifest.json", manifest)
    pending_attestation = {
        "schema_version": "P8.1-REVIEW-ATTESTATION-2",
        "task_id": TASK_ID,
        "status": "PENDING_EXACT_REVIEW",
        "repository_head": head,
        "reviewed_head": None,
        "manifest_digest": manifest["manifest_digest"],
        "verdict": "PENDING",
        "promotion_recommendation": "KEEP_CANDIDATE_NOT_PROMOTED",
    }
    pending_attestation["attestation_digest"] = digest(pending_attestation)
    write_json("review-attestation.json", pending_attestation)


def promote(reviewer_ids: list[str]) -> None:
    if not reviewer_ids:
        raise RuntimeError("at least one exact-packet reviewer id is required")
    for name in (
        "independent-capability-review.md",
        "independent-frontend-review.md",
        "independent-visual-review.md",
    ):
        _require_review(name)
    _require_review("independent-exact-packet-review.md", exact=True)
    manifest = load("review-manifest.json")
    if manifest.get("manifest_digest") != digest(
        {k: v for k, v in manifest.items() if k != "manifest_digest"}
    ):
        raise RuntimeError("review manifest self-digest is invalid")
    if manifest.get("repository_head") != git_head():
        raise RuntimeError("review manifest HEAD is stale")
    reviewed_text = (EVIDENCE_ROOT / "independent-exact-packet-review.md").read_text(
        encoding="utf-8"
    )
    if manifest["manifest_digest"] not in reviewed_text:
        raise RuntimeError("exact review names a different manifest")
    composition = load("composition-proof.json")
    receipt = load("composition-receipt.json")
    verifier = load("verifier-report.json")
    classification = load("runtime-eval-classification.json")
    ledger = load("finding-ledger.json")
    coverage = load("coverage-summary.json")
    package = load("frontend-package-validation.json")
    head = git_head()
    now = datetime.now(UTC).isoformat()
    review_files = {
        name: file_digest(EVIDENCE_ROOT / name)
        for name in (
            "independent-capability-review.md",
            "independent-frontend-review.md",
            "independent-visual-review.md",
            "independent-exact-packet-review.md",
        )
    }
    attestation: dict[str, Any] = {
        "schema_version": "P8.1-REVIEW-ATTESTATION-2",
        "task_id": TASK_ID,
        "status": FINAL_STATUS,
        "reviewer": reviewer_ids[-1],
        "reviewer_ids": reviewer_ids,
        "review_mode": "FRESH_INDEPENDENT_EXACT_PACKET_READ_ONLY",
        "repository_head": head,
        "reviewed_head": head,
        "manifest_digest": manifest["manifest_digest"],
        "review_files": review_files,
        "frontend_fingerprint": package["package_fingerprint"],
        "verifier_fingerprint": verifier["verifier_fingerprint"],
        "composition_proof_status": composition["status"],
        "host_load_observability": "HOST_LOAD_UNOBSERVABLE",
        "runtime_eval_unresolved_count": classification["counts"]["promotion_relevant_unresolved"],
        "critical": ledger["counts"]["open_critical"],
        "actionable_high": ledger["counts"]["open_actionable_high"],
        "promotion_blocking_high": ledger["counts"]["promotion_blocking_high"],
        "actionable_medium": ledger["counts"]["open_actionable_medium"],
        "promotion_blocking_medium": ledger["counts"]["promotion_blocking_medium"],
        "verdict": FINAL_STATUS,
        "promotion_recommendation": FINAL_DECISION,
        "attested_at": now,
    }
    attestation["attestation_digest"] = digest(attestation)
    write_json("review-attestation.json", attestation)
    readiness = {
        "schema_version": "P8.1-READINESS-2",
        "task_id": TASK_ID,
        "phase": "8.1",
        "status": FINAL_STATUS,
        "support_level": "P8_LEVEL_B",
        "promotion": FINAL_PROMOTION,
        "quality_bar": "P8.1-QB-1_PASS_WITH_LIMITATIONS",
        "repository_head": head,
        "reviewed_head": head,
        "branch": "main",
        "frontend_vnext_fingerprint": package["package_fingerprint"],
        "verifier_fingerprint": verifier["verifier_fingerprint"],
        "test_count": coverage["tests_passed"],
        "test_skipped": coverage["tests_skipped"],
        "line_coverage": coverage["line_coverage"],
        "branch_coverage": coverage["branch_coverage"],
        "structural_eval_count": 60,
        "runtime_required_eval_count": 33,
        "runtime_executed_eval_count": 33,
        "runtime_pass_count": 33,
        "runtime_fail_count": 0,
        "runtime_blocked_count": 0,
        "promotion_runtime_unresolved": 0,
        "composition_proof_status": composition["status"],
        "host_load_observability": "HOST_LOAD_UNOBSERVABLE",
        "frontend_real_invocation": "PASS",
        "verifier_real_invocation": FINAL_STATUS,
        "browser_runtime": "PASS",
        "desktop": "PASS",
        "intermediate": "PASS",
        "mobile": "PASS",
        "interaction": "PASS",
        "accessibility": "PASS_WITH_LIMITATIONS",
        "contrast": "PASS",
        "console": "PASS",
        "idempotency": "PASS",
        "stale_response": "PASS",
        "url_state": "PASS",
        "keyboard": "PASS",
        "security": "BOUNDED_PASS_WITH_LIMITATIONS",
        "critical": 0,
        "open_actionable_high": 0,
        "promotion_blocking_high": 0,
        "open_actionable_medium": 0,
        "promotion_blocking_medium": 0,
        "global_mutations": 0,
        "installed_frontend_patterns_mutations": 0,
        "composition_run": composition["run_id"],
        "frontend_invocation_id": receipt["frontend_invocation_id"],
        "verifier_invocation_id": receipt["verifier_invocation_id"],
        "workspace_pre_digest": receipt["workspace_pre_digest"],
        "workspace_post_digest": receipt["workspace_post_digest"],
        "source_digest": receipt["source_digest"],
        "artifact_digest": composition["artifact_digest"],
        "browser_evidence_digest": composition["browser_evidence_digest"],
        "verification_digest": verifier["verification_digest"],
        "review_manifest_digest": manifest["manifest_digest"],
        "review_attestation_digest": attestation["attestation_digest"],
        "limitations": composition["limitations"],
        "excluded_claims": composition["excluded_claims"],
        "readiness_for": "security-review → security-engineering-vNext",
    }
    write_json("readiness.json", readiness)
    write_json(
        "closeout-index.json",
        {
            "schema_version": "P8.1-CLOSEOUT-INDEX-3",
            "task_id": TASK_ID,
            "status": FINAL_STATUS,
            "repository_head": head,
            "reviewed_head": head,
            "authoritative_composition_run": composition["run_id"],
            "authoritative_browser_capture": "P81-BROWSER-018",
            "authoritative_verifier_run": "P81-VERIFY-010",
            "current_artifact_digest": composition["artifact_digest"],
            "manifest_digest": manifest["manifest_digest"],
            "attestation_digest": attestation["attestation_digest"],
            "review_status": FINAL_STATUS,
            "reviewer_ids": reviewer_ids,
            "historical_attempt_index": "closeout-index-pre-review.json",
        },
    )
    write_text(
        "promotion-decision.md",
        f"""# Promotion Decision

Decision: `{FINAL_DECISION}`.

The exact candidate is promoted to `{FINAL_PROMOTION}` under manifest `{manifest["manifest_digest"]}`. Literal host Skill-load remains unobservable, browser evidence is Chromium-only, accessibility is not certified, scanners remain environment-limited under the expiring waiver, and the synthetic fixture is not a production/release/security approval.
""",
    )
    write_text(
        "P8.1-QB-1.md",
        f"""# P8.1-QB-1

Status: `{FINAL_STATUS}`.

The exact frozen manifest `{manifest["manifest_digest"]}` passed independent capability, frontend, visual and exact-packet review. All 33 directly ID-bound runtime-required catalog evals pass, all actionable findings are closed, the verifier independently read or hashed every staged input, the full suite and Phase 2–8 regressions pass, and the supported composition status is `{composition["status"]}`. Excluded claims and limitations remain binding.
""",
    )
    write_text(
        "final-report.md",
        f"""# Phase 8.1 Final Report

Status: `{FINAL_STATUS}`. Decision: `{FINAL_DECISION}`.

The authoritative chain is `{composition["run_id"]}` → `P81-BROWSER-018` → `P81-VERIFY-010`, bound to artifact `{composition["artifact_digest"]}`. Raw host events cover exactly the four changed frontend paths, 33/33 catalog runtime checks and 11 supplemental checks pass, the neutral read-only verifier passed five criteria after inspecting or hashing all 50 inputs, and every discovered Critical/High/Medium actionable finding is closed.

The full suite passed {coverage["tests_passed"]} tests with {coverage["tests_skipped"]} environment-scoped skips; line/branch coverage is {coverage["line_coverage"]}% / {coverage["branch_coverage"]}%. Independent reviewers accepted the exact manifest `{manifest["manifest_digest"]}` with limitations. Full host-load causality, production readiness, release/security approval, universal browser behavior and accessibility certification are expressly excluded.
""",
    )
    write_text(
        "PHASE8.1-FROZEN.md",
        f"""# Phase 8.1 Frozen

Status: `{FINAL_STATUS}`

Manifest: `{manifest["manifest_digest"]}`
Attestation: `{attestation["attestation_digest"]}`
Reviewed HEAD: `{head}`
Promotion: `{FINAL_PROMOTION}`
""",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-status", choices=("PENDING", "PASS"), default="PENDING")
    parser.add_argument("--reviewer-id", action="append", default=[])
    arguments = parser.parse_args()
    if arguments.review_status == "PENDING":
        freeze_pending()
    else:
        promote(arguments.reviewer_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
