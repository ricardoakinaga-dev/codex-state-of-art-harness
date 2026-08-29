from __future__ import annotations

from pathlib import Path

import pytest

from harness_kernel.classification import classify_task
from harness_kernel.phase3_discovery import CapabilityDiscovery
from harness_kernel.phase3_integration import IntegrationError, Phase3RouterBridge
from harness_kernel.phase3_models import CapabilityRoot, Phase3Limits, RootScope


def test_selected_observed_capability_bridges_to_existing_router(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = root / "engineering-helper"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: engineering-helper\ndescription: helper\n"
        "activates_when:\n  - engineering task\n"
        "do_not_activate_when: never engineering task\n---\nbody\n",
        encoding="utf-8",
    )
    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )
    profile = classify_task(
        "engineering task",
        task_id="TASK-P3",
        run_id="RUN-P3",
        created_at="2026-08-28T00:00:00Z",
    )

    bridge = Phase3RouterBridge()
    route, registry = bridge.route(profile, (inventory.capabilities[0],))

    assert registry.find("engineering-helper") is not None
    assert route.route_status.value in {"SELECTED", "ROUTED", "DEGRADED", "CONDITIONAL"}
    assert route.decision


def test_router_bridge_bounds_record_iterables(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = root / "bounded-bridge"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: bounded-bridge\ndescription: helper\ndo_not_activate_when: never\n---\nbody\n",
        encoding="utf-8",
    )
    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )
    record = inventory.capabilities[0]
    consumed = 0

    def records():
        nonlocal consumed
        for _ in range(10_000):
            consumed += 1
            yield record

    with pytest.raises(IntegrationError, match="record count bound"):
        Phase3RouterBridge(Phase3Limits(max_capabilities=2)).registry(records())

    assert consumed <= 3
