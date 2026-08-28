from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from test_contracts import all_records

from harness_kernel.assurance import AssuranceDecision, assure_quality
from harness_kernel.authority import (
    AuthorityAction,
    AuthorityScope,
    authority_snapshot,
    check_invocation_authority,
)
from harness_kernel.boundary import BoundaryError, ProjectBoundary
from harness_kernel.errors import FailureCategory
from harness_kernel.execution import (
    ExecutionKernel,
    ExecutionLimits,
    ExecutionStatus,
    InvocationStateError,
    can_transition_invocation,
    transition_invocation,
)
from harness_kernel.graph import topological_order, validate_execution_graph
from harness_kernel.models import (
    CapabilityInvocation,
    ExecutionGraph,
    GraphStatus,
    InvocationStatus,
    NodeBudget,
)
from harness_kernel.persistence import RunStore
from harness_kernel.providers import (
    DeterministicFailureProvider,
    DeterministicSuccessProvider,
    ProviderAvailability,
    ProviderRegistry,
)
from harness_kernel.serialization import from_json, to_json
from harness_kernel.validation import validate


def invocation() -> CapabilityInvocation:
    return replace(
        all_records()[4],
        operation="execute",
        capability_origin="PROJECT",
        dependencies=("ART-1",),
        trace_context=(("trace_id", "TRACE-1"), ("span_id", "SPAN-1")),
        invocation_status=InvocationStatus.CREATED,
    )


def graph(*, cycle: bool = False) -> ExecutionGraph:
    original = all_records()[2]
    first = original.nodes[0]
    second = replace(first, node_id="NODE-2", depends_on=("NODE-1",))
    if cycle:
        first = replace(first, depends_on=("NODE-2",))
    return replace(
        original,
        nodes=(first, second),
        edges=(),
        graph_status=GraphStatus.READY,
        graph_owner="orchestrator",
        acceptance_refs=("P2-CONTRACT",),
        graph_budget=NodeBudget(tokens=1_000, duration_ms=5_000),
        merge_policy="PRESERVE_AND_ESCALATE",
    )


def test_phase2_invocation_contract_round_trips_new_execution_fields() -> None:
    value = invocation()

    assert validate(value).is_valid
    restored = from_json(to_json(value), CapabilityInvocation)

    assert restored == value
    assert restored.operation == "execute"
    assert restored.capability_origin == "PROJECT"
    assert restored.dependencies == ("ART-1",)
    assert restored.trace_context[0] == ("trace_id", "TRACE-1")


def test_invocation_lifecycle_is_explicit_and_immutable() -> None:
    created = invocation()
    validated = transition_invocation(created, InvocationStatus.VALIDATED)
    authorized = transition_invocation(validated, InvocationStatus.AUTHORIZED)
    ready = transition_invocation(authorized, InvocationStatus.READY)

    assert created.invocation_status is InvocationStatus.CREATED
    assert ready.invocation_status is InvocationStatus.READY
    assert can_transition_invocation(InvocationStatus.RUNNING, InvocationStatus.TIMED_OUT)
    with pytest.raises(InvocationStateError):
        transition_invocation(created, InvocationStatus.SUCCEEDED)


def test_project_boundary_rejects_escape_and_supports_atomic_local_records(tmp_path: Path) -> None:
    boundary = ProjectBoundary(tmp_path)

    boundary.atomic_write_json(".harness/state/run.json", {"status": "RUNNING"})
    assert boundary.read_json(".harness/state/run.json") == {"status": "RUNNING"}
    with pytest.raises(BoundaryError):
        boundary.resolve("../outside.json")
    with pytest.raises(BoundaryError):
        boundary.resolve(str(tmp_path / "outside.json"))

    outside = tmp_path.parent / "outside-phase2.txt"
    outside.write_text("outside", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)
    with pytest.raises(BoundaryError):
        boundary.read_bytes("link.txt")


def test_provider_registry_distinguishes_registered_available_and_selected() -> None:
    success = DeterministicSuccessProvider()
    registry = ProviderRegistry().register(success)

    assert registry.inspect(success.provider_id).availability is ProviderAvailability.AVAILABLE
    assert registry.resolve(success.provider_id) is not None
    unavailable = registry.with_availability(success.provider_id, ProviderAvailability.UNAVAILABLE)
    assert unavailable.resolve(success.provider_id) is None
    assert unavailable.inspect(success.provider_id).availability is ProviderAvailability.UNAVAILABLE


