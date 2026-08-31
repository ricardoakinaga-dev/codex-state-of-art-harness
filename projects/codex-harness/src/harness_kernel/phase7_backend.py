"""Bounded contracts for the project-local Phase 7 backend capability.

The Phase 7 package is a native, declarative capability.  This module never
loads or executes package code.  It only authenticates the package identity,
checks bounded metadata and compares a workspace snapshot with a later
filesystem observation.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from .phase3_models import Phase3Limits
from .phase3_paths import (
    PathSafetyError,
    bounded_file_metadata,
    bounded_walk,
    digest_bytes,
    is_metadata_only_surface,
    is_sensitive_relative_path,
    read_bounded_file,
)


class BackendPackageContractError(ValueError):
    """Raised when a package or workspace cannot be safely authenticated."""


BACKEND_CAPABILITY_ID = "backend-engineering-vnext"
BACKEND_PACKAGE_VERSION = "0.1.0"
BACKEND_PRIMARY_TYPE = "SPECIALIST"
BACKEND_ROLE = "SPECIALIST"
BACKEND_FORBIDDEN_BOUNDARIES = (
    "shell",
    "network",
    "mcp",
    "provider",
    "credential",
    "credentials",
)

_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")
_VERSION_PART = r"(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
_VERSION_PATTERN = re.compile(
    rf"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    rf"(?:-{_VERSION_PART}(?:\.{_VERSION_PART})*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_MAX_JSON_DEPTH = 64
_MAX_MANIFEST_BYTES = 256 * 1024
_MAX_METADATA_BYTES = 512 * 1024
_MAX_PACKAGE_FILES = 256
_MAX_PACKAGE_BYTES = 16 * 1024 * 1024
_MAX_SCENARIOS = 128
_MAX_BENCHMARK_RECORDS = 16
_MAX_PROCEDURES = 32
_MAX_EVIDENCE_RECORDS = 256
_ZERO_DIGEST = "sha256:" + "0" * 64


def _json_nesting_exceeds(payload: bytes, *, max_depth: int = _MAX_JSON_DEPTH) -> bool:
    """Bound JSON structure before parsing untrusted package metadata."""

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
            if depth > max_depth:
                return True
        elif byte in {93, 125}:
            depth = max(0, depth - 1)
    return False


def _reject_non_finite_json(value: str) -> object:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _strict_json(payload: bytes, *, label: str) -> Mapping[str, object]:
    if len(payload) > _MAX_METADATA_BYTES:
        raise BackendPackageContractError(f"{label} exceeds its bounded size")
    if _json_nesting_exceeds(payload):
        raise BackendPackageContractError(f"{label} exceeds the JSON nesting bound")

    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise BackendPackageContractError(f"{label} contains a duplicate JSON key")
            result[key] = value
        return result

    try:
        parsed = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=_reject_non_finite_json,
        )
    except BackendPackageContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise BackendPackageContractError(f"{label} is invalid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise BackendPackageContractError(f"{label} must contain an object")
    return parsed


def _required_text(value: object, field: str, *, maximum: int = 8_192) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > maximum:
        raise BackendPackageContractError(f"{field} is invalid")
    return value


def _bounded_strings(value: object, field: str, *, maximum: int = 256) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise BackendPackageContractError(f"{field} must be a list")
    values: list[str] = []
    for item in value:
        candidate = _required_text(item, f"{field} item", maximum=maximum)
        if candidate not in values:
            values.append(candidate)
    return tuple(values)


def _as_mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _claim_digest(value: object) -> str | None:
    if isinstance(value, str) and _DIGEST_PATTERN.fullmatch(value):
        return value
    return None


def _safe_path_parts(path: str, *, field: str) -> tuple[str, ...]:
    candidate = _required_text(path, field, maximum=4_096).replace("\\", "/")
    if candidate.startswith("/"):
        raise BackendPackageContractError(f"{field} must be relative")
    parts = tuple(PurePosixPath(candidate).parts)
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise BackendPackageContractError(f"{field} contains traversal")
    return parts


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            return True
        if stat.S_ISLNK(metadata.st_mode):
            return True
    return False


def _safe_package_path(package_path: str | Path) -> Path:
    raw = Path(package_path)
    if not raw.is_absolute():
        raise BackendPackageContractError("package path must be absolute")
    if "\x00" in str(raw) or any(part in {"", ".", ".."} for part in raw.parts[1:]):
        raise BackendPackageContractError("package path contains traversal")
    if _has_symlink_component(raw):
        raise BackendPackageContractError("package path contains a symlink")
    try:
        metadata = raw.lstat()
    except FileNotFoundError as exc:
        raise BackendPackageContractError("package path is missing") from exc
    except OSError as exc:
        raise BackendPackageContractError("package path cannot be inspected") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise BackendPackageContractError("package path is a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise BackendPackageContractError("package path is not a directory")
    try:
        resolved = raw.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BackendPackageContractError("package path cannot be resolved") from exc
    if resolved != raw or _has_symlink_component(resolved):
        raise BackendPackageContractError("package path resolves through a symlink")
    return resolved


def _limits_for_package(limits: Phase3Limits | None) -> Phase3Limits:
    if limits is not None:
        return limits
    return Phase3Limits(
        max_files_per_capability=_MAX_PACKAGE_FILES,
        max_total_files=_MAX_PACKAGE_FILES,
        max_total_bytes=_MAX_PACKAGE_BYTES,
        max_skill_bytes=64 * 1024,
        max_manifest_bytes=_MAX_MANIFEST_BYTES,
        max_reference_bytes=_MAX_METADATA_BYTES,
    )


def _package_files(package: Path, limits: Phase3Limits) -> tuple[tuple[str, int, bool, str], ...]:
    """Return safe file metadata and content digests in Phase 3 order."""

    try:
        walked = bounded_walk(package, limits)
    except (PathSafetyError, OSError) as exc:
        raise BackendPackageContractError("package cannot be walked safely") from exc
    if walked.errors:
        raise BackendPackageContractError(f"package contains an unsafe entry: {walked.errors[0]}")
    if walked.unsafe_paths:
        detail = walked.unsafe_paths[0]
        raise BackendPackageContractError(f"package contains a symlink or alias: {detail}")
    if not walked.files:
        raise BackendPackageContractError("package has no files")
    if len(walked.files) > _MAX_PACKAGE_FILES:
        raise BackendPackageContractError("package file count exceeds its bound")
    max_file_bytes = max(
        limits.max_skill_bytes, limits.max_manifest_bytes, limits.max_reference_bytes
    )
    records: list[tuple[str, int, bool, str]] = []
    for relative in sorted(walked.files):
        _safe_path_parts(relative, field="package file")
        try:
            size_bytes, executable = bounded_file_metadata(package, relative)
            if size_bytes > max_file_bytes:
                raise BackendPackageContractError(f"package file exceeds its bound: {relative}")
            payload = read_bounded_file(
                package,
                relative,
                max_bytes=max_file_bytes,
            )
            confirmation = read_bounded_file(
                package,
                relative,
                max_bytes=max_file_bytes,
            )
            after_size, after_executable = bounded_file_metadata(package, relative)
        except BackendPackageContractError:
            raise
        except (PathSafetyError, OSError) as exc:
            raise BackendPackageContractError(f"package file is unsafe: {relative}") from exc
        if (
            (size_bytes, executable) != (after_size, after_executable)
            or len(payload) != size_bytes
            or confirmation != payload
        ):
            raise BackendPackageContractError(f"package file changed during inspection: {relative}")
        records.append((relative, size_bytes, executable, digest_bytes(payload)))
    return tuple(records)


def _phase3_package_digest(files: tuple[tuple[str, int, bool, str], ...]) -> str:
    """Match Phase 3's digest, including metadata-only observation markers."""

    digest = hashlib.sha256()
    for relative, size_bytes, _executable, file_digest in files:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        suffix = Path(relative).suffix.casefold()
        metadata_only = (
            is_sensitive_relative_path(relative)
            or is_metadata_only_surface(relative)
            or not (
                suffix in {".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".cfg"}
                or Path(relative).name in {"SKILL.md", "LICENSE"}
            )
        )
        if metadata_only:
            digest.update(f"size={size_bytes}".encode("ascii"))
        digest.update(b"\n")
    return "sha256:" + digest.hexdigest()


def package_fingerprint(
    package_path: str | Path,
    *,
    limits: Phase3Limits | None = None,
) -> str:
    """Compute the deterministic native package digest used by Phase 3.

    Every entry is required to be a unique regular file.  Symlinks, hard-link
    aliases, traversal paths, special files and changing files fail closed.
    """

    package = _safe_package_path(package_path)
    return _phase3_package_digest(_package_files(package, _limits_for_package(limits)))


def _read_package_json(package: Path, relative: str, *, max_bytes: int) -> Mapping[str, object]:
    _safe_path_parts(relative, field="package metadata path")
    try:
        payload = read_bounded_file(package, relative, max_bytes=max_bytes)
    except (PathSafetyError, OSError) as exc:
        raise BackendPackageContractError(f"package metadata is unavailable: {relative}") from exc
    return _strict_json(payload, label=relative)


def _check_manifest(manifest: Mapping[str, object]) -> tuple[str, ...]:
    errors: list[str] = []
    required = (
        "schema_version",
        "capability_id",
        "display_name",
        "version",
        "type",
        "role",
        "primary_type",
        "scope",
        "contracts",
        "composition",
        "dependencies",
        "compatibility",
        "provenance",
        "security",
        "trust",
        "status",
        "registry_bridge",
        "metadata_only",
        "execution",
        "read_only",
        "allowed_tools",
        "budgets",
        "quality",
        "execution_policy",
    )
    errors.extend(f"manifest missing {field}" for field in required if field not in manifest)
    if manifest.get("schema_version") not in {"CM-1", "P3-CM-1"}:
        errors.append("manifest schema_version is unsupported")
    if manifest.get("capability_id") != BACKEND_CAPABILITY_ID:
        errors.append("manifest capability_id does not match the native backend package")
    version = manifest.get("version")
    if not isinstance(version, str) or _VERSION_PATTERN.fullmatch(version) is None:
        errors.append("manifest version is invalid")
    if version != BACKEND_PACKAGE_VERSION:
        errors.append("manifest version is not the bound backend package version")
    for field, expected in (
        ("type", BACKEND_PRIMARY_TYPE),
        ("role", BACKEND_ROLE),
        ("primary_type", BACKEND_PRIMARY_TYPE),
    ):
        if manifest.get(field) != expected:
            errors.append(f"manifest {field} is not {expected}")
    scope = _as_mapping(manifest.get("scope"))
    if scope is None:
        errors.append("manifest scope must be an object")
    else:
        if scope.get("scope") != "PROJECT" or scope.get("installation_scope") not in {
            None,
            "PROJECT",
        }:
            errors.append("manifest scope is not project-local")
        activates = scope.get("activates_when")
        excludes = scope.get("do_not_activate_when")
        if (
            not isinstance(activates, (list, tuple))
            or not activates
            or any(not isinstance(item, str) or not item.strip() for item in activates)
        ):
            errors.append("manifest activation contract is missing")
        if (
            not isinstance(excludes, (list, tuple))
            or not excludes
            or any(not isinstance(item, str) or not item.strip() for item in excludes)
        ):
            errors.append("manifest do-not-activate contract is missing")
    for field in (
        "contracts",
        "composition",
        "dependencies",
        "compatibility",
        "provenance",
        "security",
    ):
        if not isinstance(manifest.get(field), Mapping):
            errors.append(f"manifest {field} must be an object")
    if manifest.get("status") != "CANDIDATE":
        errors.append("manifest status must remain CANDIDATE until external promotion closeout")
    if manifest.get("registry_bridge") is not False:
        errors.append("manifest registry_bridge must be false")
    if manifest.get("metadata_only") is not True:
        errors.append("manifest metadata_only must be true")
    if manifest.get("execution") != "NONE":
        errors.append("manifest execution must be NONE")
    if manifest.get("read_only") is not True:
        errors.append("manifest read_only must be true")
    if not isinstance(manifest.get("allowed_tools"), (list, tuple)) or manifest.get(
        "allowed_tools"
    ):
        errors.append("manifest allowed_tools must be empty")
    dependencies = _as_mapping(manifest.get("dependencies"))
    if dependencies is not None:
        for field in ("tools", "providers"):
            value = dependencies.get(field, ())
            if value not in ((), [], None):
                errors.append(f"manifest dependencies.{field} must be empty")
    security = _as_mapping(manifest.get("security"))
    if security is not None:
        if security.get("read_only") is not True:
            errors.append("manifest security.read_only must be true")
        if security.get("allowed_tools") != []:
            errors.append("manifest security.allowed_tools must be empty")
        for field in BACKEND_FORBIDDEN_BOUNDARIES:
            value = security.get(field)
            if isinstance(value, Mapping):
                allowed = value.get("allowed", value.get("allow", False))
                mode = value.get("mode")
                if allowed is not False or str(mode).casefold() not in {"deny", "denied", "none"}:
                    errors.append(f"manifest security.{field} is not denied")
            elif value not in {False, "DENY", "deny", "DENIED", "denied", "NONE", "none"}:
                errors.append(f"manifest security.{field} is not denied")
    trust = _as_mapping(manifest.get("trust"))
    if trust is None:
        errors.append("manifest trust must be an object")
    else:
        if trust.get("level") != "PROJECT_LOCAL_CANDIDATE":
            errors.append("manifest trust level is not project-local candidate")
        if trust.get("external_execution") not in {"DENIED", "deny", "DENY"}:
            errors.append("manifest trust external execution is not denied")
        if not isinstance(trust.get("promotion"), str) or not trust.get("promotion"):
            errors.append("manifest trust promotion rule is missing")
    provenance = _as_mapping(manifest.get("provenance"))
    if provenance is not None:
        for field in (
            "source_type",
            "source_refs",
            "current_source_refs",
            "upstream_source_refs",
            "native_source_refs",
        ):
            value = provenance.get(field)
            if isinstance(value, str):
                value = (value,)
            if (
                not isinstance(value, (list, tuple))
                or not value
                or any(not isinstance(item, str) or not item.strip() for item in value)
            ):
                errors.append(f"manifest provenance.{field} is incomplete")
        source_hashes = _as_mapping(provenance.get("source_hashes"))
        if source_hashes is None or any(
            not isinstance(source_hashes.get(field), str) or not source_hashes.get(field)
            for field in ("current", "upstream", "native", "vnext")
        ):
            errors.append("manifest provenance.source_hashes are incomplete")
    contracts = _as_mapping(manifest.get("contracts"))
    if contracts is not None:
        for field in ("inputs", "outputs", "gates", "stop_conditions"):
            value = contracts.get(field)
            if (
                not isinstance(value, (list, tuple))
                or not value
                or any(not isinstance(item, str) or not item for item in value)
            ):
                errors.append(f"manifest contracts.{field} must be a non-empty string list")
    composition = _as_mapping(manifest.get("composition"))
    if composition is not None:
        if composition.get("same_invocation_role") != "SPECIALIST_ONLY":
            errors.append("manifest composition.same_invocation_role must be SPECIALIST_ONLY")
        if composition.get("fresh_final_verification_required") is not True:
            errors.append("manifest composition requires fresh final verification")
        repair_limit = composition.get("repair_limit")
        if repair_limit != 1:
            errors.append("manifest composition repair_limit must be one")
        for field in ("can_call", "can_be_called_by", "must_run_before", "must_run_after"):
            value = composition.get(field)
            if not isinstance(value, (list, tuple)):
                errors.append(f"manifest composition.{field} must be a list")
    budgets = _as_mapping(manifest.get("budgets"))
    if budgets is not None:
        for field in (
            "context_bytes",
            "selected_references_bytes",
            "procedures_per_run",
            "total_seconds",
            "attempts_per_procedure",
            "builder_invocations",
            "verifier_invocations",
            "composition_repairs",
            "evidence_records",
            "report_bytes",
            "max_no_progress_rounds",
            "unbounded_loops",
        ):
            value = budgets.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"manifest budgets.{field} must be a non-negative integer")
        if budgets.get("attempts_per_procedure") != 1:
            errors.append("manifest budgets.attempts_per_procedure must be one")
        if budgets.get("unbounded_loops") != 0:
            errors.append("manifest budgets.unbounded_loops must be zero")
        positive_bounds = {
            "context_bytes": (1, 262_144),
            "selected_references_bytes": (1, 131_072),
            "procedures_per_run": (1, _MAX_PROCEDURES),
            "total_seconds": (1, 600),
            "builder_invocations": (1, 4),
            "verifier_invocations": (1, 4),
            "evidence_records": (1, 256),
            "report_bytes": (1, 512 * 1024),
            "max_no_progress_rounds": (1, 3),
        }
        for field, (minimum, maximum) in positive_bounds.items():
            value = budgets.get(field)
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and not minimum <= value <= maximum
            ):
                errors.append(f"manifest budgets.{field} is outside its bound")
    quality = _as_mapping(manifest.get("quality"))
    if quality is not None:
        for field in (
            "profile_refs",
            "composition_contract",
            "eval_refs",
            "benchmark_refs",
            "last_result",
            "causal_claim",
        ):
            if field not in quality:
                errors.append(f"manifest quality.{field} is missing")
        if quality.get("causal_claim") is not False:
            errors.append("manifest quality.causal_claim must be false")
    execution_policy = _as_mapping(manifest.get("execution_policy"))
    if execution_policy is not None:
        required_policy_fields = (
            *BACKEND_FORBIDDEN_BOUNDARIES,
            "allowed_tools",
            "workspace_write",
            "arbitrary_interpolation",
            "subagents",
        )
        for field in required_policy_fields:
            if field not in execution_policy:
                errors.append(f"manifest execution_policy.{field} is missing")
        for field in BACKEND_FORBIDDEN_BOUNDARIES:
            value = execution_policy.get(field)
            if value is None or str(value).upper() not in {"DENY", "DENIED", "NONE"}:
                errors.append(f"manifest execution_policy.{field} is not denied")
        tools = execution_policy.get("allowed_tools")
        if not isinstance(tools, (list, tuple)) or tools:
            errors.append("manifest execution policy has allowed tools")
        for field in ("workspace_write", "arbitrary_interpolation", "subagents"):
            if str(execution_policy.get(field)).upper() not in {"DENY", "DENIED", "NONE"}:
                errors.append(f"manifest execution_policy.{field} is not denied")
    return tuple(dict.fromkeys(errors))


