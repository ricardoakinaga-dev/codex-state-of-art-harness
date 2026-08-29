from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from phase2_support import authorized_kernel
from test_contracts import all_records

from harness_kernel.artifacts import artifact_descendants
from harness_kernel.assurance import AssuranceDecision, assure_quality, create_critique
from harness_kernel.authority import AuthorityScope
from harness_kernel.boundary import BoundaryError, ProjectBoundary
from harness_kernel.errors import DeserializationError
from harness_kernel.evidence import (
    evidence_is_fresh,
    evidence_satisfies_claim,
    validate_evidence_links,
)
from harness_kernel.execution import (
    ExecutionLimits,
    ExecutionStatus,
    RunResult,
)
from harness_kernel.graph import (
    GraphValidationError,
    execute_graph,
    topological_order,
    validate_execution_graph,
)
from harness_kernel.models import (
    CapabilityInvocation,
    CapabilityManifest,
    EdgeRelation,
    ExecutionEdge,
    ExecutionGraph,
    ExecutionNode,
    GraphStatus,
    InvocationStatus,
    NodeBudget,
    NodeKind,
    Provenance,
    RecordEnvelope,
    RecordStatus,
    SchemaVersion,
    SourceType,
)
from harness_kernel.persistence import RecoveryStatus, RunStore
from harness_kernel.providers import (
    DeterministicRetryProvider,
    DeterministicSuccessProvider,
    ProviderAvailability,
    ProviderDescriptor,
    ProviderExecutionResult,
    ProviderRegistration,
    ProviderRegistry,
    ProviderResultStatus,
    digest_output,
)
from harness_kernel.registry import CapabilityRegistry
from harness_kernel.serialization import from_dict, from_json, to_dict
from harness_kernel.telemetry import create_event
from harness_kernel.verification import (
    VerificationOutcome,
    aggregate_verification,
    artifact_content_matches,
    stale_verification,
    verify_provider_result,
)

NOW = "2026-08-28T13:30:00Z"


def _category(value: object) -> str:
    return str(getattr(value, "value", value))


def _envelope() -> RecordEnvelope:
    return RecordEnvelope(
        status=RecordStatus.CURRENT,
        provenance=Provenance(SourceType.GENERATED, ("adversarial-test",), NOW),
    )


def _node(
    node_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    budget: NodeBudget | None = None,
) -> ExecutionNode:
    return ExecutionNode(
        node_id=node_id,
        kind=NodeKind.TOOL,
        capability_id=f"capability.{node_id.casefold()}",
        owner="adversarial-test",
        input_refs=(),
        output_contract="GraphNodeResult",
        depends_on=depends_on,
        can_parallelize=False,
        required=True,
        budget=budget or NodeBudget(tokens=1, duration_ms=1),
        acceptance_refs=("P2-GRAPH",),
        node_status=InvocationStatus.REQUESTED,
    )


def _graph(
    *nodes: ExecutionNode,
    edges: tuple[ExecutionEdge, ...] = (),
    graph_budget: NodeBudget | None = None,
) -> ExecutionGraph:
    total = max(1, len(nodes))
    return ExecutionGraph(
        schema_version=SchemaVersion.EXECUTION_GRAPH,
        graph_id="GRAPH-ADVERSARIAL",
        task_id="TASK-ADVERSARIAL",
        run_id="RUN-GRAPH-ADVERSARIAL",
        record=_envelope(),
        goal="exercise bounded graph behavior",
        nodes=nodes,
        edges=edges,
        merge_points=(),
        graph_status=GraphStatus.READY,
        stop_policy_ref="STOP-ADVERSARIAL",
        created_at=NOW,
        graph_owner="orchestrator",
        graph_budget=graph_budget or NodeBudget(tokens=total, duration_ms=total),
        acceptance_refs=("P2-GRAPH",),
    )


@dataclass(frozen=True, slots=True)
class _StaticProvider:
    provider_id: str
    capability_ids: tuple[str, ...]
    duration_ms: int = 1
    result_provider_id: str | None = None
    output_contract: str = "LocalExecutionResult"

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=self.provider_id,
            version="1.0.0",
            capability_ids=self.capability_ids,
            operations=("execute",),
        )

    def execute(
        self,
        invocation: CapabilityInvocation,
        manifest: CapabilityManifest | None = None,
    ) -> ProviderExecutionResult:
        del manifest
        output = {"provider": self.provider_id, "objective": invocation.objective}
        return ProviderExecutionResult(
            provider_id=self.result_provider_id or self.provider_id,
            invocation_id=invocation.invocation_id,
            status=ProviderResultStatus.SUCCEEDED,
            output=output,
            output_contract=self.output_contract,
            output_digest=digest_output(output),
            duration_ms=self.duration_ms,
        )


def _successful_verification(tmp_path: Path) -> tuple[RunResult, VerificationOutcome]:
    runtime = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    ).run(
        "Change one local label",
        task_id="TASK-EVIDENCE-ADVERSARIAL",
        run_id="RUN-EVIDENCE-ADVERSARIAL",
        provider_id="local.success",
    )
    outcome = verify_provider_result(
        runtime.invocations[0],
        runtime.provider_results[-1],
        runtime.artifacts[0],
    )
    return runtime, outcome


