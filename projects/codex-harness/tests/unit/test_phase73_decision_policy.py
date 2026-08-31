"""Tests for the explicit Phase 7.3 materiality decision policy."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from generate_phase73_decisions import build_decisions  # noqa: E402


def _branch(branch_id: str, *, risk_level: str, category: str, file: str) -> dict[str, object]:
    return {
        "branch_id": branch_id,
        "risk_level": risk_level,
        "risk_category": category,
        "file": file,
    }


def test_material_boundary_uses_prior_contract_evidence_and_tested_pass() -> None:
    decisions = build_decisions(
        {
            "branches": [
                _branch(
                    "P7.2-BRANCH-HOST",
                    risk_level="medium",
                    category="HOST_AUTH",
                    file="src/harness_kernel/phase7_host.py",
                )
            ]
        }
    )

    decision = decisions["P7.2-BRANCH-HOST"]
    assert decision["materiality"] == "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE"
    assert decision["closure_status"] == "TESTED_PASS"
    evidence = decision["existing_evidence"]
    assert isinstance(evidence, list)
    assert any("phase72_host_assurance" in item for item in evidence)


def test_defensive_other_branch_requires_explicit_non_material_acceptance() -> None:
    decisions = build_decisions(
        {
            "branches": [
                _branch(
                    "P7.2-BRANCH-PARSER",
                    risk_level="medium",
                    category="OTHER",
                    file="src/harness_kernel/phase3_parser.py",
                )
            ]
        }
    )

    decision = decisions["P7.2-BRANCH-PARSER"]
    assert decision["materiality"] == "NON_MATERIAL_DEFENSIVE"
    assert decision["closure_status"] == "ACCEPTED_NON_MATERIAL"
    assert "side effect" in str(decision["decision_reason"])


def test_classification_and_registry_semantics_are_material_even_without_risk_labels() -> None:
    decisions = build_decisions(
        {
            "branches": [
                _branch(
                    "P7.2-BRANCH-CLASSIFICATION",
                    risk_level="medium",
                    category="OTHER",
                    file="src/harness_kernel/classification.py",
                ),
                _branch(
                    "P7.2-BRANCH-REGISTRY",
                    risk_level="medium",
                    category="OTHER",
                    file="src/harness_kernel/registry.py",
                ),
            ]
        }
    )

    for branch_id in ("P7.2-BRANCH-CLASSIFICATION", "P7.2-BRANCH-REGISTRY"):
        assert (
            decisions[branch_id]["materiality"]
            == "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE"
        )
        assert decisions[branch_id]["closure_status"] == "TESTED_PASS"


def test_known_high_is_closed_only_by_the_existing_unreachable_proof() -> None:
    decisions = build_decisions(
        {
            "branches": [
                _branch(
                    "P7.2-BRANCH-f2e9d9298c4f3336",
                    risk_level="high",
                    category="RETRY",
                    file="src/harness_kernel/phase5_cli.py",
                )
            ]
        }
    )

    decision = decisions["P7.2-BRANCH-f2e9d9298c4f3336"]
    assert decision["materiality"] == "UNREACHABLE_BY_CONTRACT"
    assert decision["closure_status"] == "UNREACHABLE_PROVEN"
    assert decision["existing_evidence"] == ["evidence/phase-7.2/phase5-cli-loop-proof.md"]


def test_phase5_runner_unreachable_arcs_use_explicit_contract_proof() -> None:
    decisions = build_decisions(
        {
            "branches": [
                _branch(
                    "P7.2-BRANCH-4b19ebeca10a65d7",
                    risk_level="medium",
                    category="OTHER",
                    file="src/harness_kernel/phase5_execution.py",
                ),
                _branch(
                    "P7.2-BRANCH-5c522f0ede03d764",
                    risk_level="medium",
                    category="OTHER",
                    file="src/harness_kernel/phase5_execution.py",
                ),
            ]
        }
    )

    for branch_id in (
        "P7.2-BRANCH-4b19ebeca10a65d7",
        "P7.2-BRANCH-5c522f0ede03d764",
    ):
        assert decisions[branch_id]["materiality"] == "UNREACHABLE_BY_CONTRACT"
        assert decisions[branch_id]["closure_status"] == "UNREACHABLE_PROVEN"
        assert "line 402" in decisions[branch_id]["decision_reason"]


def test_registry_guards_that_follow_strict_syntax_checks_are_unreachable() -> None:
    decisions = build_decisions(
        {
            "branches": [
                _branch(
                    "P7.2-BRANCH-d22fdc1a09d97905",
                    risk_level="medium",
                    category="OTHER",
                    file="src/harness_kernel/registry.py",
                ),
                _branch(
                    "P7.2-BRANCH-f548dbed5622a8c7",
                    risk_level="medium",
                    category="OTHER",
                    file="src/harness_kernel/registry.py",
                ),
            ]
        }
    )

    for branch_id in (
        "P7.2-BRANCH-d22fdc1a09d97905",
        "P7.2-BRANCH-f548dbed5622a8c7",
    ):
        assert decisions[branch_id]["materiality"] == "UNREACHABLE_BY_CONTRACT"
        assert decisions[branch_id]["closure_status"] == "UNREACHABLE_PROVEN"
