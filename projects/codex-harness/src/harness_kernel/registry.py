"""Pure capability-manifest registry primitives.

The registry stores metadata only.  It never imports a capability, resolves a
Python object, calls a provider, or loads a package.  A registry operation
returns a new registry so callers can keep an append-only snapshot for audit.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from functools import total_ordering
from typing import Any, cast

from .models import (
    REGISTRY_ORIGIN_PRECEDENCE,
    CapabilityManifest,
    CapabilityStatus,
    InstallationScope,
    RecordStatus,
    RegistryOrigin,
)
from .validation import validate


class RegistryError(ValueError):
    """Base error for malformed registry metadata or resolution requests."""


class SemVerError(RegistryError):
    """Raised when a version or version range is not valid semver syntax."""


class RegistryConflictError(RegistryError):
    """Raised when an immutable registry snapshot receives a duplicate key."""


class InvalidManifestError(RegistryError):
    """Raised when a manifest cannot be admitted to the registry."""

    def __init__(self, message: str, diagnostics: Iterable[RegistryDiagnostic] = ()) -> None:
        self.diagnostics = tuple(diagnostics)
        super().__init__(message)


class DiagnosticSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


_SEMVER_PATTERN = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")
_SOURCE_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_REGISTRY_ADMISSION_CODES = frozenset(
    {
        "INVALID_CAPABILITY_ID",
        "INVALID_VERSION",
        "INVALID_MANIFEST",
        "INVALID_REGISTRY_ORIGIN",
        "INVALID_ORIGIN_PRECEDENCE",
        "MISSING_SOURCE_REPOSITORY",
        "INVALID_SOURCE_HASH",
        "INVALID_INSTALLATION_SCOPE",
        "MISSING_PROJECT_SCOPE",
        "INVALID_FORK_REFERENCE",
    }
)


@total_ordering
@dataclass(frozen=True, slots=True, eq=False)
class SemVer:
    """A semver 2.0 value with build metadata excluded from precedence."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[int | str, ...] = ()
    build: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if min(self.major, self.minor, self.patch) < 0:
            raise SemVerError("semver components cannot be negative")
        if any(isinstance(item, bool) for item in (self.major, self.minor, self.patch)):
            raise SemVerError("semver components must be integers")
        if any(isinstance(item, int) and item < 0 for item in self.prerelease):
            raise SemVerError("prerelease numeric identifiers cannot be negative")

    @classmethod
    def parse(cls, value: str) -> SemVer:
        if not isinstance(value, str):
            raise SemVerError("version must be a string")
        match = _SEMVER_PATTERN.fullmatch(value.strip())
        if match is None:
            raise SemVerError(f"invalid semver: {value!r}")

        def identifiers(
            raw: str | None, *, numeric: bool
        ) -> tuple[int | str, ...] | tuple[str, ...]:
            if not raw:
                return ()
            result: list[int | str] = []
            for item in raw.split("."):
                if not item or not re.fullmatch(r"[0-9A-Za-z-]+", item):
                    raise SemVerError(f"invalid semver identifier: {item!r}")
                if numeric and item.isdigit():
                    if len(item) > 1 and item.startswith("0"):
                        raise SemVerError(
                            "numeric prerelease identifiers cannot have leading zeroes"
                        )
                    result.append(int(item))
                else:
                    result.append(item)
            return tuple(result)

        return cls(
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
            identifiers(match.group("pre"), numeric=True),
            cast(tuple[str, ...], identifiers(match.group("build"), numeric=False)),
        )

    def _precedence(self) -> tuple[int, int, int, tuple[int | str, ...]]:
        return self.major, self.minor, self.patch, self.prerelease

    def __str__(self) -> str:
        value = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            value += "-" + ".".join(str(item) for item in self.prerelease)
        if self.build:
            value += "+" + ".".join(self.build)
        return value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SemVer) and self._precedence() == other._precedence()

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        left = self._precedence()
        right = other._precedence()
        if left[:3] != right[:3]:
            return left[:3] < right[:3]
        left_pre, right_pre = left[3], right[3]
        if not left_pre and right_pre:
            return False
        if left_pre and not right_pre:
            return True
        for left_item, right_item in zip(left_pre, right_pre, strict=False):
            if left_item == right_item:
                continue
            if isinstance(left_item, int) and isinstance(right_item, str):
                return True
            if isinstance(left_item, str) and isinstance(right_item, int):
                return False
            return str(left_item) < str(right_item)
        return len(left_pre) < len(right_pre)

    def __hash__(self) -> int:
        return hash(self._precedence())


