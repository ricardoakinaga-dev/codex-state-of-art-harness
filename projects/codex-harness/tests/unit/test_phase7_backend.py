from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import build_phase7_rerun_closeout  # noqa: E402

from harness_kernel.phase7_backend import (  # noqa: E402
    BackendPackageContractError,
    package_fingerprint,
    snapshot_workspace,
    validate_backend_benchmarks,
    validate_backend_evals,
    validate_backend_evidence_binding,
    validate_backend_manifest,
    validate_backend_package,
    validate_backend_procedures,
    validate_workspace_delta,
)

PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "backend-engineering-vnext"


def test_closeout_rejects_catalog_with_stale_execution_labels() -> None:
    evaluation = json.loads(build_phase7_rerun_closeout.CURRENT_EVAL.read_text(encoding="utf-8"))
    evaluation["behavioral_execution"] = "FULL_CATALOG"

    with pytest.raises(RuntimeError, match="behavioral_execution"):
        build_phase7_rerun_closeout._validate_catalog_evaluation(
            evaluation,
            str(evaluation["package_fingerprint"]),
        )


def test_backend_package_is_native_and_has_a_complete_specialist_contract() -> None:
    fingerprint = package_fingerprint(PACKAGE_ROOT)
    report = validate_backend_package(PACKAGE_ROOT, expected_fingerprint=fingerprint)

    assert report.ok is True
    assert report.capability_id == "backend-engineering-vnext"
    assert report.primary_type == "SPECIALIST"
    assert report.role == "SPECIALIST"
    assert report.scenario_count >= 40
    assert report.package_fingerprint.startswith("sha256:")
    assert report.forbidden_boundaries == (
        "shell",
        "network",
        "mcp",
        "provider",
        "credential",
        "credentials",
    )


def test_backend_package_without_expected_fingerprint_is_not_execution_eligible() -> None:
    report = validate_backend_package(PACKAGE_ROOT)

    assert report.ok is False
    assert "EXPECTED_PACKAGE_FINGERPRINT_REQUIRED" in report.blockers


def test_backend_evidence_binding_requires_fresh_bound_non_self_approved_identity() -> None:
    evidence = {
        "task_id": "TASK-P7-EVIDENCE-1",
        "package_fingerprint": "sha256:" + "1" * 64,
        "artifact_digest": "sha256:" + "2" * 64,
        "criteria_digest": "sha256:" + "3" * 64,
        "freshness": "FRESH",
        "status": "VERIFIED",
        "authority": "VERIFIER",
        "self_approval": False,
        "observed_at": datetime.now(UTC).isoformat(),
        "evidence_digests": {"tests": "sha256:" + "4" * 64},
    }

    report = validate_backend_evidence_binding(
        evidence,
        expected_task_id="TASK-P7-EVIDENCE-1",
        expected_package_fingerprint="sha256:" + "1" * 64,
        expected_artifact_digest="sha256:" + "2" * 64,
        expected_criteria_digest="sha256:" + "3" * 64,
        expected_authority="VERIFIER",
    )

    assert report.ok is True
    assert report.evidence_count == 1


def test_backend_evidence_binding_rejects_stale_and_mismatched_evidence() -> None:
    evidence = {
        "task_id": "TASK-P7-EVIDENCE-1",
        "package_fingerprint": "sha256:" + "1" * 64,
        "artifact_digest": "sha256:" + "2" * 64,
        "criteria_digest": "sha256:" + "3" * 64,
        "freshness": "STALE",
        "status": "STALE",
        "authority": "BUILDER",
        "self_approval": True,
        "observed_at": 1,
        "evidence_digests": {"tests": "invalid"},
    }

    report = validate_backend_evidence_binding(
        evidence,
        expected_task_id="TASK-P7-EVIDENCE-1",
        expected_package_fingerprint="sha256:" + "9" * 64,
        expected_artifact_digest="sha256:" + "8" * 64,
        expected_criteria_digest="sha256:" + "7" * 64,
        expected_authority="VERIFIER",
    )

    assert report.ok is False
    assert "EVIDENCE_NOT_FRESH" in report.blockers
    assert "EVIDENCE_SELF_APPROVAL_FORBIDDEN" in report.blockers
    assert "EVIDENCE_PACKAGE_FINGERPRINT_MISMATCH" in report.blockers
    assert "EVIDENCE_DIGEST_ENTRY_INVALID" in report.blockers


