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
    ProviderRegistry,
    ProviderResultStatus,
    digest_output,
)
from harness_kernel.registry import CapabilityRegistry
from harness_kernel.serialization import from_json, to_dict
from harness_kernel.telemetry import create_event
from harness_kernel.verification import (
    VerificationOutcome,
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
            output_contract="LocalExecutionResult",
            output_digest=digest_output(output),
            duration_ms=self.duration_ms,
        )


def _successful_verification(tmp_path: Path) -> tuple[RunResult, VerificationOutcome]:
    runtime = authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    ).run(
        "Produce a deterministic local result",
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
    selected = _StaticProvider("selected.provider", ("selected.provider",))
    fallback = _StaticProvider(
        "fallback.provider",
        ("selected.provider", "fallback.provider"),
    )
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
    assert result.route.selected[0].capability_id == "selected.provider"
    assert result.provider_results == ()
    assert result.summary.loaded_capabilities == ()
    assert _category(result.failures[0].category) == "CAPABILITY_UNAVAILABLE"
    assert result.failures[0].code == "PROVIDER_UNAVAILABLE"


def test_non_provider_manifest_cannot_admit_a_provider_execution(tmp_path: Path) -> None:
    manifest_registry = CapabilityRegistry().register(all_records()[3])
    provider = _StaticProvider("validator", ("validator",))

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
    mismatch = _StaticProvider(
        "mismatch.provider",
        ("mismatch.provider",),
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


def test_provider_reported_timeout_is_terminal_and_has_no_artifact(tmp_path: Path) -> None:
    slow = _StaticProvider("slow.provider", ("slow.provider",), duration_ms=50)
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
    provider = _StaticProvider("timed.provider", ("timed.provider",), duration_ms=7)
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
        "Preserve the fixture duration",
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
        "Exhaust bounded retries",
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
