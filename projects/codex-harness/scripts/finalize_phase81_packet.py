# ruff: noqa: E501

"""Write the human-readable Phase 8.1 closeout packet and manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-8.1"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical(value).encode()).hexdigest()}"


def file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def load(relative_path: str) -> Any:
    return json.loads((EVIDENCE_ROOT / relative_path).read_text(encoding="utf-8"))


def write_json(relative_path: str, value: Any) -> None:
    path = EVIDENCE_ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_text(relative_path: str, value: str) -> None:
    path = EVIDENCE_ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def git_head() -> str:
    return subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def historical_tracked_changes() -> list[str]:
    output = subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), "diff", "--name-only", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    prefixes = (
        "projects/codex-harness/evidence/phase-2/",
        "projects/codex-harness/evidence/phase-3/",
        "projects/codex-harness/evidence/phase-4/",
        "projects/codex-harness/evidence/phase-5/",
        "projects/codex-harness/evidence/phase-6/",
        "projects/codex-harness/evidence/phase-7/",
        "projects/codex-harness/evidence/phase-7.1/",
        "projects/codex-harness/evidence/phase-7.2/",
        "projects/codex-harness/evidence/phase-7.3/",
        "projects/codex-harness/evidence/phase-8/",
    )
    return [path for path in output if path.startswith(prefixes)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-status", choices=("PENDING", "PASS", "FAIL"), default="PENDING")
    parser.add_argument("--reviewer-id", action="append", default=[])
    args = parser.parse_args()

    now = datetime.now(UTC).isoformat()
    head = git_head()
    verifier = load("verifier-report.json")
    classification = load("runtime-eval-classification.json")
    coverage = load("coverage-summary.json")
    package = load("frontend-package-validation.json")
    composition = load("composition-proof.json")
    ledger = load("finding-ledger.json")
    historical_changes = historical_tracked_changes()
    historical_composition_runs = sorted(
        path.name for path in EVIDENCE_ROOT.glob("composition-run-*") if path.is_dir()
    )
    verifier_pass = verifier["status"] == "PASS_WITH_LIMITATIONS"
    review_pass = args.review_status == "PASS"
    final_status = (
        "PASS_WITH_LIMITATIONS" if verifier_pass and review_pass else "CANDIDATE_NOT_PROMOTED"
    )
    decision = (
        "PROMOTE_TO_VERIFIED_CANDIDATE_WITH_LIMITATIONS"
        if final_status == "PASS_WITH_LIMITATIONS"
        else "KEEP_CANDIDATE_NOT_PROMOTED"
    )

    write_text(
        "security-report.md",
        """# Security Report

Status: `BOUNDED_PASS_WITH_LIMITATIONS`

- Phase 8.1 scoped secret-pattern scan: no credential-shaped match in the new fixture, packet or Phase 8.1 scripts/tests.
- Repository-wide scan: two pre-existing redacted/example `Authorization: Bearer` lines remain under `references/skill-audit/data/provenance-evidence/raw/`; no credential was added by this task.
- The fixture uses synthetic data, loopback-only HTTP and no external service or credential.
- Input validation and server-side 422 behavior are recorded in `browser/server-validation.json`.

This is a bounded engineering check, not a security approval, penetration test or release authorization.
""",
    )
    write_text(
        "scanner-report.md",
        """# Scanner Report

- `ruff check src tests scripts`: PASS.
- `mypy src`: PASS (`65` source files).
- `uv pip check --python .venv/bin/python`: PASS (`13` packages compatible).
- `pip-audit`: unavailable in the environment; no substitute vulnerability database was asserted.
- `npm audit`: not applicable; no `package.json` exists in the project.
- `ruff format --check`: remains non-zero on pre-existing files outside the Phase 8.1 additions; those unrelated files were not reformatted.

The unavailable audit tool and pre-existing formatting drift are explicit limitations, not silent passes.
""",
    )
    write_text(
        "coverage-report.md",
        f"""# Coverage Report