def test_boundary_rejects_traversal_absolute_and_symlink_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("protected", encoding="utf-8")
    outside_directory = tmp_path / "outside-directory"
    outside_directory.mkdir()
    boundary = ProjectBoundary(project)

    for candidate in (
        "../outside.txt",
        str(outside),
        r"..\outside.txt",
        "nested/../outside.txt",
        "\x00",
    ):
        with pytest.raises(BoundaryError):
            boundary.resolve(candidate, allow_missing=True)

    escaping_link = project / "escaping-link.txt"
    escaping_link.symlink_to(outside)
    with pytest.raises(BoundaryError):
        boundary.read_bytes("escaping-link.txt")

    escaping_directory = project / "escaping-directory"
    escaping_directory.symlink_to(outside_directory, target_is_directory=True)
    with pytest.raises(BoundaryError):
        boundary.atomic_write_bytes("escaping-directory/new.txt", b"must not escape")
    assert not (outside_directory / "new.txt").exists()


def test_shared_json_deserializer_rejects_excessive_nesting() -> None:
    payload = "[" * 65 + "0" + "]" * 65

    with pytest.raises(DeserializationError, match="nesting") as error:
        from_json(payload, dict)

    assert error.value.code == "DEPTH_LIMIT_EXCEEDED"


def test_boundary_refuses_replacing_an_in_project_symlink_target(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    real_file = project / "real.txt"
    real_file.write_text("original", encoding="utf-8")
    alias = project / "alias.txt"
    alias.symlink_to(real_file)
    boundary = ProjectBoundary(project)

    with pytest.raises(BoundaryError):
        boundary.atomic_write_bytes("alias.txt", b"forged replacement")

    assert real_file.read_text(encoding="utf-8") == "original"


def test_boundary_refuses_an_in_project_symlinked_parent_for_atomic_writes(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    real_directory = project / "real-directory"
    real_directory.mkdir()
    real_target = real_directory / "record.json"
    real_target.write_text("original", encoding="utf-8")
    alias_directory = project / "alias-directory"
    alias_directory.symlink_to(real_directory, target_is_directory=True)
    boundary = ProjectBoundary(project)

    with pytest.raises(BoundaryError):
        boundary.atomic_write_bytes("alias-directory/record.json", b"forged replacement")

    assert real_target.read_text(encoding="utf-8") == "original"


def test_unavailable_selected_provider_does_not_fallback_to_another_provider(
    tmp_path: Path,
) -> None:
    selected = DeterministicSuccessProvider(provider_id="selected.provider")
    fallback = DeterministicSuccessProvider(provider_id="fallback.provider")
    providers = (
        ProviderRegistry()
        .register(selected)
        .register(fallback)
        .with_availability("selected.provider", ProviderAvailability.UNAVAILABLE)
    )

    result = authorized_kernel(tmp_path, providers=providers).run(
        "Use the selected provider exactly",
        run_id="RUN-NO-FALLBACK",
        provider_id="selected.provider",
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.route.selected == ()
    assert any(item.capability_id == "selected.provider" for item in result.route.omitted)
    assert all(item.capability_id != "selected.provider" for item in result.route.selected)
    assert result.provider_results == ()
    assert result.summary.loaded_capabilities == ()
    assert _category(result.failures[0].category) == "CAPABILITY_UNAVAILABLE"
    assert result.failures[0].code == "PROVIDER_UNAVAILABLE"


def test_non_provider_manifest_cannot_admit_a_provider_execution(tmp_path: Path) -> None:
    manifest_registry = CapabilityRegistry().register(all_records()[3])
    provider = DeterministicSuccessProvider(provider_id="validator")

    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(provider),
        registry=manifest_registry,
    ).run(
        "Reject a validator manifest as a provider",
        run_id="RUN-MANIFEST-TYPE",
        provider_id="validator",
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.provider_results == ()
    assert result.failures[0].code == "CAPABILITY_MANIFEST_TYPE_MISMATCH"


def test_mismatched_provider_result_is_failed_without_hidden_fallback(tmp_path: Path) -> None:
    mismatch = DeterministicSuccessProvider(
        provider_id="mismatch.provider",
        result_provider_id="local.success",
    )
    providers = ProviderRegistry().register(mismatch).register(DeterministicSuccessProvider())

    result = authorized_kernel(tmp_path, providers=providers).run(
        "Reject a result with the wrong provider identity",
        run_id="RUN-PROVIDER-MISMATCH",
        provider_id="mismatch.provider",
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.route.selected[0].capability_id == "mismatch.provider"
    assert result.artifacts == ()
    assert len(result.provider_results) == 1
    assert result.provider_results[0].provider_id == "mismatch.provider"
    assert result.provider_results[0].failure is not None
    assert result.provider_results[0].failure.code == "PROVIDER_RESULT_CORRELATION"
    assert all(item.provider_id != "local.success" for item in result.provider_results)


def test_graph_cycle_is_rejected_before_topology_or_execution() -> None:
    candidate = _graph(
        _node("NODE-1", depends_on=("NODE-2",)),
        _node("NODE-2", depends_on=("NODE-1",)),
    )
    validation = validate_execution_graph(candidate)

    assert not validation.is_valid
    assert any("acyclic" in finding.message for finding in validation.findings)
    with pytest.raises(GraphValidationError):
        topological_order(candidate)
    with pytest.raises(GraphValidationError):
        execute_graph(candidate, lambda _: pytest.fail("invalid graph was executed"))


def test_graph_dangling_dependency_is_rejected_before_any_node_runs() -> None:
    candidate = _graph(_node("NODE-1", depends_on=("NODE-MISSING",)))
    invoked: list[str] = []

    validation = validate_execution_graph(candidate)
    assert not validation.is_valid
    assert any(finding.code.value == "INVALID_REFERENCE" for finding in validation.findings)
    with pytest.raises(GraphValidationError):
        execute_graph(candidate, lambda node: invoked.append(node.node_id))
    assert invoked == []


@pytest.mark.parametrize("duplicate_kind", ("nodes", "edges", "dependencies"))
def test_graph_rejects_duplicate_nodes_dependencies_and_edges(duplicate_kind: str) -> None:
    if duplicate_kind == "nodes":
        candidate = _graph(_node("NODE-1"), _node("NODE-1"))
    elif duplicate_kind == "edges":
        edge = ExecutionEdge("NODE-1", "NODE-2", EdgeRelation.DATA)
        candidate = _graph(
            _node("NODE-1"),
            _node("NODE-2"),
            edges=(edge, edge),
        )
    else:
        candidate = _graph(
            _node("NODE-1"),
            _node("NODE-2", depends_on=("NODE-1", "NODE-1")),
        )

    validation = validate_execution_graph(candidate)

    assert not validation.is_valid
    assert any(
        "unique" in finding.message or "duplicate" in finding.message
        for finding in validation.findings
    )


def test_graph_rejects_impossible_node_and_graph_budgets() -> None:
    candidate = _graph(
        _node("NODE-1", budget=NodeBudget(tokens=7, duration_ms=7)),
        _node("NODE-2", budget=NodeBudget(tokens=7, duration_ms=7)),
        graph_budget=NodeBudget(tokens=10, duration_ms=10),
    )

    validation = validate_execution_graph(candidate, max_nodes=1)

    assert not validation.is_valid
    messages = {finding.message for finding in validation.findings}
    assert "graph exceeds its node budget" in messages
    assert "node token budgets exceed graph budget" in messages
    assert "node duration budgets exceed graph budget" in messages
    with pytest.raises(GraphValidationError):
        execute_graph(
            candidate, lambda _: pytest.fail("over-budget graph was executed"), max_nodes=1
        )


def test_graph_failure_preserves_independent_partial_results_and_blocks_descendants() -> None:
    candidate = _graph(
        _node("NODE-1"),
        _node("NODE-2", depends_on=("NODE-1",)),
        _node("NODE-3"),
    )
    invoked: list[str] = []

    def invoke(node: ExecutionNode) -> str:
        invoked.append(node.node_id)
        if node.node_id == "NODE-1":
            raise RuntimeError("fixture failure")
        return f"value:{node.node_id}"

    outcomes = execute_graph(candidate, invoke)
    by_id = {outcome.node_id: outcome for outcome in outcomes}

    assert invoked == ["NODE-1", "NODE-3"]
    assert by_id["NODE-1"].status is InvocationStatus.FAILED
    assert by_id["NODE-3"].status is InvocationStatus.SUCCEEDED
    assert by_id["NODE-3"].value == "value:NODE-3"
    assert by_id["NODE-2"].status is InvocationStatus.BLOCKED
    assert by_id["NODE-2"].blocked_by == ("NODE-1",)
    assert by_id["NODE-2"].failure is not None
    assert _category(by_id["NODE-2"].failure.category) == "DEPENDENCY_FAILED"


def test_cancelled_graph_never_calls_a_node() -> None:
    candidate = _graph(_node("NODE-1"), _node("NODE-2", depends_on=("NODE-1",)))
    invoked: list[str] = []

    outcomes = execute_graph(
        candidate,
        lambda node: invoked.append(node.node_id),
        cancelled=True,
    )

    assert invoked == []
    by_id = {outcome.node_id: outcome for outcome in outcomes}
    assert by_id["NODE-1"].status is InvocationStatus.CANCELLED
    assert by_id["NODE-2"].status is InvocationStatus.BLOCKED
    assert by_id["NODE-2"].blocked_by == ("NODE-1",)


def test_raising_graph_cancellation_callback_is_normalized() -> None:
    candidate = _graph(_node("NODE-1"))

    def cancelled() -> bool:
        raise RuntimeError("cancellation signal unavailable")

    outcomes = execute_graph(candidate, lambda node: node.node_id, cancelled=cancelled)

    assert outcomes[0].status is InvocationStatus.CANCELLED
    assert outcomes[0].failure is not None
    assert outcomes[0].failure.code == "CANCELLED"


def test_provider_reported_timeout_is_terminal_and_has_no_artifact(tmp_path: Path) -> None:
    slow = DeterministicSuccessProvider(provider_id="slow.provider", duration_ms=50)
    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(slow),
    ).run(
        "Enforce provider duration",
        run_id="RUN-PROVIDER-TIMEOUT",
        provider_id="slow.provider",
        timeout_ms=5,
    )

    assert result.status is ExecutionStatus.TIMED_OUT
    assert result.invocations[0].invocation_status is InvocationStatus.TIMED_OUT
    assert result.artifacts == ()
    assert result.provider_results[-1].failure is not None
    assert _category(result.provider_results[-1].failure.category) == "TIMEOUT"
    assert result.provider_results[-1].failure.code == "PROVIDER_TIMEOUT"
    assert result.summary.execution.duration_ms == 50
    completed = next(
        event for event in result.telemetry.events if event.event_type.value == "RUN_COMPLETED"
    )
    assert completed.payload.duration_ms == 50


def test_summary_and_telemetry_preserve_observed_provider_duration(tmp_path: Path) -> None:
    provider = DeterministicSuccessProvider(provider_id="timed.provider", duration_ms=7)
    authority = AuthorityScope(
        owner="test-policy",
        actor="test-runner",
        scopes=("task:TASK-DURATION", "capability:timed.provider"),
        decisions=("TRANSITION",),
        subject_owner="test-policy",
        operations=("execute",),
        issued_at=NOW,
        expires_at="2026-08-28T14:00:00Z",
    )

    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(provider),
        timestamp=NOW,
    ).run(
        "Change one local label and preserve the fixture duration",
        task_id="TASK-DURATION",
        run_id="RUN-DURATION",
        provider_id="timed.provider",
        authority=authority,
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.summary.execution.duration_ms == 7
    tool_result = next(
        event for event in result.telemetry.events if event.event_type.value == "TOOL_RESULT"
    )
    completed = next(
        event for event in result.telemetry.events if event.event_type.value == "RUN_COMPLETED"
    )
    assert tool_result.payload.duration_ms == 7
    assert completed.payload.duration_ms == 7


def test_cancellation_is_observed_before_provider_execution(tmp_path: Path) -> None:
    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    ).run(
        "Cancel before local execution",
        run_id="RUN-CANCEL-BEFORE-PROVIDER",
        provider_id="local.success",
        cancelled=True,
    )

    assert result.status is ExecutionStatus.CANCELLED
    assert result.executed is False
    assert result.provider_results == ()
    assert result.invocations[0].invocation_status is InvocationStatus.CANCELLED
    assert _category(result.failures[0].category) == "CANCELLED"
    assert result.failures[0].code == "CANCELLED_BEFORE_PROVIDER"


def test_raising_cancellation_callback_is_normalized_to_terminal_cancel(tmp_path: Path) -> None:
    def cancelled() -> bool:
        raise RuntimeError("cancellation signal unavailable")

    result = authorized_kernel(tmp_path).run(
        "Change one local label",
        run_id="RUN-RAISING-CANCEL",
        cancelled=cancelled,
    )

    assert result.status is ExecutionStatus.CANCELLED
    assert result.provider_results == ()
    assert result.failures[0].code == "CANCELLED_BEFORE_PROVIDER"


def test_retry_is_bounded_and_records_each_attempt(tmp_path: Path) -> None:
    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(
            DeterministicRetryProvider(failures_before_success=2)
        ),
    ).run(
        "Retry a deterministic provider",
        run_id="RUN-RETRY-SUCCESS",
        provider_id="local.retry",
        limits=ExecutionLimits(max_retries=2),
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert tuple(item.attempt for item in result.provider_results) == (1, 2, 3)
    assert result.summary.execution.retries == 2
    assert result.invocations[0].trace_context[-1] == ("attempt", "3")
    assert result.verification.recommendation.value == "PASS"


def test_retry_exhaustion_does_not_fallback_or_emit_a_delivery(tmp_path: Path) -> None:
    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry()
        .register(DeterministicRetryProvider(failures_before_success=4))
        .register(DeterministicSuccessProvider()),
    ).run(
        "Change one local label after bounded retries",
        run_id="RUN-RETRY-EXHAUSTED",
        provider_id="local.retry",
        limits=ExecutionLimits(max_retries=2),
    )

    assert result.status is ExecutionStatus.FAILED
    assert tuple(item.attempt for item in result.provider_results) == (1, 2, 3)
    assert all(item.provider_id == "local.retry" for item in result.provider_results)
    assert result.summary.execution.retries == 2
    assert result.artifacts == ()
    assert result.summary.delivery.status.value == "BLOCKED"


def test_persistence_replay_is_idempotent_but_conflict_and_corruption_do_not_recover(
    tmp_path: Path,
) -> None:
    boundary = ProjectBoundary(tmp_path)
    store = RunStore(boundary)
    run_id = "RUN-REPLAY"
    terminal = {"run_id": run_id, "status": "DELIVERED"}

    store.write_record(run_id, terminal)
    store.write_record(run_id, dict(terminal))
    with pytest.raises(BoundaryError):
        store.write_record(run_id, {"run_id": run_id, "status": "RUNNING"})

    assert store.load_record(run_id) == terminal
    assert store.recover(run_id).status is RecoveryStatus.FINISHED

    corrupt_id = "RUN-CORRUPT"
    boundary.atomic_write_bytes(
        f".harness/state/runs/{corrupt_id}.json",
        b'{"run_id":"RUN-CORRUPT","status":',
    )
    recovery = store.recover(corrupt_id)

    assert recovery.status is RecoveryStatus.CORRUPT
    assert store.recover("RUN-MISSING").status is RecoveryStatus.MISSING


@pytest.mark.parametrize("corrupt", (b"not-json\n", b"[]\n"))
def test_corrupt_persisted_telemetry_is_rejected_without_appending(
    tmp_path: Path, corrupt: bytes
) -> None:
    boundary = ProjectBoundary(tmp_path)
    store = RunStore(boundary)
    relative = ".harness/telemetry/runs/RUN-LOG.jsonl"
    boundary.atomic_write_bytes(relative, corrupt)

    with pytest.raises(BoundaryError):
        store.append_telemetry(
            "RUN-LOG",
            {"run_id": "RUN-LOG", "event_id": "EVT-2"},
        )

    assert boundary.read_bytes(relative) == corrupt


def test_persisted_telemetry_rebuilds_and_verifies_the_hash_chain(
    tmp_path: Path,
) -> None:
    boundary = ProjectBoundary(tmp_path)
    store = RunStore(boundary)
    first = create_event(
        event_id="EVT-CHAIN-1",
        event_sequence=1,
        timestamp=NOW,
        task_id="TASK-CHAIN",
        run_id="RUN-CHAIN",
        event_type="TASK_RECEIVED",
    )
    second = create_event(
        event_id="EVT-CHAIN-2",
        event_sequence=2,
        timestamp=NOW,
        task_id="TASK-CHAIN",
        run_id="RUN-CHAIN",
        event_type="RUN_COMPLETED",
        previous_event_digest=first.integrity.event_digest,
    )
    store.append_telemetry("RUN-CHAIN", to_dict(first))
    store.append_telemetry("RUN-CHAIN", to_dict(second))
    relative = ".harness/telemetry/runs/RUN-CHAIN.jsonl"
    original = boundary.read_bytes(relative)
    forged = json.loads(original.splitlines()[0])
    forged["reason"] = "tampered without recomputing the digest"
    boundary.atomic_write_bytes(
        relative,
        json.dumps(forged).encode("utf-8") + b"\n" + original.splitlines()[1] + b"\n",
    )

    with pytest.raises(BoundaryError):
        store.append_telemetry("RUN-CHAIN", to_dict(second))

    assert boundary.read_bytes(relative) != original
    assert from_json(original.splitlines()[0], type(first)) == first


def test_recovery_rejects_identity_and_unknown_state_snapshots(tmp_path: Path) -> None:
    store = RunStore(ProjectBoundary(tmp_path))
    store.boundary.atomic_write_json(
        ".harness/state/runs/RUN-IDENTITY.json",
        {"run_id": "RUN-OTHER", "status": "SUCCEEDED"},
    )
    store.write_record("RUN-UNKNOWN", {"run_id": "RUN-UNKNOWN", "status": "MADE_UP"})

    assert store.recover("RUN-IDENTITY").status is RecoveryStatus.CORRUPT
    assert store.recover("RUN-UNKNOWN").status is RecoveryStatus.CORRUPT


def test_forged_artifact_digest_fails_deterministic_verification(tmp_path: Path) -> None:
    runtime, _ = _successful_verification(tmp_path)
    artifact = runtime.artifacts[0]
    forged_artifact = replace(
        artifact,
        content=replace(artifact.content, digest=digest_output({"forged": True})),
    )

    outcome = verify_provider_result(
        runtime.invocations[0],
        runtime.provider_results[-1],
        forged_artifact,
    )

    assert not artifact_content_matches(forged_artifact, runtime.provider_results[-1].output)
    assert not outcome.passed
    assert outcome.report.recommendation.value == "FAIL"
    assert outcome.failure is not None
    assert outcome.failure.code == "VERIFICATION_FAILED"


def test_artifact_provider_lineage_must_match_the_provider_result(tmp_path: Path) -> None:
    runtime, _ = _successful_verification(tmp_path)
    artifact = runtime.artifacts[0]
    forged_artifact = replace(
        artifact,
        provenance=replace(artifact.provenance, tool_or_process="local.other-provider"),
    )

    outcome = verify_provider_result(
        runtime.invocations[0],
        runtime.provider_results[-1],
        forged_artifact,
    )

    assert not outcome.passed
    assert outcome.report.recommendation.value == "FAIL"


def test_verification_rejects_stale_or_missing_observed_timestamps(tmp_path: Path) -> None:
    runtime, _ = _successful_verification(tmp_path)
    result = runtime.provider_results[-1]
    stale = verify_provider_result(
        runtime.invocations[0],
        result,
        runtime.artifacts[0],
        timestamp="2026-08-28T13:30:00Z",
    )
    missing = verify_provider_result(
        runtime.invocations[0],
        replace(result, started_at=None, ended_at=None),
        runtime.artifacts[0],
    )

    assert not stale.passed
    assert stale.report.record.status is RecordStatus.STALE
    assert stale.evidence[0].freshness.status.value == "STALE"
    assert not missing.passed
    assert missing.report.record.status is RecordStatus.STALE


def test_execution_does_not_promote_success_without_observed_timestamps(tmp_path: Path) -> None:
    providers = ProviderRegistry().register(
        DeterministicSuccessProvider(emit_observed_timestamps=False)
    )
    result = authorized_kernel(tmp_path, providers=providers).run(
        "Change one local label",
        task_id="TASK-MISSING-OBSERVATION",
        run_id="RUN-MISSING-OBSERVATION",
        provider_id="local.success",
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.artifacts == ()
    assert result.provider_results[-1].started_at is None
    assert result.provider_results[-1].ended_at is None
    assert result.verification.record.status is RecordStatus.STALE
    assert "provider-result-freshness" in result.verification.blockers


def test_forged_provider_digest_is_rejected_before_verification(tmp_path: Path) -> None:
    runtime, _ = _successful_verification(tmp_path)

    with pytest.raises(ValueError, match="digest"):
        replace(
            runtime.provider_results[-1],
            output_digest=f"sha256:{'0' * 64}",
        )


def test_forged_pass_evidence_with_unexecuted_procedure_is_not_sufficient(
    tmp_path: Path,
) -> None:
    _, fresh = _successful_verification(tmp_path)
    forged_evidence = replace(
        fresh.evidence[0],
        procedure=replace(fresh.evidence[0].procedure, executed=False),
    )

    links = validate_evidence_links(
        fresh.report.claims,
        (fresh.procedure,),
        (forged_evidence,),
    )

    assert not links.is_valid
    assert any("executed fresh procedure" in finding.message for finding in links.findings)
    assert not evidence_satisfies_claim(
        fresh.report.claims[0],
        (fresh.procedure,),
        (forged_evidence,),
    )


def test_stale_verification_cannot_be_promoted_to_quality_acceptance(tmp_path: Path) -> None:
    _, fresh = _successful_verification(tmp_path)
    stale = stale_verification(fresh)
    critique = create_critique(stale.report)
    assurance = assure_quality(stale.report, critique)

    assert stale.report.record.status is RecordStatus.STALE
    assert stale.report.recommendation.value == "FAIL"
    assert stale.failure is not None
    assert stale.failure.code == "STALE_EVIDENCE"
    assert not evidence_is_fresh(stale.evidence[0])
    assert not evidence_satisfies_claim(stale.report.claims[0], (stale.procedure,), stale.evidence)
    assert assurance.decision is AssuranceDecision.FAILED


def test_artifact_lineage_does_not_allow_forged_parent_references(tmp_path: Path) -> None:
    runtime, _ = _successful_verification(tmp_path)
    artifact = runtime.artifacts[0]
    forged = replace(
        artifact,
        provenance=replace(artifact.provenance, parent_artifacts=("ART-MISSING",)),
    )

    with pytest.raises(ValueError, match="lineage is invalid"):
        artifact_descendants((forged,), forged.artifact_id)


def test_untrusted_provider_implementation_is_rejected() -> None:
    provider = _StaticProvider("untrusted.provider", ("untrusted.provider",))

    with pytest.raises(ValueError, match="built-in deterministic fixture providers"):
        ProviderRegistry().register(provider)

    with pytest.raises(ValueError, match="built-in deterministic fixture providers"):
        ProviderRegistry(
            (
                ProviderRegistration(
                    provider.descriptor,
                    provider,
                    ProviderAvailability.AVAILABLE,
                ),
            )
        )


def test_materially_conditional_route_cannot_execute(tmp_path: Path) -> None:
    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    ).run(
        "What should we do about this unknown high-impact situation?",
        run_id="RUN-CONDITIONAL-ROUTE",
        provider_id="local.success",
    )

    assert result.route.route_status.value == "CONDITIONAL"
    assert result.provider_results == ()
    assert result.status is not ExecutionStatus.SUCCEEDED


def test_dry_run_checks_expired_authority_before_fabricating_readiness(tmp_path: Path) -> None:
    authority = AuthorityScope(
        owner="test-policy",
        actor="test-runner",
        scopes=("task:TASK-EXPIRED", "capability:local.success"),
        decisions=("TRANSITION",),
        subject_owner="test-policy",
        operations=("execute",),
        issued_at="2026-08-28T12:00:00Z",
        expires_at="2026-08-28T13:00:00Z",
    )

    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
        timestamp=NOW,
    ).run(
        "Change one local label",
        task_id="TASK-EXPIRED",
        run_id="RUN-EXPIRED-DRY",
        provider_id="local.success",
        authority=authority,
        dry_run=True,
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.provider_results == ()
    assert result.invocations[0].invocation_status is InvocationStatus.BLOCKED
    assert result.invocations[0].authority_snapshot_ref is None
    assert result.failures[0].code == "AUTHORITY_EXPIRED"


def test_wrong_output_contract_cannot_promote_quality(tmp_path: Path) -> None:
    runtime, _ = _successful_verification(tmp_path)
    forged = replace(runtime.provider_results[-1], output_contract="WrongContract")

    outcome = verify_provider_result(runtime.invocations[0], forged, runtime.artifacts[0])

    assert not outcome.passed
    assert outcome.report.recommendation.value == "FAIL"


def test_graph_provider_preflight_rejects_missing_provider_before_any_call(tmp_path: Path) -> None:
    first = replace(_node("NODE-1"), capability_id="local.direct", provider_id="local.success")
    second = replace(
        _node("NODE-2", depends_on=("NODE-1",)),
        capability_id="local.direct",
        provider_id="local.missing",
    )
    candidate = _graph(first, second)

    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    ).run(
        "Run the local graph",
        graph=candidate,
    )

    assert result.status is not ExecutionStatus.SUCCEEDED
    assert result.provider_results == ()
    assert all(item.invocation_status is InvocationStatus.BLOCKED for item in result.invocations)


