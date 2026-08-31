"""Unit tests for the Phase 7.3 semantic inventory generator."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from generate_phase73_inventory import (  # noqa: E402
    InventoryGenerationError,
    build_inventory,
    generate_outputs,
)


def _branch(
    branch_id: str,
    *,
    risk_level: str = "low",
    source_line: int = 10,
    target: str = "return fallback",
    closure_evidence: str = "evidence/phase-7.2/traceability.json",
) -> dict[str, object]:
    return {
        "branch_id": branch_id,
        "file": "src/example.py",
        "function": "example",
        "source_line": source_line,
        "target_line": source_line + 1,
        "target": target,
        "risk_category": "PERSISTENCE",
        "risk_level": risk_level,
        "classification_basis": "the source branch was reviewed against the risk matrix",
        "closure_evidence": closure_evidence,
        "behavioral_requirement": "Preserve the persisted invariant and report failure honestly.",
    }


def _source(*branches: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "P7.2-HIGH-RISK-BRANCH-INVENTORY-1",
        "phase": "PHASE7.2",
        "feature_freeze": "P7_2_FEATURE_FREEZE",
        "branches": list(branches),
        "risk_counts": {"high": 999, "medium": 999, "low": 999},
        "review_status": "this prose must not influence generated counts",
    }


def test_preserves_branch_identity_and_translates_phase72_fields() -> None:
    source = _source(
        _branch("P7.2-BRANCH-HIGH", risk_level="high", source_line=41, target="raise Error"),
        _branch("P7.2-BRANCH-LOW", source_line=17),
    )

    generated = build_inventory(source)

    records = cast(list[dict[str, object]], generated["branches"])
    source_records = cast(list[dict[str, object]], source["branches"])
    high, low = records
    assert high["branch_id"] == "P7.2-BRANCH-HIGH"
    assert high["file"] == "src/example.py"
    assert high["function"] == "example"
    assert high["source_line"] == 41
    assert high["branch_target"] == "raise Error"
    assert high["category"] == "PERSISTENCE"
    assert high["risk_reason"] == source_records[0]["classification_basis"]
    assert high["existing_evidence"] == ["evidence/phase-7.2/traceability.json"]
    assert high["closure_requirement"] == source_records[0]["behavioral_requirement"]
    assert high["materiality"] == "MATERIAL_PROMOTION_RELEVANT"
    assert high["closure_status"] == "OPEN_PROMOTION_BLOCKER"
    assert low["materiality"] == "NON_MATERIAL_DEFENSIVE"
    assert low["closure_status"] == "ACCEPTED_NON_MATERIAL"
    assert all(record["closure_status"] != "DEFERRED_BLOCKING_PROMOTION" for record in records)


def test_preserves_exact_condition_and_target_line_for_branch_local_review() -> None:
    branch = _branch("P7.2-BRANCH-CONTEXT", source_line=41, target="raise Error")
    branch["condition"] = "if invalid:"
    source = _source(branch)

    generated = build_inventory(source)

    record = cast(list[dict[str, object]], generated["branches"])[0]
    assert record["condition"] == "if invalid:"
    assert record["target_line"] == 42


def test_preserves_negative_exit_target_lines_from_branch_coverage() -> None:
    branch = _branch("P7.2-BRANCH-EXIT", source_line=41, target="<exit>")
    branch["target_line"] = -40
    source = _source(branch)

    generated = build_inventory(source)

    record = cast(list[dict[str, object]], generated["branches"])[0]
    assert record["target_line"] == -40


def test_medium_branch_requires_an_explicit_decision() -> None:
    source = _source(_branch("P7.2-BRANCH-MEDIUM", risk_level="medium"))

    with pytest.raises(InventoryGenerationError, match="Medium.*decision"):
        build_inventory(source)


def test_explicit_decision_overrides_medium_heuristic() -> None:
    source = _source(_branch("P7.2-BRANCH-MEDIUM", risk_level="medium"))
    decisions = {
        "P7.2-BRANCH-MEDIUM": {
            "materiality": "NON_MATERIAL_DEFENSIVE",
            "closure_status": "ACCEPTED_NON_MATERIAL",
            "existing_evidence": ["tests/unit/test_example.py::test_defensive_branch"],
            "risk_reason": "A contract test proves this branch is defensive only.",
        }
    }

    generated = build_inventory(source, decisions)

    record = cast(list[dict[str, object]], generated["branches"])[0]
    assert record["materiality"] == "NON_MATERIAL_DEFENSIVE"
    assert record["closure_status"] == "ACCEPTED_NON_MATERIAL"
    assert record["existing_evidence"] == ["tests/unit/test_example.py::test_defensive_branch"]
    assert record["risk_reason"] == "A contract test proves this branch is defensive only."


def test_explicit_high_unreachable_decision_is_preserved() -> None:
    source = _source(_branch("P7.2-BRANCH-HIGH", risk_level="high"))
    decisions = {
        "decisions": [
            {
                "branch_id": "P7.2-BRANCH-HIGH",
                "materiality": "MATERIAL_PROMOTION_RELEVANT",
                "closure_status": "UNREACHABLE_PROVEN",
                "existing_evidence": ["evidence/phase-7.3/unreachable-proof.json"],
            }
        ]
    }

    generated = build_inventory(source, decisions)

    record = cast(list[dict[str, object]], generated["branches"])[0]
    assert record["risk_level"] == "high"
    assert record["closure_status"] == "UNREACHABLE_PROVEN"
    assert record["existing_evidence"] == ["evidence/phase-7.3/unreachable-proof.json"]


def test_risk_counts_and_semantic_counts_come_from_generated_records() -> None:
    source = _source(
        _branch("P7.2-BRANCH-HIGH", risk_level="high"),
        _branch("P7.2-BRANCH-MEDIUM", risk_level="medium", source_line=20),
        _branch("P7.2-BRANCH-LOW", risk_level="low", source_line=30),
    )
    decisions = {
        "P7.2-BRANCH-MEDIUM": {
            "materiality": "MATERIAL_PROMOTION_RELEVANT",
            "closure_status": "TESTED_PASS",
        }
    }

    generated = build_inventory(source, decisions)

    expected = {
        "total": 3,
        "high": 1,
        "medium": 1,
        "low": 1,
        "classified_high": 1,
        "classified_medium": 1,
        "classified_low": 1,
        "open_actionable_high": 1,
        "open_actionable_medium": 0,
        "promotion_blocking_high": 1,
        "promotion_blocking_medium": 0,
        "closed_high": 0,
        "closed_medium": 1,
        "material_medium": 1,
        "accepted_residual_medium": 0,
        "blocked_medium": 0,
    }
    assert cast(dict[str, int], generated["semantic_counts"]) == expected
    assert cast(dict[str, int], generated["risk_counts"]) == {
        "high": 1,
        "medium": 1,
        "low": 1,
    }


def test_generate_outputs_writes_json_and_markdown(tmp_path: Path) -> None:
    source_path = tmp_path / "phase72.json"
    output_dir = tmp_path / "out"
    source_path.write_text(
        json.dumps(_source(_branch("P7.2-BRANCH-LOW")), ensure_ascii=False),
        encoding="utf-8",
    )

    generated = generate_outputs(source_path, output_dir)

    json_path = output_dir / "medium-risk-inventory.json"
    markdown_path = output_dir / "medium-risk-inventory.md"
    assert json_path.is_file()
    assert markdown_path.is_file()
    assert json.loads(json_path.read_text(encoding="utf-8")) == generated
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Phase 7.3 Semantic Residual Inventory" in markdown
    assert "## Semantic counts" in markdown
    assert "| `total` | 1 |" in markdown
    assert "| `P7.2-BRANCH-LOW` | `src/example.py` | `example` | 10 |" in markdown


def test_empty_module_function_is_normalized_for_coverage_module_branches() -> None:
    source = _source(_branch("P7.2-BRANCH-MODULE"))
    branches = source["branches"]
    assert isinstance(branches, list)
    assert isinstance(branches[0], dict)
    branches[0]["function"] = ""

    generated = build_inventory(source)

    generated_branches = generated["branches"]
    assert isinstance(generated_branches, list)
    assert isinstance(generated_branches[0], dict)
    assert generated_branches[0]["function"] == "<module>"