def parse_semver(value: str | SemVer) -> SemVer:
    """Parse a strict semantic version without consulting external packages."""

    return value if isinstance(value, SemVer) else SemVer.parse(value)


def compare_semver(left: str | SemVer, right: str | SemVer) -> int:
    """Return ``-1``, ``0`` or ``1`` according to semver precedence."""

    first, second = parse_semver(left), parse_semver(right)
    return (first > second) - (first < second)


@dataclass(frozen=True, slots=True)
class VersionRange:
    """A small, deterministic semver range supporting common registry syntax."""

    raw: str
    alternatives: tuple[tuple[tuple[str, SemVer], ...], ...]

    def matches(self, version: str | SemVer) -> bool:
        candidate = parse_semver(version)
        return any(
            all(_compare(candidate, operator, bound) for operator, bound in alternative)
            for alternative in self.alternatives
        )


def _compare(version: SemVer, operator: str, bound: SemVer) -> bool:
    if operator == ">=":
        return version >= bound
    if operator == ">":
        return version > bound
    if operator == "<=":
        return version <= bound
    if operator == "<":
        return version < bound
    if operator in ("", "="):
        return version == bound
    raise SemVerError(f"unsupported range operator: {operator}")


def _partial_version(value: str) -> tuple[int | None, int | None, int | None]:
    token = value.strip().lstrip("v")
    if not token:
        raise SemVerError("empty version range")
    pieces = token.split(".")
    if len(pieces) > 3:
        raise SemVerError(f"invalid partial semver: {value!r}")
    result: list[int | None] = []
    for piece in pieces:
        if piece.lower() in {"x", "*"}:
            result.append(None)
        elif piece.isdigit() and (piece == "0" or not piece.startswith("0")):
            result.append(int(piece))
        else:
            raise SemVerError(f"invalid partial semver: {value!r}")
    while len(result) < 3:
        result.append(None)
    return result[0], result[1], result[2]


def _lower_bound(parts: tuple[int | None, int | None, int | None]) -> SemVer:
    return SemVer(parts[0] or 0, parts[1] or 0, parts[2] or 0)


def _next_bound(parts: tuple[int | None, int | None, int | None]) -> SemVer:
    major, minor, patch = parts
    if major is None:
        raise SemVerError("wildcard range has no upper bound")
    if minor is None:
        return SemVer(major + 1, 0, 0)
    if patch is None:
        return SemVer(major, minor + 1, 0)
    return SemVer(major, minor, patch + 1)


def _caret_bounds(parts: tuple[int | None, int | None, int | None]) -> tuple[SemVer, SemVer]:
    lower = _lower_bound(parts)
    if parts[0] is None:
        return lower, SemVer(1, 0, 0)
    if parts[0] > 0:
        return lower, SemVer(parts[0] + 1, 0, 0)
    if parts[1] is None or parts[1] > 0:
        return lower, SemVer(0, (parts[1] or 0) + 1, 0)
    return lower, SemVer(0, 0, (parts[2] or 0) + 1)


def _tilde_bounds(parts: tuple[int | None, int | None, int | None]) -> tuple[SemVer, SemVer]:
    lower = _lower_bound(parts)
    if parts[0] is None:
        return lower, SemVer(1, 0, 0)
    if parts[1] is None:
        return lower, SemVer(parts[0] + 1, 0, 0)
    return lower, SemVer(parts[0], parts[1] + 1, 0)


def _token_comparators(token: str) -> tuple[tuple[str, SemVer], ...]:
    token = token.strip()
    if not token or token in {"*", "x", "X"}:
        return ()
    match = re.match(r"^(<=|>=|<|>|=|\^|~)?(.*)$", token)
    assert match is not None
    operator, raw_version = match.group(1) or "", match.group(2)
    if operator in {"^", "~"}:
        bounds = _caret_bounds if operator == "^" else _tilde_bounds
        lower, upper = bounds(_partial_version(raw_version))
        return ((">=", lower), ("<", upper))
    parts = _partial_version(raw_version)
    has_wildcard = any(part is None for part in parts)
    if operator in {">", ">=", "<", "<="}:
        lower = _lower_bound(parts)
        if not has_wildcard:
            return ((operator, lower),)
        if operator in {">", ">="}:
            return ((operator, lower),)
        return (("<", lower if operator == "<" else _next_bound(parts)),)
    if has_wildcard:
        return (
            ((">=", _lower_bound(parts)), ("<", _next_bound(parts))) if parts[0] is not None else ()
        )
    exact = SemVer(parts[0] or 0, parts[1] or 0, parts[2] or 0)
    return (("=", exact),)


