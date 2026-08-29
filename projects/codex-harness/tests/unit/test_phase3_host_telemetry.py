from __future__ import annotations

from pathlib import Path

import pytest

from harness_kernel.phase3_host import CodexHostAdapter
from harness_kernel.phase3_models import (
    CapabilityLifecycle,
    CapabilityRoot,
    ObservationStatus,
    Phase3Limits,
    RootScope,
)
from harness_kernel.phase3_telemetry import Phase3Telemetry, TelemetryError


def test_host_adapter_reports_real_snapshot_without_load_claim(tmp_path: Path) -> None:
    adapter = CodexHostAdapter(
        project_root=tmp_path,
        home_dir=tmp_path / "home",
        limits=Phase3Limits(),
    )

    snapshot = adapter.inspect_host()
    observation = adapter.observe_load_state("demo")

    assert snapshot.fingerprint.startswith("sha256:")
    assert snapshot.observation_status is ObservationStatus.OBSERVED
    assert observation.status is ObservationStatus.UNAVAILABLE
    assert observation.loaded is False
    assert "load" in observation.reason.lower()


def test_host_adapter_bounds_explicit_root_iterables(tmp_path: Path) -> None:
    adapter = CodexHostAdapter(
        project_root=tmp_path,
        home_dir=tmp_path / "home",
        limits=Phase3Limits(max_roots=2),
    )
    consumed = 0

    def roots():
        nonlocal consumed
        for index in range(10_000):
            consumed += 1
            yield CapabilityRoot(f"root-{index}", RootScope.PROJECT, str(tmp_path))

    with pytest.raises(ValueError, match="root count bound"):
        adapter.discover_capabilities(roots())

    assert consumed <= 3


def test_telemetry_distinguishes_plan_context_and_loaded() -> None:
    telemetry = Phase3Telemetry()
    telemetry = telemetry.record("demo", CapabilityLifecycle.DISCOVERED, ObservationStatus.OBSERVED)
    telemetry = telemetry.record(
        "demo", CapabilityLifecycle.LOAD_PLANNED, ObservationStatus.INFERRED
    )
    telemetry = telemetry.record(
        "demo", CapabilityLifecycle.CONTEXT_PREPARED, ObservationStatus.OBSERVED
    )

    assert [event.lifecycle for event in telemetry.events] == [
        CapabilityLifecycle.DISCOVERED,
        CapabilityLifecycle.LOAD_PLANNED,
        CapabilityLifecycle.CONTEXT_PREPARED,
    ]
    with pytest.raises(TelemetryError):
        telemetry.record("demo", CapabilityLifecycle.HOST_LOADED, ObservationStatus.INFERRED)


def test_telemetry_redacts_paths_and_sensitive_values() -> None:
    telemetry = Phase3Telemetry().record(
        "demo",
        CapabilityLifecycle.DISCOVERED,
        ObservationStatus.OBSERVED,
        data={"path": "/home/ricardo/private", "api_token": "secret"},
    )

    value = str(telemetry.to_dict())
    assert "ricardo" not in value
    assert "secret" not in value
    assert "<REDACTED>" in value


def test_telemetry_rejects_unobserved_execution() -> None:
    with pytest.raises(TelemetryError):
        Phase3Telemetry().record(
            "demo",
            CapabilityLifecycle.EXECUTED,
            ObservationStatus.UNKNOWN,
        )
