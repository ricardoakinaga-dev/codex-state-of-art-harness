from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import pytest
from phase2_support import authorized_kernel
from test_contracts import all_records

from harness_kernel.boundary import ProjectBoundary
from harness_kernel.errors import FailureCategory
from harness_kernel.execution import ExecutionKernel, ExecutionLimits, ExecutionStatus
from harness_kernel.graph import GraphNodeResult, execute_graph
from harness_kernel.models import (
    ExecutionGraph,
    ExecutionNode,
    GraphStatus,
    InvocationStatus,
    MergeConflictOwner,
    MergePoint,
    NodeBudget,
    UnresolvedPolicy,
)
from harness_kernel.providers import (
    DeterministicFailureProvider,
    DeterministicPartialProvider,
    DeterministicRetryProvider,
    DeterministicSuccessProvider,
    ProviderExecutionResult,
    ProviderRegistry,
    ProviderResultStatus,
)


def _graph(
    *,
    first_provider: str = "local.success",
    second_provider: str = "local.success",
    cycle: bool = False,
) -> ExecutionGraph:
    original = all_records()[2]
    first = replace(
        original.nodes[0],
        node_id="NODE-1",
        capability_id="local.direct",
        provider_id=first_provider,
        output_contract="LocalExecutionResult",
        acceptance_refs=("P2-EXECUTION",),
    )
    second = replace(
        original.nodes[0],
        node_id="NODE-2",
        capability_id="local.direct",
        provider_id=second_provider,
        output_contract="LocalExecutionResult",
        depends_on=("NODE-2",) if cycle else ("NODE-1",),
        acceptance_refs=("P2-EXECUTION",),
    )
    return replace(
        original,
        task_id="TASK-GRAPH",
        run_id="RUN-GRAPH",
        nodes=(first, second),
        edges=(),
        graph_status=GraphStatus.READY,
        graph_owner="orchestrator",
        acceptance_refs=("P2-EXECUTION",),
        graph_budget=NodeBudget(tokens=2_000, duration_ms=10_000),
        merge_policy="PRESERVE_AND_ESCALATE",
    )


def _providers() -> ProviderRegistry:
    return (
        ProviderRegistry()
        .register(DeterministicSuccessProvider())
        .register(DeterministicFailureProvider())
    )


