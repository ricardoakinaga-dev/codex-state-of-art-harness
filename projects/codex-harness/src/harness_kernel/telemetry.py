"""Versioned, redacted, append-only telemetry primitives."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import Enum

from .models import (
    EvidenceKind,
    EvidenceRecord,
    EvidenceResult,
    FreshnessStatus,
    Ordering,
    PrivacyClass,
    Provenance,
    RecordEnvelope,
    RecordStatus,
    Redaction,
    SchemaVersion,
    SourceType,
    TelemetryActor,
    TelemetryEvent,
    TelemetryEventType,
    TelemetryIntegrity,
    TelemetryPayload,
)
from .serialization import to_json, to_primitive
from .validation import (
    ValidationCode,
    ValidationFinding,
    ValidationResult,
)
from .validation import (
    validate as validate_record,
)

REDACTION_MARKER = "[REDACTED]"
_SENSITIVE_KEYS = frozenset(
    {
        "secret",
        "secrets",
        "token",
        "password",
        "passwords",
        "api_key",
        "private_key",
        "credential",
        "credentials",
        "authorization",
        "cookie",
        "cookies",
        "session",
        "session_id",
        "bearer",
        "csrf",
        "csrf_token",
        "set_cookie",
        "x_api_key",
    }
)
_NON_SECRET_TOKEN_KEYS = frozenset(
    {"token_estimate", "token_count", "input_tokens", "output_tokens", "tokens"}
)
_SECRET_TEXT = re.compile(
    r"(?i)(\b(?:api[_-]?key|private[_-]?key|password|secret|credential|token|authorization|cookie|set[_-]?cookie|session(?:[_-]?id)?|csrf(?:[_-]?token)?)\b\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"
)
_BEARER_TEXT = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+")


def _normalized_key(key: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")


def _is_sensitive_key(key: object) -> bool:
    normalized = _normalized_key(key)
    if normalized in _NON_SECRET_TOKEN_KEYS:
        return False
    if normalized in _SENSITIVE_KEYS:
        return True
    return any(
        normalized.endswith(f"_{suffix}")
        for suffix in (
            "secret",
            "token",
            "password",
            "api_key",
            "private_key",
            "credential",
            "authorization",
            "cookie",
            "session",
            "session_id",
            "bearer",
            "csrf",
        )
    ) or any(
        normalized.startswith(f"{prefix}_")
        for prefix in (
            "secret",
            "token",
            "password",
            "api_key",
            "private_key",
            "credential",
            "authorization",
            "cookie",
            "session",
            "bearer",
            "csrf",
        )
    )


def redact_payload(value: object) -> object:
    """Recursively copy a payload and redact values under sensitive keys."""

    if isinstance(value, Mapping):
        return {
            key: REDACTION_MARKER if _is_sensitive_key(key) else redact_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_payload(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((redact_payload(item) for item in value), key=repr))
    if isinstance(value, str):
        redacted, _ = redact_text(value)
        return redacted
    return value


def redact_text(value: str | None) -> tuple[str | None, bool]:
    """Redact simple key/value secrets in human-readable event reasons."""

    if value is None:
        return None, False
    redacted = _SECRET_TEXT.sub(rf"\1{REDACTION_MARKER}", value)
    redacted = _BEARER_TEXT.sub(rf"\1{REDACTION_MARKER}", redacted)
    return redacted, redacted != value


def _enum_value(value: object) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def _event_type(value: TelemetryEventType | str) -> TelemetryEventType:
    try:
        return value if isinstance(value, TelemetryEventType) else TelemetryEventType(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("unknown telemetry event type") from exc


def _payload(
    value: TelemetryPayload | Mapping[str, object] | None,
) -> tuple[TelemetryPayload, bool]:
    if value is None:
        return TelemetryPayload(None, None, None, None, None, None), False
    if isinstance(value, TelemetryPayload):
        tool, changed = redact_text(value.tool)
        return replace(value, tool=tool), changed
    if not isinstance(value, Mapping):
        raise TypeError("telemetry payload must be a TelemetryPayload or mapping")
    redacted = redact_payload(value)
    assert isinstance(redacted, Mapping)
    sensitive_was_present = any(_is_sensitive_key(key) for key in value)

    def integer(name: str) -> int | None:
        item = redacted.get(name)
        if item is None:
            return None
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise ValueError(f"telemetry payload field {name} must be a non-negative integer")
        return item

    result = redacted.get("result")
    if result is not None:
        try:
            result = result if isinstance(result, EvidenceResult) else EvidenceResult(result)
        except (TypeError, ValueError) as exc:
            raise ValueError("telemetry payload result is invalid") from exc
    tool = redacted.get("tool")
    if tool is not None and not isinstance(tool, str):
        raise ValueError("telemetry payload tool must be a string")
    # Unknown non-sensitive fields are deliberately not persisted in the fixed contract payload.
    return (
        TelemetryPayload(
            integer("input_size"),
            integer("output_size"),
            integer("token_estimate"),
            integer("duration_ms"),
            tool,
            result,
        ),
        sensitive_was_present or redacted != value,
    )


def _default_record(
    event_id: str, timestamp: str, evidence_refs: tuple[str, ...]
) -> RecordEnvelope:
    return RecordEnvelope(
        status=RecordStatus.CURRENT,
        provenance=Provenance(
            source_type=SourceType.GENERATED,
            source_refs=(event_id,),
            created_at=timestamp,
        ),
        evidence_refs=evidence_refs,
    )


def _runtime_evidence_is_valid(evidence: EvidenceRecord) -> bool:
    kind = _enum_value(evidence.evidence_kind)
    result = _enum_value(evidence.result)
    freshness = _enum_value(evidence.freshness.status)
    return (
        kind in {EvidenceKind.OBSERVATION.value, EvidenceKind.TRACE.value}
        and result == EvidenceResult.PASS.value
        and evidence.procedure.executed
        and freshness == FreshnessStatus.FRESH.value
        and bool(evidence.observation.strip())
    )


def event_digest(event: TelemetryEvent) -> str:
    """Compute the canonical SHA-256 digest for an event excluding its own digest."""

    primitive = to_primitive(event)
    if not isinstance(primitive, dict) or not isinstance(primitive.get("integrity"), dict):
        raise TypeError("telemetry event cannot be canonicalized")
    primitive["integrity"]["event_digest"] = ""
    canonical = to_json(primitive, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def create_event(
    event_id: str,
    timestamp: str,
    task_id: str,
    run_id: str,
    event_type: TelemetryEventType | str,
    *,
    event_sequence: int = 1,
    record: RecordEnvelope | None = None,
    parent_event_id: str | None = None,
    actor: TelemetryActor | None = None,
    reason: str | None = None,
    payload: TelemetryPayload | Mapping[str, object] | None = None,
    artifact_refs: Iterable[str] = (),
    evidence_refs: Iterable[str] = (),
    privacy_class: PrivacyClass = PrivacyClass.INTERNAL,
    redaction: Redaction = Redaction.NONE,
    previous_event_digest: str | None = None,
    ordering: Ordering = Ordering.IN_ORDER,
    limitations: Iterable[str] = (),
    runtime_evidence: Iterable[EvidenceRecord] = (),
    schema_version: SchemaVersion | str = SchemaVersion.TELEMETRY_EVENT,
) -> TelemetryEvent:
    """Create a redacted, versioned event; no host load is inferred."""

    if (
        not isinstance(event_sequence, int)
        or isinstance(event_sequence, bool)
        or event_sequence < 1
    ):
        raise ValueError("event sequence must be a positive integer")
    event_kind = _event_type(event_type)
    refs = tuple(evidence_refs)
    artifacts = tuple(artifact_refs)
    limitation_values = tuple(limitations)
    redacted_reason, reason_changed = redact_text(reason)
    event_payload, payload_changed = _payload(payload)
    runtime_items = tuple(runtime_evidence)
    if event_kind is TelemetryEventType.CAPABILITY_LOADED:
        runtime_ids = {
            item.evidence_id for item in runtime_items if _runtime_evidence_is_valid(item)
        }
        if not refs or not runtime_ids.intersection(refs):
            raise ValueError("CAPABILITY_LOADED requires runtime observation evidence")
    event_record = record or _default_record(event_id, timestamp, refs)
    event_redaction = Redaction.APPLIED if reason_changed or payload_changed else redaction
    event = TelemetryEvent(
        schema_version=schema_version,
        event_id=event_id,
        event_sequence=event_sequence,
        timestamp=timestamp,
        task_id=task_id,
        run_id=run_id,
        record=event_record,
        parent_event_id=parent_event_id,
        event_type=event_kind,
        actor=actor or TelemetryActor(None, None),
        reason=redacted_reason,
        payload=event_payload,
        artifact_refs=artifacts,
        evidence_refs=refs,
        privacy_class=privacy_class,
        redaction=event_redaction,
        integrity=TelemetryIntegrity(previous_event_digest, "", ordering),
        limitations=limitation_values,
    )
    created = replace(event, integrity=replace(event.integrity, event_digest=event_digest(event)))
    validation = validate_record(created)
    if not validation.is_valid:
        raise ValueError("telemetry event violates its contract")
    return created


@dataclass(frozen=True, slots=True)
class TelemetryLog:
    """An immutable append-only sequence with a verified hash chain."""

    events: tuple[TelemetryEvent, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))

    @property
    def last_digest(self) -> str | None:
        return self.events[-1].integrity.event_digest if self.events else None

    def append(self, event: TelemetryEvent) -> TelemetryLog:
        if not isinstance(event, TelemetryEvent):
            raise TypeError("telemetry log accepts TelemetryEvent values only")
        expected_sequence = len(self.events) + 1
        if event.event_sequence != expected_sequence:
            raise ValueError("telemetry event sequence is not append ordered")
        if any(item.event_id == event.event_id for item in self.events):
            raise ValueError("telemetry event id is already present")
        if self.events and (event.task_id, event.run_id) != (
            self.events[0].task_id,
            self.events[0].run_id,
        ):
            raise ValueError("telemetry correlation changed within append-only log")
        if event.integrity.previous_event_digest != self.last_digest:
            raise ValueError("telemetry previous digest does not match the log")
        if event.integrity.event_digest != event_digest(event):
            raise ValueError("telemetry event digest does not match its content")
        if (
            self.events
            and event.timestamp < self.events[-1].timestamp
            and event.integrity.ordering is not Ordering.OUT_OF_ORDER
        ):
            raise ValueError("out-of-order telemetry must be explicitly marked")
        if not validate_record(event).is_valid:
            raise ValueError("telemetry event violates its contract")
        return TelemetryLog(events=(*self.events, event))

    append_event = append

    def verify_chain(self) -> bool:
        previous: str | None = None
        for expected, event in enumerate(self.events, 1):
            if event.event_sequence != expected:
                return False
            if event.integrity.previous_event_digest != previous:
                return False
            if event.integrity.event_digest != event_digest(event):
                return False
            if not validate_record(event).is_valid:
                return False
            previous = event.integrity.event_digest
        return True

    def validate(self) -> ValidationResult:
        findings: list[ValidationFinding] = []
        if not self.verify_chain():
            findings.append(
                ValidationFinding(
                    code=ValidationCode.INVARIANT_VIOLATION,
                    path="$.events",
                    message="telemetry log chain is invalid",
                )
            )
        return ValidationResult(
            valid=not findings, findings=tuple(findings), record_type="TelemetryLog"
        )


create_telemetry_event = create_event
redact = redact_payload
redact_recursive = redact_payload
compute_event_digest = event_digest
