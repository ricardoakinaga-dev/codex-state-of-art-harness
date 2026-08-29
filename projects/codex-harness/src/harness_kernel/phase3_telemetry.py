"""Honest Phase 3 lifecycle telemetry with immutable append semantics."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .phase3_models import (
    CapabilityLifecycle,
    ObservationStatus,
    Phase3Event,
    Phase3EventType,
    public_data,
)
from .phase3_paths import redact_path


class TelemetryError(ValueError):
    """Raised when telemetry would claim an unobserved host state."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


_EVENT_TYPES = {
    CapabilityLifecycle.DISCOVERED: Phase3EventType.DISCOVERED,
    CapabilityLifecycle.INSPECTED: Phase3EventType.DISCOVERED,
    CapabilityLifecycle.SELECTED: Phase3EventType.SELECTED,
    CapabilityLifecycle.LOAD_PLANNED: Phase3EventType.LOAD_PLANNED,
    CapabilityLifecycle.CONTEXT_PREPARED: Phase3EventType.CONTEXT_PREPARED,
    CapabilityLifecycle.HOST_LOADED: Phase3EventType.HOST_LOADED,
    CapabilityLifecycle.EXECUTED: Phase3EventType.EXECUTED,
    CapabilityLifecycle.BLOCKED: Phase3EventType.BLOCKED,
    CapabilityLifecycle.REJECTED: Phase3EventType.REJECTED,
    CapabilityLifecycle.INCOMPATIBLE: Phase3EventType.BLOCKED,
    CapabilityLifecycle.STALE: Phase3EventType.BLOCKED,
    CapabilityLifecycle.AMBIGUOUS: Phase3EventType.BLOCKED,
}

_STAGE_LIFECYCLES = {
    Phase3EventType.HOST_INSPECTION_STARTED: CapabilityLifecycle.DISCOVERED,
    Phase3EventType.HOST_INSPECTION_COMPLETED: CapabilityLifecycle.INSPECTED,
    Phase3EventType.ROOT_DISCOVERED: CapabilityLifecycle.DISCOVERED,
    Phase3EventType.METADATA_PARSED: CapabilityLifecycle.INSPECTED,
    Phase3EventType.MANIFEST_SYNTHESIZED: CapabilityLifecycle.INSPECTED,
    Phase3EventType.DUPLICATE_FOUND: CapabilityLifecycle.AMBIGUOUS,
    Phase3EventType.DIVERGENCE_FOUND: CapabilityLifecycle.BLOCKED,
    Phase3EventType.COMPATIBILITY_CHECKED: CapabilityLifecycle.INSPECTED,
    Phase3EventType.TRUST_EVALUATED: CapabilityLifecycle.INSPECTED,
    Phase3EventType.LOAD_OBSERVED: CapabilityLifecycle.HOST_LOADED,
    Phase3EventType.LOAD_UNOBSERVABLE: CapabilityLifecycle.BLOCKED,
    Phase3EventType.REGISTERED_FROM_HOST: CapabilityLifecycle.SELECTED,
    Phase3EventType.REJECTED_FROM_HOST: CapabilityLifecycle.REJECTED,
}


_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9$])/(?:[^\s,;]+)")
_SENSITIVE_KEY = re.compile(
    r"(?:secret|token|password|credential|authorization|cookie|private|passphrase|bearer|session|"
    r"(?:api|access|client|encryption|signing)[_-]?key|(?:^|[_-])key(?:$|[_-]))",
    re.I,
)


def _redact_value(value: str) -> str:
    try:
        if Path(value).is_absolute():
            return redact_path(value, home_dir=Path.home())
    except (OSError, RuntimeError, ValueError):
        return "$REDACTED_PATH"
    return _ABSOLUTE_PATH.sub(
        lambda match: "$PATH/" + hashlib.sha256(match.group(0).encode()).hexdigest()[:12],
        value,
    )


