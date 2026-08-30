from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
SCENARIOS = (
    PROJECT_ROOT
    / ".harness"
    / "capabilities"
    / "backend-engineering-vnext"
    / "evals"
    / "scenarios.json"
)


def test_backend_eval_catalog_has_forty_or_more_ordered_cases() -> None:
    catalog = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    scenarios = catalog["scenarios"]

    assert catalog["schema_version"] == "P7-EVAL-1"
    assert len(scenarios) >= 40
    assert [item["id"] for item in scenarios] == [
        f"P7-SC-{index:03d}" for index in range(1, len(scenarios) + 1)
    ]
    assert len({item["category"] for item in scenarios}) >= 12


def test_backend_eval_catalog_covers_security_routing_and_operational_risks() -> None:
    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]
    categories = {item["category"] for item in scenarios}

    assert {
        "negative_routing",
        "overengineering",
        "migration",
        "security_handoff",
        "transactions",
        "concurrency",
        "idempotency",
        "performance",
        "prompt_injection",
        "tool_escalation",
        "scope_creep",
        "stale_evidence",
        "artifact_substitution",
    } <= categories
    for scenario in scenarios:
        assert scenario["oracle"].strip()
        assert scenario["rationale"].strip()
        assert scenario["expected_outcome"] in {"PASS", "BLOCKED", "FAIL", "PARTIAL"}