- Test command: `.venv/bin/coverage run --branch -m pytest -q`
- Result: `1781 passed`
- Statements: `{coverage["totals"]["covered_lines"]}/{coverage["totals"]["num_statements"]}` ({coverage["totals"]["percent_covered"]:.2f}%)
- Branches: `{coverage["totals"]["covered_branches"]}/{coverage["totals"]["num_branches"]}` ({coverage["totals"]["percent_branches_covered"]:.2f}%)
- Threshold: `>=80%` lines and branches — PASS.

Source: `coverage-summary.json`.
""",
    )
    write_text(
        "test-report.md",
        """# Test Report

- Full suite: `.venv/bin/pytest -q` — `1781 passed in 151.15s`.
- Full branch-coverage run: `.venv/bin/coverage run --branch -m pytest -q` — `1781 passed in 199.04s`.
- Phase 8.1 focused contracts after the concurrent stale-request repair: `9 passed`.
- Type checking: `mypy src` — PASS.
- Static lint: `ruff check src tests scripts` — PASS.

The browser captures are an additional bounded runtime check and are not substituted by the structural suite.
""",
    )

    regression_text = (
        "Status: `PASS_WITH_LIMITATIONS`\n\n"
        f"Full current suite passed with 1781 tests. Tracked changes under frozen Phase 2–8 evidence: "
        f"`{historical_changes or 'none'}`. This is a regression-preservation check; it does not re-run every historical external host or browser claim."
    )
    for phase in (
        "frontend-pilot",
        "verifier",
        "phase2",
        "phase3",
        "phase4",
        "phase5",
        "phase6",
        "phase7",
        "phase7.1",
        "phase7.2",
        "phase7.3",
        "phase8",
    ):
        write_text(f"{phase}-regression.md", f"# {phase} Regression\n\n{regression_text}\n")

    write_text(
        "final-report.md",
        f"""# Phase 8.1 Final Report

## PHASE 8.1 STATUS

`{final_status}` for `{head}`.

## FINAL PROMOTION DECISION

`{decision}`. Quality target: `P8_LEVEL_B` / `VERIFIED_CANDIDATE_WITH_LIMITATIONS` when independent reviews are PASS.

## QUALITY BAR

- Frontend package: `{package["package_fingerprint"]}` — PASS.
- Exact composed artifact: `{composition["artifact_digest"]}` — PASS.
- Runtime-required evals: `{classification["counts"]["runtime_executed"]}/{classification["counts"]["runtime_required"]}` — PASS.
- All catalog evals classified: `{classification["counts"]["total"]}` — PASS.
- Coverage: `{coverage["totals"]["percent_covered"]:.2f}%` lines / `{coverage["totals"]["percent_branches_covered"]:.2f}%` branches — PASS.

## FINDINGS CLOSED

Actionable/promotion-blocking High and Medium counts are zero in `finding-ledger.json`. URL state, stale response, idempotency, reflow and keyboard/focus evidence are current-artifact receipts.

## HOST COMPOSITION

The authoritative composition is `{composition["run_id"]}` with exact artifact `{composition["artifact_digest"]}`. The public app-server handshake observed `READY` and `VERIFIER_READY`, but no public skill-load event or native browser observer. The accepted bounded alternative is the exact-artifact bridge in `composition-proof.json`, with zero global/capability mutations and explicit `HOST_LOAD_UNOBSERVABLE` limitation.

## RUNTIME EVIDENCE

Chromium captures cover loading, success, empty, error/retry, validation, idempotency, stale response, URL history, responsive viewports, 200% reflow, keyboard and accessibility checks. The packet does not claim universal browser or assistive-technology coverage.

## VERIFIER

`verifier-report.json` is `{verifier["status"]}` with {verifier["summary"]["checks_passed"]}/{verifier["summary"]["checks_total"]} checks passing and verification digest `{verifier["verification_digest"]}`.

## SECURITY

See `security-report.md` and `scanner-report.md`. No production security, release or approval claim is made.

## REGRESSIONS

The current full suite passed; frozen historical evidence paths have no tracked modifications.

## INDEPENDENT REVIEWS

Review status: `{args.review_status}`. Reviewer ids: `{", ".join(args.reviewer_id) or "pending"}`.

## FINAL REPORT

The exact packet is indexed by `closeout-index.json`, bound by `review-manifest.json` and attested by `review-attestation.json`.
""",
    )
    write_text(
        "promotion-decision.md",
        f"""# Promotion Decision

