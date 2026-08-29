"""Frozen, stdlib-only data models for the Phase 1 contract boundary.

The models deliberately contain data and shape only.  They do not dispatch
capabilities, import user supplied modules, or execute values received from a
JSON document.  Semantic checks live in :mod:`harness_kernel.validation`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, cast


class _ValueModel:
    """Normalize collection inputs while keeping every model deeply immutable."""

    def __post_init__(self) -> None:
        for model_field in fields(cast(Any, self)):
            value = getattr(self, model_field.name)
            normalized = _freeze_collections(value)
            if normalized is not value:
                object.__setattr__(self, model_field.name, normalized)


def _freeze_collections(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_freeze_collections(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_collections(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((_freeze_collections(item) for item in value), key=repr))
    if isinstance(value, dict):
        return tuple(
            sorted(
                (
                    (_freeze_collections(key), _freeze_collections(item))
                    for key, item in value.items()
                ),
                key=lambda pair: repr(pair[0]),
            )
        )
    return value


class _StringEnum(StrEnum):
    def __str__(self) -> str:
        return self.value


class SchemaVersion(_StringEnum):
    TASK_PROFILE = "TP-1"
    ROUTE_DECISION = "RD-1"
    EXECUTION_GRAPH = "EG-1"
    CAPABILITY_MANIFEST = "CM-1"
    CAPABILITY_INVOCATION = "CI-1"
    ARTIFACT_RECORD = "AR-1"
    EVIDENCE_RECORD = "ER-1"
    VERIFICATION_REPORT = "VR-1"
    CRITIQUE_REPORT = "CR-1"
    QUALITY_REPORT = "QR-1"
    TELEMETRY_EVENT = "TE-1"
    RUN_SUMMARY = "RS-1"

    TP_1 = "TP-1"
    RD_1 = "RD-1"
    EG_1 = "EG-1"
    CM_1 = "CM-1"
    CI_1 = "CI-1"
    AR_1 = "AR-1"
    ER_1 = "ER-1"
    VR_1 = "VR-1"
    CR_1 = "CR-1"
    QR_1 = "QR-1"
    TE_1 = "TE-1"
    RS_1 = "RS-1"


class RecordStatus(_StringEnum):
    DRAFT = "DRAFT"
    CURRENT = "CURRENT"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    INVALID = "INVALID"
    BLOCKED = "BLOCKED"


class SourceType(_StringEnum):
    LOCAL = "LOCAL"
    OFFICIAL = "OFFICIAL"
    THIRD_PARTY = "THIRD_PARTY"
    USER_PROVIDED = "USER_PROVIDED"
    GENERATED = "GENERATED"
    TOOL_OUTPUT = "TOOL_OUTPUT"
    TOOL = "TOOL"
    HUMAN = "HUMAN"
    PROVIDER = "PROVIDER"
    IMPORTED = "IMPORTED"
    DERIVED = "DERIVED"


class RegistryOrigin(_StringEnum):
    """The authority boundary from which a capability manifest originates."""

    SYSTEM = "SYSTEM"
    GLOBAL = "GLOBAL"
    PROJECT = "PROJECT"
    WORKSPACE = "WORKSPACE"
    VENDORED = "VENDORED"
    UPSTREAM = "UPSTREAM"


class InstallationScope(_StringEnum):
    """The filesystem/configuration scope that owns an installed capability."""

    SYSTEM = "SYSTEM"
    GLOBAL = "GLOBAL"
    WORKSPACE = "WORKSPACE"
    PROJECT = "PROJECT"


REGISTRY_ORIGIN_PRECEDENCE: Mapping[RegistryOrigin, int] = MappingProxyType(
    {
        RegistryOrigin.SYSTEM: 500,
        RegistryOrigin.GLOBAL: 400,
        RegistryOrigin.WORKSPACE: 300,
        RegistryOrigin.PROJECT: 200,
        RegistryOrigin.VENDORED: 100,
        RegistryOrigin.UPSTREAM: 50,
    }
)


class Confidence(_StringEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class TaskDomain(_StringEnum):
    ENGINEERING = "ENGINEERING"
    FRONTEND = "FRONTEND"
    BACKEND = "BACKEND"
    API = "API"
    SECURITY = "SECURITY"
    DESIGN = "DESIGN"
    RESEARCH = "RESEARCH"
    GAME = "GAME"
    DATA = "DATA"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    DOCUMENTATION = "DOCUMENTATION"
    CONTENT = "CONTENT"
    INTEGRATION = "INTEGRATION"
    OPERATIONS = "OPERATIONS"
    GENERAL = "GENERAL"
    MIXED = "MIXED"


class Complexity(_StringEnum):
    TRIVIAL = "TRIVIAL"
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"
    CRITICAL = "CRITICAL"


class Risk(_StringEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class VisualImportance(_StringEnum):
    NONE = "NONE"
    SUPPORTING = "SUPPORTING"
    MATERIAL = "MATERIAL"
    PRIMARY = "PRIMARY"


class SecurityImpact(_StringEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DataImpact(_StringEnum):
    NONE = "NONE"
    LOCAL = "LOCAL"
    PERSISTENT = "PERSISTENT"
    MIGRATION = "MIGRATION"
    SENSITIVE = "SENSITIVE"


class UserImpact(_StringEnum):
    INTERNAL = "INTERNAL"
    LIMITED = "LIMITED"
    BROAD = "BROAD"
    SAFETY_RELEVANT = "SAFETY_RELEVANT"


class BlastRadius(_StringEnum):
    LOCAL = "LOCAL"
    MODULE = "MODULE"
    SERVICE = "SERVICE"
    PRODUCT = "PRODUCT"
    CROSS_SYSTEM = "CROSS_SYSTEM"
    PUBLIC = "PUBLIC"
    UNKNOWN = "UNKNOWN"


class ResearchNeed(_StringEnum):
    NONE = "NONE"
    FRESHNESS_REQUIRED = "FRESHNESS_REQUIRED"
    COMPARATIVE = "COMPARATIVE"
    DEEP = "DEEP"


class ParallelismPotential(_StringEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Reversibility(_StringEnum):
    EASY = "EASY"
    CONTROLLED = "CONTROLLED"
    HARD = "HARD"
    IRREVERSIBLE = "IRREVERSIBLE"


class RepositoryClassification(_StringEnum):
    GREENFIELD = "GREENFIELD"
    BROWNFIELD = "BROWNFIELD"
    UNKNOWN = "UNKNOWN"


class TrustState(_StringEnum):
    TRUSTED = "TRUSTED"
    UNTRUSTED = "UNTRUSTED"
    UNKNOWN = "UNKNOWN"


class RouteStatus(_StringEnum):
    SELECTED = "SELECTED"
    NO_SPECIAL_ROUTE = "NO_SPECIAL_ROUTE"
    CONDITIONAL = "CONDITIONAL"
    FALLBACK = "FALLBACK"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"


class RouteKind(_StringEnum):
    DIRECT = "DIRECT"
    SPECIALIST = "SPECIALIST"
    COMPOSED = "COMPOSED"
    PROVIDER = "PROVIDER"
    DEGRADED = "DEGRADED"


class CapabilityPrimaryType(_StringEnum):
    DIRECTOR = "DIRECTOR"
    ORCHESTRATOR = "ORCHESTRATOR"
    ROUTER = "ROUTER"
    PLANNER = "PLANNER"
    SPECIALIST = "SPECIALIST"
    TOOL = "TOOL"
    PROVIDER = "PROVIDER"
    REVIEWER = "REVIEWER"
    VALIDATOR = "VALIDATOR"
    ASSURANCE = "ASSURANCE"
    RESEARCHER = "RESEARCHER"
    INTEGRATOR = "INTEGRATOR"
    VERIFICATION = "VERIFICATION"
    UTILITY = "UTILITY"


class OmittedReasonCode(_StringEnum):
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    DUPLICATE = "DUPLICATE"
    OVERACTIVATION = "OVERACTIVATION"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_NEEDED = "NOT_NEEDED"
    CONFLICT = "CONFLICT"


class ReferencePack(_StringEnum):
    MINIMAL = "MINIMAL"
    STANDARD = "STANDARD"
    EXTENDED = "EXTENDED"


class NodeKind(_StringEnum):
    DIRECTOR = "DIRECTOR"
    PLANNER = "PLANNER"
    SPECIALIST = "SPECIALIST"
    TOOL = "TOOL"
    INTEGRATOR = "INTEGRATOR"
    VERIFICATION = "VERIFICATION"
    REVIEWER = "REVIEWER"
    ASSURANCE = "ASSURANCE"


class EdgeRelation(_StringEnum):
    DATA = "DATA"
    CONTROL = "CONTROL"
    GATE = "GATE"


class MergeConflictOwner(_StringEnum):
    INTEGRATOR = "INTEGRATOR"
    DIRECTOR = "DIRECTOR"
    AUTHORITY = "AUTHORITY"


class UnresolvedPolicy(_StringEnum):
    PRESERVE_AND_ESCALATE = "PRESERVE_AND_ESCALATE"
    BLOCK = "BLOCK"
    DROP_WITH_REASON = "DROP_WITH_REASON"


class GraphStatus(_StringEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class InvocationStatus(_StringEnum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    REQUESTED = "REQUESTED"
    AUTHORIZED = "AUTHORIZED"
    READY = "READY"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class ArtifactType(_StringEnum):
    PLAN = "PLAN"
    TASK_GRAPH = "TASK_GRAPH"
    SOURCE_PATCH = "SOURCE_PATCH"
    BUILD = "BUILD"
    SCREENSHOT = "SCREENSHOT"
    TEST_REPORT = "TEST_REPORT"
    SECURITY_REPORT = "SECURITY_REPORT"
    VERIFICATION_REPORT = "VERIFICATION_REPORT"
    CRITIQUE_REPORT = "CRITIQUE_REPORT"
    QUALITY_SCORE = "QUALITY_SCORE"
    FINAL_DELIVERY = "FINAL_DELIVERY"


class ArtifactStatus(_StringEnum):
    CREATED = "CREATED"
    INSPECTED = "INSPECTED"
    VALIDATED = "VALIDATED"
    REVIEWED = "REVIEWED"
    ACCEPTED = "ACCEPTED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    SUPERSEDED = "SUPERSEDED"


class DataClass(_StringEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SENSITIVE = "SENSITIVE"


class Redaction(_StringEnum):
    NONE = "NONE"
    APPLIED = "APPLIED"
    REQUIRED = "REQUIRED"


class EvidenceKind(_StringEnum):
    OBSERVATION = "OBSERVATION"
    TEST_RESULT = "TEST_RESULT"
    BUILD_RESULT = "BUILD_RESULT"
    SCREENSHOT = "SCREENSHOT"
    TRACE = "TRACE"
    METRIC = "METRIC"
    STATIC_INSPECTION = "STATIC_INSPECTION"
    SOURCE_CITATION = "SOURCE_CITATION"
    HUMAN_INSPECTION = "HUMAN_INSPECTION"


class EvidenceResult(_StringEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    NOT_RUN = "NOT_RUN"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class FreshnessStatus(_StringEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class PrivacyClass(_StringEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SENSITIVE = "SENSITIVE"


class ClaimStatus(_StringEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    NOT_RUN = "NOT_RUN"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ProcedureStatus(_StringEnum):
    EXECUTED = "EXECUTED"
    FAILED_TO_RUN = "FAILED_TO_RUN"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


class Recommendation(_StringEnum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    BLOCK = "BLOCK"
    FAIL = "FAIL"


class Independence(_StringEnum):
    BUILDER = "BUILDER"
    SEPARATED_SELF = "SEPARATED_SELF"
    INDEPENDENT = "INDEPENDENT"


class FindingSeverity(_StringEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NOTE = "NOTE"


class FindingConfidence(_StringEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FindingCategory(_StringEnum):
    CORRECTNESS = "CORRECTNESS"
    SECURITY = "SECURITY"
    COMPLETENESS = "COMPLETENESS"
    USABILITY = "USABILITY"
    PERFORMANCE = "PERFORMANCE"
    PROVENANCE = "PROVENANCE"
    PROCESS = "PROCESS"


class FindingDisposition(_StringEnum):
    OPEN = "OPEN"
    ACCEPTED_RISK = "ACCEPTED_RISK"
    FIXED = "FIXED"
    REJECTED_WITH_REASON = "REJECTED_WITH_REASON"


class StopRecommendation(_StringEnum):
    CONTINUE = "CONTINUE"
    REPAIR = "REPAIR"
    STOP = "STOP"
    ESCALATE = "ESCALATE"


class ResidualRisk(_StringEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class QualityDimensionName(_StringEnum):
    CORRECTNESS = "CORRECTNESS"
    COMPLETENESS = "COMPLETENESS"
    USABILITY = "USABILITY"
    PERFORMANCE = "PERFORMANCE"
    SECURITY = "SECURITY"
    OPERABILITY = "OPERABILITY"
    PROVENANCE = "PROVENANCE"
    VISUAL_FIDELITY = "VISUAL_FIDELITY"


class GateStatus(_StringEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    NOT_RUN = "NOT_RUN"
    BLOCKED = "BLOCKED"


class QualityBand(_StringEnum):
    AAA_VERIFIED = "AAA_VERIFIED"
    AAA_CANDIDATE = "AAA_CANDIDATE"
    ACCEPTABLE = "ACCEPTABLE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class QualityDecision(_StringEnum):
    DELIVER = "DELIVER"
    DELIVER_WITH_LIMITATIONS = "DELIVER_WITH_LIMITATIONS"
    REPAIR = "REPAIR"
    STOP = "STOP"
    ESCALATE = "ESCALATE"


class TelemetryEventType(_StringEnum):
    RUN_CREATED = "RUN_CREATED"
    TASK_RECEIVED = "TASK_RECEIVED"
    TASK_CLASSIFIED = "TASK_CLASSIFIED"
    ROUTE_SELECTED = "ROUTE_SELECTED"
    GRAPH_CREATED = "GRAPH_CREATED"
    CAPABILITY_SELECTED = "CAPABILITY_SELECTED"
    CAPABILITY_LOADED = "CAPABILITY_LOADED"
    INVOCATION_STARTED = "INVOCATION_STARTED"
    TOOL_CALLED = "TOOL_CALLED"
    TOOL_RESULT = "TOOL_RESULT"
    INVOCATION_FINISHED = "INVOCATION_FINISHED"
    RETRY = "RETRY"
    VALIDATION_RUN = "VALIDATION_RUN"
    VALIDATION_FAIL = "VALIDATION_FAIL"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_FINISHED = "VERIFICATION_FINISHED"
    CRITIQUE_RUN = "CRITIQUE_RUN"
    CRITIQUE_RECORDED = "CRITIQUE_RECORDED"
    ASSURANCE_DECIDED = "ASSURANCE_DECIDED"
    STOP_TRIGGERED = "STOP_TRIGGERED"
    GAUNTLET_PASS = "GAUNTLET_PASS"
    GAUNTLET_FAIL = "GAUNTLET_FAIL"
    DELIVERY = "DELIVERY"
    RUN_COMPLETED = "RUN_COMPLETED"


class Ordering(_StringEnum):
    IN_ORDER = "IN_ORDER"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    UNKNOWN = "UNKNOWN"


class LifecycleState(_StringEnum):
    NEW = "NEW"
    CLASSIFIED = "CLASSIFIED"
    ROUTED = "ROUTED"
    PLANNED = "PLANNED"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    REVIEWING = "REVIEWING"
    REPAIRING = "REPAIRING"
    ASSURING = "ASSURING"
    PASSED = "PASSED"
    DELIVERED = "DELIVERED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DeliveryStatus(_StringEnum):
    NOT_DELIVERED = "NOT_DELIVERED"
    DELIVERED = "DELIVERED"
    DELIVERED_WITH_LIMITATIONS = "DELIVERED_WITH_LIMITATIONS"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class Provenance(_ValueModel):
    source_type: SourceType
    source_refs: tuple[str, ...] = ()
    created_at: str = ""


@dataclass(frozen=True, slots=True)
class RecordEnvelope(_ValueModel):
    status: RecordStatus
    provenance: Provenance
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RepositoryContext(_ValueModel):
    root: str | None
    classification: RepositoryClassification
    trust_state: TrustState


@dataclass(frozen=True, slots=True)
class EvidenceSummary(_ValueModel):
    refs: tuple[str, ...]
    confidence: Confidence


@dataclass(frozen=True, slots=True)
class ClassificationTrace(_ValueModel):
    rule_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    unresolved: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TaskProfile(_ValueModel):
    schema_version: SchemaVersion | str
    task_id: str
    run_id: str
    record: RecordEnvelope
    objective: str
    requested_outcome: str
    domain: TaskDomain
    complexity: Complexity
    risk: Risk
    visual_importance: VisualImportance
    security_impact: SecurityImpact
    data_impact: DataImpact
    user_impact: UserImpact
    blast_radius: BlastRadius
    research_need: ResearchNeed
    parallelism_potential: ParallelismPotential
    reversibility: Reversibility
    confidence: Confidence
    constraints: tuple[str, ...]
    non_goals: tuple[str, ...]
    repository_context: RepositoryContext
    evidence: EvidenceSummary
    classification_trace: ClassificationTrace
    created_at: str


@dataclass(frozen=True, slots=True)
class SelectedCapability(_ValueModel):
    capability_id: str
    role: CapabilityPrimaryType
    reason: str
    required: bool


@dataclass(frozen=True, slots=True)
class OptionalCapability(_ValueModel):
    capability_id: str
    when: str
    reason: str


@dataclass(frozen=True, slots=True)
class OmittedCapability(_ValueModel):
    capability_id: str
    reason_code: OmittedReasonCode
    explanation: str


@dataclass(frozen=True, slots=True)
class RouteDecisionDetails(_ValueModel):
    precedence_rule_ids: tuple[str, ...]
    activation_reasons: tuple[str, ...]
    non_activation_reasons: tuple[str, ...]
    alternatives_considered: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RouteCompatibility(_ValueModel):
    native_tools_considered: tuple[str, ...]
    provider_constraints: tuple[str, ...]
    conflicts_checked: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RouteBudget(_ValueModel):
    token_estimate: int | None
    latency_budget_ms: int | None
    parallelism_budget: int


@dataclass(frozen=True, slots=True)
class ContextBudget(_ValueModel):
    max_skill_kernels: int | None
    max_reference_pack: ReferencePack | str | None


@dataclass(frozen=True, slots=True)
class RouteDecision(_ValueModel):
    schema_version: SchemaVersion | str
    decision_id: str
    task_id: str
    run_id: str
    record: RecordEnvelope
    profile_ref: str
    route_status: RouteStatus
    route_kind: RouteKind
    decision: RouteDecisionDetails
    compatibility: RouteCompatibility
    budget: RouteBudget
    context_budget: ContextBudget
    confidence: Confidence
    authority_ref: str
    created_at: str
    selected: tuple[SelectedCapability, ...] = ()
    optional: tuple[OptionalCapability, ...] = ()
    omitted: tuple[OmittedCapability, ...] = ()
    quality_gates: tuple[str, ...] = ()
    fallback: str | None = None
    unresolved: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NodeBudget(_ValueModel):
    tokens: int | None
    duration_ms: int | None


@dataclass(frozen=True, slots=True)
class ExecutionNode(_ValueModel):
    node_id: str
    kind: NodeKind | str
    capability_id: str
    owner: str
    input_refs: tuple[str, ...]
    output_contract: str
    depends_on: tuple[str, ...]
    can_parallelize: bool
    required: bool
    budget: NodeBudget
    acceptance_refs: tuple[str, ...]
    provider_id: str | None = None
    invocation_ref: str | None = None
    artifact_refs: tuple[str, ...] = ()
    node_status: InvocationStatus | str = InvocationStatus.REQUESTED
    allow_failed_dependencies: bool = False


@dataclass(frozen=True, slots=True)
class ExecutionEdge(_ValueModel):
    from_node: str = field(metadata={"json_key": "from"})
    to_node: str = field(metadata={"json_key": "to"})
    relation: EdgeRelation | str = EdgeRelation.DATA


@dataclass(frozen=True, slots=True)
class MergePoint(_ValueModel):
    node_id: str
    conflict_owner: MergeConflictOwner
    unresolved_policy: UnresolvedPolicy | str


@dataclass(frozen=True, slots=True)
class ExecutionGraph(_ValueModel):
    schema_version: SchemaVersion | str
    graph_id: str
    task_id: str
    run_id: str
    record: RecordEnvelope
    goal: str
    nodes: tuple[ExecutionNode, ...]
    edges: tuple[ExecutionEdge, ...]
    merge_points: tuple[MergePoint, ...]
    graph_status: GraphStatus
    stop_policy_ref: str
    created_at: str
    graph_owner: str = "orchestrator"
    graph_budget: NodeBudget | None = None
    acceptance_refs: tuple[str, ...] = ()
    merge_policy: UnresolvedPolicy | str = UnresolvedPolicy.PRESERVE_AND_ESCALATE
    conflict_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CapabilityScope(_ValueModel):
    domains: tuple[str, ...]
    activates_when: tuple[str, ...]
    do_not_activate_when: tuple[str, ...]
    minimum_task_class: Complexity


@dataclass(frozen=True, slots=True)
class CapabilityContracts(_ValueModel):
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    gates: tuple[str, ...]
    stop_conditions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CapabilityComposition(_ValueModel):
    can_call: tuple[str, ...]
    can_be_called_by: tuple[str, ...]
    must_run_before: tuple[str, ...]
    must_run_after: tuple[str, ...]
    conflicts_with: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CapabilityDependencies(_ValueModel):
    capabilities: tuple[str, ...]
    tools: tuple[str, ...]
    providers: tuple[str, ...]
    references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ManifestProvenance(_ValueModel):
    source_type: SourceType
    source_refs: tuple[str, ...]
    inspected_at: str
    source_repository: str
    source_hash: str
    origin: RegistryOrigin
    precedence: int
    installation_scope: InstallationScope
    project_scope: str | None
    forked_from: str | None = None


@dataclass(frozen=True, slots=True)
class CapabilityCompatibility(_ValueModel):
    host_features: tuple[str, ...]
    platform_limits: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CapabilityQuality(_ValueModel):
    profile: str
    eval_refs: tuple[str, ...]
    benchmark_refs: tuple[str, ...]
    last_result: GateStatus | str


@dataclass(frozen=True, slots=True)
class CapabilitySecurity(_ValueModel):
    permissions: tuple[str, ...]
    data_classes: tuple[str, ...]
    secret_policy: str


@dataclass(frozen=True, slots=True)
class ContextCost(_ValueModel):
    metadata_tokens_estimate: int | None
    body_tokens_estimate: int | None


@dataclass(frozen=True, slots=True)
class Deprecation(_ValueModel):
    successor: str | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class CapabilityManifest(_ValueModel):
    schema_version: SchemaVersion | str
    capability_id: str
    display_name: str
    version: str
    record: RecordEnvelope
    primary_type: CapabilityPrimaryType
    status: CapabilityStatus
    owner: str
    scope: CapabilityScope
    contracts: CapabilityContracts
    composition: CapabilityComposition
    dependencies: CapabilityDependencies
    provenance: ManifestProvenance
    compatibility: CapabilityCompatibility
    quality: CapabilityQuality
    security: CapabilitySecurity
    context_cost: ContextCost
    deprecation: Deprecation


class CapabilityStatus(_StringEnum):
    CANDIDATE = "CANDIDATE"
    EXPERIMENTAL = "EXPERIMENTAL"
    VERIFIED = "VERIFIED"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class InvocationCaller(_ValueModel):
    capability_id: str
    authority_ref: str


@dataclass(frozen=True, slots=True)
class InvocationCallee(_ValueModel):
    capability_id: str
    manifest_version: str


@dataclass(frozen=True, slots=True)
class InvocationInputs(_ValueModel):
    artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    payload_digest: str


@dataclass(frozen=True, slots=True)
class InvocationHandoff(_ValueModel):
    acceptance_refs: tuple[str, ...]
    required_output_contracts: tuple[str, ...]
    known_bad_conditions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InvocationLimits(_ValueModel):
    token_budget: int | None
    duration_budget_ms: int | None
    tool_call_budget: int | None
    retry_budget: int


@dataclass(frozen=True, slots=True)
class CapabilityInvocation(_ValueModel):
    schema_version: SchemaVersion | str
    invocation_id: str
    task_id: str
    run_id: str
    record: RecordEnvelope
    graph_node_id: str | None
    caller: InvocationCaller
    callee: InvocationCallee
    objective: str
    scope: tuple[str, ...]
    non_goals: tuple[str, ...]
    inputs: InvocationInputs
    handoff: InvocationHandoff
    limits: InvocationLimits
    permissions: tuple[str, ...]
    requested_tools: tuple[str, ...]
    expected_evidence: tuple[str, ...]
    invocation_status: InvocationStatus
    failure_refs: tuple[str, ...]
    started_at: str | None
    completed_at: str | None
    operation: str = ""
    capability_origin: RegistryOrigin | str | None = None
    dependencies: tuple[str, ...] = ()
    trace_context: tuple[tuple[str, str], ...] = ()
    provider_id: str | None = None
    authority_snapshot_ref: str | None = None
    delegation_ref: str | None = None
    repair_of: str | None = None
    repair_trigger_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ArtifactProducer(_ValueModel):
    capability_id: str
    invocation_id: str | None


@dataclass(frozen=True, slots=True)
class ArtifactContent(_ValueModel):
    locator: str | None
    digest: str
    media_type: str
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class ArtifactSecurity(_ValueModel):
    data_class: DataClass
    redaction: Redaction
    access_policy: str


@dataclass(frozen=True, slots=True)
class ArtifactProvenance(_ValueModel):
    origin: SourceType | str
    tool_or_process: str | None
    parent_artifacts: tuple[str, ...]
    created_at: str


@dataclass(frozen=True, slots=True)
class ArtifactRecord(_ValueModel):
    schema_version: SchemaVersion | str
    artifact_id: str
    task_id: str
    run_id: str
    record: RecordEnvelope
    artifact_type: ArtifactType
    title: str
    producer: ArtifactProducer
    content: ArtifactContent
    source_refs: tuple[str, ...]
    contract_refs: tuple[str, ...]
    dependencies: tuple[str, ...]
    artifact_status: ArtifactStatus
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]
    security: ArtifactSecurity
    provenance: ArtifactProvenance
    supersedes: str | None


@dataclass(frozen=True, slots=True)
class EvidenceProcedure(_ValueModel):
    procedure_id: str
    description: str
    command_or_method: str
    executed: bool


@dataclass(frozen=True, slots=True)
class EvidenceEnvironment(_ValueModel):
    host: str | None
    version: str | None
    fixture: str | None
    tool: str | None


@dataclass(frozen=True, slots=True)
class EvidenceFreshness(_ValueModel):
    status: FreshnessStatus
    invalidated_by: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceProvenance(_ValueModel):
    source_type: SourceType
    source_ref: str
    content_digest: str | None


@dataclass(frozen=True, slots=True)
class EvidenceRecord(_ValueModel):
    schema_version: SchemaVersion | str
    evidence_id: str
    task_id: str
    run_id: str
    record: RecordEnvelope
    claim_ref: str
    evidence_kind: EvidenceKind
    procedure: EvidenceProcedure
    result: EvidenceResult
    observation: str
    artifact_refs: tuple[str, ...]
    environment: EvidenceEnvironment
    observed_at: str
    freshness: EvidenceFreshness
    provenance: EvidenceProvenance
    limitations: tuple[str, ...]
    confidence: Confidence
    privacy_class: PrivacyClass
    owner: str = "local.verifier"


@dataclass(frozen=True, slots=True)
class Claim(_ValueModel):
    claim_id: str
    text: str
    required: bool
    status: ClaimStatus
    evidence_refs: tuple[str, ...]
    limitation_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VerificationProcedure(_ValueModel):
    procedure_id: str
    description: str
    status: ProcedureStatus
    result: EvidenceResult
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Coverage(_ValueModel):
    required_claims: int
    evidenced_claims: int
    percentage: float | None


@dataclass(frozen=True, slots=True)
class Verifier(_ValueModel):
    capability_id: str
    independence: Independence
    blind_packet_digest: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationReport(_ValueModel):
    schema_version: SchemaVersion | str
    report_id: str
    task_id: str
    run_id: str
    record: RecordEnvelope
    artifact_refs: tuple[str, ...]
    acceptance_refs: tuple[str, ...]
    claims: tuple[Claim, ...]
    procedures: tuple[VerificationProcedure, ...]
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    not_run: tuple[str, ...]
    unknown: tuple[str, ...]
    limitations: tuple[str, ...]
    coverage: Coverage
    confidence: Confidence
    blockers: tuple[str, ...]
    recommendation: Recommendation
    verifier: Verifier
    created_at: str


@dataclass(frozen=True, slots=True)
class CritiqueFinding(_ValueModel):
    finding_id: str
    severity: FindingSeverity
    category: FindingCategory
    statement: str
    evidence_refs: tuple[str, ...]
    affected_refs: tuple[str, ...]
    confidence: FindingConfidence
    disposition: FindingDisposition
    owner: str | None


@dataclass(frozen=True, slots=True)
class CritiqueReport(_ValueModel):
    schema_version: SchemaVersion | str
    report_id: str
    task_id: str
    run_id: str
    record: RecordEnvelope
    reviewed_artifacts: tuple[str, ...]
    reviewed_reports: tuple[str, ...]
    quality_bar_ref: str
    independence: Independence
    findings: tuple[CritiqueFinding, ...]
    strengths: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    stop_recommendation: StopRecommendation
    residual_risk: ResidualRisk | str
    limitations: tuple[str, ...]
    reviewer: Verifier
    created_at: str


@dataclass(frozen=True, slots=True)
class QualityDimension(_ValueModel):
    dimension: QualityDimensionName
    score: float | None
    confidence: Confidence
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QualityGate(_ValueModel):
    gate_id: str
    status: GateStatus
    required: bool
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QualityReport(_ValueModel):
    schema_version: SchemaVersion | str
    report_id: str
    task_id: str
    run_id: str
    record: RecordEnvelope
    profile: str
    artifact_refs: tuple[str, ...]
    verification_ref: str | None
    critique_ref: str | None
    dimensions: tuple[QualityDimension, ...]
    gates: tuple[QualityGate, ...]
    quality_band: QualityBand
    open_findings: tuple[str, ...]
    residual_risk: ResidualRisk | str
    decision: QualityDecision
    decision_owner: str
    created_at: str


@dataclass(frozen=True, slots=True)
class TelemetryActor(_ValueModel):
    capability_id: str | None
    invocation_id: str | None


@dataclass(frozen=True, slots=True)
class TelemetryPayload(_ValueModel):
    input_size: int | None
    output_size: int | None
    token_estimate: int | None
    duration_ms: int | None
    tool: str | None
    result: EvidenceResult | None


@dataclass(frozen=True, slots=True)
class TelemetryIntegrity(_ValueModel):
    previous_event_digest: str | None
    event_digest: str
    ordering: Ordering


@dataclass(frozen=True, slots=True)
class TelemetryEvent(_ValueModel):
    schema_version: SchemaVersion | str
    event_id: str
    event_sequence: int
    timestamp: str
    task_id: str
    run_id: str
    record: RecordEnvelope
    parent_event_id: str | None
    event_type: TelemetryEventType
    actor: TelemetryActor
    reason: str | None
    payload: TelemetryPayload
    artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    privacy_class: PrivacyClass
    redaction: Redaction
    integrity: TelemetryIntegrity
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GateSummary(_ValueModel):
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    not_run: tuple[str, ...]
    blocked: tuple[str, ...]
    unknown: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExecutionSummary(_ValueModel):
    started_at: str
    completed_at: str | None
    duration_ms: int | None
    retries: int
    stop_reason: str | None


@dataclass(frozen=True, slots=True)
class ResourceUsage(_ValueModel):
    token_estimate: int | None
    cost_estimate: float | None
    tool_calls: int
    parallel_lanes: int


@dataclass(frozen=True, slots=True)
class Delivery(_ValueModel):
    status: DeliveryStatus
    artifact_ref: str | None
    decision_owner: str | None


@dataclass(frozen=True, slots=True)
class RunSummary(_ValueModel):
    schema_version: SchemaVersion | str
    summary_id: str
    task_id: str
    run_id: str
    record: RecordEnvelope
    lifecycle_state: LifecycleState
    route_ref: str
    profile_ref: str
    graph_ref: str | None
    selected_capabilities: tuple[str, ...]
    loaded_capabilities: tuple[str, ...]
    artifacts: tuple[str, ...]
    evidence: tuple[str, ...]
    verification_ref: str | None
    critique_ref: str | None
    quality_ref: str | None
    gate_summary: GateSummary
    execution: ExecutionSummary
    resource_usage: ResourceUsage
    delivery: Delivery
    limitations: tuple[str, ...]
    open_questions: tuple[str, ...]
    confidence: Confidence
    created_at: str
    residual_risk: ResidualRisk | str = ResidualRisk.UNKNOWN


# Small compatibility aliases keep the public vocabulary discoverable without
# adding alternate model shapes.
Status = RecordStatus
ProvenanceSourceType = SourceType
EvidenceFreshnessStatus = FreshnessStatus
TelemetryType = TelemetryEventType
Reviewer = Verifier
DecisionDetails = RouteDecisionDetails
TaskStatus = LifecycleState


type ContractRecord = (
    TaskProfile
    | RouteDecision
    | ExecutionGraph
    | CapabilityManifest
    | CapabilityInvocation
    | ArtifactRecord
    | EvidenceRecord
    | VerificationReport
    | CritiqueReport
    | QualityReport
    | TelemetryEvent
    | RunSummary
)


def is_contract_record(value: object) -> bool:
    """Return whether ``value`` is one of the twelve top-level records."""

    return is_dataclass(value) and isinstance(
        value,
        (
            TaskProfile,
            RouteDecision,
            ExecutionGraph,
            CapabilityManifest,
            CapabilityInvocation,
            ArtifactRecord,
            EvidenceRecord,
            VerificationReport,
            CritiqueReport,
            QualityReport,
            TelemetryEvent,
            RunSummary,
        ),
    )
