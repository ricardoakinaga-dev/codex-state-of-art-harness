from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import cast

import pytest
from test_contracts import all_records

import harness_kernel.execution as execution_module
from harness_kernel.authority import AuthorityAction, AuthorityScope
from harness_kernel.boundary import ProjectBoundary
from harness_kernel.errors import FailureCategory, FailureDetail
from harness_kernel.execution import (
    ExecutionKernel,
    ExecutionLimits,
    ExecutionStatus,
    RepairRecord,
    _call_provider_with_deadline,
    _route_with_provider,
)
from harness_kernel.models import (
    CapabilityInvocation,
    CapabilityManifest,
    CapabilityPrimaryType,
    CapabilityStatus,
    ExecutionGraph,
    GraphStatus,
    InvocationStatus,
    NodeBudget,
    RouteDecision,
    RouteKind,
    RouteStatus,
    SelectedCapability,
)
from harness_kernel.persistence import RunStore
from harness_kernel.providers import (
    CapabilityProvider,
    DeterministicFailureProvider,
    DeterministicPartialProvider,
    DeterministicSuccessProvider,
    ProviderExecutionResult,
    ProviderRegistry,
    ProviderResultStatus,
)
from harness_kernel.registry import CapabilityRegistry
from harness_kernel.stops import (
    FailureObservation,
    ProgressSnapshot,
    StopCondition,
    evaluate_stop,
)


def broad_test_authority() -> AuthorityScope:
    return AuthorityScope(
        owner="legacy-test-policy",
        actor="legacy-test-runner",
        scopes=("task:*", "capability:*"),
        decisions=(AuthorityAction.TRANSITION, AuthorityAction.REPLAN),
        subject_owner="legacy-test-policy",
        operations=("execute",),
        issued_at="1970-01-01T00:00:00Z",
        expires_at="2099-12-31T23:59:59Z",
    )


_DEFAULT_AUTHORITY = broad_test_authority()


def authorized_kernel(
    boundary: Path | ProjectBoundary,
    *,
    providers: ProviderRegistry | None = None,
    registry: CapabilityRegistry | None = None,
    store: RunStore | None = None,
) -> ExecutionKernel:
    selected_boundary = (
        boundary if isinstance(boundary, ProjectBoundary) else ProjectBoundary(boundary)
    )
    return ExecutionKernel(
        selected_boundary,
        providers=providers,
        registry=registry,
        store=store,
        authority=broad_test_authority(),
    )


def _providers(*values: CapabilityProvider) -> ProviderRegistry:
    registry = ProviderRegistry()
    for value in values:
        registry = registry.register(value)
    return registry


def _invocation(
    kernel: ExecutionKernel,
    *,
    provider_id: str = "local.success",
    capability_id: str | None = None,
    run_id: str = "RUN-LEGACY",
) -> CapabilityInvocation:
    profile = kernel._profile(
        "Change one local label",
        task_id="TASK-LEGACY",
        run_id=run_id,
        requested_outcome="",
    )
    limits = ExecutionLimits()
    selected_capability = capability_id or provider_id
    return execution_module._build_invocation(
        profile,
        invocation_id=f"INV-{run_id}",
        capability_id=selected_capability,
        provider_id=provider_id,
        graph_node_id=None,
        acceptance_refs=("P2-EXECUTION",),
        output_contract="LocalExecutionResult",
        limits=limits,
        timestamp=kernel.timestamp,
    )


def _execute_one(
    kernel: ExecutionKernel,
    invocation: CapabilityInvocation,
    *,
    authority: AuthorityScope | None = _DEFAULT_AUTHORITY,
    limits: ExecutionLimits | None = None,
    cancelled: bool = False,
    timeout_ms: int | None = None,
    deadline: float | None = None,
) -> execution_module._InvocationOutcome:
    return kernel._execute_one(
        invocation,
        authority=authority,
        limits=limits or ExecutionLimits(),
        invocation_count=0,
        required_conditions=(),
        cancelled=cancelled,
        timeout_ms=timeout_ms,
        deadline=deadline,
    )