def test_backend_evidence_binding_requires_pinned_expected_identity() -> None:
    evidence = {
        "task_id": "TASK-P7-EVIDENCE-1",
        "package_fingerprint": "sha256:" + "1" * 64,
        "artifact_digest": "sha256:" + "2" * 64,
        "criteria_digest": "sha256:" + "3" * 64,
        "freshness": "FRESH",
        "status": "UNKNOWN",
        "authority": "VERIFIER",
        "observed_at": 1,
        "evidence_digests": {"tests": "sha256:" + "4" * 64},
    }

    report = validate_backend_evidence_binding(evidence)

    assert report.ok is False
    assert "EXPECTED_EVIDENCE_PACKAGE_FINGERPRINT_REQUIRED" in report.blockers
    assert "EXPECTED_EVIDENCE_ARTIFACT_DIGEST_REQUIRED" in report.blockers
    assert "EXPECTED_EVIDENCE_CRITERIA_DIGEST_REQUIRED" in report.blockers
    assert "EVIDENCE_SELF_APPROVAL_FORBIDDEN" in report.blockers
    assert "EVIDENCE_STATUS_NOT_VERIFIED" in report.blockers


def test_backend_evidence_binding_missing_fields_returns_a_fail_closed_report() -> None:
    report = validate_backend_evidence_binding({})

    assert report.ok is False
    assert "EVIDENCE_TASK_ID_INVALID" in report.blockers
    assert "EVIDENCE_PACKAGE_FINGERPRINT_INVALID" in report.blockers
    assert "EVIDENCE_ARTIFACT_DIGEST_INVALID" in report.blockers
    assert "EVIDENCE_CRITERIA_DIGEST_INVALID" in report.blockers


def test_backend_evidence_binding_rejects_an_unbounded_evidence_catalog() -> None:
    evidence = {
        "task_id": "TASK-P7-EVIDENCE-1",
        "package_fingerprint": "sha256:" + "1" * 64,
        "artifact_digest": "sha256:" + "2" * 64,
        "criteria_digest": "sha256:" + "3" * 64,
        "freshness": "FRESH",
        "status": "VERIFIED",
        "authority": "VERIFIER",
        "self_approval": False,
        "observed_at": datetime.now(UTC).isoformat(),
        "evidence_digests": {
            f"entry-{index}": "sha256:" + f"{index:064x}"[-64:] for index in range(257)
        },
    }

    report = validate_backend_evidence_binding(
        evidence,
        expected_task_id="TASK-P7-EVIDENCE-1",
        expected_package_fingerprint="sha256:" + "1" * 64,
        expected_artifact_digest="sha256:" + "2" * 64,
        expected_criteria_digest="sha256:" + "3" * 64,
        expected_authority="VERIFIER",
    )

    assert report.ok is False
    assert "EVIDENCE_DIGEST_COUNT_EXCEEDED" in report.blockers


