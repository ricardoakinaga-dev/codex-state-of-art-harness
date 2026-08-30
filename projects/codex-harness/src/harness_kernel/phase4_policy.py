"""Exact-byte execution policy and preflight for the Phase 4 pilot boundary."""

from __future__ import annotations

import json
import os
import re
import stat
import time
import uuid
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .phase3_discovery import revalidate_capability
from .phase3_models import CapabilityInventory, CapabilityRecord, Phase3Limits, ResolutionResult
from .phase4_models import (
    CapabilityExecutionAuthorization,
    ContextManifest,
    ExecutionMode,
    Phase4Budget,
    PreflightResult,
    canonical_json,
    digest_payload,
    stable_digest_payload,
)


class Phase4PolicyError(ValueError):
    """Raised when a project policy cannot be safely represented."""


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")
_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|password|passwd|secret)\s*[:=]\s*[^\s,;]+"
)
_MAX_POLICY_BYTES = 128 * 1024
_MAX_POLICY_JSON_NESTING = 64


def _json_nesting_exceeds(payload: bytes, *, max_depth: int) -> bool:
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


def _read_policy_bytes(path: Path) -> bytes:
    if not hasattr(os, "O_NOFOLLOW"):
        raise Phase4PolicyError("policy file cannot be secured on this platform")
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise Phase4PolicyError("policy file is not a unique regular file")
        if metadata.st_size > _MAX_POLICY_BYTES:
            raise Phase4PolicyError("policy file exceeds its bound")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, _MAX_POLICY_BYTES - total + 1))
            if not chunk:
                return b"".join(chunks)
            total += len(chunk)
            if total > _MAX_POLICY_BYTES:
                raise Phase4PolicyError("policy file exceeds its bound")
            chunks.append(chunk)
    except Phase4PolicyError:
        raise
    except OSError as exc:
        raise Phase4PolicyError("policy file cannot be read safely") from exc
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)


