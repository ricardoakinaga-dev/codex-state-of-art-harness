"""Tests for the Phase 7.3 material Medium proof matrix."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from generate_phase73_material_proof import (  # noqa: E402
    MaterialProofError,
    build_proof,
    render_markdown,
)


def _branch(branch_id: str, *, materiality: str) -> dict[str, object]:
    return {
        "branch_id": branch_id,
        "file": "src/example.py",
        "function": "example",
        "source_line": 10,
        "branch_target": 'raise BoundaryError("invalid")',
        "category": "PERSISTENCE",
        "closure_requirement": "Preserve the persisted invariant.",
        "materiality": materiality,
        "risk_level": "medium",
        "existing_evidence": ["tests/unit/test_example.py"],
    }


def _trace(branch_id: str) -> dict[str, object]:
    return {
        "branch_id": branch_id,
        "location": {
            "condition": "if invalid:",
            "target": 'raise BoundaryError("invalid")',
            "target_line": 11,
        },
        "mapping_strength": "BEHAVIORAL_TARGETED_OR_REGRESSION",
        "test_result": "PASS",
        "coverage_result": "RESIDUAL_BRANCH_NOT_DIRECTLY_COVERED",
        "tests": [
            {
                "test_id": "P72-T01",
                "path": "tests/unit/test_example.py",
                "nodeid": "test_example.py::test_invalid",
                "result": "PASS",
            }
        ],
    }


def test_build_proof_binds_exact_source_and_disclaims_direct_coverage() -> None:
    branch_id = "P7.3-BRANCH-MATERIAL"
    proof = build_proof(
        {
            "branches": [
                _branch(
                    branch_id,
                    materiality="MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE",
                )
            ]
        },
        {"records": [_trace(branch_id)]},
    )

    assert proof["status"] == "REVIEWABLE_PROOF_MATRIX"
    assert proof["summary"] == {
        "material_medium_count": 1,
        "proof_record_count": 1,
        "mapping_strength_counts": {"BEHAVIORAL_TARGETED_OR_REGRESSION": 1},
        "exact_arc_direct_execution_count": 0,
    }
    record = proof["records"][0]
    assert record["branch_id"] == branch_id
    assert record["source_context"]["condition"] == "if invalid:"
    assert record["exact_arc_direct_execution"] is False
    assert "tests/unit/test_example.py" in record["proof_evidence"]
    assert "Independent review" in record["proof_statement"]
    assert "| `P7.3-BRANCH-MATERIAL` |" in render_markdown(proof)


def test_build_proof_rejects_a_material_branch_without_traceability() -> None:
    with pytest.raises(MaterialProofError, match="missing traceability"):
        build_proof(
            {
                "branches": [
                    _branch(
                        "P7.3-BRANCH-MATERIAL",
                        materiality="MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE",
                    )
                ]
            },
            {"records": []},
        )


def test_build_proof_rejects_material_branch_without_behavioral_evidence() -> None:
    branch_id = "P7.3-BRANCH-NO-BEHAVIORAL-EVIDENCE"
    trace = _trace(branch_id)
    trace["mapping_strength"] = "NO_DIRECT_TEST_MAPPING"
    trace["tests"] = []

    with pytest.raises(MaterialProofError, match="behavioral evidence"):
        build_proof(
            {
                "branches": [
                    _branch(
                        branch_id,
                        materiality="MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE",
                    )
                ]
            },
            {"records": [trace]},
        )


def test_non_material_branches_are_not_added_to_proof_matrix() -> None:
    proof = build_proof(
        {"branches": [_branch("P7.3-BRANCH-LOW", materiality="NON_MATERIAL_DEFENSIVE")]},
        {"records": []},
    )

    assert proof["summary"]["material_medium_count"] == 0
    assert proof["records"] == []