def parse_version_range(value: str | SemVer | VersionRange | None) -> VersionRange:
    """Parse exact, comparator, caret, tilde and wildcard ranges."""

    if isinstance(value, VersionRange):
        return value
    if isinstance(value, SemVer):
        return VersionRange(raw=str(value), alternatives=((("=", value),),))
    raw = "*" if value is None else value.strip()
    if not raw:
        raw = "*"
    alternatives: list[tuple[tuple[str, SemVer], ...]] = []
    for alternative in raw.split("||"):
        normalized = alternative.strip()
        if not normalized or normalized in {"*", "x", "X", "latest"}:
            alternatives.append(())
            continue
        hyphen = re.fullmatch(r"(.+?)\s+-\s+(.+)", normalized)
        if hyphen:
            start, end = _partial_version(hyphen.group(1)), _partial_version(hyphen.group(2))
            alternatives.append(((">=", _lower_bound(start)), ("<=", _lower_bound(end))))
            continue
        tokens = [item for item in re.split(r"[\s,]+", normalized) if item]
        comparators: list[tuple[str, SemVer]] = []
        for token in tokens:
            comparators.extend(_token_comparators(token))
        alternatives.append(tuple(comparators))
    return VersionRange(raw=raw, alternatives=tuple(alternatives))


def satisfies(version: str | SemVer, version_range: str | VersionRange | None) -> bool:
    """Return whether a version satisfies a supported range expression."""

    return parse_version_range(version_range).matches(version)


@dataclass(frozen=True, slots=True)
class RegistryDiagnostic:
    code: str
    message: str
    capability_id: str | None = None
    version: str | None = None
    dependency: str | None = None
    path: str = "$"
    severity: DiagnosticSeverity | str = DiagnosticSeverity.ERROR

    def __post_init__(self) -> None:
        if not isinstance(self.severity, DiagnosticSeverity):
            object.__setattr__(self, "severity", DiagnosticSeverity(str(self.severity).upper()))


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(_IDENTIFIER_PATTERN.fullmatch(value))