def _graph(
    *provider_ids: str,
    run_id: str = "RUN-GRAPH-LEGACY",
    independent: bool = True,
) -> ExecutionGraph:
    original = cast(ExecutionGraph, all_records()[2])
    template = original.nodes[0]
    nodes = tuple(
        replace(
            template,
            node_id=f"NODE-{index}",
            capability_id="local.direct",
            provider_id=provider_id,
            output_contract="LocalExecutionResult",
            depends_on=() if independent or index == 0 else (f"NODE-{index - 1}",),
            acceptance_refs=("P2-EXECUTION",),
            budget=NodeBudget(tokens=100, duration_ms=1_000),
        )
        for index, provider_id in enumerate(provider_ids, start=1)
    )
    return replace(
        original,
        task_id="TASK-GRAPH-LEGACY",
        run_id=run_id,
        nodes=nodes,
        edges=(),
        merge_points=(),
        conflict_refs=(),
        graph_status=GraphStatus.READY,
        graph_owner="orchestrator",
        graph_budget=NodeBudget(tokens=10_000, duration_ms=10_000),
        acceptance_refs=("P2-EXECUTION",),
    )


def _selected_graph_route(kernel: ExecutionKernel, graph: ExecutionGraph) -> RouteDecision:
    profile = kernel._profile(
        "Change one local label",
        task_id=graph.task_id,
        run_id=graph.run_id,
        requested_outcome="",
    )
    original = cast(RouteDecision, all_records()[1])
    return replace(
        original,
        task_id=profile.task_id,
        run_id=profile.run_id,
        route_status=RouteStatus.SELECTED,
        route_kind=RouteKind.PROVIDER,
        selected=(
            SelectedCapability(
                capability_id="local.direct",
                role=CapabilityPrimaryType.PROVIDER,
                reason="legacy assurance fixture",
                required=True,
            ),
        ),
        omitted=(),
        unresolved=(),
        fallback=None,
    )


def _manifest(
    *,
    capability_id: str = "local.success",
    primary_type: CapabilityPrimaryType = CapabilityPrimaryType.PROVIDER,
    status: CapabilityStatus = CapabilityStatus.VERIFIED,
) -> CapabilityManifest:
    original = cast(CapabilityManifest, all_records()[3])
    return replace(
        original,
        capability_id=capability_id,
        primary_type=primary_type,
        status=status,
    )


def test_legacy_authority_guards_block_without_provider_resolution(tmp_path: Path) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )
    invocation = _invocation(kernel)

    outcome = _execute_one(kernel, invocation, authority=None)

    assert outcome.invocation.invocation_status is InvocationStatus.BLOCKED
    assert outcome.failure is not None
    assert outcome.failure.code == "AUTHORITY_REQUIRED"
    assert outcome.provider_results == ()


def test_legacy_snapshot_is_absent_when_no_authority_exists(tmp_path: Path) -> None:
    kernel = authorized_kernel(tmp_path)

    assert kernel._snapshot_for(None, ()) is None


def test_legacy_kernel_rejects_untrusted_constructor_dependencies(tmp_path: Path) -> None:
    boundary = ProjectBoundary(tmp_path)

    with pytest.raises(TypeError, match="authority must be an AuthorityScope"):
        ExecutionKernel(boundary, authority=cast(AuthorityScope, object()))
    with pytest.raises(TypeError, match="providers must be the built-in ProviderRegistry"):
        ExecutionKernel(boundary, providers=cast(ProviderRegistry, object()))
    with pytest.raises(TypeError, match="registry must be the built-in CapabilityRegistry"):
        ExecutionKernel(boundary, registry=cast(CapabilityRegistry, object()))
    with pytest.raises(TypeError, match="store must be the built-in RunStore"):
        ExecutionKernel(boundary, store=cast(RunStore, object()))


def test_legacy_run_rejects_invalid_authority_and_timeout_at_the_boundary(
    tmp_path: Path,
) -> None:
    kernel = authorized_kernel(tmp_path)

    with pytest.raises(TypeError, match="run authority"):
        kernel.run("Change one local label", authority=cast(AuthorityScope, object()))
    with pytest.raises(ValueError, match="timeout"):
        kernel.run("Change one local label", timeout_ms=-1)


