"""Bounded, project-local execution kernel for Phase 2.

The kernel is intentionally small and explicit.  It classifies and routes a
request, validates an invocation, checks a scoped authority grant, resolves one
registered local provider, and only then executes it.  Providers return data;
verification, critique, assurance, stopping and persistence remain coordinator
responsibilities.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass, replace
from enum import StrEnum
from threading import Thread

from .assurance import (
    AssuranceDecision,
    AssuranceResult,
    assure_quality,
    build_quality_report,
    create_critique,
)
from .authority import (
    AuthorityAction,
    AuthorityScope,
    AuthoritySnapshot,
    authority_snapshot,
    check_decision,
    check_invocation_authority,
)
from .boundary import ProjectBoundary
from .classification import DEFAULT_TIMESTAMP, classify_task
from .errors import FailureCategory, FailureDetail
from .evidence import validate_evidence_links
from .graph import GraphNodeResult, GraphValidationError, execute_graph, validate_execution_graph
from .models import (
    ArtifactContent,
    ArtifactProducer,
    ArtifactProvenance,
    ArtifactRecord,
    ArtifactSecurity,
    ArtifactStatus,
    ArtifactType,
    CapabilityInvocation,
    CapabilityManifest,
    CapabilityPrimaryType,
    ClaimStatus,
    Confidence,
    DataClass,
    Delivery,
    DeliveryStatus,
    EvidenceRecord,
    ExecutionGraph,
    ExecutionSummary,
    GateSummary,
    GraphStatus,
    Independence,
    InvocationCallee,
    InvocationCaller,
    InvocationHandoff,
    InvocationInputs,
    InvocationLimits,
    InvocationStatus,
    LifecycleState,
    PrivacyClass,
    Provenance,
    QualityReport,
    Recommendation,
    RecordEnvelope,
    RecordStatus,
    Redaction,
    RegistryOrigin,
    RepositoryClassification,
    RepositoryContext,
    ResidualRisk,
    ResourceUsage,
    RouteDecision,
    RouteKind,
    RouteStatus,
    RunSummary,
    SchemaVersion,
    SelectedCapability,
    SourceType,
    TaskProfile,
    TelemetryActor,
    TelemetryEventType,
    TrustState,
    VerificationReport,
)
from .persistence import RunStore
from .providers import (
    CapabilityProvider,
    ProviderExecutionResult,
    ProviderRegistry,
    ProviderResultStatus,
    digest_output,
)
from .registry import CapabilityRegistry
from .routing import minimum_route
from .serialization import to_dict, to_json
from .stops import BudgetUsage, StopBudget, StopDecision, evaluate_stop
from .telemetry import TelemetryLog, create_event
from .validation import ValidationCode, ValidationFinding
from .verification import (
    VerificationOutcome,
    aggregate_verification,
    verify_provider_result,
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")


class ExecutionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DRY_RUN = "DRY_RUN"
    STOPPED = "STOPPED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    PARTIAL = "PARTIAL"


class InvocationStateError(ValueError):
    """Raised when a capability invocation skips a declared lifecycle edge."""


_INVOCATION_TRANSITIONS: dict[InvocationStatus, frozenset[InvocationStatus]] = {
    InvocationStatus.CREATED: frozenset(
        {InvocationStatus.VALIDATED, InvocationStatus.BLOCKED, InvocationStatus.CANCELLED}
    ),
    InvocationStatus.VALIDATED: frozenset(
        {InvocationStatus.AUTHORIZED, InvocationStatus.BLOCKED, InvocationStatus.CANCELLED}
    ),
    InvocationStatus.AUTHORIZED: frozenset(
        {InvocationStatus.READY, InvocationStatus.BLOCKED, InvocationStatus.CANCELLED}
    ),
    InvocationStatus.READY: frozenset(
        {
            InvocationStatus.RUNNING,
            InvocationStatus.BLOCKED,
            InvocationStatus.CANCELLED,
            InvocationStatus.TIMED_OUT,
            InvocationStatus.PARTIAL,
        }
    ),
    InvocationStatus.RUNNING: frozenset(
        {
            InvocationStatus.SUCCEEDED,
            InvocationStatus.PARTIAL,
            InvocationStatus.FAILED,
            InvocationStatus.BLOCKED,
            InvocationStatus.CANCELLED,
            InvocationStatus.TIMED_OUT,
        }
    ),
    InvocationStatus.SUCCEEDED: frozenset(),
    InvocationStatus.PARTIAL: frozenset(),
    InvocationStatus.FAILED: frozenset(),
    InvocationStatus.BLOCKED: frozenset(),
    InvocationStatus.CANCELLED: frozenset(),
    InvocationStatus.TIMED_OUT: frozenset(),
}


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip() and value not in result:
            result.append(value)
    return tuple(result)


def _id(value: str, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")
    return value


def can_transition_invocation(
    current: InvocationStatus | str, target: InvocationStatus | str
) -> bool:
    try:
        source = current if isinstance(current, InvocationStatus) else InvocationStatus(current)
        destination = target if isinstance(target, InvocationStatus) else InvocationStatus(target)
    except (TypeError, ValueError):
        return False
    return destination in _INVOCATION_TRANSITIONS.get(source, frozenset())


def transition_invocation(
    invocation: CapabilityInvocation,
    target: InvocationStatus | str,
    *,
    timestamp: str = DEFAULT_TIMESTAMP,
    failure_refs: Iterable[str] = (),
) -> CapabilityInvocation:
    """Return a copy after checking the invocation state machine."""

    if not isinstance(invocation, CapabilityInvocation):
        raise TypeError("invocation must be a CapabilityInvocation")
    try:
        destination = target if isinstance(target, InvocationStatus) else InvocationStatus(target)
    except (TypeError, ValueError) as exc:
        raise InvocationStateError("unknown invocation state") from exc
    if not can_transition_invocation(invocation.invocation_status, destination):
        raise InvocationStateError(
            f"invalid invocation transition: {_enum_value(invocation.invocation_status)}"
            f" -> {_enum_value(destination)}"
        )
    terminal = {
        InvocationStatus.SUCCEEDED,
        InvocationStatus.PARTIAL,
        InvocationStatus.FAILED,
        InvocationStatus.BLOCKED,
        InvocationStatus.CANCELLED,
        InvocationStatus.TIMED_OUT,
    }
    started_at = invocation.started_at
    completed_at = invocation.completed_at
    if destination is InvocationStatus.RUNNING and started_at is None:
        started_at = timestamp
    if destination in terminal:
        completed_at = timestamp
    status = (
        RecordStatus.BLOCKED
        if destination is InvocationStatus.BLOCKED
        else invocation.record.status
    )
    return replace(
        invocation,
        record=replace(invocation.record, status=status),
        invocation_status=destination,
        failure_refs=_dedupe((*invocation.failure_refs, *failure_refs)),
        started_at=started_at,
        completed_at=completed_at,
    )


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Global limits applied before and during every local run."""

    max_nodes: int = 128
    max_invocations: int = 16
    max_retries: int = 2
    max_duration_ms: int = 30_000
    max_evidence: int = 256
    max_telemetry: int = 1_024
    timeout_ms: int = 5_000
    max_repairs: int = 0

    def __post_init__(self) -> None:
        values = (
            self.max_nodes,
            self.max_invocations,
            self.max_retries,
            self.max_duration_ms,
            self.max_evidence,
            self.max_telemetry,
            self.timeout_ms,
            self.max_repairs,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values
        ):
            raise ValueError("execution limits must be non-negative integers")
        if self.max_nodes < 1:
            raise ValueError("max_nodes must be positive")


@dataclass(frozen=True, slots=True)
class RunResult:
    """Immutable output aggregate for one classified and correlated run."""

    status: ExecutionStatus | str
    profile: TaskProfile
    route: RouteDecision
    graph: ExecutionGraph | None
    invocations: tuple[CapabilityInvocation, ...]
    provider_results: tuple[ProviderExecutionResult, ...]
    artifacts: tuple[ArtifactRecord, ...]
    evidence: tuple[object, ...]
    verification: VerificationReport
    critique: object
    assurance: AssuranceResult
    quality: QualityReport
    summary: RunSummary
    telemetry: TelemetryLog
    failures: tuple[FailureDetail, ...]
    authority_snapshot: AuthoritySnapshot | None
    limitations: tuple[str, ...] = ()
    verification_reports: tuple[VerificationReport, ...] = ()
    critiques: tuple[object, ...] = ()
    assurances: tuple[AssuranceResult, ...] = ()
    quality_reports: tuple[QualityReport, ...] = ()
    repair_records: tuple[RepairRecord, ...] = ()
    stop_decision: StopDecision | None = None

    @property
    def executed(self) -> bool:
        return bool(self.provider_results)

    @property
    def provider(self) -> str | None:
        return self.invocations[0].provider_id if self.invocations else None


@dataclass(frozen=True, slots=True)
class _InvocationOutcome:
    invocation: CapabilityInvocation
    provider_results: tuple[ProviderExecutionResult, ...]
    artifact: ArtifactRecord | None
    failure: FailureDetail | None
    retries: int
    output: object | None = None
    duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class RepairRecord:
    """Auditable relationship between a failed invocation and its repair."""

    repair_id: str
    repairs_invocation_id: str
    repair_invocation_id: str
    trigger_refs: tuple[str, ...]
    status: ExecutionStatus | str
    attempt: int
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.repair_id,
                self.repairs_invocation_id,
                self.repair_invocation_id,
            )
        ):
            raise ValueError("repair identities are required")
        if not isinstance(self.attempt, int) or isinstance(self.attempt, bool) or self.attempt < 1:
            raise ValueError("repair attempt must be positive")
        object.__setattr__(self, "trigger_refs", _dedupe(self.trigger_refs))


def _record(timestamp: str, *, status: RecordStatus = RecordStatus.CURRENT) -> RecordEnvelope:
    return RecordEnvelope(
        status=status,
        provenance=Provenance(SourceType.GENERATED, ("phase-2-runtime",), timestamp),
        evidence_refs=(),
    )


def _failure(
    category: FailureCategory,
    code: str,
    message: str,
    *,
    refs: Iterable[str] = (),
    retryable: bool = False,
    attempt: int = 1,
) -> FailureDetail:
    return FailureDetail(category, code, message, retryable, _dedupe(refs), attempt)