def _safe_data(data: Mapping[str, str] | None) -> dict[str, str]:
    if not data:
        return {}
    result: dict[str, str] = {}
    for key, value in list(data.items())[:32]:
        raw_key = str(key)
        normalized_key = raw_key[:80]
        if _SENSITIVE_KEY.search(raw_key):
            result[normalized_key] = "<REDACTED>"
        else:
            result[normalized_key] = _redact_value(str(value))[:300]
    return result


@dataclass(frozen=True, slots=True)
class Phase3Telemetry:
    events: tuple[Phase3Event, ...] = ()
    max_events: int = 1_024

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_events, int)
            or isinstance(self.max_events, bool)
            or self.max_events < 1
        ):
            raise TelemetryError("max_events must be a positive integer")
        if len(self.events) > self.max_events:
            raise TelemetryError("telemetry event bound exceeded")
        object.__setattr__(self, "events", tuple(self.events))

    def record(
        self,
        capability_id: str,
        lifecycle: CapabilityLifecycle,
        observation: ObservationStatus,
        *,
        timestamp: str | None = None,
        data: Mapping[str, str] | None = None,
    ) -> Phase3Telemetry:
        if not capability_id or "\x00" in capability_id:
            raise TelemetryError("capability ID is invalid")
        if not isinstance(lifecycle, CapabilityLifecycle):
            raise TelemetryError("lifecycle is invalid")
        if not isinstance(observation, ObservationStatus):
            raise TelemetryError("observation status is invalid")
        if (
            lifecycle
            in {
                CapabilityLifecycle.HOST_LOADED,
                CapabilityLifecycle.EXECUTED,
            }
            and observation is not ObservationStatus.OBSERVED
        ):
            raise TelemetryError("runtime lifecycle telemetry requires an observed host signal")
        return self._append(
            capability_id,
            lifecycle,
            observation,
            _EVENT_TYPES[lifecycle],
            timestamp=timestamp,
            data=data,
        )

    def record_event(
        self,
        event_type: Phase3EventType,
        capability_id: str,
        observation: ObservationStatus,
        *,
        timestamp: str | None = None,
        data: Mapping[str, str] | None = None,
    ) -> Phase3Telemetry:
        """Record a host stage with an explicit event type and honest lifecycle."""

        if not isinstance(event_type, Phase3EventType) or event_type not in _STAGE_LIFECYCLES:
            raise TelemetryError("host stage event type is invalid")
        return self._append(
            capability_id,
            _STAGE_LIFECYCLES[event_type],
            observation,
            event_type,
            timestamp=timestamp,
            data=data,
        )

    def _append(
        self,
        capability_id: str,
        lifecycle: CapabilityLifecycle,
        observation: ObservationStatus,
        event_type: Phase3EventType,
        *,
        timestamp: str | None,
        data: Mapping[str, str] | None,
    ) -> Phase3Telemetry:
        if not capability_id or "\x00" in capability_id:
            raise TelemetryError("capability ID is invalid")
        if not isinstance(lifecycle, CapabilityLifecycle):
            raise TelemetryError("lifecycle is invalid")
        if not isinstance(observation, ObservationStatus):
            raise TelemetryError("observation status is invalid")
        if (
            lifecycle
            in {
                CapabilityLifecycle.HOST_LOADED,
                CapabilityLifecycle.EXECUTED,
            }
            and observation is not ObservationStatus.OBSERVED
        ):
            raise TelemetryError("runtime lifecycle telemetry requires an observed host signal")
        if len(self.events) >= self.max_events:
            raise TelemetryError("telemetry event bound exceeded")
        sequence = len(self.events) + 1
        event = Phase3Event(
            f"P3-EVT-{sequence:06d}",
            event_type,
            capability_id,
            lifecycle,
            observation,
            timestamp or _now(),
            _safe_data(data),
        )
        return Phase3Telemetry((*self.events, event), self.max_events)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "P3-TELEMETRY-1",
            "supported_event_types": [item.value for item in Phase3EventType],
            "events": public_data(self.events),
            "host_loaded_events": sum(
                1 for item in self.events if item.lifecycle is CapabilityLifecycle.HOST_LOADED
            ),
        }