def _validate_package_metadata(
    package: Path,
    manifest: Mapping[str, object],
    file_paths: tuple[str, ...],
    *,
    scenario_count: int,
    benchmark_count: int,
) -> tuple[str, ...]:
    """Validate the metadata documents that make the package executable as a contract.

    The package remains declarative, but its metadata is not optional: a
    partial validator must not turn a malformed composition/eval/budget file
    into an eligible candidate.
    """

    errors: list[str] = []

    def validate_declared_paths(field: str, value: object) -> None:
        if isinstance(value, str):
            values = (value,)
        elif isinstance(value, list):
            values = tuple(value)
        else:
            errors.append(f"manifest {field} must declare package paths")
            return
        for item in values:
            if not isinstance(item, str) or not item.strip() or item not in file_paths:
                errors.append(f"manifest {field} references a missing package file")
                continue
            try:
                _safe_path_parts(item, field=f"manifest {field} path")
            except BackendPackageContractError:
                errors.append(f"manifest {field} contains an unsafe path")

    for field in ("references", "evals", "benchmarks", "scripts"):
        validate_declared_paths(field, manifest.get(field))
    validate_declared_paths("profiles", manifest.get("profiles"))
    dependencies = _as_mapping(manifest.get("dependencies"))
    if dependencies is not None:
        validate_declared_paths("dependencies.references", dependencies.get("references"))

    def document(relative: str) -> Mapping[str, object] | None:
        if relative not in file_paths:
            errors.append(f"PACKAGE_METADATA_MISSING:{relative}")
            return None
        try:
            return _read_package_json(package, relative, max_bytes=_MAX_METADATA_BYTES)
        except BackendPackageContractError as exc:
            errors.append(f"PACKAGE_METADATA_INVALID:{relative}:{exc}")
            return None

    package_metadata = document("package-metadata.json")
    if package_metadata is not None:
        for field, expected in (
            ("schema_version", "P7-PACKAGE-1"),
            ("package_id", BACKEND_CAPABILITY_ID),
            ("native", True),
            ("scope", "PROJECT"),
            ("version", BACKEND_PACKAGE_VERSION),
            ("metadata_only", True),
            ("execution", "NONE"),
            ("host_load_claim", False),
            ("global_state_mutation", False),
            ("installed_source_mutation", False),
            ("external_state_mutation", False),
            ("package_write_allowed", False),
            ("no_false_causal_claim", True),
        ):
            if package_metadata.get(field) != expected:
                errors.append(f"package-metadata.{field} does not match its contract")
        claim_exclusions = package_metadata.get("claims_excluded")
        if not isinstance(claim_exclusions, (list, tuple)) or not claim_exclusions:
            errors.append("package-metadata.claims_excluded must be non-empty")

    composition = document("composition-contract.json")
    if composition is not None:
        required_composition_fields = (
            "schema_version",
            "capability_id",
            "role",
            "authority",
            "pipeline",
            "can_call",
            "can_be_called_by",
            "must_run_after",
            "must_run_before",
            "conflicts",
            "do_not_combine",
            "optional",
            "handoff_edges",
            "fresh_final_verification",
            "repair_policy",
            "workspace_boundary",
            "support_levels",
            "causal_claim",
            "host_observability",
        )
        for field in required_composition_fields:
            if field not in composition:
                errors.append(f"composition-contract missing {field}")
        if composition.get("schema_version") != "P7-COMPOSITION-1":
            errors.append("composition-contract schema is unsupported")
        if composition.get("capability_id") != BACKEND_CAPABILITY_ID:
            errors.append("composition-contract capability_id is not bound")
        if composition.get("role") != BACKEND_ROLE:
            errors.append("composition-contract role is not SPECIALIST")
        if composition.get("causal_claim") is not False:
            errors.append("composition-contract causal_claim must be false")
        for field in (
            "can_be_called_by",
            "must_run_after",
            "must_run_before",
            "conflicts",
            "do_not_combine",
            "optional",
            "pipeline",
            "handoff_edges",
        ):
            value = composition.get(field)
            if not isinstance(value, list) or not value:
                errors.append(f"composition-contract {field} must be a non-empty list")
        if not isinstance(composition.get("can_call"), list):
            errors.append("composition-contract can_call must be a list")
        manifest_composition = _as_mapping(manifest.get("composition"))
        if manifest_composition is not None:
            for field in ("conflicts", "do_not_combine"):
                if composition.get(field) != manifest_composition.get(field):
                    errors.append(f"composition-contract {field} disagrees with manifest")
        conflicts = composition.get("conflicts")
        do_not_combine = composition.get("do_not_combine")
        if (
            isinstance(conflicts, list)
            and isinstance(do_not_combine, list)
            and not set(do_not_combine).issubset(conflicts)
        ):
            errors.append("composition-contract do_not_combine must be conflicts subset")
        fresh = _as_mapping(composition.get("fresh_final_verification"))
        repair = _as_mapping(composition.get("repair_policy"))
        if (
            fresh is None
            or fresh.get("required_after_repair") is not True
            or fresh.get("max_invocations") != 2
            or not isinstance(fresh.get("must_rebind"), list)
            or not fresh.get("must_rebind")
        ):
            errors.append("composition-contract fresh verification is not required")
        if (
            repair is None
            or repair.get("max_repairs") != 1
            or repair.get("requires_structured_finding") is not True
            or repair.get("requires_fresh_tests") is not True
            or repair.get("requires_fresh_verification") is not True
        ):
            errors.append("composition-contract repair policy is not bounded to one")
        workspace = _as_mapping(composition.get("workspace_boundary"))
        if (
            workspace is None
            or workspace.get("package_mutation") != "DENY"
            or workspace.get("control_plane_mutation") != "DENY"
            or workspace.get("pilot_mutation") != "HOST_GRANTED_BOUNDED_ROOT_ONLY"
            or workspace.get("external_state") != "DENY"
        ):
            errors.append("composition-contract package mutation is not denied")
        support_levels = composition.get("support_levels")
        if not isinstance(support_levels, Mapping) or not all(
            isinstance(support_levels.get(key), str) and support_levels.get(key)
            for key in ("P7_LEVEL_A", "P7_LEVEL_B", "P7_LEVEL_C")
        ):
            errors.append("composition-contract support levels are incomplete")

    profiles = document("profiles.json")
    if profiles is not None:
        if profiles.get("schema_version") != "P7-PROFILES-1":
            errors.append("profiles schema is unsupported")
        if profiles.get("capability_id") != BACKEND_CAPABILITY_ID:
            errors.append("profiles capability_id is not bound")
        profile_ids = profiles.get("profile_ids")
        profile_records = profiles.get("profiles")
        profile_id_values = tuple(profile_ids) if isinstance(profile_ids, list) else ()
        if (
            not profile_id_values
            or any(not isinstance(item, str) or not item.strip() for item in profile_id_values)
            or len(set(profile_id_values)) != len(profile_id_values)
        ):
            errors.append("profiles profile_ids must be non-empty")
        if profiles.get("default_profile") not in profile_id_values:
            errors.append("profiles default_profile is not declared")
        if not isinstance(profile_records, list) or len(profile_records) != len(profile_id_values):
            errors.append("profiles records do not match profile_ids")
        elif any(
            not isinstance(item, Mapping)
            or not isinstance(item.get("id"), str)
            or item.get("id") not in profile_id_values
            or not isinstance(item.get("gates"), list)
            or not item.get("gates")
            or not isinstance(item.get("task_classes"), list)
            or not isinstance(item.get("required_dimensions"), list)
            for item in profile_records
        ):
            errors.append("profiles contain an incomplete profile contract")
        elif {item.get("id") for item in profile_records if isinstance(item, Mapping)} != set(
            profile_id_values
        ):
            errors.append("profiles records contain an unexpected profile id")

    eval_metadata = document("eval-metadata.json")
    if eval_metadata is not None:
        if eval_metadata.get("schema_version") != "P7-EVAL-METADATA-1":
            errors.append("eval-metadata schema is unsupported")
        if eval_metadata.get("package_id") != BACKEND_CAPABILITY_ID:
            errors.append("eval-metadata package_id is not bound")
        if eval_metadata.get("scenario_count") != scenario_count:
            errors.append("eval-metadata scenario_count does not match eval catalog")
        required_fields = eval_metadata.get("required_fields")
        if not isinstance(required_fields, list) or set(required_fields) != {
            "id",
            "category",
            "title",
            "input_identity",
            "required_criterion_ids",
            "evidence_refs",
            "profile",
            "expected_outcome",
            "oracle",
            "rationale",
            "expected_stop",
            "input",
            "preconditions",
            "required_observations",
            "forbidden_observations",
            "known_bad",
            "expected_artifacts",
        }:
            errors.append("eval-metadata required_fields are incomplete")

    benchmark_metadata = document("benchmark-metadata.json")
    if benchmark_metadata is not None:
        if benchmark_metadata.get("schema_version") != "P7-BENCH-METADATA-1":
            errors.append("benchmark-metadata schema is unsupported")
        if benchmark_metadata.get("package_id") != BACKEND_CAPABILITY_ID:
            errors.append("benchmark-metadata package_id is not bound")
        if benchmark_metadata.get("fixture_count") != benchmark_count:
            errors.append("benchmark-metadata fixture_count does not match benchmark catalog")
        if benchmark_metadata.get("normalized_task") != "P7_TASK_VET_APPOINTMENT_001":
            errors.append("benchmark-metadata normalized task is not bound")

    return tuple(dict.fromkeys(errors))


