"""Create the byte-bound closeout for the current Phase 7 rerun.

The historical ``evidence/phase-7/closeout`` packet is immutable audit
history. This script creates a new packet for the current 0007 builder,
0007 repair and 0009 verifier chain. It only writes the project-local
closeout directory and its new gate; it never invokes a host or mutates a
package, pilot, installed capability or global configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_SCOPE = PROJECT_ROOT.parent.parent
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "backend-engineering-vnext"
PILOT_ROOT = PROJECT_ROOT / "pilots" / "backend-appointment-api"
CURRENT_RERUN_ROOT = PROJECT_ROOT / "evidence" / "phase-7" / "reruns"
CURRENT_BUILDER_ROOT = CURRENT_RERUN_ROOT / "PHASE7-RERUN-0007"
CURRENT_REPAIR_ROOT = CURRENT_RERUN_ROOT / "PHASE7-REPAIR-0007"
CURRENT_EVAL = CURRENT_RERUN_ROOT / "eval-rerun-20260830-rerun-0007.json"
QUALITY_RUN = CURRENT_BUILDER_ROOT / "quality-run-0003.json"
CLOSEOUT_ROOT = PROJECT_ROOT / "evidence" / "phase-7" / "closeout-rerun-0009"
FINAL_GATE_PATH = PROJECT_ROOT / ".agent" / "gates" / "PHASE7-FINAL-RERUN-0009.json"

BUILDER_RECEIPT = CURRENT_BUILDER_ROOT / "builder-receipt.json"
REPAIR_RECEIPT = CURRENT_REPAIR_ROOT / "repair-receipt.json"
VERIFIER_RECEIPT = CURRENT_REPAIR_ROOT / "verifier-receipt-0009.json"

CLOSURE_FILES = frozenset(
    {
        "README.md",
        "final-report.md",
        "independent-review.md",
        "review-manifest.json",
        "review-attestation.json",
        "readiness.json",
        "gate.json",
    }
)
SKIP_PARTS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".coverage"})
SKIP_SUFFIXES = frozenset({".pyc", ".pyo"})


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON evidence must be an object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


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
    previous = entries.get(item["path"])
    if previous is not None and previous != item:
        raise RuntimeError(f"closeout entry has conflicting bytes: {path}")
    entries[item["path"]] = item


def _add_tree(entries: dict[str, dict[str, Any]], root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError(f"closeout tree is not a regular directory: {root}")
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"closeout tree contains a symlink: {path}")
        if not path.is_file():
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


def _validate_catalog_evaluation(
    evaluation: dict[str, Any], expected_package_fingerprint: str
) -> None:
    """Reject stale, fixture-only or causal labels at the closeout boundary."""

    _require(
        evaluation.get("package_fingerprint") == expected_package_fingerprint,
        "evaluation package fingerprint is not current",
    )
    for key, expected in {
        "execution_scope": "FULL_CATALOG",
        "behavioral_execution": "DETERMINISTIC_CONTRACT_OBSERVERS",
        "known_bad_execution": "SCHEMA_GUARD_ONLY",
        "oracle_source": "catalog_expected_outcome_and_expected_stop",
        "fixture_only": False,
        "causal_claim": False,
        "procedure_catalog_bound": True,
    }.items():
        _require(evaluation.get(key) == expected, f"evaluation {key} is not current")
    _require(evaluation.get("superseded", False) is False, "evaluation is superseded")
    _require(
        evaluation.get("superseded_by") in (None, ""),
        "evaluation has a superseding record",
    )


def _check_current_evidence() -> tuple[dict[str, Any], ...]:
    builder = _load_json(BUILDER_RECEIPT)
    repair = _load_json(REPAIR_RECEIPT)
    verifier = _load_json(VERIFIER_RECEIPT)
    evaluation = _load_json(CURRENT_EVAL)
    quality = _load_json(QUALITY_RUN)
    package_fingerprint: str
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from harness_kernel.phase7_backend import package_fingerprint as fingerprint_for

    package_fingerprint = fingerprint_for(PACKAGE_ROOT.resolve())
    _require(
        builder.get("package_fingerprint") == package_fingerprint,
        "builder receipt is not bound to the current package",
    )
    _require(
        repair.get("package_fingerprint") == package_fingerprint,
        "repair receipt is not bound to the current package",
    )
    _validate_catalog_evaluation(evaluation, package_fingerprint)
    _require(builder.get("semantic_status") == "SUCCESS", "builder is not successful")
    _require(repair.get("semantic_status") == "SUCCESS", "repair is not successful")
    _require(verifier.get("status") == "PASS_WITH_LIMITATIONS", "verifier is not green")
    _require(verifier.get("local_checks", {}).get("all_pass") is True, "verifier checks failed")
    verifier_host = verifier.get("host_result")
    _require(isinstance(verifier_host, dict), "verifier host result is missing")
    _require(
        verifier_host.get("transport_status") == "SUCCESS"
        and verifier_host.get("invocation_observed") is True
        and verifier_host.get("execution_observed") is True
        and verifier_host.get("host_report_valid") is True
        and verifier_host.get("workspace_unchanged") is True,
        "verifier host observation is incomplete",
    )
    _require(evaluation.get("status") == "PASS", "catalog evaluation is not green")
    _require(
        evaluation.get("scenario_count") == 48
        and evaluation.get("passed_scenarios") == 48
        and evaluation.get("critical_false_pass_count") == 0
        and evaluation.get("critical_oracle_mismatch_count") == 0,
        "catalog evaluation is incomplete",
    )
    _require(
        quality.get("results", {}).get("tests", {}).get("passed") == 563, "quality run is stale"
    )
    _require(
        quality.get("results", {}).get("tests", {}).get("failed") == 0,
        "quality run contains test failures",
    )
    _require(
        quality.get("results", {}).get("line_coverage", {}).get("status") == "PASS",
        "line coverage threshold is not green",
    )
    return builder, repair, verifier, evaluation, quality


def _review_record(args: argparse.Namespace) -> dict[str, str]:
    note = str(args.review_note).strip()
    if len(note) > 2_000:
        raise RuntimeError("independent review note exceeds its bound")
    reviewer = str(args.reviewer_id).strip()
    if len(reviewer) > 256:
        raise RuntimeError("independent reviewer identity exceeds its bound")
    return {
        "status": str(args.independent_review),
        "reviewer_id": reviewer or "UNSPECIFIED",
        "note": note or "No independent-review result was supplied to the closeout integrator.",
    }


def _collect_entries() -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    _add_tree(entries, PACKAGE_ROOT)
    _add_tree(entries, PILOT_ROOT)
    _add_tree(entries, CURRENT_BUILDER_ROOT)
    _add_tree(entries, CURRENT_REPAIR_ROOT)
    _add_tree(entries, PROJECT_ROOT / "tests" / "evals" / "phase7")
    for relative in (
        "config/phase7-execution-policy.json",
        "scripts/build_phase7_rerun_closeout.py",
        "scripts/run_phase7_evals.py",
        "scripts/run_phase7_real_builder.py",
        "scripts/run_phase7_real_repair.py",
        "scripts/run_phase7_real_verifier.py",
        "evidence/phase-7/reruns/eval-rerun-20260830-rerun-0007.json",
        "src/harness_kernel/phase4_host.py",
        "src/harness_kernel/phase4_policy.py",
        "src/harness_kernel/phase6_host.py",
        "src/harness_kernel/phase7_backend.py",
        "src/harness_kernel/phase7_host.py",
        "tests/integration/test_phase6_host.py",
        "tests/unit/test_phase4_host.py",
        "tests/unit/test_phase4_policy.py",
        "tests/unit/test_phase7_backend.py",
        "tests/unit/test_phase7_host.py",
        ".agent/plans/PHASE-7-backend-engineering-modernization.md",
        ".agent/gates/PHASE7-SCOPE-READY-0001.json",
        ".agent/gates/PHASE7-TECHNICALLY-SPECIFIED-0001.json",
        ".agent/gates/PHASE7-IMPLEMENTATION-READY-0001.json",
        ".agent/gates/PHASE7-RERUN-SCOPE-READY-0001.json",
        ".agent/gates/PHASE7-RERUN-SCOPE-READY-0002.json",
        ".agent/gates/PHASE7-RERUN-SCOPE-READY-0003.json",
        ".agent/gates/PHASE7-REPAIR-SCOPE-READY-0001.json",
        "evidence/phase-7/P7-QB-1.md",
        "evidence/phase-7/README.md",
        "../../architecture/docs/adr/ADR-016-backend-engineering-vnext-modernization.md",
    ):
        _add_file(entries, PROJECT_ROOT / relative)
    return [entries[key] for key in sorted(entries)]


def _claim_policy() -> dict[str, bool]:
    return {
        "aaa_verified": False,
        "production_ready": False,
        "release_approval": False,
        "security_approval": False,
        "universal_superiority": False,
    }


def _limitations(review: dict[str, str]) -> list[str]:
    values = [
        "branch coverage is 65.54% and is reported below the 80% target",
        "pip-audit is unavailable in the project environment",
        "host skill-load event remains unobservable",
        "host response is composition telemetry and not local factual evidence",
        (
            "network and provider absence are bounded protocol observations, not a "
            "syscall-level isolation claim"
        ),
        "host control-plane authentication is separate from the capability credential boundary",
        (
            "artifact-v3 is a derived disposable artifact; the fixed formatter was applied "
            "and its changed-path list is receipt-bound"
        ),
        "no independent release authority or production approval is represented by this packet",
    ]
    if review["status"] == "PENDING":
        values.append("independent review is still pending")
    if review["status"] == "FAIL":
        values.append("independent review returned FAIL")
    return values


def _readme(
    *,
    status: str,
    promotion: str,
    review: dict[str, str],
    package_digest: str,
    manifest_digest: str,
    verifier: dict[str, Any],
    evaluation: dict[str, Any],
    quality: dict[str, Any],
) -> str:
    limitations = _limitations(review)
    lines = [
        "# Phase 7 current rerun closeout",
        "",
        "This is the authoritative closeout for the additive project-local",
        "`backend-engineering-vnext` rerun chain `PHASE7-RERUN-0007` →",
        "`PHASE7-REPAIR-0007` → `verifier-receipt-0009.json`. The older",
        "`evidence/phase-7/closeout/` directory and earlier reruns remain",
        "historical audit records and are not silently merged into this packet.",
        "",
        f"Result: `{status}` / `{promotion}`.",
        f"Independent review input: `{review['status']}` (`{review['reviewer_id']}`).",
        f"Package fingerprint: `{package_digest}`.",
        f"Manifest entries digest: `{manifest_digest}`.",
        "",
        "Observed green evidence:",
        "",
        (
            f"- catalog evaluator: `{evaluation['passed_scenarios']}/"
            f"{evaluation['scenario_count']}`; known-bad checks are schema guards and "
            "behavioral observations are deterministic contract observers"
        ),
        (
            f"- real verifier: `{verifier['status']}`, all local checks true, fixed test "
            "observer and host response valid, artifact workspace unchanged"
        ),
        (
            f"- complete Harness suite: `{quality['results']['tests']['passed']}` passed, "
            f"`{quality['results']['line_coverage']['percent']:.2f}%` line coverage"
        ),
        "- strict mypy and Ruff format/check: PASS",
        (
            "- builder and repair: SUCCESS, bounded app/tests deltas, no capability "
            "credential tools exposed"
        ),
        "",
        "Explicit limitations:",
        "",
    ]
    lines.extend(f"- {item}" for item in limitations)
    lines.extend(
        [
            "",
            "This packet does not authorize promotion, production use, release,",
            "security approval, causal superiority, or an AAA/perfect-quality",
            "claim. The next decision is owned by a human/release authority, not",
            "by the package, builder, verifier or closeout integrator.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--independent-review",
        choices=("PENDING", "PASS", "FAIL"),
        default="PENDING",
    )
    parser.add_argument("--reviewer-id", default="")
    parser.add_argument("--review-note", default="")
    args = parser.parse_args()

    if CLOSEOUT_ROOT.exists():
        raise RuntimeError("current rerun closeout already exists; refusing overwrite")
    if FINAL_GATE_PATH.exists():
        raise RuntimeError("current rerun final gate already exists; refusing overwrite")

    builder, repair, verifier, evaluation, quality = _check_current_evidence()
    review = _review_record(args)
    status = "FAIL" if review["status"] == "FAIL" else "PASS_WITH_LIMITATIONS"
    promotion = "NOT_PROMOTED"
    package_digest = str(evaluation["package_fingerprint"])
    entries = _collect_entries()
    entries_digest = _sha256_bytes(
        json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    observed_at = _now()
    manifest = {
        "schema_version": "P7-RERUN-REVIEW-MANIFEST-1",
        "task_id": "PHASE7-001",
        "chain_id": "PHASE7-RERUN-0007",
        "status": status,
        "promotion": promotion,
        "observed_at": observed_at,
        "authority": "CLOSEOUT_EVIDENCE_INTEGRATOR",
        "package": {
            "capability_id": "backend-engineering-vnext",
            "version": "0.1.0",
            "path": ".harness/capabilities/backend-engineering-vnext",
            "fingerprint": package_digest,
        },
        "entry_policy": {
            "hash": "sha256 over exact bytes",
            "paths": "project-relative, with approved architecture input retained as ../..",
            "symlinks": "rejected",
            "generated_caches": "excluded",
        },
        "entries": entries,
        "entry_count": len(entries),
        "entries_digest": entries_digest,
        "current_chain": {
            "builder_receipt": {
                "path": "evidence/phase-7/reruns/PHASE7-RERUN-0007/builder-receipt.json",
                "digest": _sha256_file(BUILDER_RECEIPT),
                "status": builder["semantic_status"],
            },
            "repair_receipt": {
                "path": "evidence/phase-7/reruns/PHASE7-REPAIR-0007/repair-receipt.json",
                "digest": _sha256_file(REPAIR_RECEIPT),
                "status": repair["semantic_status"],
            },
            "verifier_receipt": {
                "path": "evidence/phase-7/reruns/PHASE7-REPAIR-0007/verifier-receipt-0009.json",
                "digest": _sha256_file(VERIFIER_RECEIPT),
                "status": verifier["status"],
                "artifact_tree_digest": verifier["artifact"]["tree_digest"],
            },
            "catalog_evaluation": {
                "path": "evidence/phase-7/reruns/eval-rerun-20260830-rerun-0007.json",
                "digest": _sha256_file(CURRENT_EVAL),
                "status": evaluation["status"],
                "passed": evaluation["passed_scenarios"],
                "total": evaluation["scenario_count"],
            },
            "quality_run": {
                "path": "evidence/phase-7/reruns/PHASE7-RERUN-0007/quality-run-0003.json",
                "digest": _sha256_file(QUALITY_RUN),
                "status": quality["results"]["tests"]["status"],
            },
        },
        "independent_review": review,
        "historical_exclusions": [
            "evidence/phase-7/closeout/",
            "evidence/phase-7/closeout-rerun-0007/",
            "evidence/phase-7/closeout-rerun-0008/",
            "evidence/phase-7/reruns/PHASE7-RERUN-0001 through PHASE7-RERUN-0005",
            "evidence/phase-7/eval-rerun-20260830.json",
            "evidence/phase-7/closeout/package-eval-run.json",
        ],
        "closure_controls_excluded_from_entries": sorted(CLOSURE_FILES),
        "claim_policy": _claim_policy(),
    }

    CLOSEOUT_ROOT.mkdir(parents=True)
    manifest_path = CLOSEOUT_ROOT / "review-manifest.json"
    _write_json(manifest_path, manifest)
    manifest_digest = _sha256_file(manifest_path)

    independent_review = (
        "# Independent review input\n\n"
        f"- status: `{review['status']}`\n"
        f"- reviewer: `{review['reviewer_id']}`\n"
        f"- note: {review['note']}\n\n"
        "This record is an integrator transcription of the review result; it is"
        " not a release approval or a cryptographic signature."
    )
    (CLOSEOUT_ROOT / "independent-review.md").write_text(independent_review, encoding="utf-8")

    attestation = {
        "schema_version": "P7-RERUN-REVIEW-ATTESTATION-1",
        "task_id": "PHASE7-001",
        "chain_id": "PHASE7-RERUN-0007",
        "observed_at": observed_at,
        "attestation_type": "NON_CRYPTOGRAPHIC_EVIDENCE_ATTESTATION",
        "attestor": "CLOSEOUT_EVIDENCE_INTEGRATOR",
        "manifest_path": "evidence/phase-7/closeout-rerun-0009/review-manifest.json",
        "manifest_digest": manifest_digest,
        "package_fingerprint": package_digest,
        "status": status,
        "promotion": promotion,
        "independent_review": review,
        "attestation": (
            "The listed bytes and observations are the current closeout boundary. "
            "The packet preserves its observed limitations and does not convert "
            "unavailable or unobservable checks into passes."
        ),
        "claims_excluded": sorted(
            {
                "AAA_QUALITY",
                "HARNESS_AAA_VERIFIED",
                "causal_improvement",
                "production_readiness",
                "release_approval",
                "security_approval",
                "universal_superiority",
            }
        ),
    }
    attestation_path = CLOSEOUT_ROOT / "review-attestation.json"
    _write_json(attestation_path, attestation)
    attestation_digest = _sha256_file(attestation_path)

    limitations = _limitations(review)
    readiness = {
        "schema_version": "P7-RERUN-READINESS-1",
        "task_id": "PHASE7-001",
        "chain_id": "PHASE7-RERUN-0007",
        "observed_at": observed_at,
        "manifest_digest": manifest_digest,
        "attestation_digest": attestation_digest,
        "status": status,
        "promotion": promotion,
        "candidate_support": "P7_LEVEL_B_CANDIDATE" if status != "FAIL" else "P7_LEVEL_A_CANDIDATE",
        "promotable_support": None,
        "levels": {
            "P7_LEVEL_A": {
                "candidate": True,
                "promoted": False,
                "reason": (
                    "The package catalog and bounded contract surface are current and rebound."
                ),
            },
            "P7_LEVEL_B": {
                "candidate": status != "FAIL",
                "promoted": False,
                "reason": (
                    "Real builder, one bounded repair and a fresh read-only verifier are rebound; "
                    "release authority is still absent."
                ),
            },
            "P7_LEVEL_C": {
                "candidate": False,
                "promoted": False,
                "reason": (
                    "A strict adversarial critic/repair/fresh-verification authority chain "
                    "is not claimed."
                ),
            },
        },
        "limitations": limitations,
        "aaa_verified": False,
        "claim_policy": _claim_policy(),
    }
    readiness_path = CLOSEOUT_ROOT / "readiness.json"
    _write_json(readiness_path, readiness)
    readiness_digest = _sha256_file(readiness_path)

    gate = {
        "schema_version": "P7-RERUN-FINAL-GATE-1",
        "gate_id": "PHASE7-FINAL-RERUN-0009",
        "task_id": "PHASE7-001",
        "chain_id": "PHASE7-RERUN-0007",
        "observed_at": observed_at,
        "status": status,
        "promotion": promotion,
        "candidate_support": readiness["candidate_support"],
        "promoted_support": None,
        "package_fingerprint": package_digest,
        "manifest_digest": manifest_digest,
        "attestation_digest": attestation_digest,
        "readiness_digest": readiness_digest,
        "evidence": {
            "builder": "evidence/phase-7/reruns/PHASE7-RERUN-0007/builder-receipt.json",
            "repair": "evidence/phase-7/reruns/PHASE7-REPAIR-0007/repair-receipt.json",
            "verifier": "evidence/phase-7/reruns/PHASE7-REPAIR-0007/verifier-receipt-0009.json",
            "evaluation": "evidence/phase-7/reruns/eval-rerun-20260830-rerun-0007.json",
            "quality": "evidence/phase-7/reruns/PHASE7-RERUN-0007/quality-run-0003.json",
        },
        "independent_review": review,
        "limitations": limitations,
        "decision": (
            "Retain the additive candidate at the observed support level and do not promote. "
            "A human/release authority must decide whether the explicit limitations are acceptable."
        ),
        "claims_excluded": attestation["claims_excluded"],
    }
    gate_path = CLOSEOUT_ROOT / "gate.json"
    _write_json(gate_path, gate)
    FINAL_GATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_json(FINAL_GATE_PATH, gate)

    final_report = _readme(
        status=status,
        promotion=promotion,
        review=review,
        package_digest=package_digest,
        manifest_digest=manifest_digest,
        verifier=verifier,
        evaluation=evaluation,
        quality=quality,
    )
    (CLOSEOUT_ROOT / "README.md").write_text(final_report, encoding="utf-8")
    (CLOSEOUT_ROOT / "final-report.md").write_text(final_report, encoding="utf-8")

    print(
        json.dumps(
            {
                "status": status,
                "promotion": promotion,
                "package_fingerprint": package_digest,
                "manifest_digest": manifest_digest,
                "entry_count": len(entries),
                "closeout": str(CLOSEOUT_ROOT),
            },
            sort_keys=True,
        )
    )
    return 0 if status != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
