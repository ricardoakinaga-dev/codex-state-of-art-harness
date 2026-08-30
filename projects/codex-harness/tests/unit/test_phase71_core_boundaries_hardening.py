from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from enum import StrEnum
from pathlib import Path

import pytest
from test_contracts import all_records, profile

import harness_kernel.assurance as assurance_module
import harness_kernel.authority as authority_module
import harness_kernel.providers as providers_module
import harness_kernel.routing as routing_module
import harness_kernel.serialization as serialization_module
import harness_kernel.telemetry as telemetry_module
from harness_kernel.assurance import AssuranceDecision, assure_quality, create_critique
from harness_kernel.authority import (
    AuthorityAction,
    AuthorityDecision,
    AuthorityScope,
    authority_snapshot,
    authorize_decision,
    check_decision,
    check_invocation_authority,
    check_transition,
)
from harness_kernel.errors import (
    ContractValidationError,
    DeserializationError,
    FailureCategory,
    FailureDetail,
    SerializationError,
)
from harness_kernel.models import (
    CapabilityInvocation,
    CapabilityManifest,
    CapabilityPrimaryType,
    CapabilityStatus,
    Complexity,
    Confidence,
    DataImpact,
    EvidenceKind,
    EvidenceResult,
    FreshnessStatus,
    Independence,
    InvocationStatus,
    LifecycleState,
    Ordering,
    QualityBand,
    RecordStatus,
    Redaction,
    RegistryOrigin,
    ResearchNeed,
    RouteKind,
    RouteStatus,
    SecurityImpact,
    SourceType,
    TaskDomain,
    TelemetryEventType,
    TelemetryPayload,
    VisualImportance,
)
from harness_kernel.providers import (
    DeterministicFailureProvider,
    DeterministicPartialProvider,
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
from harness_kernel.routing import MinimumRoutePolicy, RoutePolicyError, minimum_route
from harness_kernel.serialization import from_dict, from_json, to_dict, to_json, to_primitive
from harness_kernel.state import (
    AuthorityStatus,
    StatusDimensions,
    WorkStatus,
    can_transition,
    can_work_transition,
    transition,
    update_status,
    validate_status,
    validate_transition,
)
from harness_kernel.telemetry import TelemetryLog, create_event, redact_payload, redact_text

NOW = "2026-08-28T12:00:00Z"


def record(index: int) -> object:
    return all_records()[index]


def authority(**overrides: object) -> AuthorityScope:
    values: dict[str, object] = {
        "owner": "owner",
        "actor": "runner",
        "scopes": ("task:TASK-1", "capability:local.success"),
        "decisions": (AuthorityAction.TRANSITION, AuthorityAction.RETRY),
        "subject_owner": "owner",
        "operations": ("execute",),
        "conditions": ("fresh-evidence",),
        "delegation_chain": ("DELEGATION-1",),
        "subject_id": "INV-1",
        "issued_at": "2026-08-28T12:00:00Z",
        "expires_at": "2026-08-28T13:00:00Z",
    }
    values.update(overrides)
    return AuthorityScope(**values)


def invocation() -> CapabilityInvocation:
    return replace(
        record(4),
        operation="execute",
        capability_origin=RegistryOrigin.PROJECT,
        invocation_status=InvocationStatus.REQUESTED,
        trace_context=(
            ("trace_id", "TRACE-1"),
            ("attempt", "2"),
        ),
        started_at=NOW,
    )


def manifest(
    capability_id: str,
    *,
    primary_type: CapabilityPrimaryType = CapabilityPrimaryType.SPECIALIST,
    status: CapabilityStatus = CapabilityStatus.VERIFIED,
    domains: tuple[str, ...] = ("ENGINEERING",),
    minimum: Complexity = Complexity.SMALL,
    activates: tuple[str, ...] = (),
    do_not_activate: tuple[str, ...] = (),
    version: str = "1.0.0",
) -> CapabilityManifest:
    base = record(3)
    assert isinstance(base, CapabilityManifest)
    return replace(
        base,
        capability_id=capability_id,
        primary_type=primary_type,
        status=status,
        version=version,
        scope=replace(
            base.scope,
            domains=domains,
            minimum_task_class=minimum,
            activates_when=activates,
            do_not_activate_when=do_not_activate,
        ),
        record=replace(base.record, status=RecordStatus.CURRENT),
    )


def route_profile(**overrides: object):
    values: dict[str, object] = {
        "task_id": "TASK-ROUTE-BOUNDARY",
        "run_id": "RUN-ROUTE-BOUNDARY",
        "objective": "validate local contract",
        "requested_outcome": "a deterministic validation result",
        "domain": TaskDomain.ENGINEERING,
        "complexity": Complexity.SMALL,
        "risk": "LOW",
        "visual_importance": VisualImportance.NONE,
        "security_impact": SecurityImpact.NONE,
        "data_impact": DataImpact.LOCAL,
        "research_need": ResearchNeed.NONE,
        "confidence": Confidence.HIGH,
    }
    values.update(overrides)
    return replace(profile(), **values)


def assurance_packet():
    verification = record(7)
    evidence = record(6)
    artifact = record(5)
    critique = create_critique(verification, evidence=(evidence,), artifacts=(artifact,))
    return verification, critique, evidence, artifact


def event(
    event_id: str = "EVT-BOUNDARY-1",
    *,
    sequence: int = 1,
    previous: str | None = None,
    timestamp: str = NOW,
    event_type: TelemetryEventType | str = TelemetryEventType.TOOL_RESULT,
    **kwargs: object,
):
    return create_event(
        event_id=event_id,
        event_sequence=sequence,
        timestamp=timestamp,
        task_id="TASK-TELEMETRY-BOUNDARY",
        run_id="RUN-TELEMETRY-BOUNDARY",
        event_type=event_type,
        previous_event_digest=previous,
        **kwargs,
    )


def test_authority_scope_normalizes_and_deduplicates_grants_without_mutation() -> None:
    value = authority(
        scopes=(" task:TASK-1 ", "", "task:TASK-1", "capability:local.success"),
        decisions=("retry", AuthorityAction.RETRY),
        operations=(" execute ", "execute"),
        conditions=("fresh-evidence", "fresh-evidence"),
        delegation_chain=(" DELEGATION-1 ",),
        subject_type=" invocation ",
        subject_id=" INV-1 ",
    )

    assert value.scopes == ("task:TASK-1", "capability:local.success")
    assert value.decisions == (AuthorityAction.RETRY, AuthorityAction.RETRY)
    assert value.operations == ("execute",)
    assert value.subject_type == "INVOCATION"
    assert value.subject_id == "INV-1"
    assert value.conditions == ("fresh-evidence",)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"owner": ""}, "owner"),
        ({"actor": ""}, "actor"),
        ({"subject_type": ""}, "subject type"),
        ({"subject_id": ""}, "subject id"),
        ({"scopes": ("ok", 1)}, "scopes"),
        ({"decisions": ("UNKNOWN",)}, "unknown authority action"),
    ),
)
def test_authority_scope_rejects_malformed_security_grants(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        authority(**kwargs)


def test_authority_decision_and_check_alias_properties_preserve_contract() -> None:
    decision = AuthorityDecision(
        action="retry",
        owner="owner",
        actor="runner",
        scope=("task:TASK-1", "task:TASK-1"),
        evidence_refs=(" EVID-1 ", "EVID-1"),
    )
    checked = authorize_decision(decision, authority())

    assert decision.action is AuthorityAction.RETRY
    assert decision.scope == ("task:TASK-1",)
    assert decision.evidence_refs == ("EVID-1",)
    assert checked.allowed is True
    assert checked.authorized is True
    assert checked.ok is True


def test_authority_private_normalizers_fail_closed_and_cover_wildcards() -> None:
    assert authority_module._strings(("", "x", "x")) == ("x",)
    assert authority_module._covers(("task:*",), ("task:TASK-1",)) == ()
    assert authority_module._covers(("*",), ("anything",)) == ()
    assert authority_module._covers(("task:TASK-1",), ("task:TASK-2",)) == ("task:TASK-2",)
    assert authority_module._covers(("x",), ()) == ()
    assert authority_module._timestamp(None) is None
    assert authority_module._state("blocked") is LifecycleState.BLOCKED
    with pytest.raises(TypeError):
        authority_module._strings((object(),))
    with pytest.raises(TypeError):
        authority_module._action(object())
    with pytest.raises((TypeError, ValueError)):
        authority_module._state(object())
    with pytest.raises(ValueError, match="timezone"):
        authority_module._timestamp("2026-08-28T12:00:00")


@pytest.mark.parametrize(
    ("action", "kwargs", "code"),
    (
        (AuthorityAction.BLOCK, {}, "MISSING_SCOPE"),
        (AuthorityAction.BLOCK, {"required_scope": ("task:TASK-2",)}, "MISSING_SCOPE"),
        (AuthorityAction.FINALIZE, {"required_scope": ("task:TASK-1",)}, "UNAUTHORIZED_DECISION"),
        (
            AuthorityAction.FINALIZE,
            {"required_scope": ("task:TASK-1",), "evidence_refs": ()},
            "UNAUTHORIZED_DECISION",
        ),
        (
            AuthorityAction.APPROVE,
            {"required_scope": ("task:TASK-1",), "evidence_refs": ("EVID-1",)},
            "UNAUTHORIZED_DECISION",
        ),
    ),
)
def test_check_decision_reports_missing_scope_and_grant_before_sensitive_actions(
    action: AuthorityAction, kwargs: dict[str, object], code: str
) -> None:
    result = check_decision(authority(), action, **kwargs)

    assert result.allowed is False
    assert result.code == code
    assert result.required_scope == tuple(kwargs.get("required_scope", ()))


def test_check_decision_reports_self_approval_missing_evidence_and_human_gate() -> None:
    finalizer = authority(
        actor="owner",
        decisions=(AuthorityAction.FINALIZE, AuthorityAction.APPROVE),
    )
    self_approval = check_decision(
        finalizer,
        AuthorityAction.FINALIZE,
        required_scope=("task:TASK-1",),
        evidence_refs=("EVID-1",),
    )
    missing_evidence = check_decision(
        authority(decisions=(AuthorityAction.FINALIZE,)),
        AuthorityAction.FINALIZE,
        required_scope=("task:TASK-1",),
    )
    human_required = check_decision(
        authority(decisions=(AuthorityAction.RETRY,)),
        AuthorityAction.RETRY,
        required_scope=("task:TASK-1",),
        human_required=True,
    )
    allowed = check_decision(
        authority(decisions=(AuthorityAction.APPROVE,), human=True, subject_owner="someone-else"),
        AuthorityAction.APPROVE,
        required_scope=("task:TASK-1",),
        evidence_refs=("EVID-1",),
        human_required=True,
    )

    assert self_approval.code == "SELF_APPROVAL"
    assert missing_evidence.code == "MISSING_EVIDENCE"
    assert human_required.code == "HUMAN_AUTHORITY_REQUIRED"
    assert allowed.allowed is True


def test_check_decision_rejects_forged_blank_actor_and_wrong_authority_type() -> None:
    forged = object.__new__(AuthorityScope)
    object.__setattr__(forged, "owner", " ")
    object.__setattr__(forged, "actor", "runner")
    result = check_decision(forged, AuthorityAction.RETRY, required_scope=("task:TASK-1",))

    assert result.code == "INVALID_ACTOR"
    with pytest.raises(TypeError, match="AuthorityScope"):
        check_decision(object(), AuthorityAction.RETRY, required_scope=("task:TASK-1",))


@pytest.mark.parametrize(
    ("changes", "code"),
    (
        ({"task_id": ""}, "INVALID_SUBJECT"),
        ({"operation": ""}, "MISSING_OPERATION"),
        ({"authority": authority(subject_type="TASK")}, "INVALID_SUBJECT_TYPE"),
        ({"at": "not-a-time"}, "INVALID_AUTHORITY_TIME"),
        ({"at": "2026-08-28T11:59:59Z"}, "AUTHORITY_NOT_YET_VALID"),
        ({"at": "2026-08-28T13:00:00Z"}, "AUTHORITY_EXPIRED"),
        ({"invocation_id": "INV-OTHER"}, "AUTHORITY_SUBJECT_MISMATCH"),
        ({"operation": "inspect"}, "UNAUTHORIZED_OPERATION"),
        ({"authority": authority(operations=())}, "MISSING_OPERATION_GRANT"),
        ({"required_scope": ("task:TASK-2",)}, "MISSING_SCOPE"),
        ({"required_conditions": ("approved",)}, "AUTHORITY_CONDITION_UNMET"),
        ({"delegation_ref": "DELEGATION-MISSING"}, "DELEGATION_MISSING"),
    ),
)
def test_invocation_authority_rejects_each_boundary_before_provider_call(
    changes: dict[str, object], code: str
) -> None:
    values: dict[str, object] = {
        "authority": authority(),
        "task_id": "TASK-1",
        "invocation_id": "INV-1",
        "capability_id": "local.success",
        "operation": "execute",
        "required_scope": ("task:TASK-1", "capability:local.success"),
        "at": "2026-08-28T12:30:00Z",
    }
    values.update(changes)
    result = check_invocation_authority(**values)

    assert result.allowed is False
    assert result.code == code


def test_invocation_authority_allows_wildcard_condition_and_delegation() -> None:
    result = check_invocation_authority(
        authority(
            scopes=("task:*", "capability:*"),
            conditions=("evidence:*",),
        ),
        task_id="TASK-1",
        invocation_id="INV-1",
        capability_id="local.success",
        operation="execute",
        required_scope=("task:TASK-1", "capability:local.success"),
        required_conditions=("evidence:fresh",),
        delegation_ref="DELEGATION-1",
        at="2026-08-28T12:30:00Z",
    )

    assert result.allowed is True
    assert result.action is AuthorityAction.TRANSITION


def test_authority_snapshot_is_canonical_and_rejects_non_invocation_targets() -> None:
    value = authority_snapshot(
        authority(),
        subject_id="INV-1",
        operation="execute",
        required_scope=("capability:local.success", "task:TASK-1"),
    )
    repeated = authority_snapshot(
        authority(),
        subject_id="INV-1",
        operation="execute",
        required_scope=("capability:local.success", "task:TASK-1"),
    )

    assert value == repeated
    assert value.digest.startswith("sha256:")
    with pytest.raises(ValueError, match="subject and operation"):
        authority_snapshot(authority(), subject_id="", operation="execute")
    with pytest.raises(ValueError, match="invalid subject type"):
        authority_snapshot(authority(subject_type="TASK"), subject_id="INV-1", operation="execute")


def test_check_transition_maps_block_replan_finalize_and_invalid_state_paths() -> None:
    blocked = check_transition(
        LifecycleState.NEW,
        LifecycleState.BLOCKED,
        authority(decisions=(AuthorityAction.BLOCK,)),
        required_scope=("task:TASK-1",),
    )
    replan = check_transition(
        LifecycleState.BLOCKED,
        LifecycleState.ROUTED,
        authority(decisions=(AuthorityAction.REPLAN,)),
        required_scope=("task:TASK-1",),
    )
    finalize = check_transition(
        LifecycleState.PASSED,
        LifecycleState.DELIVERED,
        authority(decisions=(AuthorityAction.FINALIZE,)),
        required_scope=("task:TASK-1",),
        evidence_refs=("EVID-1",),
    )
    explicit = check_transition(
        LifecycleState.ROUTED,
        LifecycleState.PLANNED,
        authority(decisions=(AuthorityAction.RETRY,)),
        required_scope=("task:TASK-1",),
        action="retry",
    )
    invalid_edge = check_transition(
        LifecycleState.NEW,
        LifecycleState.DELIVERED,
        authority(),
        required_scope=("task:TASK-1",),
        action="retry",
    )
    invalid_state = check_transition("UNKNOWN", LifecycleState.NEW, authority())

    assert blocked.action is AuthorityAction.BLOCK
    assert replan.action is AuthorityAction.REPLAN
    assert finalize.action is AuthorityAction.FINALIZE
    assert explicit.action is AuthorityAction.RETRY
    assert invalid_edge.code == "INVALID_TRANSITION"
    assert invalid_edge.action is AuthorityAction.RETRY
    assert invalid_state.code == "INVALID_STATE"


def test_authorize_decision_requires_explicit_grant_and_preserves_scope() -> None:
    decision = AuthorityDecision(
        action=AuthorityAction.RETRY,
        owner="owner",
        actor="runner",
        scope=("task:TASK-1",),
    )

    denied = authorize_decision(decision)

    assert denied.code == "AUTHORITY_REQUIRED"
    assert denied.required_scope == ("task:TASK-1",)
    with pytest.raises(TypeError, match="AuthorityDecision"):
        authorize_decision(object())


def test_state_rejects_unknown_lifecycle_and_work_edges_without_mutation() -> None:
    assert can_transition("NEW", "CLASSIFIED")
    assert not can_transition("unknown", "CLASSIFIED")
    assert not can_transition("NEW", "unknown")
    assert can_work_transition(WorkStatus.PENDING, "READY")
    assert can_work_transition(WorkStatus.RUNNING, WorkStatus.CANCELLED)
    assert not can_work_transition("unknown", WorkStatus.READY)
    assert not can_work_transition(WorkStatus.DONE, WorkStatus.READY)

    invalid_current = validate_transition("unknown", "CLASSIFIED")
    invalid_target = validate_transition("NEW", "unknown")
    invalid_edge = validate_transition("NEW", "DELIVERED")
    valid_edge = transition("NEW", "CLASSIFIED")

    assert invalid_current.findings[0].message == "$.current"
    assert invalid_target.findings[0].message == "$.target"
    assert invalid_edge.findings[0].message == "$.transition"
    assert valid_edge is LifecycleState.CLASSIFIED
    with pytest.raises(ValueError, match="invalid lifecycle transition"):
        transition("NEW", "DELIVERED")


def test_state_validation_catches_each_invalid_dimension_and_update_is_immutable() -> None:
    original = StatusDimensions(
        work=WorkStatus.RUNNING,
        lifecycle=LifecycleState.EXECUTING,
        verification=EvidenceResult.NOT_RUN,
        quality=QualityBand.PARTIAL,
        authority=AuthorityStatus.PENDING,
    )
    updated = update_status(original, work=WorkStatus.REVIEW, authority=AuthorityStatus.CONFIRMED)
    invalid = StatusDimensions(
        work="UNKNOWN",
        lifecycle="UNKNOWN",
        verification="NOT_A_VERIFICATION_STATUS",
        quality="UNKNOWN",
        authority="NOT_AN_AUTHORITY_STATUS",
    )

    result = validate_status(invalid)

    assert updated is not original
    assert original.work is WorkStatus.RUNNING
    assert updated.work is WorkStatus.REVIEW
    assert updated.lifecycle is original.lifecycle
    assert validate_status(original).is_valid
    assert len(result.findings) == 5
    assert validate_status(object()).findings[0].code.value == "INVALID_TYPE"
    with pytest.raises(TypeError, match="StatusDimensions"):
        update_status(object())


def test_create_critique_materializes_repair_findings_and_continue_strengths() -> None:
    verification = record(7)
    evidence = record(6)
    artifact = record(5)
    passing = create_critique(verification, evidence=(evidence,), artifacts=(artifact,))
    failing = create_critique(
        replace(verification, recommendation="FAIL", not_run=("P7-MISSING",)),
        evidence=(evidence,),
        artifacts=(artifact,),
        timestamp="2026-08-28T13:00:00Z",
    )

    assert passing.findings == ()
    assert passing.strengths
    assert passing.stop_recommendation.value == "CONTINUE"
    assert failing.findings[0].severity.value == "HIGH"
    assert failing.stop_recommendation.value == "REPAIR"
    assert failing.missing_evidence == ("P7-MISSING",)
    assert failing.residual_risk == "HIGH"


@pytest.mark.parametrize(
    ("verification_change", "critique_change", "message"),
    (
        ({}, {"record": replace(record(8).record, status=RecordStatus.STALE)}, "critique"),
        ({"record": replace(record(7).record, status=RecordStatus.STALE)}, {}, "verification"),
        ({}, {"task_id": "TASK-OTHER"}, "correlation"),
        ({}, {"reviewed_reports": ()}, "current verification"),
        ({}, {"reviewed_artifacts": ()}, "artifact scope"),
        (
            {},
            {
                "reviewer": replace(
                    create_critique(record(7)).reviewer,
                    independence=Independence.INDEPENDENT,
                )
            },
            "reviewer metadata",
        ),
    ),
)
def test_assurance_rejects_stale_or_misaligned_review_packets(
    verification_change: dict[str, object], critique_change: dict[str, object], message: str
) -> None:
    verification, critique, evidence, artifact = assurance_packet()
    if verification_change:
        verification = replace(verification, **verification_change)
    if critique_change:
        critique = replace(critique, **critique_change)

    result = assure_quality(verification, critique, evidence=(evidence,), artifacts=(artifact,))

    assert result.decision is AssuranceDecision.FAILED
    assert message in result.reason


def test_assurance_rejects_untyped_or_unbound_packet_content() -> None:
    verification, critique, evidence, artifact = assurance_packet()
    untyped_evidence = assure_quality(
        verification, critique, evidence=(object(),), artifacts=(artifact,)
    )
    missing_digest = assure_quality(
        verification,
        replace(critique, reviewer=replace(critique.reviewer, blind_packet_digest=None)),
        evidence=(evidence,),
        artifacts=(artifact,),
    )
    wrong_digest = assure_quality(
        verification,
        replace(critique, reviewer=replace(critique.reviewer, blind_packet_digest="sha256:wrong")),
        evidence=(evidence,),
        artifacts=(artifact,),
    )
    mismatched_bar = assure_quality(
        verification,
        replace(critique, quality_bar_ref="P7-OTHER"),
        evidence=(evidence,),
        artifacts=(artifact,),
    )
    empty_packet_critique = create_critique(verification, evidence=(), artifacts=())
    missing_packet = assure_quality(verification, empty_packet_critique, evidence=(), artifacts=())
    evidence_only_critique = create_critique(verification, evidence=(evidence,), artifacts=())
    mismatched_artifact = assure_quality(
        verification, evidence_only_critique, evidence=(evidence,), artifacts=()
    )
    artifact_identity_mismatch = assure_quality(
        verification,
        create_critique(
            verification,
            evidence=(evidence,),
            artifacts=(replace(artifact, artifact_id="ART-OTHER"),),
        ),
        evidence=(evidence,),
        artifacts=(replace(artifact, artifact_id="ART-OTHER"),),
    )

    assert untyped_evidence.decision is AssuranceDecision.FAILED
    assert "typed evidence" in untyped_evidence.reason
    assert missing_digest.decision is AssuranceDecision.FAILED
    assert "blind verification digest" in missing_digest.reason
    assert wrong_digest.decision is AssuranceDecision.FAILED
    assert "does not match" in wrong_digest.reason
    assert mismatched_bar.decision is AssuranceDecision.BLOCKED
    assert missing_packet.decision is AssuranceDecision.BLOCKED
    assert mismatched_artifact.decision is AssuranceDecision.BLOCKED
    assert artifact_identity_mismatch.decision is AssuranceDecision.FAILED
    assert "artifact packet" in artifact_identity_mismatch.reason


def test_assurance_rejects_invalid_evidence_links_and_independence_handoff() -> None:
    verification, critique, evidence, artifact = assurance_packet()
    invalid_evidence = replace(evidence, evidence_id="EVID-OTHER")
    bad_link_critique = create_critique(
        verification, evidence=(invalid_evidence,), artifacts=(artifact,)
    )
    bad_links = assure_quality(
        verification,
        bad_link_critique,
        evidence=(invalid_evidence,),
        artifacts=(artifact,),
    )
    independent_required = assure_quality(
        verification,
        critique,
        require_independent=True,
        evidence=(evidence,),
        artifacts=(artifact,),
    )
    independent_human = replace(
        critique,
        independence=Independence.INDEPENDENT,
        reviewer=replace(critique.reviewer, independence=Independence.INDEPENDENT),
        record=replace(
            critique.record,
            provenance=replace(critique.record.provenance, source_type=SourceType.HUMAN),
        ),
    )
    accepted_independent = assure_quality(
        verification,
        independent_human,
        require_independent=True,
        evidence=(evidence,),
        artifacts=(artifact,),
    )

    assert bad_links.decision is AssuranceDecision.FAILED
    assert "link gate" in bad_links.reason
    assert independent_required.decision is AssuranceDecision.BLOCKED
    assert accepted_independent.decision is AssuranceDecision.QUALITY_ACCEPTED


@pytest.mark.parametrize(
    ("verification_change", "expected"),
    (
        ({"recommendation": "FAIL"}, AssuranceDecision.FAILED),
        ({"claims": (replace(record(7).claims[0], status="FAIL"),)}, AssuranceDecision.FAILED),
        ({"recommendation": "PARTIAL"}, AssuranceDecision.BLOCKED),
        ({"not_run": ("NOT-RUN",)}, AssuranceDecision.BLOCKED),
        ({"unknown": ("UNKNOWN",)}, AssuranceDecision.BLOCKED),
    ),
)
def test_assurance_maps_failed_partial_and_unknown_verification_to_safe_stop(
    verification_change: dict[str, object], expected: AssuranceDecision
) -> None:
    verification, critique, evidence, artifact = assurance_packet()
    changed = replace(verification, **verification_change)
    critique = create_critique(changed, evidence=(evidence,), artifacts=(artifact,))

    result = assure_quality(changed, critique, evidence=(evidence,), artifacts=(artifact,))

    assert result.decision is expected
    assert result.quality_band in {QualityBand.FAILED, QualityBand.BLOCKED}


def test_assurance_repair_required_and_quality_report_stop_are_observable() -> None:
    verification, critique, evidence, artifact = assurance_packet()
    open_finding = replace(
        critique.findings[0]
        if critique.findings
        else create_critique(
            replace(verification, recommendation="FAIL"),
            evidence=(evidence,),
            artifacts=(artifact,),
        ).findings[0],
        disposition="OPEN",
        severity="HIGH",
    )
    repaired_review = replace(
        critique,
        findings=(open_finding,),
        reviewer=replace(
            critique.reviewer,
            blind_packet_digest=critique.reviewer.blind_packet_digest,
        ),
    )
    # A passing verification with an open material critique is the repair branch.
    result = assure_quality(
        verification,
        repaired_review,
        evidence=(evidence,),
        artifacts=(artifact,),
    )
    report = assurance_module.build_quality_report(verification, repaired_review, result)

    assert result.decision is AssuranceDecision.REPAIR_REQUIRED
    assert result.quality_band is QualityBand.PARTIAL
    assert report.decision.value == "STOP"
    assert report.gates[0].status.value == "BLOCKED"
    assert report.open_findings == (open_finding.finding_id,)


def test_assure_quality_rejects_untyped_reports_and_build_report_acceptance_is_immutable() -> None:
    verification, critique, evidence, artifact = assurance_packet()
    invalid = assure_quality(object(), critique, evidence=(evidence,), artifacts=(artifact,))
    accepted = assure_quality(verification, critique, evidence=(evidence,), artifacts=(artifact,))
    report = assurance_module.build_quality_report(verification, critique, accepted)

    assert invalid.decision is AssuranceDecision.FAILED
    assert accepted.decision is AssuranceDecision.QUALITY_ACCEPTED
    assert report.decision.value == "DELIVER"
    assert report.quality_band is QualityBand.ACCEPTABLE
    assert report.gates[0].status.value == "PASS"


def provider_descriptor_kwargs(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "provider_id": "p",
        "version": "1.0.0",
        "capability_ids": ("cap",),
        "operations": ("execute",),
    }
    values.update(changes)
    return values


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        (provider_descriptor_kwargs(provider_id=""), "identity"),
        (provider_descriptor_kwargs(version=""), "identity"),
        (provider_descriptor_kwargs(capability_ids=()), "capability"),
        (provider_descriptor_kwargs(operations=()), "operation"),
        (provider_descriptor_kwargs(capability_ids=("cap", 1)), "non-empty"),
        (provider_descriptor_kwargs(execution_mode="NETWORK"), "allowlist"),
        (provider_descriptor_kwargs(origin=RegistryOrigin.SYSTEM), "project-origin"),
        (provider_descriptor_kwargs(local_only=False), "project-local"),
        (provider_descriptor_kwargs(supports_cancellation="yes"), "boolean"),
        (provider_descriptor_kwargs(limits=(("x", 1), ("x", 2))), "unique"),
        (provider_descriptor_kwargs(limits=(("x", -1),)), "non-negative"),
        (
            provider_descriptor_kwargs(security_characteristics=("project-local",)),
            "insufficient",
        ),
    ),
)
def test_provider_descriptor_rejects_unsafe_or_incomplete_metadata(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ProviderDescriptor(**kwargs)


def test_provider_descriptor_deduplicates_metadata_and_registration_is_immutable() -> None:
    descriptor = ProviderDescriptor(
        provider_id="provider",
        version="1.0.0",
        capability_ids=("cap", "cap"),
        operations=("execute", "execute"),
        limits=(("budget", 1),),
        security_characteristics=(
            "project-local",
            "non-networked",
            "non-shell",
            "non-privileged",
            "non-shell",
        ),
    )
    provider = DeterministicSuccessProvider(provider_id="provider")
    registration = ProviderRegistration(
        provider.descriptor, provider, ProviderAvailability.AVAILABLE
    )

    assert descriptor.capability_ids == ("cap",)
    assert descriptor.operations == ("execute",)
    assert descriptor.security_characteristics[-1] == "non-privileged"
    assert registration.usable is True
    assert (
        ProviderRegistration(provider.descriptor, provider, ProviderAvailability.BLOCKED).usable
        is False
    )


def valid_provider_result(**overrides: object) -> ProviderExecutionResult:
    values: dict[str, object] = {
        "provider_id": "provider",
        "invocation_id": "INV-1",
        "status": ProviderResultStatus.SUCCEEDED,
        "output": {"value": 1},
        "output_contract": "LocalExecutionResult",
        "output_digest": None,
    }
    values.update(overrides)
    return ProviderExecutionResult(**values)


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"provider_id": ""}, "identity"),
        ({"invocation_id": ""}, "identity"),
        ({"output_contract": ""}, "contract"),
        ({"duration_ms": -1}, "duration"),
        ({"attempt": 0}, "attempt"),
        ({"status": "UNKNOWN"}, "UNKNOWN"),
        ({"output": {"value": 1}, "output_digest": "sha256:wrong"}, "digest"),
        ({"output": None, "output_digest": "sha256:present"}, "requires output"),
        (
            {
                "status": ProviderResultStatus.FAILED,
                "output": None,
                "failure": None,
            },
            "typed failure",
        ),
        (
            {
                "status": ProviderResultStatus.SUCCEEDED,
                "failure": FailureDetail(FailureCategory.PROVIDER, "ERR", "failure"),
            },
            "cannot carry",
        ),
        ({"artifact_refs": ("",)}, "artifact_refs"),
        ({"evidence_refs": (1,)}, "evidence_refs"),
        ({"telemetry_refs": ("",)}, "telemetry_refs"),
        ({"resource_observations": (("only-one",),)}, "string pairs"),
    ),
)
def test_provider_execution_result_rejects_corrupt_output_failure_or_observation_metadata(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        valid_provider_result(**changes)


def test_provider_execution_result_normalizes_digest_status_and_reference_order() -> None:
    failure = FailureDetail(
        category="TIMEOUT",
        code="TIMEOUT",
        message="provider timed out",
        retryable=True,
        refs=("INV-1",),
    )
    result = valid_provider_result(
        status="FAILED",
        output=None,
        failure=failure,
        artifact_refs=("ART-1", "ART-1"),
        evidence_refs=("EVID-1",),
        telemetry_refs=("EVT-1",),
        resource_observations=(("duration_ms", "5"),),
    )

    assert result.status is ProviderResultStatus.FAILED
    assert result.output_digest is None
    assert result.artifact_refs == ("ART-1",)
    assert result.failure is failure
    assert result.resource_observations == (("duration_ms", "5"),)


def test_provider_digest_and_attempt_helpers_cover_safe_canonicalization() -> None:
    assert digest_output({"b": 2, "a": 1}) == digest_output({"a": 1, "b": 2})
    assert providers_module._attempt(invocation()) == 2
    assert (
        providers_module._attempt(replace(invocation(), trace_context=(("attempt", "bad"),))) == 1
    )
    assert providers_module._attempt(replace(invocation(), trace_context=())) == 1
    assert providers_module._fixture_observation_timestamps(
        replace(invocation(), started_at=None)
    ) == (
        "1970-01-01T00:00:00Z",
        "1970-01-01T00:00:00Z",
    )
    with pytest.raises((TypeError, SerializationError)):
        digest_output({1: "non-string-key"})


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"duration_ms": -1}, "duration"),
        ({"duration_ms": 60_001}, "duration"),
        ({"delay_ms": -1}, "delay"),
        ({"delay_ms": 60_001}, "delay"),
        ({"output_contract": "Other"}, "LocalExecutionResult"),
        ({"result_provider_id": ""}, "identity"),
        ({"emit_observed_timestamps": "yes"}, "boolean"),
    ),
)
def test_success_provider_rejects_unbounded_fixture_configuration(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        DeterministicSuccessProvider(**changes)


def test_success_provider_reports_attempt_timestamp_and_optional_observations() -> None:
    provider = DeterministicSuccessProvider(
        provider_id="local.success.boundary",
        duration_ms=7,
        result_provider_id="result-provider",
        emit_observed_timestamps=False,
    )
    result = provider.execute(invocation())

    assert result.status is ProviderResultStatus.SUCCEEDED
    assert result.provider_id == "result-provider"
    assert result.attempt == 2
    assert result.started_at is None
    assert result.ended_at is None
    assert result.output_digest == digest_output(result.output)
    assert result.output["operation"] == "execute"  # type: ignore[index]


def test_failure_partial_and_retry_providers_preserve_typed_failure_paths() -> None:
    failure = DeterministicFailureProvider(provider_id="failure-boundary").execute(invocation())
    partial = DeterministicPartialProvider(provider_id="partial-boundary").execute(invocation())
    retry = DeterministicRetryProvider(failures_before_success=2, provider_id="retry-boundary")
    first = retry.execute(replace(invocation(), trace_context=(("attempt", "1"),)))
    final = retry.execute(replace(invocation(), trace_context=(("attempt", "3"),)))

    assert failure.status is ProviderResultStatus.FAILED
    assert failure.failure is not None
    assert failure.failure.code == "FIXTURE_FAILURE"
    assert partial.status is ProviderResultStatus.PARTIAL
    assert partial.failure is not None
    assert partial.failure.code == "FIXTURE_PARTIAL"
    assert first.failure is not None and first.failure.retryable is True
    assert first.failure.attempt == 1
    assert final.status is ProviderResultStatus.SUCCEEDED
    assert final.attempt == 3


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"failures_before_success": -1}, "non-negative"),
        ({"failures_before_success": True}, "non-negative"),
        ({"duration_ms": -1}, "duration_ms"),
        ({"delay_ms": 60_001}, "delay_ms"),
    ),
)
def test_retry_provider_rejects_invalid_retry_configuration(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        DeterministicRetryProvider(**changes)


def test_provider_registry_is_explicit_immutable_and_missing_resolution_is_safe() -> None:
    success = DeterministicSuccessProvider(provider_id="registry-success")
    registry = ProviderRegistry().register(success)
    unavailable = registry.with_availability(success.provider_id, ProviderAvailability.UNAVAILABLE)
    blocked = registry.with_availability(success.provider_id, ProviderAvailability.BLOCKED)

    assert registry.registrations == (registry.registrations[0],)
    assert registry.resolve(success.provider_id) is success
    assert registry.resolve("missing") is None
    assert registry.resolve(success.provider_id, operation="missing") is None
    assert registry.resolve(success.provider_id, capability_id="missing") is None
    assert registry.providers_for("local.direct") == (success.provider_id,)
    assert unavailable.inspect(success.provider_id).usable is False
    assert blocked.inspect(success.provider_id).availability is ProviderAvailability.BLOCKED
    assert registry.inspect("missing").availability is ProviderAvailability.UNAVAILABLE
    with pytest.raises(KeyError, match="not registered"):
        registry.with_availability("missing", ProviderAvailability.AVAILABLE)


def test_provider_registry_rejects_custom_mismatched_duplicate_and_bad_registrations() -> None:
    class CustomProvider:
        @property
        def descriptor(self) -> ProviderDescriptor:
            return DeterministicSuccessProvider(provider_id="custom").descriptor

        def execute(
            self,
            invocation: CapabilityInvocation,
            manifest: CapabilityManifest | None = None,
        ):
            del invocation, manifest
            return None

    with pytest.raises(ValueError, match="built-in"):
        ProviderRegistry().register(CustomProvider())
    success = DeterministicSuccessProvider(provider_id="duplicate")
    registry = ProviderRegistry().register(success)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(success)
    with pytest.raises(TypeError, match="typed registration"):
        ProviderRegistry((object(),))
    with pytest.raises(ValueError, match="built-in"):
        ProviderRegistry(
            (
                ProviderRegistration(
                    success.descriptor,
                    CustomProvider(),
                    ProviderAvailability.AVAILABLE,
                ),
            )
        )
    with pytest.raises(ValueError, match="metadata"):
        ProviderRegistry(
            (
                ProviderRegistration(
                    DeterministicFailureProvider().descriptor,
                    success,
                    ProviderAvailability.AVAILABLE,
                ),
            )
        )


def test_route_policy_rejects_negative_budgets_and_helper_matching_is_conservative() -> None:
    with pytest.raises(RoutePolicyError, match="skill"):
        MinimumRoutePolicy(max_skill_kernels=-1)
    with pytest.raises(RoutePolicyError, match="parallelism"):
        MinimumRoutePolicy(default_parallelism_budget=-1)

    assert routing_module._tokens("API-safe check") == frozenset({"api-safe", "check"})
    assert routing_module._condition_hit("api-safe", "An API-safe check")
    assert routing_module._condition_hit("api safe", "An API safe check")
    assert not routing_module._condition_hit("database migration", "fix a button")
    assert routing_module._complexity_at_least(Complexity.CRITICAL, Complexity.MEDIUM)
    assert not routing_module._complexity_at_least(Complexity.SMALL, Complexity.LARGE)
    assert routing_module._dedupe(("x", "", "x", "y")) == ("x", "y")
    assert routing_module._safe_code("not safe!*value") == "not_safe_value"
    assert routing_module._safe_id("ROUTE", "") == "ROUTE"


def test_matching_manifest_rejects_domain_complexity_and_do_not_activation() -> None:
    task = route_profile(domain=TaskDomain.API, complexity=Complexity.SMALL)
    text = routing_module._profile_text(task)
    domain_mismatch = manifest("domain-mismatch", domains=("SECURITY",))
    complexity_mismatch = manifest("complexity-mismatch", minimum=Complexity.LARGE)
    forbidden = manifest(
        "forbidden",
        domains=("API",),
        activates=("api",),
        do_not_activate=("migration",),
    )

    assert not routing_module._matching_manifest(domain_mismatch, task, text)
    assert not routing_module._matching_manifest(complexity_mismatch, task, text)
    assert not routing_module._matching_manifest(
        forbidden,
        replace(task, objective="API migration"),
        "API migration",
    )


def test_matching_manifest_requires_meaningful_general_phrase_but_allows_domain_phrase() -> None:
    general_single = manifest("general-single", domains=("GENERAL",), activates=("security",))
    general_phrase = manifest(
        "general-phrase", domains=("GENERAL",), activates=("security review",)
    )
    domain_phrase = manifest("domain-phrase", domains=("API",), activates=("API",))
    task = route_profile(domain=TaskDomain.API, objective="security review for an API")
    text = routing_module._profile_text(task)

    assert not routing_module._matching_manifest(general_single, task, text)
    assert routing_module._matching_manifest(general_phrase, task, text)
    assert routing_module._matching_manifest(domain_phrase, task, text)
    assert routing_module._matching_manifest(
        manifest("no-trigger", domains=("GENERAL",)), task, text
    )


def test_route_helpers_pick_highest_version_and_reject_invalid_profiles_safely() -> None:
    candidates = (
        manifest("same", version="1.0.0"),
        manifest("same", version="2.0.0"),
        manifest("other", primary_type=CapabilityPrimaryType.VERIFICATION),
    )
    picked = routing_module._pick(candidates, (CapabilityPrimaryType.SPECIALIST,))
    missing = routing_module._pick(candidates, (CapabilityPrimaryType.PROVIDER,))
    invalid = minimum_route(object(), decision_id="ROUTE-INVALID")
    invalid_id = minimum_route(
        replace(route_profile(), task_id="not valid!"), decision_id="ROUTE-INVALID-ID"
    )

    assert picked is not None and picked.version == "2.0.0"
    assert missing is None
    assert invalid.route_status is RouteStatus.REJECTED
    assert invalid.route_kind is RouteKind.DEGRADED
    assert invalid.unresolved == ("INVALID_PROFILE",)
    assert invalid_id.task_id == "TASK-REJECTED"


def test_route_explicit_provider_and_capability_failures_are_classified_without_execution() -> None:
    task = route_profile(research_need=ResearchNeed.FRESHNESS_REQUIRED)
    ordinary = manifest("ordinary", primary_type=CapabilityPrimaryType.SPECIALIST)
    rejected = manifest(
        "rejected", primary_type=CapabilityPrimaryType.PROVIDER, status=CapabilityStatus.REJECTED
    )
    deprecated = manifest(
        "deprecated",
        primary_type=CapabilityPrimaryType.PROVIDER,
        status=CapabilityStatus.DEPRECATED,
    )
    stale = replace(
        manifest("stale", primary_type=CapabilityPrimaryType.PROVIDER),
        record=replace(record(3).record, status=RecordStatus.STALE),
    )
    wrong_scope = manifest(
        "wrong-scope", primary_type=CapabilityPrimaryType.PROVIDER, domains=("SECURITY",)
    )
    registry = routing_module.CapabilityRegistry.from_manifests(
        (ordinary, rejected, deprecated, stale, wrong_scope)
    )

    type_mismatch = minimum_route(task, registry, explicit_provider="ordinary")
    rejected_provider = minimum_route(task, registry, explicit_provider="rejected")
    deprecated_provider = minimum_route(task, registry, explicit_provider="deprecated")
    stale_provider = minimum_route(task, registry, explicit_provider="stale")
    scope_provider = minimum_route(task, registry, explicit_provider="wrong-scope")
    missing_provider = minimum_route(task, registry, explicit_provider="missing")
    missing_capability = minimum_route(task, registry, explicit_capabilities=("missing",))
    rejected_capability = minimum_route(task, registry, explicit_capabilities=("rejected",))
    deprecated_capability = minimum_route(task, registry, explicit_capabilities=("deprecated",))
    stale_capability = minimum_route(task, registry, explicit_capabilities=("stale",))
    wrong_capability = minimum_route(task, registry, explicit_capabilities=("wrong-scope",))

    assert type_mismatch.route_status is RouteStatus.FALLBACK
    assert "PROVIDER_TYPE_MISMATCH" in type_mismatch.unresolved
    assert "PROVIDER_REJECTED" in rejected_provider.unresolved
    assert "PROVIDER_DEPRECATED" in deprecated_provider.unresolved
    assert "PROVIDER_UNAVAILABLE" in stale_provider.unresolved
    assert "PROVIDER_SCOPE_MISMATCH" in scope_provider.unresolved
    assert "PROVIDER_UNAVAILABLE" in missing_provider.unresolved
    assert "CAPABILITY_UNAVAILABLE" in missing_capability.unresolved
    assert "CAPABILITY_REJECTED" in rejected_capability.unresolved
    assert "CAPABILITY_DEPRECATED" in deprecated_capability.unresolved
    assert "CAPABILITY_UNAVAILABLE" in stale_capability.unresolved
    assert "CAPABILITY_SCOPE_MISMATCH" in wrong_capability.unresolved
    assert all(route.selected == () for route in (missing_provider, missing_capability))


def test_route_selects_specialist_verifier_provider_and_visual_optional_paths() -> None:
    task = route_profile(
        complexity=Complexity.LARGE,
        risk="HIGH",
        security_impact=SecurityImpact.MEDIUM,
        data_impact=DataImpact.PERSISTENT,
        visual_importance=VisualImportance.PRIMARY,
    )
    specialist = manifest("specialist", primary_type=CapabilityPrimaryType.SPECIALIST)
    verifier = manifest("verifier", primary_type=CapabilityPrimaryType.VERIFICATION)
    reviewer = manifest("reviewer", primary_type=CapabilityPrimaryType.REVIEWER)
    registry = routing_module.CapabilityRegistry.from_manifests((specialist, verifier, reviewer))
    selected = minimum_route(
        task,
        registry,
        available_tools=("pytest",),
        provider_constraints=("local",),
    )
    provider_manifest = manifest("provider", primary_type=CapabilityPrimaryType.PROVIDER)
    provider_registry = routing_module.CapabilityRegistry.from_manifests(
        (provider_manifest, verifier)
    )
    provider = minimum_route(
        route_profile(
            complexity=Complexity.SMALL,
            risk="LOW",
            security_impact=SecurityImpact.NONE,
            data_impact=DataImpact.LOCAL,
            visual_importance=VisualImportance.NONE,
            research_need=ResearchNeed.NONE,
        ),
        provider_registry,
        explicit_provider="provider",
        allow_fallback=False,
        native_tools=("python",),
    )

    assert selected.route_status is RouteStatus.SELECTED
    assert selected.route_kind is RouteKind.COMPOSED
    assert {item.capability_id for item in selected.selected} == {"specialist", "verifier"}
    assert selected.optional[0].capability_id == "reviewer"
    assert selected.compatibility.native_tools_considered == ("pytest",)
    assert selected.compatibility.provider_constraints == ("local",)
    assert provider.route_kind is RouteKind.PROVIDER
    assert provider.selected[0].capability_id == "provider"


def test_route_handles_unknown_confidence_no_verification_and_fallback_policy() -> None:
    unknown = route_profile(
        complexity=Complexity.CRITICAL,
        risk="UNKNOWN",
        confidence=Confidence.UNKNOWN,
        domain=TaskDomain.GENERAL,
    )
    no_fallback = MinimumRoutePolicy(allow_fallback=False)
    conditional = minimum_route(unknown, routing_module.CapabilityRegistry(), policy=no_fallback)
    fallback = minimum_route(
        route_profile(domain=TaskDomain.API, complexity=Complexity.MEDIUM),
        routing_module.CapabilityRegistry(),
        allow_fallback=True,
    )
    no_verification = minimum_route(
        route_profile(complexity=Complexity.MEDIUM), routing_module.CapabilityRegistry()
    )

    assert conditional.route_status is RouteStatus.CONDITIONAL
    assert conditional.fallback == "inspect-and-clarify-before-material-action"
    assert "CLASSIFICATION_UNCERTAIN" in conditional.unresolved
    assert fallback.route_status is RouteStatus.FALLBACK
    assert fallback.fallback == "direct-with-focused-verification"
    assert no_verification.route_status is RouteStatus.FALLBACK
    assert "VERIFICATION_UNAVAILABLE" in no_verification.unresolved


def test_route_direct_path_and_fallback_with_existing_non_activation_reason() -> None:
    direct = minimum_route(
        route_profile(complexity=Complexity.TRIVIAL, risk="LOW"),
        routing_module.CapabilityRegistry(),
    )
    out_of_scope = minimum_route(
        route_profile(domain=TaskDomain.API, objective="ordinary API change"),
        routing_module.CapabilityRegistry(),
        explicit_capabilities=("missing-capability",),
    )

    assert direct.route_status is RouteStatus.NO_SPECIAL_ROUTE
    assert direct.route_kind is RouteKind.DIRECT
    assert "trivial-local-scope" in direct.decision.non_activation_reasons
    assert out_of_scope.route_status is RouteStatus.FALLBACK
    assert "CAPABILITY_UNAVAILABLE" in out_of_scope.unresolved


class SerializationEnum(StrEnum):
    READY = "READY"


@dataclass(frozen=True)
class SerializationChild:
    count: int


@dataclass(frozen=True)
class SerializationSample:
    renamed: int = field(metadata={"json_key": "wire_count"})
    maybe: int | None = None
    labels: tuple[str, ...] = ()
    values: list[int] = field(default_factory=list)
    metadata: dict[str, int] = field(default_factory=dict)
    child: SerializationChild = field(default_factory=lambda: SerializationChild(0))
    state: SerializationEnum = SerializationEnum.READY
    created: datetime = datetime(2026, 8, 28, 12, tzinfo=__import__("datetime").timezone.utc)
    day: date = date(2026, 8, 28)
    clock: time = time(12, 0)
    enabled: bool = True
    ratio: float = 1.0


def test_serialization_round_trip_handles_aliases_enums_times_and_ordering() -> None:
    value = SerializationSample(
        renamed=3,
        maybe=None,
        labels=("a", "b"),
        values=[1, 2],
        metadata={"x": 1},
        child=SerializationChild(4),
    )
    primitive = to_primitive(value)
    restored = serialization_module._construct_dataclass(primitive, SerializationSample, path="$")

    assert primitive["wire_count"] == 3
    assert primitive["state"] == "READY"
    assert primitive["created"].endswith("+00:00")
    assert restored == value
    assert to_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert to_json({"b": 1, "a": 2}, sort_keys=False) == '{"b":1,"a":2}'


def test_serialization_rejects_nonfinite_unsupported_and_non_string_keys_with_paths() -> None:
    with pytest.raises(SerializationError, match="non-finite") as nonfinite:
        to_primitive({"nested": [float("nan")]})
    with pytest.raises(SerializationError, match="keys") as nonstring:
        to_primitive({1: "value"})
    with pytest.raises(TypeError, match="unsupported"):
        to_primitive(Path("/tmp/not-a-contract"))
    with pytest.raises(TypeError, match="root"):
        to_dict(["not", "a", "mapping"])
    assert nonfinite.value.path == "$.nested[0]"
    assert nonstring.value.path == "$"


@pytest.mark.parametrize(
    ("data", "message"),
    (
        ({"wire_count": "wrong"}, "expected integer"),
        ({"wire_count": 1, "labels": "wrong"}, "expected JSON array"),
        ({"wire_count": 1, "metadata": []}, "expected JSON object"),
        ({"wire_count": 1, "child": 1}, "expected JSON object"),
        ({"wire_count": 1, "state": "UNKNOWN"}, "invalid enum"),
        ({"wire_count": 1, "enabled": 1}, "expected boolean"),
        ({"wire_count": 1, "ratio": "wrong"}, "expected number"),
        ({"wire_count": 1, "created": 1}, "timestamp string"),
        ({"wire_count": 1, "created": "not-time"}, "ISO timestamp"),
        ({"wire_count": 1, "maybe": object()}, "value does not match"),
    ),
)
def test_serialization_convert_rejects_wrong_nested_types_with_precise_paths(
    data: dict[str, object], message: str
) -> None:
    with pytest.raises(DeserializationError, match=message):
        serialization_module._construct_dataclass(data, SerializationSample, path="$.sample")


def test_serialization_convert_covers_unions_collections_enums_and_scalar_boundaries() -> None:
    convert = serialization_module._convert
    assert convert(None, int | None, path="$") is None
    assert convert("x", int | str, path="$") == "x"
    assert convert([1, 2], tuple[int, ...], path="$") == (1, 2)
    assert convert([1, 2], list[int], path="$") == [1, 2]
    assert convert({"x": 1}, dict[str, int], path="$") == {"x": 1}
    assert convert("READY", SerializationEnum, path="$") is SerializationEnum.READY
    assert convert(1, float, path="$") == 1.0
    assert convert("2026-08-28T12:00:00Z", datetime, path="$").tzinfo is not None
    assert convert("2026-08-28", date, path="$") == date(2026, 8, 28)
    assert convert("12:00:00", time, path="$") == time(12, 0)
    assert convert(None, type(None), path="$") is None
    assert convert({"raw": True}, object, path="$") == {"raw": True}

    for value, annotation, message in (
        ("wrong", tuple[int, ...], "array"),
        ("wrong", list[int], "array"),
        ([], dict[str, int], "object"),
        ("UNKNOWN", SerializationEnum, "enum"),
        (1, str, "string"),
        (1, bool, "boolean"),
        (True, int, "integer"),
        ("wrong", float, "number"),
        (1, type(None), "null"),
    ):
        with pytest.raises(DeserializationError, match=message):
            convert(value, annotation, path="$.value")


def test_serialization_shape_limits_duplicate_keys_constants_and_input_types_fail_closed() -> None:
    with pytest.raises(DeserializationError, match="duplicate") as duplicate:
        from_json('{"wire_count":1,"wire_count":2}', SerializationSample)
    with pytest.raises(DeserializationError, match="non-finite"):
        from_json('{"wire_count":NaN}', SerializationSample)
    with pytest.raises(DeserializationError, match="nesting"):
        from_json("[" * 65 + "0" + "]" * 65, SerializationSample)
    with pytest.raises(DeserializationError, match="invalid JSON"):
        from_json(b"}", SerializationSample)
    with pytest.raises(DeserializationError, match="text or bytes"):
        from_json(123, SerializationSample)
    with pytest.raises(DeserializationError, match="model type"):
        from_json("{}", "SerializationSample")
    assert duplicate.value.code == "DUPLICATE_KEY"

    deep: object = {"wire_count": 1}
    for _ in range(66):
        deep = {"wire_count": 1, "child": deep}
    with pytest.raises(DeserializationError, match="nesting"):
        from_dict(deep, SerializationSample)
    with pytest.raises(DeserializationError, match="SIZE_LIMIT_EXCEEDED"):
        from_dict({"items": [{} for _ in range(100_001)]}, dict)


def test_serialization_public_deserialization_validates_contract_fields() -> None:
    original = record(0)
    payload = to_dict(original)
    restored = from_dict(payload, type(original))
    swapped = from_dict(type(original), payload)
    as_dict = from_dict(payload, dict)

    assert restored == original
    assert swapped == original
    assert as_dict == payload
    with pytest.raises(ContractValidationError, match="unknown field"):
        from_dict({**payload, "__unknown__": "do-not-execute"}, type(original))
    missing = dict(payload)
    missing.pop("task_id")
    with pytest.raises(DeserializationError, match="required field"):
        from_dict(missing, type(original))
    with pytest.raises(DeserializationError, match="mapping"):
        from_dict([], type(original))
    with pytest.raises(DeserializationError, match="dataclass"):
        from_dict(payload, int)
    with pytest.raises(DeserializationError, match="mapping"):
        from_dict(payload, "not-a-model")


def test_telemetry_redaction_covers_nested_containers_and_preserves_non_secret_tokens() -> None:
    payload = {
        "api-key": "secret-value",
        "safe": ["Authorization: Bearer inline-secret", {"token": "nested-secret"}],
        "counts": (1, 2),
        "set-values": {"b", "a"},
        "token_estimate": 12,
        "normal": "unchanged",
    }
    redacted = redact_payload(payload)
    unchanged, changed = redact_text("no credentials in this sentence")
    bearer, bearer_changed = redact_text("Authorization: Bearer inline-secret")

    assert redacted["api-key"] == "[REDACTED]"  # type: ignore[index]
    assert redacted["safe"][1]["token"] == "[REDACTED]"  # type: ignore[index]
    assert redacted["safe"][0] == "Authorization: [REDACTED]"  # type: ignore[index]
    assert redacted["counts"] == (1, 2)  # type: ignore[index]
    assert redacted["set-values"] == ("a", "b")  # type: ignore[index]
    assert redacted["token_estimate"] == 12  # type: ignore[index]
    assert unchanged == "no credentials in this sentence"
    assert changed is False
    assert bearer == "Authorization: [REDACTED]"
    assert bearer_changed is True
    assert telemetry_module._normalized_key("X-Api-Key") == "x_api_key"
    assert telemetry_module._is_sensitive_key("token")
    assert not telemetry_module._is_sensitive_key("tokens")
    assert telemetry_module._is_sensitive_key("prefix_secret")
    assert telemetry_module._is_sensitive_key("secret_prefix")
    assert telemetry_module._is_sensitive_key("authorization-header")
    assert not telemetry_module._is_sensitive_key("ordinary")
    assert redact_text(None) == (None, False)


@pytest.mark.parametrize(
    ("timestamp", "message"),
    (
        ("", "required"),
        ("2026-08-28", "explicit timezone"),
        ("2026-08-28T12:00:00", "explicit timezone"),
        ("not-a-time", "ISO-8601"),
    ),
)
def test_telemetry_rejects_unzoned_or_malformed_time_and_event_type(
    timestamp: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        event(timestamp=timestamp)
    with pytest.raises(ValueError, match="unknown telemetry event"):
        event(event_type="UNKNOWN")


def test_telemetry_payload_normalizes_fixed_contract_and_rejects_bad_values() -> None:
    normalized = telemetry_module._payload(
        {
            "input_size": 1,
            "output_size": 2,
            "token_estimate": 3,
            "duration_ms": 4,
            "tool": "python",
            "result": "PASS",
            "ignored": "not persisted",
        }
    )
    typed = telemetry_module._payload(
        TelemetryPayload(1, 2, 3, 4, "Authorization: Bearer secret", EvidenceResult.PASS)
    )

    assert normalized[0].input_size == 1
    assert normalized[0].result is EvidenceResult.PASS
    assert normalized[0].tool == "python"
    assert typed[0].tool == "Authorization: [REDACTED]"
    assert typed[1] is True
    for field_name, bad in (
        ("input_size", -1),
        ("output_size", True),
        ("token_estimate", "3"),
        ("duration_ms", -1),
    ):
        with pytest.raises(ValueError, match=field_name):
            telemetry_module._payload({field_name: bad})
    with pytest.raises(ValueError, match="result"):
        telemetry_module._payload({"result": "NOT_A_RESULT"})
    with pytest.raises(ValueError, match="tool"):
        telemetry_module._payload({"tool": 1})
    with pytest.raises(TypeError, match="payload"):
        telemetry_module._payload(object())


def test_telemetry_event_requires_observation_and_redacts_records() -> None:
    evidence = record(6)
    invalid_evidence = replace(
        evidence,
        evidence_kind=EvidenceKind.TEST_RESULT,
        freshness=replace(evidence.freshness, status=FreshnessStatus.STALE),
    )
    common = {
        "event_id": "EVT-CAPABILITY-LOADED",
        "event_sequence": 1,
        "timestamp": NOW,
        "task_id": "TASK-TELEMETRY-BOUNDARY",
        "run_id": "RUN-TELEMETRY-BOUNDARY",
        "event_type": TelemetryEventType.CAPABILITY_LOADED,
        "evidence_refs": (evidence.evidence_id,),
    }

    with pytest.raises(ValueError, match="runtime observation"):
        create_event(**common, runtime_evidence=(invalid_evidence,))
    with pytest.raises(ValueError, match="runtime observation"):
        create_event(**{**common, "evidence_refs": ()}, runtime_evidence=(evidence,))
    with pytest.raises(ValueError, match="limitation count"):
        event(limitations=("x",) * 257)
    with pytest.raises(ValueError, match="bounded strings"):
        event(limitations=("x" * 4_097,))
    with pytest.raises(ValueError, match="contract"):
        event(schema_version="TE-999")

    source_record = replace(
        record(0).record,
        provenance=replace(record(0).record.provenance, source_refs=("secret: value",)),
    )
    created = event(
        event_id="EVT-REDACTED",
        reason="password: top-secret",
        record=source_record,
        limitations=("token: hidden",),
    )

    assert created.redaction is Redaction.APPLIED
    assert created.reason == "password: [REDACTED]"
    assert created.limitations == ("token: [REDACTED]",)
    assert created.record.provenance.source_refs == ("secret: [REDACTED]",)
    assert "top-secret" not in repr(created)


def test_telemetry_event_digest_is_canonical_and_rejects_non_events() -> None:
    first = event()
    repeated = event()

    assert telemetry_module.event_digest(first) == first.integrity.event_digest
    assert telemetry_module.event_digest(first) == telemetry_module.event_digest(repeated)
    with pytest.raises(TypeError, match="unsupported"):
        telemetry_module.event_digest(object())


def test_telemetry_log_rejects_non_append_events_and_accepts_explicit_out_of_order() -> None:
    first = event()
    second = event(
        "EVT-BOUNDARY-2",
        sequence=2,
        previous=first.integrity.event_digest,
        timestamp="2026-08-28T12:00:01Z",
    )
    out_of_order = event(
        "EVT-BOUNDARY-3",
        sequence=2,
        previous=first.integrity.event_digest,
        timestamp="2026-08-28T11:00:00Z",
        ordering=Ordering.OUT_OF_ORDER,
    )
    duplicate = event(
        "EVT-BOUNDARY-1",
        sequence=2,
        previous=first.integrity.event_digest,
    )
    unordered_without_marker = event(
        "EVT-BOUNDARY-OLD",
        sequence=2,
        previous=first.integrity.event_digest,
        timestamp="2026-08-28T11:00:00Z",
    )
    log = TelemetryLog().append(first)
    chained = log.append(second)
    ordered = log.append(out_of_order)

    assert log.events == (first,)
    assert chained.last_digest == second.integrity.event_digest
    assert chained.verify_chain()
    assert ordered.verify_chain()
    for bad, message in (
        (object(), "TelemetryEvent"),
        (replace(second, event_sequence=3), "append ordered"),
        (duplicate, "already present"),
        (replace(second, task_id="TASK-OTHER"), "correlation"),
        (
            replace(
                second,
                integrity=replace(second.integrity, previous_event_digest="sha256:wrong"),
            ),
            "previous digest",
        ),
        (replace(second, reason="tampered"), "digest"),
        (unordered_without_marker, "out-of-order"),
    ):
        with pytest.raises((TypeError, ValueError), match=message):
            log.append(bad)


def test_telemetry_log_verify_and_validate_each_tamper_shape() -> None:
    first = event()
    log = TelemetryLog((first,))
    bad_sequence = TelemetryLog((replace(first, event_sequence=2),))
    bad_previous = TelemetryLog(
        (replace(first, integrity=replace(first.integrity, previous_event_digest="wrong")),)
    )
    bad_digest = TelemetryLog(
        (replace(first, integrity=replace(first.integrity, event_digest="wrong")),)
    )
    bad_record = TelemetryLog(
        (replace(first, record=replace(first.record, status=RecordStatus.STALE)),)
    )

    for invalid in (bad_sequence, bad_previous, bad_digest, bad_record):
        assert invalid.verify_chain() is False
        assert invalid.validate().is_valid is False
    assert log.verify_chain() is True
    assert log.validate().is_valid is True
    assert log.last_digest == first.integrity.event_digest