def test_terminal_graph_replay_is_rejected_before_provider_execution(tmp_path: Path) -> None:
    first = replace(
        _node("NODE-1"),
        capability_id="local.direct",
        provider_id="local.success",
        node_status=InvocationStatus.SUCCEEDED,
    )
    candidate = replace(_graph(first), graph_status=GraphStatus.COMPLETED)

    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    ).run("Run the local graph", graph=candidate)

    assert result.status is not ExecutionStatus.SUCCEEDED
    assert result.provider_results == ()


def test_active_graph_replay_is_rejected_before_provider_execution(tmp_path: Path) -> None:
    candidate = replace(_graph(_node("NODE-1")), graph_status=GraphStatus.RUNNING)

    assert not validate_execution_graph(candidate).is_valid

    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    ).run("Run the local graph", graph=candidate)

    assert result.status is not ExecutionStatus.SUCCEEDED
    assert result.provider_results == ()


def test_retry_attempts_consume_invocation_budget(tmp_path: Path) -> None:
    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(
            DeterministicRetryProvider(failures_before_success=2)
        ),
    ).run(
        "Change one local label",
        run_id="RUN-RETRY-BUDGET",
        provider_id="local.retry",
        limits=ExecutionLimits(max_invocations=1, max_retries=2),
    )

    assert result.status is not ExecutionStatus.SUCCEEDED
    assert len(result.provider_results) == 1
    assert result.provider_results[0].attempt == 1
    assert result.provider_results[0].failure is not None
    assert result.provider_results[0].failure.code == "FIXTURE_RETRYABLE_FAILURE"
    assert result.summary.delivery.status.value == "BLOCKED"