def _route_with_provider(
    route: RouteDecision, provider_id: str, *, provider_admitted: bool
) -> RouteDecision:
    selected = SelectedCapability(
        capability_id=provider_id,
        role=CapabilityPrimaryType.PROVIDER,
        reason="explicit local provider selected by the execution kernel",
        required=True,
    )
    decision = replace(
        route.decision,
        activation_reasons=_dedupe(
            (*route.decision.activation_reasons, "explicit local provider selected")
        ),
    )
    return replace(
        route,
        route_status=RouteStatus.SELECTED,
        route_kind=RouteKind.PROVIDER,
        decision=decision,
        selected=(selected,),
        quality_gates=_dedupe((*route.quality_gates, "provider-availability", "verification")),
        fallback=None,
        omitted=tuple(
            item
            for item in route.omitted
            if not provider_admitted or item.capability_id != provider_id
        ),
        unresolved=tuple(
            item
            for item in route.unresolved
            if not provider_admitted or item != "PROVIDER_UNAVAILABLE"
        ),
    )


def _build_invocation(
    profile: TaskProfile,
    *,
    invocation_id: str,
    capability_id: str,
    provider_id: str,
    graph_node_id: str | None,
    acceptance_refs: tuple[str, ...],
    output_contract: str,
    limits: ExecutionLimits,
    timestamp: str,
    dependencies: tuple[str, ...] = (),
    repair_of: str | None = None,
    repair_trigger_refs: tuple[str, ...] = (),
    delegation_ref: str | None = None,
) -> CapabilityInvocation:
    objective_digest = digest_output(profile.objective)
    return CapabilityInvocation(
        schema_version=SchemaVersion.CAPABILITY_INVOCATION,
        invocation_id=invocation_id,
        task_id=profile.task_id,
        run_id=profile.run_id,
        record=_record(timestamp),
        graph_node_id=graph_node_id,
        caller=InvocationCaller("orchestrator", f"AUTH-ROUTE-{profile.task_id}"),
        callee=InvocationCallee(capability_id, "1.0.0"),
        objective=profile.objective,
        scope=(f"task:{profile.task_id}", f"capability:{capability_id}"),
        non_goals=(
            "load host skills",
            "invoke shell or network",
        ),
        inputs=InvocationInputs((), (), objective_digest),
        handoff=InvocationHandoff(
            acceptance_refs or ("P2-EXECUTION",),
            (output_contract,),
            (
                "provider unavailable",
                "authority denied",
            ),
        ),
        limits=InvocationLimits(
            token_budget=None,
            duration_budget_ms=limits.max_duration_ms,
            tool_call_budget=1,
            retry_budget=limits.max_retries,
        ),
        permissions=("project-local-read",),
        requested_tools=(),
        expected_evidence=(
            "provider output digest",
            "verification result",
        ),
        invocation_status=InvocationStatus.CREATED,
        failure_refs=(),
        started_at=None,
        completed_at=None,
        operation="execute",
        capability_origin=RegistryOrigin.PROJECT,
        dependencies=dependencies,
        trace_context=(("trace_id", profile.run_id), ("span_id", invocation_id), ("attempt", "1")),
        provider_id=provider_id,
        delegation_ref=delegation_ref,
        repair_of=repair_of,
        repair_trigger_refs=repair_trigger_refs,
    )


def _artifact(
    invocation: CapabilityInvocation,
    output: object,
    *,
    acceptance_refs: tuple[str, ...],
    timestamp: str,
    partial: bool = False,
) -> ArtifactRecord:
    encoded = to_json(output).encode("utf-8")
    artifact_id = f"ART-{invocation.invocation_id}"
    evidence_id = f"EVID-{invocation.invocation_id}"
    status = ArtifactStatus.PARTIAL if partial else ArtifactStatus.ACCEPTED
    return ArtifactRecord(
        schema_version=SchemaVersion.ARTIFACT_RECORD,
        artifact_id=artifact_id,
        task_id=invocation.task_id,
        run_id=invocation.run_id,
        record=replace(_record(timestamp), evidence_refs=(evidence_id,)),
        artifact_type=ArtifactType.FINAL_DELIVERY,
        title="project-local provider result",
        producer=ArtifactProducer(invocation.callee.capability_id, invocation.invocation_id),
        content=ArtifactContent(
            locator=(f".harness/state/runs/{invocation.run_id}/{artifact_id}.json"),
            digest=digest_output(output),
            media_type="application/json",
            size_bytes=len(encoded),
        ),
        source_refs=(invocation.invocation_id,),
        contract_refs=acceptance_refs or ("P2-EXECUTION",),
        dependencies=invocation.dependencies,
        artifact_status=status,
        evidence_refs=(evidence_id,),
        limitations=("partial provider output",) if partial else (),
        security=ArtifactSecurity(DataClass.INTERNAL, Redaction.NONE, "project-local"),
        provenance=ArtifactProvenance(
            SourceType.PROVIDER,
            invocation.provider_id,
            (),
            timestamp,
        ),
        supersedes=None,
    )


def _synthetic_provider_result(
    invocation: CapabilityInvocation,
    failure: FailureDetail,
) -> ProviderExecutionResult:
    return ProviderExecutionResult(
        provider_id=invocation.provider_id or "orchestrator",
        invocation_id=invocation.invocation_id,
        status=ProviderResultStatus.FAILED,
        output=None,
        output_contract=invocation.handoff.required_output_contracts[0]
        if invocation.handoff.required_output_contracts
        else "ExecutionResult",
        output_digest=None,
        failure=failure,
        duration_ms=0,
        attempt=1,
    )


def _with_attempt(invocation: CapabilityInvocation, attempt: int) -> CapabilityInvocation:
    context = tuple(
        (key, str(attempt) if key == "attempt" else value)
        for key, value in invocation.trace_context
    )
    return replace(invocation, trace_context=context)


def _terminal_without_execution(
    invocation: CapabilityInvocation,
    status: InvocationStatus,
    failure: FailureDetail,
    *,
    timestamp: str,
) -> CapabilityInvocation:
    """Move a never-called invocation to a truthful terminal state."""

    if status in (InvocationStatus.BLOCKED, InvocationStatus.CANCELLED):
        return transition_invocation(
            invocation, status, timestamp=timestamp, failure_refs=(failure.code,)
        )
    prepared = transition_invocation(invocation, InvocationStatus.VALIDATED, timestamp=timestamp)
    prepared = transition_invocation(prepared, InvocationStatus.AUTHORIZED, timestamp=timestamp)
    prepared = transition_invocation(prepared, InvocationStatus.READY, timestamp=timestamp)
    return transition_invocation(
        prepared, status, timestamp=timestamp, failure_refs=(failure.code,)
    )


def _provider_failure(provider_id: str, invocation_id: str) -> FailureDetail:
    return _failure(
        FailureCategory.PROVIDER,
        "PROVIDER_EXCEPTION",
        "local provider failed without exposing internal details",
        refs=(provider_id, invocation_id),
    )


def _authority_required_failure(invocation: CapabilityInvocation) -> FailureDetail:
    return _failure(
        FailureCategory.AUTHORITY_DENIED,
        "AUTHORITY_REQUIRED",
        "an explicit authority grant is required before execution",
        refs=(invocation.invocation_id,),
    )


def _authority_denied_outcome(
    invocation: CapabilityInvocation, *, timestamp: str
) -> _InvocationOutcome:
    failure = _authority_required_failure(invocation)
    blocked = transition_invocation(
        invocation,
        InvocationStatus.BLOCKED,
        timestamp=timestamp,
        failure_refs=(failure.code,),
    )
    return _InvocationOutcome(blocked, (), None, failure, 0)


def _call_provider_with_deadline(
    provider: CapabilityProvider,
    invocation: CapabilityInvocation,
    *,
    manifest: CapabilityManifest | None,
    timeout_ms: int,
    cancelled: bool | Callable[[], bool],
) -> tuple[object | None, int, bool, bool, bool]:
    """Run a local fixture with a real deadline and daemonized overrun guard.

    Phase 2 providers are deterministic, project-local fixtures. A daemon
    thread keeps the coordinator responsive when a cooperative fixture hangs;
    the hostile-code sandbox remains an explicit non-goal of this phase.
    """

    started = time.monotonic()
    values: list[object] = []
    errors: list[BaseException] = []

    def invoke() -> None:
        try:
            values.append(provider.execute(invocation, manifest))
        except BaseException as exc:  # noqa: BLE001 - normalize every fixture failure
            errors.append(exc)

    worker = Thread(target=invoke, name=f"harness-provider-{invocation.invocation_id}", daemon=True)
    worker.start()
    deadline = started + timeout_ms / 1000
    while worker.is_alive():
        if callable(cancelled):
            try:
                if cancelled():
                    elapsed = max(0, int((time.monotonic() - started) * 1000))
                    return None, elapsed, True, False, False
            except Exception:
                elapsed = max(0, int((time.monotonic() - started) * 1000))
                return None, elapsed, True, False, False
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            elapsed = max(0, int((time.monotonic() - started) * 1000))
            return None, elapsed, False, True, False
        worker.join(min(0.01, remaining))
    elapsed = max(0, int((time.monotonic() - started) * 1000))
    if callable(cancelled):
        try:
            if cancelled():
                return None, elapsed, True, False, False
        except Exception:
            return None, elapsed, True, False, False
    if errors:
        return None, elapsed, False, False, True
    return (values[0] if values else None), elapsed, False, False, False


def _status_for_outcome(outcome: _InvocationOutcome) -> ExecutionStatus:
    if outcome.invocation.invocation_status is InvocationStatus.PARTIAL:
        return ExecutionStatus.PARTIAL
    if outcome.failure is None:
        return ExecutionStatus.SUCCEEDED
    if outcome.failure.category is FailureCategory.CANCELLED:
        return ExecutionStatus.CANCELLED
    if outcome.failure.category is FailureCategory.TIMEOUT:
        return ExecutionStatus.TIMED_OUT
    if outcome.failure.category is FailureCategory.BUDGET:
        return ExecutionStatus.BLOCKED
    return ExecutionStatus.FAILED