def validate_backend_manifest(
    manifest: Mapping[str, object] | str | Path,
    *,
    package_path: str | Path | None = None,
) -> tuple[str, ...]:
    """Return deterministic manifest contract violations without executing it."""

    if isinstance(manifest, Mapping):
        value = manifest
    else:
        raw = Path(manifest)
        if package_path is not None:
            package = _safe_package_path(package_path)
            relative = raw.name if raw.parent == package else "manifest.json"
        elif raw.is_dir():
            package = _safe_package_path(raw)
            relative = "manifest.json"
        else:
            package = _safe_package_path(raw.parent)
            relative = raw.name
        value = _read_package_json(package, relative, max_bytes=_MAX_MANIFEST_BYTES)
    return _check_manifest(value)


def _validate_eval_catalog(catalog: Mapping[str, object]) -> tuple[str, ...]:
    errors: list[str] = []
    if catalog.get("schema_version") != "P7-EVAL-1":
        errors.append("eval catalog schema_version is unsupported")
    if catalog.get("package_id") != BACKEND_CAPABILITY_ID:
        errors.append("eval catalog package_id does not match the package")
    scenarios = catalog.get("scenarios")
    if not isinstance(scenarios, list):
        return (*errors, "eval catalog scenarios must be a list")
    if len(scenarios) < 40:
        errors.append("eval catalog must contain at least 40 scenarios")
    if len(scenarios) > _MAX_SCENARIOS:
        errors.append("eval catalog exceeds its scenario bound")
    expected_ids = [f"P7-SC-{index:03d}" for index in range(1, len(scenarios) + 1)]
    actual_ids: list[str] = []
    categories: set[str] = set()
    for index, raw in enumerate(scenarios):
        if not isinstance(raw, Mapping):
            errors.append(f"eval scenario {index + 1} must be an object")
            continue
        required_fields = (
            "id",
            "category",
            "title",
            "input_identity",
            "required_criterion_ids",
            "evidence_refs",
            "profile",
            "expected_outcome",
            "oracle",
            "rationale",
            "expected_stop",
        )
        for field in required_fields:
            if field not in raw:
                errors.append(f"eval scenario {index + 1} is missing {field}")
        scenario_id = raw.get("id")
        if not isinstance(scenario_id, str):
            errors.append(f"eval scenario {index + 1} is missing id")
        else:
            actual_ids.append(scenario_id)
        category = raw.get("category")
        if isinstance(category, str) and category:
            categories.add(category)
        else:
            errors.append(f"eval scenario {index + 1} has no category")
        for field in ("title", "oracle", "rationale"):
            value = raw.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 4_096:
                errors.append(f"eval scenario {index + 1} has invalid {field}")
        for field in ("input_identity", "profile", "expected_stop"):
            value = raw.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 4_096:
                errors.append(f"eval scenario {index + 1} has invalid {field}")
        for field in ("required_criterion_ids", "evidence_refs"):
            values = raw.get(field)
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(item, str) or not item.strip() for item in values)
            ):
                errors.append(f"eval scenario {index + 1} has invalid {field}")
        input_case = raw.get("input")
        if (
            not isinstance(input_case, Mapping)
            or not isinstance(input_case.get("task"), str)
            or not input_case.get("task")
            or not isinstance(input_case.get("scope"), str)
            or not input_case.get("scope")
            or not isinstance(input_case.get("prompt"), str)
            or not input_case.get("prompt")
        ):
            errors.append(f"eval scenario {index + 1} has an incomplete input case")
        for field in (
            "preconditions",
            "required_observations",
            "forbidden_observations",
            "expected_artifacts",
        ):
            values = raw.get(field)
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(item, str) or not item.strip() for item in values)
            ):
                errors.append(f"eval scenario {index + 1} has invalid {field}")
        known_bad = raw.get("known_bad")
        if (
            not isinstance(known_bad, Mapping)
            or not isinstance(known_bad.get("description"), str)
            or not known_bad.get("description")
            or not isinstance(known_bad.get("violation"), str)
            or not known_bad.get("violation")
            or known_bad.get("mutation")
            not in {
                "remove_required_observations",
                "remove_input_prompt",
                "remove_expected_artifact",
            }
            or not isinstance(known_bad.get("fixture"), Mapping)
            or known_bad.get("expected_outcome") not in {"PASS", "BLOCKED", "FAIL", "PARTIAL"}
        ):
            errors.append(f"eval scenario {index + 1} has an invalid known_bad case")
        elif known_bad.get("expected_outcome") == raw.get("expected_outcome"):
            errors.append(f"eval scenario {index + 1} known_bad outcome is not distinct")
        if not isinstance(raw.get("critical"), bool):
            errors.append(f"eval scenario {index + 1} has invalid critical flag")
        if raw.get("expected_outcome") not in {"PASS", "BLOCKED", "FAIL", "PARTIAL"}:
            errors.append(f"eval scenario {index + 1} has an invalid expected outcome")
    if actual_ids != expected_ids:
        errors.append("eval scenario IDs are not contiguous and deterministic")
    if len(categories) < 12:
        errors.append("eval catalog must cover at least 12 categories")
    return tuple(dict.fromkeys(errors))