def test_persisted_artifact_tampering_makes_recovery_corrupt(tmp_path: Path) -> None:
    runtime = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    ).run(
        "Change one local label and persist one local artifact",
        task_id="TASK-PERSIST-INTEGRITY",
        run_id="RUN-PERSIST-INTEGRITY",
        provider_id="local.success",
        persist=True,
    )
    locator = runtime.artifacts[0].content.locator
    assert locator is not None
    ProjectBoundary(tmp_path).atomic_write_bytes(locator, b'{"tampered":true}')

    recovery = RunStore(ProjectBoundary(tmp_path)).recover(runtime.summary.run_id)

    assert recovery.status is RecoveryStatus.CORRUPT


def test_persisted_evidence_tampering_makes_recovery_corrupt(tmp_path: Path) -> None:
    runtime = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    ).run(
        "Change one local label and persist evidence",
        task_id="TASK-PERSIST-EVIDENCE",
        run_id="RUN-PERSIST-EVIDENCE",
        provider_id="local.success",
        persist=True,
    )
    boundary = ProjectBoundary(tmp_path)
    relative = ".harness/evidence/runs/RUN-PERSIST-EVIDENCE.json"
    payload = boundary.read_json(relative)
    assert isinstance(payload, dict)
    records = payload.get("records")
    assert isinstance(records, list) and records
    first = records[0]
    assert isinstance(first, dict)
    provenance = first.get("provenance")
    assert isinstance(provenance, dict)
    forged = {
        **payload,
        "records": [{**first, "provenance": {**provenance, "source_ref": "forged.provider"}}],
    }
    boundary.atomic_write_json(relative, forged)

    recovery = RunStore(boundary).recover(runtime.summary.run_id)

    assert recovery.status is RecoveryStatus.CORRUPT