def test_legacy_repair_record_rejects_non_positive_attempt() -> None:
    with pytest.raises(ValueError, match="repair attempt must be positive"):
        RepairRecord(
            repair_id="REPAIR-1",
            repairs_invocation_id="INV-1",
            repair_invocation_id="INV-2",
            trigger_refs=("FAILURE-1",),
            status=ExecutionStatus.FAILED,
            attempt=0,
        )


def test_legacy_blocked_route_never_enters_provider_execution(tmp_path: Path) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-LEGACY-ROUTE-BLOCKED",
        provider_id="missing.provider",
    )

    assert result.route.route_status is RouteStatus.BLOCKED
    assert "PROVIDER_UNAVAILABLE" in result.route.unresolved
    assert result.provider_results == ()
    assert result.failures[0].code == "PROVIDER_UNAVAILABLE"


def test_legacy_missing_provider_is_blocked_after_authorization(tmp_path: Path) -> None:
    kernel = authorized_kernel(tmp_path, providers=ProviderRegistry())
    invocation = _invocation(
        kernel,
        provider_id="missing.provider",
        capability_id="missing.provider",
        run_id="RUN-LEGACY-MISSING-PROVIDER",
    )

    outcome = _execute_one(kernel, invocation)

    assert outcome.invocation.invocation_status is InvocationStatus.BLOCKED
    assert outcome.failure is not None
    assert outcome.failure.code == "PROVIDER_UNAVAILABLE"
    assert outcome.provider_results == ()


def _assert_manifest_admission_failure(
    tmp_path: Path,
    primary_type: CapabilityPrimaryType,
    status: CapabilityStatus,
    expected_code: str,
) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
        registry=CapabilityRegistry.from_manifests(
            (_manifest(primary_type=primary_type, status=status),)
        ),
    )
    invocation = _invocation(kernel, run_id=f"RUN-LEGACY-MANIFEST-{expected_code}")

    outcome = _execute_one(kernel, invocation)

    assert outcome.invocation.invocation_status is InvocationStatus.BLOCKED
    assert outcome.failure is not None
    assert outcome.failure.code == expected_code
    assert outcome.provider_results == ()


def test_legacy_manifest_type_mismatch_blocks_before_provider_call(tmp_path: Path) -> None:
    _assert_manifest_admission_failure(
        tmp_path,
        CapabilityPrimaryType.VALIDATOR,
        CapabilityStatus.VERIFIED,
        "CAPABILITY_MANIFEST_TYPE_MISMATCH",
    )


def test_legacy_manifest_not_admitted_blocks_before_provider_call(tmp_path: Path) -> None:
    _assert_manifest_admission_failure(
        tmp_path,
        CapabilityPrimaryType.PROVIDER,
        CapabilityStatus.DEPRECATED,
        "CAPABILITY_MANIFEST_NOT_ADMITTED",
    )


def test_legacy_admitted_provider_manifest_reaches_successful_execution(tmp_path: Path) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
        registry=CapabilityRegistry.from_manifests((_manifest(),)),
    )
    invocation = _invocation(kernel, run_id="RUN-LEGACY-MANIFEST-ADMITTED")

    outcome = _execute_one(kernel, invocation)

    assert outcome.failure is None
    assert outcome.invocation.invocation_status is InvocationStatus.SUCCEEDED
    assert outcome.artifact is not None


def test_legacy_negative_invocation_timeout_is_rejected_inside_kernel(tmp_path: Path) -> None:
    kernel = authorized_kernel(tmp_path)
    invocation = _invocation(kernel, run_id="RUN-LEGACY-NEGATIVE-TIMEOUT")

    with pytest.raises(ValueError, match="timeout must be non-negative"):
        _execute_one(kernel, invocation, timeout_ms=-1)


def test_legacy_zero_global_deadline_times_out_before_provider(tmp_path: Path) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-LEGACY-DEADLINE-BEFORE",
        limits=ExecutionLimits(max_duration_ms=0),
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.invocations[0].invocation_status is InvocationStatus.TIMED_OUT
    assert result.provider_results == ()
    assert any(item.code == "TIMEOUT_BEFORE_PROVIDER" for item in result.failures)