def validate_backend_evals(
    catalog: Mapping[str, object] | str | Path,
    *,
    package_path: str | Path | None = None,
) -> tuple[str, ...]:
    """Return deterministic eval-catalog contract violations."""

    if isinstance(catalog, Mapping):
        value = catalog
    else:
        raw = Path(catalog)
        if package_path is not None:
            package = _safe_package_path(package_path)
            relative = raw.name if raw.parent == package else "evals/scenarios.json"
        elif raw.is_dir():
            package = _safe_package_path(raw)
            relative = "evals/scenarios.json"
        else:
            package = _safe_package_path(raw.parent)
            relative = raw.name
        value = _read_package_json(package, relative, max_bytes=_MAX_METADATA_BYTES)
    return _validate_eval_catalog(value)


def _validate_benchmark_catalog(catalog: Mapping[str, object]) -> tuple[str, ...]:
    errors: list[str] = []
    schema = catalog.get("schema_version")
    if schema not in {"P7-BENCH-1", "P7-BENCH-METADATA-1"}:
        errors.append("benchmark catalog schema_version is unsupported")
    if catalog.get("package_id") != BACKEND_CAPABILITY_ID:
        errors.append("benchmark catalog package_id does not match the package")
    if catalog.get("causal_claim") not in {False, None}:
        errors.append("benchmark catalog cannot make a causal claim")
    normalized_task = _as_mapping(catalog.get("normalized_task"))
    normalized_task_id = normalized_task.get("id") if normalized_task is not None else None
    if not isinstance(normalized_task_id, str) or not normalized_task_id:
        errors.append("benchmark catalog normalized_task.id is missing")
    if catalog.get("same_task") is not True:
        errors.append("benchmark catalog same_task must be true")
    records = catalog.get("records", catalog.get("fixtures"))
    if not isinstance(records, list):
        return (*errors, "benchmark catalog records must be a list")
    if len(records) != 4:
        errors.append("benchmark catalog must contain exactly four bounded paths")
    if len(records) > _MAX_BENCHMARK_RECORDS:
        errors.append("benchmark catalog exceeds its record bound")
    observed_baselines: set[str] = set()
    observed_ids: set[str] = set()
    for index, raw in enumerate(records):
        if not isinstance(raw, Mapping):
            errors.append(f"benchmark record {index + 1} must be an object")
            continue
        record_id = raw.get("id")
        if not isinstance(record_id, str) or not record_id:
            errors.append(f"benchmark record {index + 1} is missing id")
        elif record_id in observed_ids:
            errors.append("benchmark record IDs must be unique")
        else:
            observed_ids.add(record_id)
        baseline = raw.get("baseline", raw.get("label"))
        if isinstance(baseline, str):
            observed_baselines.add(baseline.casefold())
        else:
            errors.append(f"benchmark record {index + 1} is missing baseline")
        if raw.get("task_id") != normalized_task_id:
            errors.append(f"benchmark record {index + 1} task_id does not match normalized task")
        if raw.get("fixture_only") is not True:
            errors.append(f"benchmark record {index + 1} must be fixture-only")
        if raw.get("causal_claim") is not False:
            errors.append(f"benchmark record {index + 1} cannot make a causal claim")
        outcome = raw.get("expected_outcome")
        if outcome is not None and outcome not in {"PASS", "BLOCKED", "FAIL", "PARTIAL"}:
            errors.append(f"benchmark record {index + 1} has an invalid expected outcome")
        observation_status = raw.get("observation_status")
        if observation_status not in {"OBSERVED", "BLOCKED", "PARTIAL"}:
            errors.append(f"benchmark record {index + 1} has an invalid observation status")
        observation = raw.get("observation")
        if not isinstance(observation, Mapping):
            errors.append(f"benchmark record {index + 1} observation is missing")
        else:
            environment = observation.get("environment")
            sample_count = observation.get("sample_count")
            reason = observation.get("reason")
            if not isinstance(environment, str) or not environment.strip():
                errors.append(f"benchmark record {index + 1} observation environment is missing")
            if (
                not isinstance(sample_count, int)
                or isinstance(sample_count, bool)
                or sample_count < 0
            ):
                errors.append(f"benchmark record {index + 1} observation sample_count is invalid")
            if observation_status == "OBSERVED" and (
                not isinstance(sample_count, int) or sample_count < 1
            ):
                errors.append(f"benchmark record {index + 1} observed status has no samples")
            if observation_status == "BLOCKED" and (
                not isinstance(reason, str) or not reason.strip()
            ):
                errors.append(f"benchmark record {index + 1} blocked status has no reason")
            measurements = observation.get("measurements")
            if observation_status == "OBSERVED" and (
                not isinstance(measurements, Mapping) or not measurements
            ):
                errors.append(f"benchmark record {index + 1} observed measurements are missing")
        observed = raw.get("observed")
        if not isinstance(observed, bool):
            errors.append(f"benchmark record {index + 1} observed flag is invalid")
        elif observed != (observation_status == "OBSERVED"):
            errors.append(f"benchmark record {index + 1} observed flag disagrees with status")
        for field in ("context_bytes", "latency_ms"):
            value = raw.get(field)
            if value is not None and (
                not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0
            ):
                errors.append(f"benchmark record {index + 1} has invalid {field}")
    required_baselines = {"current", "native", "upstream", "vnext"}
    if not required_baselines.issubset(observed_baselines):
        errors.append("benchmark catalog must include current, native, upstream and vNext paths")
    invariants = _as_mapping(catalog.get("quality_invariants"))
    if invariants is not None:
        if invariants.get("false_critical_pass", 0) != 0:
            errors.append("benchmark false_critical_pass invariant must be zero")
        if invariants.get("unbounded_loops", 0) != 0:
            errors.append("benchmark unbounded_loops invariant must be zero")
    return tuple(dict.fromkeys(errors))