def test_persisted_typed_summary_without_its_bundle_is_corrupt(tmp_path: Path) -> None:
    runtime = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    ).run(
        "Change one local label and persist the complete bundle",
        task_id="TASK-PERSIST-MISSING",
        run_id="RUN-PERSIST-MISSING",
        provider_id="local.success",
        persist=True,
    )
    for relative in (
        ".harness/evidence/runs/RUN-PERSIST-MISSING.json",
        ".harness/evidence/runs/RUN-PERSIST-MISSING-artifacts.json",
        ".harness/telemetry/runs/RUN-PERSIST-MISSING.jsonl",
        ".harness/state/lifecycle/RUN-PERSIST-MISSING.jsonl",
    ):
        (tmp_path / relative).unlink()

    recovery = RunStore(ProjectBoundary(tmp_path)).recover(runtime.summary.run_id)

    assert recovery.status is RecoveryStatus.CORRUPT


def test_telemetry_redacts_limitations() -> None:
    event = create_event(
        event_id="EVT-REDACT-LIMITATIONS",
        event_sequence=1,
        timestamp=NOW,
        task_id="TASK-REDACT",
        run_id="RUN-REDACT",
        event_type="TASK_RECEIVED",
        limitations=("api_key=TOPSECRET", "password is hunter2"),
    )

    serialized = to_dict(event)
    assert "TOPSECRET" not in repr(serialized)
    assert "hunter2" not in repr(serialized)
    assert "[REDACTED]" in repr(serialized)


