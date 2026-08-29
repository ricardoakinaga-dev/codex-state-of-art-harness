from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness_kernel.classification import classify_task
from harness_kernel.phase3_host import CodexHostAdapter, public_inventory, public_snapshot
from harness_kernel.phase3_integration import Phase3RouterBridge
from harness_kernel.phase3_models import ObservationStatus
from harness_kernel.phase3_resolution import ResolutionEngine


def test_real_host_smoke_is_read_only_and_sanitized() -> None:
    project = Path(__file__).parents[2]
    home = Path.home()
    adapter = CodexHostAdapter(project_root=project, home_dir=home)

    snapshot = adapter.inspect_host()
    inventory = adapter.discover_capabilities(snapshot.roots)
    snapshot_json = json.dumps(
        public_snapshot(snapshot, workspace_root=project, home_dir=home),
        sort_keys=True,
    )
    inventory_json = json.dumps(
        public_inventory(inventory, workspace_root=project, home_dir=home),
        sort_keys=True,
    )

    assert snapshot.observation_status is ObservationStatus.OBSERVED
    assert snapshot.capability_count == len(inventory.capabilities)
    assert adapter.observe_load_state("not-discovered").loaded is False
    assert str(home) not in snapshot_json
    assert str(home) not in inventory_json
    assert all(not root.mutable for root in snapshot.roots)


def test_real_cross_agent_capabilities_are_routable_or_explicitly_blocked() -> None:
    project = Path(__file__).parents[2]
    adapter = CodexHostAdapter(project_root=project, home_dir=Path.home())
    inventory = adapter.discover_capabilities()
    by_id: dict[str, list[object]] = {}
    for record in inventory.capabilities:
        by_id.setdefault(record.capability_id, []).append(record)

    present = {
        name: by_id[name]
        for name in (
            "design-director",
            "engineering-framework",
            "everything-claude-code-conventions",
        )
        if name in by_id
    }
    if not present:
        pytest.skip("cross-agent capability fixtures are not installed on this host")

    engine = ResolutionEngine()
    design_result = (
        engine.resolve(inventory, "design-director") if "design-director" in present else None
    )
    conventions_result = (
        engine.resolve(inventory, "everything-claude-code-conventions")
        if "everything-claude-code-conventions" in present
        else None
    )
    for result in (design_result, conventions_result):
        if result is not None:
            assert result.status.value in {"RESOLVED", "BLOCKED"}
            if result.status.value == "RESOLVED":
                assert result.selected[0].load_eligibility == "ELIGIBLE_DECLARATIVE_METADATA_ONLY"

    engineering_result = (
        engine.resolve(inventory, "engineering-framework")
        if "engineering-framework" in present
        else None
    )
    if engineering_result is not None and len(present["engineering-framework"]) > 1:
        assert engineering_result.status.value == "BLOCKED"
        assert "CAPABILITY_DIVERGENCE" in engineering_result.blockers

    routable = tuple(
        result.selected[0]
        for result in (design_result, conventions_result)
        if result is not None and result.status.value == "RESOLVED" and result.selected
    )
    if routable:
        profile = classify_task(
            "review design and engineering process",
            requested_outcome="select declarative cross-agent capability metadata",
            task_id="TASK-P3-REAL-CROSS-AGENT",
            run_id="RUN-P3-REAL-CROSS-AGENT",
            created_at="2026-08-29T00:00:00Z",
        )
        route, registry = Phase3RouterBridge().route(profile, routable)
        assert registry.find(routable[0].capability_id) is not None
        assert route.route_status.value in {"SELECTED", "ROUTED", "DEGRADED", "CONDITIONAL"}
