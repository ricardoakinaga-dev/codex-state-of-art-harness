"""Pure structural and invariant validation for Phase 1 contract records."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, StrEnum
from typing import Any

from .errors import ContractValidationError
from .models import (
    REGISTRY_ORIGIN_PRECEDENCE,
    ArtifactRecord,
    BlastRadius,
    CapabilityInvocation,
    CapabilityManifest,
    CapabilityStatus,
    ClaimStatus,
    Complexity,
    Confidence,
    CritiqueReport,
    DataImpact,
    DeliveryStatus,
    EvidenceRecord,
    EvidenceResult,
    ExecutionGraph,
    FreshnessStatus,
    GateStatus,
    Independence,
    InstallationScope,
    InvocationStatus,
    LifecycleState,
    ManifestProvenance,
    NodeKind,
    OmittedReasonCode,
    ParallelismPotential,
    Provenance,
    QualityBand,
    QualityDecision,
    QualityReport,
    Recommendation,
    RecordEnvelope,
    RecordStatus,
    RegistryOrigin,
    ResearchNeed,
    ResidualRisk,
    Reversibility,
    Risk,
    RouteDecision,
    RouteStatus,
    RunSummary,
    SchemaVersion,
    SecurityImpact,
    SourceType,
    TaskDomain,
    TaskProfile,
    TelemetryEvent,
    TelemetryEventType,
    UnresolvedPolicy,
    UserImpact,
    VerificationReport,
    VisualImportance,
)
from .models import FindingSeverity as CritiqueFindingSeverity


class ValidationCode(StrEnum):
    REQUIRED_FIELD = "REQUIRED_FIELD"
    INVALID_TYPE = "INVALID_TYPE"
    INVALID_ID = "INVALID_ID"
    INVALID_VERSION = "INVALID_VERSION"
    INVALID_ENUM = "INVALID_ENUM"
    INVALID_STATUS = "INVALID_STATUS"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    INVALID_REFERENCE = "INVALID_REFERENCE"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"

    def __str__(self) -> str:
        return self.value


class ValidationSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


FindingSeverity = ValidationSeverity
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")
_SCHEMA_BY_TYPE: dict[type[Any], SchemaVersion] = {
    TaskProfile: SchemaVersion.TASK_PROFILE,
    RouteDecision: SchemaVersion.ROUTE_DECISION,
    ExecutionGraph: SchemaVersion.EXECUTION_GRAPH,
    CapabilityManifest: SchemaVersion.CAPABILITY_MANIFEST,
    CapabilityInvocation: SchemaVersion.CAPABILITY_INVOCATION,
    ArtifactRecord: SchemaVersion.ARTIFACT_RECORD,
    EvidenceRecord: SchemaVersion.EVIDENCE_RECORD,
    VerificationReport: SchemaVersion.VERIFICATION_REPORT,
    CritiqueReport: SchemaVersion.CRITIQUE_REPORT,
    QualityReport: SchemaVersion.QUALITY_REPORT,
    TelemetryEvent: SchemaVersion.TELEMETRY_EVENT,
    RunSummary: SchemaVersion.RUN_SUMMARY,
}


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    code: ValidationCode
    message: str
    path: str = "$"
    severity: ValidationSeverity = ValidationSeverity.ERROR
    rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    findings: tuple[ValidationFinding, ...] = ()
    record_type: str | None = None

    def __post_init__(self) -> None:
        findings: Iterable[ValidationFinding] = self.findings
        if not isinstance(findings, tuple):
            object.__setattr__(self, "findings", tuple(findings))

    @property
    def is_valid(self) -> bool:
        return self.valid and not any(
            finding.severity is ValidationSeverity.ERROR for finding in self.findings
        )

    @property
    def ok(self) -> bool:
        return self.is_valid

    @property
    def errors(self) -> tuple[ValidationFinding, ...]:
        return tuple(
            finding for finding in self.findings if finding.severity is ValidationSeverity.ERROR
        )

    def raise_for_error(self) -> None:
        if not self.is_valid:
            raise ContractValidationError(self.findings)


def _add(
    findings: list[ValidationFinding],
    code: ValidationCode,
    path: str,
    message: str,
    *,
    rule_id: str | None = None,
) -> None:
    findings.append(ValidationFinding(code=code, message=message, path=path, rule_id=rule_id))


def _nonempty(
    value: Any, path: str, findings: list[ValidationFinding], *, identifier: bool = False
) -> None:
    if not isinstance(value, str) or not value.strip():
        _add(
            findings,
            ValidationCode.INVALID_ID if identifier else ValidationCode.REQUIRED_FIELD,
            path,
            "identifier must be a non-empty string" if identifier else "required string is missing",
        )
    elif identifier and not _ID_PATTERN.fullmatch(value):
        _add(
            findings, ValidationCode.INVALID_ID, path, "identifier contains unsupported characters"
        )


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _enum(
    value: Any,
    enum_type: type[object],
    path: str,
    findings: list[ValidationFinding],
    *,
    status: bool = False,
) -> None:
    if not issubclass(enum_type, Enum):
        if not isinstance(value, str) or not value.strip():
            _add(
                findings,
                ValidationCode.INVALID_ENUM,
                path,
                "value must be a non-empty string",
            )
        return
    values = {member.value for member in enum_type}
    if not isinstance(value, enum_type) and not (isinstance(value, str) and value in values):
        _add(
            findings,
            ValidationCode.INVALID_STATUS if status else ValidationCode.INVALID_ENUM,
            path,
            "value is not in the canonical enum set",
        )


def _timestamp(value: Any, path: str, findings: list[ValidationFinding]) -> None:
    if not isinstance(value, str) or not value.strip():
        _add(findings, ValidationCode.INVALID_TIMESTAMP, path, "timestamp is required")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _add(findings, ValidationCode.INVALID_TIMESTAMP, path, "timestamp must be ISO-8601")
        return
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        _add(
            findings,
            ValidationCode.INVALID_TIMESTAMP,
            path,
            "timestamp must include an explicit timezone",
        )
    if "T" not in value.upper():
        _add(
            findings,
            ValidationCode.INVALID_TIMESTAMP,
            path,
            "timestamp must include a time component",
        )


def _refs(values: Any, path: str, findings: list[ValidationFinding]) -> None:
    if not isinstance(values, tuple):
        _add(findings, ValidationCode.INVALID_TYPE, path, "references must be immutable tuples")
        return
    for index, value in enumerate(values):
        _nonempty(value, f"{path}[{index}]", findings, identifier=True)


def _text_refs(values: Any, path: str, findings: list[ValidationFinding]) -> None:
    if not isinstance(values, tuple):
        _add(findings, ValidationCode.INVALID_TYPE, path, "references must be immutable tuples")
        return
    for index, value in enumerate(values):
        _nonempty(value, f"{path}[{index}]", findings)


def _common(
    value: Any, expected: SchemaVersion, primary_id: str, findings: list[ValidationFinding]
) -> None:
    schema = getattr(value, "schema_version", None)
    if schema != expected and schema != expected.value:
        _add(
            findings,
            ValidationCode.INVALID_VERSION,
            "$.schema_version",
            "unsupported schema version",
        )
    _nonempty(getattr(value, primary_id, None), f"$.{primary_id}", findings, identifier=True)
    if hasattr(value, "task_id"):
        _nonempty(value.task_id, "$.task_id", findings, identifier=True)
    if hasattr(value, "run_id"):
        _nonempty(value.run_id, "$.run_id", findings, identifier=True)
    if hasattr(value, "created_at"):
        _timestamp(value.created_at, "$.created_at", findings)
    elif hasattr(value, "timestamp"):
        _timestamp(value.timestamp, "$.timestamp", findings)
    envelope = getattr(value, "record", None)
    if not isinstance(envelope, RecordEnvelope):
        _add(findings, ValidationCode.INVALID_TYPE, "$.record", "record envelope is required")
        return
    _enum(envelope.status, RecordStatus, "$.record.status", findings, status=True)
    provenance: object = envelope.provenance
    if not isinstance(provenance, Provenance):
        _add(findings, ValidationCode.INVALID_TYPE, "$.record.provenance", "provenance is required")
    else:
        _enum(provenance.source_type, SourceType, "$.record.provenance.source_type", findings)
        _timestamp(provenance.created_at, "$.record.provenance.created_at", findings)
    _refs(envelope.evidence_refs, "$.record.evidence_refs", findings)


def _nonnegative(value: Any, path: str, findings: list[ValidationFinding]) -> None:
    if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
        _add(
            findings,
            ValidationCode.INVARIANT_VIOLATION,
            path,
            "value must be a non-negative integer",
        )


def _cycle(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> bool:
    graph: dict[str, list[str]] = {node: [] for node in nodes}
    for source, target in edges:
        if source in graph and target in graph:
            graph[source].append(target)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(child) for child in graph[node]):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def _specific(value: Any, findings: list[ValidationFinding]) -> None:
    if isinstance(value, TaskProfile):
        for name, enum_type in (
            ("domain", TaskDomain),
            ("complexity", Complexity),
            ("risk", Risk),
            ("visual_importance", VisualImportance),
            ("security_impact", SecurityImpact),
            ("data_impact", DataImpact),
            ("user_impact", UserImpact),
            ("blast_radius", BlastRadius),
            ("research_need", ResearchNeed),
            ("parallelism_potential", ParallelismPotential),
            ("reversibility", Reversibility),
            ("confidence", Confidence),
        ):
            _enum(getattr(value, name), enum_type, f"$.{name}", findings)
        _nonempty(value.objective, "$.objective", findings)
        _nonempty(value.requested_outcome, "$.requested_outcome", findings)
    elif isinstance(value, RouteDecision):
        _nonempty(value.profile_ref, "$.profile_ref", findings, identifier=True)
        _enum(value.route_status, RouteStatus, "$.route_status", findings, status=True)
        _refs(value.unresolved, "$.unresolved", findings)
        _nonnegative(value.budget.token_estimate, "$.budget.token_estimate", findings)
        _nonnegative(value.budget.latency_budget_ms, "$.budget.latency_budget_ms", findings)
        _nonnegative(value.budget.parallelism_budget, "$.budget.parallelism_budget", findings)
        if value.confidence == Confidence.HIGH and not value.record.evidence_refs:
            _add(
                findings,
                ValidationCode.MISSING_EVIDENCE,
                "$.record.evidence_refs",
                "high confidence needs evidence",
            )
        for item in value.omitted:
            _nonempty(item.capability_id, "$.omitted[].capability_id", findings, identifier=True)
            _enum(item.reason_code, OmittedReasonCode, "$.omitted[].reason_code", findings)
            _nonempty(item.explanation, "$.omitted[].explanation", findings)
    elif isinstance(value, ExecutionGraph):
        ids = [node.node_id for node in value.nodes]
        if len(ids) != len(set(ids)):
            _add(findings, ValidationCode.INVARIANT_VIOLATION, "$.nodes", "node IDs must be unique")
        node_ids = set(ids)
        dependency_edges: list[tuple[str, str]] = []
        for node in value.nodes:
            _nonempty(node.node_id, "$.nodes[].node_id", findings, identifier=True)
            _nonempty(node.owner, "$.nodes[].owner", findings)
            _nonempty(node.output_contract, "$.nodes[].output_contract", findings)
            _enum(node.kind, NodeKind, "$.nodes[].kind", findings)
            for dependency in node.depends_on:
                if dependency not in node_ids:
                    _add(
                        findings,
                        ValidationCode.INVALID_REFERENCE,
                        "$.nodes[].depends_on",
                        "unknown dependency",
                    )
                dependency_edges.append((dependency, node.node_id))
        for edge in value.edges:
            if edge.from_node not in node_ids or edge.to_node not in node_ids:
                _add(
                    findings,
                    ValidationCode.INVALID_REFERENCE,
                    "$.edges",
                    "edge points to an unknown node",
                )
            dependency_edges.append((edge.from_node, edge.to_node))
        if _cycle(node_ids, dependency_edges):
            _add(
                findings,
                ValidationCode.INVARIANT_VIOLATION,
                "$.edges",
                "execution graph must be acyclic",
            )
        for merge in value.merge_points:
            if merge.node_id not in node_ids:
                _add(
                    findings,
                    ValidationCode.INVALID_REFERENCE,
                    "$.merge_points[].node_id",
                    "unknown merge node",
                )
            _enum(
                merge.unresolved_policy,
                UnresolvedPolicy,
                "$.merge_points[].unresolved_policy",
                findings,
            )
        _nonempty(value.graph_owner, "$.graph_owner", findings)
        _enum(value.merge_policy, UnresolvedPolicy, "$.merge_policy", findings)
        if value.acceptance_refs:
            _refs(value.acceptance_refs, "$.acceptance_refs", findings)
        _refs(value.conflict_refs, "$.conflict_refs", findings)
        if value.graph_budget is not None:
            _nonnegative(value.graph_budget.tokens, "$.graph_budget.tokens", findings)
            _nonnegative(value.graph_budget.duration_ms, "$.graph_budget.duration_ms", findings)
    elif isinstance(value, CapabilityManifest):
        _nonempty(value.capability_id, "$.capability_id", findings, identifier=True)
        _nonempty(value.version, "$.version", findings)
        _nonempty(value.owner, "$.owner", findings)
        _enum(value.status, CapabilityStatus, "$.status", findings, status=True)
        provenance: Any = value.provenance
        if not isinstance(provenance, ManifestProvenance):
            _add(
                findings,
                ValidationCode.INVALID_TYPE,
                "$.provenance",
                "manifest provenance is required",
            )
        else:
            origin = getattr(provenance.origin, "value", provenance.origin)
            _enum(provenance.source_type, SourceType, "$.provenance.source_type", findings)
            _text_refs(provenance.source_refs, "$.provenance.source_refs", findings)
            _timestamp(provenance.inspected_at, "$.provenance.inspected_at", findings)
            _nonempty(provenance.source_repository, "$.provenance.source_repository", findings)
            if not isinstance(provenance.source_hash, str) or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", provenance.source_hash
            ):
                _add(
                    findings,
                    ValidationCode.INVALID_REFERENCE,
                    "$.provenance.source_hash",
                    "source_hash must be a sha256 digest",
                )
            _enum(provenance.origin, RegistryOrigin, "$.provenance.origin", findings)
            if (
                not isinstance(provenance.precedence, int)
                or isinstance(provenance.precedence, bool)
                or provenance.precedence < 0
            ):
                _add(
                    findings,
                    ValidationCode.INVARIANT_VIOLATION,
                    "$.provenance.precedence",
                    "precedence must be a non-negative integer",
                )
            _enum(
                provenance.installation_scope,
                InstallationScope,
                "$.provenance.installation_scope",
                findings,
            )
            if (
                origin in {item.value for item in RegistryOrigin}
                and provenance.precedence != (REGISTRY_ORIGIN_PRECEDENCE[RegistryOrigin(origin)])
            ):
                _add(
                    findings,
                    ValidationCode.INVARIANT_VIOLATION,
                    "$.provenance.precedence",
                    "precedence must match the canonical registry-origin policy",
                )
            if origin in (RegistryOrigin.PROJECT.value, RegistryOrigin.VENDORED.value):
                _nonempty(provenance.project_scope, "$.provenance.project_scope", findings)
            if provenance.forked_from is not None:
                _nonempty(provenance.forked_from, "$.provenance.forked_from", findings)
        if (
            isinstance(provenance, ManifestProvenance)
            and value.status == CapabilityStatus.VERIFIED
            and (not provenance.source_refs or not value.quality.eval_refs)
        ):
            _add(
                findings,
                ValidationCode.INVARIANT_VIOLATION,
                "$.status",
                "verified manifest needs source and eval",
            )
    elif isinstance(value, CapabilityInvocation):
        _nonempty(value.objective, "$.objective", findings)
        _nonempty(value.inputs.payload_digest, "$.inputs.payload_digest", findings)
        _enum(
            value.invocation_status, InvocationStatus, "$.invocation_status", findings, status=True
        )
        invocation_status = _enum_value(value.invocation_status)
        if invocation_status != InvocationStatus.REQUESTED.value and (
            value.operation or value.provider_id is not None or value.capability_origin is not None
        ):
            _nonempty(value.operation, "$.operation", findings)
        # Scope labels predate the Phase 2 namespaced identifiers; preserve
        # valid Phase 1 free-form labels while still requiring immutable text.
        _text_refs(value.scope, "$.scope", findings)
        _refs(value.dependencies, "$.dependencies", findings)
        if value.provider_id is not None:
            _nonempty(value.provider_id, "$.provider_id", findings, identifier=True)
        if value.capability_origin is not None:
            _enum(value.capability_origin, RegistryOrigin, "$.capability_origin", findings)
        if value.repair_of is not None:
            _nonempty(value.repair_of, "$.repair_of", findings, identifier=True)
        _refs(value.repair_trigger_refs, "$.repair_trigger_refs", findings)
        if len({key for key, _ in value.trace_context}) != len(value.trace_context):
            _add(
                findings,
                ValidationCode.INVARIANT_VIOLATION,
                "$.trace_context",
                "trace context keys must be unique",
            )
        for key, trace_value in value.trace_context:
            _nonempty(key, "$.trace_context[].key", findings)
            _nonempty(trace_value, "$.trace_context[].value", findings)
        if invocation_status == InvocationStatus.AUTHORIZED.value:
            if not value.scope or not value.permissions:
                _add(
                    findings,
                    ValidationCode.INVARIANT_VIOLATION,
                    "$.permissions",
                    "authorized invocation needs scope and permissions",
                )
            if all(
                budget is None
                for budget in (
                    value.limits.token_budget,
                    value.limits.duration_budget_ms,
                    value.limits.tool_call_budget,
                )
            ):
                _add(
                    findings,
                    ValidationCode.INVARIANT_VIOLATION,
                    "$.limits",
                    "authorized invocation needs a budget",
                )
        if invocation_status == InvocationStatus.SUCCEEDED.value and (
            not value.handoff.required_output_contracts or not value.expected_evidence
        ):
            _add(
                findings,
                ValidationCode.MISSING_EVIDENCE,
                "$.expected_evidence",
                "succeeded invocation needs output and evidence",
            )
    elif isinstance(value, ArtifactRecord):
        _nonempty(value.title, "$.title", findings)
        _nonempty(value.content.digest, "$.content.digest", findings)
        _nonempty(value.content.media_type, "$.content.media_type", findings)
    elif isinstance(value, EvidenceRecord):
        _enum(value.result, EvidenceResult, "$.result", findings, status=True)
        _enum(value.freshness.status, FreshnessStatus, "$.freshness.status", findings, status=True)
        _nonempty(value.owner, "$.owner", findings, identifier=True)
        _nonempty(value.observation, "$.observation", findings)
        _nonempty(
            value.procedure.procedure_id, "$.procedure.procedure_id", findings, identifier=True
        )
        if value.result == EvidenceResult.PASS and (
            not value.procedure.executed or value.freshness.status != FreshnessStatus.FRESH
        ):
            _add(
                findings,
                ValidationCode.INVARIANT_VIOLATION,
                "$.procedure",
                "PASS needs an executed fresh procedure",
            )
    elif isinstance(value, VerificationReport):
        claims = {claim.claim_id: claim for claim in value.claims}
        declared = set(value.passed) | set(value.failed) | set(value.not_run) | set(value.unknown)
        for claim in value.claims:
            if claim.required and claim.claim_id not in declared:
                _add(
                    findings,
                    ValidationCode.INVARIANT_VIOLATION,
                    "$.claims",
                    "required claim must be classified",
                )
            if claim.status == ClaimStatus.PASS and not claim.evidence_refs:
                _add(
                    findings,
                    ValidationCode.MISSING_EVIDENCE,
                    "$.claims[].evidence_refs",
                    "PASS claim needs evidence",
                )
        if value.recommendation == Recommendation.PASS and any(
            claim.required and claim.status != ClaimStatus.PASS for claim in claims.values()
        ):
            _add(
                findings,
                ValidationCode.INVARIANT_VIOLATION,
                "$.recommendation",
                "PASS cannot hide a required non-PASS claim",
            )
    elif isinstance(value, CritiqueReport):
        if (
            value.independence == Independence.INDEPENDENT
            and not value.reviewer.blind_packet_digest
        ):
            _add(
                findings,
                ValidationCode.INVARIANT_VIOLATION,
                "$.reviewer.blind_packet_digest",
                "independent review needs blind packet",
            )
        for finding in value.findings:
            if finding.severity != CritiqueFindingSeverity.NOTE and not finding.evidence_refs:
                _add(
                    findings,
                    ValidationCode.MISSING_EVIDENCE,
                    "$.findings[].evidence_refs",
                    "material finding needs evidence",
                )
    elif isinstance(value, QualityReport):
        for index, dimension in enumerate(value.dimensions):
            if dimension.score is not None:
                if not isinstance(dimension.score, (int, float)) or not math.isfinite(
                    dimension.score
                ):
                    _add(
                        findings,
                        ValidationCode.INVARIANT_VIOLATION,
                        f"$.dimensions[{index}].score",
                        "score must be finite",
                    )
                if not dimension.evidence_refs and dimension.confidence != Confidence.LOW:
                    _add(
                        findings,
                        ValidationCode.MISSING_EVIDENCE,
                        f"$.dimensions[{index}]",
                        "score needs evidence or LOW confidence",
                    )
        if value.quality_band == QualityBand.AAA_VERIFIED and any(
            gate.required and gate.status in (GateStatus.FAIL, GateStatus.BLOCKED)
            for gate in value.gates
        ):
            _add(
                findings,
                ValidationCode.INVARIANT_VIOLATION,
                "$.quality_band",
                "required failed gate blocks AAA_VERIFIED",
            )
        _nonempty(value.decision_owner, "$.decision_owner", findings)
        if value.decision == QualityDecision.DELIVER_WITH_LIMITATIONS and not any(
            d.limitations for d in value.dimensions
        ):
            _add(
                findings,
                ValidationCode.INVARIANT_VIOLATION,
                "$.decision",
                "delivery with limitations needs limitations",
            )
    elif isinstance(value, TelemetryEvent):
        _nonnegative(value.event_sequence, "$.event_sequence", findings)
        _timestamp(value.timestamp, "$.timestamp", findings)
        _nonempty(value.integrity.event_digest, "$.integrity.event_digest", findings)
        if (
            value.event_type
            in (
                TelemetryEventType.CAPABILITY_LOADED,
                TelemetryEventType.DELIVERY,
            )
            and not value.evidence_refs
        ):
            _add(
                findings,
                ValidationCode.MISSING_EVIDENCE,
                "$.evidence_refs",
                "event needs evidence",
            )
    elif isinstance(value, RunSummary):
        _nonempty(value.route_ref, "$.route_ref", findings, identifier=True)
        _enum(value.residual_risk, ResidualRisk, "$.residual_risk", findings)
        if value.lifecycle_state == LifecycleState.DELIVERED:
            if (
                value.delivery.status
                not in (DeliveryStatus.DELIVERED, DeliveryStatus.DELIVERED_WITH_LIMITATIONS)
                or not value.delivery.artifact_ref
            ):
                _add(
                    findings,
                    ValidationCode.INVARIANT_VIOLATION,
                    "$.delivery",
                    "delivered run needs delivery artifact",
                )
            if value.gate_summary.failed or value.gate_summary.blocked:
                _add(
                    findings,
                    ValidationCode.INVARIANT_VIOLATION,
                    "$.gate_summary",
                    "delivered run cannot have failed gates",
                )


def validate(value: object) -> ValidationResult:
    """Validate a contract without mutating it or executing any payload."""

    findings: list[ValidationFinding] = []
    model_type = type(value)
    expected = _SCHEMA_BY_TYPE.get(model_type)
    if expected is None:
        _add(findings, ValidationCode.INVALID_TYPE, "$", "value is not a supported contract record")
    else:
        primary_id = next(
            name
            for name in (
                "task_id",
                "decision_id",
                "graph_id",
                "capability_id",
                "invocation_id",
                "artifact_id",
                "evidence_id",
                "report_id",
                "event_id",
                "summary_id",
            )
            if hasattr(value, name)
        )
        _common(value, expected, primary_id, findings)
        _specific(value, findings)
    return ValidationResult(
        valid=not findings, findings=tuple(findings), record_type=model_type.__name__
    )


def validate_record(value: object) -> ValidationResult:
    return validate(value)


def is_valid(value: object) -> bool:
    return validate(value).is_valid
