from __future__ import annotations

from pathlib import Path

import pytest

from harness_kernel.phase3_host import CodexHostAdapter
from harness_kernel.phase3_models import (
    CapabilityLifecycle,
    CapabilityRoot,
    ObservationStatus,
    Phase3EventType,
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
    assert snapshot.official_behavior["skill_discovery"] is ObservationStatus.VERIFIED_OFFICIAL
    assert (
        snapshot.official_behavior["official_ancestor_root_semantics"]
        is ObservationStatus.VERIFIED_OFFICIAL
    )
    assert (
        snapshot.official_behavior["adapter_ancestor_discovery"]
        is ObservationStatus.UNSUPPORTED_BY_HOST
    )
    assert (
        snapshot.official_behavior["host_load_observation"] is ObservationStatus.UNSUPPORTED_BY_HOST
    )
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


def test_telemetry_supports_explicit_host_stage_taxonomy_without_claiming_load() -> None:
    telemetry = Phase3Telemetry()
    for event_type in (
        Phase3EventType.HOST_INSPECTION_STARTED,
        Phase3EventType.ROOT_DISCOVERED,
        Phase3EventType.METADATA_PARSED,
        Phase3EventType.MANIFEST_SYNTHESIZED,
        Phase3EventType.DUPLICATE_FOUND,
        Phase3EventType.DIVERGENCE_FOUND,
        Phase3EventType.COMPATIBILITY_CHECKED,
        Phase3EventType.TRUST_EVALUATED,
        Phase3EventType.REGISTERED_FROM_HOST,
        Phase3EventType.LOAD_UNOBSERVABLE,
        Phase3EventType.REJECTED_FROM_HOST,
    ):
        telemetry = telemetry.record_event(
            event_type,
            "demo",
            ObservationStatus.OBSERVED,
        )

    assert telemetry.events[0].event_type is Phase3EventType.HOST_INSPECTION_STARTED
    assert telemetry.events[-2].event_type is Phase3EventType.LOAD_UNOBSERVABLE
    assert not any(item.lifecycle is CapabilityLifecycle.HOST_LOADED for item in telemetry.events)


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


def test_telemetry_redacts_compound_secret_key_names() -> None:
    telemetry = Phase3Telemetry().record(
        "demo",
        CapabilityLifecycle.DISCOVERED,
        ObservationStatus.OBSERVED,
        data={
            "session_cookie": "session-secret",
            "private_key": "private-secret",
            "accessKey": "access-secret",
        },
    )

    value = str(telemetry.to_dict())

    assert "session-secret" not in value
    assert "private-secret" not in value
    assert "access-secret" not in value


def test_telemetry_checks_untruncated_secret_key_names() -> None:
    telemetry = Phase3Telemetry().record(
        "demo",
        CapabilityLifecycle.DISCOVERED,
        ObservationStatus.OBSERVED,
        data={"x" * 80 + "private_key": "long-prefix-secret"},
    )

    assert "long-prefix-secret" not in str(telemetry.to_dict())


def test_telemetry_rejects_unobserved_execution() -> None:
    with pytest.raises(TelemetryError):
        Phase3Telemetry().record(
            "demo",
            CapabilityLifecycle.EXECUTED,
            ObservationStatus.UNKNOWN,
        )
