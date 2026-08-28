"""Immutable lifecycle transitions and multidimensional status values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from .models import EvidenceResult, LifecycleState, QualityBand
from .validation import ValidationCode, ValidationFinding, ValidationResult


class WorkStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    IMPLEMENTED = "IMPLEMENTED"
    REVIEW = "REVIEW"
    REWORK = "REWORK"
    VERIFIED = "VERIFIED"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AuthorityStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


def _lifecycle(value: LifecycleState | str) -> LifecycleState | None:
    try:
        return value if isinstance(value, LifecycleState) else LifecycleState(value)
    except (TypeError, ValueError):
        return None


def _work(value: WorkStatus | str) -> WorkStatus | str:
    try:
        return value if isinstance(value, WorkStatus) else WorkStatus(value)
    except (TypeError, ValueError):
        return value


def _verification(value: EvidenceResult | str) -> EvidenceResult | str:
    try:
        return value if isinstance(value, EvidenceResult) else EvidenceResult(value)
    except (TypeError, ValueError):
        return value


def _quality(value: QualityBand | str) -> QualityBand | str:
    try:
        return value if isinstance(value, QualityBand) else QualityBand(value)
    except (TypeError, ValueError):
        return value


def _authority(value: AuthorityStatus | str) -> AuthorityStatus | str:
    try:
        return value if isinstance(value, AuthorityStatus) else AuthorityStatus(value)
    except (TypeError, ValueError):
        return value


LIFECYCLE_TRANSITIONS: Mapping[LifecycleState, tuple[LifecycleState, ...]] = MappingProxyType(
    {
        LifecycleState.NEW: (LifecycleState.CLASSIFIED, LifecycleState.BLOCKED),
        LifecycleState.CLASSIFIED: (LifecycleState.ROUTED, LifecycleState.BLOCKED),
        LifecycleState.ROUTED: (LifecycleState.PLANNED, LifecycleState.EXECUTING),
        LifecycleState.PLANNED: (LifecycleState.EXECUTING, LifecycleState.BLOCKED),
        LifecycleState.EXECUTING: (
            LifecycleState.VERIFYING,
            LifecycleState.BLOCKED,
            LifecycleState.FAILED,
            LifecycleState.CANCELLED,
        ),
        LifecycleState.VERIFYING: (
            LifecycleState.REVIEWING,
            LifecycleState.REPAIRING,
            LifecycleState.FAILED,
        ),
        LifecycleState.REVIEWING: (
            LifecycleState.REPAIRING,
            LifecycleState.ASSURING,
            LifecycleState.BLOCKED,
        ),
        LifecycleState.REPAIRING: (LifecycleState.VERIFYING, LifecycleState.FAILED),
        LifecycleState.ASSURING: (
            LifecycleState.PASSED,
            LifecycleState.PARTIAL,
            LifecycleState.BLOCKED,
        ),
        LifecycleState.BLOCKED: (
            LifecycleState.ROUTED,
            LifecycleState.PLANNED,
            LifecycleState.FAILED,
        ),
        LifecycleState.FAILED: (LifecycleState.ROUTED,),
        LifecycleState.PARTIAL: (LifecycleState.REPAIRING, LifecycleState.DELIVERED),
        LifecycleState.PASSED: (LifecycleState.DELIVERED,),
        LifecycleState.DELIVERED: (),
        LifecycleState.CANCELLED: (),
    }
)


WORK_TRANSITIONS: Mapping[WorkStatus, tuple[WorkStatus, ...]] = MappingProxyType(
    {
        WorkStatus.PENDING: (WorkStatus.READY, WorkStatus.BLOCKED, WorkStatus.CANCELLED),
        WorkStatus.READY: (WorkStatus.RUNNING, WorkStatus.BLOCKED, WorkStatus.CANCELLED),
        WorkStatus.RUNNING: (
            WorkStatus.IMPLEMENTED,
            WorkStatus.REVIEW,
            WorkStatus.REWORK,
            WorkStatus.BLOCKED,
            WorkStatus.FAILED,
            WorkStatus.CANCELLED,
        ),
        WorkStatus.IMPLEMENTED: (WorkStatus.REVIEW, WorkStatus.VERIFIED, WorkStatus.REWORK),
        WorkStatus.REVIEW: (WorkStatus.VERIFIED, WorkStatus.REWORK, WorkStatus.BLOCKED),
        WorkStatus.REWORK: (WorkStatus.RUNNING, WorkStatus.IMPLEMENTED, WorkStatus.FAILED),
        WorkStatus.VERIFIED: (WorkStatus.DONE, WorkStatus.REWORK),
        WorkStatus.DONE: (),
        WorkStatus.BLOCKED: (WorkStatus.READY, WorkStatus.RUNNING, WorkStatus.FAILED),
        WorkStatus.FAILED: (WorkStatus.READY, WorkStatus.RUNNING),
        WorkStatus.CANCELLED: (),
    }
)


@dataclass(frozen=True, slots=True)
class StatusDimensions:
    """Independent work, lifecycle, verification, quality, and authority axes."""

    work: WorkStatus | str
    lifecycle: LifecycleState | str
    verification: EvidenceResult | str
    quality: QualityBand | str
    authority: AuthorityStatus | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "work", _work(self.work))
        object.__setattr__(self, "lifecycle", _lifecycle(self.lifecycle) or self.lifecycle)
        object.__setattr__(self, "verification", _verification(self.verification))
        object.__setattr__(self, "quality", _quality(self.quality))
        object.__setattr__(self, "authority", _authority(self.authority))


def can_transition(current: LifecycleState | str, target: LifecycleState | str) -> bool:
    current_state = _lifecycle(current)
    target_state = _lifecycle(target)
    return current_state is not None and target_state in LIFECYCLE_TRANSITIONS.get(
        current_state, ()
    )


def validate_transition(
    current: LifecycleState | str, target: LifecycleState | str
) -> ValidationResult:
    current_state = _lifecycle(current)
    target_state = _lifecycle(target)
    findings: list[ValidationFinding] = []
    if current_state is None:
        findings.append(
            ValidationFinding(ValidationCode.INVALID_ENUM, "$.current", "unknown lifecycle state")
        )
    if target_state is None:
        findings.append(
            ValidationFinding(ValidationCode.INVALID_ENUM, "$.target", "unknown lifecycle state")
        )
    if (
        not findings
        and current_state is not None
        and target_state is not None
        and target_state not in LIFECYCLE_TRANSITIONS[current_state]
    ):
        findings.append(
            ValidationFinding(
                ValidationCode.INVARIANT_VIOLATION,
                "$.transition",
                "invalid lifecycle transition",
            )
        )
    return ValidationResult(
        valid=not findings, findings=tuple(findings), record_type="LifecycleTransition"
    )


def transition(current: LifecycleState | str, target: LifecycleState | str) -> LifecycleState:
    result = validate_transition(current, target)
    if not result.is_valid:
        raise ValueError("invalid lifecycle transition")
    normalized = _lifecycle(target)
    assert normalized is not None
    return normalized


def can_work_transition(current: WorkStatus | str, target: WorkStatus | str) -> bool:
    try:
        current_status = current if isinstance(current, WorkStatus) else WorkStatus(current)
        target_status = target if isinstance(target, WorkStatus) else WorkStatus(target)
    except (TypeError, ValueError):
        return False
    return target_status in WORK_TRANSITIONS.get(current_status, ())


def update_status(
    status: StatusDimensions,
    *,
    work: WorkStatus | str | None = None,
    lifecycle: LifecycleState | str | None = None,
    verification: EvidenceResult | str | None = None,
    quality: QualityBand | str | None = None,
    authority: AuthorityStatus | str | None = None,
) -> StatusDimensions:
    """Return a copy with selected dimensions changed; never mutate ``status``."""

    if not isinstance(status, StatusDimensions):
        raise TypeError("status must be StatusDimensions")
    return StatusDimensions(
        work=status.work if work is None else work,
        lifecycle=status.lifecycle if lifecycle is None else lifecycle,
        verification=status.verification if verification is None else verification,
        quality=status.quality if quality is None else quality,
        authority=status.authority if authority is None else authority,
    )


def validate_status(status: object) -> ValidationResult:
    findings: list[ValidationFinding] = []
    if not isinstance(status, StatusDimensions):
        findings.append(
            ValidationFinding(ValidationCode.INVALID_TYPE, "$", "status dimensions are required")
        )
        return ValidationResult(
            valid=False, findings=tuple(findings), record_type="StatusDimensions"
        )
    if not isinstance(status.work, WorkStatus):
        findings.append(
            ValidationFinding(ValidationCode.INVALID_ENUM, "$.work", "unknown work status")
        )
    if _lifecycle(status.lifecycle) is None:
        findings.append(
            ValidationFinding(ValidationCode.INVALID_ENUM, "$.lifecycle", "unknown lifecycle state")
        )
    if not isinstance(status.verification, EvidenceResult):
        findings.append(
            ValidationFinding(
                ValidationCode.INVALID_ENUM, "$.verification", "unknown verification status"
            )
        )
    if not isinstance(status.quality, QualityBand):
        findings.append(
            ValidationFinding(ValidationCode.INVALID_ENUM, "$.quality", "unknown quality status")
        )
    if not isinstance(status.authority, AuthorityStatus):
        findings.append(
            ValidationFinding(
                ValidationCode.INVALID_ENUM, "$.authority", "unknown authority status"
            )
        )
    return ValidationResult(
        valid=not findings, findings=tuple(findings), record_type="StatusDimensions"
    )


is_valid_transition = can_transition
transition_lifecycle = transition
MultiDimensionalStatus = StatusDimensions
StateStatus = StatusDimensions
