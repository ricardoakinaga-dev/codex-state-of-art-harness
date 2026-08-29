"""Deterministic duplicate, dependency and precedence resolution."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace

from .phase3_discovery import revalidate_capability
from .phase3_models import (
    CapabilityInventory,
    CapabilityLifecycle,
    CapabilityRecord,
    CompatibilityStatus,
    DependencyResolution,
    DependencyStatus,
    DuplicateFinding,
    Phase3Limits,
    ResolutionResult,
    ResolutionStatus,
    RootScope,
    TrustLevel,
)


class ResolutionError(ValueError):
    """Raised when a resolution request cannot be represented safely."""


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")
_CORE_NUMBER = r"(?:0|[1-9][0-9]*)"
_VERSION_IDENTIFIER = r"(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
_VERSION = re.compile(
    rf"^({_CORE_NUMBER})\.({_CORE_NUMBER})\.({_CORE_NUMBER})"
    rf"(?:-({_VERSION_IDENTIFIER}(?:\.{_VERSION_IDENTIFIER})*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_MAX_VERSION_LENGTH = 256
_UNVERIFIABLE_DIGEST = "sha256:unavailable-metadata"


def _is_semver(value: str) -> bool:
    return len(value) <= _MAX_VERSION_LENGTH and _VERSION.fullmatch(value) is not None


class ResolutionEngine:
    """Resolve metadata only; selected records are never executed or imported."""

    precedence: Mapping[RootScope, int] = {
        RootScope.PROJECT: 900,
        RootScope.WORKSPACE: 800,
        RootScope.VENDORED: 700,
        RootScope.GLOBAL: 600,
        RootScope.SYSTEM: 500,
        RootScope.EXTERNAL: 400,
        RootScope.UNKNOWN: 0,
    }
    trust_rank: Mapping[TrustLevel, int] = {
        TrustLevel.PROJECT_TRUSTED: 7,
        TrustLevel.VERIFIED_LOCAL: 6,
        TrustLevel.OFFICIAL: 5,
        TrustLevel.KNOWN_UPSTREAM: 4,
        TrustLevel.THIRD_PARTY: 3,
        TrustLevel.UNVERIFIED: 2,
        TrustLevel.REJECTED: 0,
    }

    def __init__(self, limits: Phase3Limits | None = None) -> None:
        self.limits = limits or Phase3Limits()

    @staticmethod
    def _version(value: str) -> tuple[int, int, int, int, tuple[tuple[int, str], ...]]:
        match = _VERSION.fullmatch(value)
        if not _is_semver(value) or not match:
            return (0, 0, 0, 0, ())
        prerelease = match.group(4)
        if prerelease is None:
            return (int(match.group(1)), int(match.group(2)), int(match.group(3)), 1, ())
        tokens = tuple(
            (0, f"{len(item):04d}:{item}") if item.isdigit() else (1, item)
            for item in prerelease.split(".")
        )
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)), 0, tokens)

    @staticmethod
    def _parse_request(request: str) -> tuple[str, str | None]:
        if not isinstance(request, str) or not request or "\x00" in request:
            raise ResolutionError("capability request is invalid")
        if "@" in request:
            capability_id, version = request.rsplit("@", 1)
            if _ID.fullmatch(capability_id) and _is_semver(version):
                return capability_id, version
            raise ResolutionError("capability request is invalid")
        if not _ID.fullmatch(request):
            raise ResolutionError("capability request is invalid")
        return request, None

    def duplicate_report(self, inventory: CapabilityInventory) -> tuple[DuplicateFinding, ...]:
        by_id: dict[str, list[CapabilityRecord]] = {}
        for index, record in enumerate(inventory.capabilities):
            if index >= self.limits.max_duplicate_candidates:
                raise ResolutionError("duplicate candidate bound exceeded")
            by_id.setdefault(record.capability_id, []).append(record)
        findings: list[DuplicateFinding] = []
        for capability_id, records in sorted(by_id.items()):
            versions = sorted({item.version for item in records}, key=self._version)
            hashes = sorted({item.content_hash for item in records})
            paths = tuple(sorted(item.path for item in records))
            divergent_versions = tuple(
                version
                for version in versions
                if len({item.content_hash for item in records if item.version == version}) > 1
            )
            unverifiable_versions = tuple(
                version
                for version in versions
                if len([item for item in records if item.version == version]) > 1
                and any(
                    package_file.sha256 == _UNVERIFIABLE_DIGEST
                    for item in records
                    if item.version == version
                    for package_file in item.files
                )
            )
            if divergent_versions:
                findings.append(
                    DuplicateFinding(
                        capability_id,
                        "DIVERGENT_BYTES",
                        True,
                        divergent_versions,
                        tuple(hashes),
                        paths,
                        "same capability ID/version has divergent package bytes",
                    )
                )
            if unverifiable_versions:
                findings.append(
                    DuplicateFinding(
                        capability_id,
                        "UNVERIFIABLE_BYTES",
                        True,
                        unverifiable_versions,
                        tuple(hashes),
                        paths,
                        "same capability ID/version includes bytes unavailable to "
                        "the safe inspector",
                    )
                )
            elif len(records) > 1 and len(hashes) == 1:
                findings.append(
                    DuplicateFinding(
                        capability_id,
                        "SAME_BYTES_MULTIPLE_ROOTS",
                        False,
                        tuple(versions),
                        tuple(hashes),
                        paths,
                        "same package bytes are visible from multiple roots",
                    )
                )
            if len(versions) > 1:
                findings.append(
                    DuplicateFinding(
                        capability_id,
                        "MULTIPLE_VERSIONS",
                        False,
                        tuple(versions),
                        tuple(hashes),
                        paths,
                        (
                            "multiple valid versions are available; unpinned requests "
                            "select the highest compatible SemVer"
                        ),
                    )
                )
        aliases: dict[str, list[CapabilityRecord]] = {}
        for record in inventory.capabilities:
            for alias in record.provenance.aliases:
                aliases.setdefault(alias, []).append(record)
            if record.provenance.forked_from:
                findings.append(
                    DuplicateFinding(
                        record.capability_id,
                        "FORKED_SOURCE",
                        False,
                        (record.version,),
                        (record.content_hash,),
                        (record.path,),
                        f"package declares forked_from={record.provenance.forked_from[:120]}",
                    )
                )
        for alias, records in sorted(aliases.items()):
            findings.append(
                DuplicateFinding(
                    alias,
                    "ALIAS_COLLISION" if len(records) > 1 else "ALIAS",
                    len(records) > 1,
                    tuple(sorted({item.version for item in records}, key=self._version)),
                    tuple(sorted({item.content_hash for item in records})),
                    tuple(sorted(item.path for item in records)),
                    "alias metadata maps to multiple records"
                    if len(records) > 1
                    else "alias metadata was observed for one record",
                )
            )
        return tuple(findings)

    def _select(
        self,
        candidates: tuple[CapabilityRecord, ...],
        *,
        version: str | None,
        explicit: bool,
        blocked_versions: tuple[str, ...] = (),
    ) -> CapabilityRecord | None:
        eligible = tuple(
            item
            for item in candidates
            if item.status
            not in {
                CapabilityLifecycle.REJECTED,
                CapabilityLifecycle.INCOMPATIBLE,
                CapabilityLifecycle.STALE,
                CapabilityLifecycle.AMBIGUOUS,
            }
            and item.kind.value != "INVALID"
            and item.trust.level is not TrustLevel.REJECTED
            and item.compatibility.status is not CompatibilityStatus.INCOMPATIBLE
            and item.version not in blocked_versions
        )
        if version is not None:
            eligible = tuple(item for item in eligible if item.version == version)
        if not eligible:
            return None
        ranked = max(
            (
                1 if explicit else 0,
                self.precedence.get(item.scope, 0),
                self.trust_rank.get(item.trust.level, 0),
                self._version(item.version),
            )
            for item in eligible
        )
        return min(
            (
                item
                for item in eligible
                if (
                    1 if explicit else 0,
                    self.precedence.get(item.scope, 0),
                    self.trust_rank.get(item.trust.level, 0),
                    self._version(item.version),
                )
                == ranked
            ),
            key=lambda item: item.path,
        )

    @staticmethod
    def _conflict_id(value: str) -> str:
        return value.rsplit("@", 1)[0] if "@" in value else value

    def resolve(
        self,
        inventory: CapabilityInventory,
        request: str,
        *,
        explicit_pins: Mapping[str, str] | None = None,
    ) -> ResolutionResult:
        capability_id, request_version = self._parse_request(request)
        pin = (explicit_pins or {}).get(capability_id, request_version)
        if pin is not None and not _is_semver(pin):
            raise ResolutionError("explicit version pin is invalid")
        current_records: list[CapabilityRecord] = []
        stale_ids: set[str] = set()
        blocked_statuses = {
            CapabilityLifecycle.REJECTED,
            CapabilityLifecycle.INCOMPATIBLE,
            CapabilityLifecycle.STALE,
            CapabilityLifecycle.AMBIGUOUS,
        }
        for record in inventory.capabilities:
            if record.status in blocked_statuses:
                current_records.append(record)
                continue
            fresh, _ = revalidate_capability(record, self.limits)
            if fresh:
                current_records.append(record)
                continue
            stale_ids.add(record.capability_id)
            current_records.append(
                replace(
                    record,
                    status=CapabilityLifecycle.STALE,
                    load_eligibility="BLOCKED_STALE_FINGERPRINT",
                )
            )
        current_inventory = replace(inventory, capabilities=tuple(current_records))
        duplicates = self.duplicate_report(current_inventory)
        blocked_versions = tuple(
            sorted(
                {
                    version
                    for item in duplicates
                    if item.capability_id == capability_id
                    and item.blocking
                    and item.category in {"DIVERGENT_BYTES", "UNVERIFIABLE_BYTES"}
                    for version in item.versions
                },
                key=self._version,
            )
        )

        def divergence_result() -> ResolutionResult:
            duplicate_blockers = tuple(
                dict.fromkeys(
                    "CAPABILITY_DIVERGENCE"
                    if item.category == "DIVERGENT_BYTES"
                    else "CAPABILITY_UNVERIFIABLE_BYTES"
                    for item in duplicates
                    if item.capability_id == capability_id and item.blocking
                )
            )
            return ResolutionResult(
                request,
                ResolutionStatus.BLOCKED,
                (),
                tuple(item for item in duplicates if item.capability_id == capability_id),
                (),
                duplicate_blockers,
                (
                    "automatic selection is blocked; a version pin cannot distinguish "
                    "divergent bytes",
                ),
                "explicit pin > project > workspace > approved shared > global > system > external",
            )

        if pin is not None and pin in blocked_versions:
            return divergence_result()
        by_id: dict[str, tuple[CapabilityRecord, ...]] = {}
        for record in current_inventory.capabilities:
            by_id[record.capability_id] = (*by_id.get(record.capability_id, ()), record)
        root = self._select(
            by_id.get(capability_id, ()),
            version=pin,
            explicit=pin is not None,
            blocked_versions=blocked_versions,
        )
        if root is None:
            if blocked_versions:
                return divergence_result()
            if capability_id in stale_ids:
                return ResolutionResult(
                    request,
                    ResolutionStatus.BLOCKED,
                    (),
                    tuple(item for item in duplicates if item.capability_id == capability_id),
                    (),
                    ("CAPABILITY_STALE_FINGERPRINT",),
                    ("inventory snapshot is stale and must be rediscovered",),
                    "explicit pin > project > workspace > approved shared > global > "
                    "system > external",
                )
            return ResolutionResult(
                request,
                ResolutionStatus.MISSING,
                (),
                tuple(item for item in duplicates if item.capability_id == capability_id),
                (),
                ("CAPABILITY_MISSING_OR_UNUSABLE",),
                ("no compatible, trusted and non-rejected record matched the request",),
                "explicit pin > project > workspace > approved shared > global > system > external",
            )
        selected: list[CapabilityRecord] = [root]
        dependencies: list[DependencyResolution] = []
        blockers: list[str] = []
        visiting: list[str] = []
        processed: set[str] = set()

        def visit(record: CapabilityRecord, depth: int = 0) -> None:
            if record.capability_id in visiting:
                dependencies.append(
                    DependencyResolution(
                        record.capability_id,
                        DependencyStatus.CYCLE,
                        record.version,
                        record.capability_id,
                        "dependency cycle detected",
                    )
                )
                blockers.append("DEPENDENCY_CYCLE")
                return
            if record.capability_id in processed:
                return
            processed.add(record.capability_id)
            visiting.append(record.capability_id)
            for dependency in record.dependencies:
                dep_id, dep_version = self._parse_request(dependency)
                selected_dependency = next(
                    (item for item in selected if item.capability_id == dep_id), None
                )
                if (
                    selected_dependency is not None
                    and dep_version is not None
                    and dep_version != selected_dependency.version
                ):
                    dependencies.append(
                        DependencyResolution(
                            dep_id,
                            DependencyStatus.INCOMPATIBLE,
                            selected_dependency.version,
                            dependency,
                            "dependency requires a version different from the selected record",
                        )
                    )
                    blockers.append("DEPENDENCY_VERSION_CONFLICT")
                    continue
                if dep_id in visiting:
                    dependencies.append(
                        DependencyResolution(
                            dep_id,
                            DependencyStatus.CYCLE,
                            None,
                            dependency,
                            "dependency cycle detected",
                        )
                    )
                    blockers.append("DEPENDENCY_CYCLE")
                    continue
                if selected_dependency is not None:
                    dependencies.append(
                        DependencyResolution(
                            dep_id,
                            DependencyStatus.RESOLVED,
                            selected_dependency.version,
                            dependency,
                            "dependency already selected",
                        )
                    )
                    continue
                if depth >= self.limits.max_dependency_depth:
                    dependencies.append(
                        DependencyResolution(
                            dep_id,
                            DependencyStatus.BLOCKED,
                            None,
                            dependency,
                            "dependency depth bound exceeded",
                        )
                    )
                    blockers.append("DEPENDENCY_DEPTH")
                    continue
                dependency_blocked_versions = tuple(
                    sorted(
                        {
                            version
                            for item in duplicates
                            if item.capability_id == dep_id
                            and item.blocking
                            and item.category in {"DIVERGENT_BYTES", "UNVERIFIABLE_BYTES"}
                            for version in item.versions
                        },
                        key=self._version,
                    )
                )
                if dep_version is not None and dep_version in dependency_blocked_versions:
                    dependencies.append(
                        DependencyResolution(
                            dep_id,
                            DependencyStatus.AMBIGUOUS,
                            None,
                            dependency,
                            "dependency has divergent package bytes",
                        )
                    )
                    blockers.append("AMBIGUOUS_DEPENDENCY")
                    continue
                candidate = self._select(
                    by_id.get(dep_id, ()),
                    version=dep_version,
                    explicit=dep_version is not None,
                    blocked_versions=dependency_blocked_versions,
                )
                if candidate is None:
                    if dependency_blocked_versions:
                        dependencies.append(
                            DependencyResolution(
                                dep_id,
                                DependencyStatus.AMBIGUOUS,
                                None,
                                dependency,
                                "dependency has no non-divergent eligible package version",
                            )
                        )
                        blockers.append("AMBIGUOUS_DEPENDENCY")
                        continue
                    if dep_id in stale_ids:
                        dependencies.append(
                            DependencyResolution(
                                dep_id,
                                DependencyStatus.BLOCKED,
                                None,
                                dependency,
                                "dependency inventory snapshot is stale",
                            )
                        )
                        blockers.append("STALE_DEPENDENCY")
                        continue
                    dependencies.append(
                        DependencyResolution(
                            dep_id,
                            DependencyStatus.MISSING,
                            None,
                            dependency,
                            "dependency is missing or incompatible",
                        )
                    )
                    blockers.append("MISSING_DEPENDENCY")
                    continue
                dependencies.append(
                    DependencyResolution(
                        dep_id,
                        DependencyStatus.RESOLVED,
                        candidate.version,
                        dependency,
                        "dependency selected by the same precedence policy",
                    )
                )
                selected.append(candidate)
                visit(candidate, depth + 1)
            visiting.pop()

        visit(root)
        selected_ids = {item.capability_id for item in selected}
        for record in selected:
            for conflict in record.conflicts:
                conflict_id = self._conflict_id(conflict)
                if conflict_id in selected_ids and conflict_id != record.capability_id:
                    blockers.append(f"CAPABILITY_CONFLICT:{record.capability_id}:{conflict_id}")
        status = ResolutionStatus.BLOCKED if blockers else ResolutionStatus.RESOLVED
        return ResolutionResult(
            request,
            status,
            () if blockers else tuple(selected),
            tuple(
                item
                for item in duplicates
                if item.capability_id in selected_ids or item.capability_id == capability_id
            ),
            tuple(dependencies),
            tuple(dict.fromkeys(blockers)),
            ("selection is metadata-only and follows the documented Phase 3 precedence policy",),
            "explicit pin > project > workspace > approved shared > global > system > external",
        )