def validate_backend_benchmarks(
    catalog: Mapping[str, object] | str | Path,
    *,
    package_path: str | Path | None = None,
) -> tuple[str, ...]:
    """Return deterministic four-way benchmark metadata violations."""

    if isinstance(catalog, Mapping):
        value = catalog
    else:
        raw = Path(catalog)
        if package_path is not None:
            package = _safe_package_path(package_path)
            relative = raw.name if raw.parent == package else "benchmarks/benchmark-fixtures.json"
        elif raw.is_dir():
            package = _safe_package_path(raw)
            relative = "benchmarks/benchmark-fixtures.json"
        else:
            package = _safe_package_path(raw.parent)
            relative = raw.name
        value = _read_package_json(package, relative, max_bytes=_MAX_METADATA_BYTES)
    return _validate_benchmark_catalog(value)


def validate_backend_procedures(
    catalog: Mapping[str, object] | str | Path,
    *,
    package_path: str | Path | None = None,
) -> tuple[str, ...]:
    """Return deterministic procedure-catalog contract violations."""

    if isinstance(catalog, Mapping):
        value = catalog
    else:
        raw = Path(catalog)
        if package_path is not None:
            package = _safe_package_path(package_path)
            relative = (
                raw.name if raw.parent == package else "scripts/deterministic-procedures.json"
            )
        elif raw.is_dir():
            package = _safe_package_path(raw)
            relative = "scripts/deterministic-procedures.json"
        else:
            package = _safe_package_path(raw.parent)
            relative = raw.name
        value = _read_package_json(package, relative, max_bytes=_MAX_METADATA_BYTES)
    return _validate_procedure_catalog(value)


def _validate_procedure_catalog(catalog: Mapping[str, object]) -> tuple[str, ...]:
    errors: list[str] = []
    if catalog.get("schema_version") != "P7-PROCEDURES-1":
        errors.append("deterministic procedure schema is unsupported")
    if catalog.get("package_id") != BACKEND_CAPABILITY_ID:
        errors.append("deterministic procedure package_id is not bound")
    if catalog.get("metadata_only") is not True:
        errors.append("deterministic procedures must be metadata-only")
    if catalog.get("execution") not in {"none", "NONE"}:
        errors.append("deterministic procedures cannot execute")
    if catalog.get("read_only") is not True:
        errors.append("deterministic procedures must be read-only")
    if catalog.get("allowed_tools") not in ([], ()):
        errors.append("deterministic procedures must have no allowed tools")
    for field in ("workspace_write", "arbitrary_interpolation", "subagents"):
        if str(catalog.get(field, "")).casefold() not in {"deny", "denied", "none"}:
            errors.append(f"deterministic procedure {field} boundary is not denied")
    procedures = catalog.get("procedures")
    if procedures is None:
        errors.append("deterministic procedure list is missing")
    elif not isinstance(procedures, list):
        errors.append("deterministic procedures must be a list")
    elif not procedures:
        errors.append("deterministic procedure list is missing")
    elif len(procedures) > _MAX_PROCEDURES:
        errors.append("deterministic procedure count exceeds its bound")
    else:
        procedure_ids: set[str] = set()
        for index, procedure in enumerate(procedures):
            if not isinstance(procedure, Mapping):
                errors.append(f"procedure {index + 1} must be an object")
                continue
            procedure_id = procedure.get("id")
            if not isinstance(procedure_id, str) or not procedure_id.strip():
                errors.append(f"procedure {index + 1} id is missing")
            elif procedure_id in procedure_ids:
                errors.append("deterministic procedure IDs must be unique")
            else:
                procedure_ids.add(procedure_id)
            for field in ("purpose", "inputs", "outputs", "observation"):
                value = procedure.get(field)
                if isinstance(value, str):
                    if not value.strip():
                        errors.append(f"procedure {index + 1} {field} is empty")
                elif isinstance(value, list):
                    if not value or any(
                        not isinstance(item, str) or not item.strip() for item in value
                    ):
                        errors.append(f"procedure {index + 1} {field} is incomplete")
                else:
                    errors.append(f"procedure {index + 1} {field} is missing")
            if procedure.get("max_attempts") != 1:
                errors.append(f"procedure {index + 1} must have one attempt")
            if procedure.get("mutation") not in {"none", "NONE"}:
                errors.append(f"procedure {index + 1} is mutating")
    for field in BACKEND_FORBIDDEN_BOUNDARIES:
        if str(catalog.get(field, "deny")).casefold() not in {"deny", "denied", "none"}:
            errors.append(f"procedure catalog {field} boundary is not denied")
    return tuple(dict.fromkeys(errors))


@dataclass(frozen=True, slots=True)
class BackendPackageReport:
    """Immutable result of the native backend package contract check."""

    ok: bool
    capability_id: str
    version: str
    primary_type: str
    role: str
    scenario_count: int
    package_fingerprint: str
    forbidden_boundaries: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    manifest_fingerprint: str | None = None
    files: tuple[str, ...] = ()
    benchmark_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.ok, bool):
            raise ValueError("ok must be boolean")
        for field in ("capability_id", "version", "primary_type", "role", "package_fingerprint"):
            _required_text(getattr(self, field), field, maximum=512)
        if not _DIGEST_PATTERN.fullmatch(self.package_fingerprint):
            raise ValueError("package_fingerprint must be a sha256 digest")
        if self.manifest_fingerprint is not None and not _DIGEST_PATTERN.fullmatch(
            self.manifest_fingerprint
        ):
            raise ValueError("manifest_fingerprint must be a sha256 digest")
        if (
            not isinstance(self.scenario_count, int)
            or isinstance(self.scenario_count, bool)
            or self.scenario_count < 0
        ):
            raise ValueError("scenario_count must be a non-negative integer")
        if (
            not isinstance(self.benchmark_count, int)
            or isinstance(self.benchmark_count, bool)
            or self.benchmark_count < 0
        ):
            raise ValueError("benchmark_count must be a non-negative integer")
        object.__setattr__(self, "forbidden_boundaries", tuple(self.forbidden_boundaries))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "files", tuple(self.files))

    @property
    def errors(self) -> tuple[str, ...]:
        """Compatibility alias used by callers that call blockers errors."""

        return self.blockers

    @property
    def fingerprint(self) -> str:
        return self.package_fingerprint


@dataclass(frozen=True, slots=True)
class WorkspaceDeltaReport:
    """Immutable bounded comparison of two workspace observations."""

    ok: bool
    changed_paths: tuple[str, ...]
    unauthorized_paths: tuple[str, ...]
    added_paths: tuple[str, ...] = ()
    removed_paths: tuple[str, ...] = ()
    digest: str = _ZERO_DIGEST
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.ok, bool):
            raise ValueError("ok must be boolean")
        for field in (
            "changed_paths",
            "unauthorized_paths",
            "added_paths",
            "removed_paths",
            "errors",
        ):
            values = tuple(getattr(self, field))
            if any(not isinstance(item, str) or not item or "\x00" in item for item in values):
                raise ValueError(f"{field} contains an invalid path or error")
            object.__setattr__(self, field, values)
        if not _DIGEST_PATTERN.fullmatch(self.digest):
            raise ValueError("workspace delta digest must be a sha256 digest")

    @property
    def changed(self) -> tuple[str, ...]:
        return self.changed_paths