def test_kernel_executes_a_graph_in_order_and_preserves_node_ownership(tmp_path: Path) -> None:
    kernel = authorized_kernel(tmp_path, providers=_providers())

    result = kernel.run(
        "Run the local graph",
        task_id="TASK-GRAPH",
        run_id="RUN-GRAPH",
        graph=_graph(),
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.graph is not None
    assert result.graph.graph_status is GraphStatus.COMPLETED
    assert tuple(item.graph_node_id for item in result.invocations) == ("NODE-1", "NODE-2")
    assert all(item.invocation_status is InvocationStatus.SUCCEEDED for item in result.invocations)
    assert len(result.provider_results) == 2
    assert len(result.artifacts) == 2
    assert result.summary.graph_ref == "GRAPH-1"


def test_kernel_requires_explicit_authority_before_graph_execution(tmp_path: Path) -> None:
    result = ExecutionKernel(ProjectBoundary(tmp_path)).run(
        "Run the local graph without authority",
        task_id="TASK-GRAPH",
        run_id="RUN-GRAPH-NO-AUTHORITY",
        graph=replace(_graph(), run_id="RUN-GRAPH-NO-AUTHORITY"),
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.provider_results == ()
    assert result.graph is not None
    assert result.graph.graph_status is GraphStatus.BLOCKED
    assert all(item.invocation_status is InvocationStatus.BLOCKED for item in result.invocations)
    assert result.failures[0].code == "AUTHORITY_REQUIRED"


def test_kernel_blocks_graph_descendants_after_a_failed_dependency(tmp_path: Path) -> None:
    kernel = authorized_kernel(tmp_path, providers=_providers())

    result = kernel.run(
        "Run the local graph",
        task_id="TASK-GRAPH",
        run_id="RUN-GRAPH-FAIL",
        graph=replace(_graph(first_provider="local.failure"), run_id="RUN-GRAPH-FAIL"),
    )

    assert result.status in {ExecutionStatus.FAILED, ExecutionStatus.BLOCKED}
    assert result.graph is not None
    assert result.graph.graph_status is GraphStatus.BLOCKED
    assert result.invocations[0].invocation_status is InvocationStatus.FAILED
    assert result.invocations[1].invocation_status is InvocationStatus.BLOCKED
    assert any(item.category is FailureCategory.DEPENDENCY_FAILED for item in result.failures)
    assert len(result.provider_results) == 1


def test_graph_merge_policy_blocks_unresolved_conflicts_before_the_merge_node() -> None:
    candidate = replace(
        _graph(),
        merge_points=(
            MergePoint(
                node_id="NODE-2",
                conflict_owner=MergeConflictOwner.INTEGRATOR,
                unresolved_policy=UnresolvedPolicy.BLOCK,
            ),
        ),
        conflict_refs=("CONFLICT-1",),
    )
    invoked: list[str] = []

    outcomes = execute_graph(
        candidate,
        lambda node: (
            invoked.append(node.node_id)
            or GraphNodeResult(node.node_id, InvocationStatus.SUCCEEDED, value=node.node_id)
        ),
    )
    by_id = {item.node_id: item for item in outcomes}

    assert invoked == ["NODE-1"]
    assert by_id["NODE-2"].status is InvocationStatus.BLOCKED
    assert by_id["NODE-2"].failure is not None
    assert by_id["NODE-2"].failure.code == "MERGE_CONFLICT_UNRESOLVED"


def test_invalid_graph_is_rejected_before_any_provider_call(tmp_path: Path) -> None:
    provider = DeterministicSuccessProvider()
    kernel = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(provider),
    )

    result = kernel.run(
        "Run the local graph",
        task_id="TASK-GRAPH",
        run_id="RUN-GRAPH-CYCLE",
        graph=replace(_graph(cycle=True), run_id="RUN-GRAPH-CYCLE"),
    )

    assert result.status is ExecutionStatus.FAILED
    assert not result.provider_results
    assert result.failures[0].category is FailureCategory.VALIDATION


def test_retry_is_bounded_and_each_attempt_is_observable(tmp_path: Path) -> None:
    provider = DeterministicRetryProvider(failures_before_success=1)
    kernel = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(provider),
    )

    result = kernel.run(
        "Retry the local fixture once",
        run_id="RUN-RETRY",
        provider_id="local.retry",
        limits=ExecutionLimits(max_retries=1),
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert len(result.provider_results) == 2
    assert result.provider_results[0].status is ProviderResultStatus.FAILED
    assert result.provider_results[1].status is ProviderResultStatus.SUCCEEDED
    assert any(event.event_type.value == "RETRY" for event in result.telemetry.events)


def test_global_duration_budget_covers_retry_attempts(tmp_path: Path) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(
            DeterministicRetryProvider(
                failures_before_success=2,
                duration_ms=30,
                delay_ms=30,
            )
        ),
    )

    result = kernel.run(
        "Retry a local fixture within one global duration budget",
        run_id="RUN-RETRY-DEADLINE",
        provider_id="local.retry",
        limits=ExecutionLimits(max_retries=2, max_duration_ms=50, timeout_ms=1000),
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    assert len(result.provider_results) <= 2
    assert not result.artifacts
    assert result.summary.delivery.status.value == "BLOCKED"


def test_graph_duration_budget_covers_retry_attempts(tmp_path: Path) -> None:
    node = replace(
        _graph().nodes[0],
        capability_id="local.direct",
        provider_id="local.retry",
        budget=NodeBudget(tokens=1, duration_ms=180),
    )
    graph = replace(
        _graph(),
        nodes=(node,),
        graph_budget=NodeBudget(tokens=1, duration_ms=180),
    )
    kernel = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(
            DeterministicRetryProvider(
                failures_before_success=1,
                duration_ms=100,
                delay_ms=100,
            )
        ),
    )

    result = kernel.run(
        "Change one local label",
        task_id="TASK-GRAPH",
        run_id="RUN-GRAPH",
        graph=graph,
        limits=ExecutionLimits(max_retries=1, max_duration_ms=1000, timeout_ms=1000),
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    assert len(result.provider_results) == 2
    assert result.provider_results[0].attempt == 1
    assert result.provider_results[1].failure is not None
    assert result.provider_results[1].failure.code == "PROVIDER_TIMEOUT"
    assert not result.artifacts
    assert result.summary.delivery.status.value == "BLOCKED"


def test_real_provider_timeout_returns_before_a_slow_fixture_finishes(tmp_path: Path) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(
            DeterministicSuccessProvider(
                provider_id="local.sleeping", delay_ms=200, duration_ms=200
            )
        ),
    )

    started = time.monotonic()
    result = kernel.run(
        "Time out a slow local fixture",
        run_id="RUN-REAL-TIMEOUT",
        provider_id="local.sleeping",
        timeout_ms=15,
        limits=ExecutionLimits(timeout_ms=1000, max_duration_ms=1000),
    )

    elapsed = time.monotonic() - started
    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.invocations[0].invocation_status is InvocationStatus.TIMED_OUT
    assert result.provider_results[-1].failure is not None
    assert result.provider_results[-1].failure.code == "PROVIDER_TIMEOUT"
    assert elapsed < 0.5


