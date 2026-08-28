from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from harness_kernel.errors import SerializationError
from harness_kernel.models import (
    ArtifactContent,
    ArtifactProducer,
    ArtifactProvenance,
    ArtifactRecord,
    ArtifactSecurity,
    ArtifactStatus,
    ArtifactType,
    BlastRadius,
    CapabilityCompatibility,
    CapabilityComposition,
    CapabilityContracts,
    CapabilityDependencies,
    CapabilityInvocation,
    CapabilityManifest,
    CapabilityPrimaryType,
    CapabilityQuality,
    CapabilityScope,
    CapabilitySecurity,
    CapabilityStatus,
    Claim,
    ClaimStatus,
    ClassificationTrace,
    Complexity,
    Confidence,
    ContextBudget,
    ContextCost,
    CritiqueFinding,
    CritiqueReport,
    DataClass,
    DataImpact,
    Delivery,
    DeliveryStatus,
    Deprecation,
    EvidenceEnvironment,
    EvidenceFreshness,
    EvidenceKind,
    EvidenceProcedure,
    EvidenceProvenance,
    EvidenceRecord,
    EvidenceResult,
    EvidenceSummary,
    ExecutionGraph,
    ExecutionNode,
    ExecutionSummary,
    FindingCategory,
    FindingConfidence,
    FindingDisposition,
    FindingSeverity,
    FreshnessStatus,
    GateStatus,
    GateSummary,
    GraphStatus,
    Independence,
    InstallationScope,
    InvocationCallee,
    InvocationCaller,
    InvocationHandoff,
    InvocationInputs,
    InvocationLimits,
    InvocationStatus,
    LifecycleState,
    ManifestProvenance,
    MergeConflictOwner,
    MergePoint,
    NodeBudget,
    Ordering,
    ParallelismPotential,
    PrivacyClass,
    ProcedureStatus,
    Provenance,
    QualityBand,
    QualityDecision,
    QualityDimension,
    QualityDimensionName,
    QualityGate,
    QualityReport,
    Recommendation,
    RecordEnvelope,
    RecordStatus,
    Redaction,
    RegistryOrigin,
    RepositoryClassification,
    RepositoryContext,
    ResearchNeed,
    ResourceUsage,
    Reversibility,
    Risk,
    RouteBudget,
    RouteCompatibility,
    RouteDecision,
    RouteDecisionDetails,
    RouteKind,
    RouteStatus,
    RunSummary,
    SchemaVersion,
    SecurityImpact,
    SelectedCapability,
    SourceType,
    StopRecommendation,
    TaskDomain,
    TaskProfile,
    TelemetryActor,
    TelemetryEvent,
    TelemetryEventType,
    TelemetryIntegrity,
    TelemetryPayload,
    TrustState,
    UserImpact,
    VerificationProcedure,
    VerificationReport,
    Verifier,
    VisualImportance,
)
from harness_kernel.serialization import from_json, to_dict, to_json
from harness_kernel.validation import validate

NOW = "2026-08-28T12:00:00Z"


def envelope(status: RecordStatus = RecordStatus.CURRENT) -> RecordEnvelope:
    return RecordEnvelope(
        status=status,
        provenance=Provenance(
            source_type=SourceType.GENERATED,
            source_refs=("SRC-1",),
            created_at=NOW,
        ),
        evidence_refs=("EVID-1",),
    )