@dataclass(frozen=True, slots=True)
class BackendEvidenceBindingReport:
    """Immutable freshness and identity result for a backend handoff."""

    ok: bool
    task_id: str
    package_fingerprint: str
    artifact_digest: str
    criteria_digest: str
    evidence_count: int
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.ok, bool):
            raise ValueError("ok must be boolean")
        for field in (
            "task_id",
            "package_fingerprint",
            "artifact_digest",
            "criteria_digest",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field} must be non-empty")
        for field in ("package_fingerprint", "artifact_digest", "criteria_digest"):
            if not _DIGEST_PATTERN.fullmatch(getattr(self, field)):
                raise ValueError(f"{field} must be a sha256 digest")
        if (
            not isinstance(self.evidence_count, int)
            or isinstance(self.evidence_count, bool)
            or self.evidence_count < 0
        ):
            raise ValueError("evidence_count must be a non-negative integer")
        object.__setattr__(self, "blockers", tuple(self.blockers))


def validate_backend_evidence_binding(
    evidence: Mapping[str, object],
    *,
    expected_task_id: str | None = None,
    expected_package_fingerprint: str | None = None,
    expected_artifact_digest: str | None = None,
    expected_criteria_digest: str | None = None,
    expected_authority: str | None = None,
    max_age_seconds: int = 86_400,
) -> BackendEvidenceBindingReport:
    """Reject stale, unbound, future, or self-approved backend evidence.

    This check intentionally accepts a mapping rather than filesystem paths:
    the Phase 4/6 owners authenticate paths and artifact bytes, while this
    boundary authenticates the immutable identity/freshness handoff.
    """

    blockers: list[str] = []

    def text(field: str) -> str:
        value = evidence.get(field)
        if not isinstance(value, str) or not value or "\x00" in value:
            blockers.append(f"EVIDENCE_{field.upper()}_INVALID")
            return "UNKNOWN_TASK" if field == "task_id" else _ZERO_DIGEST
        return value

    task_id = text("task_id")
    package_fingerprint = text("package_fingerprint")
    artifact_digest = text("artifact_digest")
    criteria_digest = text("criteria_digest")
    for field, value in (
        ("package_fingerprint", package_fingerprint),
        ("artifact_digest", artifact_digest),
        ("criteria_digest", criteria_digest),
    ):
        if value and _DIGEST_PATTERN.fullmatch(value) is None:
            # TESTED_BRANCH_FINDING_ID: P7.1-BRANCH-1f3a3c37ff18
            blockers.append(f"EVIDENCE_{field.upper()}_INVALID")
            if field == "package_fingerprint":
                package_fingerprint = _ZERO_DIGEST
            elif field == "artifact_digest":
                artifact_digest = _ZERO_DIGEST
            else:
                criteria_digest = _ZERO_DIGEST

    expected_values = (
        ("task_id", expected_task_id),
        ("package_fingerprint", expected_package_fingerprint),
        ("artifact_digest", expected_artifact_digest),
        ("criteria_digest", expected_criteria_digest),
    )
    for field, expected in expected_values:
        if expected is None:
            blockers.append(f"EXPECTED_EVIDENCE_{field.upper()}_REQUIRED")
        elif (
            not isinstance(expected, str)
            or not expected
            or "\x00" in expected
            or (field != "task_id" and _DIGEST_PATTERN.fullmatch(expected) is None)
        ):
            blockers.append(f"EXPECTED_EVIDENCE_{field.upper()}_INVALID")
    if expected_task_id is not None and task_id != expected_task_id:
        blockers.append("EVIDENCE_TASK_ID_MISMATCH")
    if (
        expected_package_fingerprint is not None
        and package_fingerprint != expected_package_fingerprint
    ):
        blockers.append("EVIDENCE_PACKAGE_FINGERPRINT_MISMATCH")
    if expected_artifact_digest is not None and artifact_digest != expected_artifact_digest:
        blockers.append("EVIDENCE_ARTIFACT_DIGEST_MISMATCH")
    if expected_criteria_digest is not None and criteria_digest != expected_criteria_digest:
        blockers.append("EVIDENCE_CRITERIA_DIGEST_MISMATCH")

    freshness = evidence.get("freshness")
    if freshness != "FRESH":
        blockers.append("EVIDENCE_NOT_FRESH")
    status = evidence.get("status")
    if status not in {"VERIFIED", "PASS", "PASS_WITH_LIMITATIONS"}:
        blockers.append("EVIDENCE_STATUS_NOT_VERIFIED")
    if evidence.get("self_approval") is not False:
        blockers.append("EVIDENCE_SELF_APPROVAL_FORBIDDEN")
    authority = evidence.get("authority")
    if not isinstance(authority, str) or not authority:
        blockers.append("EVIDENCE_AUTHORITY_MISSING")
    if expected_authority is None:
        blockers.append("EXPECTED_EVIDENCE_AUTHORITY_REQUIRED")
    elif not isinstance(expected_authority, str) or not expected_authority:
        blockers.append("EXPECTED_EVIDENCE_AUTHORITY_INVALID")
    elif authority != expected_authority:
        blockers.append("EVIDENCE_AUTHORITY_MISMATCH")
    observed_at = evidence.get("observed_at")
    now = datetime.now(UTC)
    observed_datetime: datetime | None = None
    if isinstance(observed_at, int) and not isinstance(observed_at, bool):
        try:
            observed_datetime = datetime.fromtimestamp(observed_at, UTC)
        except (OverflowError, OSError, ValueError):
            blockers.append("EVIDENCE_TIMESTAMP_INVALID")
    elif isinstance(observed_at, str) and observed_at:
        try:
            parsed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError:
            blockers.append("EVIDENCE_TIMESTAMP_INVALID")
        else:
            if parsed.tzinfo is None:
                blockers.append("EVIDENCE_TIMESTAMP_INVALID_OR_FUTURE")
            else:
                observed_datetime = parsed.astimezone(UTC)
    else:
        blockers.append("EVIDENCE_TIMESTAMP_MISSING")
    if (
        not isinstance(max_age_seconds, int)
        or isinstance(max_age_seconds, bool)
        or max_age_seconds < 0
    ):
        blockers.append("EVIDENCE_MAX_AGE_INVALID")
    if observed_datetime is not None and isinstance(max_age_seconds, int) and max_age_seconds >= 0:
        if observed_datetime > now:
            blockers.append("EVIDENCE_TIMESTAMP_IN_FUTURE")
        elif max_age_seconds < 0 or (now - observed_datetime).total_seconds() > max_age_seconds:
            blockers.append("EVIDENCE_TIMESTAMP_STALE")

    evidence_digests = evidence.get("evidence_digests")
    evidence_count = 0
    if not isinstance(evidence_digests, Mapping) or not evidence_digests:
        blockers.append("EVIDENCE_DIGESTS_MISSING")
    else:
        evidence_count = len(evidence_digests)
        if evidence_count > _MAX_EVIDENCE_RECORDS:
            blockers.append("EVIDENCE_DIGEST_COUNT_EXCEEDED")
        for key, value in evidence_digests.items():
            if (
                not isinstance(key, str)
                or not key
                or not isinstance(value, str)
                or _DIGEST_PATTERN.fullmatch(value) is None
            ):
                blockers.append("EVIDENCE_DIGEST_ENTRY_INVALID")
                break
    return BackendEvidenceBindingReport(
        ok=not blockers,
        task_id=task_id,
        package_fingerprint=package_fingerprint,
        artifact_digest=artifact_digest,
        criteria_digest=criteria_digest,
        evidence_count=evidence_count,
        blockers=tuple(dict.fromkeys(blockers)),
    )


# Friendly aliases keep the public contract discoverable without duplicating
# any mutable implementation.
BackendPackageValidationReport = BackendPackageReport
PackageValidationReport = BackendPackageReport
WorkspaceDeltaValidationReport = WorkspaceDeltaReport


def _empty_package_report(blockers: tuple[str, ...]) -> BackendPackageReport:
    return BackendPackageReport(
        ok=False,
        capability_id=BACKEND_CAPABILITY_ID,
        version=BACKEND_PACKAGE_VERSION,
        primary_type=BACKEND_PRIMARY_TYPE,
        role=BACKEND_ROLE,
        scenario_count=0,
        package_fingerprint=_ZERO_DIGEST,
        forbidden_boundaries=BACKEND_FORBIDDEN_BOUNDARIES,
        blockers=blockers,
    )


def _canonical_package_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".harness" / "capabilities" / BACKEND_CAPABILITY_ID


def _package_declared_digest(manifest: Mapping[str, object]) -> str | None:
    candidates: list[object] = [manifest.get("package_fingerprint"), manifest.get("content_hash")]
    identity = _as_mapping(manifest.get("identity"))
    if identity is not None:
        candidates.append(identity.get("package_fingerprint"))
    provenance = _as_mapping(manifest.get("provenance"))
    if provenance is not None:
        candidates.append(provenance.get("package_fingerprint"))
    return next((digest for digest in (_claim_digest(item) for item in candidates) if digest), None)


