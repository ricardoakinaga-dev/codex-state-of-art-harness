"""Tests for the Phase 7.3 cross-artifact consistency validator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from generate_phase73_materiality_review import build_review  # noqa: E402
from phase73_risk_semantics import semantic_counts  # noqa: E402
from validate_phase73_consistency import (  # noqa: E402
    ConsistencyError,
    validate_consistency,
)


def _record(
    branch_id: str,
    risk_level: str,
    materiality: str,
    closure_status: str,
) -> dict[str, object]:
    return {
        "branch_id": branch_id,
        "file": "src/example.py",
        "function": "example",
        "source_line": 10,
        "branch_target": "return value",
        "category": "PERSISTENCE",
        "risk_reason": "The branch protects a persisted invariant.",
        "materiality": materiality,
        "existing_evidence": ["evidence/test.json"],
        "closure_requirement": "Direct test or reviewable proof.",
        "closure_status": closure_status,
        "risk_level": risk_level,
    }


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def _fixture_paths(tmp_path: Path) -> dict[str, Path]:
    records = [
        _record(
            "P7.3-BRANCH-HIGH",
            "high",
            "MATERIAL_PROMOTION_RELEVANT",
            "TESTED_PASS",
        ),
        _record(
            "P7.3-BRANCH-MEDIUM",
            "medium",
            "NON_MATERIAL_DEFENSIVE",
            "ACCEPTED_NON_MATERIAL",
        ),
    ]
    counts = semantic_counts(records)
    phase72 = {
        "branches": [
            {
                "branch_id": record["branch_id"],
                "risk_level": record["risk_level"],
                "file": record["file"],
                "function": record["function"],
                "source_line": record["source_line"],
                "target": record["branch_target"],
            }
            for record in records
        ],
        "risk_counts": {"high": 1, "medium": 1, "low": 0},
    }
    traceability = {"records": [{"branch_id": record["branch_id"]} for record in records]}
    phase73 = {
        "branches": records,
        "risk_counts": {"high": 1, "medium": 1, "low": 0},
        "semantic_counts": counts,
    }
    final_report = (
        "# Phase 7.3 Final Report\n\n"
        "<!-- PHASE73_SEMANTIC_COUNTS_START -->\n"
        f"{json.dumps(counts, sort_keys=True)}\n"
        "<!-- PHASE73_SEMANTIC_COUNTS_END -->\n"
    )
    final_report_path = tmp_path / "final-report.md"
    final_report_path.write_text(final_report, encoding="utf-8")
    return {
        "phase72_inventory": _write_json(tmp_path / "phase72-inventory.json", phase72),
        "phase72_traceability": _write_json(tmp_path / "phase72-traceability.json", traceability),
        "phase73_inventory": _write_json(tmp_path / "phase73-inventory.json", phase73),
        "readiness": _write_json(tmp_path / "readiness.json", {"risk_counts": counts}),
        "ledger": _write_json(tmp_path / "ledger.json", {"semantic_counts": counts}),
        "final_report": final_report_path,
    }


def test_consistency_validator_accepts_matching_branch_sets_and_counts(tmp_path: Path) -> None:
    paths = _fixture_paths(tmp_path)
    paths["final_report"].write_text(
        "# Phase 7.3 Final Report\n\n"
        "<!-- PHASE73_SEMANTIC_COUNTS_START -->\n"
        f"{json.dumps(json.loads(paths['readiness'].read_text())['risk_counts'], sort_keys=True)}\n"
        "<!-- PHASE73_SEMANTIC_COUNTS_END -->\n",
        encoding="utf-8",
    )

    report = validate_consistency(**paths)

    assert report["status"] == "PASS"
    assert report["branch_set_consistent"] is True
    assert report["count_surfaces_consistent"] is True


def test_consistency_validator_rejects_readiness_count_drift(tmp_path: Path) -> None:
    paths = _fixture_paths(tmp_path)
    readiness = json.loads(paths["readiness"].read_text(encoding="utf-8"))
    readiness["risk_counts"]["medium"] = 2
    paths["readiness"].write_text(json.dumps(readiness), encoding="utf-8")

    with pytest.raises(ConsistencyError, match="readiness"):
        validate_consistency(**paths)


def test_consistency_validator_rejects_branch_set_drift(tmp_path: Path) -> None:
    paths = _fixture_paths(tmp_path)
    phase73 = json.loads(paths["phase73_inventory"].read_text(encoding="utf-8"))
    phase73["branches"].pop()
    paths["phase73_inventory"].write_text(json.dumps(phase73), encoding="utf-8")

    with pytest.raises(ConsistencyError, match="branch set"):
        validate_consistency(**paths)


def test_consistency_validator_requires_authority_reconciliation_for_delta(
    tmp_path: Path,
) -> None:
    paths = _fixture_paths(tmp_path)
    authority = json.loads(paths["phase72_inventory"].read_text(encoding="utf-8"))
    authority["branches"][0]["branch_id"] = "P7.2-AUTHORITY-ONLY"
    paths["authoritative_phase72_inventory"] = _write_json(
        tmp_path / "authoritative-phase72.json", authority
    )

    with pytest.raises(ConsistencyError, match="reconciliation"):
        validate_consistency(**paths)


def test_consistency_validator_requires_material_medium_proof(tmp_path: Path) -> None:
    paths = _fixture_paths(tmp_path)
    phase73 = json.loads(paths["phase73_inventory"].read_text(encoding="utf-8"))
    medium = phase73["branches"][1]
    medium["materiality"] = "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE"
    medium["closure_status"] = "TESTED_PASS"
    counts = semantic_counts(phase73["branches"])
    phase73["semantic_counts"] = counts
    paths["phase73_inventory"].write_text(json.dumps(phase73), encoding="utf-8")
    paths["readiness"].write_text(json.dumps({"risk_counts": counts}), encoding="utf-8")
    paths["ledger"].write_text(json.dumps({"semantic_counts": counts}), encoding="utf-8")
    paths["final_report"].write_text(
        "<!-- PHASE73_SEMANTIC_COUNTS_START -->\n"
        f"{json.dumps(counts)}\n"
        "<!-- PHASE73_SEMANTIC_COUNTS_END -->\n",
        encoding="utf-8",
    )

    with pytest.raises(ConsistencyError, match="material proof"):
        validate_consistency(**paths)


def test_consistency_validator_rejects_material_proof_without_behavioral_tests(
    tmp_path: Path,
) -> None:
    paths = _fixture_paths(tmp_path)
    phase73 = json.loads(paths["phase73_inventory"].read_text(encoding="utf-8"))
    medium = phase73["branches"][1]
    medium["materiality"] = "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE"
    medium["closure_status"] = "TESTED_PASS"
    counts = semantic_counts(phase73["branches"])
    phase73["semantic_counts"] = counts
    paths["phase73_inventory"].write_text(json.dumps(phase73), encoding="utf-8")
    paths["readiness"].write_text(json.dumps({"risk_counts": counts}), encoding="utf-8")
    paths["ledger"].write_text(json.dumps({"semantic_counts": counts}), encoding="utf-8")
    paths["final_report"].write_text(
        "<!-- PHASE73_SEMANTIC_COUNTS_START -->\n"
        f"{json.dumps(counts)}\n"
        "<!-- PHASE73_SEMANTIC_COUNTS_END -->\n",
        encoding="utf-8",
    )
    proof = {
        "records": [
            {
                "branch_id": medium["branch_id"],
                "file": medium["file"],
                "function": medium["function"],
                "source_line": medium["source_line"],
                "branch_target": medium["branch_target"],
                "category": medium["category"],
                "proof_status": "REVIEWABLE",
                "exact_arc_direct_execution": False,
                "source_context": {
                    "condition": "if invalid:",
                    "target": medium["branch_target"],
                    "target_line": 11,
                },
                "prior_contract_tests": [],
                "prior_traceability": {
                    "mapping_strength": "NO_DIRECT_TEST_MAPPING",
                    "test_result": "NO_DIRECT_RESULT",
                    "coverage_result": "RESIDUAL_BRANCH_NOT_DIRECTLY_COVERED",
                },
                "proof_evidence": ["tests/unit/test_example.py"],
                "proof_type": "PRIOR_CONTRACT_EVIDENCE_REVIEW",
                "proof_statement": "independent review required",
                "source_record_digest": "sha256:" + "a" * 64,
            }
        ]
    }
    material_proof = _write_json(tmp_path / "material-proof.json", proof)

    with pytest.raises(ConsistencyError, match="behavioral evidence"):
        validate_consistency(**paths, material_proof=material_proof)


def test_consistency_validator_binds_branch_local_materiality_review(tmp_path: Path) -> None:
    paths = _fixture_paths(tmp_path)
    phase73 = json.loads(paths["phase73_inventory"].read_text(encoding="utf-8"))
    decisions = {
        "decisions": {
            record["branch_id"]: {
                "materiality": record["materiality"],
                "closure_status": record["closure_status"],
                "decision_reason": f"Reviewed {record['branch_id']} at its exact source branch.",
                "existing_evidence": record["existing_evidence"],
            }
            for record in phase73["branches"]
        }
    }
    review = build_review(phase73, decisions)
    review_records = review["records"]
    assert isinstance(review_records, list)
    first_context = review_records[0]["source_context"]
    assert isinstance(first_context, dict)
    first_context["file"] = "src/drifted.py"
    review_path = _write_json(tmp_path / "materiality-review.json", review)

    with pytest.raises(ConsistencyError, match="materiality review"):
        validate_consistency(**paths, materiality_review=review_path)
