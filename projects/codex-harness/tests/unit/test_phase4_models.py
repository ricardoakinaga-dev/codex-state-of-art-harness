from __future__ import annotations

import json
import math

import pytest

from harness_kernel.phase4_models import (
    AssuranceDecision,
    ExecutionMode,
    HostInvocationResult,
    HostLoadObservation,
    InvocationLifecycle,
    InvocationResultStatus,
    Phase4Budget,
    canonical_json,
    digest_payload,
    public_data,
)


def test_phase4_budget_is_bounded_and_immutable() -> None:
    budget = Phase4Budget(
        timeout_seconds=12,
        max_context_bytes=8_000,
        max_host_events=40,
        max_artifacts=2,
        max_evidence=4,
    )

    assert budget.timeout_seconds == 12
    with pytest.raises(ValueError, match="timeout"):
        Phase4Budget(timeout_seconds=0)
    with pytest.raises(ValueError, match="timeout"):
        Phase4Budget(timeout_seconds=True)  # type: ignore[arg-type]
    with pytest.raises(AttributeError):
        budget.timeout_seconds = 20  # type: ignore[misc]


def test_phase4_enums_preserve_explicit_boundary_states() -> None:
    assert ExecutionMode.CONTROLLED_REAL.value == "CONTROLLED_REAL"
    assert InvocationLifecycle.AUTHORIZED.value == "AUTHORIZED"
    assert InvocationResultStatus.TIMED_OUT.value == "TIMED_OUT"
    assert HostLoadObservation.UNOBSERVABLE.value == "HOST_LOAD_UNOBSERVABLE"
    assert AssuranceDecision.PASS_WITH_LIMITATIONS.value == "PASS_WITH_LIMITATIONS"


def test_canonical_digest_is_order_independent_and_json_safe() -> None:
    left = {"b": [2, 1], "a": "value"}
    right = {"a": "value", "b": [2, 1]}

    assert canonical_json(left) == canonical_json(right)
    assert digest_payload(left) == digest_payload(right)
    assert json.loads(canonical_json(left)) == left
    assert public_data({"mode": ExecutionMode.DRY_RUN}) == {"mode": "DRY_RUN"}


def test_canonical_serialization_rejects_nonfinite_and_cyclic_values() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        canonical_json({"value": math.nan})
    cyclic: list[object] = []
    cyclic.append(cyclic)
    with pytest.raises(ValueError, match="cyclic"):
        public_data(cyclic)


def test_host_command_preserves_repeated_argument_tokens() -> None:
    result = HostInvocationResult(
        status=InvocationResultStatus.SUCCESS,
        thread_id="thread",
        session_id="session",
        turn_id="turn",
        host_version="test-host",
        events=(),
        final_message="bounded",
        load_observation=HostLoadObservation.UNOBSERVABLE,
        invocation_observed=True,
        execution_observed=True,
        denied_approvals=0,
        cancellation_status="NOT_REQUESTED",
        error_code=None,
        started_at=1,
        completed_at=2,
        host_command=("-c", "mcp_servers={}", "-c", "features.apps=false"),
    )

    assert result.host_command == ("-c", "mcp_servers={}", "-c", "features.apps=false")