def validate_backend_package(
    package_path: str | Path,
    *,
    expected_package_path: str | Path | None = None,
    expected_fingerprint: str | None = None,
    limits: Phase3Limits | None = None,
) -> BackendPackageReport:
    """Validate the exact project-local native backend package.

    Contract failures are returned as an immutable ``ok=False`` report so a
    caller can preserve a factual blocked result.  Path-authentication
    failures (missing, symlinked or escaping roots) are also reported rather
    than silently substituted; ``package_fingerprint`` remains the strict
    raising primitive for callers that only need identity.
    """

    try:
        package = _safe_package_path(package_path)
    except BackendPackageContractError as exc:
        return _empty_package_report((str(exc),))
    blockers: list[str] = []
    expected: Path | None
    try:
        expected = (
            Path(expected_package_path)
            if expected_package_path is not None
            else _canonical_package_path()
        )
    except (TypeError, ValueError):
        expected = None
        blockers.append("EXPECTED_PACKAGE_PATH_INVALID")
    try:
        if expected is not None:
            expected = _safe_package_path(expected)
    except BackendPackageContractError:
        expected = None
        blockers.append("EXPECTED_PACKAGE_PATH_INVALID")
    blockers = list(dict.fromkeys(blockers))
    if expected is not None and package != expected:
        blockers.append("PACKAGE_PATH_IDENTITY_MISMATCH")
    try:
        selected_limits = _limits_for_package(limits)
        files = _package_files(package, selected_limits)
        fingerprint = _phase3_package_digest(files)
    except BackendPackageContractError as exc:
        return _empty_package_report((str(exc),))
    if expected_fingerprint is None:
        blockers.append("EXPECTED_PACKAGE_FINGERPRINT_REQUIRED")
    else:
        if (
            not isinstance(expected_fingerprint, str)
            or _DIGEST_PATTERN.fullmatch(expected_fingerprint) is None
        ):
            blockers.append("EXPECTED_PACKAGE_FINGERPRINT_INVALID")
        elif fingerprint != expected_fingerprint:
            blockers.append("PACKAGE_FINGERPRINT_MISMATCH")
    file_paths = tuple(item[0] for item in files)
    if "manifest.json" not in file_paths:
        blockers.append("MANIFEST_MISSING")
        return BackendPackageReport(
            False,
            BACKEND_CAPABILITY_ID,
            BACKEND_PACKAGE_VERSION,
            BACKEND_PRIMARY_TYPE,
            BACKEND_ROLE,
            0,
            fingerprint,
            BACKEND_FORBIDDEN_BOUNDARIES,
            tuple(dict.fromkeys(blockers)),
            files=file_paths,
        )
    try:
        manifest_payload = read_bounded_file(
            package, "manifest.json", max_bytes=_MAX_MANIFEST_BYTES
        )
        manifest = _strict_json(manifest_payload, label="manifest.json")
    except BackendPackageContractError as exc:
        blockers.append(str(exc))
        return BackendPackageReport(
            False,
            BACKEND_CAPABILITY_ID,
            BACKEND_PACKAGE_VERSION,
            BACKEND_PRIMARY_TYPE,
            BACKEND_ROLE,
            0,
            fingerprint,
            BACKEND_FORBIDDEN_BOUNDARIES,
            tuple(dict.fromkeys(blockers)),
            files=file_paths,
        )
    blockers.extend(_check_manifest(manifest))
    manifest_digest = digest_bytes(manifest_payload)
    declared_digest = _package_declared_digest(manifest)
    if declared_digest is not None and declared_digest != fingerprint:
        blockers.append("PACKAGE_FINGERPRINT_DECLARATION_MISMATCH")
    if "SKILL.md" not in file_paths:
        blockers.append("SKILL_MISSING")
    else:
        try:
            skill_payload = read_bounded_file(package, "SKILL.md", max_bytes=64 * 1024)
            skill_text = skill_payload.decode("utf-8")
        except (PathSafetyError, OSError, UnicodeDecodeError) as exc:
            blockers.append(f"SKILL_INVALID: {type(exc).__name__}")
        else:
            front_matter: dict[str, str] = {}
            for line in skill_text.splitlines():
                if line.strip() == "---":
                    continue
                if ":" in line and not line.startswith(" "):
                    key, value = line.split(":", 1)
                    clean_key = key.strip()
                    clean_value = value.strip().strip("'\"")
                    if clean_key and clean_key not in front_matter:
                        front_matter[clean_key] = clean_value
            if front_matter.get("name") != BACKEND_CAPABILITY_ID:
                blockers.append("SKILL_IDENTITY_MISMATCH")
            if front_matter.get("version") not in {None, manifest.get("version")}:
                blockers.append("SKILL_VERSION_MISMATCH")
            if front_matter.get("primary_type") not in {None, BACKEND_PRIMARY_TYPE}:
                blockers.append("SKILL_PRIMARY_TYPE_MISMATCH")
    scenario_count = 0
    benchmark_count = 0
    eval_errors: tuple[str, ...] = ("EVAL_CATALOG_MISSING",)
    benchmark_errors: tuple[str, ...] = ("BENCHMARK_CATALOG_MISSING",)
    procedure_errors: tuple[str, ...] = ()
    if "evals/scenarios.json" in file_paths:
        try:
            catalog = _read_package_json(
                package, "evals/scenarios.json", max_bytes=_MAX_METADATA_BYTES
            )
            eval_errors = _validate_eval_catalog(catalog)
            raw_scenarios = catalog.get("scenarios")
            scenario_count = len(raw_scenarios) if isinstance(raw_scenarios, list) else 0
        except BackendPackageContractError as exc:
            eval_errors = (str(exc),)
    if "benchmarks/benchmark-fixtures.json" in file_paths:
        try:
            benchmark = _read_package_json(
                package,
                "benchmarks/benchmark-fixtures.json",
                max_bytes=_MAX_METADATA_BYTES,
            )
            benchmark_errors = _validate_benchmark_catalog(benchmark)
            raw_records = benchmark.get("records", benchmark.get("fixtures"))
            benchmark_count = len(raw_records) if isinstance(raw_records, list) else 0
        except BackendPackageContractError as exc:
            benchmark_errors = (str(exc),)
    if "scripts/deterministic-procedures.json" in file_paths:
        try:
            procedure_errors = _validate_procedure_catalog(
                _read_package_json(
                    package,
                    "scripts/deterministic-procedures.json",
                    max_bytes=_MAX_METADATA_BYTES,
                )
            )
        except BackendPackageContractError as exc:
            procedure_errors = (str(exc),)
    blockers.extend(
        _validate_package_metadata(
            package,
            manifest,
            file_paths,
            scenario_count=scenario_count,
            benchmark_count=benchmark_count,
        )
    )
    blockers.extend(eval_errors)
    blockers.extend(benchmark_errors)
    blockers.extend(procedure_errors)
    if any(executable for _path, _size, executable, _digest in files):
        blockers.append("EXECUTABLE_PACKAGE_ENTRY")
    capability_id = manifest.get("capability_id")
    version = manifest.get("version")
    primary_type = manifest.get("primary_type")
    role = manifest.get("role")
    return BackendPackageReport(
        ok=not blockers,
        capability_id=capability_id if isinstance(capability_id, str) else BACKEND_CAPABILITY_ID,
        version=version if isinstance(version, str) else BACKEND_PACKAGE_VERSION,
        primary_type=primary_type if isinstance(primary_type, str) else BACKEND_PRIMARY_TYPE,
        role=role if isinstance(role, str) else BACKEND_ROLE,
        scenario_count=scenario_count,
        package_fingerprint=fingerprint,
        forbidden_boundaries=BACKEND_FORBIDDEN_BOUNDARIES,
        blockers=tuple(dict.fromkeys(blockers)),
        manifest_fingerprint=manifest_digest,
        files=file_paths,
        benchmark_count=benchmark_count,
    )


def _workspace_relative(path: Path, workspace: Path) -> str:
    try:
        return path.relative_to(workspace).as_posix()
    except ValueError as exc:
        raise BackendPackageContractError("workspace path escapes the workspace") from exc