def _manifest_diagnostics(manifest: CapabilityManifest) -> tuple[RegistryDiagnostic, ...]:
    diagnostics: list[RegistryDiagnostic] = []
    if not _is_identifier(manifest.capability_id):
        diagnostics.append(
            RegistryDiagnostic(
                "INVALID_CAPABILITY_ID",
                "capability_id must be a non-empty registry identifier",
                capability_id=manifest.capability_id,
                path="$.capability_id",
            )
        )
    try:
        parse_semver(manifest.version)
    except SemVerError as exc:
        diagnostics.append(
            RegistryDiagnostic(
                "INVALID_VERSION",
                str(exc),
                capability_id=manifest.capability_id,
                version=str(manifest.version),
                path="$.version",
            )
        )

    provenance = manifest.provenance
    origin = _value(getattr(provenance, "origin", None))
    if origin not in {item.value for item in RegistryOrigin}:
        diagnostics.append(
            RegistryDiagnostic(
                "INVALID_REGISTRY_ORIGIN",
                "manifest provenance has an unknown registry origin",
                capability_id=manifest.capability_id,
                version=str(manifest.version),
                path="$.provenance.origin",
            )
        )
    precedence = getattr(provenance, "precedence", None)
    if not isinstance(precedence, int) or isinstance(precedence, bool):
        diagnostics.append(
            RegistryDiagnostic(
                "INVALID_ORIGIN_PRECEDENCE",
                "registry origin precedence must be an integer",
                capability_id=manifest.capability_id,
                version=str(manifest.version),
                path="$.provenance.precedence",
            )
        )
    elif (
        origin in {item.value for item in RegistryOrigin}
        and precedence != REGISTRY_ORIGIN_PRECEDENCE[RegistryOrigin(origin)]
    ):
        diagnostics.append(
            RegistryDiagnostic(
                "INVALID_ORIGIN_PRECEDENCE",
                "precedence must match the canonical registry-origin policy",
                capability_id=manifest.capability_id,
                version=str(manifest.version),
                path="$.provenance.precedence",
            )
        )
    source_repository = getattr(provenance, "source_repository", None)
    if not isinstance(source_repository, str) or not source_repository.strip():
        diagnostics.append(
            RegistryDiagnostic(
                "MISSING_SOURCE_REPOSITORY",
                "manifest provenance needs a source repository",
                capability_id=manifest.capability_id,
                version=str(manifest.version),
                path="$.provenance.source_repository",
            )
        )
    source_hash = getattr(provenance, "source_hash", None)
    if not isinstance(source_hash, str) or not _SOURCE_HASH_PATTERN.fullmatch(source_hash):
        diagnostics.append(
            RegistryDiagnostic(
                "INVALID_SOURCE_HASH",
                "source_hash must be a sha256 digest",
                capability_id=manifest.capability_id,
                version=str(manifest.version),
                path="$.provenance.source_hash",
            )
        )
    installation_scope = _value(getattr(provenance, "installation_scope", None))
    if installation_scope not in {item.value for item in InstallationScope}:
        diagnostics.append(
            RegistryDiagnostic(
                "INVALID_INSTALLATION_SCOPE",
                "manifest provenance has an unknown installation scope",
                capability_id=manifest.capability_id,
                version=str(manifest.version),
                path="$.provenance.installation_scope",
            )
        )
    project_scope = getattr(provenance, "project_scope", None)
    if origin in {RegistryOrigin.PROJECT.value, RegistryOrigin.VENDORED.value} and (
        not isinstance(project_scope, str) or not project_scope.strip()
    ):
        diagnostics.append(
            RegistryDiagnostic(
                "MISSING_PROJECT_SCOPE",
                "project and vendored capabilities need project ownership",
                capability_id=manifest.capability_id,
                version=str(manifest.version),
                path="$.provenance.project_scope",
            )
        )
    forked_from = getattr(provenance, "forked_from", None)
    if forked_from is not None and (not isinstance(forked_from, str) or not forked_from.strip()):
        diagnostics.append(
            RegistryDiagnostic(
                "INVALID_FORK_REFERENCE",
                "forked_from must be a non-empty reference when present",
                capability_id=manifest.capability_id,
                version=str(manifest.version),
                path="$.provenance.forked_from",
            )
        )

    try:
        structural = validate(manifest)
    except (TypeError, ValueError, AttributeError) as exc:
        diagnostics.append(
            RegistryDiagnostic(
                "INVALID_MANIFEST",
                f"manifest validation failed: {type(exc).__name__}",
                capability_id=manifest.capability_id,
                version=str(manifest.version),
            )
        )
    else:
        if not structural.is_valid:
            for finding in structural.findings:
                diagnostics.append(
                    RegistryDiagnostic(
                        "INVALID_MANIFEST",
                        finding.message,
                        capability_id=manifest.capability_id,
                        version=manifest.version,
                        path=finding.path,
                    )
                )

    if _value(manifest.record.status) in {
        RecordStatus.STALE.value,
        RecordStatus.SUPERSEDED.value,
        RecordStatus.INVALID.value,
        RecordStatus.BLOCKED.value,
    }:
        diagnostics.append(
            RegistryDiagnostic(
                "STALE_MANIFEST",
                "manifest record is not current",
                capability_id=manifest.capability_id,
                version=manifest.version,
                path="$.record.status",
            )
        )
    if not manifest.provenance.source_refs:
        diagnostics.append(
            RegistryDiagnostic(
                "MISSING_PROVENANCE",
                "manifest provenance needs at least one source reference",
                capability_id=manifest.capability_id,
                version=manifest.version,
                path="$.provenance.source_refs",
            )
        )
    if not str(manifest.provenance.inspected_at).strip():
        diagnostics.append(
            RegistryDiagnostic(
                "MISSING_INSPECTION_PROVENANCE",
                "manifest provenance needs an inspection timestamp",
                capability_id=manifest.capability_id,
                version=manifest.version,
                path="$.provenance.inspected_at",
            )
        )
    if not manifest.record.provenance.source_refs:
        diagnostics.append(
            RegistryDiagnostic(
                "MISSING_RECORD_PROVENANCE",
                "record provenance needs a source reference",
                capability_id=manifest.capability_id,
                version=manifest.version,
                path="$.record.provenance.source_refs",
                severity=DiagnosticSeverity.WARNING,
            )
        )
    if _value(manifest.status) == CapabilityStatus.VERIFIED.value and (
        not manifest.provenance.source_refs or not manifest.quality.eval_refs
    ):
        diagnostics.append(
            RegistryDiagnostic(
                "UNVERIFIED_PROVENANCE",
                "verified capability needs source and evaluation references",
                capability_id=manifest.capability_id,
                version=manifest.version,
                path="$.status",
            )
        )
    if _value(manifest.status) == CapabilityStatus.ACTIVE.value and (
        not manifest.contracts.gates or not manifest.contracts.stop_conditions
    ):
        diagnostics.append(
            RegistryDiagnostic(
                "ACTIVE_MISSING_GATES",
                "active capability needs gates and stop conditions",
                capability_id=manifest.capability_id,
                version=manifest.version,
                path="$.contracts",
            )
        )
    if _value(manifest.status) == CapabilityStatus.DEPRECATED.value:
        diagnostics.append(
            RegistryDiagnostic(
                "DEPRECATED_MANIFEST",
                "capability is deprecated and excluded from default selection",
                capability_id=manifest.capability_id,
                version=manifest.version,
                path="$.status",
                severity=DiagnosticSeverity.WARNING,
            )
        )
    if _value(manifest.status) == CapabilityStatus.REJECTED.value:
        diagnostics.append(
            RegistryDiagnostic(
                "REJECTED_MANIFEST",
                "capability is rejected and cannot be selected",
                capability_id=manifest.capability_id,
                version=manifest.version,
                path="$.status",
            )
        )
    return tuple(diagnostics)


