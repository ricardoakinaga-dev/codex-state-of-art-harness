from __future__ import annotations

import json
from pathlib import Path

from harness_kernel.classification import classify_task
from harness_kernel.registry import CapabilityRegistry
from harness_kernel.routing import minimum_route

FIXTURE = Path(__file__).parents[1] / "fixtures" / "golden" / "routing-scenarios.json"


def test_golden_routing_scenarios_match_the_bounded_oracles() -> None:
    scenarios = json.loads(FIXTURE.read_text(encoding="utf-8"))

    for scenario in scenarios:
        profile = classify_task(
            scenario["objective"],
            task_id=f"TASK-{scenario['id']}",
            run_id=f"RUN-{scenario['id']}",
            evidence_refs=(f"EVID-{scenario['id']}",),
            created_at="2026-08-28T12:00:00Z",
        )
        route = minimum_route(
            profile,
            CapabilityRegistry(),
            decision_id=f"ROUTE-{scenario['id']}",
        )
        expected = scenario["expected"]

        for field in ("domain", "complexity", "risk", "security_impact", "blast_radius"):
            if field in expected:
                assert getattr(profile, field).value == expected[field]
        if "visual_importance" in expected:
            assert profile.visual_importance.value == expected["visual_importance"]
        assert route.route_status.value == expected["route_status"]
        if "route_kind" in expected:
            assert route.route_kind.value == expected["route_kind"]
        for gate in expected.get("required_gates", []):
            assert gate in route.quality_gates
        for unresolved in expected.get("forbidden_unresolved", []):
            assert unresolved not in profile.classification_trace.unresolved