def _safe_workspace(workspace: str | Path) -> Path:
    raw = Path(workspace)
    if not raw.is_absolute():
        raise BackendPackageContractError("workspace must be absolute")
    if _has_symlink_component(raw):
        raise BackendPackageContractError("workspace contains a symlink")
    try:
        metadata = raw.lstat()
    except (FileNotFoundError, OSError) as exc:
        raise BackendPackageContractError("workspace is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise BackendPackageContractError("workspace must be a regular directory")
    try:
        return raw.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BackendPackageContractError("workspace cannot be resolved") from exc


def _safe_allowed_root(root: str | Path, workspace: Path) -> Path:
    raw = Path(root)
    if not raw.is_absolute():
        raise BackendPackageContractError("allowed workspace roots must be absolute")
    if _has_symlink_component(raw):
        raise BackendPackageContractError("allowed workspace root contains a symlink")
    try:
        resolved = raw.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BackendPackageContractError("allowed workspace root is unavailable") from exc
    if not resolved.is_dir():
        raise BackendPackageContractError("allowed workspace root is not a directory")
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise BackendPackageContractError("allowed workspace root escapes the workspace") from exc
    relative = resolved.relative_to(workspace).parts
    if relative and relative[0] == ".agent":
        raise BackendPackageContractError("allowed workspace root is protected")
    if len(relative) >= 2 and relative[:2] == (".harness", "capabilities"):
        raise BackendPackageContractError("allowed workspace root is protected")
    return resolved


def _safe_declared_path(path: str | Path, *, workspace: Path | None = None) -> Path:
    raw = Path(path)
    if not raw.is_absolute():
        if workspace is None:
            raise BackendPackageContractError("declared path must be absolute")
        if any(part in {"", ".", ".."} for part in raw.parts):
            raise BackendPackageContractError("declared path contains traversal")
        raw = workspace / raw
    if "\x00" in str(raw) or _has_symlink_component(raw):
        raise BackendPackageContractError("declared path contains a symlink")
    return raw.resolve(strict=False)


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _protected_workspace_path(
    path: Path,
    *,
    workspace: Path,
    package_path: Path | None,
) -> bool:
    relative = path.relative_to(workspace).parts if _under(path, workspace) else ()
    if relative and relative[0] == ".agent":
        return True
    if len(relative) >= 2 and relative[0] == ".harness" and relative[1] == "capabilities":
        return True
    return package_path is not None and (_under(path, package_path) or _under(package_path, path))


def _current_workspace_signatures(
    workspace: Path,
    *,
    limits: Phase3Limits,
) -> tuple[dict[str, str], tuple[str, ...], tuple[str, ...]]:
    try:
        walked = bounded_walk(workspace, limits)
    except (PathSafetyError, OSError) as exc:
        raise BackendPackageContractError("workspace cannot be walked safely") from exc
    signatures: dict[str, str] = {}
    errors = tuple(walked.errors)
    unsafe = tuple(walked.unsafe_paths)
    directory_count = 0
    directory_queue: list[tuple[Path, str]] = [(workspace, "")]
    while directory_queue:
        current_directory, prefix = directory_queue.pop(0)
        try:
            entries = sorted(current_directory.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            errors += (f"{prefix or '.'}: {type(exc).__name__}",)
            continue
        for entry in entries:
            relative = f"{prefix}/{entry.name}" if prefix else entry.name
            try:
                metadata = entry.lstat()
            except OSError as exc:
                errors += (f"{relative}: {type(exc).__name__}",)
                continue
            if stat.S_ISLNK(metadata.st_mode):
                unsafe += (relative,)
                continue
            if not stat.S_ISDIR(metadata.st_mode):
                continue
            directory_count += 1
            if directory_count > limits.max_total_files:
                errors += ("workspace directory count bound exceeded",)
                continue
            mode = stat.S_IMODE(metadata.st_mode)
            signatures[relative] = digest_bytes(f"directory\0mode={mode:o}".encode("ascii"))
            if len(relative.split("/")) <= limits.max_depth:
                directory_queue.append((entry, relative))
            else:
                errors += (f"{relative}: depth bound",)
    max_file_bytes = max(
        limits.max_skill_bytes, limits.max_manifest_bytes, limits.max_reference_bytes
    )
    for relative in sorted(walked.files):
        try:
            before_metadata = (workspace / relative).lstat()
            if stat.S_ISLNK(before_metadata.st_mode) or not stat.S_ISREG(before_metadata.st_mode):
                unsafe += (relative,)
                continue
            before_mode = stat.S_IMODE(before_metadata.st_mode)
            payload = read_bounded_file(workspace, relative, max_bytes=max_file_bytes)
            after_metadata = (workspace / relative).lstat()
        except (PathSafetyError, OSError):
            errors += (f"{relative}: unreadable",)
            continue
        if (
            before_metadata.st_ino != after_metadata.st_ino
            or before_metadata.st_dev != after_metadata.st_dev
            or before_metadata.st_size != after_metadata.st_size
            or stat.S_IMODE(after_metadata.st_mode) != before_mode
        ):
            errors += (f"{relative}: changed during inspection",)
            continue
        signatures[relative] = digest_bytes(
            b"file\0mode=" + f"{before_mode:o}".encode("ascii") + b"\0" + payload
        )
    return signatures, unsafe, errors


def snapshot_workspace(
    workspace: str | Path,
    *,
    max_files: int = 256,
    max_bytes: int = 16 * 1024 * 1024,
) -> Mapping[str, str]:
    """Capture a redaction-safe relative-path to SHA-256 workspace snapshot."""

    if not isinstance(max_files, int) or isinstance(max_files, bool) or max_files < 1:
        raise BackendPackageContractError("max_files must be positive")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise BackendPackageContractError("max_bytes must be positive")
    workspace_path = _safe_workspace(workspace)
    limits = Phase3Limits(
        max_files_per_capability=max_files,
        max_total_files=max_files,
        max_total_bytes=max_bytes,
        max_skill_bytes=max_bytes,
        max_manifest_bytes=max_bytes,
        max_reference_bytes=max_bytes,
    )
    signatures, unsafe, errors = _current_workspace_signatures(workspace_path, limits=limits)
    if unsafe or errors:
        raise BackendPackageContractError("workspace snapshot contains unsafe entries")
    return MappingProxyType(dict(sorted(signatures.items())))


def _before_matches(value: object, payload: bytes, digest: str) -> bool:
    if isinstance(value, bytes):
        return value == payload
    if isinstance(value, str):
        return value == payload.decode("utf-8", errors="surrogateescape") or value == digest
    if isinstance(value, Mapping):
        declared = value.get("sha256", value.get("digest"))
        return bool(declared == digest)
    return False


def _delta_digest(
    changed: tuple[str, ...],
    unauthorized: tuple[str, ...],
    added: tuple[str, ...],
    removed: tuple[str, ...],
) -> str:
    payload = {
        "changed_paths": changed,
        "unauthorized_paths": unauthorized,
        "added_paths": added,
        "removed_paths": removed,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return digest_bytes(encoded)


def validate_workspace_delta(
    workspace: str | Path,
    before: Mapping[str, object],
    *,
    allowed_roots: tuple[str | Path, ...] = (),
    package_path: str | Path | None = None,
    max_files: int = 256,
    max_bytes: int = 16 * 1024 * 1024,
) -> WorkspaceDeltaReport:
    """Compare a bounded workspace snapshot and reject writes outside roots.

    ``before`` may contain raw text/bytes (useful for small tests), SHA-256
    strings from :func:`snapshot_workspace`, or mappings with a ``digest``
    field.  Current contents are never copied into the report.
    """

    try:
        workspace_path = _safe_workspace(workspace)
        if not isinstance(before, Mapping):
            raise BackendPackageContractError("workspace snapshot must be a mapping")
        if len(before) > max_files:
            raise BackendPackageContractError("workspace snapshot exceeds its file bound")
        limits = Phase3Limits(
            max_files_per_capability=max_files,
            max_total_files=max_files,
            max_total_bytes=max_bytes,
            max_skill_bytes=max_bytes,
            max_manifest_bytes=max_bytes,
            max_reference_bytes=max_bytes,
        )
        roots = tuple(
            dict.fromkeys(_safe_allowed_root(item, workspace_path) for item in allowed_roots)
        )
        protected_package = (
            _safe_declared_path(package_path, workspace=workspace_path)
            if package_path is not None
            else None
        )
        current, unsafe, errors = _current_workspace_signatures(workspace_path, limits=limits)
    except BackendPackageContractError as exc:
        return WorkspaceDeltaReport(
            ok=False,
            changed_paths=(),
            unauthorized_paths=(),
            digest=_delta_digest((), (), (), ()),
            errors=(str(exc),),
        )
    normalized_before: dict[str, object] = {}
    invalid_before: list[str] = []
    for raw_path, value in before.items():
        try:
            parts = _safe_path_parts(raw_path, field="workspace snapshot path")
        except BackendPackageContractError:
            invalid_before.append("__invalid_snapshot_path__")
            continue
        normalized_before["/".join(parts)] = value
    changed = sorted(
        set(normalized_before).symmetric_difference(current)
        | {
            path
            for path in set(normalized_before).intersection(current)
            if not _before_matches(normalized_before[path], b"", current[path])
        }
    )
    # The digest-only path above intentionally does not read contents.  Read
    # only entries whose prior value is raw content to distinguish a digest
    # snapshot from the small raw-value fixture used by the public contract.
    for path in tuple(changed):
        if path not in normalized_before or path not in current:
            continue
        previous = normalized_before[path]
        try:
            payload = read_bounded_file(workspace_path, path, max_bytes=max_bytes)
        except (PathSafetyError, OSError):
            continue
        if isinstance(previous, str) and _DIGEST_PATTERN.fullmatch(previous):
            unchanged_content = digest_bytes(payload) == previous
        elif isinstance(previous, Mapping) and _DIGEST_PATTERN.fullmatch(
            str(previous.get("sha256", previous.get("digest", "")))
        ):
            unchanged_content = digest_bytes(payload) == str(
                previous.get("sha256", previous.get("digest"))
            )
        else:
            unchanged_content = _before_matches(previous, payload, current[path])
        if unchanged_content:
            changed.remove(path)
    added = tuple(sorted(set(current).difference(normalized_before)))
    removed = tuple(sorted(set(normalized_before).difference(current)))
    unsafe_paths = tuple(sorted(set(unsafe) | set(invalid_before)))
    changed_paths = tuple(sorted(set(changed) | set(unsafe_paths)))
    unauthorized: set[str] = set(unsafe_paths)
    for relative in changed_paths:
        candidate = workspace_path / relative
        allowed = bool(roots) and any(_under(candidate, root) for root in roots)
        if _protected_workspace_path(
            candidate,
            workspace=workspace_path,
            package_path=protected_package,
        ):
            allowed = False
        if not allowed:
            unauthorized.add(relative)
    all_errors = tuple(sorted(set(errors)))
    return WorkspaceDeltaReport(
        ok=not unauthorized and not all_errors,
        changed_paths=changed_paths,
        unauthorized_paths=tuple(sorted(unauthorized)),
        added_paths=added,
        removed_paths=removed,
        digest=_delta_digest(
            changed_paths,
            tuple(sorted(unauthorized)),
            added,
            removed,
        ),
        errors=all_errors,
    )


workspace_delta = validate_workspace_delta
