from __future__ import annotations

import pytest

from harness_kernel.models import EvidenceResult, LifecycleState, QualityBand
from harness_kernel.state import (
    LIFECYCLE_TRANSITIONS,
    StatusDimensions,
    can_transition,
    transition,
    update_status,
    validate_transition,
)


def test_lifecycle_graph_accepts_documented_edges_and_rejects_shortcuts() -> None:
    assert can_transition(LifecycleState.NEW, LifecycleState.CLASSIFIED)
    assert can_transition("ASSURING", "PASSED")
    assert not can_transition(LifecycleState.NEW, LifecycleState.DELIVERED)
    assert LifecycleState.DELIVERED not in LIFECYCLE_TRANSITIONS[LifecycleState.DELIVERED]


def test_transition_is_pure_and_invalid_transition_has_structured_result() -> None:
    current = LifecycleState.ROUTED

    next_state = transition(current, LifecycleState.PLANNED)
    invalid = validate_transition(current, LifecycleState.DELIVERED)

    assert current is LifecycleState.ROUTED
    assert next_state is LifecycleState.PLANNED
    assert not invalid.is_valid
    with pytest.raises(ValueError, match="invalid lifecycle transition"):
        transition(current, LifecycleState.DELIVERED)


def test_multidimensional_status_updates_one_dimension_without_collapsing_others() -> None:
    status = StatusDimensions(
        work="IN_PROGRESS",
        lifecycle=LifecycleState.EXECUTING,
        verification=EvidenceResult.NOT_RUN,
        quality=QualityBand.PARTIAL,
        authority="PENDING",
    )

    verifying = update_status(status, lifecycle=LifecycleState.VERIFYING)

    assert status.lifecycle is LifecycleState.EXECUTING
    assert verifying.lifecycle is LifecycleState.VERIFYING
    assert verifying.work == "IN_PROGRESS"
    assert verifying.verification is EvidenceResult.NOT_RUN
    assert verifying.quality is QualityBand.PARTIAL
    assert verifying.authority == "PENDING"