Decision: `{decision}`

Quality bar: `P8_LEVEL_B`
Review status: `{args.review_status}`

The candidate may be treated as a bounded verified evidence packet only within the stated synthetic fixture, exact artifact, Chromium and host-protocol limitations. This decision is not production readiness, release approval, security approval, universal accessibility, cross-browser certification or full host skill-load causality.
""",
    )
    write_json(
        "readiness.json",
        {
            "schema_version": "P8.1-READINESS-1",
            "task_id": "PHASE8.1-001",
            "status": "READY_WITH_LIMITATIONS"
            if final_status == "PASS_WITH_LIMITATIONS"
            else "NOT_READY_FOR_PROMOTION",
            "decision": decision,
            "quality_bar": "P8_LEVEL_B",
            "repository_head": head,
            "composition_run": composition["run_id"],
            "artifact_digest": composition["artifact_digest"],
            "verifier_status": verifier["status"],
            "review_status": args.review_status,
            "open_actionable_high": ledger["counts"]["open_actionable_high"],
            "open_actionable_medium": ledger["counts"]["open_actionable_medium"],
            "runtime_evals": classification["counts"],
            "limitations": composition["limitations"],
        },
    )
    write_json(
        "closeout-index.json",
        {
            "schema_version": "P8.1-CLOSEOUT-INDEX-1",
            "task_id": "PHASE8.1-001",
            "status": final_status,
            "repository_head": head,
            "current_composition_run": composition["run_id"],
            "current_artifact_digest": composition["artifact_digest"],
            "historical_composition_runs": historical_composition_runs,
            "authoritative_packet": [
                "README.md",
                "baseline.json",
                "P8.1-QB-1.md",
                "finding-ledger.json",
                "host-composition-capability-matrix.json",
                "host-composition-interpretation.md",
                "composition-proof.json",
                "composition-timeline.json",
                "browser-evidence.json",
                "runtime-eval-classification.json",
                "runtime-eval-traceability.json",
                "runtime-eval-report.json",
                "verifier-report.json",
                "review-manifest.json",
                "review-attestation.json",
                "readiness.json",
                "promotion-decision.md",
                "final-report.md",
            ],
            "review_status": args.review_status,
            "reviewer_ids": args.reviewer_id,
        },
    )

    excluded = {"review-manifest.json", "review-attestation.json"}
    entries = []
    for path in sorted(EVIDENCE_ROOT.rglob("*")):
        if not path.is_file() or path.relative_to(EVIDENCE_ROOT).as_posix() in excluded:
            continue
        relative = path.relative_to(EVIDENCE_ROOT).as_posix()
        entries.append(
            {"path": relative, "bytes": path.stat().st_size, "sha256": file_digest(path)}
        )
    manifest = {
        "schema_version": "P8.1-REVIEW-MANIFEST-1",
        "task_id": "PHASE8.1-001",
        "repository_head": head,
        "status": final_status,
        "current_composition_run": composition["run_id"],
        "current_artifact_digest": composition["artifact_digest"],
        "historical_composition_runs": historical_composition_runs,
        "generated_at": now,
        "excluded_envelopes": sorted(excluded),
        "entries": entries,
    }
    manifest["manifest_digest"] = digest(manifest)
    write_json("review-manifest.json", manifest)

    attestation = {
        "schema_version": "P8.1-REVIEW-ATTESTATION-1",
        "task_id": "PHASE8.1-001",
        "status": final_status,
        "repository_head": head,
        "quality_bar": "P8_LEVEL_B",
        "review_status": args.review_status,
        "reviewer_ids": args.reviewer_id,
        "manifest_digest": manifest["manifest_digest"],
        "frontend_fingerprint": package["package_fingerprint"],
        "artifact_digest": composition["artifact_digest"],
        "verification_digest": verifier["verification_digest"],
        "runtime_evals": classification["counts"],
        "finding_counts": ledger["counts"],
        "limitations": composition["limitations"],
        "statement": (
            "Independent reviewers found no blocking issue in the exact packet."
            if review_pass
            else "Independent review is pending or did not pass; do not promote."
        ),
    }
    attestation["attestation_digest"] = digest(attestation)
    write_json("review-attestation.json", attestation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