def _tuple_strings(values: object, field_name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise Phase4PolicyError(f"{field_name} must be a list")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or "\x00" in value:
            raise Phase4PolicyError(f"{field_name} contains an invalid string")
        if value not in result:
            result.append(value)
    return tuple(result)


def _strict_bool(values: Mapping[str, object], key: str, default: bool = False) -> bool:
    value = values.get(key, default)
    if not isinstance(value, bool):
        raise Phase4PolicyError(f"{key} must be boolean")
    return value


def _metadata_only_scripts(record: CapabilityRecord) -> bool:
    """Recognize JSON procedure metadata without granting script execution."""

    if not record.scripts:
        return False
    files = {item.relative_path: item for item in record.files}
    return all(
        path.casefold().endswith(".json")
        and files.get(path) is not None
        and files[path].kind == "metadata_only"
        and not files[path].executable
        for path in record.scripts
    )


@dataclass(frozen=True, slots=True)
class PilotRule:
    capability_id: str
    version: str
    package_fingerprint: str
    execution_approved: bool = False
    allowed_modes: tuple[ExecutionMode, ...] = (ExecutionMode.DRY_RUN, ExecutionMode.PREPARE_ONLY)
    allowed_tools: tuple[str, ...] = ()
    allowed_side_effects: tuple[str, ...] = ()
    allowed_providers: tuple[str, ...] = ()
    allow_scripts: bool = False
    allow_network: bool = False
    allow_shell: bool = False
    allow_mcp: bool = False
    allow_credentials: bool = False
    expected_artifact_types: tuple[str, ...] = ("HOST_RESPONSE",)
    reason: str = "no execution permission granted"
    host_executable_digest: str | None = None
    host_interpreter_digest: str | None = None

    def __post_init__(self) -> None:
        if _ID_PATTERN.fullmatch(self.capability_id) is None:
            raise Phase4PolicyError("capability_id is invalid")
        if _VERSION_PATTERN.fullmatch(self.version) is None:
            raise Phase4PolicyError("version is invalid")
        if _DIGEST_PATTERN.fullmatch(self.package_fingerprint) is None:
            raise Phase4PolicyError("package_fingerprint is invalid")
        if (
            self.host_executable_digest is not None
            and _DIGEST_PATTERN.fullmatch(self.host_executable_digest) is None
        ):
            raise Phase4PolicyError("host_executable_digest is invalid")
        if (
            self.host_interpreter_digest is not None
            and _DIGEST_PATTERN.fullmatch(self.host_interpreter_digest) is None
        ):
            raise Phase4PolicyError("host_interpreter_digest is invalid")
        if not isinstance(self.execution_approved, bool):
            raise Phase4PolicyError("execution_approved must be boolean")
        if not self.reason or "\x00" in self.reason or len(self.reason) > 2_048:
            raise Phase4PolicyError("reason is invalid")
        object.__setattr__(
            self, "allowed_tools", _tuple_strings(self.allowed_tools, "allowed_tools")
        )
        object.__setattr__(
            self,
            "allowed_side_effects",
            _tuple_strings(self.allowed_side_effects, "allowed_side_effects"),
        )
        object.__setattr__(
            self,
            "allowed_providers",
            _tuple_strings(self.allowed_providers, "allowed_providers"),
        )
        object.__setattr__(
            self,
            "expected_artifact_types",
            _tuple_strings(self.expected_artifact_types, "expected_artifact_types"),
        )
        if any(
            item not in {"HOST_RESPONSE", "FILE", "VISUAL", "UNKNOWN"}
            for item in self.expected_artifact_types
        ):
            raise Phase4PolicyError("expected_artifact_types contains an unsupported type")
        modes: list[ExecutionMode] = []
        for mode in self.allowed_modes:
            if not isinstance(mode, ExecutionMode):
                raise Phase4PolicyError("allowed_modes contains an invalid mode")
            if mode is ExecutionMode.BLOCKED:
                raise Phase4PolicyError("BLOCKED cannot be an allowed mode")
            if mode not in modes:
                modes.append(mode)
        object.__setattr__(self, "allowed_modes", tuple(modes))


@dataclass(frozen=True, slots=True)
class ExecutionPolicyRegistry:
    rules: tuple[PilotRule, ...]
    schema_version: str = "P4-POLICY-1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules", tuple(self.rules))
        identities: set[tuple[str, str]] = set()
        for rule in self.rules:
            identity = (rule.capability_id, rule.version)
            if identity in identities:
                raise Phase4PolicyError("duplicate capability policy identity")
            identities.add(identity)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> ExecutionPolicyRegistry:
        if payload.get("schema_version") != "P4-POLICY-1":
            raise Phase4PolicyError("unsupported Phase 4 policy schema")
        raw_rules = payload.get("rules")
        if not isinstance(raw_rules, list):
            raise Phase4PolicyError("policy rules must be a list")
        if set(payload).difference({"schema_version", "rules"}):
            raise Phase4PolicyError("policy contains unsupported top-level fields")
        rules: list[PilotRule] = []
        for raw in raw_rules:
            if not isinstance(raw, Mapping):
                raise Phase4PolicyError("policy rule must be an object")
            supported_fields = {
                "capability_id",
                "version",
                "package_fingerprint",
                "execution_approved",
                "allowed_modes",
                "allowed_tools",
                "allowed_side_effects",
                "allowed_providers",
                "allow_scripts",
                "allow_network",
                "allow_shell",
                "allow_mcp",
                "allow_credentials",
                "expected_artifact_types",
                "reason",
                "host_executable_digest",
                "host_interpreter_digest",
            }
            if set(raw).difference(supported_fields):
                raise Phase4PolicyError("policy rule contains unsupported fields")
            raw_modes = _tuple_strings(
                raw.get(
                    "allowed_modes",
                    [ExecutionMode.DRY_RUN.value, ExecutionMode.PREPARE_ONLY.value],
                ),
                "allowed_modes",
            )
            modes = tuple(ExecutionMode(value) for value in raw_modes)
            rules.append(
                PilotRule(
                    capability_id=_required_string(raw, "capability_id"),
                    version=_required_string(raw, "version"),
                    package_fingerprint=_required_string(raw, "package_fingerprint"),
                    execution_approved=_strict_bool(raw, "execution_approved"),
                    allowed_modes=modes,
                    allowed_tools=_tuple_strings(raw.get("allowed_tools"), "allowed_tools"),
                    allowed_side_effects=_tuple_strings(
                        raw.get("allowed_side_effects"), "allowed_side_effects"
                    ),
                    allowed_providers=_tuple_strings(
                        raw.get("allowed_providers"), "allowed_providers"
                    ),
                    allow_scripts=_strict_bool(raw, "allow_scripts"),
                    allow_network=_strict_bool(raw, "allow_network"),
                    allow_shell=_strict_bool(raw, "allow_shell"),
                    allow_mcp=_strict_bool(raw, "allow_mcp"),
                    allow_credentials=_strict_bool(raw, "allow_credentials"),
                    expected_artifact_types=_tuple_strings(
                        raw.get("expected_artifact_types", ("HOST_RESPONSE",)),
                        "expected_artifact_types",
                    ),
                    reason=_required_string(raw, "reason"),
                    host_executable_digest=(
                        _required_string(raw, "host_executable_digest")
                        if "host_executable_digest" in raw
                        else None
                    ),
                    host_interpreter_digest=(
                        _required_string(raw, "host_interpreter_digest")
                        if "host_interpreter_digest" in raw
                        else None
                    ),
                )
            )
        return cls(tuple(rules))

    @classmethod
    def from_json(cls, path: str | Path) -> ExecutionPolicyRegistry:
        candidate = Path(path)
        try:
            content = _read_policy_bytes(candidate)
            if _json_nesting_exceeds(content, max_depth=_MAX_POLICY_JSON_NESTING):
                raise Phase4PolicyError("policy JSON nesting exceeds its bound")
            payload = json.loads(
                content.decode("utf-8"),
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON constant is not allowed: {value}")
                ),
            )
        except Phase4PolicyError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise Phase4PolicyError("policy file cannot be read safely") from exc
        if not isinstance(payload, Mapping):
            raise Phase4PolicyError("policy file must contain an object")
        return cls.from_mapping(payload)

    def rule_for_identity(self, capability_id: str, version: str) -> PilotRule | None:
        return next(
            (
                rule
                for rule in self.rules
                if rule.capability_id == capability_id and rule.version == version
            ),
            None,
        )

    def rule_for_record(self, record: CapabilityRecord) -> PilotRule | None:
        rule = self.rule_for_identity(record.capability_id, record.version)
        if rule is None or rule.package_fingerprint != record.content_hash:
            return None
        return rule

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "rules": [
                {
                    "capability_id": rule.capability_id,
                    "version": rule.version,
                    "package_fingerprint": rule.package_fingerprint,
                    "execution_approved": rule.execution_approved,
                    "allowed_modes": [mode.value for mode in rule.allowed_modes],
                    "allowed_tools": list(rule.allowed_tools),
                    "allowed_side_effects": list(rule.allowed_side_effects),
                    "allowed_providers": list(rule.allowed_providers),
                    "allow_scripts": rule.allow_scripts,
                    "allow_network": rule.allow_network,
                    "allow_shell": rule.allow_shell,
                    "allow_mcp": rule.allow_mcp,
                    "allow_credentials": rule.allow_credentials,
                    "expected_artifact_types": list(rule.expected_artifact_types),
                    "reason": rule.reason,
                    "host_executable_digest": rule.host_executable_digest,
                    "host_interpreter_digest": rule.host_interpreter_digest,
                }
                for rule in self.rules
            ],
        }


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise Phase4PolicyError(f"{key} is required")
    return value