def test_telemetry_redacts_sensitive_provenance_source_refs() -> None:
    record = RecordEnvelope(
        status=RecordStatus.CURRENT,
        provenance=Provenance(SourceType.GENERATED, ("password=hunter2",), NOW),
    )

    event = create_event(
        event_id="EVT-REDACT-RECORD",
        event_sequence=1,
        timestamp=NOW,
        task_id="TASK-REDACT",
        run_id="RUN-REDACT",
        event_type="TASK_RECEIVED",
        record=record,
    )

    serialized = to_dict(event)
    assert "hunter2" not in repr(serialized)
    assert event.redaction.value == "APPLIED"


def test_persistence_rejects_artifact_locator_outside_owned_runs(tmp_path: Path) -> None:
    runtime, _ = _successful_verification(tmp_path)
    artifact = replace(
        runtime.artifacts[0],
        content=replace(runtime.artifacts[0].content, locator="src/generated.json"),
    )

    with pytest.raises(BoundaryError, match="owned run"):
        RunStore(ProjectBoundary(tmp_path)).write_artifact(
            artifact, runtime.provider_results[-1].output
        )


@pytest.mark.parametrize(
    "payload",
    (
        {"value": "x" * (4 * 1024 * 1024 + 1)},
        {"value": float("nan")},
    ),
)
def test_direct_mapping_deserialization_enforces_json_bounds(payload: dict[str, object]) -> None:
    with pytest.raises(DeserializationError):
        from_dict(payload, dict)


