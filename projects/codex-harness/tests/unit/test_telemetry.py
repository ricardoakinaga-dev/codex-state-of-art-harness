from __future__ import annotations

from dataclasses import replace

import pytest
from test_contracts import all_records

from harness_kernel.models import (
    EvidenceFreshness,
    EvidenceKind,
    EvidenceResult,
    FreshnessStatus,
    TelemetryEventType,
)
from harness_kernel.telemetry import (
    TelemetryLog,
    create_event,
    redact_payload,
)


def test_event_creation_is_versioned_deterministic_and_chain_ready() -> None:
    first = create_event(
        event_id="EVT-1",
        event_sequence=1,
        timestamp="2026-08-28T12:00:00Z",
        task_id="TASK-1",
        run_id="RUN-1",
        event_type=TelemetryEventType.TOOL_RESULT,
        reason="synthetic verification",
    )
    repeated = create_event(
        event_id="EVT-1",
        event_sequence=1,
        timestamp="2026-08-28T12:00:00Z",
        task_id="TASK-1",
        run_id="RUN-1",
        event_type=TelemetryEventType.TOOL_RESULT,
        reason="synthetic verification",
    )

    assert first.schema_version == "TE-1"
    assert first.integrity.previous_event_digest is None
    assert first.integrity.event_digest == repeated.integrity.event_digest


def test_append_only_log_returns_new_log_and_rejects_tampering() -> None:
    first = create_event(
        event_id="EVT-1",
        event_sequence=1,
        timestamp="2026-08-28T12:00:00Z",
        task_id="TASK-1",
        run_id="RUN-1",
        event_type=TelemetryEventType.TASK_RECEIVED,
    )
    second = create_event(
        event_id="EVT-2",
        event_sequence=2,
        timestamp="2026-08-28T12:00:01Z",
        task_id="TASK-1",
        run_id="RUN-1",
        event_type=TelemetryEventType.TOOL_RESULT,
        previous_event_digest=first.integrity.event_digest,
    )
    empty = TelemetryLog()
    one = empty.append(first)
    two = one.append(second)

    assert empty.events == ()
    assert one.events == (first,)
    assert two.events == (first, second)
    assert two.verify_chain()
    with pytest.raises(ValueError, match="digest"):
        one.append(replace(second, reason="tampered"))


def test_redaction_recurses_and_never_keeps_sensitive_values() -> None:
    payload = {
        "safe": {"count": 2},
        "nested": {"password": "fixture-password", "items": [{"api_key": "fixture-key"}]},
    }

    redacted = redact_payload(payload)

    assert redacted == {
        "safe": {"count": 2},
        "nested": {"password": "[REDACTED]", "items": [{"api_key": "[REDACTED]"}]},
    }
    assert "fixture-password" not in repr(redacted)
    assert "fixture-key" not in repr(redacted)


def test_redaction_covers_auth_cookies_sessions_and_inline_bearer_values() -> None:
    payload = {
        "authorization": "Bearer auth-secret",
        "session_id": "session-secret",
        "cookie": "sid=cookie-secret",
        "note": "Authorization: Bearer inline-secret",
        "safe": "no credentials here",
    }

    redacted = redact_payload(payload)

    assert redacted["authorization"] == "[REDACTED]"  # type: ignore[index]
    assert redacted["session_id"] == "[REDACTED]"  # type: ignore[index]
    assert redacted["cookie"] == "[REDACTED]"  # type: ignore[index]
    assert "auth-secret" not in repr(redacted)
    assert "session-secret" not in repr(redacted)
    assert "cookie-secret" not in repr(redacted)
    assert "inline-secret" not in repr(redacted)


def test_capability_loaded_requires_observed_fresh_runtime_evidence() -> None:
    evidence = replace(
        all_records()[6],
        evidence_kind=EvidenceKind.OBSERVATION,
        result=EvidenceResult.PASS,
        procedure=replace(all_records()[6].procedure, executed=True),
        freshness=EvidenceFreshness(status=FreshnessStatus.FRESH, invalidated_by=()),
    )
    common = dict(
        event_id="EVT-LOAD",
        event_sequence=1,
        timestamp="2026-08-28T12:00:00Z",
        task_id="TASK-1",
        run_id="RUN-1",
        event_type=TelemetryEventType.CAPABILITY_LOADED,
        evidence_refs=(evidence.evidence_id,),
    )

    with pytest.raises(ValueError, match="runtime observation"):
        create_event(**common)

    loaded = create_event(**common, runtime_evidence=(evidence,))

    assert loaded.event_type is TelemetryEventType.CAPABILITY_LOADED
    assert loaded.evidence_refs == (evidence.evidence_id,)