def _workspace_root(
    inventory: CapabilityInventory, workspace: Path
) -> tuple[Path | None, str | None]:
    if not workspace.is_absolute():
        return None, "WORKSPACE_MUST_BE_ABSOLUTE"
    try:
        metadata = workspace.lstat()
    except FileNotFoundError:
        return None, "WORKSPACE_MISSING"
    except OSError:
        return None, "WORKSPACE_UNAVAILABLE"
    if (
        workspace.is_symlink()
        or stat.S_ISLNK(metadata.st_mode)
        or _has_symlink_component(workspace)
    ):
        return None, "WORKSPACE_SYMLINK"
    if not workspace.is_dir():
        return None, "WORKSPACE_NOT_DIRECTORY"
    try:
        resolved = workspace.resolve(strict=True)
    except (OSError, RuntimeError):
        return None, "WORKSPACE_UNAVAILABLE"
    project_roots = [
        Path(root.canonical_path or root.path)
        for root in inventory.roots
        if str(root.scope) == "PROJECT"
    ]
    project_candidates: list[Path] = []
    for root in project_roots:
        try:
            candidate = root.resolve(strict=False).parent.parent
        except (OSError, RuntimeError):
            continue
        if candidate.is_dir():
            project_candidates.append(candidate)
    if not project_candidates:
        return None, "PROJECT_ROOT_UNAVAILABLE"
    if not any(
        resolved == candidate or resolved.is_relative_to(candidate)
        for candidate in project_candidates
    ):
        return None, "WORKSPACE_OUTSIDE_PROJECT"
    return resolved, None


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return True
        if stat.S_ISLNK(metadata.st_mode):
            return True
    return False