def test_authority_checks_expiry_operation_and_scope_before_execution() -> None:
    authority = AuthorityScope(
        owner="owner",
        actor="runner",
        scopes=("task:TASK-1", "capability:local.success"),
        decisions=(AuthorityAction.TRANSITION,),
        subject_owner="owner",
        operations=("execute",),
        issued_at="2026-08-28T12:00:00Z",
        expires_at="2026-08-28T13:00:00Z",
    )

    allowed = check_invocation_authority(
        authority,
        task_id="TASK-1",
        invocation_id="INV-1",
        capability_id="local.success",
        operation="execute",
        required_scope=("task:TASK-1", "capability:local.success"),
        at="2026-08-28T12:30:00Z",
    )
    expired = check_invocation_authority(
        authority,
        task_id="TASK-1",
        invocation_id="INV-1",
        capability_id="local.success",
        operation="execute",
        required_scope=("task:TASK-1",),
        at="2026-08-28T13:30:00Z",
    )

    assert allowed.allowed
    assert not expired.allowed
    assert expired.code == "AUTHORITY_EXPIRED"
    snapshot = authority_snapshot(authority, subject_id="INV-1", operation="execute")
    assert snapshot.digest.startswith("sha256:")
    assert snapshot.operation == "execute"


def test_kernel_propagates_and_enforces_delegation_reference(tmp_path: Path) -> None:
    authority = AuthorityScope(
        owner="owner",
        actor="runner",
        scopes=("task:TASK-DELEGATED", "capability:local.success"),
        decisions=(AuthorityAction.TRANSITION,),
        subject_owner="owner",
        operations=("execute",),
        delegation_chain=("DELEGATION-1",),
        issued_at="2026-08-28T12:00:00Z",
        expires_at="2026-08-28T14:00:00Z",
    )
    kernel = ExecutionKernel(
        ProjectBoundary(tmp_path),
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
        timestamp="2026-08-28T13:30:00Z",
    )

    denied = kernel.run(
        "Use delegated local authority",
        task_id="TASK-DELEGATED",
        run_id="RUN-DELEGATION-DENIED",
        provider_id="local.success",
        authority=authority,
        delegation_ref="DELEGATION-MISSING",
    )
    allowed = kernel.run(
        "Use delegated local authority",
        task_id="TASK-DELEGATED",
        run_id="RUN-DELEGATION-ALLOWED",
        provider_id="local.success",
        authority=authority,
        delegation_ref="DELEGATION-1",
    )

    assert denied.failures[0].code == "DELEGATION_MISSING"
    assert denied.provider_results == ()
    assert allowed.status is ExecutionStatus.SUCCEEDED
    assert allowed.authority_snapshot is not None
    assert allowed.authority_snapshot.required_scope == (
        "task:TASK-DELEGATED",
        "capability:local.success",
    )


def test_graph_validation_rejects_cycles_and_accepts_deterministic_topology() -> None:
    valid = graph()
    result = validate_execution_graph(valid, max_nodes=4)

    assert result.is_valid
    assert topological_order(valid) == ("NODE-1", "NODE-2")

    invalid = graph(cycle=True)
    invalid = replace(invalid, graph_budget=NodeBudget(tokens=1, duration_ms=1))
    result = validate_execution_graph(invalid, max_nodes=1)

    assert not result.is_valid
    codes = {finding.code.value for finding in result.findings}
    assert "INVARIANT_VIOLATION" in codes


def test_direct_kernel_produces_artifact_evidence_verification_assurance_and_summary(
    tmp_path: Path,
) -> None:
    kernel = ExecutionKernel(
        ProjectBoundary(tmp_path),
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    )

    result = kernel.run(
        "Change one local label",
        task_id="TASK-P2-DIRECT",
        run_id="RUN-P2-DIRECT",
        provider_id="local.success",
    )

    assert result.status == "SUCCEEDED"
    assert result.summary.lifecycle_state.value == "DELIVERED"
    assert result.artifacts
    assert result.evidence
    assert result.verification.recommendation.value == "PASS"
    assert result.assurance.decision is AssuranceDecision.QUALITY_ACCEPTED
    assert result.telemetry.verify_chain()
    assert result.invocations[0].invocation_status is InvocationStatus.SUCCEEDED


