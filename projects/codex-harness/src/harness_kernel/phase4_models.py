"""Immutable contracts for the bounded Phase 4 capability invocation boundary."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from .phase3_models import CapabilityInventory, CapabilityRecord, ResolutionResult


class Phase4Enum(StrEnum):
    def __str__(self) -> str:
        return self.value


class ExecutionMode(Phase4Enum):
    DRY_RUN = "DRY_RUN"
    PREPARE_ONLY = "PREPARE_ONLY"
    CONTROLLED_REAL = "CONTROLLED_REAL"
    BLOCKED = "BLOCKED"


class InvocationLifecycle(Phase4Enum):
    DISCOVERED = "DISCOVERED"
    RESOLVED = "RESOLVED"
    AUTHORIZED = "AUTHORIZED"
    CONTEXT_PREPARED = "CONTEXT_PREPARED"
    INVOCATION_REQUESTED = "INVOCATION_REQUESTED"
    HOST_ACKNOWLEDGED = "HOST_ACKNOWLEDGED"
    EXECUTING = "EXECUTING"
    RESULT_RECEIVED = "RESULT_RECEIVED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class InvocationResultStatus(Phase4Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILURE = "FAILURE"
    BLOCKED = "BLOCKED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
    PREPARED = "PREPARED"


class HostLoadObservation(Phase4Enum):
    OBSERVED = "HOST_LOAD_OBSERVED"
    PARTIAL = "HOST_LOAD_PARTIAL"
    UNOBSERVABLE = "HOST_LOAD_UNOBSERVABLE"
    UNSUPPORTED = "HOST_LOAD_UNSUPPORTED"


class FactStatus(Phase4Enum):
    HOST_OBSERVED = "HOST_OBSERVED"
    HARNESS_OBSERVED = "HARNESS_OBSERVED"
    DECLARED_BY_CAPABILITY = "DECLARED_BY_CAPABILITY"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class ArtifactType(Phase4Enum):
    HOST_RESPONSE = "HOST_RESPONSE"
    FILE = "FILE"
    VISUAL = "VISUAL"
    UNKNOWN = "UNKNOWN"


class AssuranceDecision(Phase4Enum):
    PASS = "PASS"
    PASS_WITH_LIMITATIONS = "PASS_WITH_LIMITATIONS"
    REPAIR = "REPAIR"
    STOP = "STOP"
    BLOCK = "BLOCK"


_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


def _freeze_mapping(value: Mapping[str, object] | None) -> Mapping[str, object]:
    if value is None:
        return MappingProxyType({})
    frozen = _freeze(value)
    if not isinstance(frozen, Mapping):
        raise TypeError("mapping value could not be frozen")
    return frozen


def _as_tuple(
    values: tuple[str, ...] | list[str] | None, *, deduplicate: bool = True
) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise ValueError("Phase 4 string collections must be lists or tuples")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or "\x00" in value:
            raise ValueError("Phase 4 string values must be non-empty NUL-free strings")
        if not deduplicate or value not in result:
            result.append(value)
    return tuple(result)


def _validate_digest(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a sha256 digest")


def _validate_text(value: str, field_name: str, *, max_length: int = 32_768) -> None:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > max_length:
        raise ValueError(f"{field_name} is invalid or exceeds its bound")


def _validate_bool(value: object, field_name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be boolean")


def _validate_int(value: object, field_name: str, *, minimum: int = 0) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{field_name} must be an integer >= {minimum}")


def public_data(value: object) -> object:
    """Convert records to JSON-safe values without exposing arbitrary objects."""

    if isinstance(value, Phase4Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: public_data(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): public_data(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [public_data(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def canonical_json(value: object) -> str:
    return json.dumps(public_data(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_payload(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _stable_digest_value(
    value: object,
    *,
    workspace: Path | None,
    home: Path,
) -> object:
    """Canonicalize host paths without making evidence digests machine-local."""

    if isinstance(value, str):
        result = value
        if workspace is not None:
            result = result.replace(str(workspace), "$WORKSPACE")
        return result.replace(str(home), "$HOME")
    if isinstance(value, Mapping):
        return {
            str(key): _stable_digest_value(item, workspace=workspace, home=home)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_stable_digest_value(item, workspace=workspace, home=home) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _stable_digest_value(
                getattr(value, item.name), workspace=workspace, home=home
            )
            for item in fields(value)
        }
    if isinstance(value, Path):
        return _stable_digest_value(str(value), workspace=workspace, home=home)
    return value


def stable_digest_payload(value: object, *, workspace: str | Path | None = None) -> str:
    """Digest a payload while aliasing project and home paths consistently."""

    workspace_path = Path(workspace).resolve(strict=False) if workspace is not None else None
    normalized = _stable_digest_value(
        value,
        workspace=workspace_path,
        home=Path.home().resolve(strict=False),
    )
    return digest_payload(normalized)


@dataclass(frozen=True, slots=True)
class Phase4Budget:
    timeout_seconds: int = 60
    max_context_bytes: int = 128 * 1024
    max_host_events: int = 512
    max_tool_calls: int = 0
    max_repair_iterations: int = 0
    max_verification_iterations: int = 1
    max_artifacts: int = 16
    max_evidence: int = 64
    max_output_bytes: int = 256 * 1024

    def __post_init__(self) -> None:
        for name in (
            "timeout_seconds",
            "max_context_bytes",
            "max_host_events",
            "max_output_bytes",
        ):
            _validate_int(getattr(self, name), name, minimum=1)
        for name in (
            "max_tool_calls",
            "max_repair_iterations",
            "max_verification_iterations",
            "max_artifacts",
            "max_evidence",
        ):
            _validate_int(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class CapabilityExecutionAuthorization:
    authorization_id: str
    task_id: str
    run_id: str
    capability_id: str
    capability_version: str
    package_fingerprint: str
    scope: str
    requested_loading_level: str
    requested_execution_mode: ExecutionMode
    allowed_tools: tuple[str, ...]
    allowed_side_effects: tuple[str, ...]
    filesystem_policy: Mapping[str, object]
    network_policy: str
    shell_policy: str
    provider_policy: str
    mcp_policy: str
    credential_policy: str
    timeout_seconds: int
    iteration_budget: Mapping[str, object]
    context_budget: Mapping[str, object]
    artifact_policy: Mapping[str, object]
    evidence_policy: Mapping[str, object]
    issued_by: str
    issued_at: int
    expires_at: int
    reason: str
    constraints: tuple[str, ...]
    host_executable_digest: str | None = None
    host_interpreter_digest: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "authorization_id",
            "task_id",
            "run_id",
            "capability_id",
            "capability_version",
            "scope",
            "requested_loading_level",
            "issued_by",
            "reason",
        ):
            _validate_text(getattr(self, name), name, max_length=512)
        _validate_digest(self.package_fingerprint, "package_fingerprint")
        if self.host_executable_digest is not None:
            _validate_digest(self.host_executable_digest, "host_executable_digest")
        if self.host_interpreter_digest is not None:
            _validate_digest(self.host_interpreter_digest, "host_interpreter_digest")
        _validate_int(self.issued_at, "issued_at")
        _validate_int(self.expires_at, "expires_at")
        _validate_int(self.timeout_seconds, "timeout_seconds", minimum=1)
        if self.expires_at <= self.issued_at:
            raise ValueError("authorization time bounds are invalid")
        if not isinstance(self.requested_execution_mode, ExecutionMode):
            raise ValueError("requested_execution_mode is invalid")
        policy_values = {
            "network_policy": {"DENY", "ALLOW"},
            "shell_policy": {"DENY", "ALLOW"},
            "provider_policy": {"DENY", "ALLOW", "ALLOW_SELECTED"},
            "mcp_policy": {"DENY", "ALLOW"},
            "credential_policy": {"DENY", "ALLOW"},
        }
        for name, allowed in policy_values.items():
            value = getattr(self, name)
            if not isinstance(value, str) or value not in allowed:
                raise ValueError(f"{name} is unsupported")
        object.__setattr__(self, "allowed_tools", _as_tuple(self.allowed_tools))
        object.__setattr__(self, "allowed_side_effects", _as_tuple(self.allowed_side_effects))
        object.__setattr__(self, "constraints", _as_tuple(self.constraints))
        for name in (
            "filesystem_policy",
            "iteration_budget",
            "context_budget",
            "artifact_policy",
            "evidence_policy",
        ):
            object.__setattr__(self, name, _freeze_mapping(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class ContextManifest:
    task_id: str
    task_digest: str
    capability_id: str
    package_fingerprint: str
    skill_path: str
    sources: tuple[str, ...]
    selected_references: tuple[str, ...]
    omitted_references: tuple[str, ...]
    estimated_bytes: int
    digest: str
    acceptance_criteria: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("task_id", "capability_id", "skill_path"):
            _validate_text(getattr(self, name), name, max_length=1024)
        _validate_digest(self.task_digest, "task_digest")
        _validate_digest(self.package_fingerprint, "package_fingerprint")
        _validate_digest(self.digest, "digest")
        _validate_int(self.estimated_bytes, "estimated_bytes")
        for name in (
            "sources",
            "selected_references",
            "omitted_references",
            "acceptance_criteria",
        ):
            object.__setattr__(self, name, _as_tuple(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class CapabilityInvocationRequest:
    invocation_id: str
    authorization: CapabilityExecutionAuthorization
    context: ContextManifest
    skill_name: str
    skill_path: str
    task: str
    acceptance_criteria: tuple[str, ...]
    workspace: str
    expected_artifacts: tuple[str, ...]
    idempotency_key: str

    def __post_init__(self) -> None:
        for name in (
            "invocation_id",
            "skill_name",
            "skill_path",
            "workspace",
            "idempotency_key",
        ):
            _validate_text(getattr(self, name), name, max_length=2048)
        _validate_text(self.task, "task", max_length=16_384)
        if not Path(self.workspace).is_absolute() or not Path(self.skill_path).is_absolute():
            raise ValueError("workspace and skill_path must be absolute")
        object.__setattr__(self, "acceptance_criteria", _as_tuple(self.acceptance_criteria))
        object.__setattr__(self, "expected_artifacts", _as_tuple(self.expected_artifacts))
        if self.authorization.capability_id != self.skill_name:
            raise ValueError("authorization capability does not match skill name")
        if self.authorization.task_id != self.context.task_id:
            raise ValueError("authorization task does not match context task")
        if self.authorization.capability_id != self.context.capability_id:
            raise ValueError("authorization capability does not match context capability")
        if self.context.package_fingerprint != self.authorization.package_fingerprint:
            raise ValueError("context fingerprint does not match authorization")
        if self.context.skill_path != self.skill_path:
            raise ValueError("context skill path does not match request")
        if self.context.task_digest != digest_payload(self.task):
            raise ValueError("context task digest does not match request task")
        if self.context.acceptance_criteria != self.acceptance_criteria:
            raise ValueError("context acceptance criteria do not match request")
        authorized_host_digest = self.authorization.filesystem_policy.get("host_executable_digest")
        if self.authorization.host_executable_digest != authorized_host_digest:
            raise ValueError("authorization host executable digest is not policy-bound")
        authorized_interpreter_digest = self.authorization.filesystem_policy.get(
            "host_interpreter_digest"
        )
        if self.authorization.host_interpreter_digest != authorized_interpreter_digest:
            raise ValueError("authorization host interpreter digest is not policy-bound")
        authorized_workspace = self.authorization.filesystem_policy.get("workspace")
        if (
            isinstance(authorized_workspace, str)
            and authorized_workspace
            and str(Path(self.workspace).resolve()) != str(Path(authorized_workspace).resolve())
        ):
            raise ValueError("request workspace does not match authorization")
        authorized_types = self.authorization.artifact_policy.get("types")
        if (
            isinstance(authorized_types, (list, tuple))
            and authorized_types
            and tuple(authorized_types) != self.expected_artifacts
        ):
            raise ValueError("request artifact types do not match authorization")


@dataclass(frozen=True, slots=True)
class HostPreparation:
    supported: bool
    reason: str
    official_support: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        _validate_bool(self.supported, "supported")
        _validate_text(self.reason, "reason", max_length=2048)
        object.__setattr__(self, "official_support", _freeze_mapping(self.official_support))


@dataclass(frozen=True, slots=True)
class Phase4Event:
    sequence: int
    method: str
    fact_status: FactStatus
    event_class: str
    item_type: str | None = None
    item_id: str | None = None
    status: str | None = None
    detail: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None

    def __post_init__(self) -> None:
        _validate_int(self.sequence, "sequence")
        if not isinstance(self.fact_status, FactStatus):
            raise ValueError("fact_status is invalid")
        _validate_text(self.method, "method", max_length=256)
        _validate_text(self.event_class, "event_class", max_length=256)
        for name in (
            "item_type",
            "item_id",
            "status",
            "detail",
            "thread_id",
            "turn_id",
        ):
            value = getattr(self, name)
            if value is not None:
                _validate_text(value, name, max_length=2_048)


@dataclass(frozen=True, slots=True)
class ProtocolMessageObservation:
    """Bounded observation of every protocol message parsed from the host."""

    sequence: int
    method: str | None
    message_kind: str
    has_id: bool
    has_error: bool

    def __post_init__(self) -> None:
        _validate_int(self.sequence, "sequence")
        if self.method is not None:
            _validate_text(self.method, "method", max_length=256)
        if self.message_kind not in {"request", "notification", "response"}:
            raise ValueError("message_kind is invalid")
        _validate_bool(self.has_id, "has_id")
        _validate_bool(self.has_error, "has_error")


@dataclass(frozen=True, slots=True)
class HostInvocationResult:
    status: InvocationResultStatus
    thread_id: str | None
    session_id: str | None
    turn_id: str | None
    host_version: str
    events: tuple[Phase4Event, ...]
    final_message: str | None
    load_observation: HostLoadObservation
    invocation_observed: bool
    execution_observed: bool
    denied_approvals: int
    cancellation_status: str
    error_code: str | None
    started_at: int
    completed_at: int | None
    protocol_message_count: int = 0
    mcp_event_count: int = 0
    approval_request_count: int = 0
    protocol_messages: tuple[ProtocolMessageObservation, ...] = ()
    host_executable_path: str | None = None
    host_executable_digest: str | None = None
    host_command: tuple[str, ...] = ()
    host_interpreter_path: str | None = None
    host_interpreter_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, InvocationResultStatus):
            raise ValueError("status is invalid")
        if not isinstance(self.load_observation, HostLoadObservation):
            raise ValueError("load_observation is invalid")
        for name in ("invocation_observed", "execution_observed"):
            _validate_bool(getattr(self, name), name)
        _validate_text(self.host_version, "host_version", max_length=512)
        if self.final_message is not None:
            _validate_text(self.final_message, "final_message", max_length=256_000)
        for name in ("thread_id", "session_id", "turn_id", "error_code"):
            value = getattr(self, name)
            if value is not None:
                _validate_text(value, name, max_length=512)
        _validate_int(self.denied_approvals, "denied_approvals")
        _validate_int(self.protocol_message_count, "protocol_message_count")
        _validate_int(self.mcp_event_count, "mcp_event_count")
        _validate_int(self.approval_request_count, "approval_request_count")
        if self.mcp_event_count > self.protocol_message_count:
            raise ValueError("mcp_event_count cannot exceed protocol_message_count")
        if self.approval_request_count > self.protocol_message_count:
            raise ValueError("approval_request_count cannot exceed protocol_message_count")
        object.__setattr__(self, "protocol_messages", tuple(self.protocol_messages))
        if any(not isinstance(item, ProtocolMessageObservation) for item in self.protocol_messages):
            raise ValueError("protocol_messages contain an invalid record")
        if self.protocol_messages:
            if len(self.protocol_messages) != self.protocol_message_count:
                raise ValueError("protocol_messages must cover every parsed protocol message")
            if tuple(item.sequence for item in self.protocol_messages) != tuple(
                range(self.protocol_message_count)
            ):
                raise ValueError("protocol_messages must have contiguous sequence numbers")
            observed_mcp = sum(
                1
                for item in self.protocol_messages
                if item.method is not None and item.method.startswith("mcpServer/")
            )
            observed_approvals = sum(
                1
                for item in self.protocol_messages
                if item.method is not None and item.method.endswith("requestApproval")
            )
            if observed_mcp != self.mcp_event_count:
                raise ValueError("mcp_event_count does not match protocol observations")
            if observed_approvals != self.approval_request_count:
                raise ValueError("approval_request_count does not match protocol observations")
        for name in ("host_executable_path",):
            value = getattr(self, name)
            if value is not None:
                _validate_text(value, name, max_length=4_096)
                if not Path(value).is_absolute():
                    raise ValueError(f"{name} must be absolute")
        if self.host_executable_digest is not None:
            _validate_digest(self.host_executable_digest, "host_executable_digest")
            if self.host_executable_path is None:
                raise ValueError("host_executable_digest requires host_executable_path")
        if self.host_interpreter_path is not None:
            _validate_text(self.host_interpreter_path, "host_interpreter_path", max_length=4_096)
            if not Path(self.host_interpreter_path).is_absolute():
                raise ValueError("host_interpreter_path must be absolute")
        if self.host_interpreter_digest is not None:
            _validate_digest(self.host_interpreter_digest, "host_interpreter_digest")
            if self.host_interpreter_path is None:
                raise ValueError("host_interpreter_digest requires host_interpreter_path")
        object.__setattr__(self, "host_command", _as_tuple(self.host_command, deduplicate=False))
        _validate_int(self.started_at, "started_at")
        if self.completed_at is not None:
            _validate_int(self.completed_at, "completed_at")
        _validate_text(self.cancellation_status, "cancellation_status", max_length=256)
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        object.__setattr__(self, "events", tuple(self.events))
        if any(not isinstance(item, Phase4Event) for item in self.events):
            raise ValueError("events contain an invalid record")


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: str
    producer_capability: str
    invocation_id: str
    location: str
    digest: str
    artifact_type: ArtifactType
    timestamp: int
    provenance: FactStatus
    dependencies: tuple[str, ...]
    evidence_state: str
    size_bytes: int

    def __post_init__(self) -> None:
        for name in (
            "artifact_id",
            "producer_capability",
            "invocation_id",
            "location",
            "evidence_state",
        ):
            _validate_text(getattr(self, name), name, max_length=2048)
        if not isinstance(self.artifact_type, ArtifactType):
            raise ValueError("artifact_type is invalid")
        if not isinstance(self.provenance, FactStatus):
            raise ValueError("provenance is invalid")
        _validate_digest(self.digest, "digest")
        object.__setattr__(self, "dependencies", _as_tuple(self.dependencies))
        _validate_int(self.timestamp, "timestamp")
        _validate_int(self.size_bytes, "size_bytes")


@dataclass(frozen=True, slots=True)
class VerificationResult:
    status: str
    acceptance_criteria: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    checks: tuple[str, ...]
    reason: str
    request_digest: str
    host_executable_digest: str | None
    host_interpreter_digest: str | None
    digest: str

    def __post_init__(self) -> None:
        _validate_text(self.status, "status", max_length=128)
        _validate_text(self.reason, "reason", max_length=4_096)
        _validate_digest(self.request_digest, "request_digest")
        for name in ("host_executable_digest", "host_interpreter_digest"):
            value = getattr(self, name)
            if value is not None:
                _validate_digest(value, name)
        _validate_digest(self.digest, "digest")
        for name in ("acceptance_criteria", "artifact_refs", "evidence_refs", "checks"):
            object.__setattr__(self, name, _as_tuple(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class AssuranceResult:
    decision: AssuranceDecision
    reason: str
    limitations: tuple[str, ...]
    verification_digest: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, AssuranceDecision):
            raise ValueError("decision is invalid")
        _validate_text(self.reason, "reason", max_length=4_096)
        object.__setattr__(self, "limitations", _as_tuple(self.limitations))
        if self.verification_digest is not None:
            _validate_digest(self.verification_digest, "verification_digest")


@dataclass(frozen=True, slots=True)
class PreflightResult:
    allowed: bool
    mode: ExecutionMode
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    authorization: CapabilityExecutionAuthorization | None
    context: ContextManifest | None
    digest: str

    def __post_init__(self) -> None:
        _validate_bool(self.allowed, "allowed")
        if not isinstance(self.mode, ExecutionMode):
            raise ValueError("mode is invalid")
        object.__setattr__(self, "blockers", _as_tuple(self.blockers))
        object.__setattr__(self, "warnings", _as_tuple(self.warnings))
        _validate_digest(self.digest, "digest")
        if self.allowed and self.blockers:
            raise ValueError("an allowed preflight cannot contain blockers")
        if self.allowed and (self.authorization is None or self.context is None):
            raise ValueError("an allowed preflight requires authorization and context")


@dataclass(frozen=True, slots=True)
class PreparedInvocation:
    record: CapabilityRecord
    inventory: CapabilityInventory
    resolution: ResolutionResult
    request: CapabilityInvocationRequest | None
    preflight: PreflightResult
    mode: ExecutionMode
    prepared_at: int

    def __post_init__(self) -> None:
        _validate_int(self.prepared_at, "prepared_at")
        if self.mode is not self.preflight.mode:
            raise ValueError("prepared mode does not match preflight mode")
        if self.preflight.allowed and self.request is None:
            raise ValueError("an allowed preflight requires an invocation request")
        if not self.preflight.allowed and self.request is not None:
            raise ValueError("a blocked preflight cannot carry an invocation request")
        if self.request is not None and self.preflight.allowed:
            if self.preflight.authorization is None or self.preflight.context is None:
                raise ValueError("an allowed preflight is missing authorization or context")
            if self.request.authorization != self.preflight.authorization:
                raise ValueError("request authorization is not bound to preflight")
            if self.request.context != self.preflight.context:
                raise ValueError("request context is not bound to preflight")
            if self.request.authorization.requested_execution_mode is not self.mode:
                raise ValueError("request authorization mode is not bound to prepared mode")


@dataclass(frozen=True, slots=True)
class InvocationReceipt:
    invocation_id: str
    mode: ExecutionMode
    status: InvocationResultStatus
    capability_id: str
    capability_version: str
    package_fingerprint: str
    authorization_id: str | None
    authorization_digest: str | None
    context_digest: str | None
    request_digest: str | None
    lifecycle: tuple[InvocationLifecycle, ...]
    host_invoked: bool
    host_load_observation: HostLoadObservation
    host_event_count: int
    host_event_digest: str
    result_digest: str | None
    host_executable_path: str | None
    host_executable_digest: str | None
    host_command: tuple[str, ...]
    host_interpreter_path: str | None
    host_interpreter_digest: str | None
    artifact_refs: tuple[str, ...]
    verification_refs: tuple[str, ...]
    created_at: int
    closed_at: int
    receipt_digest: str

    def __post_init__(self) -> None:
        for name in (
            "invocation_id",
            "capability_id",
            "capability_version",
        ):
            _validate_text(getattr(self, name), name, max_length=2048)
        if not isinstance(self.mode, ExecutionMode):
            raise ValueError("mode is invalid")
        if not isinstance(self.status, InvocationResultStatus):
            raise ValueError("status is invalid")
        if not isinstance(self.host_load_observation, HostLoadObservation):
            raise ValueError("host_load_observation is invalid")
        _validate_bool(self.host_invoked, "host_invoked")
        _validate_digest(self.package_fingerprint, "package_fingerprint")
        _validate_digest(self.host_event_digest, "host_event_digest")
        _validate_digest(self.receipt_digest, "receipt_digest")
        for name in (
            "authorization_digest",
            "context_digest",
            "request_digest",
            "result_digest",
        ):
            value = getattr(self, name)
            if value is not None:
                _validate_digest(value, name)
        _validate_int(self.host_event_count, "host_event_count")
        _validate_int(self.created_at, "created_at")
        _validate_int(self.closed_at, "closed_at")
        if self.closed_at < self.created_at:
            raise ValueError("receipt numeric fields are invalid")
        object.__setattr__(self, "lifecycle", tuple(self.lifecycle))
        if not self.lifecycle or self.lifecycle[0] is not InvocationLifecycle.DISCOVERED:
            raise ValueError("receipt lifecycle must begin at DISCOVERED")
        if self.lifecycle[-1] is not InvocationLifecycle.CLOSED:
            raise ValueError("receipt lifecycle must end at CLOSED")
        if any(not isinstance(item, InvocationLifecycle) for item in self.lifecycle):
            raise ValueError("receipt lifecycle contains an invalid state")
        for name in ("host_executable_path", "host_interpreter_path"):
            value = getattr(self, name)
            if value is not None:
                _validate_text(value, name, max_length=4_096)
                if not Path(value).is_absolute():
                    raise ValueError(f"{name} must be absolute")
        for digest_name, path_name in (
            ("host_executable_digest", "host_executable_path"),
            ("host_interpreter_digest", "host_interpreter_path"),
        ):
            value = getattr(self, digest_name)
            if value is not None:
                _validate_digest(value, digest_name)
                if getattr(self, path_name) is None:
                    raise ValueError(f"{digest_name} requires {path_name}")
        object.__setattr__(self, "host_command", _as_tuple(self.host_command, deduplicate=False))
        object.__setattr__(self, "artifact_refs", _as_tuple(self.artifact_refs))
        object.__setattr__(self, "verification_refs", _as_tuple(self.verification_refs))


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    mode: ExecutionMode
    status: InvocationResultStatus
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    host_invoked: bool
    preflight: PreflightResult
    receipt: InvocationReceipt
    artifacts: tuple[ArtifactRecord, ...]
    verification: VerificationResult | None
    assurance: AssuranceResult | None
    host_result: HostInvocationResult | None
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ExecutionMode):
            raise ValueError("mode is invalid")
        if not isinstance(self.status, InvocationResultStatus):
            raise ValueError("status is invalid")
        _validate_bool(self.host_invoked, "host_invoked")
        object.__setattr__(self, "blockers", _as_tuple(self.blockers))
        object.__setattr__(self, "warnings", _as_tuple(self.warnings))
        object.__setattr__(self, "limitations", _as_tuple(self.limitations))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))


def invocation_receipt_material(receipt: InvocationReceipt) -> dict[str, object]:
    """Return the exact immutable field set covered by a receipt digest."""

    return {
        "invocation_id": receipt.invocation_id,
        "mode": receipt.mode,
        "status": receipt.status,
        "capability_id": receipt.capability_id,
        "capability_version": receipt.capability_version,
        "package_fingerprint": receipt.package_fingerprint,
        "authorization_id": receipt.authorization_id,
        "authorization_digest": receipt.authorization_digest,
        "context_digest": receipt.context_digest,
        "request_digest": receipt.request_digest,
        "lifecycle": receipt.lifecycle,
        "host_invoked": receipt.host_invoked,
        "host_load_observation": receipt.host_load_observation,
        "host_event_count": receipt.host_event_count,
        "host_event_digest": receipt.host_event_digest,
        "result_digest": receipt.result_digest,
        "host_executable_path": receipt.host_executable_path,
        "host_executable_digest": receipt.host_executable_digest,
        "host_command": receipt.host_command,
        "host_interpreter_path": receipt.host_interpreter_path,
        "host_interpreter_digest": receipt.host_interpreter_digest,
        "artifact_refs": receipt.artifact_refs,
        "verification_refs": receipt.verification_refs,
        "created_at": receipt.created_at,
        "closed_at": receipt.closed_at,
    }


def invocation_receipt_digest(receipt: InvocationReceipt) -> str:
    return digest_payload(invocation_receipt_material(receipt))