def test_legacy_expired_attempt_deadline_stops_before_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )
    invocation = _invocation(kernel, run_id="RUN-LEGACY-ATTEMPT-DEADLINE")
    clock = iter((100.0, 200.0))
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))

    outcome = _execute_one(
        kernel,
        invocation,
        limits=ExecutionLimits(timeout_ms=1_000, max_duration_ms=1_000),
        deadline=150.0,
    )

    assert outcome.invocation.invocation_status is InvocationStatus.TIMED_OUT
    assert outcome.provider_results == ()
    assert outcome.failure is not None
    assert outcome.failure.code == "TIMEOUT_BEFORE_PROVIDER"


def test_legacy_provider_exception_is_normalized_and_not_leaked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raises(
        _self: DeterministicSuccessProvider,
        _invocation: CapabilityInvocation,
        _manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult:
        raise RuntimeError("private provider detail")

    monkeypatch.setattr(DeterministicSuccessProvider, "execute", raises)
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-LEGACY-PROVIDER-EXCEPTION",
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.provider_results[-1].failure is not None
    assert result.provider_results[-1].failure.code == "PROVIDER_EXCEPTION"
    assert "private provider detail" not in result.provider_results[-1].failure.message


def test_legacy_invalid_provider_result_is_typed_as_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def returns_invalid(
        _self: DeterministicSuccessProvider,
        _invocation: CapabilityInvocation,
        _manifest: CapabilityManifest | None = None,
    ) -> object:
        return object()

    monkeypatch.setattr(DeterministicSuccessProvider, "execute", returns_invalid)
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-LEGACY-INVALID-RESULT",
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.provider_results[-1].failure is not None
    assert result.provider_results[-1].failure.code == "INVALID_PROVIDER_RESULT"
    assert result.artifacts == ()


def test_legacy_cancellation_after_provider_completion_is_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_execute = DeterministicSuccessProvider.execute
    provider_done = Event()
    release = Event()
    released_poll = False

    def execute_then_wait(
        self: DeterministicSuccessProvider,
        invocation: CapabilityInvocation,
        manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult:
        result = original_execute(self, invocation, manifest)
        provider_done.set()
        release.wait(timeout=1.0)
        return result

    def cancelled() -> bool:
        nonlocal released_poll
        if not provider_done.is_set():
            return False
        if not release.is_set():
            release.set()
            return False
        if not released_poll:
            released_poll = True
            return False
        return True

    monkeypatch.setattr(DeterministicSuccessProvider, "execute", execute_then_wait)
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-LEGACY-CANCEL-AFTER-PROVIDER",
        cancelled=cancelled,
    )

    assert result.status is ExecutionStatus.CANCELLED
    assert result.invocations[0].invocation_status is InvocationStatus.CANCELLED
    assert result.provider_results[-1].failure is not None
    assert result.provider_results[-1].failure.code == "CANCELLED_DURING_PROVIDER"
    assert result.artifacts == ()


def test_legacy_partial_output_gets_a_partial_artifact(tmp_path: Path) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicPartialProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-LEGACY-PARTIAL-ARTIFACT",
        provider_id="local.partial",
    )

    assert result.status is ExecutionStatus.PARTIAL
    assert result.invocations[0].invocation_status is InvocationStatus.PARTIAL
    assert result.artifacts
    assert result.artifacts[0].artifact_status.value == "PARTIAL"
    assert result.provider_results[-1].artifact_refs == (result.artifacts[0].artifact_id,)
    assert result.summary.delivery.status.value == "BLOCKED"


def test_legacy_partial_without_output_does_not_create_an_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def execute_without_output(
        self: DeterministicPartialProvider,
        invocation: CapabilityInvocation,
        _manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult:
        return ProviderExecutionResult(
            provider_id=self.provider_id,
            invocation_id=invocation.invocation_id,
            status=ProviderResultStatus.PARTIAL,
            output=None,
            output_contract="LocalExecutionResult",
            output_digest=None,
            failure=None,
            duration_ms=1,
            started_at=invocation.started_at,
            ended_at=invocation.started_at,
        )

    monkeypatch.setattr(DeterministicPartialProvider, "execute", execute_without_output)
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicPartialProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-LEGACY-PARTIAL-NO-OUTPUT",
        provider_id="local.partial",
    )

    assert result.status is ExecutionStatus.PARTIAL
    assert result.invocations[0].invocation_status is InvocationStatus.PARTIAL
    assert result.provider_results[-1].output is None
    assert result.artifacts == ()
    assert result.summary.delivery.status.value == "BLOCKED"