def profile() -> TaskProfile:
    return TaskProfile(
        schema_version=SchemaVersion.TASK_PROFILE,
        task_id="TASK-1",
        run_id="RUN-1",
        record=envelope(),
        objective="validate a contract",
        requested_outcome="a deterministic validation result",
        domain=TaskDomain.ENGINEERING,
        complexity=Complexity.SMALL,
        risk=Risk.LOW,
        visual_importance=VisualImportance.NONE,
        security_impact=SecurityImpact.LOW,
        data_impact=DataImpact.LOCAL,
        user_impact=UserImpact.INTERNAL,
        blast_radius=BlastRadius.LOCAL,
        research_need=ResearchNeed.NONE,
        parallelism_potential=ParallelismPotential.NONE,
        reversibility=Reversibility.EASY,
        confidence=Confidence.HIGH,
        constraints=("stdlib-only",),
        non_goals=("execute capabilities",),
        repository_context=RepositoryContext(
            root="/workspace/project",
            classification=RepositoryClassification.BROWNFIELD,
            trust_state=TrustState.TRUSTED,
        ),
        evidence=EvidenceSummary(refs=("EVID-1",), confidence=Confidence.HIGH),
        classification_trace=ClassificationTrace(
            rule_ids=("CONTRACT-BOUNDARY",),
            assumptions=(),
            unresolved=(),
        ),
        created_at=NOW,
    )


