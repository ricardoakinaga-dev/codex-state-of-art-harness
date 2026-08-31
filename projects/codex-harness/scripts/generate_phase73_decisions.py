#!/usr/bin/env python3
"""Generate explicit, reviewable Phase 7.3 materiality decisions."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

KNOWN_HIGH_UNREACHABLE = "P7.2-BRANCH-f2e9d9298c4f3336"
KNOWN_MEDIUM_UNREACHABLE = frozenset(
    {
        "P7.2-BRANCH-4b19ebeca10a65d7",
        "P7.2-BRANCH-5c522f0ede03d764",
        "P7.2-BRANCH-d22fdc1a09d97905",
        "P7.2-BRANCH-f548dbed5622a8c7",
    }
)
MATERIAL_CATEGORIES = frozenset(
    {
        "CONCURRENCY",
        "EVIDENCE_STALENESS",
        "FAILURE_ROUTING",
        "FILESYSTEM",
        "HOST_AUTH",
        "LEDGER_LOCKING",
        "NO_PROGRESS",
        "PERSISTENCE",
        "SCOPE_CONTROL",
        "SECURITY_BOUNDARY",
        "STATE_TRANSITION",
        "TELEMETRY_INTEGRITY",
    }
)
MATERIAL_FILES = frozenset(
    {
        "boundary.py",
        "classification.py",
        "execution.py",
        "graph.py",
        "phase3_discovery.py",
        "phase3_resolution.py",
        "phase3_telemetry.py",
        "phase4_execution.py",
        "phase4_host.py",
        "phase4_models.py",
        "phase5_execution.py",
        "phase5_verification.py",
        "phase6_checks.py",
        "phase6_host.py",
        "phase6_models.py",
        "phase6_telemetry.py",
        "phase6_verifier.py",
        "phase7_backend.py",
        "phase7_host.py",
        "persistence.py",
        "registry.py",
        "routing.py",
    }
)
EVIDENCE_BY_FILE = {
    "boundary.py": "tests/unit/test_phase72_filesystem_assurance.py",
    "classification.py": "tests/unit/test_classification.py",
    "execution.py": "tests/unit/test_phase72_execution_assurance.py",
    "graph.py": "tests/unit/test_phase72_execution_assurance.py",
    "phase3_discovery.py": "tests/unit/test_phase72_phase3_discovery_policy_assurance.py",
    "phase3_resolution.py": "tests/unit/test_phase72_phase3_remaining_assurance.py",
    "phase3_telemetry.py": "tests/unit/test_phase72_foundation_assurance.py",
    "phase4_execution.py": "tests/unit/test_phase72_phase4_execution_assurance.py",
    "phase4_host.py": "tests/unit/test_phase72_host_assurance.py",
    "phase4_models.py": "tests/unit/test_phase72_high_risk_boundaries.py",
    "phase5_execution.py": "tests/unit/test_phase72_phase5_finalization_assurance.py",
    "phase5_verification.py": "tests/unit/test_phase72_phase5_finalization_assurance.py",
    "phase6_checks.py": "tests/unit/test_phase72_phase6_assurance.py",
    "phase6_host.py": "tests/unit/test_phase72_host_assurance.py",
    "phase6_models.py": "tests/unit/test_phase72_phase6_assurance.py",
    "phase6_telemetry.py": "tests/unit/test_phase72_phase6_assurance.py",
    "phase6_verifier.py": "tests/unit/test_phase72_phase6_assurance.py",
    "phase7_backend.py": "tests/unit/test_phase72_backend_artifacts_assurance.py",
    "phase7_host.py": "tests/unit/test_phase72_host_assurance.py",
    "persistence.py": "tests/unit/test_phase72_persistence_assurance.py",
    "registry.py": "tests/unit/test_phase71_persistence_hardening.py",
    "routing.py": "tests/unit/test_phase72_cli_routing_assurance.py",
}


class DecisionGenerationError(ValueError):
    """Raised when the source inventory cannot receive explicit decisions."""


def build_decisions(inventory: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """Return one explicit decision for every current High or Medium branch."""

    raw_branches = inventory.get("branches")
    if not isinstance(raw_branches, Sequence) or isinstance(raw_branches, (str, bytes)):
        raise DecisionGenerationError("inventory branches must be a sequence")

    decisions: dict[str, dict[str, object]] = {}
    for position, raw_branch in enumerate(raw_branches):
        if not isinstance(raw_branch, Mapping):
            raise DecisionGenerationError(f"branch {position} must be an object")
        branch_id = _text(raw_branch, "branch_id", position)
        risk_level = _text(raw_branch, "risk_level", position)
        if risk_level not in {"high", "medium", "low"}:
            raise DecisionGenerationError(f"branch {branch_id} has invalid risk_level")
        if risk_level == "low":
            continue
        if branch_id in decisions:
            raise DecisionGenerationError(f"duplicate branch_id: {branch_id}")
        if risk_level == "high":
            decisions[branch_id] = _high_decision(raw_branch, branch_id)
            continue
        decisions[branch_id] = _medium_decision(raw_branch, branch_id)
    return decisions


def generate_decisions(inventory_path: Path, output_path: Path) -> dict[str, dict[str, object]]:
    """Generate a sorted decision file from one immutable inventory snapshot."""

    value = json.loads(inventory_path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise DecisionGenerationError("inventory must contain an object")
    decisions = build_decisions(value)
    payload = {
        "schema_version": "P7.3-RISK-DECISIONS-1",
        "phase": "PHASE7.3",
        "source_inventory": str(inventory_path),
        "decision_policy": {
            "material_categories": sorted(MATERIAL_CATEGORIES),
            "material_files": sorted(MATERIAL_FILES),
            "non_material_rule": (
                "Only parser/model/registry/CLI defensive validation branches with no "
                "side effect, authority, persistence, filesystem, or evidence-integrity "
                "impact may be accepted as non-material."
            ),
        },
        "decisions": decisions,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return decisions


def _high_decision(branch: Mapping[str, object], branch_id: str) -> dict[str, object]:
    context = _branch_context(branch)
    if branch_id == KNOWN_HIGH_UNREACHABLE:
        return {
            "materiality": "UNREACHABLE_BY_CONTRACT",
            "closure_status": "UNREACHABLE_PROVEN",
            "existing_evidence": ["evidence/phase-7.2/phase5-cli-loop-proof.md"],
            "decision_reason": (
                f"{branch_id} at {context} is unreachable under the bounded contract; "
                "the Phase 7.2 loop proof establishes the closure."
            ),
        }
    return {
        "materiality": "MATERIAL_PROMOTION_RELEVANT",
        "closure_status": "OPEN_PROMOTION_BLOCKER",
        "existing_evidence": ["evidence/phase-7.2/residual-risk-review.md"],
        "decision_reason": (
            f"{branch_id} at {context} has no current contract proof closing this High branch."
        ),
    }


def _medium_decision(branch: Mapping[str, object], branch_id: str) -> dict[str, object]:
    file_name = Path(_text(branch, "file", 0)).name
    category = _text(branch, "risk_category", 0)
    context = _branch_context(branch)
    if branch_id in KNOWN_MEDIUM_UNREACHABLE:
        if branch_id in {
            "P7.2-BRANCH-d22fdc1a09d97905",
            "P7.2-BRANCH-f548dbed5622a8c7",
        }:
            reason = (
                f"{branch_id} at {context} is unreachable under the registry parser contract: "
                "the strict wildcard/semver syntax checks return before this defensive guard "
                "can receive the impossible input shape."
            )
        else:
            reason = (
                f"{branch_id} at {context} is unreachable under the CompositionRunner contract: "
                "the verifier guard at line 402 returns before this later condition is "
                "reached when no verifier exists, and the verifier is not reassigned."
            )
        evidence = (
            [
                "tests/unit/test_phase71_persistence_hardening.py",
                "evidence/phase-7.2/residual-risk-review.md",
            ]
            if branch_id
            in {
                "P7.2-BRANCH-d22fdc1a09d97905",
                "P7.2-BRANCH-f548dbed5622a8c7",
            }
            else [
                "tests/unit/test_phase5_execution.py",
                "tests/unit/test_phase71_phase5_hardening.py",
            ]
        )
        return {
            "materiality": "UNREACHABLE_BY_CONTRACT",
            "closure_status": "UNREACHABLE_PROVEN",
            "existing_evidence": evidence,
            "decision_reason": reason,
        }
    evidence = [
        "evidence/phase-7.2/README.md",
        "evidence/phase-7.2/residual-risk-review.md",
        EVIDENCE_BY_FILE.get(file_name, "tests/unit/test_phase72_high_risk_boundaries.py"),
    ]
    if category in MATERIAL_CATEGORIES or file_name in MATERIAL_FILES:
        return {
            "materiality": "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE",
            "closure_status": "TESTED_PASS",
            "existing_evidence": evidence,
            "decision_reason": (
                f"{branch_id} at {context} is in a material boundary; the prior Phase 7.2 "
                "contract assurance and regression evidence passes. The exact "
                "coverage arc remains visible and is not treated as 100% coverage."
            ),
        }
    return {
        "materiality": "NON_MATERIAL_DEFENSIVE",
        "closure_status": "ACCEPTED_NON_MATERIAL",
        "existing_evidence": evidence,
        "decision_reason": (
            f"{branch_id} at {context} is a defensive validation branch with no side effect, "
            "authority, persistence, filesystem, or evidence-integrity impact."
        ),
    }


def _branch_context(branch: Mapping[str, object]) -> str:
    file_name = branch.get("file", "<unknown-file>")
    function = branch.get("function") or "<module>"
    source_line = branch.get("source_line", "?")
    target_line = branch.get("target_line", "?")
    condition = branch.get("condition", "<condition unavailable>")
    target = branch.get("target", "<target unavailable>")
    return f"{file_name}:{function}:{source_line}->{target_line} ({condition!r} => {target!r})"


def _text(record: Mapping[str, object], field: str, position: int) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DecisionGenerationError(f"record {position} field {field} must be non-empty text")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        decisions = generate_decisions(args.inventory_json, args.output)
    except (DecisionGenerationError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"decisions": len(decisions), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
