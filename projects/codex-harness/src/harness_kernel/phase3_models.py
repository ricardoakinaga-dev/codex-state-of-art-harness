"""Immutable records for the bounded Phase 3 host boundary.

The records in this module describe host data and declarative package
content.  They do not represent executable providers, scripts, MCP servers or
loaded runtime objects.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class P3Enum(StrEnum):
    def __str__(self) -> str:
        return self.value


class ObservationStatus(P3Enum):
    OBSERVED = "OBSERVED"
    OFFICIAL_DOCUMENTED = "OFFICIAL_DOCUMENTED"
    INFERRED = "INFERRED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class RootScope(P3Enum):
    PROJECT = "PROJECT"
    WORKSPACE = "WORKSPACE"
    GLOBAL = "GLOBAL"
    SYSTEM = "SYSTEM"
    VENDORED = "VENDORED"
    EXTERNAL = "EXTERNAL"
    UNKNOWN = "UNKNOWN"


class ParseStatus(P3Enum):
    VALID = "VALID"
    LEGACY = "LEGACY"
    INVALID = "INVALID"


class CapabilityKind(P3Enum):
    NATIVE = "NATIVE"
    SYNTHESIZED = "SYNTHESIZED"
    LEGACY = "LEGACY"
    INVALID = "INVALID"


class CapabilityLifecycle(P3Enum):
    DISCOVERED = "DISCOVERED"
    INSPECTED = "INSPECTED"
    SELECTED = "SELECTED"
    LOAD_PLANNED = "LOAD_PLANNED"
    CONTEXT_PREPARED = "CONTEXT_PREPARED"
    HOST_LOADED = "HOST_LOADED"
    EXECUTED = "EXECUTED"
    BLOCKED = "BLOCKED"
    INCOMPATIBLE = "INCOMPATIBLE"
    REJECTED = "REJECTED"
    STALE = "STALE"
    AMBIGUOUS = "AMBIGUOUS"


class DisclosureLevel(P3Enum):
    IDENTITY = "L0_IDENTITY"
    ROUTING_METADATA = "L1_ROUTING_METADATA"
    INSTRUCTION_KERNEL = "L2_INSTRUCTION_KERNEL"
    SELECTED_REFERENCES = "L3_SELECTED_REFERENCES"
    APPROVED_PACKAGE = "L4_APPROVED_DECLARATIVE_PACKAGE"


class CompatibilityStatus(P3Enum):
    COMPATIBLE = "COMPATIBLE"
    PARTIAL = "PARTIAL"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


class TrustLevel(P3Enum):
    PROJECT_TRUSTED = "PROJECT_TRUSTED"
    VERIFIED_LOCAL = "VERIFIED_LOCAL"
    OFFICIAL = "OFFICIAL"
    KNOWN_UPSTREAM = "KNOWN_UPSTREAM"
    THIRD_PARTY = "THIRD_PARTY"
    UNVERIFIED = "UNVERIFIED"
    REJECTED = "REJECTED"


class ResolutionStatus(P3Enum):
    RESOLVED = "RESOLVED"
    MISSING = "MISSING"
    INCOMPATIBLE = "INCOMPATIBLE"
    BLOCKED = "BLOCKED"
    AMBIGUOUS = "AMBIGUOUS"
    CYCLE = "CYCLE"


class DependencyStatus(P3Enum):
    RESOLVED = "RESOLVED"
    MISSING = "MISSING"
    INCOMPATIBLE = "INCOMPATIBLE"
    BLOCKED = "BLOCKED"
    AMBIGUOUS = "AMBIGUOUS"
    CYCLE = "CYCLE"


class Phase3EventType(P3Enum):
    DISCOVERED = "CAPABILITY_DISCOVERED"
    SELECTED = "CAPABILITY_SELECTED"
    LOAD_PLANNED = "CAPABILITY_LOAD_PLANNED"
    CONTEXT_PREPARED = "CAPABILITY_CONTEXT_PREPARED"
    HOST_LOADED = "CAPABILITY_HOST_LOADED"
    EXECUTED = "CAPABILITY_EXECUTED"
    BLOCKED = "CAPABILITY_BLOCKED"
    REJECTED = "CAPABILITY_REJECTED"


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")


def _as_tuple(values: Sequence[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or "\x00" in value:
            raise ValueError("Phase 3 string values must be NUL-free strings")
        if value not in result:
            result.append(value)
    return tuple(result)


def _map_proxy(values: Mapping[str, str] | None) -> Mapping[str, str]:
    if values is None:
        return MappingProxyType({})
    clean: dict[str, str] = {}
    for key, value in values.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("Phase 3 mappings must contain strings")
        clean[key] = value
    return MappingProxyType(clean)


def _freeze_value(value: Any) -> Any:
    """Recursively freeze JSON-shaped values carried by immutable records."""

    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze_value(item) for item in value), key=repr))
    return value


@dataclass(frozen=True, slots=True)
class Phase3Limits:
    max_roots: int = 32
    max_capabilities: int = 512
    max_files_per_capability: int = 256
    max_total_files: int = 4096
    max_skill_bytes: int = 64 * 1024
    max_manifest_bytes: int = 128 * 1024
    max_reference_files: int = 64
    max_reference_bytes: int = 256 * 1024
    max_total_bytes: int = 16 * 1024 * 1024
    max_depth: int = 4

    def __post_init__(self) -> None:
        for name in (
            "max_roots",
            "max_capabilities",
            "max_files_per_capability",
            "max_total_files",
            "max_skill_bytes",
            "max_manifest_bytes",
            "max_reference_files",
            "max_reference_bytes",
            "max_total_bytes",
            "max_depth",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class CapabilityRoot:
    root_id: str
    scope: RootScope | str
    path: str
    source: str = ""
    authority: str = "READ_ONLY"
    readable: bool = True
    mutable: bool = False
    confidence: ObservationStatus | str = ObservationStatus.INFERRED
    canonical_path: str | None = None
    security_status: str = "UNASSESSED"

    def __post_init__(self) -> None:
        if not _ID_PATTERN.fullmatch(self.root_id):
            raise ValueError("root_id is invalid")
        if not isinstance(self.path, str) or not self.path or "\x00" in self.path:
            raise ValueError("root path is invalid")
        if not self.path.startswith("/"):
            raise ValueError("host root paths must be absolute")
        if any(part == ".." for part in self.path.replace("\\", "/").split("/")):
            raise ValueError("host root path cannot contain traversal")
        try:
            normalized_scope = RootScope(self.scope)
        except ValueError:
            normalized_scope = RootScope.UNKNOWN
        object.__setattr__(self, "scope", normalized_scope)
        try:
            normalized_confidence = ObservationStatus(self.confidence)
        except ValueError:
            normalized_confidence = ObservationStatus.UNKNOWN
        object.__setattr__(self, "confidence", normalized_confidence)
        if self.canonical_path is None:
            object.__setattr__(self, "canonical_path", self.path)


@dataclass(frozen=True, slots=True)
class WalkResult:
    files: tuple[str, ...]
    unsafe_paths: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    total_bytes: int = 0


@dataclass(frozen=True, slots=True)
class PackageFile:
    relative_path: str
    size_bytes: int
    sha256: str
    kind: str = "text"
    executable: bool = False
    observation: ObservationStatus | str = ObservationStatus.OBSERVED

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "observation", ObservationStatus(self.observation))
        except ValueError:
            object.__setattr__(self, "observation", ObservationStatus.UNKNOWN)


@dataclass(frozen=True, slots=True)
class SkillSection:
    title: str
    lines: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines", _as_tuple(self.lines))


@dataclass(frozen=True, slots=True)
class SkillDocument:
    source: str
    status: ParseStatus
    capability_id: str | None
    description: str
    version: str | None
    front_matter: Mapping[str, str]
    unknown_fields: tuple[tuple[str, str], ...]
    sections: tuple[SkillSection, ...]
    body: str
    activates_when: tuple[str, ...] = ()
    do_not_activate_when: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    primary_type: str = "SPECIALIST"
    platform_limits: tuple[str, ...] = ()
    gates: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "front_matter", _map_proxy(self.front_matter))
        for name in (
            "unknown_fields",
            "activates_when",
            "do_not_activate_when",
            "references",
            "dependencies",
            "tools",
            "providers",
            "conflicts",
            "domains",
            "platform_limits",
            "gates",
            "stop_conditions",
            "errors",
        ):
            value = getattr(self, name)
            if name == "unknown_fields":
                object.__setattr__(self, name, tuple(value))
            else:
                object.__setattr__(self, name, _as_tuple(value))


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    field: str
    source: str
    evidence: str
    confidence: ObservationStatus | str = ObservationStatus.OBSERVED


@dataclass(frozen=True, slots=True)
class ObservedCapabilityManifest:
    schema_version: str
    capability_id: str
    display_name: str
    version: str
    kind: CapabilityKind
    description: str
    primary_type: str
    activates_when: tuple[str, ...]
    do_not_activate_when: tuple[str, ...]
    domains: tuple[str, ...]
    dependencies: tuple[str, ...]
    tools: tuple[str, ...]
    providers: tuple[str, ...]
    references: tuple[str, ...]
    conflicts: tuple[str, ...]
    platform_limits: tuple[str, ...]
    field_provenance: Mapping[str, str] = field(default_factory=dict)
    provenance_details: tuple[FieldProvenance, ...] = ()
    unknown_fields: tuple[tuple[str, str], ...] = ()
    gates: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _ID_PATTERN.fullmatch(self.capability_id):
            raise ValueError("capability_id is invalid")
        object.__setattr__(self, "field_provenance", _map_proxy(self.field_provenance))
        for name in (
            "activates_when",
            "do_not_activate_when",
            "domains",
            "dependencies",
            "tools",
            "providers",
            "references",
            "conflicts",
            "platform_limits",
            "gates",
            "stop_conditions",
            "unknown_fields",
            "provenance_details",
        ):
            value = getattr(self, name)
            if name == "provenance_details" or name == "unknown_fields":
                object.__setattr__(self, name, tuple(value))
            else:
                object.__setattr__(self, name, _as_tuple(value))


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    source_type: str
    source_refs: tuple[str, ...]
    source_repository: str
    upstream: str | None
    forked_from: str | None
    tag: str | None
    commit: str | None
    local_modifications: bool
    content_hash: str
    scope: RootScope
    authority: str
    confidence: ObservationStatus | str
    observed_at: str
    license: str | None = None
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_refs", _as_tuple(self.source_refs))
        object.__setattr__(self, "aliases", _as_tuple(self.aliases))
        try:
            object.__setattr__(self, "confidence", ObservationStatus(self.confidence))
        except ValueError:
            object.__setattr__(self, "confidence", ObservationStatus.UNKNOWN)


@dataclass(frozen=True, slots=True)
class CompatibilityAssessment:
    status: CompatibilityStatus
    required_features: tuple[str, ...]
    missing_features: tuple[str, ...]
    platform_limits: tuple[str, ...]
    portability_debt: tuple[str, ...]
    reasons: tuple[str, ...]
    confidence: ObservationStatus | str

    def __post_init__(self) -> None:
        for name in (
            "required_features",
            "missing_features",
            "platform_limits",
            "portability_debt",
            "reasons",
        ):
            object.__setattr__(self, name, _as_tuple(getattr(self, name)))
        try:
            object.__setattr__(self, "confidence", ObservationStatus(self.confidence))
        except ValueError:
            object.__setattr__(self, "confidence", ObservationStatus.UNKNOWN)


@dataclass(frozen=True, slots=True)
class TrustAssessment:
    level: TrustLevel
    evidence: tuple[str, ...]
    owner_claim: str | None
    reason: str
    confidence: ObservationStatus | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _as_tuple(self.evidence))
        try:
            object.__setattr__(self, "confidence", ObservationStatus(self.confidence))
        except ValueError:
            object.__setattr__(self, "confidence", ObservationStatus.UNKNOWN)


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    capability_id: str
    display_name: str
    path: str
    root_id: str
    scope: RootScope
    skill_md: str | None
    manifest_path: str | None
    files: tuple[PackageFile, ...]
    directories: tuple[str, ...]
    agents: tuple[str, ...]
    references: tuple[str, ...]
    scripts: tuple[str, ...]
    evals: tuple[str, ...]
    benchmarks: tuple[str, ...]
    rubrics: tuple[str, ...]
    templates: tuple[str, ...]
    examples: tuple[str, ...]
    assets: tuple[str, ...]
    version: str
    status: CapabilityLifecycle
    kind: CapabilityKind
    provenance: ProvenanceRecord
    content_hash: str
    compatibility: CompatibilityAssessment
    trust: TrustAssessment
    load_eligibility: str
    manifest: ObservedCapabilityManifest
    description: str = ""
    activates_when: tuple[str, ...] = ()
    do_not_activate_when: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    gates: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _ID_PATTERN.fullmatch(self.capability_id):
            raise ValueError("capability_id is invalid")
        if not self.path.startswith("/") or "\x00" in self.path:
            raise ValueError("capability path must be absolute and NUL-free")
        for name in (
            "files",
            "directories",
            "agents",
            "references",
            "scripts",
            "evals",
            "benchmarks",
            "rubrics",
            "templates",
            "examples",
            "assets",
            "activates_when",
            "do_not_activate_when",
            "dependencies",
            "conflicts",
            "gates",
            "stop_conditions",
        ):
            value = getattr(self, name)
            object.__setattr__(self, name, tuple(value) if name == "files" else _as_tuple(value))


@dataclass(frozen=True, slots=True)
class CapabilityInventory:
    roots: tuple[CapabilityRoot, ...]
    capabilities: tuple[CapabilityRecord, ...]
    errors: tuple[str, ...]
    observed_at: str
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "roots", tuple(self.roots))
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "errors", _as_tuple(self.errors))


@dataclass(frozen=True, slots=True)
class HostFeatureDescription:
    name: str
    status: ObservationStatus
    entries: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", _as_tuple(self.entries))
        object.__setattr__(self, "limitations", _as_tuple(self.limitations))
        try:
            object.__setattr__(self, "status", ObservationStatus(self.status))
        except ValueError:
            object.__setattr__(self, "status", ObservationStatus.UNKNOWN)


@dataclass(frozen=True, slots=True)
class HostSnapshot:
    host_id: str
    adapter_version: str
    observed_at: str
    identity: Mapping[str, str]
    version: str
    roots: tuple[CapabilityRoot, ...]
    project_root: str | None
    workspace_root: str | None
    config_refs: tuple[str, ...]
    capability_count: int
    tool_metadata: HostFeatureDescription
    provider_metadata: HostFeatureDescription
    limitations: tuple[str, ...]
    confidence: ObservationStatus
    fingerprint: str
    observation_status: ObservationStatus

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity", _map_proxy(self.identity))
        object.__setattr__(self, "roots", tuple(self.roots))
        object.__setattr__(self, "config_refs", _as_tuple(self.config_refs))
        object.__setattr__(self, "limitations", _as_tuple(self.limitations))
        try:
            object.__setattr__(self, "confidence", ObservationStatus(self.confidence))
        except ValueError:
            object.__setattr__(self, "confidence", ObservationStatus.UNKNOWN)
        try:
            object.__setattr__(
                self, "observation_status", ObservationStatus(self.observation_status)
            )
        except ValueError:
            object.__setattr__(self, "observation_status", ObservationStatus.UNKNOWN)


@dataclass(frozen=True, slots=True)
class LoadObservation:
    capability_id: str
    status: ObservationStatus
    loaded: bool
    reason: str
    observed_at: str
    source: str = "host-adapter"

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "status", ObservationStatus(self.status))
        except ValueError:
            object.__setattr__(self, "status", ObservationStatus.UNKNOWN)


@dataclass(frozen=True, slots=True)
class LoadedReference:
    relative_path: str
    size_bytes: int
    sha256: str
    content: str | None
    binary: bool = False


@dataclass(frozen=True, slots=True)
class LoadedScript:
    relative_path: str
    size_bytes: int
    sha256: str
    execution: str = "DISABLED_PHASE3"


@dataclass(frozen=True, slots=True)
class LoadResult:
    capability_id: str
    level: DisclosureLevel
    identity: Mapping[str, str]
    routing_metadata: Mapping[str, Any]
    instruction_kernel: str | None
    references: tuple[LoadedReference, ...]
    scripts: tuple[LoadedScript, ...]
    package_files: tuple[PackageFile, ...]
    context_tokens_estimate: int
    context_prepared: bool
    host_loaded: bool
    host_load: LoadObservation
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity", _map_proxy(self.identity))
        object.__setattr__(self, "routing_metadata", _freeze_value(self.routing_metadata))
        object.__setattr__(self, "references", tuple(self.references))
        object.__setattr__(self, "scripts", tuple(self.scripts))
        object.__setattr__(self, "package_files", tuple(self.package_files))
        object.__setattr__(self, "warnings", _as_tuple(self.warnings))


@dataclass(frozen=True, slots=True)
class CapabilityLoadPlan:
    requested: tuple[str, ...]
    selected: tuple[str, ...]
    level: DisclosureLevel
    context_tokens_estimate: int
    prepared: bool
    host_load_observable: bool
    actual_host_loaded: bool
    statuses: Mapping[str, CapabilityLifecycle]
    blockers: tuple[str, ...]
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested", _as_tuple(self.requested))
        object.__setattr__(self, "selected", _as_tuple(self.selected))
        object.__setattr__(self, "statuses", _freeze_value(self.statuses))
        object.__setattr__(self, "blockers", _as_tuple(self.blockers))


@dataclass(frozen=True, slots=True)
class DuplicateFinding:
    capability_id: str
    category: str
    blocking: bool
    versions: tuple[str, ...]
    hashes: tuple[str, ...]
    paths: tuple[str, ...]
    explanation: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "versions", _as_tuple(self.versions))
        object.__setattr__(self, "hashes", _as_tuple(self.hashes))
        object.__setattr__(self, "paths", _as_tuple(self.paths))


@dataclass(frozen=True, slots=True)
class DependencyResolution:
    capability_id: str
    status: DependencyStatus
    selected_version: str | None
    dependency: str | None
    detail: str

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "status", DependencyStatus(self.status))
        except ValueError:
            object.__setattr__(self, "status", DependencyStatus.BLOCKED)


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    request: str
    status: ResolutionStatus
    selected: tuple[CapabilityRecord, ...]
    duplicates: tuple[DuplicateFinding, ...]
    dependencies: tuple[DependencyResolution, ...]
    blockers: tuple[str, ...]
    explanation: tuple[str, ...]
    policy: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected", tuple(self.selected))
        object.__setattr__(self, "duplicates", tuple(self.duplicates))
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(self, "blockers", _as_tuple(self.blockers))
        object.__setattr__(self, "explanation", _as_tuple(self.explanation))


@dataclass(frozen=True, slots=True)
class Phase3Event:
    event_id: str
    event_type: Phase3EventType
    capability_id: str
    lifecycle: CapabilityLifecycle
    observation: ObservationStatus
    timestamp: str
    data: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _map_proxy(self.data))


def public_data(value: Any) -> Any:
    """Convert frozen records to JSON-safe values without executing content."""

    if isinstance(value, P3Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: public_data(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): public_data(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [public_data(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