def test_direct_max_duration_is_a_real_provider_deadline(tmp_path: Path) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(
            DeterministicSuccessProvider(
                provider_id="local.sleeping", delay_ms=200, duration_ms=200
            )
        ),
    )

    result = kernel.run(
        "Apply the direct duration budget to a slow local fixture",
        run_id="RUN-DIRECT-DURATION",
        provider_id="local.sleeping",
        limits=ExecutionLimits(timeout_ms=1000, max_duration_ms=15),
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.invocations[0].invocation_status is InvocationStatus.TIMED_OUT
    assert result.provider_results[-1].failure is not None
    assert result.provider_results[-1].failure.code == "PROVIDER_TIMEOUT"


def test_cancellation_during_a_slow_provider_is_terminal(tmp_path: Path) -> None:
    calls = 0

    def cancelled() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 2

    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(
            DeterministicSuccessProvider(
                provider_id="local.sleeping", delay_ms=200, duration_ms=200
            )
        ),
    ).run(
        "Cancel a slow local fixture",
        run_id="RUN-REAL-CANCEL",
        provider_id="local.sleeping",
        cancelled=cancelled,
        timeout_ms=1000,
    )

    assert result.status is ExecutionStatus.CANCELLED
    assert result.invocations[0].invocation_status is InvocationStatus.CANCELLED
    assert result.provider_results[-1].failure is not None
    assert result.provider_results[-1].failure.code == "CANCELLED_DURING_PROVIDER"


def test_repair_is_explicit_bounded_and_keeps_trigger_provenance(tmp_path: Path) -> None:
    providers = (
        ProviderRegistry()
        .register(DeterministicFailureProvider())
        .register(DeterministicSuccessProvider(provider_id="local.repair"))
    )
    kernel = authorized_kernel(tmp_path, providers=providers)

    result = kernel.run(
        "Repair the local fixture",
        run_id="RUN-REPAIR",
        provider_id="local.failure",
        repair_provider_id="local.repair",
        max_repairs=1,
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert len(result.invocations) == 2
    assert result.repair_records
    repair = result.repair_records[0]
    assert repair.repairs_invocation_id == "INV-RUN-REPAIR"
    assert repair.repair_invocation_id == "INV-RUN-REPAIR-REPAIR-1"
    assert repair.trigger_refs
    assert result.provider_results[-1].status is ProviderResultStatus.SUCCEEDED


def test_repair_exhaustion_is_terminal_and_bounded(tmp_path: Path) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicFailureProvider()),
    )

    result = kernel.run(
        "Change one local label after explicit repair attempts",
        run_id="RUN-REPAIR-EXHAUSTED",
        provider_id="local.failure",
        repair_provider_id="local.failure",
        max_repairs=2,
    )

    assert result.status is ExecutionStatus.FAILED
    assert len(result.invocations) == 2
    assert len(result.repair_records) == 1
    assert [item.attempt for item in result.repair_records] == [1]
    assert "explicit repair stopped after repeated failure" in result.limitations


def test_partial_provider_result_remains_partial_and_is_not_delivered(tmp_path: Path) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicPartialProvider()),
    )

    result = kernel.run(
        "Preserve a partial local result",
        run_id="RUN-PARTIAL",
        provider_id="local.partial",
    )

    assert result.status is ExecutionStatus.PARTIAL
    assert result.invocations[0].invocation_status is InvocationStatus.PARTIAL
    assert result.summary.delivery.status.value == "BLOCKED"
    assert not result.summary.gate_summary.passed