def test_legacy_terminal_failure_does_not_attempt_repair(tmp_path: Path) -> None:
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider(), DeterministicFailureProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-LEGACY-TERMINAL-NO-REPAIR",
        provider_id="local.success",
        repair_provider_id="local.repair",
        max_repairs=1,
        cancelled=True,
    )

    assert result.status is ExecutionStatus.CANCELLED
    assert result.repair_records == ()
    assert result.provider_results == ()
    assert "repair provider supplied but repair budget is zero" not in result.limitations


def test_legacy_repair_authority_denial_is_recorded_without_repair_execution(
    tmp_path: Path,
) -> None:
    authority = AuthorityScope(
        owner="legacy-test-policy",
        actor="legacy-test-runner",
        scopes=(
            "task:TASK-LEGACY-REPAIR-AUTH",
            "capability:local.failure",
            "capability:local.repair",
        ),
        decisions=(AuthorityAction.TRANSITION,),
        subject_owner="legacy-test-policy",
        operations=("execute",),
        issued_at="1970-01-01T00:00:00Z",
        expires_at="2099-12-31T23:59:59Z",
    )
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicFailureProvider()),
    )

    result = kernel.run(
        "Change one local label",
        task_id="TASK-LEGACY-REPAIR-AUTH",
        run_id="RUN-LEGACY-REPAIR-AUTH",
        provider_id="local.failure",
        authority=authority,
        repair_provider_id="local.repair",
        max_repairs=1,
    )

    assert result.status is ExecutionStatus.FAILED
    assert len(result.provider_results) == 1
    assert len(result.repair_records) == 1
    assert result.repair_records[0].status is ExecutionStatus.BLOCKED
    assert "repair authority denied" in result.limitations[0]


def test_legacy_repair_terminal_category_stops_the_repair_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def execute_with_terminal_repair(
        self: DeterministicFailureProvider,
        invocation: CapabilityInvocation,
        _manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult:
        is_repair = invocation.repair_of is not None
        code = "INITIAL_FAILURE" if not is_repair else "REPAIR_TIMEOUT"
        category = FailureCategory.PROVIDER if not is_repair else FailureCategory.TIMEOUT
        failure = FailureDetail(
            category=category,
            code=code,
            message="typed legacy repair fixture failure",
            retryable=False,
            refs=(invocation.invocation_id,),
        )
        return ProviderExecutionResult(
            provider_id=self.provider_id,
            invocation_id=invocation.invocation_id,
            status=ProviderResultStatus.FAILED,
            output=None,
            output_contract="LocalExecutionResult",
            output_digest=None,
            failure=failure,
            duration_ms=1,
            started_at=invocation.started_at,
            ended_at=invocation.started_at,
        )

    monkeypatch.setattr(DeterministicFailureProvider, "execute", execute_with_terminal_repair)
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicFailureProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-LEGACY-REPAIR-TERMINAL",
        provider_id="local.failure",
        repair_provider_id="local.failure",
        max_repairs=1,
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    assert len(result.repair_records) == 1
    assert result.repair_records[0].failure_code == "REPAIR_TIMEOUT"
    assert "explicit repair stopped at a terminal boundary" in result.limitations


def test_legacy_repair_loop_rechecks_budget_after_distinct_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def execute_with_distinct_failures(
        self: DeterministicFailureProvider,
        invocation: CapabilityInvocation,
        _manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult:
        nonlocal calls
        calls += 1
        failure = FailureDetail(
            category=FailureCategory.PROVIDER,
            code=f"DISTINCT_FAILURE_{calls}",
            message="distinct typed legacy fixture failure",
            retryable=False,
            refs=(invocation.invocation_id,),
        )
        return ProviderExecutionResult(
            provider_id=self.provider_id,
            invocation_id=invocation.invocation_id,
            status=ProviderResultStatus.FAILED,
            output=None,
            output_contract="LocalExecutionResult",
            output_digest=None,
            failure=failure,
            duration_ms=1,
            started_at=invocation.started_at,
            ended_at=invocation.started_at,
        )

    monkeypatch.setattr(DeterministicFailureProvider, "execute", execute_with_distinct_failures)
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicFailureProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-LEGACY-REPAIR-BOUNDED",
        provider_id="local.failure",
        repair_provider_id="local.failure",
        max_repairs=2,
    )

    assert result.status is ExecutionStatus.FAILED
    assert calls == 3
    assert len(result.repair_records) == 2
    assert result.repair_records[-1].failure_code == "DISTINCT_FAILURE_3"
    assert "explicit repair budget was exhausted" in result.limitations


def test_legacy_graph_stop_before_run_is_blocked_without_provider_calls(tmp_path: Path) -> None:
    graph = _graph("local.success", run_id="RUN-LEGACY-GRAPH-STOP")
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )

    result = kernel.run(
        "Change one local label",
        graph=graph,
        stop_before_run=True,
    )

    assert result.status is ExecutionStatus.STOPPED
    assert result.graph is not None
    assert result.graph.graph_status is GraphStatus.BLOCKED
    assert result.invocations[0].invocation_status is InvocationStatus.BLOCKED
    assert result.provider_results == ()