def test_dry_run_and_stop_before_run_never_call_a_provider(tmp_path: Path) -> None:
    provider = DeterministicSuccessProvider()
    kernel = ExecutionKernel(
        ProjectBoundary(tmp_path), providers=ProviderRegistry().register(provider)
    )

    dry = kernel.run("Change one local label", run_id="RUN-P2-DRY", dry_run=True)
    stopped = kernel.run(
        "Change one local label",
        run_id="RUN-P2-STOP",
        stop_before_run=True,
    )

    assert dry.status == "DRY_RUN"
    assert not dry.provider_results
    assert stopped.status == "STOPPED"
    assert not stopped.provider_results


def test_failure_provider_is_typed_and_does_not_become_success(tmp_path: Path) -> None:
    kernel = ExecutionKernel(
        ProjectBoundary(tmp_path),
        providers=ProviderRegistry().register(DeterministicFailureProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-P2-FAIL",
        provider_id="local.failure",
    )

    assert result.status == "FAILED"
    assert result.failures[0].category is FailureCategory.PROVIDER
    assert result.summary.delivery.status.value == "BLOCKED"
    assert result.verification.recommendation.value != "PASS"


def test_timeout_cancel_and_budget_are_first_class_failures(tmp_path: Path) -> None:
    kernel = ExecutionKernel(
        ProjectBoundary(tmp_path),
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    )

    timeout = kernel.run("Change one local label", run_id="RUN-P2-TIMEOUT", timeout_ms=0)
    cancelled = kernel.run("Change one local label", run_id="RUN-P2-CANCEL", cancelled=True)
    budget = kernel.run(
        "Change one local label",
        run_id="RUN-P2-BUDGET",
        limits=ExecutionLimits(max_invocations=0),
    )

    assert timeout.failures[0].category is FailureCategory.TIMEOUT
    assert cancelled.failures[0].category is FailureCategory.CANCELLED
    assert budget.failures[0].category is FailureCategory.BUDGET


def test_run_store_is_project_local_and_recovery_distinguishes_finished_unfinished_corrupt(
    tmp_path: Path,
) -> None:
    store = RunStore(ProjectBoundary(tmp_path))
    store.write_record("RUN-1", {"run_id": "RUN-1", "status": "DELIVERED"})

    assert store.load_record("RUN-1")["status"] == "DELIVERED"
    assert store.recover("RUN-1").status == "FINISHED"
    store.write_record("RUN-2", {"run_id": "RUN-2", "status": "RUNNING"})
    assert store.recover("RUN-2").status == "UNFINISHED"
    store.boundary.atomic_write_bytes(".harness/state/runs/RUN-3.json", b"not-json")
    assert store.recover("RUN-3").status == "CORRUPT"


@pytest.mark.parametrize(
    ("field", "state"),
    (
        ("status", "SUCCEEDED"),
        ("status", "FAILED"),
        ("status", "DRY_RUN"),
        ("status", "STOPPED"),
        ("status", "BLOCKED"),
        ("status", "CANCELLED"),
        ("status", "TIMED_OUT"),
        ("status", "PARTIAL"),
        ("lifecycle_state", "PARTIAL"),
    ),
)
def test_run_store_recovers_completed_phase2_execution_states(
    tmp_path: Path, field: str, state: str
) -> None:
    store = RunStore(ProjectBoundary(tmp_path))
    run_id = f"RUN-P2-{state}"
    store.write_record(run_id, {"run_id": run_id, field: state})

    assert store.recover(run_id).status == "FINISHED"


def test_assurance_requires_verification_and_critique_evidence() -> None:
    records = all_records()
    accepted = assure_quality(records[7], records[8], quality_bar_ref="P2-QB-1")
    blocked = assure_quality(
        replace(records[7], recommendation="FAIL"),
        records[8],
        quality_bar_ref="P2-QB-1",
    )

    assert accepted.decision is AssuranceDecision.QUALITY_ACCEPTED
    assert blocked.decision is AssuranceDecision.FAILED