def test_persistence_writes_owned_artifact_body_and_lifecycle_idempotently(
    tmp_path: Path,
) -> None:
    kernel = authorized_kernel(tmp_path)

    first = kernel.run("Persist a local result", run_id="RUN-PERSISTENCE", persist=True)
    replay = kernel.run("Persist a local result", run_id="RUN-PERSISTENCE", persist=True)
    locator = first.artifacts[0].content.locator

    assert locator is not None
    assert (tmp_path / locator).is_file()
    assert (tmp_path / ".harness/evidence/runs/RUN-PERSISTENCE-artifacts.json").is_file()
    assert (tmp_path / ".harness/state/lifecycle/RUN-PERSISTENCE.jsonl").is_file()
    assert replay.summary == first.summary


def test_corrupt_telemetry_does_not_discard_the_computed_run(tmp_path: Path) -> None:
    boundary = ProjectBoundary(tmp_path)
    boundary.atomic_write_bytes(
        ".harness/telemetry/runs/RUN-TELEMETRY-CORRUPT.jsonl", b"not-json\n"
    )

    result = authorized_kernel(boundary).run(
        "Change one local label while telemetry storage is corrupt",
        run_id="RUN-TELEMETRY-CORRUPT",
        persist=True,
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert "telemetry persistence failed; run evidence is incomplete" in result.limitations
    assert "telemetry persistence failed; run evidence is incomplete" in result.summary.limitations
    assert result.summary.delivery.status.value == "DELIVERED_WITH_LIMITATIONS"
    assert (tmp_path / ".harness/state/diagnostics/RUN-TELEMETRY-CORRUPT-telemetry.json").is_file()
    assert (
        tmp_path / ".harness/telemetry/runs/RUN-TELEMETRY-CORRUPT.jsonl"
    ).read_bytes() == b"not-json\n"


def test_evidence_and_telemetry_limits_are_observable(tmp_path: Path) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    )

    limited_evidence = kernel.run(
        "Limit evidence",
        run_id="RUN-EVIDENCE-LIMIT",
        limits=ExecutionLimits(max_evidence=0),
    )
    limited_telemetry = kernel.run(
        "Limit telemetry",
        run_id="RUN-TELEMETRY-LIMIT",
        limits=ExecutionLimits(max_telemetry=2),
    )

    assert limited_evidence.status is not ExecutionStatus.SUCCEEDED
    assert any(item.category is FailureCategory.BUDGET for item in limited_evidence.failures)
    assert len(limited_telemetry.telemetry.events) <= 2
    assert "telemetry budget truncated events" in limited_telemetry.limitations


def test_fixture_telemetry_labels_do_not_claim_real_tool_success(tmp_path: Path) -> None:
    result = authorized_kernel(tmp_path).run(
        "Change one local label with a deterministic fixture",
        run_id="RUN-FIXTURE-TELEMETRY",
    )

    tool_results = [
        event for event in result.telemetry.events if event.event_type.value == "TOOL_RESULT"
    ]

    assert tool_results
    assert all("fixture" in event.reason.casefold() for event in tool_results)
    assert all(
        "not a real provider/tool success" in event.reason.casefold() for event in tool_results
    )


def test_provider_result_rejects_forged_digest_and_allows_typed_partial_failure() -> None:
    with pytest.raises(ValueError, match="digest"):
        ProviderExecutionResult(
            provider_id="local.success",
            invocation_id="INV-1",
            status=ProviderResultStatus.SUCCEEDED,
            output={"answer": 1},
            output_digest="sha256:forged",
            output_contract="LocalExecutionResult",
        )

    partial = ProviderExecutionResult(
        provider_id="local.success",
        invocation_id="INV-1",
        status=ProviderResultStatus.PARTIAL,
        output={"answer": 1},
        output_digest=None,
        output_contract="LocalExecutionResult",
        failure=None,
    )
    assert partial.status is ProviderResultStatus.PARTIAL


def test_graph_executor_honors_structured_node_failure_and_cancellation() -> None:
    graph = _graph()
    called: list[str] = []

    def invoke(node: ExecutionNode) -> object:
        called.append(node.node_id)
        if node.node_id == "NODE-1":
            return GraphNodeResult(
                node.node_id,
                InvocationStatus.FAILED,
                failure=None,
            )
        return GraphNodeResult(node.node_id, InvocationStatus.SUCCEEDED)

    outcomes = execute_graph(graph, invoke)

    assert called == ["NODE-1"]
    assert outcomes[0].status is InvocationStatus.FAILED
    assert outcomes[1].status is InvocationStatus.BLOCKED
