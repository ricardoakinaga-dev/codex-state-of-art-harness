"""Honest, immutable telemetry for Phase 6 verification lifecycles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import TYPE_CHECKING

from .phase6_models import (
    Finding,
    ProcedureResult,
    VerificationInput,
    VerificationOutput,
    VerificationStatus,
    canonical_json,
    digest_payload,
    freeze_json,
    public_data,
)

if TYPE_CHECKING:
    from .phase6_composition import VerificationPlan


class Phase6TelemetryError(ValueError):
    """Raised when telemetry would overclaim a verification lifecycle."""


class Phase6EventType(StrEnum):
    VERIFICATION_CAPABILITY_SELECTED = "VERIFICATION_CAPABILITY_SELECTED"
    VERIFICATION_PLAN_CREATED = "VERIFICATION_PLAN_CREATED"
    VERIFICATION_PROCEDURE_STARTED = "VERIFICATION_PROCEDURE_STARTED"
    VERIFICATION_PROCEDURE_COMPLETED = "VERIFICATION_PROCEDURE_COMPLETED"
    VERIFICATION_PROCEDURE_BLOCKED = "VERIFICATION_PROCEDURE_BLOCKED"
    VERIFICATION_FINDING_CREATED = "VERIFICATION_FINDING_CREATED"
    VERIFICATION_REPORT_CREATED = "VERIFICATION_REPORT_CREATED"
    VERIFICATION_REPORT_STALE = "VERIFICATION_REPORT_STALE"
    VERIFICATION_FINALIZED = "VERIFICATION_FINALIZED"


@dataclass(frozen=True, slots=True)
class Phase6TelemetryEvent:
    event_id: str
    event_type: Phase6EventType
    run_id: str
    task_id: str
    capability_id: str
    observed: bool
    procedure_id: str | None = None
    criterion_id: str | None = None
    status: VerificationStatus | str | None = None
    payload: Mapping[str, object] = field(default_factory=dict)
    digest: str = ""

    def __post_init__(self) -> None:
        for name in ("event_id", "run_id", "task_id", "capability_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or "\x00" in value or len(value) > 200:
                raise Phase6TelemetryError(f"telemetry {name} is invalid")
        if not isinstance(self.event_type, Phase6EventType):
            raise Phase6TelemetryError("telemetry event_type is invalid")
        if not isinstance(self.observed, bool):
            raise Phase6TelemetryError("telemetry observed must be boolean")
        if (
            self.event_type is Phase6EventType.VERIFICATION_PROCEDURE_COMPLETED
            and not self.observed
        ):
            raise Phase6TelemetryError("unobserved procedure completion is forbidden")
        if self.status is not None:
            try:
                object.__setattr__(self, "status", VerificationStatus(self.status))
            except ValueError as exc:
                raise Phase6TelemetryError("telemetry status is invalid") from exc
        payload = freeze_json(self.payload, name="telemetry payload")
        if not isinstance(payload, Mapping):
            raise Phase6TelemetryError("telemetry payload must be an object")
        if len(canonical_json(payload).encode("utf-8")) > 16 * 1024:
            raise Phase6TelemetryError("telemetry payload exceeds its byte bound")
        object.__setattr__(self, "payload", payload)
        computed = digest_payload(
            {
                item.name: public_data(getattr(self, item.name))
                for item in fields(self)
                if item.name != "digest"
            }
        )
        if self.digest and self.digest != computed:
            raise Phase6TelemetryError("telemetry event digest does not match")
        object.__setattr__(self, "digest", computed)


@dataclass(frozen=True, slots=True)
class Phase6Telemetry:
    events: tuple[Phase6TelemetryEvent, ...] = ()
    max_events: int = 256

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_events, int)
            or isinstance(self.max_events, bool)
            or self.max_events < 1
            or self.max_events > 256
        ):
            raise Phase6TelemetryError("telemetry max_events must be between 1 and 256")
        events = tuple(self.events)
        if len(events) > self.max_events or any(
            not isinstance(event, Phase6TelemetryEvent) for event in events
        ):
            raise Phase6TelemetryError("telemetry event bound or type is invalid")
        if len({event.event_id for event in events}) != len(events):
            raise Phase6TelemetryError("telemetry event IDs must be unique")
        object.__setattr__(self, "events", events)

    def record(
        self,
        event_type: Phase6EventType,
        verification_input: VerificationInput,
        *,
        observed: bool = True,
        procedure_id: str | None = None,
        criterion_id: str | None = None,
        status: VerificationStatus | str | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> Phase6Telemetry:
        if not isinstance(event_type, Phase6EventType):
            raise Phase6TelemetryError("telemetry event_type is invalid")
        if len(self.events) >= self.max_events:
            raise Phase6TelemetryError("telemetry event bound exceeded")
        event = Phase6TelemetryEvent(
            event_id=f"P6-EVT-{len(self.events) + 1:04d}",
            event_type=event_type,
            run_id=verification_input.run_id,
            task_id=verification_input.task_id,
            capability_id=verification_input.capability_id,
            observed=observed,
            procedure_id=procedure_id,
            criterion_id=criterion_id,
            status=status,
            payload=payload or {},
        )
        return Phase6Telemetry((*self.events, event), self.max_events)

    @property
    def digest(self) -> str:
        return digest_payload(tuple(event.digest for event in self.events))


def build_verification_telemetry(
    plan: VerificationPlan,
    verification_input: VerificationInput,
    procedure_results: tuple[ProcedureResult, ...],
    output: VerificationOutput,
) -> Phase6Telemetry:
    """Build events from observed lifecycle facts, never from planned work alone."""

    telemetry = (
        Phase6Telemetry()
        .record(
            Phase6EventType.VERIFICATION_CAPABILITY_SELECTED,
            verification_input,
            payload={"package_digest": verification_input.package_digest},
        )
        .record(
            Phase6EventType.VERIFICATION_PLAN_CREATED,
            verification_input,
            payload={"plan_digest": plan.digest, "procedure_count": len(plan.procedures)},
        )
    )
    for result in procedure_results:
        telemetry = telemetry.record(
            Phase6EventType.VERIFICATION_PROCEDURE_STARTED,
            verification_input,
            procedure_id=result.procedure_id,
            criterion_id=result.criterion_id,
        )
        if result.status in {VerificationStatus.BLOCKED, VerificationStatus.NOT_RUN}:
            telemetry = telemetry.record(
                Phase6EventType.VERIFICATION_PROCEDURE_BLOCKED,
                verification_input,
                procedure_id=result.procedure_id,
                criterion_id=result.criterion_id,
                status=result.status,
            )
        elif result.executed:
            telemetry = telemetry.record(
                Phase6EventType.VERIFICATION_PROCEDURE_COMPLETED,
                verification_input,
                procedure_id=result.procedure_id,
                criterion_id=result.criterion_id,
                status=result.status,
            )
    for finding in output.findings:
        telemetry = _record_finding(telemetry, verification_input, finding)
    if output.freshness_status.value == "STALE":
        telemetry = telemetry.record(
            Phase6EventType.VERIFICATION_REPORT_STALE,
            verification_input,
            status=output.status,
        )
    telemetry = telemetry.record(
        Phase6EventType.VERIFICATION_REPORT_CREATED,
        verification_input,
        status=output.status,
        payload={"report_digest": output.report_digest},
    )
    return telemetry.record(
        Phase6EventType.VERIFICATION_FINALIZED,
        verification_input,
        status=output.status,
        payload={"stop_reason": output.stop_reason},
    )


def _record_finding(
    telemetry: Phase6Telemetry, verification_input: VerificationInput, finding: Finding
) -> Phase6Telemetry:
    return telemetry.record(
        Phase6EventType.VERIFICATION_FINDING_CREATED,
        verification_input,
        criterion_id=finding.criterion_id,
        payload={"finding_id": finding.finding_id, "severity": finding.severity},
    )
