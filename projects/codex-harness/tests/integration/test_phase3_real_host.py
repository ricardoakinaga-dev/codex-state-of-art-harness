from __future__ import annotations

import json
from pathlib import Path

from harness_kernel.phase3_host import CodexHostAdapter, public_inventory, public_snapshot
from harness_kernel.phase3_models import ObservationStatus


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
