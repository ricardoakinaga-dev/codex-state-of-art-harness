"""Project-local Phase 6 discovery and Phase 4 preflight integration."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .phase3_discovery import CapabilityDiscovery, DiscoveryError
from .phase3_host import CodexHostAdapter
from .phase3_loader import SafeCapabilityLoader
from .phase3_models import (
    CapabilityInventory,
    CapabilityKind,
    CapabilityLifecycle,
    CapabilityRecord,
    DisclosureLevel,
    LoadResult,
    Phase3Limits,
    RootScope,
)
from .phase3_paths import PathSafetyError, canonicalize_root, digest_bytes, read_bounded_file
from .phase3_resolution import ResolutionEngine
from .phase4_execution import InvocationEngine
from .phase4_host import CodexAppServerAdapter
from .phase4_models import (
    CapabilityInvocationRequest,
    ExecutionMode,
    Phase4Budget,
    PreparedInvocation,
)
from .phase4_policy import ExecutionPolicyRegistry, Phase4PolicyError
from .phase6_models import digest_payload


class Phase6HostError(ValueError):
    """Raised when a Phase 6 host boundary cannot be represented safely."""


def _reject_non_finite_json(value: str) -> object:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


class Phase6AppServerAdapter(CodexAppServerAdapter):
    """Use the official app-server with an explicit local-package fallback."""

    @staticmethod
    def _project_local_skill_is_bound(request: CapabilityInvocationRequest) -> bool:
        """Validate the local route without relabeling it as host discovery."""

        if request.skill_name != "verification-loop-vnext":
            return False
        candidate = Path(request.skill_path)
        if candidate.name != "SKILL.md":
            return False
        try:
            resolved = candidate.resolve(strict=True)
            if resolved != candidate:
                return False
            package_root = resolved.parent
            if (
                package_root.name != request.skill_name
                or package_root.parent.name != "capabilities"
                or package_root.parent.parent.name != ".harness"
            ):
                return False
            project_root = package_root.parent.parent.parent
            workspace = Path(request.workspace).resolve(strict=True)
            if project_root not in workspace.parents and workspace != project_root:
                return False
            capabilities_root = canonicalize_root(
                project_root / ".harness" / "capabilities",
                root_id="phase6.fallback",
                scope=RootScope.PROJECT,
                source="Phase 6 strict local fallback",
                allow_missing=False,
            )
            inventory = CapabilityDiscovery(Phase3Limits()).scan(
                (capabilities_root,),
            )
            if inventory.errors:
                return False
            matches = tuple(
                item for item in inventory.capabilities if item.path == str(package_root)
            )
            manifest_bytes = read_bounded_file(
                package_root,
                "manifest.json",
                max_bytes=128 * 1024,
            )
            manifest = json.loads(
                manifest_bytes.decode("utf-8"),
                parse_constant=_reject_non_finite_json,
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            RecursionError,
            PathSafetyError,
            DiscoveryError,
            ValueError,
        ):
            return False
        if len(matches) != 1:
            return False
        record = matches[0]
        scope = manifest.get("scope") if isinstance(manifest, Mapping) else None
        execution_policy = (
            manifest.get("execution_policy") if isinstance(manifest, Mapping) else None
        )
        security = manifest.get("security") if isinstance(manifest, Mapping) else None
        if not (
            isinstance(manifest, Mapping)
            and isinstance(scope, Mapping)
            and isinstance(execution_policy, Mapping)
            and isinstance(security, Mapping)
        ):
            return False
        return (
            record.kind is CapabilityKind.NATIVE
            and record.status is CapabilityLifecycle.INSPECTED
            and record.load_eligibility == "ELIGIBLE_DECLARATIVE_METADATA_ONLY"
            and record.path == str(package_root)
            and record.skill_md == "SKILL.md"
            and record.manifest_path == "manifest.json"
            and record.version == request.authorization.capability_version
            and record.content_hash == request.authorization.package_fingerprint
            and record.manifest.capability_id == request.skill_name
            and record.manifest.primary_type == "VERIFIER"
            and record.manifest.tools == ()
            and record.manifest.providers == ()
            and manifest.get("capability_id") == request.skill_name
            and manifest.get("version") == request.authorization.capability_version
            and manifest.get("type") == "VERIFIER"
            and manifest.get("role") == "VERIFIER"
            and manifest.get("primary_type") == "VERIFIER"
            and manifest.get("status") == "CANDIDATE"
            and manifest.get("registry_bridge") is False
            and manifest.get("allowed_tools") == []
            and manifest.get("read_only") is True
            and scope.get("scope") == "PROJECT"
            and scope.get("installation_scope") == "PROJECT"
            and execution_policy.get("allowed_tools") == []
            and execution_policy.get("shell") == "deny"
            and execution_policy.get("network") == "deny"
            and execution_policy.get("mcp") == "deny"
            and execution_policy.get("provider") == "deny"
            and execution_policy.get("credential") == "deny"
            and execution_policy.get("credentials") == "deny"
            and execution_policy.get("workspace_write") == "deny"
            and execution_policy.get("arbitrary_interpolation") == "deny"
            and security.get("read_only") is True
            and security.get("allowed_tools") == []
            and isinstance(security.get("credential"), Mapping)
            and security["credential"].get("allowed") is False
            and isinstance(security.get("workspace_write"), Mapping)
            and security["workspace_write"].get("allowed") is False
            and isinstance(security.get("credentials"), Mapping)
            and security["credentials"].get("allowed") is False
        )

    @staticmethod
    def _skill_is_discovered(
        response: Mapping[str, object], request: CapabilityInvocationRequest
    ) -> bool:
        # The official response is useful telemetry, but package identity must
        # still be proven locally before this vNext adapter proceeds.
        return Phase6AppServerAdapter._project_local_skill_is_bound(request)


@dataclass(frozen=True, slots=True)
class Phase6HostSnapshot:
    """Fresh native discovery plus bounded declarative loading observations."""

    project_root: str
    capability_id: str
    record: CapabilityRecord | None
    inventory: CapabilityInventory
    load_result: LoadResult | None
    load_level: DisclosureLevel
    instruction_loaded: bool
    host_load_observation: str
    package_digest: str | None
    manifest_digest: str | None
    blockers: tuple[str, ...] = ()
    digest: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.project_root, str) or not self.project_root.startswith("/"):
            raise Phase6HostError("project_root must be absolute")
        if not isinstance(self.capability_id, str) or not self.capability_id:
            raise Phase6HostError("capability_id is required")
        if self.record is not None and self.record.capability_id != self.capability_id:
            raise Phase6HostError("discovered record does not match capability_id")
        if self.package_digest is not None and not self.package_digest.startswith("sha256:"):
            raise Phase6HostError("package_digest is invalid")
        if self.manifest_digest is not None and not self.manifest_digest.startswith("sha256:"):
            raise Phase6HostError("manifest_digest is invalid")
        object.__setattr__(self, "blockers", tuple(self.blockers))
        if self.digest:
            expected = self._computed_digest()
            if self.digest != expected:
                raise Phase6HostError("host snapshot digest does not match its content")
        else:
            object.__setattr__(self, "digest", self._computed_digest())

    def _computed_digest(self) -> str:
        return digest_payload(
            {
                "project_root": self.project_root,
                "capability_id": self.capability_id,
                "package_digest": self.package_digest,
                "manifest_digest": self.manifest_digest,
                "inventory_fingerprint": self.inventory.fingerprint,
                "load_level": self.load_level.value,
                "instruction_loaded": self.instruction_loaded,
                "host_load_observation": self.host_load_observation,
                "blockers": self.blockers,
            }
        )


@dataclass(frozen=True, slots=True)
class Phase6Preflight:
    """Phase 4 preflight receipt for an exact vNext record."""

    snapshot: Phase6HostSnapshot
    mode: ExecutionMode
    allowed: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    prepared: PreparedInvocation | None
    host_invoked: bool = False
    digest: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ExecutionMode):
            raise Phase6HostError("preflight mode is invalid")
        object.__setattr__(self, "blockers", tuple(dict.fromkeys(self.blockers)))
        object.__setattr__(self, "warnings", tuple(dict.fromkeys(self.warnings)))
        if self.allowed and (self.blockers or self.prepared is None):
            raise Phase6HostError("allowed preflight must carry a prepared invocation")
        if self.prepared is not None and self.prepared.preflight.allowed != self.allowed:
            raise Phase6HostError("preflight status is not bound to Phase 4 preparation")
        if self.host_invoked:
            raise Phase6HostError("preflight cannot claim host invocation")
        if self.digest:
            expected = self._computed_digest()
            if self.digest != expected:
                raise Phase6HostError("preflight digest does not match its content")
        else:
            object.__setattr__(self, "digest", self._computed_digest())

    def _computed_digest(self) -> str:
        return digest_payload(
            {
                "snapshot_digest": self.snapshot.digest,
                "mode": self.mode.value,
                "allowed": self.allowed,
                "blockers": self.blockers,
                "warnings": self.warnings,
                "phase4_digest": self.prepared.preflight.digest if self.prepared else None,
                "prepared_invocation_id": (
                    self.prepared.request.invocation_id
                    if self.prepared is not None and self.prepared.request is not None
                    else None
                ),
            }
        )


def _root(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise Phase6HostError(f"{label} must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise Phase6HostError(f"{label} is unavailable") from exc
    if not resolved.is_dir():
        raise Phase6HostError(f"{label} must be a directory")
    return resolved


def _manifest_digest(record: CapabilityRecord) -> str | None:
    if record.manifest_path is None:
        return None
    try:
        content = read_bounded_file(record.path, record.manifest_path, max_bytes=128 * 1024)
        return digest_bytes(content)
    except (OSError, PathSafetyError):
        return None


def discover_vnext_package(project_root: str | Path) -> Phase6HostSnapshot:
    """Discover exactly one native vNext package and load only its kernel."""

    root = _root(project_root, "project_root")
    adapter = CodexHostAdapter(project_root=root, workspace_root=root, home_dir=Path.home())
    try:
        inventory = adapter.discover_capabilities()
    except (DiscoveryError, OSError, PathSafetyError, RuntimeError) as exc:
        error = f"DISCOVERY_FAILED:{type(exc).__name__}"
        inventory = CapabilityInventory(
            roots=(),
            capabilities=(),
            errors=(error,),
            observed_at=str(int(time.time())),
            fingerprint=digest_payload({"project_root": str(root), "error": error}),
        )
    matches = tuple(
        item for item in inventory.capabilities if item.capability_id == "verification-loop-vnext"
    )
    blockers: list[str] = []
    if any(
        error.startswith("project.harness:") or error.startswith("project.harness/")
        for error in inventory.errors
    ):
        blockers.append("PROJECT_VNEXT_DISCOVERY_ERRORS")
    record: CapabilityRecord | None = None
    if not matches:
        blockers.append("CAPABILITY_NOT_DISCOVERED")
    elif len(matches) != 1:
        blockers.append("DUPLICATE_CAPABILITY")
    else:
        record = matches[0]
        if record.kind is not CapabilityKind.NATIVE:
            blockers.append("CAPABILITY_NOT_NATIVE")
        if record.status is not CapabilityLifecycle.INSPECTED:
            blockers.append("CAPABILITY_STATUS_BLOCKED")
        if record.load_eligibility != "ELIGIBLE_DECLARATIVE_METADATA_ONLY":
            blockers.append("CAPABILITY_LOAD_NOT_ELIGIBLE")
    load_result: LoadResult | None = None
    if record is not None and not blockers:
        load_result = SafeCapabilityLoader().load(record, DisclosureLevel.INSTRUCTION_KERNEL)
        if not load_result.context_prepared or load_result.instruction_kernel is None:
            blockers.append("INSTRUCTION_KERNEL_UNAVAILABLE")
    package_digest = record.content_hash if record is not None else None
    manifest_digest = _manifest_digest(record) if record is not None else None
    load_level = DisclosureLevel.INSTRUCTION_KERNEL
    return Phase6HostSnapshot(
        project_root=str(root),
        capability_id="verification-loop-vnext",
        record=record,
        inventory=inventory,
        load_result=load_result,
        load_level=load_level,
        instruction_loaded=load_result is not None and load_result.instruction_kernel is not None,
        host_load_observation=(
            load_result.host_load.status.value if load_result is not None else "UNAVAILABLE"
        ),
        package_digest=package_digest,
        manifest_digest=manifest_digest,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def _policy(path: str | Path | None, project_root: Path) -> ExecutionPolicyRegistry:
    if path is None:
        return ExecutionPolicyRegistry(())
    candidate = Path(path)
    try:
        candidate.lstat()
    except FileNotFoundError:
        return ExecutionPolicyRegistry(())
    except OSError as exc:
        raise Phase6HostError("Phase 6 execution policy cannot be loaded safely") from exc
    try:
        relative = candidate.resolve(strict=False).relative_to(project_root)
        content = read_bounded_file(project_root, relative.as_posix(), max_bytes=128 * 1024)
        payload = json.loads(content.decode("utf-8"))
    except (
        OSError,
        PathSafetyError,
        UnicodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as exc:
        raise Phase6HostError("Phase 6 execution policy cannot be loaded safely") from exc
    if not isinstance(payload, Mapping):
        raise Phase6HostError("Phase 6 execution policy must be an object")
    try:
        return ExecutionPolicyRegistry.from_mapping(payload)
    except Phase4PolicyError as exc:
        raise Phase6HostError("Phase 6 execution policy cannot be loaded safely") from exc


def prepare_vnext_preflight(
    project_root: str | Path,
    *,
    snapshot: Phase6HostSnapshot | None = None,
    task_id: str,
    run_id: str,
    task: str,
    acceptance_criteria: tuple[str, ...],
    workspace: str | Path | None = None,
    policy_path: str | Path | None = None,
    mode: ExecutionMode = ExecutionMode.PREPARE_ONLY,
    budget: Phase4Budget | None = None,
) -> Phase6Preflight:
    """Run the existing Phase 4 preflight for the fresh vNext discovery."""

    root = _root(project_root, "project_root")
    selected_snapshot = snapshot or discover_vnext_package(root)
    if Path(selected_snapshot.project_root).resolve(strict=False) != root:
        raise Phase6HostError("preflight snapshot is bound to a different project root")
    selected_workspace = _root(workspace or project_root, "workspace")
    if selected_snapshot.record is None or selected_snapshot.blockers:
        return Phase6Preflight(
            snapshot=selected_snapshot,
            mode=mode,
            allowed=False,
            blockers=(*selected_snapshot.blockers, "CAPABILITY_NOT_ELIGIBLE"),
            warnings=(),
            prepared=None,
        )
    resolution = ResolutionEngine().resolve(
        selected_snapshot.inventory, selected_snapshot.capability_id
    )
    try:
        policy = _policy(policy_path, root)
    except Phase6HostError as exc:
        return Phase6Preflight(
            snapshot=selected_snapshot,
            mode=mode,
            allowed=False,
            blockers=("EXECUTION_POLICY_UNAVAILABLE", str(exc)),
            warnings=(),
            prepared=None,
        )
    engine = InvocationEngine(Phase6AppServerAdapter(), clock=lambda: int(time.time()))
    prepared = engine.prepare(
        selected_snapshot.record,
        selected_snapshot.inventory,
        resolution,
        policy,
        task_id=task_id,
        run_id=run_id,
        task=task,
        acceptance_criteria=acceptance_criteria,
        workspace=selected_workspace,
        mode=mode,
        budget=budget or Phase4Budget(),
    )
    return Phase6Preflight(
        snapshot=selected_snapshot,
        mode=mode,
        allowed=prepared.preflight.allowed,
        blockers=prepared.preflight.blockers,
        warnings=prepared.preflight.warnings,
        prepared=prepared,
    )


discover = discover_vnext_package
preflight = prepare_vnext_preflight