def test_legacy_graph_dry_run_authorizes_plan_without_provider_calls(tmp_path: Path) -> None:
    graph = _graph("local.success", run_id="RUN-LEGACY-GRAPH-DRY")
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )

    result = kernel.run("Change one local label", graph=graph, dry_run=True)

    assert result.status is ExecutionStatus.DRY_RUN
    assert result.graph is not None
    assert result.graph.graph_status is GraphStatus.READY
    assert result.invocations[0].invocation_status is InvocationStatus.READY
    assert result.provider_results == ()


def test_legacy_graph_dry_run_denies_missing_delegation_before_execution(
    tmp_path: Path,
) -> None:
    graph = _graph("local.success", run_id="RUN-LEGACY-GRAPH-DRY-DENIED")
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )

    result = kernel.run(
        "Change one local label",
        graph=graph,
        dry_run=True,
        delegation_ref="DELEGATION-MISSING",
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.graph is not None
    assert result.graph.graph_status is GraphStatus.BLOCKED
    assert result.invocations[0].invocation_status is InvocationStatus.BLOCKED
    assert result.failures[0].code == "DELEGATION_MISSING"
    assert result.provider_results == ()


def test_legacy_graph_cancellation_is_reflected_in_graph_state(tmp_path: Path) -> None:
    graph = _graph("local.success", run_id="RUN-LEGACY-GRAPH-CANCEL")
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )

    result = kernel.run("Change one local label", graph=graph, cancelled=True)

    assert result.status is ExecutionStatus.CANCELLED
    assert result.graph is not None
    assert result.graph.graph_status is GraphStatus.CANCELLED
    assert result.invocations[0].invocation_status is InvocationStatus.CANCELLED
    assert result.provider_results == ()


def test_legacy_graph_partial_state_is_not_promoted_to_success(tmp_path: Path) -> None:
    graph = _graph(
        "local.partial",
        "local.success",
        run_id="RUN-LEGACY-GRAPH-PARTIAL",
    )
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicPartialProvider(), DeterministicSuccessProvider()),
    )

    result = kernel.run("Change one local label", graph=graph)

    assert result.status is ExecutionStatus.PARTIAL
    assert result.graph is not None
    assert result.graph.graph_status is GraphStatus.PARTIAL
    assert [item.invocation_status for item in result.invocations] == [
        InvocationStatus.PARTIAL,
        InvocationStatus.SUCCEEDED,
    ]
    assert result.summary.delivery.status.value == "BLOCKED"


