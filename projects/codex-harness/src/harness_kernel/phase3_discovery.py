"""Bounded discovery and manifest synthesis for local capability packages."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .phase3_models import (
    CapabilityInventory,
    CapabilityKind,
    CapabilityLifecycle,
    CapabilityRecord,
    CapabilityRoot,
    CompatibilityAssessment,
    FieldProvenance,
    ObservationStatus,
    ObservedCapabilityManifest,
    PackageFile,
    ParseStatus,
    Phase3Limits,
    ProvenanceRecord,
    RootScope,
    WalkResult,
)
from .phase3_parser import parse_skill_bytes
from .phase3_paths import (
    PathSafetyError,
    bounded_file_metadata,
    bounded_walk,
    digest_bytes,
    is_sensitive_relative_path,
    read_bounded_file,
)
from .phase3_trust import assess_compatibility, assess_trust, stale_for_fingerprint


class DiscoveryError(ValueError):
    """Raised when discovery input is invalid or exceeds safe bounds."""


_VERSION_IDENTIFIER = r"(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
_VERSION = re.compile(
    rf"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    rf"(?:-{_VERSION_IDENTIFIER}(?:\.{_VERSION_IDENTIFIER})*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")
_MAX_VERSION_LENGTH = 256
_MAX_JSON_NESTING = 64
_TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".cfg"}
_SENSITIVE_FIELD = re.compile(
    r"(?:secret|token|password|credential|authorization|api[_-]?key|private[_-]?key)", re.I
)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _is_semver(value: str) -> bool:
    return len(value) <= _MAX_VERSION_LENGTH and _VERSION.fullmatch(value) is not None


def _json_nesting_exceeds(payload: bytes) -> bool:
    depth = 0
    escaped = False
    in_string = False
    for byte in payload:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                in_string = False
            continue
        if byte == 34:
            in_string = True
        elif byte in {91, 123}:
            depth += 1
            if depth > _MAX_JSON_NESTING:
                return True
        elif byte in {93, 125}:
            depth = max(0, depth - 1)
    return False


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, list | tuple):
        return ()
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item and item not in result:
            result.append(item[:400])
    return tuple(result[:64])


def _nested(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    return value if isinstance(value, Mapping) else {}


def _safe_unknown_value(key: str, value: object) -> str:
    if _SENSITIVE_FIELD.search(key):
        return "<REDACTED>"
    if isinstance(value, Mapping | list | tuple | set | frozenset):
        return "<UNTRUSTED_METADATA>"
    return str(value)[:400]


def _claim(data: Mapping[str, Any], key: str, limit: int) -> str | None:
    value = data.get(key)
    return value[:limit] if isinstance(value, str) else None


def _load_json(payload: bytes) -> tuple[dict[str, Any] | None, str | None]:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        seen: set[str] = set()
        for key, value in values:
            if key in seen:
                raise ValueError("duplicate JSON object key")
            seen.add(key)
            result[key] = value
        return result

    if _json_nesting_exceeds(payload):
        return None, "manifest JSON nesting exceeds its bound"
    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")),
        )
    except (UnicodeDecodeError, TypeError, ValueError, RecursionError) as exc:
        return None, str(exc)[:200]
    if not isinstance(parsed, dict):
        return None, "manifest JSON must be an object"
    return parsed, None


def _package_digest(files: Iterable[PackageFile]) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda value: value.relative_path):
        digest.update(item.relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.sha256.encode("ascii"))
        if item.observation is not ObservationStatus.OBSERVED:
            digest.update(f"size={item.size_bytes}".encode("ascii"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def _validate_native_manifest(data: Mapping[str, Any]) -> tuple[str, ...]:
    """Validate the small native envelope before treating JSON as authoritative."""

    errors: list[str] = []
    for field in ("schema_version", "capability_id", "display_name", "version"):
        if field not in data:
            errors.append(f"native manifest is missing {field}")
    schema = data.get("schema_version")
    if schema not in {"CM-1", "P3-CM-1"}:
        errors.append("native manifest schema_version is unsupported")
    capability_id = data.get("capability_id")
    if not isinstance(capability_id, str) or not _ID.fullmatch(capability_id):
        errors.append("native manifest capability_id is invalid")
    version = data.get("version")
    if not isinstance(version, str) or not _is_semver(version):
        errors.append("native manifest version is invalid")
    for field in (
        "scope",
        "contracts",
        "composition",
        "dependencies",
        "compatibility",
        "provenance",
        "security",
    ):
        if field in data and not isinstance(data[field], Mapping):
            errors.append(f"native manifest {field} must be an object")
    scope = data.get("scope")
    if (
        isinstance(scope, Mapping)
        and _strings(scope.get("activates_when"))
        and not _strings(scope.get("do_not_activate_when"))
    ):
        errors.append("native manifest do-not-activate metadata is missing")
    return tuple(errors)


def _field_map(source: str, values: Mapping[str, str]) -> tuple[FieldProvenance, ...]:
    return tuple(
        FieldProvenance(item, source, source, confidence)
        for item, confidence in sorted(values.items())
    )


def _manifest_from_data(
    data: Mapping[str, Any],
    *,
    package_name: str,
    content_kind: CapabilityKind,
    source: str,
    skill_id: str | None,
    skill_description: str,
    skill_values: Mapping[str, str],
    skill_lists: Mapping[str, tuple[str, ...]],
    skill_unknown_fields: tuple[tuple[str, str], ...],
    skill_errors: tuple[str, ...],
) -> tuple[ObservedCapabilityManifest, tuple[str, ...]]:
    scope = _nested(data, "scope")
    dependencies = _nested(data, "dependencies")
    composition = _nested(data, "composition")
    compatibility = _nested(data, "compatibility")
    capability_id = str(data.get("capability_id") or skill_id or package_name)
    display_name = str(data.get("display_name") or skill_values.get("name") or capability_id)
    version_value = str(data.get("version") or skill_values.get("version") or "0.1.0")
    errors = list(skill_errors)
    if not _ID.fullmatch(capability_id):
        errors.append("capability ID is invalid")
        capability_id = "invalid-package"
    if not _is_semver(version_value):
        errors.append("manifest version is not semantic-version shaped")
        version_value = "0.1.0"
    if data:
        declared = {
            "capability_id": "capability_id",
            "display_name": "display_name",
            "description": "description",
            "version": "version",
            "primary_type": "primary_type",
            "scope": "scope",
            "dependencies": "dependencies",
            "composition": "composition",
            "compatibility": "compatibility",
        }
        provenance = {key: ObservationStatus.OBSERVED.value for key in data if key in declared}
        provenance.update(
            {key: ObservationStatus.UNKNOWN.value for key in data if key not in declared}
        )
        field_details = _field_map("manifest.json", provenance)
        description = str(data.get("description") or skill_description)[:2000]
        activates = _strings(scope.get("activates_when"))
        blocked = _strings(scope.get("do_not_activate_when"))
        domains = _strings(scope.get("domains"))
        deps = _strings(dependencies.get("capabilities"))
        tools = _strings(dependencies.get("tools"))
        providers = _strings(dependencies.get("providers"))
        references = _strings(dependencies.get("references"))
        conflicts = _strings(composition.get("conflicts_with"))
        platform_limits = _strings(compatibility.get("platform_limits"))
        contracts = _nested(data, "contracts")
        gates = _strings(contracts.get("gates"))
        stop_conditions = _strings(contracts.get("stop_conditions"))
        primary_type = str(data.get("primary_type") or "SPECIALIST").upper()
        unknown_fields = tuple(
            (key, _safe_unknown_value(key, value))
            for key, value in data.items()
            if key not in declared
        )
        kind = content_kind
    else:
        provenance = {"name": ObservationStatus.OBSERVED.value} if skill_id else {}
        provenance.update(
            {key: ObservationStatus.OBSERVED.value for key in skill_values if key != "name"}
        )
        provenance.update({key: ObservationStatus.UNKNOWN.value for key, _ in skill_unknown_fields})
        field_details = _field_map(source, provenance)
        description = skill_description[:2000]
        activates = _strings(skill_lists.get("activates_when"))
        blocked = _strings(skill_lists.get("do_not_activate_when"))
        domains = _strings(skill_lists.get("domains"))
        deps = _strings(skill_lists.get("dependencies"))
        tools = _strings(skill_lists.get("tools"))
        providers = _strings(skill_lists.get("providers"))
        references = _strings(skill_lists.get("references"))
        conflicts = _strings(skill_lists.get("conflicts"))
        platform_limits = _strings(skill_lists.get("platform_limits"))
        gates = _strings(skill_lists.get("gates"))
        stop_conditions = _strings(skill_lists.get("stop_conditions"))
        primary_type = str(skill_values.get("primary_type", "SPECIALIST")).upper()
        unknown_fields = tuple(
            (key, _safe_unknown_value(key, value)) for key, value in skill_unknown_fields
        )
        kind = content_kind
    if not capability_id:
        errors.append("capability ID is missing")
    manifest = ObservedCapabilityManifest(
        "P3-CM-1",
        capability_id,
        display_name,
        version_value,
        kind,
        description,
        primary_type,
        activates,
        blocked,
        domains,
        deps,
        tools,
        providers,
        references,
        conflicts,
        platform_limits,
        {item.field: str(item.confidence) for item in field_details},
        field_details,
        unknown_fields,
        gates,
        stop_conditions,
    )
    return manifest, tuple(errors)


def _relative_categories(files: Iterable[str]) -> dict[str, tuple[str, ...]]:
    values = tuple(sorted(files))
    return {
        key: tuple(item for item in values if item == key or item.startswith(f"{key}/"))
        for key in (
            "agents",
            "references",
            "scripts",
            "evals",
            "benchmarks",
            "rubrics",
            "templates",
            "examples",
            "assets",
        )
    }


class CapabilityDiscovery:
    """Inspect explicit roots and return declarative package records only."""

    def __init__(
        self, limits: Phase3Limits | None = None, *, observed_at: str | None = None
    ) -> None:
        self.limits = limits or Phase3Limits()
        self.observed_at = observed_at or _now()

    def _package_paths(
        self, root: CapabilityRoot, walked: WalkResult | None = None
    ) -> tuple[tuple[Path, str | None, str | None], ...]:
        base = Path(root.canonical_path or root.path)
        walk = walked if walked is not None else bounded_walk(root, self.limits)
        packages: dict[str, tuple[str | None, str | None]] = {}
        for relative in walk.files:
            path = Path(relative)
            if path.name not in {"SKILL.md", "manifest.json"}:
                continue
            package = path.parent.as_posix()
            skill = relative if path.name == "SKILL.md" else None
            manifest = relative if path.name == "manifest.json" else None
            old_skill, old_manifest = packages.get(package, (None, None))
            packages[package] = (skill or old_skill, manifest or old_manifest)
        return tuple(
            (
                base / relative,
                "SKILL.md" if values[0] else None,
                "manifest.json" if values[1] else None,
            )
            for relative, values in sorted(packages.items())
        )

    def _inspect_package(
        self,
        root: CapabilityRoot,
        package: Path,
        skill_relative: str | None,
        manifest_relative: str | None,
        *,
        walked: WalkResult | None = None,
    ) -> CapabilityRecord:
        walk = walked if walked is not None else bounded_walk(package, self.limits)
        if len(walk.files) > self.limits.max_files_per_capability:
            raise DiscoveryError("capability file count bound exceeded")
        file_records: list[PackageFile] = []
        payloads: dict[str, bytes] = {}
        max_file = max(
            self.limits.max_skill_bytes,
            self.limits.max_manifest_bytes,
            self.limits.max_reference_bytes,
        )
        errors = list(walk.errors) + [
            f"{relative}: unsafe symlink or alias" for relative in walk.unsafe_paths
        ]
        for relative in walk.files:
            suffix = Path(relative).suffix.casefold()
            metadata_only = (
                is_sensitive_relative_path(relative)
                or relative.startswith(("scripts/", "assets/"))
                or not (suffix in _TEXT_SUFFIXES or Path(relative).name in {"SKILL.md", "LICENSE"})
            )
            if metadata_only:
                try:
                    size_bytes, executable = bounded_file_metadata(package, relative)
                except PathSafetyError as exc:
                    errors.append(f"{relative}: {str(exc)[:160]}")
                    continue
                if size_bytes > max_file:
                    errors.append(f"{relative}: metadata file exceeds its bound")
                    continue
                file_records.append(
                    PackageFile(
                        relative,
                        size_bytes,
                        "sha256:unavailable-metadata",
                        "sensitive_metadata"
                        if is_sensitive_relative_path(relative)
                        else "metadata_only",
                        executable,
                        ObservationStatus.UNAVAILABLE,
                    )
                )
                continue
            try:
                _, executable = bounded_file_metadata(package, relative)
                payload = read_bounded_file(package, relative, max_bytes=max_file)
                digest = digest_bytes(payload)
            except PathSafetyError as exc:
                errors.append(f"{relative}: {str(exc)[:160]}")
                continue
            payloads[relative] = payload if relative in {skill_relative, manifest_relative} else b""
            kind = (
                "text"
                if suffix in _TEXT_SUFFIXES or Path(relative).name in {"SKILL.md", "LICENSE"}
                else "binary"
            )
            file_records.append(
                PackageFile(
                    relative,
                    len(payload),
                    digest,
                    kind,
                    executable,
                )
            )
        files = tuple(sorted(file_records, key=lambda item: item.relative_path))
        content_hash = _package_digest(files)
        skill_doc = None
        skill_error: tuple[str, ...] = ()
        if skill_relative is not None and skill_relative in payloads:
            skill_doc = parse_skill_bytes(payloads[skill_relative], source=skill_relative)
            skill_error = skill_doc.errors
        native: dict[str, Any] | None = None
        native_error: str | None = None
        native_errors: tuple[str, ...] = ()
        if manifest_relative is not None and manifest_relative in payloads:
            native, native_error = _load_json(payloads[manifest_relative])
            if native_error:
                errors.append(f"manifest.json: {native_error}")
        package_name = package.name
        skill_id = skill_doc.capability_id if skill_doc is not None else None
        skill_values = skill_doc.front_matter if skill_doc is not None else {}
        skill_lists: dict[str, tuple[str, ...]] = {}
        if skill_doc is not None:
            for key in (
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
            ):
                value = getattr(skill_doc, key)
                skill_lists[key] = tuple(value)
        if native is not None:
            native_errors = _validate_native_manifest(native)
            errors.extend(native_errors)
            kind = CapabilityKind.NATIVE
        elif skill_doc is not None and skill_doc.status is ParseStatus.LEGACY:
            kind = CapabilityKind.LEGACY
        elif skill_doc is not None and skill_doc.status is ParseStatus.VALID:
            kind = CapabilityKind.SYNTHESIZED
        else:
            kind = CapabilityKind.INVALID
        if native_error:
            kind = CapabilityKind.INVALID
        if native is not None and native_errors:
            kind = CapabilityKind.INVALID
        manifest, manifest_errors = _manifest_from_data(
            native or {},
            package_name=package_name,
            content_kind=kind,
            source=skill_relative or manifest_relative or "package",
            skill_id=skill_id,
            skill_description=skill_doc.description if skill_doc is not None else "",
            skill_values=skill_values,
            skill_lists=skill_lists,
            skill_unknown_fields=skill_doc.unknown_fields if skill_doc is not None else (),
            skill_errors=skill_error,
        )
        errors.extend(manifest_errors)
        if manifest.capability_id == "":
            kind = CapabilityKind.INVALID
        if errors or manifest.kind is CapabilityKind.INVALID:
            lifecycle = CapabilityLifecycle.REJECTED
            eligibility = "BLOCKED_INVALID_METADATA"
        else:
            lifecycle = CapabilityLifecycle.INSPECTED
            eligibility = "ELIGIBLE_DECLARATIVE_METADATA_ONLY"
        categories = _relative_categories(item.relative_path for item in files)
        scope = root.scope if isinstance(root.scope, RootScope) else RootScope.UNKNOWN
        source_repository = f"local://{root.root_id}"
        native_provenance = _nested(native or {}, "provenance")
        provenance = ProvenanceRecord(
            "LOCAL" if scope is not RootScope.EXTERNAL else "THIRD_PARTY",
            (skill_relative or manifest_relative or package_name,),
            source_repository,
            _claim(native_provenance, "upstream", 300),
            _claim(native_provenance, "forked_from", 300),
            _claim(native_provenance, "tag", 120),
            _claim(native_provenance, "commit", 120),
            kind is not CapabilityKind.NATIVE,
            content_hash,
            scope,
            root.authority,
            root.confidence,
            self.observed_at,
            license=(
                str(native.get("license"))
                if native is not None and isinstance(native.get("license"), str)
                else None
            ),
            aliases=_strings(native_provenance.get("aliases")),
        )
        trust = assess_trust(
            scope,
            content_hash=content_hash,
            source_repository=source_repository,
            source_type=provenance.source_type,
            rejected=lifecycle is CapabilityLifecycle.REJECTED,
        )
        compatibility: CompatibilityAssessment = assess_compatibility(manifest)
        if compatibility.status.value == "INCOMPATIBLE":
            lifecycle = CapabilityLifecycle.INCOMPATIBLE
            eligibility = "BLOCKED_INCOMPATIBLE_HOST"
        return CapabilityRecord(
            manifest.capability_id,
            manifest.display_name,
            str(package),
            root.root_id,
            scope,
            skill_relative,
            manifest_relative,
            files,
            tuple(
                sorted(
                    {
                        str(Path(item.relative_path).parent)
                        for item in files
                        if "/" in item.relative_path
                    }
                )
            ),
            categories["agents"],
            categories["references"],
            categories["scripts"],
            categories["evals"],
            categories["benchmarks"],
            categories["rubrics"],
            categories["templates"],
            categories["examples"],
            categories["assets"],
            manifest.version,
            lifecycle,
            kind,
            provenance,
            content_hash,
            compatibility,
            trust,
            eligibility,
            manifest,
            manifest.description,
            manifest.activates_when,
            manifest.do_not_activate_when,
            manifest.dependencies,
            manifest.conflicts,
            manifest.gates,
            manifest.stop_conditions,
        )

    def scan(
        self,
        roots: Iterable[CapabilityRoot],
        *,
        expected_fingerprint: str | None = None,
    ) -> CapabilityInventory:
        roots_value_list: list[CapabilityRoot] = []
        for index, root in enumerate(roots):
            if index >= self.limits.max_roots:
                raise DiscoveryError("root count bound exceeded")
            roots_value_list.append(root)
        roots_value = tuple(roots_value_list)
        if len(roots_value) > self.limits.max_roots:
            raise DiscoveryError("root count bound exceeded")
        seen_paths: set[str] = set()
        capabilities: list[CapabilityRecord] = []
        errors: list[str] = []
        accepted_roots: list[CapabilityRoot] = []
        scanned_files = 0
        scanned_bytes = 0
        scan_exhausted = False
        for root in roots_value:
            if scan_exhausted:
                break
            canonical = root.canonical_path or root.path
            if canonical in seen_paths:
                errors.append(f"duplicate canonical root: {root.root_id}")
                continue
            seen_paths.add(canonical)
            accepted_roots.append(root)
            if not root.readable or not Path(canonical).exists():
                errors.append(f"{root.root_id}: root unavailable")
                continue
            try:
                root_walk = bounded_walk(root, self.limits)
                scanned_files += len(root_walk.files)
                scanned_bytes += root_walk.total_bytes
                if (
                    scanned_files > self.limits.max_total_files
                    or scanned_bytes > self.limits.max_total_bytes
                ):
                    raise DiscoveryError("scan-wide file or byte bound exceeded")
                errors.extend(
                    f"{root.root_id}/{relative}: unsafe symlink or alias"
                    for relative in root_walk.unsafe_paths
                )
                errors.extend(f"{root.root_id}/{message}" for message in root_walk.errors)
                package_paths = self._package_paths(root, root_walk)
            except DiscoveryError as exc:
                errors.append(f"{root.root_id}: {str(exc)[:200]}")
                if "scan-wide" in str(exc):
                    scan_exhausted = True
                continue
            except PathSafetyError as exc:
                errors.append(f"{root.root_id}: {str(exc)[:200]}")
                continue
            for package, skill_relative, manifest_relative in package_paths:
                if len(capabilities) >= self.limits.max_capabilities:
                    raise DiscoveryError("capability count bound exceeded")
                try:
                    package_walk = bounded_walk(package, self.limits)
                    scanned_files += len(package_walk.files)
                    scanned_bytes += package_walk.total_bytes
                    if (
                        scanned_files > self.limits.max_total_files
                        or scanned_bytes > self.limits.max_total_bytes
                    ):
                        raise DiscoveryError("scan-wide file or byte bound exceeded")
                    capabilities.append(
                        self._inspect_package(
                            root,
                            package,
                            skill_relative,
                            manifest_relative,
                            walked=package_walk,
                        )
                    )
                except DiscoveryError as exc:
                    errors.append(f"{root.root_id}/{package.name}: {str(exc)[:200]}")
                    if "scan-wide" in str(exc):
                        scan_exhausted = True
                        break
                except (PathSafetyError, OSError) as exc:
                    errors.append(f"{root.root_id}/{package.name}: {str(exc)[:200]}")
        identity = "\n".join(
            f"{item.capability_id}|{item.version}|{item.content_hash}|{item.root_id}"
            for item in sorted(
                capabilities, key=lambda value: (value.capability_id, value.version, value.root_id)
            )
        )
        fingerprint = digest_bytes(identity.encode("utf-8"))
        final_capabilities = tuple(
            replace(
                item,
                status=CapabilityLifecycle.STALE,
                load_eligibility="BLOCKED_STALE_FINGERPRINT",
            )
            if expected_fingerprint is not None
            and stale_for_fingerprint(expected_fingerprint, fingerprint)
            and item.status not in {CapabilityLifecycle.REJECTED, CapabilityLifecycle.INCOMPATIBLE}
            else item
            for item in capabilities
        )
        if expected_fingerprint is not None and stale_for_fingerprint(
            expected_fingerprint, fingerprint
        ):
            errors.append("inventory fingerprint is stale relative to the expected snapshot")
        return CapabilityInventory(
            tuple(accepted_roots),
            tuple(
                sorted(
                    final_capabilities,
                    key=lambda item: (item.capability_id, item.version, item.root_id, item.path),
                )
            ),
            tuple(errors),
            self.observed_at,
            fingerprint,
        )