def _safe_skill_path(record: CapabilityRecord) -> tuple[Path | None, str | None]:
    if not record.skill_md:
        return None, "SKILL_SOURCE_MISSING"
    package = Path(record.path)
    relative_skill = Path(record.skill_md)
    if (
        not package.is_absolute()
        or relative_skill.is_absolute()
        or any(part in {"", ".", ".."} for part in relative_skill.parts)
    ):
        return None, "SKILL_SOURCE_ESCAPE"
    if _has_symlink_component(package):
        return None, "SKILL_SOURCE_SYMLINK"
    candidate = package / relative_skill
    if _has_symlink_component(candidate):
        return None, "SKILL_SOURCE_SYMLINK"
    try:
        resolved_package = package.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None, "SKILL_SOURCE_UNAVAILABLE"
    if not resolved_candidate.is_relative_to(resolved_package):
        return None, "SKILL_SOURCE_ESCAPE"
    if not resolved_candidate.is_file():
        return None, "SKILL_SOURCE_MISSING"
    return resolved_candidate, None


def _estimated_context(
    record: CapabilityRecord, budget: Phase4Budget
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    file_sizes = {item.relative_path: item.size_bytes for item in record.files}
    skill_size = file_sizes.get(record.skill_md or "SKILL.md", 0)
    references = tuple(record.references)
    selected: list[str] = []
    omitted: list[str] = []
    total = skill_size
    for reference in references:
        size = file_sizes.get(reference, 0)
        if total + size <= budget.max_context_bytes:
            selected.append(reference)
            total += size
        else:
            omitted.append(reference)
    return total, tuple(selected), tuple(omitted)


def _compute_preflight_digest(
    *,
    allowed: bool,
    mode: ExecutionMode,
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
    authorization: CapabilityExecutionAuthorization | None,
    context: ContextManifest | None,
    workspace: str | Path | None = None,
) -> str:
    return stable_digest_payload(
        {
            "allowed": allowed,
            "mode": mode,
            "blockers": blockers,
            "warnings": warnings,
            "authorization": authorization,
            "context": context,
        },
        workspace=workspace,
    )


def preflight_digest(preflight: PreflightResult) -> str:
    """Recompute the digest over the exact preflight binding fields."""

    workspace: str | None = None
    if preflight.authorization is not None:
        candidate = preflight.authorization.filesystem_policy.get("workspace")
        if isinstance(candidate, str):
            workspace = candidate
    return _compute_preflight_digest(
        allowed=preflight.allowed,
        mode=preflight.mode,
        blockers=preflight.blockers,
        warnings=preflight.warnings,
        authorization=preflight.authorization,
        context=preflight.context,
        workspace=workspace,
    )


def build_preflight(
    record: CapabilityRecord,
    inventory: CapabilityInventory,
    resolution: ResolutionResult,
    policy: ExecutionPolicyRegistry,
    *,
    task_id: str,
    run_id: str,
    task: str,
    acceptance_criteria: tuple[str, ...],
    workspace: str | Path,
    mode: ExecutionMode,
    budget: Phase4Budget,
    now: int | None = None,
) -> PreflightResult:
    blockers: list[str] = []
    warnings: list[str] = []
    criteria_values = (
        tuple(acceptance_criteria) if isinstance(acceptance_criteria, (list, tuple)) else ()
    )
    task_valid = isinstance(task, str) and bool(task) and "\x00" not in task and len(task) <= 16_384
    if not task_valid:
        blockers.append("TASK_INVALID")
    criteria_valid = bool(criteria_values)
    if not criteria_valid or any(
        not isinstance(item, str) or not item or "\x00" in item or len(item) > 2_048
        for item in criteria_values
    ):
        blockers.append("ACCEPTANCE_CRITERIA_INVALID")
    if (isinstance(task, str) and _SECRET_PATTERN.search(task)) or any(
        isinstance(item, str) and _SECRET_PATTERN.search(item) for item in criteria_values
    ):
        blockers.append("CREDENTIAL_INPUT_FORBIDDEN")
    if mode is ExecutionMode.BLOCKED:
        blockers.append("EXECUTION_MODE_BLOCKED")
    if blockers:
        return _blocked_preflight(mode, blockers, warnings)
    if resolution.status.value != "RESOLVED" or not resolution.selected:
        blockers.append("CAPABILITY_NOT_RESOLVED")
    record_identity = (
        record.capability_id,
        record.version,
        record.content_hash,
        record.root_id,
        record.path,
    )
    selected_identities = {
        (
            item.capability_id,
            item.version,
            item.content_hash,
            item.root_id,
            item.path,
        )
        for item in resolution.selected
    }
    if record_identity not in selected_identities or record_identity not in {
        (
            item.capability_id,
            item.version,
            item.content_hash,
            item.root_id,
            item.path,
        )
        for item in inventory.capabilities
    }:
        blockers.append("RESOLUTION_RECORD_MISMATCH")
    if record.status.value in {"REJECTED", "INCOMPATIBLE", "STALE", "AMBIGUOUS"}:
        blockers.append("CAPABILITY_STATUS_BLOCKED")
    if record.kind.value == "INVALID":
        blockers.append("CAPABILITY_KIND_BLOCKED")
    if (
        record.trust.level.value == "REJECTED"
        or record.compatibility.status.value == "INCOMPATIBLE"
    ):
        blockers.append("CAPABILITY_TRUST_OR_COMPATIBILITY_BLOCKED")

    rule = policy.rule_for_identity(record.capability_id, record.version)
    if rule is None:
        blockers.append("BLOCKED_EXECUTION_POLICY")
    else:
        metadata_only_scripts = _metadata_only_scripts(record)
        if rule.package_fingerprint != record.content_hash:
            blockers.append("CAPABILITY_FINGERPRINT_MISMATCH")
        if not rule.execution_approved and mode is ExecutionMode.CONTROLLED_REAL:
            blockers.append("BLOCKED_EXECUTION_POLICY")
        if mode not in rule.allowed_modes:
            blockers.append("EXECUTION_MODE_NOT_ALLOWED")
        if mode is ExecutionMode.CONTROLLED_REAL:
            if rule.host_executable_digest is None:
                blockers.append("HOST_EXECUTABLE_NOT_BOUND")
            if rule.host_interpreter_digest is None:
                blockers.append("HOST_INTERPRETER_NOT_BOUND")
            if record.scripts and not rule.allow_scripts and not metadata_only_scripts:
                blockers.append("FORBIDDEN_SCRIPT")
            undeclared_tools = set(record.manifest.tools).difference(rule.allowed_tools)
            if undeclared_tools:
                blockers.append("FORBIDDEN_TOOL")
            undeclared_providers = set(record.manifest.providers).difference(rule.allowed_providers)
            if undeclared_providers:
                blockers.append("FORBIDDEN_PROVIDER")
            if record.dependencies:
                blockers.append("DEPENDENCY_NOT_INDEPENDENTLY_APPROVED")
            if record.manifest.tools or rule.allowed_tools:
                blockers.append("HOST_TOOL_POLICY_UNSUPPORTED")
            if record.manifest.providers or rule.allowed_providers:
                blockers.append("HOST_PROVIDER_POLICY_UNSUPPORTED")
            if rule.allowed_side_effects:
                blockers.append("HOST_SIDE_EFFECT_POLICY_UNSUPPORTED")
            if rule.allow_network:
                blockers.append("HOST_NETWORK_POLICY_UNSUPPORTED")
            if rule.allow_shell:
                blockers.append("HOST_SHELL_POLICY_UNSUPPORTED")
            if rule.allow_mcp:
                blockers.append("HOST_MCP_POLICY_UNSUPPORTED")
            if rule.allow_credentials:
                blockers.append("HOST_CREDENTIAL_POLICY_UNSUPPORTED")
        else:
            if record.scripts:
                warnings.append("SCRIPTS_PRESENT_NOT_EXECUTED")
                if metadata_only_scripts:
                    warnings.append("SCRIPTS_METADATA_ONLY")
            if record.dependencies:
                warnings.append("DEPENDENCIES_NOT_EXECUTED")
        if not rule.allow_network:
            warnings.append("NETWORK_DENIED")
        if not rule.allow_shell:
            warnings.append("SHELL_DENIED")
        if not rule.allow_mcp:
            warnings.append("MCP_DENIED")
        if not rule.allow_credentials:
            warnings.append("CREDENTIALS_DENIED")

    workspace_path, workspace_error = _workspace_root(inventory, Path(workspace))
    if workspace_error:
        blockers.append(workspace_error)
    skill_path, skill_error = _safe_skill_path(record)
    if skill_error:
        blockers.append(skill_error)

    fresh, freshness_reason = revalidate_capability(record, Phase3Limits())
    if not fresh:
        blockers.append("CAPABILITY_STALE_BEFORE_EXECUTION")
        warnings.append(freshness_reason)

    if workspace_path is None or skill_path is None:
        return _blocked_preflight(mode, blockers, warnings)

    estimated_bytes, selected_refs, omitted_refs = _estimated_context(record, budget)
    if estimated_bytes > budget.max_context_bytes:
        blockers.append("CONTEXT_BUDGET_EXCEEDED")
    if omitted_refs:
        warnings.append("CONTEXT_REFERENCES_OMITTED_BY_BUDGET")
    context_payload = {
        "task_id": task_id,
        "task_digest": digest_payload(task),
        "capability_id": record.capability_id,
        "package_fingerprint": record.content_hash,
        "skill_path": str(skill_path),
        "sources": ("HOST_MANAGED_SKILL",),
        "selected_references": selected_refs,
        "omitted_references": omitted_refs,
        "estimated_bytes": estimated_bytes,
        "acceptance_criteria": criteria_values,
    }
    context = ContextManifest(
        task_id=task_id,
        task_digest=digest_payload(task),
        capability_id=record.capability_id,
        package_fingerprint=record.content_hash,
        skill_path=str(skill_path),
        sources=("HOST_MANAGED_SKILL",),
        selected_references=selected_refs,
        omitted_references=omitted_refs,
        estimated_bytes=estimated_bytes,
        digest=stable_digest_payload(context_payload, workspace=workspace_path),
        acceptance_criteria=criteria_values,
    )
    issued_at = int(time.time()) if now is None else now
    authorization_payload = {
        "task_id": task_id,
        "run_id": run_id,
        "capability_id": record.capability_id,
        "version": record.version,
        "fingerprint": record.content_hash,
        "mode": mode,
        "context": context.digest,
        "host_executable_digest": rule.host_executable_digest if rule is not None else None,
        "host_interpreter_digest": rule.host_interpreter_digest if rule is not None else None,
        "issued_at": issued_at,
    }
    authorization_id = (
        "AUTH-" + uuid.uuid5(uuid.NAMESPACE_URL, canonical_json(authorization_payload)).hex[:24]
    )
    authorization = CapabilityExecutionAuthorization(
        authorization_id=authorization_id,
        task_id=task_id,
        run_id=run_id,
        capability_id=record.capability_id,
        capability_version=record.version,
        package_fingerprint=record.content_hash,
        scope=record.scope.value,
        requested_loading_level="L2_INSTRUCTION_KERNEL",
        requested_execution_mode=mode,
        allowed_tools=rule.allowed_tools if rule is not None else (),
        allowed_side_effects=rule.allowed_side_effects if rule is not None else (),
        filesystem_policy={
            "workspace": str(workspace_path),
            "mode": "READ_ONLY",
            "artifact_root": str(workspace_path / ".harness" / "phase4" / "artifacts"),
            "host_executable_digest": rule.host_executable_digest if rule is not None else None,
            "host_interpreter_digest": rule.host_interpreter_digest if rule is not None else None,
        },
        network_policy="ALLOW" if rule is not None and rule.allow_network else "DENY",
        shell_policy="ALLOW" if rule is not None and rule.allow_shell else "DENY",
        provider_policy="ALLOW_SELECTED" if rule is not None and rule.allowed_providers else "DENY",
        mcp_policy="ALLOW" if rule is not None and rule.allow_mcp else "DENY",
        credential_policy="ALLOW" if rule is not None and rule.allow_credentials else "DENY",
        timeout_seconds=budget.timeout_seconds,
        iteration_budget={
            "host_calls": 1,
            "tool_calls": budget.max_tool_calls,
            "repair_iterations": budget.max_repair_iterations,
            "verification_iterations": budget.max_verification_iterations,
        },
        context_budget={"max_bytes": budget.max_context_bytes},
        artifact_policy={
            "types": rule.expected_artifact_types if rule is not None else (),
            "max_count": budget.max_artifacts,
            "max_bytes": budget.max_output_bytes,
        },
        evidence_policy={"max_events": budget.max_host_events, "max_count": budget.max_evidence},
        issued_by="phase4-preflight",
        issued_at=issued_at,
        expires_at=issued_at + budget.timeout_seconds,
        reason=rule.reason if rule is not None else "blocked",
        constraints=(
            "no arbitrary shell",
            "no scripts",
            "no network",
            "no MCP",
            "no providers",
            "no credentials",
            "no subagents",
        ),
        host_executable_digest=rule.host_executable_digest if rule is not None else None,
        host_interpreter_digest=rule.host_interpreter_digest if rule is not None else None,
    )
    if mode is ExecutionMode.CONTROLLED_REAL and rule is not None and not rule.execution_approved:
        blockers.append("BLOCKED_EXECUTION_POLICY")
    allowed = not blockers
    unique_blockers = tuple(dict.fromkeys(blockers))
    unique_warnings = tuple(dict.fromkeys(warnings))
    digest = _compute_preflight_digest(
        allowed=allowed,
        mode=mode,
        blockers=unique_blockers,
        warnings=unique_warnings,
        authorization=authorization if not blockers else None,
        context=context if not blockers else None,
        workspace=workspace_path,
    )
    return PreflightResult(
        allowed=allowed,
        mode=mode,
        blockers=unique_blockers,
        warnings=unique_warnings,
        authorization=authorization if not blockers else None,
        context=context if not blockers else None,
        digest=digest,
    )


def _blocked_preflight(
    mode: ExecutionMode,
    blockers: list[str],
    warnings: list[str],
) -> PreflightResult:
    unique_blockers = tuple(dict.fromkeys(blockers))
    unique_warnings = tuple(dict.fromkeys(warnings))
    return PreflightResult(
        allowed=False,
        mode=mode,
        blockers=unique_blockers,
        warnings=unique_warnings,
        authorization=None,
        context=None,
        digest=digest_payload(
            {
                "allowed": False,
                "mode": mode,
                "blockers": unique_blockers,
                "warnings": unique_warnings,
                "authorization": None,
                "context": None,
            }
        ),
    )