def test_date_only_telemetry_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timestamp"):
        create_event(
            event_id="EVT-DATE-ONLY",
            event_sequence=1,
            timestamp="2026-08-28",
            task_id="TASK-TIME",
            run_id="RUN-TIME",
            event_type="TASK_RECEIVED",
        )


def test_subject_type_mismatch_is_denied_before_provider_execution(tmp_path: Path) -> None:
    authority = replace(
        AuthorityScope(
            owner="test-policy",
            actor="test-runner",
            scopes=("task:TASK-SUBJECT", "capability:local.success"),
            decisions=("TRANSITION",),
            subject_owner="test-policy",
            operations=("execute",),
        ),
        subject_type="RUN",
    )

    result = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    ).run(
        "Change one local label",
        task_id="TASK-SUBJECT",
        run_id="RUN-SUBJECT",
        provider_id="local.success",
        authority=authority,
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.provider_results == ()
    assert result.failures[0].code == "INVALID_SUBJECT_TYPE"


def test_unrelated_or_stale_critique_cannot_assure_quality(tmp_path: Path) -> None:
    runtime, fresh = _successful_verification(tmp_path)
    critique = create_critique(fresh.report)
    unrelated = replace(critique, task_id="TASK-OTHER", run_id="RUN-OTHER")
    stale_critique = replace(
        critique,
        record=replace(critique.record, status=RecordStatus.STALE),
    )
    stale_report = replace(
        fresh.report,
        record=replace(fresh.report.record, status=RecordStatus.STALE),
    )

    assert (
        assure_quality(fresh.report, unrelated).decision is not AssuranceDecision.QUALITY_ACCEPTED
    )
    assert assure_quality(stale_report, critique).decision is not AssuranceDecision.QUALITY_ACCEPTED
    assert (
        assure_quality(fresh.report, stale_critique).decision
        is not AssuranceDecision.QUALITY_ACCEPTED
    )
    assert runtime.summary.run_id == fresh.report.run_id


def test_packet_bound_assurance_requires_a_blind_digest(tmp_path: Path) -> None:
    runtime, fresh = _successful_verification(tmp_path)
    critique = create_critique(fresh.report)
    without_digest = replace(
        critique,
        reviewer=replace(critique.reviewer, blind_packet_digest=None),
    )

    assurance = assure_quality(
        fresh.report,
        without_digest,
        evidence=fresh.evidence,
        artifacts=runtime.artifacts,
    )

    assert assurance.decision is AssuranceDecision.FAILED
    assert "blind verification digest" in assurance.reason


def test_assurance_requires_the_current_packet_even_for_typed_reports(tmp_path: Path) -> None:
    _, fresh = _successful_verification(tmp_path)
    critique = create_critique(fresh.report)

    assurance = assure_quality(fresh.report, critique)

    assert assurance.decision is AssuranceDecision.BLOCKED
    assert "current evidence and artifact packet" in assurance.reason


def test_packet_bound_assurance_rejects_forged_evidence_payload(tmp_path: Path) -> None:
    runtime, fresh = _successful_verification(tmp_path)
    critique = create_critique(
        fresh.report,
        evidence=fresh.evidence,
        artifacts=runtime.artifacts,
    )
    forged = replace(fresh.evidence[0], observation="forged observation")

    assurance = assure_quality(
        fresh.report,
        critique,
        evidence=(forged,),
        artifacts=runtime.artifacts,
    )

    assert assurance.decision is AssuranceDecision.FAILED
    assert "blind packet digest" in assurance.reason


def test_evidence_content_digest_must_match_artifact(tmp_path: Path) -> None:
    runtime, fresh = _successful_verification(tmp_path)
    forged = replace(
        fresh.evidence[0],
        provenance=replace(
            fresh.evidence[0].provenance,
            content_digest=f"sha256:{'0' * 64}",
        ),
    )

    links = validate_evidence_links(
        fresh.report.claims,
        (fresh.procedure,),
        (forged,),
        artifacts=runtime.artifacts,
    )

    assert not links.is_valid
    assert any("digest" in finding.message for finding in links.findings)


def test_evidence_source_must_match_artifact_producer(tmp_path: Path) -> None:
    runtime, fresh = _successful_verification(tmp_path)
    forged = replace(
        fresh.evidence[0],
        provenance=replace(fresh.evidence[0].provenance, source_ref="different.provider"),
    )

    links = validate_evidence_links(
        fresh.report.claims,
        (fresh.procedure,),
        (forged,),
        artifacts=runtime.artifacts,
    )

    assert not links.is_valid
    assert any("source" in finding.message for finding in links.findings)


def test_aggregate_verification_rejects_mismatched_outcome_identity(tmp_path: Path) -> None:
    runtime, fresh = _successful_verification(tmp_path)
    forged_report = replace(fresh.report, task_id="TASK-OTHER")
    forged = VerificationOutcome(forged_report, fresh.evidence, fresh.procedure)

    with pytest.raises(ValueError, match="correlation"):
        aggregate_verification(
            (forged,),
            task_id=runtime.summary.task_id,
            run_id=runtime.summary.run_id,
        )