def all_records() -> tuple[object, ...]:
    selected = SelectedCapability(
        capability_id="validator",
        role=CapabilityPrimaryType.VALIDATOR,
        reason="contract boundary",
        required=True,
    )
    route = RouteDecision(
        schema_version=SchemaVersion.ROUTE_DECISION,
        decision_id="ROUTE-1",
        task_id="TASK-1",
        run_id="RUN-1",
        record=envelope(),
        profile_ref="TASK-1@TP-1",
        route_status=RouteStatus.SELECTED,
        route_kind=RouteKind.SPECIALIST,
        selected=(selected,),
        optional=(),
        omitted=(),
        decision=RouteDecisionDetails(
            precedence_rule_ids=("MINIMUM-ROUTE",),
            activation_reasons=("contract-validation",),
            non_activation_reasons=(),
            alternatives_considered=("DIRECT",),
        ),
        compatibility=RouteCompatibility(
            native_tools_considered=("pytest",),
            provider_constraints=(),
            conflicts_checked=(),
        ),
        budget=RouteBudget(token_estimate=100, latency_budget_ms=1000, parallelism_budget=1),
        quality_gates=("validation",),
        context_budget=ContextBudget(max_skill_kernels=1, max_reference_pack="MINIMAL"),
        fallback=None,
        confidence=Confidence.HIGH,
        unresolved=(),
        authority_ref="AUTH-1",
        created_at=NOW,
    )
    node = ExecutionNode(
        node_id="NODE-1",
        kind="VERIFICATION",
        capability_id="validator",
        owner="contracts-worker",
        input_refs=("TASK-1",),
        output_contract="ValidationResult",
        depends_on=(),
        can_parallelize=False,
        required=True,
        budget=NodeBudget(tokens=100, duration_ms=1000),
        acceptance_refs=("P1-CONTRACT",),
    )
    graph = ExecutionGraph(
        schema_version=SchemaVersion.EXECUTION_GRAPH,
        graph_id="GRAPH-1",
        task_id="TASK-1",
        run_id="RUN-1",
        record=envelope(),
        goal="validate contracts",
        nodes=(node,),
        edges=(),
        merge_points=(
            MergePoint(
                node_id="NODE-1",
                conflict_owner=MergeConflictOwner.INTEGRATOR,
                unresolved_policy="PRESERVE_AND_ESCALATE",
            ),
        ),
        graph_status=GraphStatus.READY,
        stop_policy_ref="STOP-1",
        created_at=NOW,
    )
    manifest = CapabilityManifest(
        schema_version=SchemaVersion.CAPABILITY_MANIFEST,
        capability_id="validator",
        display_name="Contract validator",
        version="1.0.0",
        record=envelope(),
        primary_type=CapabilityPrimaryType.VALIDATOR,
        status=CapabilityStatus.VERIFIED,
        owner="kernel",
        scope=CapabilityScope(
            domains=("ENGINEERING",),
            activates_when=("contract boundary",),
            do_not_activate_when=("runtime execution",),
            minimum_task_class=Complexity.SMALL,
        ),
        contracts=CapabilityContracts(
            inputs=("record",),
            outputs=("ValidationResult",),
            gates=("validation",),
            stop_conditions=("INVALID_INPUT",),
        ),
        composition=CapabilityComposition(
            can_call=(),
            can_be_called_by=("integrator",),
            must_run_before=(),
            must_run_after=(),
            conflicts_with=(),
        ),
        dependencies=CapabilityDependencies(
            capabilities=(),
            tools=("python",),
            providers=(),
            references=("architecture/docs/contracts/CapabilityManifest.json.md",),
        ),
        provenance=ManifestProvenance(
            source_type=SourceType.LOCAL,
            source_refs=("src/harness_kernel",),
            inspected_at=NOW,
            source_repository="local://codex-state-of-art-harness",
            source_hash="sha256:505ea67af7f335671b2e0aaaf6068f49b4e6fc2bcda96d8fd7544bb8e097512d",
            origin=RegistryOrigin.PROJECT,
            precedence=200,
            installation_scope=InstallationScope.PROJECT,
            project_scope="codex-state-of-art-harness",
        ),
        compatibility=CapabilityCompatibility(host_features=("python3.12",), platform_limits=()),
        quality=CapabilityQuality(
            profile="contract-core",
            eval_refs=("P1-CONTRACT",),
            benchmark_refs=(),
            last_result="PASS",
        ),
        security=CapabilitySecurity(
            permissions=("read-local-data",), data_classes=("INTERNAL",), secret_policy="none"
        ),
        context_cost=ContextCost(metadata_tokens_estimate=100, body_tokens_estimate=None),
        deprecation=Deprecation(successor=None, reason=None),
    )
    invocation = CapabilityInvocation(
        schema_version=SchemaVersion.CAPABILITY_INVOCATION,
        invocation_id="INV-1",
        task_id="TASK-1",
        run_id="RUN-1",
        record=envelope(),
        graph_node_id="NODE-1",
        caller=InvocationCaller(capability_id="orchestrator", authority_ref="AUTH-1"),
        callee=InvocationCallee(capability_id="validator", manifest_version="1.0.0"),
        objective="validate the contract",
        scope=("contract fields",),
        non_goals=("execute payload",),
        inputs=InvocationInputs(
            artifact_refs=("ART-1",), evidence_refs=("EVID-1",), payload_digest="sha256:abc"
        ),
        handoff=InvocationHandoff(
            acceptance_refs=("P1-CONTRACT",),
            required_output_contracts=("ValidationResult",),
            known_bad_conditions=("missing ID",),
        ),
        limits=InvocationLimits(
            token_budget=100, duration_budget_ms=1000, tool_call_budget=1, retry_budget=0
        ),
        permissions=("read-local-data",),
        requested_tools=("python",),
        expected_evidence=("validation findings",),
        invocation_status=InvocationStatus.REQUESTED,
        failure_refs=(),
        started_at=None,
        completed_at=None,
    )
    artifact = ArtifactRecord(
        schema_version=SchemaVersion.ARTIFACT_RECORD,
        artifact_id="ART-1",
        task_id="TASK-1",
        run_id="RUN-1",
        record=envelope(),
        artifact_type=ArtifactType.TEST_REPORT,
        title="Contract tests",
        producer=ArtifactProducer(capability_id="validator", invocation_id="INV-1"),
        content=ArtifactContent(
            locator="tests/unit/test_contracts.py",
            digest="sha256:abc",
            media_type="text/plain",
            size_bytes=100,
        ),
        source_refs=("TASK-1",),
        contract_refs=("P1-CONTRACT",),
        dependencies=(),
        artifact_status=ArtifactStatus.CREATED,
        evidence_refs=("EVID-1",),
        limitations=(),
        security=ArtifactSecurity(
            data_class=DataClass.INTERNAL, redaction=Redaction.NONE, access_policy="workspace"
        ),
        provenance=ArtifactProvenance(
            origin="GENERATED", tool_or_process="pytest", parent_artifacts=(), created_at=NOW
        ),
        supersedes=None,
    )
    evidence = EvidenceRecord(
        schema_version=SchemaVersion.EVIDENCE_RECORD,
        evidence_id="EVID-1",
        task_id="TASK-1",
        run_id="RUN-1",
        record=envelope(),
        claim_ref="CLAIM-1",
        evidence_kind=EvidenceKind.TEST_RESULT,
        procedure=EvidenceProcedure(
            procedure_id="PROC-1",
            description="run contract tests",
            command_or_method="pytest",
            executed=True,
        ),
        result=EvidenceResult.PASS,
        observation="all contract tests passed",
        artifact_refs=("ART-1",),
        environment=EvidenceEnvironment(
            host="workspace", version="3.12", fixture="unit", tool="pytest"
        ),
        observed_at=NOW,
        freshness=EvidenceFreshness(status=FreshnessStatus.FRESH, invalidated_by=()),
        provenance=EvidenceProvenance(
            source_type=SourceType.LOCAL, source_ref="pytest", content_digest="sha256:abc"
        ),
        limitations=(),
        confidence=Confidence.HIGH,
        privacy_class=PrivacyClass.INTERNAL,
    )
    verification = VerificationReport(
        schema_version=SchemaVersion.VERIFICATION_REPORT,
        report_id="VER-1",
        task_id="TASK-1",
        run_id="RUN-1",
        record=envelope(),
        artifact_refs=("ART-1",),
        acceptance_refs=("P1-CONTRACT",),
        claims=(
            Claim(
                claim_id="CLAIM-1",
                text="contracts serialize deterministically",
                required=True,
                status=ClaimStatus.PASS,
                evidence_refs=("EVID-1",),
                limitation_refs=(),
            ),
        ),
        procedures=(
            VerificationProcedure(
                procedure_id="PROC-1",
                description="run unit tests",
                status=ProcedureStatus.EXECUTED,
                result=EvidenceResult.PASS,
                evidence_refs=("EVID-1",),
            ),
        ),
        passed=("CLAIM-1",),
        failed=(),
        not_run=(),
        unknown=(),
        limitations=(),
        coverage=(1, 1, 100.0),
        confidence=Confidence.HIGH,
        blockers=(),
        recommendation=Recommendation.PASS,
        verifier=Verifier(capability_id="validator", independence=Independence.SEPARATED_SELF),
        created_at=NOW,
    )
    critique = CritiqueReport(
        schema_version=SchemaVersion.CRITIQUE_REPORT,
        report_id="CRIT-1",
        task_id="TASK-1",
        run_id="RUN-1",
        record=envelope(),
        reviewed_artifacts=("ART-1",),
        reviewed_reports=("VER-1",),
        quality_bar_ref="P1-QB-1",
        independence=Independence.SEPARATED_SELF,
        findings=(
            CritiqueFinding(
                finding_id="FIND-1",
                severity=FindingSeverity.NOTE,
                category=FindingCategory.PROCESS,
                statement="scope is local",
                evidence_refs=(),
                affected_refs=(),
                confidence=FindingConfidence.HIGH,
                disposition=FindingDisposition.FIXED,
                owner=None,
            ),
        ),
        strengths=("deterministic output",),
        missing_evidence=(),
        stop_recommendation=StopRecommendation.CONTINUE,
        residual_risk="LOW",
        limitations=(),
        reviewer=Verifier(capability_id="reviewer", independence=Independence.SEPARATED_SELF),
        created_at=NOW,
    )
    quality = QualityReport(
        schema_version=SchemaVersion.QUALITY_REPORT,
        report_id="QUAL-1",
        task_id="TASK-1",
        run_id="RUN-1",
        record=envelope(),
        profile="contract-core",
        artifact_refs=("ART-1",),
        verification_ref="VER-1",
        critique_ref="CRIT-1",
        dimensions=(
            QualityDimension(
                dimension=QualityDimensionName.CORRECTNESS,
                score=1.0,
                confidence=Confidence.HIGH,
                evidence_refs=("EVID-1",),
                limitations=(),
            ),
        ),
        gates=(
            QualityGate(
                gate_id="P1-CONTRACT",
                status=GateStatus.PASS,
                required=True,
                evidence_refs=("EVID-1",),
            ),
        ),
        quality_band=QualityBand.ACCEPTABLE,
        open_findings=(),
        residual_risk="LOW",
        decision=QualityDecision.DELIVER,
        decision_owner="contracts-worker",
        created_at=NOW,
    )
    telemetry = TelemetryEvent(
        schema_version=SchemaVersion.TELEMETRY_EVENT,
        event_id="EVT-1",
        event_sequence=1,
        timestamp=NOW,
        task_id="TASK-1",
        run_id="RUN-1",
        record=envelope(),
        parent_event_id=None,
        event_type=TelemetryEventType.TOOL_RESULT,
        actor=TelemetryActor(capability_id="validator", invocation_id="INV-1"),
        reason="contract tests",
        payload=TelemetryPayload(
            input_size=10,
            output_size=20,
            token_estimate=100,
            duration_ms=10,
            tool="pytest",
            result=EvidenceResult.PASS,
        ),
        artifact_refs=("ART-1",),
        evidence_refs=("EVID-1",),
        privacy_class=PrivacyClass.INTERNAL,
        redaction=Redaction.NONE,
        integrity=TelemetryIntegrity(
            previous_event_digest=None, event_digest="sha256:event", ordering=Ordering.IN_ORDER
        ),
        limitations=(),
    )
    summary = RunSummary(
        schema_version=SchemaVersion.RUN_SUMMARY,
        summary_id="SUMMARY-1",
        task_id="TASK-1",
        run_id="RUN-1",
        record=envelope(),
        lifecycle_state=LifecycleState.DELIVERED,
        route_ref="ROUTE-1",
        profile_ref="TASK-1@TP-1",
        graph_ref="GRAPH-1",
        selected_capabilities=("validator",),
        loaded_capabilities=("validator",),
        artifacts=("ART-1",),
        evidence=("EVID-1",),
        verification_ref="VER-1",
        critique_ref="CRIT-1",
        quality_ref="QUAL-1",
        gate_summary=GateSummary(passed=("P1-CONTRACT",), failed=(), not_run=(), blocked=()),
        execution=ExecutionSummary(
            started_at=NOW, completed_at=NOW, duration_ms=10, retries=0, stop_reason=None
        ),
        resource_usage=ResourceUsage(
            token_estimate=100, cost_estimate=0.0, tool_calls=1, parallel_lanes=1
        ),
        delivery=Delivery(
            status=DeliveryStatus.DELIVERED, artifact_ref="ART-1", decision_owner="contracts-worker"
        ),
        limitations=(),
        open_questions=(),
        confidence=Confidence.HIGH,
        created_at=NOW,
    )
    return (
        profile(),
        route,
        graph,
        manifest,
        invocation,
        artifact,
        evidence,
        verification,
        critique,
        quality,
        telemetry,
        summary,
    )