def test_legacy_graph_success_mixed_with_failure_remains_partial(tmp_path: Path) -> None:
    graph = _graph(
        "local.failure",
        "local.success",
        run_id="RUN-LEGACY-GRAPH-MIXED",
    )
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicFailureProvider(), DeterministicSuccessProvider()),
    )

    result = kernel.run("Change one local label", graph=graph)

    assert result.status is ExecutionStatus.PARTIAL
    assert result.graph is not None
    assert result.graph.graph_status is GraphStatus.PARTIAL
    assert [item.invocation_status for item in result.invocations] == [
        InvocationStatus.FAILED,
        InvocationStatus.SUCCEEDED,
    ]
    assert result.provider_results[0].status is ProviderResultStatus.FAILED
    assert result.provider_results[1].status is ProviderResultStatus.SUCCEEDED


def test_legacy_graph_timeout_marks_unexecuted_node_truthfully(tmp_path: Path) -> None:
    graph = _graph("local.success", run_id="RUN-LEGACY-GRAPH-TIMEOUT")
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )

    result = kernel.run(
        "Change one local label",
        graph=graph,
        limits=ExecutionLimits(max_duration_ms=0),
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.graph is not None
    assert result.graph.graph_status is GraphStatus.PARTIAL
    assert result.invocations[0].invocation_status is InvocationStatus.TIMED_OUT
    assert result.provider_results == ()
    assert result.failures[0].code == "GRAPH_TIMEOUT"


def test_legacy_graph_provider_preflight_blocks_all_nodes_before_side_effects(
    tmp_path: Path,
) -> None:
    graph = _graph(
        "local.success",
        "missing.provider",
        run_id="RUN-LEGACY-GRAPH-PREFLIGHT",
    )
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )
    profile = kernel._profile(
        "Change one local label",
        task_id=graph.task_id,
        run_id=graph.run_id,
        requested_outcome="",
    )
    route = _selected_graph_route(kernel, graph)

    result = kernel._run_graph(
        profile,
        route,
        graph,
        authority=broad_test_authority(),
        limits=ExecutionLimits(),
        conditions=(),
        cancelled=False,
        timeout_ms=None,
        delegation_ref=None,
        dry_run=False,
        stop_before_run=False,
        persist=False,
        deadline=None,
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.graph is not None
    assert result.graph.graph_status is GraphStatus.BLOCKED
    assert all(item.invocation_status is InvocationStatus.BLOCKED for item in result.invocations)
    assert result.provider_results == ()
    assert result.failures[0].code == "PROVIDER_PREFLIGHT_FAILED"


def test_legacy_rejected_route_is_returned_unchanged_before_provider_resolution() -> None:
    route = replace(cast(RouteDecision, all_records()[1]), route_status=RouteStatus.REJECTED)

    result = _route_with_provider(
        route,
        "local.success",
        provider_admitted=True,
        admitted_provider_ids=("local.success",),
    )

    assert result is route


def test_legacy_provider_worker_reports_cancellation_after_it_finishes(tmp_path: Path) -> None:
    provider_done = Event()
    release = Event()

    class Provider:
        def execute(
            self,
            invocation: CapabilityInvocation,
            manifest: CapabilityManifest | None = None,
        ) -> ProviderExecutionResult:
            del manifest
            provider_done.set()
            release.wait(timeout=1.0)
            return ProviderExecutionResult(
                provider_id=invocation.provider_id or "local.success",
                invocation_id=invocation.invocation_id,
                status=ProviderResultStatus.SUCCEEDED,
                output={"late": True},
                output_contract="LocalExecutionResult",
                output_digest=None,
                started_at="2026-08-28T12:00:00Z",
                ended_at="2026-08-28T12:00:00Z",
            )

    def cancelled() -> bool:
        if not provider_done.is_set():
            return False
        if not release.is_set():
            release.set()
            return False
        return True

    kernel = authorized_kernel(tmp_path)
    value, _elapsed, was_cancelled, timed_out, raised = _call_provider_with_deadline(
        Provider(),
        _invocation(kernel, run_id="RUN-LEGACY-WORKER-CANCEL"),
        manifest=None,
        timeout_ms=1_000,
        cancelled=cancelled,
    )

    assert value is None
    assert was_cancelled is True
    assert timed_out is False
    assert raised is False
    assert provider_done.is_set()
    assert release.is_set()


def test_legacy_graph_with_only_failures_keeps_the_partial_graph_state(tmp_path: Path) -> None:
    graph = _graph("local.failure", run_id="RUN-LEGACY-GRAPH-ONLY-FAILURE")
    result = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicFailureProvider()),
    ).run("Change one local label", graph=graph)

    assert result.status is ExecutionStatus.FAILED
    assert result.graph is not None
    assert result.graph.graph_status is GraphStatus.PARTIAL
    assert result.invocations[0].invocation_status is InvocationStatus.FAILED
    assert result.provider_results[0].status is ProviderResultStatus.FAILED