def test_backend_metadata_validators_require_complete_executable_catalogs() -> None:
    package = json.loads((PACKAGE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    package.pop("trust")
    assert "manifest missing trust" in validate_backend_manifest(package)

    evals = json.loads((PACKAGE_ROOT / "evals" / "scenarios.json").read_text(encoding="utf-8"))
    benchmarks = json.loads(
        (PACKAGE_ROOT / "benchmarks" / "benchmark-fixtures.json").read_text(encoding="utf-8")
    )
    procedures = json.loads(
        (PACKAGE_ROOT / "scripts" / "deterministic-procedures.json").read_text(encoding="utf-8")
    )

    assert validate_backend_evals(evals) == ()
    assert validate_backend_benchmarks(benchmarks) == ()
    assert validate_backend_procedures(procedures) == ()

    procedures.pop("procedures")
    assert "deterministic procedure list is missing" in validate_backend_procedures(procedures)


def test_backend_package_fingerprint_is_deterministic_and_rejects_symlink_substitution(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "SKILL.md").write_text("---\nname: test\n---\n", encoding="utf-8")
    (package / "manifest.json").write_text(
        json.dumps({"capability_id": "test", "version": "0.1.0"}), encoding="utf-8"
    )

    first = package_fingerprint(package)
    second = package_fingerprint(package)
    assert first == second

    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (package / "outside.json").symlink_to(outside)
    with pytest.raises(BackendPackageContractError, match="symlink"):
        package_fingerprint(package)


def test_backend_package_rejects_a_symlinked_expected_identity(tmp_path: Path) -> None:
    alias = tmp_path / "package-alias"
    alias.symlink_to(PACKAGE_ROOT, target_is_directory=True)
    fingerprint = package_fingerprint(PACKAGE_ROOT)

    report = validate_backend_package(
        PACKAGE_ROOT,
        expected_package_path=alias,
        expected_fingerprint=fingerprint,
    )

    assert report.ok is False
    assert "EXPECTED_PACKAGE_PATH_INVALID" in report.blockers


def test_workspace_delta_allows_only_the_declared_pilot_root(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    pilot = workspace / "pilots" / "backend-appointment-api"
    pilot.mkdir(parents=True)
    (pilot / "app.py").write_text("v1", encoding="utf-8")
    before = snapshot_workspace(workspace)

    (pilot / "app.py").write_text("v2", encoding="utf-8")
    report = validate_workspace_delta(workspace, before, allowed_roots=(pilot,))

    assert report.ok is True
    assert report.changed_paths == ("pilots/backend-appointment-api/app.py",)
    assert report.unauthorized_paths == ()


def test_workspace_delta_rejects_package_and_control_plane_mutation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    pilot = workspace / "pilots" / "backend-appointment-api"
    package = workspace / ".harness" / "capabilities" / "backend-engineering-vnext"
    control = workspace / ".agent"
    pilot.mkdir(parents=True)
    package.mkdir(parents=True)
    control.mkdir()
    before = snapshot_workspace(workspace)

    (package / "SKILL.md").write_text("tampered", encoding="utf-8")
    (control / "state.json").write_text("tampered", encoding="utf-8")
    report = validate_workspace_delta(workspace, before, allowed_roots=(pilot,))

    assert report.ok is False
    assert report.unauthorized_paths == (
        ".agent/state.json",
        ".harness/capabilities/backend-engineering-vnext/SKILL.md",
    )


def test_workspace_delta_detects_empty_directory_creation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    pilot = workspace / "pilot"
    pilot.mkdir(parents=True)
    before = snapshot_workspace(workspace)

    (pilot / "empty").mkdir()
    report = validate_workspace_delta(workspace, before, allowed_roots=(pilot,))

    assert report.ok is True
    assert report.changed_paths == ("pilot/empty",)


def test_workspace_delta_detects_mode_only_file_changes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    pilot = workspace / "pilot"
    pilot.mkdir(parents=True)
    target = pilot / "artifact.txt"
    target.write_text("stable\n", encoding="utf-8")
    before = snapshot_workspace(workspace)
    target.chmod(0o600 if target.stat().st_mode & 0o777 != 0o600 else 0o644)

    report = validate_workspace_delta(workspace, before, allowed_roots=(pilot,))

    assert report.ok is True
    assert report.changed_paths == ("pilot/artifact.txt",)


def test_workspace_delta_malformed_snapshot_returns_a_report_instead_of_raising(
    tmp_path: Path,
) -> None:
    report = validate_workspace_delta(
        tmp_path,
        {1: "not-a-path"},  # type: ignore[dict-item]
        allowed_roots=(tmp_path,),
    )

    assert report.ok is False
    assert report.unauthorized_paths