def _admission_diagnostics(manifest: CapabilityManifest) -> tuple[RegistryDiagnostic, ...]:
    diagnostics = _manifest_diagnostics(manifest)
    return tuple(
        item
        for item in diagnostics
        if item.severity is DiagnosticSeverity.ERROR and item.code in _REGISTRY_ADMISSION_CODES
    )


@dataclass(frozen=True, slots=True)
class ManifestInspection:
    manifest: CapabilityManifest | None
    valid: bool
    stale: bool
    provenance_ok: bool
    diagnostics: tuple[RegistryDiagnostic, ...] = ()

    @property
    def usable(self) -> bool:
        if self.manifest is None:
            return False
        status = _value(self.manifest.status)
        return (
            self.valid
            and not self.stale
            and self.provenance_ok
            and status not in {CapabilityStatus.DEPRECATED.value, CapabilityStatus.REJECTED.value}
        )

    @property
    def is_valid(self) -> bool:
        return self.valid


@dataclass(frozen=True, slots=True)
class DependencyResolution:
    root: str
    resolved: tuple[CapabilityManifest, ...]
    diagnostics: tuple[RegistryDiagnostic, ...] = ()
    cycles: tuple[tuple[str, ...], ...] = ()
    external_tools: tuple[str, ...] = ()
    external_providers: tuple[str, ...] = ()
    external_references: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(item.severity is DiagnosticSeverity.ERROR for item in self.diagnostics)

    @property
    def is_valid(self) -> bool:
        return self.ok

    @property
    def resolved_ids(self) -> tuple[str, ...]:
        return tuple(item.capability_id for item in self.resolved)


def _sort_manifests(manifests: Iterable[CapabilityManifest]) -> tuple[CapabilityManifest, ...]:
    return tuple(
        sorted(manifests, key=lambda item: (item.capability_id, parse_semver(item.version)))
    )


def _record_is_stale(manifest: CapabilityManifest) -> bool:
    return _value(manifest.record.status) in {
        RecordStatus.STALE.value,
        RecordStatus.SUPERSEDED.value,
        RecordStatus.INVALID.value,
        RecordStatus.BLOCKED.value,
    }


def _status_allowed(
    manifest: CapabilityManifest,
    *,
    include_stale: bool,
    include_deprecated: bool,
    include_rejected: bool,
) -> bool:
    if _record_is_stale(manifest) and not include_stale:
        return False
    status = _value(manifest.status)
    if status == CapabilityStatus.DEPRECATED.value and not include_deprecated:
        return False
    if status == CapabilityStatus.REJECTED.value and not include_rejected:
        return False
    return (
        status
        in {
            CapabilityStatus.CANDIDATE.value,
            CapabilityStatus.EXPERIMENTAL.value,
            CapabilityStatus.VERIFIED.value,
            CapabilityStatus.ACTIVE.value,
        }
        or include_rejected
        or include_deprecated
    )