def test_legacy_repeated_repair_failure_stops_before_a_third_provider_call(
    tmp_path: Path,
) -> None:
    result = authorized_kernel(tmp_path).run(
        "Change one local label",
        run_id="RUN-LEGACY-REPAIR-REPEATED",
        provider_id="local.failure",
        repair_provider_id="local.failure",
        max_repairs=2,
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.stop_decision is not None
    assert result.stop_decision.condition is StopCondition.REPEATED_FAILURE
    assert len(result.provider_results) == 2
    assert "explicit repair stopped after repeated failure" in result.limitations


def test_legacy_no_progress_is_a_stop_signal_when_failures_are_not_repeated() -> None:
    decision = evaluate_stop(
        progress_history=(
            ProgressSnapshot(0, criteria=("same-state",)),
            ProgressSnapshot(1, criteria=("same-state",)),
        ),
        failure_history=(
            FailureObservation("failure-a", "provider-a"),
            FailureObservation("failure-b", "provider-b"),
        ),
    )

    assert decision.condition is StopCondition.NO_PROGRESS
    assert decision.should_stop is True


def test_legacy_timeout_does_not_promote_a_late_worker_or_retry_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_execute = DeterministicSuccessProvider.execute
    calls = 0

    def slow_execute(
        self: DeterministicSuccessProvider,
        invocation: CapabilityInvocation,
        manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult:
        nonlocal calls
        del manifest
        calls += 1
        time.sleep(0.025)
        return original_execute(self, invocation)

    monkeypatch.setattr(DeterministicSuccessProvider, "execute", slow_execute)
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicSuccessProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-LEGACY-TIMEOUT-LATE-WORKER",
        timeout_ms=1,
        limits=ExecutionLimits(timeout_ms=1, max_duration_ms=100, max_retries=3),
    )

    time.sleep(0.04)
    assert result.status is ExecutionStatus.TIMED_OUT
    assert calls == 1
    assert len(result.provider_results) == 1
    assert result.artifacts == ()


def test_legacy_partial_without_output_has_no_synthetic_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def partial_without_output(
        self: DeterministicPartialProvider,
        invocation: CapabilityInvocation,
        manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult:
        del manifest
        failure = FailureDetail(
            FailureCategory.PROVIDER,
            "PARTIAL_WITHOUT_OUTPUT",
            "partial provider result contained no output",
            refs=(invocation.invocation_id,),
        )
        return ProviderExecutionResult(
            provider_id=self.provider_id,
            invocation_id=invocation.invocation_id,
            status=ProviderResultStatus.PARTIAL,
            output=None,
            output_contract="LocalExecutionResult",
            output_digest=None,
            failure=failure,
            started_at=invocation.started_at,
            ended_at=invocation.started_at,
        )

    monkeypatch.setattr(DeterministicPartialProvider, "execute", partial_without_output)
    kernel = authorized_kernel(
        tmp_path,
        providers=_providers(DeterministicPartialProvider()),
    )

    result = kernel.run(
        "Change one local label",
        run_id="RUN-LEGACY-PARTIAL-NO-OUTPUT",
        provider_id="local.partial",
    )

    assert result.status is ExecutionStatus.PARTIAL
    assert result.invocations[0].invocation_status is InvocationStatus.PARTIAL
    assert result.provider_results[-1].failure is not None
    assert result.provider_results[-1].failure.code == "PARTIAL_WITHOUT_OUTPUT"
    assert result.artifacts == ()