def test_all_documented_records_are_frozen_and_validate() -> None:
    records = all_records()

    for record in records:
        result = validate(record)
        assert result.is_valid, (type(record).__name__, result.findings)
        assert record.record.evidence_refs == ("EVID-1",)

    with pytest.raises(FrozenInstanceError):
        records[0].objective = "mutate"  # type: ignore[misc]


def test_collection_inputs_are_normalized_to_tuples() -> None:
    item = RecordEnvelope(
        status=RecordStatus.CURRENT,
        provenance=Provenance(SourceType.LOCAL, ["SRC-1"], NOW),
        evidence_refs=["EVID-1"],
    )

    assert item.provenance.source_refs == ("SRC-1",)
    assert item.evidence_refs == ("EVID-1",)


def test_json_is_reproducible_and_round_trips_with_enums_and_tuples() -> None:
    record = all_records()[0]

    first = to_json(record)
    second = to_json(record)

    assert first == second
    assert first == to_json(record, sort_keys=True)
    assert '"schema_version":"TP-1"' in first
    assert json.loads(first)["constraints"] == ["stdlib-only"]

    restored = from_json(first, TaskProfile)
    assert restored == record
    assert validate(restored).is_valid
    assert to_dict(restored) == to_dict(record)


def test_serializer_rejects_unsupported_runtime_values() -> None:
    with pytest.raises(SerializationError):
        to_json(object())