class ExecutionKernel:
    """Coordinate one bounded direct or graph execution.

    Authority is caller-owned.  The kernel never synthesizes a grant; callers
    may provide one per run or inject an immutable grant at construction time.
    A missing grant is a first-class denial before any provider is resolved.
    """

    def __init__(
        self,
        boundary: ProjectBoundary,
        *,
        providers: ProviderRegistry | None = None,
        registry: CapabilityRegistry | None = None,
        store: RunStore | None = None,
        authority: AuthorityScope | None = None,
        timestamp: str = DEFAULT_TIMESTAMP,
    ) -> None:
        if not isinstance(boundary, ProjectBoundary):
            raise TypeError("execution kernel requires a ProjectBoundary")
        if authority is not None and not isinstance(authority, AuthorityScope):
            raise TypeError("execution kernel authority must be an AuthorityScope")
        self.boundary = boundary
        self.providers = providers or ProviderRegistry.local_defaults()
        self.registry = registry or CapabilityRegistry()
        self.store = store or RunStore(boundary)
        self.authority = authority
        self.timestamp = timestamp

    def _profile(
        self,
        objective: str | TaskProfile | Mapping[str, object],
        *,
        task_id: str | None,
        run_id: str | None,
        requested_outcome: str,
    ) -> TaskProfile:
        if isinstance(objective, TaskProfile):
            if task_id is not None and task_id != objective.task_id:
                raise ValueError("task id does not match the supplied profile")
            if run_id is not None and run_id != objective.run_id:
                raise ValueError("run id does not match the supplied profile")
            return objective
        if isinstance(objective, str) and (not objective.strip() or len(objective) > 10_000):
            raise ValueError("objective is invalid")
        selected_task = task_id or "TASK-EXECUTION"
        selected_run = run_id or "RUN-EXECUTION"
        _id(selected_task, "task id")
        _id(selected_run, "run id")
        repository = RepositoryContext(
            root=str(self.boundary.root),
            classification=RepositoryClassification.BROWNFIELD,
            trust_state=TrustState.TRUSTED,
        )
        return classify_task(
            objective,
            requested_outcome,
            task_id=selected_task,
            run_id=selected_run,
            repository_context=repository,
            created_at=self.timestamp,
        )

    def _execute_one(
        self,
        invocation: CapabilityInvocation,
        *,
        authority: AuthorityScope | None,
        limits: ExecutionLimits,
        invocation_count: int,
        required_conditions: tuple[str, ...],
        cancelled: bool | Callable[[], bool],
        timeout_ms: int | None,
    ) -> _InvocationOutcome:
        if authority is None:
            return _authority_denied_outcome(invocation, timestamp=self.timestamp)
        current = transition_invocation(
            invocation, InvocationStatus.VALIDATED, timestamp=self.timestamp
        )
        check = check_invocation_authority(
            authority,
            task_id=current.task_id,
            invocation_id=current.invocation_id,
            capability_id=current.callee.capability_id,
            operation=current.operation,
            required_scope=current.scope,
            at=self.timestamp,
            required_conditions=required_conditions,
            delegation_ref=current.delegation_ref,
        )
        if not check.allowed:
            failure = _failure(
                FailureCategory.AUTHORITY_DENIED,
                check.code,
                "invocation authority denied before provider resolution",
                refs=(current.invocation_id,),
            )
            blocked = transition_invocation(
                current,
                InvocationStatus.BLOCKED,
                timestamp=self.timestamp,
                failure_refs=(failure.code,),
            )
            return _InvocationOutcome(blocked, (), None, failure, 0)
        snapshot = authority_snapshot(
            authority,
            subject_id=current.invocation_id,
            operation=current.operation,
            authority_id=f"AUTH-{current.invocation_id}",
            required_scope=current.scope,
        )
        current = replace(current, authority_snapshot_ref=snapshot.digest)
        current = transition_invocation(
            current, InvocationStatus.AUTHORIZED, timestamp=self.timestamp
        )
        current = transition_invocation(current, InvocationStatus.READY, timestamp=self.timestamp)

        is_cancelled = cancelled() if callable(cancelled) else cancelled
        if is_cancelled:
            failure = _failure(
                FailureCategory.CANCELLED,
                "CANCELLED_BEFORE_PROVIDER",
                "run cancellation was observed before provider execution",
                refs=(current.invocation_id,),
            )
            cancelled_invocation = transition_invocation(
                current,
                InvocationStatus.CANCELLED,
                timestamp=self.timestamp,
                failure_refs=(failure.code,),
            )
            return _InvocationOutcome(cancelled_invocation, (), None, failure, 0)
        effective_timeout = min(limits.timeout_ms, limits.max_duration_ms)
        if timeout_ms is not None:
            effective_timeout = min(timeout_ms, effective_timeout)
        if effective_timeout < 0:
            raise ValueError("timeout must be non-negative")
        if effective_timeout == 0:
            failure = _failure(
                FailureCategory.TIMEOUT,
                "TIMEOUT_BEFORE_PROVIDER",
                "run timeout elapsed before provider execution",
                refs=(current.invocation_id,),
            )
            timed_out = transition_invocation(
                current,
                InvocationStatus.TIMED_OUT,
                timestamp=self.timestamp,
                failure_refs=(failure.code,),
            )
            return _InvocationOutcome(timed_out, (), None, failure, 0)
        if invocation_count >= limits.max_invocations:
            failure = _failure(
                FailureCategory.BUDGET,
                "INVOCATION_BUDGET_EXHAUSTED",
                "maximum invocation budget was reached",
                refs=(current.invocation_id,),
            )
            blocked = transition_invocation(
                current,
                InvocationStatus.BLOCKED,
                timestamp=self.timestamp,
                failure_refs=(failure.code,),
            )
            return _InvocationOutcome(blocked, (), None, failure, 0)
        provider = self.providers.resolve(
            current.provider_id or "",
            operation=current.operation,
            capability_id=current.callee.capability_id,
        )
        if provider is None:
            failure = _failure(
                FailureCategory.CAPABILITY_UNAVAILABLE,
                "PROVIDER_UNAVAILABLE",
                "selected provider is not registered and available",
                refs=(current.provider_id or "", current.invocation_id),
            )
            blocked = transition_invocation(
                current,
                InvocationStatus.BLOCKED,
                timestamp=self.timestamp,
                failure_refs=(failure.code,),
            )
            return _InvocationOutcome(blocked, (), None, failure, 0)

        manifest = self.registry.find(
            current.callee.capability_id,
            current.callee.manifest_version,
            include_stale=True,
            include_deprecated=True,
            include_rejected=True,
        )
        if manifest is not None:
            inspection = self.registry.inspect(
                manifest.capability_id,
                manifest.version,
            )
            if manifest.primary_type is not CapabilityPrimaryType.PROVIDER:
                failure = _failure(
                    FailureCategory.CAPABILITY_UNAVAILABLE,
                    "CAPABILITY_MANIFEST_TYPE_MISMATCH",
                    "selected capability manifest is not a provider manifest",
                    refs=(manifest.capability_id, current.invocation_id),
                )
                blocked = transition_invocation(
                    current,
                    InvocationStatus.BLOCKED,
                    timestamp=self.timestamp,
                    failure_refs=(failure.code,),
                )
                return _InvocationOutcome(blocked, (), None, failure, 0)
            if not inspection.usable:
                failure = _failure(
                    FailureCategory.CAPABILITY_UNAVAILABLE,
                    "CAPABILITY_MANIFEST_NOT_ADMITTED",
                    "selected provider manifest failed registry admission",
                    refs=(manifest.capability_id, current.invocation_id),
                )
                blocked = transition_invocation(
                    current,
                    InvocationStatus.BLOCKED,
                    timestamp=self.timestamp,
                    failure_refs=(failure.code,),
                )
                return _InvocationOutcome(blocked, (), None, failure, 0)

        running = transition_invocation(current, InvocationStatus.RUNNING, timestamp=self.timestamp)
        results: list[ProviderExecutionResult] = []
        retries = 0
        elapsed_total_ms = 0
        provider_reported_duration_ms = 0
        attempt_invocation = running
        while True:
            raw_result, elapsed_ms, cancelled_during, provider_timed_out, provider_raised = (
                _call_provider_with_deadline(
                    provider,
                    attempt_invocation,
                    manifest=manifest,
                    timeout_ms=effective_timeout,
                    cancelled=cancelled,
                )
            )
            elapsed_total_ms += elapsed_ms
            if cancelled_during:
                result = _synthetic_provider_result(
                    attempt_invocation,
                    _failure(
                        FailureCategory.CANCELLED,
                        "CANCELLED_DURING_PROVIDER",
                        "run cancellation was observed during provider execution",
                        refs=(attempt_invocation.invocation_id,),
                    ),
                )
            elif provider_timed_out:
                result = _synthetic_provider_result(
                    attempt_invocation,
                    _failure(
                        FailureCategory.TIMEOUT,
                        "PROVIDER_TIMEOUT",
                        "provider did not finish before the invocation timeout",
                        refs=(attempt_invocation.invocation_id,),
                    ),
                )
            elif provider_raised:
                result = _synthetic_provider_result(
                    attempt_invocation,
                    _provider_failure(
                        attempt_invocation.provider_id or "provider",
                        attempt_invocation.invocation_id,
                    ),
                )
            elif not isinstance(raw_result, ProviderExecutionResult):
                result = _synthetic_provider_result(
                    attempt_invocation,
                    _failure(
                        FailureCategory.PROVIDER,
                        "INVALID_PROVIDER_RESULT",
                        "provider returned an invalid structured result",
                        refs=(attempt_invocation.invocation_id,),
                    ),
                )
            else:
                result = raw_result
            provider_reported_duration_ms += result.duration_ms
            if not cancelled_during and callable(cancelled) and cancelled():
                result = _synthetic_provider_result(
                    attempt_invocation,
                    _failure(
                        FailureCategory.CANCELLED,
                        "CANCELLED_DURING_PROVIDER",
                        "run cancellation was observed after provider execution",
                        refs=(attempt_invocation.invocation_id,),
                        attempt=result.attempt,
                    ),
                )
            if result.started_at is None or result.ended_at is None:
                result = replace(
                    result,
                    started_at=result.started_at or self.timestamp,
                    ended_at=result.ended_at or self.timestamp,
                )
            if (
                result.provider_id != attempt_invocation.provider_id
                or result.invocation_id != attempt_invocation.invocation_id
            ):
                result = _synthetic_provider_result(
                    attempt_invocation,
                    _failure(
                        FailureCategory.PROVIDER,
                        "PROVIDER_RESULT_CORRELATION",
                        "provider result correlation did not match the invocation",
                        refs=(attempt_invocation.invocation_id,),
                    ),
                )
            if (
                not provider_timed_out
                and not cancelled_during
                and result.status
                in (
                    ProviderResultStatus.SUCCEEDED,
                    ProviderResultStatus.PARTIAL,
                )
                and (result.duration_ms > effective_timeout or elapsed_ms > effective_timeout)
            ):
                result = _synthetic_provider_result(
                    attempt_invocation,
                    _failure(
                        FailureCategory.TIMEOUT,
                        "PROVIDER_TIMEOUT",
                        "provider duration exceeded the invocation timeout",
                        refs=(attempt_invocation.invocation_id,),
                        attempt=result.attempt,
                    ),
                )
            results.append(result)
            if (
                result.status is ProviderResultStatus.FAILED
                and result.failure is not None
                and result.failure.retryable
                and retries < limits.max_retries
            ):
                retries += 1
                attempt_invocation = _with_attempt(attempt_invocation, retries + 1)
                continue
            break

        final = results[-1]
        observed_duration_ms = provider_reported_duration_ms or elapsed_total_ms
        if final.status is ProviderResultStatus.SUCCEEDED and final.output is not None:
            succeeded = transition_invocation(
                attempt_invocation,
                InvocationStatus.SUCCEEDED,
                timestamp=self.timestamp,
            )
            artifact = _artifact(
                succeeded,
                final.output,
                acceptance_refs=succeeded.handoff.acceptance_refs,
                timestamp=self.timestamp,
            )
            final = replace(
                final,
                artifact_refs=(artifact.artifact_id,),
            )
            results[-1] = final
            return _InvocationOutcome(
                succeeded,
                tuple(results),
                artifact,
                None,
                retries,
                final.output,
                observed_duration_ms,
            )
        if final.status is ProviderResultStatus.PARTIAL:
            partial = transition_invocation(
                attempt_invocation,
                InvocationStatus.PARTIAL,
                timestamp=self.timestamp,
            )
            partial_artifact = (
                _artifact(
                    partial,
                    final.output,
                    acceptance_refs=partial.handoff.acceptance_refs,
                    timestamp=self.timestamp,
                    partial=True,
                )
                if final.output is not None
                else None
            )
            if partial_artifact is not None:
                final = replace(final, artifact_refs=(partial_artifact.artifact_id,))
                results[-1] = final
            failure = final.failure or _failure(
                FailureCategory.PROVIDER,
                "PARTIAL_PROVIDER_RESULT",
                "provider returned a partial result",
                refs=(partial.invocation_id,),
            )
            return _InvocationOutcome(
                partial,
                tuple(results),
                partial_artifact,
                failure,
                retries,
                final.output,
                observed_duration_ms,
            )
        failure = final.failure or _failure(
            FailureCategory.PROVIDER,
            "PROVIDER_FAILED",
            "provider returned a failed result",
            refs=(attempt_invocation.invocation_id,),
            attempt=final.attempt,
        )
        target = (
            InvocationStatus.CANCELLED
            if failure.category is FailureCategory.CANCELLED
            else InvocationStatus.TIMED_OUT
            if failure.category is FailureCategory.TIMEOUT
            else InvocationStatus.FAILED
        )
        failed = transition_invocation(
            attempt_invocation,
            target,
            timestamp=self.timestamp,
            failure_refs=(failure.code,),
        )
        return _InvocationOutcome(
            failed,
            tuple(results),
            None,
            failure,
            retries,
            duration_ms=observed_duration_ms,
        )

    def _telemetry(
        self,
        profile: TaskProfile,
        invocation: CapabilityInvocation,
        *,
        invocations: tuple[CapabilityInvocation, ...] = (),
        provider_results: tuple[ProviderExecutionResult, ...],
        artifacts: tuple[ArtifactRecord, ...],
        evidence: tuple[object, ...],
        accepted: bool,
        limits: ExecutionLimits,
        graph: ExecutionGraph | None = None,
        stop_decision: StopDecision | None = None,
        final_status: ExecutionStatus | str | None = None,
        duration_ms: int = 0,
    ) -> tuple[TelemetryLog, tuple[str, ...]]:
        log = TelemetryLog()
        limitations: list[str] = []
        runtime_invocations = invocations or (invocation,)
        runtime_duration_by_invocation: dict[str, int] = {
            item.invocation_id: 0 for item in runtime_invocations
        }
        for provider_result in provider_results:
            runtime_duration_by_invocation[provider_result.invocation_id] = (
                runtime_duration_by_invocation.get(provider_result.invocation_id, 0)
                + provider_result.duration_ms
            )
        evidence_records = tuple(item for item in evidence if isinstance(item, EvidenceRecord))
        evidence_refs = tuple(str(item.evidence_id) for item in evidence_records)
        artifact_refs = tuple(item.artifact_id for item in artifacts)
        valid_runtime_evidence = tuple(
            item
            for item in evidence_records
            if item.procedure.executed
            and _enum_value(item.result) == "PASS"
            and _enum_value(item.freshness.status) == "FRESH"
            and _enum_value(item.evidence_kind) in {"OBSERVATION", "TRACE"}
        )

        def add(
            event_type: TelemetryEventType,
            reason: str,
            *,
            actor: TelemetryActor | None = None,
            event_evidence: tuple[str, ...] = (),
            event_artifacts: tuple[str, ...] = (),
            runtime_evidence: tuple[EvidenceRecord, ...] = (),
            result: object | None = None,
            event_duration_ms: int | None = None,
        ) -> None:
            nonlocal log
            if len(log.events) >= limits.max_telemetry:
                if "telemetry budget truncated events" not in limitations:
                    limitations.append("telemetry budget truncated events")
                return
            payload: dict[str, object] = {"duration_ms": event_duration_ms}
            if result is not None:
                payload["result"] = result
            event_actor = actor or TelemetryActor(
                invocation.callee.capability_id, invocation.invocation_id
            )
            try:
                event = create_event(
                    event_id=f"EVT-{profile.run_id}-{len(log.events) + 1}",
                    event_sequence=len(log.events) + 1,
                    timestamp=self.timestamp,
                    task_id=profile.task_id,
                    run_id=profile.run_id,
                    event_type=event_type,
                    previous_event_digest=log.last_digest,
                    actor=event_actor,
                    reason=reason,
                    payload=payload,
                    artifact_refs=event_artifacts,
                    evidence_refs=event_evidence,
                    runtime_evidence=runtime_evidence,
                    privacy_class=PrivacyClass.INTERNAL,
                )
                log = log.append(event)
            except (TypeError, ValueError):
                limitations.append("telemetry event was rejected by its contract")

        add(
            TelemetryEventType.RUN_CREATED,
            "bounded project-local run created",
            actor=TelemetryActor(None, None),
        )
        add(TelemetryEventType.TASK_RECEIVED, "bounded project-local run received")
        add(TelemetryEventType.TASK_CLASSIFIED, "task profile classified")
        add(TelemetryEventType.ROUTE_SELECTED, "explicit route decision recorded")
        if graph is not None:
            add(TelemetryEventType.GRAPH_CREATED, "validated sequential execution graph recorded")
        for current in runtime_invocations:
            current_actor = TelemetryActor(current.callee.capability_id, current.invocation_id)
            add(
                TelemetryEventType.CAPABILITY_SELECTED,
                "registered provider selected without fallback",
                actor=current_actor,
            )
            if current.started_at is not None:
                add(
                    TelemetryEventType.INVOCATION_STARTED,
                    "invocation entered provider execution",
                    actor=current_actor,
                )
        if valid_runtime_evidence:
            add(
                TelemetryEventType.CAPABILITY_LOADED,
                "registered local provider loaded after runtime evidence was created",
                event_evidence=tuple(item.evidence_id for item in valid_runtime_evidence),
                runtime_evidence=valid_runtime_evidence,
            )
        for provider_result in provider_results:
            current = next(
                (
                    item
                    for item in runtime_invocations
                    if item.invocation_id == provider_result.invocation_id
                ),
                invocation,
            )
            current_actor = TelemetryActor(current.callee.capability_id, current.invocation_id)
            add(
                TelemetryEventType.TOOL_CALLED,
                "provider invocation attempt recorded",
                actor=current_actor,
            )
            if provider_result.attempt > 1:
                add(
                    TelemetryEventType.RETRY,
                    f"bounded provider retry {provider_result.attempt}",
                    actor=current_actor,
                )
            add(
                TelemetryEventType.TOOL_RESULT,
                "structured provider result recorded",
                actor=current_actor,
                event_evidence=evidence_refs,
                event_artifacts=tuple(provider_result.artifact_refs),
                result="PASS"
                if provider_result.status is ProviderResultStatus.SUCCEEDED
                else "FAIL",
                event_duration_ms=provider_result.duration_ms,
            )
        for current in runtime_invocations:
            add(
                TelemetryEventType.INVOCATION_FINISHED,
                "invocation reached an explicit terminal state",
                actor=TelemetryActor(current.callee.capability_id, current.invocation_id),
                event_artifacts=tuple(
                    artifact.artifact_id
                    for artifact in artifacts
                    if artifact.producer.invocation_id == current.invocation_id
                ),
                result=(
                    "PASS" if current.invocation_status is InvocationStatus.SUCCEEDED else "FAIL"
                ),
                event_duration_ms=runtime_duration_by_invocation.get(current.invocation_id, 0),
            )
        add(TelemetryEventType.VERIFICATION_STARTED, "verification procedure started")
        add(
            TelemetryEventType.VALIDATION_RUN if accepted else TelemetryEventType.VALIDATION_FAIL,
            "verification procedure evaluated provider outputs",
            event_evidence=evidence_refs,
            event_artifacts=artifact_refs,
            result="PASS" if accepted else "FAIL",
        )
        add(
            TelemetryEventType.VERIFICATION_FINISHED,
            "verification report finalized",
            event_evidence=evidence_refs,
            event_artifacts=artifact_refs,
            result="PASS" if accepted else "FAIL",
        )
        add(
            TelemetryEventType.CRITIQUE_RUN,
            "critique inspected the verification packet",
            event_evidence=evidence_refs,
        )
        add(
            TelemetryEventType.CRITIQUE_RECORDED,
            "critique record was attached to the run",
            event_evidence=evidence_refs,
        )
        add(
            TelemetryEventType.ASSURANCE_DECIDED,
            "assurance decision evaluated verification and critique",
            event_evidence=evidence_refs,
            result="PASS" if accepted else "FAIL",
        )
        if stop_decision is not None and stop_decision.should_stop:
            add(
                TelemetryEventType.STOP_TRIGGERED,
                stop_decision.reason or "stop policy triggered",
                result="FAIL",
            )
        if accepted:
            add(
                TelemetryEventType.DELIVERY,
                "delivery accepted by assurance",
                event_evidence=evidence_refs,
                event_artifacts=artifact_refs,
                result="PASS",
            )
        add(
            TelemetryEventType.RUN_COMPLETED,
            "run completed with bounded terminal status "
            f"{_enum_value(final_status) if final_status is not None else 'UNKNOWN'}",
            result="PASS" if accepted else "FAIL",
            event_duration_ms=duration_ms,
        )
        return log, tuple(dict.fromkeys(limitations))

    def _assemble_many(
        self,
        profile: TaskProfile,
        route: RouteDecision,
        *,
        outcomes: tuple[_InvocationOutcome, ...],
        verification_outcomes: tuple[_InvocationOutcome, ...] | None,
        graph: ExecutionGraph | None,
        status: ExecutionStatus,
        reported_failures: tuple[FailureDetail, ...],
        authority_snapshot_value: AuthoritySnapshot | None,
        limits: ExecutionLimits,
        persist: bool,
        extra_artifacts: tuple[ArtifactRecord, ...] = (),
        extra_limitations: tuple[str, ...] = (),
        repair_records: tuple[RepairRecord, ...] = (),
        stop_decision: StopDecision | None = None,
    ) -> RunResult:
        """Assemble one immutable run from direct or graph outcomes."""

        if not outcomes:
            raise ValueError("a run must own at least one invocation outcome")
        selected_outcomes = verification_outcomes or outcomes
        packets: list[VerificationOutcome] = []
        for outcome in selected_outcomes:
            failure = outcome.failure or _failure(
                FailureCategory.VALIDATION,
                "NOT_EXECUTED",
                "provider execution was not performed",
                refs=(outcome.invocation.invocation_id,),
            )
            provider_result = (
                outcome.provider_results[-1]
                if outcome.provider_results
                else _synthetic_provider_result(outcome.invocation, failure)
            )
            packets.append(
                verify_provider_result(
                    outcome.invocation,
                    provider_result,
                    outcome.artifact,
                    acceptance_refs=outcome.invocation.handoff.acceptance_refs,
                    timestamp=self.timestamp,
                )
            )
        aggregate = aggregate_verification(
            tuple(packets),
            task_id=profile.task_id,
            run_id=profile.run_id,
            acceptance_refs=(graph.acceptance_refs if graph is not None else ("P2-EXECUTION",)),
            timestamp=self.timestamp,
        )
        evidence = tuple(aggregate.evidence)
        artifacts = tuple(
            dict.fromkeys(
                artifact.artifact_id
                for artifact in (*extra_artifacts, *(item.artifact for item in outcomes))
                if artifact is not None
            )
        )
        artifact_by_id = {
            artifact.artifact_id: artifact
            for artifact in (*extra_artifacts, *(item.artifact for item in outcomes))
            if artifact is not None
        }
        artifact_values = tuple(artifact_by_id[item] for item in artifacts)

        limitations = list(extra_limitations)
        verification = aggregate.report
        if len(evidence) > limits.max_evidence:
            evidence = evidence[: limits.max_evidence]
            limitations.append("evidence budget truncated records")
            budget_failure = _failure(
                FailureCategory.BUDGET,
                "EVIDENCE_BUDGET_EXHAUSTED",
                "maximum evidence budget was exhausted",
                refs=(profile.run_id,),
            )
            reported_failures = (*reported_failures, budget_failure)
            allowed_evidence = {item.evidence_id for item in evidence}
            bounded_claims = tuple(
                replace(
                    claim,
                    status=(
                        ClaimStatus.NOT_RUN
                        if claim.status is ClaimStatus.PASS
                        and not set(claim.evidence_refs).intersection(allowed_evidence)
                        else claim.status
                    ),
                    evidence_refs=tuple(
                        ref for ref in claim.evidence_refs if ref in allowed_evidence
                    ),
                    limitation_refs=(
                        tuple(dict.fromkeys((*claim.limitation_refs, "evidence-budget")))
                        if claim.status is ClaimStatus.PASS
                        and not set(claim.evidence_refs).intersection(allowed_evidence)
                        else claim.limitation_refs
                    ),
                )
                for claim in verification.claims
            )
            bounded_passed = tuple(
                claim.claim_id for claim in bounded_claims if claim.status is ClaimStatus.PASS
            )
            bounded_failed = tuple(
                claim.claim_id for claim in bounded_claims if claim.status is ClaimStatus.FAIL
            )
            bounded_not_run = tuple(
                claim.claim_id for claim in bounded_claims if claim.status is ClaimStatus.NOT_RUN
            )
            bounded_unknown = tuple(
                claim.claim_id for claim in bounded_claims if claim.status is ClaimStatus.UNKNOWN
            )
            required_claims = sum(1 for claim in bounded_claims if claim.required)
            evidenced_claims = sum(
                1
                for claim in bounded_claims
                if claim.required and claim.status is ClaimStatus.PASS and claim.evidence_refs
            )
            verification = replace(
                verification,
                record=replace(
                    verification.record,
                    evidence_refs=tuple(item.evidence_id for item in evidence),
                ),
                claims=bounded_claims,
                procedures=tuple(
                    replace(
                        procedure,
                        evidence_refs=tuple(
                            ref for ref in procedure.evidence_refs if ref in allowed_evidence
                        ),
                    )
                    for procedure in verification.procedures
                ),
                passed=bounded_passed,
                failed=tuple(dict.fromkeys((*verification.failed, *bounded_failed))),
                not_run=tuple(dict.fromkeys((*verification.not_run, *bounded_not_run))),
                unknown=tuple(dict.fromkeys((*verification.unknown, *bounded_unknown))),
                coverage=replace(
                    verification.coverage,
                    required_claims=required_claims,
                    evidenced_claims=evidenced_claims,
                    percentage=(100.0 * evidenced_claims / required_claims)
                    if required_claims
                    else 0.0,
                ),
                confidence=verification.confidence,
                blockers=tuple(dict.fromkeys((*verification.blockers, "evidence-budget"))),
                recommendation=Recommendation.FAIL,
                limitations=tuple(
                    dict.fromkeys((*verification.limitations, "evidence budget truncated records"))
                ),
            )

        artifact_ids = {artifact.artifact_id for artifact in artifact_values}
        lineage_valid = all(
            item.task_id == profile.task_id
            and item.run_id == profile.run_id
            and item.owner.strip()
            and set(item.artifact_refs).issubset(artifact_ids)
            and item.evidence_id in item.record.evidence_refs
            for item in evidence
            if isinstance(item, EvidenceRecord)
        )
        lineage_validation = validate_evidence_links(
            verification.claims,
            verification.procedures,
            tuple(item for item in evidence if isinstance(item, EvidenceRecord)),
        )
        if not lineage_valid or not lineage_validation.is_valid:
            lineage_failure = _failure(
                FailureCategory.VERIFICATION,
                "EVIDENCE_LINEAGE_INVALID",
                "evidence lineage did not match the current run and artifact set",
                refs=tuple(finding.path for finding in lineage_validation.findings)[:16],
            )
            reported_failures = (*reported_failures, lineage_failure)
            limitations.append("evidence lineage failed the integrated verification gate")
            verification = replace(
                verification,
                record=replace(verification.record, status=RecordStatus.INVALID),
                passed=(),
                failed=tuple(
                    dict.fromkeys(
                        (*verification.failed, *(claim.claim_id for claim in verification.claims))
                    )
                ),
                coverage=replace(verification.coverage, evidenced_claims=0, percentage=0.0),
                confidence=Confidence.LOW,
                blockers=tuple(dict.fromkeys((*verification.blockers, "evidence-lineage"))),
                recommendation=Recommendation.FAIL,
                limitations=tuple(
                    dict.fromkeys(
                        (*verification.limitations, "evidence lineage failed integrated validation")
                    )
                ),
            )

        critique = create_critique(
            verification,
            reviewer_id="local.critic",
            independence=Independence.SEPARATED_SELF,
            timestamp=self.timestamp,
        )
        assurance = assure_quality(verification, critique)
        quality = build_quality_report(
            verification,
            critique,
            assurance,
            timestamp=self.timestamp,
        )
        failure_values = list(reported_failures)
        selected_ids = {item.invocation.invocation_id for item in selected_outcomes}
        for outcome in outcomes:
            if outcome.invocation.invocation_id in selected_ids and outcome.failure is not None:
                failure_values.append(outcome.failure)
        if aggregate.failure is not None:
            failure_values.append(aggregate.failure)
        unique_failures: list[FailureDetail] = []
        seen_failures: set[tuple[object, str, str, tuple[str, ...]]] = set()
        for failure in failure_values:
            key = (failure.category, failure.code, failure.message, failure.refs)
            if key not in seen_failures:
                seen_failures.add(key)
                unique_failures.append(failure)
        normalized_failures = tuple(unique_failures)
        if (
            status is ExecutionStatus.SUCCEEDED
            and assurance.decision is not AssuranceDecision.QUALITY_ACCEPTED
        ):
            status = ExecutionStatus.FAILED
        if status is ExecutionStatus.SUCCEEDED and any(
            failure.category is FailureCategory.BUDGET for failure in normalized_failures
        ):
            status = ExecutionStatus.BLOCKED
        provider_results = tuple(
            result for outcome in outcomes for result in outcome.provider_results
        )
        duration_ms = sum(outcome.duration_ms for outcome in outcomes)
        invocations = tuple(outcome.invocation for outcome in outcomes)
        retries = sum(outcome.retries for outcome in outcomes)
        telemetry, telemetry_limitations = self._telemetry(
            profile,
            invocations[0],
            invocations=invocations,
            provider_results=provider_results,
            artifacts=artifact_values,
            evidence=evidence,
            accepted=assurance.decision is AssuranceDecision.QUALITY_ACCEPTED,
            limits=limits,
            graph=graph,
            stop_decision=stop_decision,
            final_status=status,
            duration_ms=duration_ms,
        )
        all_limitations = tuple(
            dict.fromkeys((*limitations, *verification.limitations, *telemetry_limitations))
        )
        summary = self._summary(
            profile,
            route,
            graph,
            invocations,
            artifact_values,
            evidence,
            verification,
            critique,
            quality,
            status,
            normalized_failures,
            retries,
            all_limitations,
            duration_ms,
        )
        result = RunResult(
            status=status,
            profile=profile,
            route=route,
            graph=graph,
            invocations=invocations,
            provider_results=provider_results,
            artifacts=artifact_values,
            evidence=evidence,
            verification=verification,
            critique=critique,
            assurance=assurance,
            quality=quality,
            summary=summary,
            telemetry=telemetry,
            failures=normalized_failures,
            authority_snapshot=authority_snapshot_value,
            limitations=all_limitations,
            verification_reports=(verification,),
            critiques=(critique,),
            assurances=(assurance,),
            quality_reports=(quality,),
            repair_records=repair_records,
            stop_decision=stop_decision,
        )
        if persist:
            self._persist(result)
        return result

    def _assemble(
        self,
        profile: TaskProfile,
        route: RouteDecision,
        invocation: CapabilityInvocation,
        *,
        outcome: _InvocationOutcome,
        graph: ExecutionGraph | None,
        status: ExecutionStatus,
        reported_failures: tuple[FailureDetail, ...],
        authority_snapshot_value: AuthoritySnapshot | None,
        limits: ExecutionLimits,
        persist: bool,
        extra_artifacts: tuple[ArtifactRecord, ...] = (),
        extra_limitations: tuple[str, ...] = (),
    ) -> RunResult:
        del invocation
        return self._assemble_many(
            profile,
            route,
            outcomes=(outcome,),
            verification_outcomes=None,
            graph=graph,
            status=status,
            reported_failures=reported_failures,
            authority_snapshot_value=authority_snapshot_value,
            limits=limits,
            persist=persist,
            extra_artifacts=extra_artifacts,
            extra_limitations=extra_limitations,
        )

    def _summary(
        self,
        profile: TaskProfile,
        route: RouteDecision,
        graph: ExecutionGraph | None,
        invocations: tuple[CapabilityInvocation, ...],
        artifacts: tuple[ArtifactRecord, ...],
        evidence: tuple[object, ...],
        verification: VerificationReport,
        critique: object,
        quality: QualityReport,
        status: ExecutionStatus,
        failures: tuple[FailureDetail, ...],
        retries: int,
        limitations: tuple[str, ...],
        duration_ms: int,
    ) -> RunSummary:
        accepted = status is ExecutionStatus.SUCCEEDED and not failures
        lifecycle = (
            LifecycleState.DELIVERED
            if accepted
            else {
                ExecutionStatus.CANCELLED: LifecycleState.CANCELLED,
                ExecutionStatus.BLOCKED: LifecycleState.BLOCKED,
                ExecutionStatus.STOPPED: LifecycleState.BLOCKED,
                ExecutionStatus.TIMED_OUT: LifecycleState.BLOCKED,
                ExecutionStatus.DRY_RUN: LifecycleState.ROUTED,
                ExecutionStatus.PARTIAL: LifecycleState.PARTIAL,
            }.get(status, LifecycleState.FAILED)
        )
        artifact_ref = artifacts[0].artifact_id if accepted and artifacts else None
        evidence_refs = tuple(
            str(item.evidence_id) for item in evidence if isinstance(item, EvidenceRecord)
        )
        failed = () if accepted else ("P2-EXECUTION",)
        blocked = tuple(
            dict.fromkeys(
                (
                    *(
                        ("AUTHORITY",)
                        if any(
                            failure.category is FailureCategory.AUTHORITY_DENIED
                            for failure in failures
                        )
                        else ()
                    ),
                    *(
                        failure.code
                        for failure in failures
                        if failure.category
                        in {
                            FailureCategory.DEPENDENCY_FAILED,
                            FailureCategory.BUDGET,
                        }
                    ),
                )
            )
        )
        delivery_status = (
            DeliveryStatus.DELIVERED_WITH_LIMITATIONS
            if accepted and limitations
            else DeliveryStatus.DELIVERED
            if accepted
            else DeliveryStatus.NOT_DELIVERED
            if status is ExecutionStatus.DRY_RUN
            else DeliveryStatus.BLOCKED
        )
        return RunSummary(
            schema_version=SchemaVersion.RUN_SUMMARY,
            summary_id=f"SUMMARY-{profile.run_id}",
            task_id=profile.task_id,
            run_id=profile.run_id,
            record=replace(_record(self.timestamp), evidence_refs=evidence_refs),
            lifecycle_state=lifecycle,
            route_ref=route.decision_id,
            profile_ref=f"{profile.task_id}@{_enum_value(profile.schema_version)}",
            graph_ref=graph.graph_id if graph is not None else None,
            selected_capabilities=tuple(item.capability_id for item in route.selected),
            loaded_capabilities=tuple(
                dict.fromkeys(
                    invocation.provider_id
                    for invocation in invocations
                    if invocation.started_at and invocation.provider_id is not None
                )
            ),
            artifacts=tuple(item.artifact_id for item in artifacts),
            evidence=evidence_refs,
            verification_ref=verification.report_id,
            critique_ref=str(getattr(critique, "report_id", "")) or None,
            quality_ref=quality.report_id,
            gate_summary=GateSummary(
                passed=tuple(verification.passed) if accepted else (),
                failed=tuple(dict.fromkeys((*failed, *verification.failed))),
                not_run=tuple(dict.fromkeys((*verification.not_run, *verification.unknown))),
                blocked=tuple(dict.fromkeys((*blocked, *verification.blockers))),
            ),
            execution=ExecutionSummary(
                started_at=self.timestamp,
                completed_at=self.timestamp,
                duration_ms=duration_ms,
                retries=retries,
                stop_reason=failures[0].code if failures else None,
            ),
            resource_usage=ResourceUsage(
                token_estimate=None,
                cost_estimate=None,
                tool_calls=sum(1 for invocation in invocations if invocation.started_at),
                parallel_lanes=1,
            ),
            delivery=Delivery(
                delivery_status, artifact_ref, "local.assurance" if accepted else None
            ),
            limitations=limitations,
            open_questions=tuple(profile.classification_trace.unresolved),
            confidence=profile.confidence,
            created_at=self.timestamp,
            residual_risk=(
                ResidualRisk.HIGH
                if failures
                else ResidualRisk.MEDIUM
                if limitations
                else ResidualRisk.LOW
            ),
        )

    def _persist(self, result: RunResult) -> None:
        output_by_invocation = {
            item.invocation_id: item.output
            for item in result.provider_results
            if item.output is not None
        }
        for artifact in result.artifacts:
            producer_id = artifact.producer.invocation_id
            if producer_id is not None and producer_id in output_by_invocation:
                self.store.write_artifact(artifact, output_by_invocation[producer_id])
        self.store.write_artifact_records(
            result.summary.run_id,
            tuple(to_dict(item) for item in result.artifacts),
        )
        self.store.write_evidence(
            result.summary.run_id,
            tuple(to_dict(item) for item in result.evidence if isinstance(item, EvidenceRecord)),
        )
        telemetry_failed = False
        for event in result.telemetry.events:
            try:
                self.store.append_telemetry(result.summary.run_id, to_dict(event))
            except ValueError:
                telemetry_failed = True
                break
        if telemetry_failed:
            with suppress(ValueError):
                self.store.write_diagnostic(
                    result.summary.run_id,
                    "telemetry",
                    "TELEMETRY_PERSISTENCE_FAILED",
                )
        lifecycle_failed = False
        for invocation in result.invocations:
            try:
                self.store.append_lifecycle(
                    result.summary.run_id,
                    {
                        "event_id": f"LIFECYCLE-{invocation.invocation_id}",
                        "run_id": result.summary.run_id,
                        "task_id": invocation.task_id,
                        "invocation_id": invocation.invocation_id,
                        "graph_node_id": invocation.graph_node_id,
                        "status": _enum_value(invocation.invocation_status),
                        "started_at": invocation.started_at,
                        "completed_at": invocation.completed_at,
                        "authority_snapshot_ref": invocation.authority_snapshot_ref,
                        "repair_of": invocation.repair_of,
                    },
                )
            except ValueError:
                lifecycle_failed = True
                break
        if lifecycle_failed:
            with suppress(ValueError):
                self.store.write_diagnostic(
                    result.summary.run_id,
                    "lifecycle",
                    "LIFECYCLE_PERSISTENCE_FAILED",
                )
        self.store.write_summary(result.summary)

    def _snapshot_for(
        self,
        authority: AuthorityScope | None,
        invocations: tuple[CapabilityInvocation | _InvocationOutcome, ...],
    ) -> AuthoritySnapshot | None:
        if authority is None:
            return None
        for item in invocations:
            invocation = item.invocation if isinstance(item, _InvocationOutcome) else item
            if invocation.authority_snapshot_ref is not None:
                return authority_snapshot(
                    authority,
                    subject_id=invocation.invocation_id,
                    operation=invocation.operation,
                    authority_id=f"AUTH-{invocation.invocation_id}",
                    required_scope=invocation.scope,
                )
        return None

    def _run_graph(
        self,
        profile: TaskProfile,
        route: RouteDecision,
        graph: ExecutionGraph,
        *,
        authority: AuthorityScope | None,
        limits: ExecutionLimits,
        conditions: tuple[str, ...],
        cancelled: bool | Callable[[], bool],
        timeout_ms: int | None,
        delegation_ref: str | None,
        dry_run: bool,
        stop_before_run: bool,
        persist: bool,
    ) -> RunResult:
        """Validate, schedule, and aggregate a deterministic sequential DAG."""

        indexed = {node.node_id: node for node in graph.nodes}
        invocation_by_node = {
            node.node_id: _build_invocation(
                profile,
                invocation_id=f"INV-{profile.run_id}-{node.node_id}",
                capability_id=node.capability_id,
                provider_id=node.provider_id
                or (route.selected[0].capability_id if route.selected else ""),
                graph_node_id=node.node_id,
                acceptance_refs=node.acceptance_refs or graph.acceptance_refs,
                output_contract=node.output_contract,
                limits=limits,
                timestamp=self.timestamp,
                dependencies=tuple(
                    dict.fromkeys(
                        (
                            *node.depends_on,
                            *(
                                edge.from_node
                                for edge in graph.edges
                                if edge.to_node == node.node_id
                            ),
                        )
                    )
                ),
                delegation_ref=delegation_ref,
            )
            for node in graph.nodes
        }
        if authority is None:
            reference_invocation = next(iter(invocation_by_node.values()), None)
            if reference_invocation is None:
                selected_capability = (
                    route.selected[0].capability_id if route.selected else "orchestrator"
                )
                reference_invocation = _build_invocation(
                    profile,
                    invocation_id=f"INV-{profile.run_id}-GRAPH",
                    capability_id=selected_capability,
                    provider_id=selected_capability,
                    graph_node_id=None,
                    acceptance_refs=graph.acceptance_refs,
                    output_contract="GraphValidationResult",
                    limits=limits,
                    timestamp=self.timestamp,
                )
            authority_failure = _authority_required_failure(reference_invocation)
            denied_outcomes = tuple(
                _authority_denied_outcome(invocation, timestamp=self.timestamp)
                for invocation in invocation_by_node.values()
            )
            graph_value = replace(graph, graph_status=GraphStatus.BLOCKED)
            return self._assemble_many(
                profile,
                route,
                outcomes=denied_outcomes,
                verification_outcomes=None,
                graph=graph_value,
                status=ExecutionStatus.FAILED,
                reported_failures=(authority_failure,),
                authority_snapshot_value=None,
                limits=limits,
                persist=persist,
                extra_limitations=("graph rejected before provider execution",),
            )
        validation = validate_execution_graph(
            graph,
            max_nodes=limits.max_nodes,
            authority=authority,
            required_conditions=conditions,
        )
        if graph.task_id != profile.task_id or graph.run_id != profile.run_id:
            validation = replace(
                validation,
                valid=False,
                findings=(
                    *validation.findings,
                    ValidationFinding(
                        ValidationCode.INVARIANT_VIOLATION,
                        "graph identity does not match the run profile",
                        "$.graph_id",
                    ),
                ),
            )
        if not validation.is_valid:
            failure = _failure(
                FailureCategory.VALIDATION,
                "GRAPH_VALIDATION_FAILED",
                "execution graph failed preflight validation",
                refs=tuple(f"{item.code.value}:{item.path}" for item in validation.findings)[:16],
            )
            invalid_outcomes = tuple(
                _InvocationOutcome(
                    _terminal_without_execution(
                        invocation,
                        InvocationStatus.BLOCKED,
                        failure,
                        timestamp=self.timestamp,
                    ),
                    (),
                    None,
                    failure,
                    0,
                )
                for invocation in invocation_by_node.values()
            )
            graph_value = replace(graph, graph_status=GraphStatus.BLOCKED)
            return self._assemble_many(
                profile,
                route,
                outcomes=invalid_outcomes
                or (
                    _InvocationOutcome(
                        _terminal_without_execution(
                            _build_invocation(
                                profile,
                                invocation_id=f"INV-{profile.run_id}-GRAPH",
                                capability_id=route.selected[0].capability_id,
                                provider_id=route.selected[0].capability_id,
                                graph_node_id=None,
                                acceptance_refs=graph.acceptance_refs,
                                output_contract="GraphValidationResult",
                                limits=limits,
                                timestamp=self.timestamp,
                            ),
                            InvocationStatus.BLOCKED,
                            failure,
                            timestamp=self.timestamp,
                        ),
                        (),
                        None,
                        failure,
                        0,
                    ),
                ),
                verification_outcomes=None,
                graph=graph_value,
                status=ExecutionStatus.FAILED,
                reported_failures=(failure,),
                authority_snapshot_value=None,
                limits=limits,
                persist=persist,
                extra_limitations=("graph rejected before provider execution",),
            )
        if dry_run or stop_before_run:
            dry = dry_run
            dry_outcomes: list[_InvocationOutcome] = []
            for invocation in invocation_by_node.values():
                if dry:
                    prepared = transition_invocation(
                        invocation, InvocationStatus.VALIDATED, timestamp=self.timestamp
                    )
                    prepared = transition_invocation(
                        prepared, InvocationStatus.AUTHORIZED, timestamp=self.timestamp
                    )
                    prepared = transition_invocation(
                        prepared, InvocationStatus.READY, timestamp=self.timestamp
                    )
                    failure = _failure(
                        FailureCategory.VALIDATION,
                        "DRY_RUN_NOT_EXECUTED",
                        "dry-run produced a graph plan without invoking providers",
                        refs=(invocation.invocation_id,),
                    )
                    dry_outcomes.append(_InvocationOutcome(prepared, (), None, failure, 0))
                else:
                    failure = _failure(
                        FailureCategory.CANCELLED,
                        "STOP_BEFORE_RUN",
                        "stop policy prevented graph provider execution",
                        refs=(invocation.invocation_id,),
                    )
                    dry_outcomes.append(
                        _InvocationOutcome(
                            _terminal_without_execution(
                                invocation,
                                InvocationStatus.BLOCKED,
                                failure,
                                timestamp=self.timestamp,
                            ),
                            (),
                            None,
                            failure,
                            0,
                        )
                    )
            graph_value = replace(
                graph,
                graph_status=GraphStatus.READY if dry else GraphStatus.BLOCKED,
            )
            return self._assemble_many(
                profile,
                route,
                outcomes=tuple(dry_outcomes),
                verification_outcomes=None,
                graph=graph_value,
                status=ExecutionStatus.DRY_RUN if dry else ExecutionStatus.STOPPED,
                reported_failures=(),
                authority_snapshot_value=None,
                limits=limits,
                persist=persist,
            )

        captured: dict[str, _InvocationOutcome] = {}

        def invoke(node: object) -> object:
            if not hasattr(node, "node_id"):
                raise TypeError("graph scheduler returned an invalid node")
            graph_node = indexed[str(node.node_id)]
            node_timeout = timeout_ms if timeout_ms is not None else limits.timeout_ms
            if graph_node.budget.duration_ms is not None:
                node_timeout = min(node_timeout, graph_node.budget.duration_ms)
            outcome = self._execute_one(
                invocation_by_node[graph_node.node_id],
                authority=authority,
                limits=limits,
                invocation_count=len(captured),
                required_conditions=conditions,
                cancelled=cancelled,
                timeout_ms=node_timeout,
            )
            captured[graph_node.node_id] = outcome
            return GraphNodeResult(
                graph_node.node_id,
                outcome.invocation.invocation_status,
                value=outcome.output,
                failure=outcome.failure,
            )

        try:
            node_results = execute_graph(
                graph,
                invoke,
                max_nodes=limits.max_nodes,
                max_invocations=limits.max_invocations,
                max_duration_ms=limits.max_duration_ms,
                cancelled=cancelled,
            )
        except GraphValidationError:
            # The same validation was performed above; this is a defensive
            # boundary for a scheduler that observes a changed graph object.
            failure = _failure(
                FailureCategory.VALIDATION,
                "GRAPH_SCHEDULER_REJECTED",
                "graph scheduler rejected the validated graph",
                refs=(graph.graph_id,),
            )
            outcomes = tuple(
                _InvocationOutcome(
                    _terminal_without_execution(
                        invocation,
                        InvocationStatus.BLOCKED,
                        failure,
                        timestamp=self.timestamp,
                    ),
                    (),
                    None,
                    failure,
                    0,
                )
                for invocation in invocation_by_node.values()
            )
            graph_value = replace(graph, graph_status=GraphStatus.BLOCKED)
            return self._assemble_many(
                profile,
                route,
                outcomes=outcomes,
                verification_outcomes=None,
                graph=graph_value,
                status=ExecutionStatus.FAILED,
                reported_failures=(failure,),
                authority_snapshot_value=None,
                limits=limits,
                persist=persist,
            )

        outcomes_list: list[_InvocationOutcome] = []
        for node_result in node_results:
            captured_outcome = captured.get(node_result.node_id)
            if captured_outcome is not None:
                outcomes_list.append(captured_outcome)
                continue
            failure = node_result.failure or _failure(
                FailureCategory.DEPENDENCY_FAILED
                if node_result.status is InvocationStatus.BLOCKED
                else FailureCategory.CANCELLED
                if node_result.status is InvocationStatus.CANCELLED
                else FailureCategory.TIMEOUT
                if node_result.status is InvocationStatus.TIMED_OUT
                else FailureCategory.BUDGET,
                "GRAPH_NODE_NOT_EXECUTED",
                "graph node was not executed after scheduler preflight",
                refs=(node_result.node_id, *node_result.blocked_by),
            )
            outcomes_list.append(
                _InvocationOutcome(
                    _terminal_without_execution(
                        invocation_by_node[node_result.node_id],
                        node_result.status,
                        failure,
                        timestamp=self.timestamp,
                    ),
                    (),
                    None,
                    failure,
                    0,
                )
            )
        scheduled_outcomes = tuple(outcomes_list)
        statuses = tuple(item.invocation.invocation_status for item in scheduled_outcomes)
        if all(status is InvocationStatus.SUCCEEDED for status in statuses):
            graph_status = GraphStatus.COMPLETED
            execution_status = ExecutionStatus.SUCCEEDED
        elif any(status is InvocationStatus.CANCELLED for status in statuses):
            graph_status = GraphStatus.CANCELLED
            execution_status = ExecutionStatus.CANCELLED
        elif any(status is InvocationStatus.BLOCKED for status in statuses):
            graph_status = GraphStatus.BLOCKED
            execution_status = ExecutionStatus.BLOCKED
        elif any(status is InvocationStatus.TIMED_OUT for status in statuses):
            graph_status = GraphStatus.PARTIAL
            execution_status = ExecutionStatus.TIMED_OUT
        elif any(status is InvocationStatus.PARTIAL for status in statuses) or any(
            status is InvocationStatus.SUCCEEDED for status in statuses
        ):
            graph_status = GraphStatus.PARTIAL
            execution_status = ExecutionStatus.PARTIAL
        else:
            graph_status = GraphStatus.PARTIAL
            execution_status = ExecutionStatus.FAILED
        outcomes_by_node = {item.invocation.graph_node_id: item for item in scheduled_outcomes}

        def node_artifact_refs(node_id: str) -> tuple[str, ...]:
            artifact = outcomes_by_node[node_id].artifact
            return (artifact.artifact_id,) if artifact is not None else ()

        graph_nodes = tuple(
            replace(
                node,
                node_status=outcomes_by_node[node.node_id].invocation.invocation_status,
                invocation_ref=outcomes_by_node[node.node_id].invocation.invocation_id,
                artifact_refs=node_artifact_refs(node.node_id),
            )
            for node in graph.nodes
        )
        graph_value = replace(graph, nodes=graph_nodes, graph_status=graph_status)
        stop = evaluate_stop(
            budget=StopBudget(max_duration_ms=limits.max_duration_ms),
            usage=BudgetUsage(
                iterations=1,
                duration_ms=0,
                tool_calls=len(captured),
            ),
            blocked_dependencies=tuple(
                item.invocation.graph_node_id or ""
                for item in scheduled_outcomes
                if item.failure is not None
                and item.failure.category is FailureCategory.DEPENDENCY_FAILED
            ),
        )
        return self._assemble_many(
            profile,
            route,
            outcomes=scheduled_outcomes,
            verification_outcomes=None,
            graph=graph_value,
            status=execution_status,
            reported_failures=(),
            authority_snapshot_value=self._snapshot_for(authority, scheduled_outcomes),
            limits=limits,
            persist=persist,
            stop_decision=stop if stop.should_stop else None,
        )

    def _run_direct(
        self,
        profile: TaskProfile,
        route: RouteDecision,
        *,
        provider_id: str,
        authority: AuthorityScope | None,
        limits: ExecutionLimits,
        conditions: tuple[str, ...],
        dry_run: bool,
        stop_before_run: bool,
        cancelled: bool | Callable[[], bool],
        timeout_ms: int | None,
        delegation_ref: str | None,
        repair_provider_id: str | None,
        persist: bool,
    ) -> RunResult:
        invocation = _build_invocation(
            profile,
            invocation_id=f"INV-{profile.run_id}",
            capability_id=provider_id,
            provider_id=provider_id,
            graph_node_id=None,
            acceptance_refs=("P2-EXECUTION",),
            output_contract="LocalExecutionResult",
            limits=limits,
            timestamp=self.timestamp,
            delegation_ref=delegation_ref,
        )
        if authority is None:
            outcome = _authority_denied_outcome(invocation, timestamp=self.timestamp)
            failure = outcome.failure
            assert failure is not None
            return self._assemble_many(
                profile,
                route,
                outcomes=(outcome,),
                verification_outcomes=None,
                graph=None,
                status=ExecutionStatus.FAILED,
                reported_failures=(failure,),
                authority_snapshot_value=None,
                limits=limits,
                persist=persist,
            )
        stop = evaluate_stop(
            budget=StopBudget(
                max_duration_ms=limits.max_duration_ms,
                max_tool_calls=limits.max_invocations,
            ),
            usage=BudgetUsage(),
            human_override=stop_before_run,
        )
        if dry_run:
            prepared = transition_invocation(
                invocation, InvocationStatus.VALIDATED, timestamp=self.timestamp
            )
            prepared = transition_invocation(
                prepared, InvocationStatus.AUTHORIZED, timestamp=self.timestamp
            )
            prepared = transition_invocation(
                prepared, InvocationStatus.READY, timestamp=self.timestamp
            )
            failure = _failure(
                FailureCategory.VALIDATION,
                "DRY_RUN_NOT_EXECUTED",
                "dry-run produced a route without invoking a provider",
                refs=(prepared.invocation_id,),
            )
            outcome = _InvocationOutcome(prepared, (), None, failure, 0)
            return self._assemble_many(
                profile,
                route,
                outcomes=(outcome,),
                verification_outcomes=None,
                graph=None,
                status=ExecutionStatus.DRY_RUN,
                reported_failures=(),
                authority_snapshot_value=None,
                limits=limits,
                persist=persist,
                stop_decision=None,
            )
        if stop_before_run:
            failure = _failure(
                FailureCategory.CANCELLED,
                "STOP_BEFORE_RUN",
                "stop policy prevented provider execution",
                refs=(invocation.invocation_id,),
            )
            prepared = _terminal_without_execution(
                invocation,
                InvocationStatus.BLOCKED,
                failure,
                timestamp=self.timestamp,
            )
            outcome = _InvocationOutcome(prepared, (), None, failure, 0)
            return self._assemble_many(
                profile,
                route,
                outcomes=(outcome,),
                verification_outcomes=None,
                graph=None,
                status=ExecutionStatus.STOPPED,
                reported_failures=(),
                authority_snapshot_value=None,
                limits=limits,
                persist=persist,
                stop_decision=stop,
            )
        outcome = self._execute_one(
            invocation,
            authority=authority,
            limits=limits,
            invocation_count=0,
            required_conditions=conditions,
            cancelled=cancelled,
            timeout_ms=timeout_ms,
        )
        outcome_values: list[_InvocationOutcome] = [outcome]
        verification_outcomes: tuple[_InvocationOutcome, ...] | None = None
        repair_records: list[RepairRecord] = []
        limitations: list[str] = []
        final_status = _status_for_outcome(outcome)
        if outcome.failure is not None and repair_provider_id is not None:
            if limits.max_repairs < 1:
                limitations.append("repair provider supplied but repair budget is zero")
            elif outcome.failure.category not in {
                FailureCategory.AUTHORITY_DENIED,
                FailureCategory.CANCELLED,
                FailureCategory.TIMEOUT,
                FailureCategory.BUDGET,
            }:
                repair_scope = (f"task:{profile.task_id}", f"capability:{repair_provider_id}")
                repair_authority = (
                    check_decision(
                        authority,
                        AuthorityAction.REPLAN,
                        required_scope=repair_scope,
                    )
                    if authority is not None
                    else None
                )
                trigger_refs = tuple(
                    dict.fromkeys((*outcome.invocation.failure_refs, outcome.failure.code))
                )
                if repair_authority is not None and repair_authority.allowed:
                    for attempt in range(1, limits.max_repairs + 1):
                        repair_id = f"INV-{profile.run_id}-REPAIR-{attempt}"
                        repair_invocation = _build_invocation(
                            profile,
                            invocation_id=repair_id,
                            capability_id=repair_provider_id,
                            provider_id=repair_provider_id,
                            graph_node_id=None,
                            acceptance_refs=("P2-EXECUTION",),
                            output_contract="LocalExecutionResult",
                            limits=limits,
                            timestamp=self.timestamp,
                            repair_of=outcome.invocation.invocation_id,
                            repair_trigger_refs=trigger_refs,
                            delegation_ref=delegation_ref,
                        )
                        repaired = self._execute_one(
                            repair_invocation,
                            authority=authority,
                            limits=limits,
                            invocation_count=len(outcome_values),
                            required_conditions=conditions,
                            cancelled=cancelled,
                            timeout_ms=timeout_ms,
                        )
                        outcome_values.append(repaired)
                        final_status = _status_for_outcome(repaired)
                        repair_records.append(
                            RepairRecord(
                                repair_id=f"REPAIR-{profile.run_id}-{attempt}",
                                repairs_invocation_id=outcome.invocation.invocation_id,
                                repair_invocation_id=repaired.invocation.invocation_id,
                                trigger_refs=trigger_refs,
                                status=final_status,
                                attempt=attempt,
                                failure_code=repaired.failure.code if repaired.failure else None,
                            )
                        )
                        if repaired.failure is None:
                            limitations.append(
                                "initial provider failure was resolved by explicit repair"
                            )
                            break
                        if repaired.failure.category in {
                            FailureCategory.AUTHORITY_DENIED,
                            FailureCategory.CANCELLED,
                            FailureCategory.TIMEOUT,
                            FailureCategory.BUDGET,
                        }:
                            limitations.append("explicit repair stopped at a terminal boundary")
                            break
                    else:
                        limitations.append("explicit repair budget was exhausted")
                    verification_outcomes = (outcome_values[-1],)
                else:
                    repair_id = f"INV-{profile.run_id}-REPAIR-1"
                    repair_authority_code = (
                        repair_authority.code
                        if repair_authority is not None
                        else "AUTHORITY_REQUIRED"
                    )
                    limitations.append(f"repair authority denied: {repair_authority_code}")
                    repair_records.append(
                        RepairRecord(
                            repair_id=f"REPAIR-{profile.run_id}-1",
                            repairs_invocation_id=outcome.invocation.invocation_id,
                            repair_invocation_id=repair_id,
                            trigger_refs=trigger_refs,
                            status=ExecutionStatus.BLOCKED,
                            attempt=1,
                            failure_code=repair_authority_code,
                        )
                    )
        outcomes = tuple(outcome_values)
        snapshot = self._snapshot_for(authority, tuple(outcomes))
        if final_status is ExecutionStatus.SUCCEEDED and not limitations:
            stop_after = evaluate_stop(
                budget=StopBudget(max_duration_ms=limits.max_duration_ms),
                usage=BudgetUsage(iterations=1, tool_calls=len(outcome.provider_results)),
                required_passed=True,
                current_evidence=True,
                artifact_integrated=True,
                residual_risk_acceptable=True,
            )
            stop = stop_after if stop_after.should_stop else stop
        return self._assemble_many(
            profile,
            route,
            outcomes=outcomes,
            verification_outcomes=verification_outcomes,
            graph=None,
            status=final_status,
            reported_failures=(),
            authority_snapshot_value=snapshot,
            limits=limits,
            persist=persist,
            extra_limitations=tuple(limitations),
            repair_records=tuple(repair_records),
            stop_decision=stop if stop.should_stop else None,
        )

    def run(
        self,
        objective: str | TaskProfile | Mapping[str, object],
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        requested_outcome: str = "",
        provider_id: str | None = None,
        graph: ExecutionGraph | None = None,
        authority: AuthorityScope | None = None,
        limits: ExecutionLimits | None = None,
        dry_run: bool = False,
        stop_before_run: bool = False,
        cancelled: bool | Callable[[], bool] = False,
        timeout_ms: int | None = None,
        delegation_ref: str | None = None,
        persist: bool = False,
        required_conditions: Iterable[str] = (),
        repair_provider_id: str | None = None,
        max_repairs: int | None = None,
    ) -> RunResult:
        """Run a bounded direct invocation or a validated sequential graph."""

        selected_limits = limits or ExecutionLimits()
        if authority is not None and not isinstance(authority, AuthorityScope):
            raise TypeError("run authority must be an AuthorityScope")
        if max_repairs is not None:
            if not isinstance(max_repairs, int) or isinstance(max_repairs, bool) or max_repairs < 0:
                raise ValueError("max_repairs must be a non-negative integer or null")
            selected_limits = replace(selected_limits, max_repairs=max_repairs)
        if timeout_ms is not None and (
            not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms < 0
        ):
            raise ValueError("timeout must be a non-negative integer or null")
        if repair_provider_id is not None:
            _id(repair_provider_id, "repair provider id")
        if delegation_ref is not None:
            _id(delegation_ref, "delegation reference")
        graph_task_id = graph.task_id if graph is not None and task_id is None else task_id
        graph_run_id = graph.run_id if graph is not None and run_id is None else run_id
        profile = self._profile(
            objective,
            task_id=graph_task_id,
            run_id=graph_run_id,
            requested_outcome=requested_outcome,
        )
        graph_provider = (
            next(
                (
                    node.provider_id
                    for node in graph.nodes
                    if node.provider_id is not None and node.provider_id.strip()
                ),
                None,
            )
            if graph is not None
            else None
        )
        selected_provider = provider_id or graph_provider or "local.success"
        _id(selected_provider, "provider id")
        provider_admitted = (
            self.providers.resolve(
                selected_provider,
                operation="execute",
                capability_id=selected_provider,
            )
            is not None
        )
        route = _route_with_provider(
            minimum_route(
                profile,
                self.registry,
                explicit_provider=selected_provider,
                authority_ref=f"AUTH-ROUTE-{profile.task_id}",
            ),
            selected_provider,
            provider_admitted=provider_admitted,
        )
        conditions = _dedupe(required_conditions)
        authority_value = authority if authority is not None else self.authority
        if graph is not None:
            return self._run_graph(
                profile,
                route,
                graph,
                authority=authority_value,
                limits=selected_limits,
                conditions=conditions,
                cancelled=cancelled,
                timeout_ms=timeout_ms,
                delegation_ref=delegation_ref,
                dry_run=dry_run,
                stop_before_run=stop_before_run,
                persist=persist,
            )
        return self._run_direct(
            profile,
            route,
            provider_id=selected_provider,
            authority=authority_value,
            limits=selected_limits,
            conditions=conditions,
            dry_run=dry_run,
            stop_before_run=stop_before_run,
            cancelled=cancelled,
            timeout_ms=timeout_ms,
            delegation_ref=delegation_ref,
            repair_provider_id=repair_provider_id,
            persist=persist,
        )


Kernel = ExecutionKernel
Run = RunResult