def _dependency_parts(value: str) -> tuple[str, str]:
    raw = value.strip()
    if not raw:
        raise RegistryError("dependency identifier cannot be empty")
    at = raw.rfind("@")
    if at > 0 and at < len(raw) - 1:
        suffix = raw[at + 1 :].strip()
        if suffix[0].isdigit() or suffix[0] in "<>=^~*xXl":
            return raw[:at], suffix
    match = re.match(
        r"^(?P<id>[A-Za-z0-9][A-Za-z0-9._:/@-]*?)(?P<range>(?:\^|~|>=|<=|>|<|=).+)$", raw
    )
    if match:
        return match.group("id"), match.group("range")
    return raw, "*"


@dataclass(frozen=True, slots=True)
class CapabilityRegistry:
    """An immutable collection of capability manifests indexed by ID/version."""

    manifests: tuple[CapabilityManifest, ...] = ()

    def __post_init__(self) -> None:
        normalized = tuple(self.manifests)
        if normalized != self.manifests:
            object.__setattr__(self, "manifests", normalized)
        seen: set[tuple[str, str]] = set()
        for manifest in normalized:
            if not isinstance(manifest, CapabilityManifest):
                raise TypeError("registry entries must be CapabilityManifest values")
            fatal = _admission_diagnostics(manifest)
            if fatal:
                raise InvalidManifestError("manifest failed registry admission", fatal)
            key = (manifest.capability_id, manifest.version)
            if key in seen:
                raise RegistryConflictError(f"duplicate capability ID/version: {key[0]}@{key[1]}")
            seen.add(key)

    @classmethod
    def from_manifests(cls, manifests: Iterable[CapabilityManifest]) -> CapabilityRegistry:
        registry = cls()
        for manifest in manifests:
            registry = registry.register(manifest)
        return registry

    def register(
        self, manifest: CapabilityManifest, *, replace: bool = False
    ) -> CapabilityRegistry:
        """Return a new registry containing ``manifest`` after metadata checks."""

        if not isinstance(manifest, CapabilityManifest):
            raise TypeError("manifest must be a CapabilityManifest")
        diagnostics = _manifest_diagnostics(manifest)
        fatal = tuple(
            item
            for item in diagnostics
            if item.severity is DiagnosticSeverity.ERROR and item.code in _REGISTRY_ADMISSION_CODES
        )
        if fatal:
            raise InvalidManifestError("manifest failed registry admission", diagnostics)
        key = (manifest.capability_id, manifest.version)
        existing = tuple(
            item for item in self.manifests if (item.capability_id, item.version) == key
        )
        if existing and not replace:
            existing_origin = _value(existing[0].provenance.origin)
            incoming_origin = _value(manifest.provenance.origin)
            raise RegistryConflictError(
                "duplicate capability ID/version requires explicit resolution; "
                f"origins={existing_origin!r},{incoming_origin!r} for {key[0]}@{key[1]}"
            )
        kept = tuple(item for item in self.manifests if (item.capability_id, item.version) != key)
        return CapabilityRegistry(kept + (manifest,))

    def list(
        self,
        capability_id: str | None = None,
        *,
        include_stale: bool = True,
        include_deprecated: bool = True,
        include_rejected: bool = True,
        status: CapabilityStatus | str | None = None,
    ) -> tuple[CapabilityManifest, ...]:
        """List deterministic manifest snapshots, optionally filtered by state."""

        wanted = _value(status) if status is not None else None
        return _sort_manifests(
            item
            for item in self.manifests
            if (capability_id is None or item.capability_id == capability_id)
            and (wanted is None or _value(item.status) == wanted)
            and _status_allowed(
                item,
                include_stale=include_stale,
                include_deprecated=include_deprecated,
                include_rejected=include_rejected,
            )
        )

    def find(
        self,
        capability_id: str,
        version: str | SemVer | VersionRange | None = None,
        *,
        include_stale: bool = False,
        include_deprecated: bool = False,
        include_rejected: bool = False,
    ) -> CapabilityManifest | None:
        """Find the highest matching usable version without loading it."""

        version_range = parse_version_range(version) if version is not None else None
        candidates = [
            item
            for item in self.manifests
            if item.capability_id == capability_id
            and _status_allowed(
                item,
                include_stale=include_stale,
                include_deprecated=include_deprecated,
                include_rejected=include_rejected,
            )
            and (version_range is None or version_range.matches(item.version))
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (
                REGISTRY_ORIGIN_PRECEDENCE.get(RegistryOrigin(_value(item.provenance.origin)), -1),
                parse_semver(item.version),
            ),
        )

    def inspect(
        self,
        capability_id: str,
        version: str | SemVer | VersionRange | None = None,
    ) -> ManifestInspection:
        """Inspect validity, freshness and provenance of a manifest snapshot."""

        manifest = self.find(
            capability_id,
            version,
            include_stale=True,
            include_deprecated=True,
            include_rejected=True,
        )
        if manifest is None:
            return ManifestInspection(
                manifest=None,
                valid=False,
                stale=False,
                provenance_ok=False,
                diagnostics=(
                    RegistryDiagnostic(
                        "MISSING_MANIFEST",
                        "capability manifest was not found",
                        capability_id=capability_id,
                    ),
                ),
            )
        diagnostics = _manifest_diagnostics(manifest)
        errors = tuple(item for item in diagnostics if item.severity is DiagnosticSeverity.ERROR)
        provenance_codes = {"MISSING_PROVENANCE", "MISSING_INSPECTION_PROVENANCE"}
        return ManifestInspection(
            manifest=manifest,
            valid=not any(item.code == "INVALID_MANIFEST" for item in errors),
            stale=_record_is_stale(manifest),
            provenance_ok=not any(item.code in provenance_codes for item in errors),
            diagnostics=diagnostics,
        )

    def diagnose(
        self, capability_id: str, version: str | SemVer | VersionRange | None = None
    ) -> tuple[RegistryDiagnostic, ...]:
        """Return manifest and declared conflict diagnostics without side effects."""

        inspection = self.inspect(capability_id, version)
        diagnostics = list(inspection.diagnostics)
        if inspection.manifest is None:
            return tuple(diagnostics)
        for conflict in sorted(inspection.manifest.composition.conflicts_with):
            conflict_id, _ = _dependency_parts(conflict)
            if any(item.capability_id == conflict_id for item in self.manifests):
                diagnostics.append(
                    RegistryDiagnostic(
                        "CAPABILITY_CONFLICT",
                        f"manifest declares a conflict with {conflict_id}",
                        capability_id=capability_id,
                        version=inspection.manifest.version,
                        dependency=conflict,
                        path="$.composition.conflicts_with",
                    )
                )
        return tuple(diagnostics)

    def resolve_dependencies(
        self,
        root: str | CapabilityManifest,
        *,
        include_root: bool = True,
    ) -> DependencyResolution:
        """Resolve capability dependencies in deterministic dependency-first order."""

        root_id = (
            root.capability_id
            if isinstance(root, CapabilityManifest)
            else _dependency_parts(root)[0]
        )
        root_version = root.version if isinstance(root, CapabilityManifest) else None
        root_manifest = self.find(root_id, root_version)
        diagnostics: list[RegistryDiagnostic] = []
        cycles: list[tuple[str, ...]] = []
        ordered: list[CapabilityManifest] = []
        visiting: list[tuple[str, str]] = []
        visited: set[tuple[str, str]] = set()
        tools: set[str] = set()
        providers: set[str] = set()
        references: set[str] = set()

        if root_manifest is None:
            diagnostics.append(
                RegistryDiagnostic(
                    "MISSING_ROOT",
                    "root capability is not available for dependency resolution",
                    capability_id=root_id,
                    version=root_version,
                )
            )
            return DependencyResolution(root_id, (), tuple(diagnostics))

        def select(spec: str, parent: CapabilityManifest) -> CapabilityManifest | None:
            try:
                dependency_id, raw_range = _dependency_parts(spec)
                constraint = parse_version_range(raw_range)
            except (RegistryError, SemVerError) as exc:
                diagnostics.append(
                    RegistryDiagnostic(
                        "INVALID_DEPENDENCY_SPEC",
                        str(exc),
                        capability_id=parent.capability_id,
                        version=parent.version,
                        dependency=spec,
                        path="$.dependencies.capabilities",
                    )
                )
                return None
            candidates = [
                item
                for item in self.manifests
                if item.capability_id == dependency_id and constraint.matches(item.version)
            ]
            usable = [
                item for item in candidates if self.inspect(item.capability_id, item.version).usable
            ]
            if usable:
                return max(usable, key=lambda item: parse_semver(item.version))
            if not candidates:
                code, message = "MISSING_DEPENDENCY", "required capability dependency is absent"
            elif any(_value(item.status) == CapabilityStatus.REJECTED.value for item in candidates):
                code, message = (
                    "REJECTED_DEPENDENCY",
                    "required dependency is rejected and cannot be used",
                )
            elif any(
                _value(item.status) == CapabilityStatus.DEPRECATED.value for item in candidates
            ):
                code, message = (
                    "DEPRECATED_DEPENDENCY",
                    "required dependency is deprecated and cannot be used",
                )
            elif any(_record_is_stale(item) for item in candidates):
                code, message = "STALE_DEPENDENCY", "required dependency is stale or superseded"
            else:
                code, message = (
                    "UNSATISFIED_DEPENDENCY",
                    "no usable version satisfies the dependency range",
                )
            diagnostics.append(
                RegistryDiagnostic(
                    code,
                    message,
                    capability_id=parent.capability_id,
                    version=parent.version,
                    dependency=spec,
                    path="$.dependencies.capabilities",
                )
            )
            return None

        def visit(manifest: CapabilityManifest) -> None:
            key = (manifest.capability_id, manifest.version)
            if key in visiting:
                start = visiting.index(key)
                cycle = tuple(item[0] for item in visiting[start:]) + (manifest.capability_id,)
                if cycle not in cycles:
                    cycles.append(cycle)
                    diagnostics.append(
                        RegistryDiagnostic(
                            "DEPENDENCY_CYCLE",
                            "capability dependency graph contains a cycle",
                            capability_id=manifest.capability_id,
                            version=manifest.version,
                            dependency=" -> ".join(cycle),
                            path="$.dependencies.capabilities",
                        )
                    )
                return
            if key in visited:
                return
            visiting.append(key)
            tools.update(manifest.dependencies.tools)
            providers.update(manifest.dependencies.providers)
            references.update(manifest.dependencies.references)
            for dependency in sorted(manifest.dependencies.capabilities):
                child = select(dependency, manifest)
                if child is not None:
                    visit(child)
            visiting.pop()
            visited.add(key)
            ordered.append(manifest)

        visit(root_manifest)
        root_key = (root_manifest.capability_id, root_manifest.version)
        result_order = tuple(
            item
            for item in ordered
            if include_root or (item.capability_id, item.version) != root_key
        )
        for manifest in result_order:
            for conflict in sorted(manifest.composition.conflicts_with):
                conflict_id, _ = _dependency_parts(conflict)
                if any(item.capability_id == conflict_id for item in result_order):
                    diagnostics.append(
                        RegistryDiagnostic(
                            "CAPABILITY_CONFLICT",
                            f"resolved capability conflicts with {conflict_id}",
                            capability_id=manifest.capability_id,
                            version=manifest.version,
                            dependency=conflict,
                            path="$.composition.conflicts_with",
                        )
                    )
        return DependencyResolution(
            root=root_id,
            resolved=result_order,
            diagnostics=tuple(diagnostics),
            cycles=tuple(cycles),
            external_tools=tuple(sorted(tools)),
            external_providers=tuple(sorted(providers)),
            external_references=tuple(sorted(references)),
        )


Registry = CapabilityRegistry
SemVerRange = VersionRange
parse_version = parse_semver


def register(
    registry: CapabilityRegistry, manifest: CapabilityManifest, *, replace: bool = False
) -> CapabilityRegistry:
    return registry.register(manifest, replace=replace)


def list_manifests(
    registry: CapabilityRegistry,
    capability_id: str | None = None,
    **kwargs: Any,
) -> tuple[CapabilityManifest, ...]:
    return registry.list(capability_id, **kwargs)


def find(
    registry: CapabilityRegistry,
    capability_id: str,
    version: str | SemVer | VersionRange | None = None,
    **kwargs: Any,
) -> CapabilityManifest | None:
    return registry.find(capability_id, version, **kwargs)


def resolve_dependencies(
    registry: CapabilityRegistry,
    root: str | CapabilityManifest,
    *,
    include_root: bool = True,
) -> DependencyResolution:
    return registry.resolve_dependencies(root, include_root=include_root)
