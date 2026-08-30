"""Immutable, bounded contracts for the project-local Phase 6 verifier."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any


class Phase6Enum(StrEnum):
    def __str__(self) -> str:
        return self.value


class VerificationStatus(Phase6Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    STALE = "STALE"
    NOT_RUN = "NOT_RUN"
    UNKNOWN = "UNKNOWN"


class VerificationProfile(Phase6Enum):
    FOCUSED = "FOCUSED"
    DOMAIN = "DOMAIN"
    FULL = "FULL"
    VISUAL = "VISUAL"
    STRUCTURAL = "STRUCTURAL"
    SECURITY_AWARE = "SECURITY_AWARE"
    COMPOSITION = "COMPOSITION"


class VerificationRole(Phase6Enum):
    VERIFIER = "VERIFIER"
    REVIEWER = "REVIEWER"
    BUILDER = "BUILDER"
    DESIGN_DIRECTOR = "DESIGN_DIRECTOR"
    ORCHESTRATOR = "ORCHESTRATOR"
    ASSURANCE = "ASSURANCE"


class ReadOnlyPolicy(Phase6Enum):
    READ_ONLY = "READ_ONLY"
    MUTATION_DENIED = "MUTATION_DENIED"


class FreshnessStatus(Phase6Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class EvidenceKind(Phase6Enum):
    OBSERVATION = "OBSERVATION"
    ARTIFACT = "ARTIFACT"
    RENDER = "RENDER"
    TEST = "TEST"


class VerificationConfidence(Phase6Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class FindingSeverity(Phase6Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"
    POLISH = "POLISH"


class StopCondition(Phase6Enum):
    ALL_REQUIRED_CRITERIA_RESOLVED = "ALL_REQUIRED_CRITERIA_RESOLVED"
    BLOCKING_FAILURE_FOUND = "BLOCKING_FAILURE_FOUND"
    MISSING_REQUIRED_TOOL = "MISSING_REQUIRED_TOOL"
    MISSING_REQUIRED_ARTIFACT = "MISSING_REQUIRED_ARTIFACT"
    STALE_INPUT = "STALE_INPUT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    NO_PROGRESS = "NO_PROGRESS"
    REPEATED_PROCEDURE_FAILURE = "REPEATED_PROCEDURE_FAILURE"
    HUMAN_OVERRIDE = "HUMAN_OVERRIDE"


_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")
_DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"
_ZERO_DIGEST = "sha256:" + "0" * 64
_MAX_TEXT = 32_768
_MAX_JSON_DEPTH = 16
_MAX_JSON_BYTES = 16 * 1024


def _text(value: object, name: str, *, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > maximum:
        raise ValueError(f"{name} is invalid")
    return value


def _optional_text(value: object, name: str, *, maximum: int = _MAX_TEXT) -> str | None:
    if value is None:
        return None
    return _text(value, name, maximum=maximum)


def _identity(value: object, name: str) -> str:
    candidate = _text(value, name, maximum=200)
    path_parts = candidate.replace("\\", "/").split("/")
    if ".." in path_parts or _IDENTITY_PATTERN.fullmatch(candidate) is None:
        raise ValueError(f"{name} is malformed")
    return candidate


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{name} must be a sha256 digest")
    return value


def _integer(value: object, name: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} exceeds its maximum of {maximum}")
    return value


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _parse_timestamp(value: str, name: str) -> datetime:
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include an explicit timezone")
    return parsed.astimezone(UTC)


def _timestamp(value: object, name: str) -> str | int:
    if isinstance(value, int) and not isinstance(value, bool):
        return _integer(value, name)
    candidate = _text(value, name, maximum=128)
    _parse_timestamp(candidate, name)
    return candidate


def timestamp_is_current(observed_at: str | int, input_observed_at: str | int) -> bool:
    """Compare epoch or timezone-aware ISO-8601 timestamps without lexicographic guessing."""

    if timestamp_is_future(observed_at) or timestamp_is_future(input_observed_at):
        return False

    if isinstance(observed_at, int) and isinstance(input_observed_at, int):
        return observed_at >= input_observed_at
    if isinstance(observed_at, str) and isinstance(input_observed_at, str):
        try:
            return _parse_timestamp(observed_at, "observed_at") >= _parse_timestamp(
                input_observed_at, "input_observed_at"
            )
        except ValueError:
            return False
    return False


def timestamp_is_future(value: str | int) -> bool:
    """Return whether a validated timestamp is ahead of the current UTC clock."""

    now = datetime.now(UTC)
    if isinstance(value, int):
        return value > int(now.timestamp())
    try:
        return _parse_timestamp(value, "timestamp") > now
    except ValueError:
        return True


def _strings(value: object, name: str, *, maximum: int = 256) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list or tuple")
    result: list[str] = []
    for item in value:
        candidate = _text(item, f"{name} item", maximum=maximum)
        if candidate not in result:
            result.append(candidate)
    return tuple(result)


def _enum[T: Phase6Enum](value: T | str, enum_type: type[T], name: str) -> T:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except ValueError as exc:
        raise ValueError(f"{name} is invalid") from exc


def freeze_json(value: object, *, name: str = "value", _depth: int = 0) -> object:
    """Copy JSON-shaped input into immutable tuples and mapping proxies."""

    if _depth > _MAX_JSON_DEPTH:
        raise ValueError(f"{name} exceeds the JSON nesting bound")
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and "\x00" in value:
            raise ValueError(f"{name} contains NUL")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{name} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or "\x00" in key:
                raise ValueError(f"{name} has an invalid object key")
            frozen[key] = freeze_json(item, name=f"{name}.{key}", _depth=_depth + 1)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item, name=f"{name}[]", _depth=_depth + 1) for item in value)
    raise ValueError(f"{name} must contain JSON-shaped values")


def _public(value: object, *, omit: frozenset[str] = frozenset()) -> object:
    if isinstance(value, Phase6Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _public(getattr(value, item.name))
            for item in fields(value)
            if item.name not in omit
        }
    if isinstance(value, Mapping):
        return {str(key): _public(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_public(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def public_data(value: object) -> object:
    """Return JSON-safe data for a Phase 6 contract or JSON-shaped value."""

    return _public(value)


def canonical_json(value: object) -> str:
    return json.dumps(
        public_data(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest_payload(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _path(value: object, name: str) -> str:
    candidate = _text(value, name, maximum=4_096)
    raw_parts = candidate.replace("\\", "/").split("/")
    if not Path(candidate).is_absolute() or ".." in raw_parts or "" in raw_parts[1:]:
        raise ValueError(f"{name} must be an absolute non-traversing path")
    return str(Path(candidate).resolve(strict=False))


def _confined(path_value: str, workspace_value: str, name: str) -> str:
    path = Path(_path(path_value, name))
    workspace = Path(_path(workspace_value, "workspace"))
    try:
        path.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(f"{name} must remain inside workspace") from exc
    return str(path)


@dataclass(frozen=True, slots=True)
class VerificationBudget:
    max_procedures: int = 32
    max_duration_seconds: int = 120
    max_attempts_per_procedure: int = 1
    max_evidence_records: int = 256
    max_report_bytes: int = 128 * 1024
    max_criteria: int = 256

    def __post_init__(self) -> None:
        _integer(self.max_procedures, "max_procedures", minimum=1, maximum=32)
        _integer(self.max_duration_seconds, "max_duration_seconds", minimum=1, maximum=120)
        _integer(
            self.max_attempts_per_procedure, "max_attempts_per_procedure", minimum=1, maximum=1
        )
        _integer(self.max_evidence_records, "max_evidence_records", minimum=1, maximum=256)
        _integer(self.max_report_bytes, "max_report_bytes", minimum=1, maximum=128 * 1024)
        _integer(self.max_criteria, "max_criteria", minimum=1, maximum=256)

    @property
    def max_procedure_count(self) -> int:
        return self.max_procedures

    @property
    def max_seconds(self) -> int:
        return self.max_duration_seconds

    @property
    def max_attempts(self) -> int:
        return self.max_attempts_per_procedure

    @property
    def max_evidence(self) -> int:
        return self.max_evidence_records

    @property
    def max_output_bytes(self) -> int:
        return self.max_report_bytes


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    path: str
    digest: str = _ZERO_DIGEST
    package_digest: str | None = None
    manifest_digest: str | None = None
    version: str = "1"
    size_bytes: int | None = None
    observed_at: str | int = _DEFAULT_TIMESTAMP
    producer_id: str | None = None
    producer_role: VerificationRole | None = None

    def __post_init__(self) -> None:
        _identity(self.artifact_id, "artifact_id")
        object.__setattr__(self, "path", _path(self.path, "artifact path"))
        _digest(self.digest, "artifact digest")
        for name in ("package_digest", "manifest_digest"):
            value = getattr(self, name)
            if value is not None:
                _digest(value, name)
        _text(self.version, "artifact version", maximum=128)
        if self.size_bytes is not None:
            _integer(self.size_bytes, "size_bytes", maximum=128 * 1024)
        object.__setattr__(
            self, "observed_at", _timestamp(self.observed_at, "artifact observed_at")
        )
        if self.producer_id is not None:
            _identity(self.producer_id, "producer_id")
        if self.producer_role is not None:
            object.__setattr__(
                self,
                "producer_role",
                _enum(self.producer_role, VerificationRole, "producer_role"),
            )

    @property
    def artifact_digest(self) -> str:
        return self.digest


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    evidence_id: str
    path: str | None = None
    digest: str = _ZERO_DIGEST
    artifact_id: str | None = None
    artifact_digest: str | None = None
    package_digest: str | None = None
    observed_at: str | int = _DEFAULT_TIMESTAMP
    freshness: FreshnessStatus = FreshnessStatus.FRESH
    run_id: str | None = None
    task_id: str | None = None

    def __post_init__(self) -> None:
        _identity(self.evidence_id, "evidence_id")
        if self.path is not None:
            object.__setattr__(self, "path", _path(self.path, "evidence path"))
        _digest(self.digest, "evidence digest")
        if self.artifact_id is not None:
            _identity(self.artifact_id, "evidence artifact_id")
        for name in ("artifact_digest", "package_digest"):
            value = getattr(self, name)
            if value is not None:
                _digest(value, name)
        object.__setattr__(
            self, "observed_at", _timestamp(self.observed_at, "evidence observed_at")
        )
        object.__setattr__(
            self,
            "freshness",
            _enum(self.freshness, FreshnessStatus, "evidence freshness"),
        )
        for name in ("run_id", "task_id"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _identity(value, name))
        if (self.run_id is None) != (self.task_id is None):
            raise ValueError("evidence binding fields must be complete")


@dataclass(frozen=True, slots=True)
class Claim:
    criterion_id: str = ""
    text: str = ""
    required: bool = True
    qualitative: bool = False
    claim_id: str | None = None

    def __post_init__(self) -> None:
        selected = self.criterion_id or self.claim_id
        if not selected:
            raise ValueError("claim criterion_id is required")
        identifier = _identity(selected, "criterion_id")
        if self.criterion_id and self.claim_id and self.criterion_id != self.claim_id:
            raise ValueError("claim_id and criterion_id must match")
        object.__setattr__(self, "criterion_id", identifier)
        object.__setattr__(self, "claim_id", identifier)
        _text(self.text, "claim text", maximum=16_384)
        _boolean(self.required, "claim required")
        _boolean(self.qualitative, "claim qualitative")


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    severity: FindingSeverity
    criterion_id: str
    observation: str
    evidence_refs: tuple[str, ...] = ()
    artifact_ref: str | None = None
    impact: str = ""
    recommended_action: str = ""
    confidence: VerificationConfidence = VerificationConfidence.UNKNOWN
    status: str = "OPEN"

    def __post_init__(self) -> None:
        _identity(self.finding_id, "finding_id")
        _identity(self.criterion_id, "finding criterion_id")
        object.__setattr__(
            self, "severity", _enum(self.severity, FindingSeverity, "finding severity")
        )
        _text(self.observation, "finding observation", maximum=16_384)
        object.__setattr__(
            self, "evidence_refs", _strings(self.evidence_refs, "finding evidence_refs")
        )
        if self.artifact_ref is not None:
            _identity(self.artifact_ref, "finding artifact_ref")
        if self.impact:
            _text(self.impact, "finding impact", maximum=8_192)
        if self.recommended_action:
            _text(self.recommended_action, "finding recommended_action", maximum=8_192)
        object.__setattr__(
            self,
            "confidence",
            _enum(self.confidence, VerificationConfidence, "finding confidence"),
        )
        _identity(self.status, "finding status")


@dataclass(frozen=True, slots=True)
class ProcedureSpec:
    procedure_id: str
    criterion_id: str
    description: str
    check: str = "DECLARATIVE"
    required_tool: str | None = None
    deterministic: bool = True
    read_only: bool = True
    max_attempts: int = 1
    parameters: Mapping[str, object] = field(default_factory=dict)
    digest: str = ""

    def __post_init__(self) -> None:
        _identity(self.procedure_id, "procedure_id")
        _identity(self.criterion_id, "procedure criterion_id")
        _text(self.description, "procedure description", maximum=16_384)
        _identity(self.check, "procedure check")
        if self.required_tool is not None:
            _identity(self.required_tool, "required_tool")
        _boolean(self.deterministic, "procedure deterministic")
        _boolean(self.read_only, "procedure read_only")
        _integer(self.max_attempts, "procedure max_attempts", minimum=1, maximum=1)
        parameters = freeze_json(self.parameters, name="procedure parameters")
        if not isinstance(parameters, Mapping):
            raise ValueError("procedure parameters must be a mapping")
        if len(canonical_json(parameters).encode("utf-8")) > _MAX_JSON_BYTES:
            raise ValueError("procedure parameters exceed their byte bound")
        object.__setattr__(self, "parameters", parameters)
        computed = digest_payload(
            {
                item.name: _public(getattr(self, item.name))
                for item in fields(self)
                if item.name != "digest"
            }
        )
        if self.digest and self.digest != computed:
            raise ValueError("procedure digest does not match its content")
        object.__setattr__(self, "digest", computed)

    @property
    def tool(self) -> str | None:
        return self.required_tool


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    criterion_id: str
    digest: str = ""
    artifact_refs: tuple[str, ...] = ()
    artifact_digest: str | None = None
    package_digest: str | None = None
    observed_at: str | int = _DEFAULT_TIMESTAMP
    freshness: FreshnessStatus = FreshnessStatus.FRESH
    kind: EvidenceKind = EvidenceKind.OBSERVATION
    path: str | None = None
    observation: str = ""
    reviewer_id: str | None = None
    reviewer_role: VerificationRole | None = None
    source: str = "deterministic"
    run_id: str | None = None
    task_id: str | None = None
    input_digest: str | None = None

    def __post_init__(self) -> None:
        _identity(self.evidence_id, "evidence_id")
        _identity(self.criterion_id, "evidence criterion_id")
        object.__setattr__(self, "artifact_refs", _strings(self.artifact_refs, "artifact_refs"))
        for name in ("artifact_digest", "package_digest"):
            value = getattr(self, name)
            if value is not None:
                _digest(value, name)
        object.__setattr__(
            self, "observed_at", _timestamp(self.observed_at, "evidence observed_at")
        )
        object.__setattr__(
            self,
            "freshness",
            _enum(self.freshness, FreshnessStatus, "evidence freshness"),
        )
        object.__setattr__(self, "kind", _enum(self.kind, EvidenceKind, "evidence kind"))
        if self.path is not None:
            object.__setattr__(self, "path", _path(self.path, "evidence path"))
        if self.observation:
            _text(self.observation, "evidence observation", maximum=16_384)
        if self.reviewer_id is not None:
            _identity(self.reviewer_id, "reviewer_id")
        if self.reviewer_role is not None:
            object.__setattr__(
                self,
                "reviewer_role",
                _enum(self.reviewer_role, VerificationRole, "reviewer_role"),
            )
        if (self.reviewer_id is None) != (self.reviewer_role is None):
            raise ValueError("reviewer identity and role must be supplied together")
        _text(self.source, "evidence source", maximum=512)
        for name in ("run_id", "task_id"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _identity(value, name))
        if self.input_digest is not None:
            _digest(self.input_digest, "evidence input_digest")
        if (self.run_id is None) != (self.task_id is None):
            raise ValueError("evidence binding fields must be complete")
        computed = evidence_content_digest(self)
        if self.digest:
            _digest(self.digest, "evidence digest")
            if self.digest != computed:
                raise ValueError("evidence digest does not match its content")
        object.__setattr__(self, "digest", computed)

    @property
    def is_current(self) -> bool:
        return self.freshness is FreshnessStatus.FRESH


def evidence_content_digest(evidence: Evidence) -> str:
    """Hash the stable evidence content, excluding only run-local bindings."""

    return digest_payload(
        {
            item.name: _public(getattr(evidence, item.name))
            for item in fields(evidence)
            if item.name not in {"digest", "run_id", "task_id", "input_digest"}
        }
    )


@dataclass(frozen=True, slots=True)
class ProcedureResult:
    procedure_id: str = ""
    criterion_id: str = ""
    status: VerificationStatus = VerificationStatus.NOT_RUN
    executed: bool = False
    evidence: tuple[Evidence, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    attempts: int = 0
    observed_at: str | int = _DEFAULT_TIMESTAMP
    observation: str = ""
    error: str | None = None
    output: Mapping[str, object] = field(default_factory=dict)
    spec: ProcedureSpec | None = None
    run_id: str | None = None
    task_id: str | None = None
    input_digest: str | None = None
    plan_digest: str | None = None
    verifier_id: str | None = None
    digest: str = ""

    def __post_init__(self) -> None:
        spec = self.spec
        if spec is not None and not isinstance(spec, ProcedureSpec):
            raise ValueError("procedure spec is invalid")
        if spec is None:
            if not self.procedure_id or not self.criterion_id:
                raise ValueError("procedure result needs a spec or procedure identity")
            spec = ProcedureSpec(
                procedure_id=self.procedure_id,
                criterion_id=self.criterion_id,
                description="declared procedure result",
            )
            object.__setattr__(self, "spec", spec)
        if self.procedure_id and self.procedure_id != spec.procedure_id:
            raise ValueError("procedure result ID does not match spec")
        if self.criterion_id and self.criterion_id != spec.criterion_id:
            raise ValueError("procedure result criterion does not match spec")
        object.__setattr__(self, "procedure_id", spec.procedure_id)
        object.__setattr__(self, "criterion_id", spec.criterion_id)
        object.__setattr__(
            self, "status", _enum(self.status, VerificationStatus, "procedure status")
        )
        _boolean(self.executed, "procedure executed")
        _integer(self.attempts, "procedure attempts", minimum=0, maximum=spec.max_attempts)
        if self.executed and self.attempts < 1:
            raise ValueError("an executed procedure must record an attempt")
        evidence = tuple(self.evidence)
        if any(not isinstance(item, Evidence) for item in evidence):
            raise ValueError("procedure evidence contains an invalid record")
        if len({item.evidence_id for item in evidence}) != len(evidence):
            raise ValueError("procedure evidence IDs must be unique")
        object.__setattr__(self, "evidence", evidence)
        refs = (
            _strings(self.evidence_refs, "evidence_refs")
            if self.evidence_refs
            else tuple(item.evidence_id for item in evidence)
        )
        if set(refs) != {item.evidence_id for item in evidence}:
            raise ValueError("procedure evidence_refs must match evidence")
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(
            self, "observed_at", _timestamp(self.observed_at, "procedure observed_at")
        )
        if self.observation:
            _text(self.observation, "procedure observation", maximum=16_384)
        if self.error is not None:
            _text(self.error, "procedure error", maximum=4_096)
        output = freeze_json(self.output, name="procedure output")
        if not isinstance(output, Mapping):
            raise ValueError("procedure output must be a mapping")
        if len(canonical_json(output).encode("utf-8")) > _MAX_JSON_BYTES:
            raise ValueError("procedure output exceeds its byte bound")
        object.__setattr__(self, "output", output)
        for name in ("run_id", "task_id", "verifier_id"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _identity(value, name))
        for name in ("input_digest", "plan_digest"):
            value = getattr(self, name)
            if value is not None:
                _digest(value, f"procedure {name}")
        bound_values = (self.run_id, self.task_id, self.input_digest, self.verifier_id)
        if any(value is not None for value in bound_values) and not all(
            value is not None for value in bound_values
        ):
            raise ValueError("procedure binding fields must be complete")
        computed = digest_payload(
            {
                item.name: _public(getattr(self, item.name))
                for item in fields(self)
                if item.name != "digest"
            }
        )
        if self.digest and self.digest != computed:
            raise ValueError("procedure result digest does not match its content")
        object.__setattr__(self, "digest", computed)

    def as_criterion_result(
        self,
        claim: Claim,
        *,
        status: VerificationStatus | str | None = None,
        reason: str = "",
        limitations: Sequence[str] = (),
        confidence: VerificationConfidence | str = VerificationConfidence.HIGH,
    ) -> CriterionResult:
        if self.spec is None:
            raise ValueError("procedure result is missing its spec")
        return CriterionResult(
            criterion_id=self.criterion_id,
            claim=claim,
            procedure=self.spec,
            procedure_result=self,
            evidence=self.evidence,
            status=_enum(status or self.status, VerificationStatus, "criterion status"),
            reason=reason,
            limitations=tuple(limitations),
            confidence=_enum(confidence, VerificationConfidence, "criterion confidence"),
        )


@dataclass(frozen=True, slots=True)
class CriterionResult:
    criterion_id: str
    claim: Claim
    procedure: ProcedureSpec
    procedure_result: ProcedureResult | None = None
    evidence: tuple[Evidence, ...] = ()
    status: VerificationStatus = VerificationStatus.UNKNOWN
    reason: str = ""
    limitations: tuple[str, ...] = ()
    confidence: VerificationConfidence = VerificationConfidence.UNKNOWN
    digest: str = ""

    def __post_init__(self) -> None:
        _identity(self.criterion_id, "criterion result criterion_id")
        if not isinstance(self.claim, Claim) or self.claim.criterion_id != self.criterion_id:
            raise ValueError("criterion result claim is not bound")
        if not isinstance(self.procedure, ProcedureSpec):
            raise ValueError("criterion result procedure is invalid")
        if self.procedure.criterion_id != self.criterion_id:
            raise ValueError("criterion result procedure is not bound")
        procedure_result = self.procedure_result
        if procedure_result is not None and (
            procedure_result.criterion_id != self.criterion_id
            or procedure_result.spec != self.procedure
        ):
            raise ValueError("criterion result procedure result is not bound")
        evidence = tuple(self.evidence)
        if any(not isinstance(item, Evidence) for item in evidence):
            raise ValueError("criterion result evidence is invalid")
        if len({item.evidence_id for item in evidence}) != len(evidence):
            raise ValueError("criterion result evidence IDs must be unique")
        if any(item.criterion_id != self.criterion_id for item in evidence):
            raise ValueError("criterion result evidence is not bound to the criterion")
        if procedure_result is not None and not evidence:
            evidence = procedure_result.evidence
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(
            self, "status", _enum(self.status, VerificationStatus, "criterion status")
        )
        if self.reason:
            _text(self.reason, "criterion reason", maximum=16_384)
        object.__setattr__(
            self, "limitations", _strings(self.limitations, "criterion limitations", maximum=4_096)
        )
        object.__setattr__(
            self,
            "confidence",
            _enum(self.confidence, VerificationConfidence, "criterion confidence"),
        )
        if self.status is VerificationStatus.PASS:
            if procedure_result is None or not procedure_result.executed:
                raise ValueError("PASS needs an executed procedure")
            if procedure_result.status is not VerificationStatus.PASS:
                raise ValueError("PASS needs a passing procedure result")
            if not evidence or any(not item.is_current for item in evidence):
                raise ValueError("PASS needs current evidence")
        computed = digest_payload(
            {
                item.name: _public(getattr(self, item.name))
                for item in fields(self)
                if item.name != "digest"
            }
        )
        if self.digest and self.digest != computed:
            raise ValueError("criterion result digest does not match its content")
        object.__setattr__(self, "digest", computed)

    @property
    def expected(self) -> str:
        """Return the immutable expected claim text for report consumers."""

        return self.claim.text

    @property
    def observed(self) -> str:
        """Return the bounded observation that led to this criterion status."""

        if self.procedure_result is None:
            return "not observed"
        return self.procedure_result.observation or self.procedure_result.error or "no observation"

    @property
    def procedure_id(self) -> str:
        return self.procedure.procedure_id

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        return tuple(item.evidence_id for item in self.evidence)


def _criteria(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("required_criteria must be a non-empty list or tuple")
    result: list[str] = []
    for item in value:
        if isinstance(item, Claim):
            identifier = item.criterion_id
        else:
            identifier = _identity(item, "required criterion")
        if identifier in result:
            raise ValueError("required criteria must be unique")
        result.append(identifier)
    return tuple(result)


def _output_status(results: Sequence[CriterionResult]) -> VerificationStatus:
    if not results:
        return VerificationStatus.NOT_RUN
    statuses = {item.status for item in results}
    if VerificationStatus.STALE in statuses:
        return VerificationStatus.STALE
    if VerificationStatus.BLOCKED in statuses:
        return VerificationStatus.BLOCKED
    if VerificationStatus.FAIL in statuses:
        return VerificationStatus.FAIL
    if VerificationStatus.PARTIAL in statuses:
        return VerificationStatus.PARTIAL
    if VerificationStatus.UNKNOWN in statuses:
        return VerificationStatus.UNKNOWN
    if VerificationStatus.NOT_RUN in statuses:
        return VerificationStatus.NOT_RUN
    return VerificationStatus.PASS


def _finding_for_result(result: CriterionResult) -> Finding:
    severity = {
        VerificationStatus.FAIL: FindingSeverity.HIGH,
        VerificationStatus.BLOCKED: FindingSeverity.HIGH,
        VerificationStatus.STALE: FindingSeverity.HIGH,
        VerificationStatus.PARTIAL: FindingSeverity.MEDIUM,
        VerificationStatus.UNKNOWN: FindingSeverity.MEDIUM,
        VerificationStatus.NOT_RUN: FindingSeverity.MEDIUM,
    }.get(result.status, FindingSeverity.INFO)
    return Finding(
        finding_id=f"F-{result.criterion_id}",
        severity=severity,
        criterion_id=result.criterion_id,
        observation=result.reason or result.status.value,
        evidence_refs=result.evidence_refs,
        impact=f"Criterion is {result.status.value.lower()}.",
        recommended_action=(
            "Refresh evidence and rerun."
            if result.status in {VerificationStatus.STALE, VerificationStatus.UNKNOWN}
            else "Resolve the criterion condition and rerun."
        ),
        confidence=result.confidence,
    )


def _output_freshness(
    verification_input: VerificationInput | None,
    results: Sequence[CriterionResult],
) -> FreshnessStatus:
    if verification_input is None:
        return FreshnessStatus.UNKNOWN
    if verification_input.freshness is FreshnessStatus.STALE:
        return FreshnessStatus.STALE
    if verification_input.freshness is FreshnessStatus.UNKNOWN:
        return FreshnessStatus.UNKNOWN
    evidence = tuple(item for result in results for item in result.evidence)
    if any(item.freshness is FreshnessStatus.STALE for item in evidence):
        return FreshnessStatus.STALE
    if any(item.freshness is FreshnessStatus.UNKNOWN for item in evidence):
        return FreshnessStatus.UNKNOWN
    references = verification_input.evidence_refs
    if any(item.freshness is FreshnessStatus.STALE for item in references):
        return FreshnessStatus.STALE
    if any(item.freshness is FreshnessStatus.UNKNOWN for item in references):
        return FreshnessStatus.UNKNOWN
    if any(
        item.procedure_result is not None
        and not timestamp_is_current(
            item.procedure_result.observed_at,
            verification_input.observed_at,
        )
        for item in results
    ):
        return FreshnessStatus.STALE
    if any(
        not timestamp_is_current(item.observed_at, verification_input.observed_at)
        for item in references
    ):
        return FreshnessStatus.STALE
    if not evidence and any(item.status is not VerificationStatus.PASS for item in results):
        return FreshnessStatus.UNKNOWN
    return FreshnessStatus.FRESH


def _artifact_digest_verified(
    verification_input: VerificationInput | None,
    results: Sequence[CriterionResult],
) -> bool:
    if verification_input is None or not verification_input.artifact_refs or not results:
        return False
    artifacts = {item.artifact_id: item.digest for item in verification_input.artifact_refs}
    for result in results:
        if result.status is not VerificationStatus.PASS or not result.evidence:
            return False
        for evidence in result.evidence:
            if not evidence.artifact_refs or evidence.artifact_digest is None:
                return False
            if any(
                artifacts.get(artifact_id) != evidence.artifact_digest
                for artifact_id in evidence.artifact_refs
            ):
                return False
    return True


def _recommended_action(status: VerificationStatus) -> str:
    return {
        VerificationStatus.PASS: "DELIVER_OR_PROCEED",
        VerificationStatus.FAIL: "RESOLVE_FINDINGS_AND_RERUN",
        VerificationStatus.PARTIAL: "DISCLOSE_LIMITATIONS_AND_COMPLETE_OPTIONAL_COVERAGE",
        VerificationStatus.BLOCKED: "RESOLVE_BLOCKERS_AND_RERUN",
        VerificationStatus.STALE: "REFRESH_ARTIFACT_AND_EVIDENCE_AND_RERUN",
        VerificationStatus.NOT_RUN: "RUN_DECLARED_PROCEDURES",
        VerificationStatus.UNKNOWN: "OBTAIN_MISSING_EVIDENCE_AND_RERUN",
    }[status]


@dataclass(frozen=True, slots=True)
class VerificationInput:
    run_id: str
    task_id: str
    capability_id: str
    package_digest: str
    manifest_digest: str
    workspace: str
    required_criteria: tuple[str, ...]
    deferred_criteria: tuple[str, ...] = ()
    artifact_refs: tuple[ArtifactRef, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    profile: VerificationProfile = VerificationProfile.FOCUSED
    role: VerificationRole = VerificationRole.VERIFIER
    allowed_tools: tuple[str, ...] = ()
    read_only_policy: ReadOnlyPolicy = ReadOnlyPolicy.READ_ONLY
    read_only: bool = True
    observed_at: str | int = _DEFAULT_TIMESTAMP
    freshness: FreshnessStatus = FreshnessStatus.FRESH
    budgets: VerificationBudget = field(default_factory=VerificationBudget)
    claims: tuple[Claim, ...] = ()
    digest: str = ""
    verification_id: str | None = None
    acceptance_criteria_ref: str | None = None
    builder_invocation_ref: str | None = None
    builder_host_invocation_ref: str | None = None
    capability_provenance: str | None = None
    scope: str = "PROJECT"
    authority: str = "VERIFIER"
    known_limitations: tuple[str, ...] = ()
    context_budget: int | None = None

    def __post_init__(self) -> None:
        for name in ("run_id", "task_id", "capability_id"):
            _identity(getattr(self, name), name)
        _digest(self.package_digest, "package_digest")
        _digest(self.manifest_digest, "manifest_digest")
        object.__setattr__(self, "workspace", _path(self.workspace, "workspace"))
        if not isinstance(self.budgets, VerificationBudget):
            raise ValueError("budgets are invalid")
        raw_required_criteria: object = self.required_criteria
        criteria = _criteria(raw_required_criteria)
        if len(criteria) > self.budgets.max_criteria:
            raise ValueError("required criteria exceed the budget")
        object.__setattr__(self, "required_criteria", criteria)
        deferred = _strings(self.deferred_criteria, "deferred_criteria")
        if set(criteria).intersection(deferred):
            raise ValueError("deferred criteria cannot be required criteria")
        object.__setattr__(self, "deferred_criteria", deferred)
        if not isinstance(self.claims, (list, tuple)):
            raise ValueError("claims must be a list or tuple")
        supplied_claims = tuple(self.claims)
        if any(not isinstance(item, Claim) for item in supplied_claims):
            raise ValueError("claims contain an invalid record")
        claim_map: dict[str, Claim] = {}
        for item in supplied_claims:
            if item.criterion_id in claim_map and claim_map[item.criterion_id] != item:
                raise ValueError("claims must not diverge for one criterion")
            claim_map[item.criterion_id] = item
        if not isinstance(raw_required_criteria, (list, tuple)):
            raise ValueError("required criteria must be a list or tuple")
        for raw_criterion in raw_required_criteria:
            if isinstance(raw_criterion, Claim):
                if (
                    raw_criterion.criterion_id in claim_map
                    and claim_map[raw_criterion.criterion_id] != raw_criterion
                ):
                    raise ValueError("claims must not diverge for one criterion")
                claim_map[raw_criterion.criterion_id] = raw_criterion
        for criterion_id in self.required_criteria:
            if criterion_id not in claim_map:
                claim_map[criterion_id] = Claim(criterion_id=criterion_id, text=criterion_id)
        if any(item not in criteria for item in claim_map):
            raise ValueError("claims must refer to required criteria")
        object.__setattr__(
            self,
            "claims",
            tuple(claim_map[item] for item in self.required_criteria),
        )
        artifacts = tuple(self.artifact_refs)
        evidence = tuple(self.evidence_refs)
        if any(not isinstance(item, ArtifactRef) for item in artifacts):
            raise ValueError("artifact_refs contain an invalid record")
        if any(not isinstance(item, EvidenceRef) for item in evidence):
            raise ValueError("evidence_refs contain an invalid record")
        if len(evidence) > self.budgets.max_evidence_records:
            raise ValueError("evidence_refs exceed the budget")
        if len({item.artifact_id for item in artifacts}) != len(artifacts):
            raise ValueError("artifact_refs must be unique")
        if len({item.evidence_id for item in evidence}) != len(evidence):
            raise ValueError("evidence_refs must be unique")
        for artifact_ref in artifacts:
            _confined(artifact_ref.path, self.workspace, "artifact path")
            if artifact_ref.producer_id == self.capability_id:
                raise ValueError("verifier cannot be the artifact producer")
            if artifact_ref.producer_role is VerificationRole.VERIFIER:
                raise ValueError("a verifier-produced artifact cannot be self-verified")
            if (
                artifact_ref.package_digest is not None
                and artifact_ref.package_digest != self.package_digest
            ):
                raise ValueError("artifact package digest is not bound")
            if (
                artifact_ref.manifest_digest is not None
                and artifact_ref.manifest_digest != self.manifest_digest
            ):
                raise ValueError("artifact manifest digest is not bound")
        artifact_ids = {item.artifact_id for item in artifacts}
        for evidence_ref in evidence:
            if evidence_ref.path is not None:
                _confined(evidence_ref.path, self.workspace, "evidence path")
            if evidence_ref.run_id is not None and evidence_ref.run_id != self.run_id:
                raise ValueError("evidence run_id is not bound")
            if evidence_ref.task_id is not None and evidence_ref.task_id != self.task_id:
                raise ValueError("evidence task_id is not bound")
            if (
                evidence_ref.artifact_id is not None
                and evidence_ref.artifact_id not in artifact_ids
            ):
                raise ValueError("evidence points to an unknown artifact")
            if (
                evidence_ref.package_digest is not None
                and evidence_ref.package_digest != self.package_digest
            ):
                raise ValueError("evidence package digest is not bound")
            if evidence_ref.artifact_digest is not None and evidence_ref.artifact_id is not None:
                artifact_ref = next(
                    ref for ref in artifacts if ref.artifact_id == evidence_ref.artifact_id
                )
                if evidence_ref.artifact_digest != artifact_ref.digest:
                    raise ValueError("evidence artifact digest is not bound")
        object.__setattr__(self, "artifact_refs", artifacts)
        object.__setattr__(self, "evidence_refs", evidence)
        object.__setattr__(self, "profile", _enum(self.profile, VerificationProfile, "profile"))
        object.__setattr__(self, "role", _enum(self.role, VerificationRole, "role"))
        if self.role is not VerificationRole.VERIFIER:
            raise ValueError("verification input role must be VERIFIER")
        object.__setattr__(self, "allowed_tools", _strings(self.allowed_tools, "allowed_tools"))
        object.__setattr__(
            self,
            "read_only_policy",
            _enum(self.read_only_policy, ReadOnlyPolicy, "read_only_policy"),
        )
        _boolean(self.read_only, "read_only")
        object.__setattr__(self, "observed_at", _timestamp(self.observed_at, "observed_at"))
        object.__setattr__(self, "freshness", _enum(self.freshness, FreshnessStatus, "freshness"))
        if not self.read_only or self.read_only_policy not in {
            ReadOnlyPolicy.READ_ONLY,
            ReadOnlyPolicy.MUTATION_DENIED,
        }:
            raise ValueError("verification input must be read-only")
        verification_id = self.verification_id or f"VERIFICATION-{self.run_id}"
        object.__setattr__(self, "verification_id", _identity(verification_id, "verification_id"))
        for name in (
            "acceptance_criteria_ref",
            "builder_invocation_ref",
            "builder_host_invocation_ref",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _identity(value, name))
        if self.capability_provenance is not None:
            object.__setattr__(
                self,
                "capability_provenance",
                _text(self.capability_provenance, "capability_provenance", maximum=4_096),
            )
        object.__setattr__(self, "scope", _identity(self.scope, "scope"))
        object.__setattr__(self, "authority", _identity(self.authority, "authority"))
        if self.scope != "PROJECT":
            raise ValueError("verification scope must be PROJECT")
        if self.authority != "VERIFIER":
            raise ValueError("verification authority must be VERIFIER")
        object.__setattr__(
            self,
            "known_limitations",
            _strings(self.known_limitations, "known_limitations", maximum=4_096),
        )
        if self.context_budget is not None:
            _integer(self.context_budget, "context_budget", minimum=1, maximum=128 * 1024)
        computed = digest_payload(
            {
                item.name: _public(getattr(self, item.name))
                for item in fields(self)
                if item.name != "digest"
            }
        )
        if self.digest and self.digest != computed:
            raise ValueError("verification input digest does not match its content")
        object.__setattr__(self, "digest", computed)

    @property
    def criteria(self) -> tuple[str, ...]:
        return self.required_criteria

    @property
    def input_digest(self) -> str:
        return self.digest


def verification_input_content_digest(verification_input: VerificationInput) -> str:
    """Recompute the immutable input digest for a trust-boundary recheck."""

    return digest_payload(
        {
            item.name: _public(getattr(verification_input, item.name))
            for item in fields(verification_input)
            if item.name != "digest"
        }
    )


@dataclass(frozen=True, slots=True)
class VerificationOutput:
    input_digest: str
    run_id: str
    task_id: str
    capability_id: str
    package_digest: str
    manifest_digest: str
    criterion_results: tuple[CriterionResult, ...]
    passed: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    not_run: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    stop_reason: StopCondition | None = None
    confidence: VerificationConfidence = VerificationConfidence.UNKNOWN
    artifact_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    profile: VerificationProfile = VerificationProfile.FOCUSED
    role: VerificationRole = VerificationRole.VERIFIER
    reviewer_id: str | None = None
    reviewer_role: VerificationRole | None = None
    input: VerificationInput | None = None
    report_digest: str = ""
    status: VerificationStatus = VerificationStatus.UNKNOWN
    claims: tuple[Claim, ...] = ()
    evidence_used: tuple[str, ...] = ()
    procedures_run: tuple[str, ...] = ()
    procedures_not_run: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    findings: tuple[Finding, ...] = ()
    artifact_digest_verified: bool = False
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    recommended_next_action: str = ""
    deferred_criteria: tuple[str, ...] = ()
    deferred_procedures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _digest(self.input_digest, "input_digest")
        for name in ("run_id", "task_id", "capability_id"):
            _identity(getattr(self, name), name)
        _digest(self.package_digest, "package_digest")
        _digest(self.manifest_digest, "manifest_digest")
        results = tuple(self.criterion_results)
        if any(not isinstance(item, CriterionResult) for item in results):
            raise ValueError("criterion_results contain an invalid record")
        ids = tuple(item.criterion_id for item in results)
        if len(set(ids)) != len(ids):
            raise ValueError("criterion results contain duplicate criteria")
        if self.input is not None:
            if self.input_digest != self.input.digest:
                raise ValueError("output input digest is not bound")
            identity_expected = {
                "run_id": self.input.run_id,
                "task_id": self.input.task_id,
                "capability_id": self.input.capability_id,
                "package_digest": self.input.package_digest,
                "manifest_digest": self.input.manifest_digest,
            }
            if any(getattr(self, name) != value for name, value in identity_expected.items()):
                raise ValueError("output identity is not bound to input")
            if set(ids) != set(self.input.required_criteria):
                raise ValueError("output criteria do not exactly match input criteria")
            expected_deferred = self.input.deferred_criteria
            supplied_deferred = _strings(self.deferred_criteria, "deferred_criteria")
            if supplied_deferred and supplied_deferred != expected_deferred:
                raise ValueError("deferred criteria are not bound to input")
            object.__setattr__(self, "deferred_criteria", expected_deferred)
            expected_artifacts = tuple(item.artifact_id for item in self.input.artifact_refs)
            expected_evidence = tuple(item.evidence_id for item in self.input.evidence_refs)
            if self.artifact_refs and self.artifact_refs != expected_artifacts:
                raise ValueError("output artifact references are not bound to input")
            if self.evidence_refs and self.evidence_refs != expected_evidence:
                raise ValueError("output evidence references are not bound to input")
            if self.profile is not self.input.profile:
                raise ValueError("output profile is not bound to input")
            if self.role is not self.input.role:
                raise ValueError("output role is not bound to input")
            object.__setattr__(
                self, "artifact_refs", tuple(item.artifact_id for item in self.input.artifact_refs)
            )
            object.__setattr__(
                self, "evidence_refs", tuple(item.evidence_id for item in self.input.evidence_refs)
            )
            object.__setattr__(self, "profile", self.input.profile)
            object.__setattr__(self, "role", self.input.role)
        object.__setattr__(self, "criterion_results", results)
        object.__setattr__(self, "artifact_refs", _strings(self.artifact_refs, "artifact_refs"))
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs, "evidence_refs"))
        object.__setattr__(self, "profile", _enum(self.profile, VerificationProfile, "profile"))
        object.__setattr__(self, "role", _enum(self.role, VerificationRole, "role"))
        if self.role is not VerificationRole.VERIFIER:
            raise ValueError("verification output role must be VERIFIER")
        if self.input is not None:
            artifact_map = {item.artifact_id: item for item in self.input.artifact_refs}
            evidence_map = {item.evidence_id: item for item in self.input.evidence_refs}
            for result in results:
                for evidence in result.evidence:
                    if evidence.evidence_id not in evidence_map:
                        if result.status is VerificationStatus.PASS:
                            raise ValueError("PASS evidence is missing from input evidence refs")
                        raise ValueError("criterion evidence is not bound to input evidence")
                    if evidence.digest != evidence_map[evidence.evidence_id].digest:
                        raise ValueError("criterion evidence digest is not bound to input")
                    if (
                        evidence.package_digest is not None
                        and evidence.package_digest != self.package_digest
                    ):
                        raise ValueError("criterion evidence package digest is not bound")
                    for artifact_id in evidence.artifact_refs:
                        artifact = artifact_map.get(artifact_id)
                        if artifact is None:
                            raise ValueError("criterion evidence points to an unknown artifact")
                        if (
                            evidence.artifact_digest is not None
                            and evidence.artifact_digest != artifact.digest
                        ):
                            raise ValueError("criterion evidence artifact digest is not bound")
                    if result.status is VerificationStatus.PASS and (
                        not evidence.is_current
                        or not timestamp_is_current(evidence.observed_at, self.input.observed_at)
                        or evidence_map[evidence.evidence_id].freshness is not FreshnessStatus.FRESH
                        or not timestamp_is_current(
                            evidence_map[evidence.evidence_id].observed_at,
                            self.input.observed_at,
                        )
                    ):
                        raise ValueError("PASS evidence is stale")
                if result.status is VerificationStatus.PASS and not evidence_map:
                    raise ValueError("PASS requires declared evidence")
                if (
                    self.input.profile is VerificationProfile.VISUAL
                    and result.claim.qualitative
                    and result.status is VerificationStatus.PASS
                ):
                    has_render = any(
                        item.kind is EvidenceKind.RENDER
                        and item.is_current
                        and timestamp_is_current(item.observed_at, self.input.observed_at)
                        for item in result.evidence
                    )
                    has_reviewer = (
                        self.reviewer_role is VerificationRole.REVIEWER
                        and self.reviewer_id is not None
                        and any(
                            item.reviewer_role is VerificationRole.REVIEWER
                            and item.reviewer_id == self.reviewer_id
                            for item in result.evidence
                        )
                    )
                    if not has_render or not has_reviewer:
                        raise ValueError(
                            "qualitative visual PASS needs independent current render evidence"
                        )
        expected_passed = tuple(
            item.criterion_id for item in results if item.status is VerificationStatus.PASS
        )
        expected_failed = tuple(
            item.criterion_id for item in results if item.status is VerificationStatus.FAIL
        )
        expected_not_run = tuple(
            item.criterion_id for item in results if item.status is VerificationStatus.NOT_RUN
        )
        expected_unknown = tuple(
            item.criterion_id for item in results if item.status is VerificationStatus.UNKNOWN
        )
        for name, status_expected in (
            ("passed", expected_passed),
            ("failed", expected_failed),
            ("not_run", expected_not_run),
            ("unknown", expected_unknown),
        ):
            supplied = _strings(getattr(self, name), name)
            if supplied and supplied != status_expected:
                raise ValueError(f"{name} does not match criterion statuses")
            object.__setattr__(self, name, status_expected)
        derived_status = _output_status(results)
        stop_reason = (
            _enum(self.stop_reason, StopCondition, "stop_reason")
            if self.stop_reason is not None
            else None
        )
        if stop_reason in {
            StopCondition.BUDGET_EXHAUSTED,
            StopCondition.MISSING_REQUIRED_TOOL,
            StopCondition.MISSING_REQUIRED_ARTIFACT,
            StopCondition.NO_PROGRESS,
            StopCondition.REPEATED_PROCEDURE_FAILURE,
            StopCondition.HUMAN_OVERRIDE,
        } and derived_status in {
            VerificationStatus.PASS,
            VerificationStatus.NOT_RUN,
            VerificationStatus.UNKNOWN,
        }:
            derived_status = VerificationStatus.BLOCKED
        if derived_status is VerificationStatus.PASS and self.input is None:
            raise ValueError("PASS output requires a bound verification input")
        supplied_status = _enum(self.status, VerificationStatus, "status")
        if (
            supplied_status is not VerificationStatus.UNKNOWN
            and supplied_status is not derived_status
        ):
            raise ValueError("status does not match criterion statuses")
        object.__setattr__(self, "status", derived_status)
        if self.input is not None:
            object.__setattr__(self, "claims", tuple(item.claim for item in results))
        else:
            claims = tuple(self.claims)
            if any(not isinstance(item, Claim) for item in claims):
                raise ValueError("claims contain an invalid record")
            object.__setattr__(self, "claims", claims)
        derived_evidence = tuple(
            evidence_id for result in results for evidence_id in result.evidence_refs
        )
        derived_evidence = tuple(dict.fromkeys(derived_evidence))
        supplied_evidence = _strings(self.evidence_used, "evidence_used")
        if supplied_evidence and supplied_evidence != derived_evidence:
            raise ValueError("evidence_used does not match criterion evidence")
        object.__setattr__(self, "evidence_used", derived_evidence)
        derived_run = tuple(
            result.procedure_id
            for result in results
            if result.procedure_result is not None and result.procedure_result.executed
        )
        derived_not_run = tuple(
            result.procedure_id
            for result in results
            if result.procedure_result is None
            or not result.procedure_result.executed
            or result.status is VerificationStatus.NOT_RUN
        )
        derived_not_run = derived_not_run + tuple(
            f"NOT-RUN-{criterion_id}" for criterion_id in self.deferred_criteria
        )
        for name, derived in (
            ("procedures_run", derived_run),
            ("procedures_not_run", derived_not_run),
        ):
            supplied = _strings(getattr(self, name), name)
            if supplied and supplied != derived:
                raise ValueError(f"{name} does not match criterion procedures")
            object.__setattr__(self, name, derived)
        deferred_procedures = tuple(
            f"NOT-RUN-{criterion_id}" for criterion_id in self.deferred_criteria
        )
        supplied_deferred_procedures = _strings(self.deferred_procedures, "deferred_procedures")
        if supplied_deferred_procedures and supplied_deferred_procedures != deferred_procedures:
            raise ValueError("deferred procedures do not match deferred criteria")
        object.__setattr__(self, "deferred_procedures", deferred_procedures)
        supplied_failures = _strings(self.failures, "failures")
        if supplied_failures and supplied_failures != expected_failed:
            raise ValueError("failures does not match failed criteria")
        object.__setattr__(self, "failures", expected_failed)
        supplied_unknowns = _strings(self.unknowns, "unknowns")
        if supplied_unknowns and supplied_unknowns != expected_unknown:
            raise ValueError("unknowns does not match unknown criteria")
        object.__setattr__(self, "unknowns", expected_unknown)
        findings = tuple(self.findings)
        if any(not isinstance(item, Finding) for item in findings):
            raise ValueError("findings contain an invalid record")
        if not findings:
            findings = tuple(
                _finding_for_result(item)
                for item in results
                if item.status is not VerificationStatus.PASS
            )
        object.__setattr__(self, "findings", findings)
        freshness = _output_freshness(self.input, results)
        supplied_freshness = _enum(self.freshness_status, FreshnessStatus, "freshness_status")
        if (
            supplied_freshness is not FreshnessStatus.UNKNOWN
            and supplied_freshness is not freshness
        ):
            raise ValueError("freshness_status does not match criterion evidence")
        object.__setattr__(self, "freshness_status", freshness)
        artifact_verified = _artifact_digest_verified(self.input, results)
        _boolean(self.artifact_digest_verified, "artifact_digest_verified")
        if self.artifact_digest_verified and not artifact_verified:
            raise ValueError("artifact_digest_verified does not match criterion evidence")
        object.__setattr__(self, "artifact_digest_verified", artifact_verified)
        action = self.recommended_next_action or _recommended_action(self.status)
        if self.recommended_next_action and self.recommended_next_action != _recommended_action(
            self.status
        ):
            raise ValueError("recommended_next_action does not match status")
        object.__setattr__(
            self, "recommended_next_action", _text(action, "recommended_next_action")
        )
        limitations = _strings(self.limitations, "limitations", maximum=4_096)
        derived_limitations = tuple(
            f"{item.criterion_id}: {item.reason}"
            for item in results
            if item.status is VerificationStatus.PARTIAL and item.reason
        )
        if not limitations:
            limitations = derived_limitations
        object.__setattr__(self, "limitations", limitations)
        blockers = _strings(self.blockers, "blockers", maximum=4_096)
        derived_blockers = tuple(
            f"{item.criterion_id}: {item.reason or item.status.value}"
            for item in results
            if item.status in {VerificationStatus.BLOCKED, VerificationStatus.STALE}
        )
        if stop_reason is StopCondition.BUDGET_EXHAUSTED:
            derived_blockers = derived_blockers + ("verification budget exhausted",)
        if not blockers:
            blockers = derived_blockers
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "stop_reason", stop_reason)
        object.__setattr__(
            self,
            "confidence",
            _enum(self.confidence, VerificationConfidence, "confidence"),
        )
        if self.reviewer_id is not None:
            _identity(self.reviewer_id, "reviewer_id")
        if self.reviewer_role is not None:
            reviewer_role = _enum(self.reviewer_role, VerificationRole, "reviewer_role")
            if reviewer_role is not VerificationRole.REVIEWER or self.reviewer_id is None:
                raise ValueError("reviewer must be an identified REVIEWER")
            if self.reviewer_id == self.capability_id:
                raise ValueError("verifier cannot review its own output")
            if self.input is not None and self.reviewer_id in {
                item.producer_id
                for item in self.input.artifact_refs
                if item.producer_id is not None
            }:
                raise ValueError("reviewer cannot be the artifact producer")
            object.__setattr__(self, "reviewer_role", reviewer_role)
        serialized = canonical_json(
            {
                item.name: getattr(self, item.name)
                for item in fields(self)
                if item.name not in {"report_digest", "input"}
            }
        ).encode("utf-8")
        if self.input is not None and len(serialized) > self.input.budgets.max_report_bytes:
            raise ValueError("verification output exceeds the report byte budget")
        computed = digest_payload(
            {
                item.name: _public(getattr(self, item.name))
                for item in fields(self)
                if item.name not in {"report_digest", "input"}
            }
        )
        if self.report_digest and self.report_digest != computed:
            raise ValueError("report digest does not match its content")
        object.__setattr__(self, "report_digest", computed)

    @classmethod
    def from_input(
        cls,
        verification_input: VerificationInput,
        criterion_results: Sequence[CriterionResult],
        **kwargs: Any,
    ) -> VerificationOutput:
        return cls(
            input_digest=verification_input.digest,
            run_id=verification_input.run_id,
            task_id=verification_input.task_id,
            capability_id=verification_input.capability_id,
            package_digest=verification_input.package_digest,
            manifest_digest=verification_input.manifest_digest,
            criterion_results=tuple(criterion_results),
            input=verification_input,
            profile=verification_input.profile,
            role=verification_input.role,
            **kwargs,
        )

    @property
    def results(self) -> tuple[CriterionResult, ...]:
        return self.criterion_results

    @property
    def digest(self) -> str:
        return self.report_digest


# Compatibility names for callers that use the shorter contract vocabulary.
Status = VerificationStatus
Profile = VerificationProfile
Role = VerificationRole
Budget = VerificationBudget
ArtifactReference = ArtifactRef
EvidenceReference = EvidenceRef
Procedure = ProcedureSpec
EvidenceRecord = Evidence
CriterionVerification = CriterionResult
