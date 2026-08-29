"""Progressive, declarative-only loading for observed capability packages."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import PurePosixPath

from .phase3_discovery import revalidate_capability
from .phase3_models import (
    CapabilityLifecycle,
    CapabilityLoadPlan,
    CapabilityRecord,
    CompatibilityStatus,
    DisclosureLevel,
    LoadedReference,
    LoadedScript,
    LoadObservation,
    LoadResult,
    ObservationStatus,
    PackageFile,
    Phase3Limits,
    TrustLevel,
)
from .phase3_paths import (
    PathSafetyError,
    bounded_file_metadata,
    digest_bytes,
    is_metadata_only_surface,
    is_sensitive_relative_path,
    read_bounded_file,
)


class LoaderError(ValueError):
    """Raised when a requested disclosure level is not representable safely."""


_LEVELS = (
    DisclosureLevel.IDENTITY,
    DisclosureLevel.ROUTING_METADATA,
    DisclosureLevel.INSTRUCTION_KERNEL,
    DisclosureLevel.SELECTED_REFERENCES,
    DisclosureLevel.APPROVED_PACKAGE,
)
_TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".cfg"}
_SCRIPT_LANGUAGES = {
    ".bash": "shell",
    ".go": "go",
    ".js": "javascript",
    ".kts": "kotlin",
    ".pl": "perl",
    ".ps1": "powershell",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sh": "shell",
    ".ts": "typescript",
}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _at_least(actual: DisclosureLevel, wanted: DisclosureLevel) -> bool:
    return _LEVELS.index(actual) >= _LEVELS.index(wanted)


def _estimate(value: str | None) -> int:
    return max(0, (len(value or "") + 3) // 4)


def _bounded_unique(values: Iterable[str], *, limit: int, label: str) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        if index >= limit:
            raise LoaderError(f"{label} count bound exceeded")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _bounded_records(
    values: Iterable[CapabilityRecord], *, limit: int
) -> tuple[CapabilityRecord, ...]:
    result: list[CapabilityRecord] = []
    for index, value in enumerate(values):
        if index >= limit:
            raise LoaderError("record count bound exceeded")
        result.append(value)
    return tuple(result)


class SafeCapabilityLoader:
    """Read bounded declarative text and inventory metadata; never execute it."""

    def __init__(
        self, limits: Phase3Limits | None = None, *, observed_at: str | None = None
    ) -> None:
        self.limits = limits or Phase3Limits()
        self.observed_at = observed_at or _now()

    def _identity(self, record: CapabilityRecord) -> dict[str, str]:
        return {
            "capability_id": record.capability_id,
            "display_name": record.display_name,
            "version": record.version,
            "kind": record.kind.value,
            "scope": record.scope.value,
            "content_hash": record.content_hash,
            "trust": record.trust.level.value,
            "compatibility": record.compatibility.status.value,
        }

    def _routing_metadata(self, record: CapabilityRecord) -> dict[str, object]:
        return {
            "description": record.description,
            "activates_when": record.activates_when,
            "do_not_activate_when": record.do_not_activate_when,
            "domains": record.manifest.domains,
            "dependencies": record.dependencies,
            "conflicts": record.conflicts,
            "tools": record.manifest.tools,
            "providers": record.manifest.providers,
            "references": record.manifest.references,
            "load_eligibility": record.load_eligibility,
        }

    def _load_references(
        self,
        record: CapabilityRecord,
        selected: Iterable[str],
        warnings: list[str],
        approved: frozenset[str],
    ) -> tuple[LoadedReference, ...]:
        loaded: list[LoadedReference] = []
        total = 0
        seen: set[str] = set()
        for index, relative in enumerate(selected):
            if index >= self.limits.max_reference_files:
                warnings.append("reference file count bound reached")
                break
            if not isinstance(relative, str) or not relative or "\x00" in relative:
                warnings.append("reference path is invalid")
                continue
            if relative in seen:
                continue
            seen.add(relative)
            if relative not in approved:
                warnings.append(f"reference is not approved by package inventory: {relative}")
                continue
            normalized_relative = relative.replace("\\", "/")
            if len(PurePosixPath(normalized_relative).parts) > self.limits.max_reference_depth:
                warnings.append("reference depth bound reached")
                continue
            suffix = (
                normalized_relative.rsplit(".", 1)[-1].casefold()
                if "." in normalized_relative
                else ""
            )
            try:
                metadata_only = (
                    is_sensitive_relative_path(relative)
                    or is_metadata_only_surface(relative)
                    or f".{suffix}" not in _TEXT_SUFFIXES
                )
            except PathSafetyError:
                metadata_only = False
            if metadata_only:
                try:
                    size_bytes, _ = bounded_file_metadata(record.path, relative)
                except PathSafetyError as exc:
                    warnings.append(
                        f"reference blocked outside package: {relative}: {str(exc)[:160]}"
                    )
                    continue
                total += size_bytes
                if total > self.limits.max_reference_bytes:
                    warnings.append("reference byte bound reached")
                    break
                reference_hash = "sha256:unavailable-metadata"
                if not is_sensitive_relative_path(relative):
                    try:
                        reference_hash = digest_bytes(
                            read_bounded_file(
                                record.path,
                                relative,
                                max_bytes=self.limits.max_reference_bytes,
                            )
                        )
                    except PathSafetyError as exc:
                        warnings.append(
                            f"reference metadata unavailable: {relative}: {str(exc)[:160]}"
                        )
                        continue
                loaded.append(
                    LoadedReference(
                        relative,
                        size_bytes,
                        reference_hash,
                        None,
                        binary=True,
                    )
                )
                continue
            try:
                payload = read_bounded_file(
                    record.path,
                    relative,
                    max_bytes=self.limits.max_reference_bytes,
                )
            except PathSafetyError as exc:
                warnings.append(f"reference blocked outside package: {relative}: {str(exc)[:160]}")
                continue
            total += len(payload)
            if total > self.limits.max_reference_bytes:
                warnings.append("reference byte bound reached")
                break
            if f".{suffix}" not in _TEXT_SUFFIXES:
                loaded.append(
                    LoadedReference(
                        relative, len(payload), digest_bytes(payload), None, binary=True
                    )
                )
                continue
            try:
                content = payload.decode("utf-8")
            except UnicodeDecodeError:
                loaded.append(
                    LoadedReference(
                        relative, len(payload), digest_bytes(payload), None, binary=True
                    )
                )
                continue
            loaded.append(
                LoadedReference(
                    relative, len(payload), digest_bytes(payload), content, binary=False
                )
            )
        return tuple(loaded)

    def _scripts(self, record: CapabilityRecord) -> tuple[LoadedScript, ...]:
        by_path = {item.relative_path: item for item in record.files}
        return tuple(
            LoadedScript(
                relative,
                by_path[relative].size_bytes if relative in by_path else 0,
                by_path[relative].sha256 if relative in by_path else "sha256:" + "0" * 64,
                declared_purpose=None,
                language=_SCRIPT_LANGUAGES.get(PurePosixPath(relative).suffix.casefold()),
            )
            for relative in record.scripts[: self.limits.max_files_per_capability]
        )

    def load(
        self,
        record: CapabilityRecord,
        level: DisclosureLevel,
        *,
        selected_references: Iterable[str] | None = None,
    ) -> LoadResult:
        if not isinstance(level, DisclosureLevel):
            raise LoaderError("disclosure level is invalid")
        warnings: list[str] = []
        identity = self._identity(record)
        routing = (
            self._routing_metadata(record)
            if _at_least(level, DisclosureLevel.ROUTING_METADATA)
            else {}
        )
        fresh = True
        if record.status not in {
            CapabilityLifecycle.REJECTED,
            CapabilityLifecycle.INCOMPATIBLE,
            CapabilityLifecycle.STALE,
            CapabilityLifecycle.AMBIGUOUS,
        }:
            fresh, freshness_reason = revalidate_capability(record, self.limits)
            if not fresh:
                warnings.append(f"capability snapshot is stale: {freshness_reason}")
        blocked_record = (
            not fresh
            or record.status
            in {
                CapabilityLifecycle.REJECTED,
                CapabilityLifecycle.INCOMPATIBLE,
                CapabilityLifecycle.STALE,
                CapabilityLifecycle.AMBIGUOUS,
            }
            or record.trust.level is TrustLevel.REJECTED
            or record.compatibility.status is CompatibilityStatus.INCOMPATIBLE
            or record.load_eligibility.startswith("BLOCKED")
        )
        if blocked_record:
            warnings.append("capability is blocked; only already-observed metadata is exposed")
        instruction: str | None = None
        references: tuple[LoadedReference, ...] = ()
        scripts: tuple[LoadedScript, ...] = ()
        package_files: tuple[PackageFile, ...] = ()
        if not blocked_record and _at_least(level, DisclosureLevel.INSTRUCTION_KERNEL):
            if record.skill_md is None:
                warnings.append("instruction kernel is unavailable; package has no SKILL.md")
            else:
                try:
                    payload = read_bounded_file(
                        record.path,
                        record.skill_md,
                        max_bytes=self.limits.max_skill_bytes,
                    )
                    instruction = payload.decode("utf-8")
                except (PathSafetyError, UnicodeDecodeError) as exc:
                    warnings.append(f"instruction kernel blocked: {str(exc)[:160]}")
        if not blocked_record and _at_least(level, DisclosureLevel.SELECTED_REFERENCES):
            requested = (
                selected_references
                if selected_references is not None
                else record.manifest.references or record.references
            )
            approved = frozenset(
                (*record.references, *record.manifest.references, *record.scripts, *record.assets)
            )
            references = self._load_references(record, requested, warnings, approved)
        if _at_least(level, DisclosureLevel.APPROVED_PACKAGE):
            package_files = record.files
            scripts = self._scripts(record)
            if scripts:
                warnings.append(
                    "script files are inventory-only and execution is disabled in Phase 3"
                )
            if record.manifest.providers:
                warnings.append("provider metadata is inventory-only and execution is deferred")
        serialized_metadata = json.dumps(routing, sort_keys=True, default=str)
        token_estimate = _estimate(json.dumps(identity, sort_keys=True)) + _estimate(
            serialized_metadata
        )
        token_estimate += _estimate(instruction)
        token_estimate += sum(_estimate(item.content) for item in references)
        host_load = LoadObservation(
            record.capability_id,
            ObservationStatus.UNAVAILABLE,
            False,
            "the Phase 3 adapter has no observable host-load signal",
            self.observed_at,
        )
        return LoadResult(
            record.capability_id,
            level,
            identity,
            routing,
            instruction,
            references,
            scripts,
            package_files,
            token_estimate,
            not blocked_record and instruction is not None,
            False,
            host_load,
            tuple(warnings),
        )

    def plan(
        self,
        requested: Iterable[str],
        records: Iterable[CapabilityRecord],
        level: DisclosureLevel,
        *,
        blockers: Iterable[str] = (),
        host_load_observable: bool = False,
    ) -> CapabilityLoadPlan:
        requested_value = _bounded_unique(
            requested, limit=self.limits.max_capabilities, label="requested"
        )
        record_values = _bounded_records(records, limit=self.limits.max_capabilities)
        blocker_values = _bounded_unique(
            blockers, limit=self.limits.max_capabilities, label="blocker"
        )
        statuses: dict[str, CapabilityLifecycle] = {}
        selected: list[str] = []
        tokens = 0
        for record in record_values:
            if blocker_values or record.load_eligibility.startswith("BLOCKED"):
                statuses[record.capability_id] = CapabilityLifecycle.BLOCKED
                continue
            result = self.load(record, level)
            if any(
                warning.startswith("capability snapshot is stale:") for warning in result.warnings
            ):
                statuses[record.capability_id] = CapabilityLifecycle.BLOCKED
                continue
            if _at_least(level, DisclosureLevel.INSTRUCTION_KERNEL) and not result.context_prepared:
                statuses[record.capability_id] = CapabilityLifecycle.BLOCKED
                continue
            selected.append(record.capability_id)
            tokens += result.context_tokens_estimate
            statuses[record.capability_id] = (
                CapabilityLifecycle.SELECTED
                if level is DisclosureLevel.IDENTITY
                else CapabilityLifecycle.LOAD_PLANNED
                if level is DisclosureLevel.ROUTING_METADATA
                else CapabilityLifecycle.CONTEXT_PREPARED
            )
        if blocker_values:
            statuses.update({item: CapabilityLifecycle.BLOCKED for item in requested_value})
        fingerprint_source = "|".join(
            f"{item.capability_id}:{item.content_hash}:{level.value}" for item in record_values
        )
        fingerprint = digest_bytes(fingerprint_source.encode("utf-8"))
        return CapabilityLoadPlan(
            requested_value,
            tuple(selected),
            level,
            tokens,
            bool(selected)
            and not blocker_values
            and _at_least(level, DisclosureLevel.INSTRUCTION_KERNEL),
            host_load_observable,
            False,
            statuses,
            blocker_values,
            fingerprint,
        )
