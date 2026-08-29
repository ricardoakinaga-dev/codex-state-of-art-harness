"""Read-only Codex host adapter and sanitized host snapshot."""

from __future__ import annotations

import os
import platform
import stat
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, cast

from .phase3_discovery import CapabilityDiscovery
from .phase3_models import (
    CapabilityInventory,
    CapabilityRecord,
    CapabilityRoot,
    HostFeatureDescription,
    HostSnapshot,
    LoadObservation,
    ObservationStatus,
    Phase3Limits,
    RootScope,
    public_data,
)
from .phase3_paths import PathSafetyError, canonicalize_root, digest_bytes, redact_path


class HostAdapterError(ValueError):
    """Raised for an invalid read-only host inspection request."""


class HostAdapter(Protocol):
    def inspect_host(self) -> HostSnapshot: ...

    def discover_capability_roots(self) -> tuple[CapabilityRoot, ...]: ...

    def discover_capabilities(
        self,
        roots: Iterable[CapabilityRoot] | None = None,
        *,
        expected_fingerprint: str | None = None,
    ) -> CapabilityInventory: ...

    def inspect_capability(self, capability_id: str) -> CapabilityRecord: ...

    def observe_load_state(self, capability_id: str) -> LoadObservation: ...

    def describe_tools(self) -> HostFeatureDescription: ...

    def describe_providers(self) -> HostFeatureDescription: ...

    def describe_limitations(self) -> tuple[str, ...]: ...


class CodexHostAdapter:
    """Inspect known local Codex directories without mutating or executing them."""

    def __init__(
        self,
        *,
        project_root: str | Path,
        workspace_root: str | Path | None = None,
        home_dir: str | Path | None = None,
        codex_home: str | Path | None = None,
        limits: Phase3Limits | None = None,
    ) -> None:
        self.project_root = self._existing_dir(project_root, "project_root")
        self.workspace_root = (
            self._existing_dir(workspace_root, "workspace_root")
            if workspace_root is not None
            else None
        )
        selected_home = home_dir if home_dir is not None else Path.home()
        self.home_dir = self._existing_dir(selected_home, "home_dir", allow_missing=True)
        selected_codex_home = codex_home
        if selected_codex_home is None:
            environment_value = os.environ.get("CODEX_HOME")
            selected_codex_home = environment_value if environment_value else None
        self.codex_home = (
            self._existing_dir(selected_codex_home, "codex_home", allow_missing=True)
            if selected_codex_home is not None
            else self.home_dir / ".codex"
        )
        self.limits = limits or Phase3Limits()
        self.discovery = CapabilityDiscovery(self.limits)

    @staticmethod
    def _existing_dir(value: str | Path, label: str, *, allow_missing: bool = False) -> Path:
        path = Path(value)
        if not path.is_absolute():
            raise HostAdapterError(f"{label} must be absolute")
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            if allow_missing:
                return path.absolute()
            raise HostAdapterError(f"{label} is unavailable") from None
        except OSError as exc:
            raise HostAdapterError(f"{label} is unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise HostAdapterError(f"{label} symlink is not accepted")
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise HostAdapterError(f"{label} is unavailable") from exc
        if not resolved.is_dir():
            raise HostAdapterError(f"{label} must be a directory")
        return resolved

    def _candidate_specs(self) -> tuple[tuple[str, Path, RootScope, str], ...]:
        specs: list[tuple[str, Path, RootScope, str]] = [
            (
                "project.agents",
                self.project_root / ".agents" / "skills",
                RootScope.PROJECT,
                "official project skill discovery",
            ),
            (
                "project.harness",
                self.project_root / ".harness" / "capabilities",
                RootScope.PROJECT,
                "project-local harness capabilities",
            ),
            (
                "global.agents",
                self.home_dir / ".agents" / "skills",
                RootScope.GLOBAL,
                "official user skill discovery",
            ),
            (
                "global.codex",
                self.home_dir / ".codex" / "skills",
                RootScope.GLOBAL,
                "legacy Codex compatibility root",
            ),
            (
                "system.codex",
                Path("/etc/codex/skills"),
                RootScope.SYSTEM,
                "system Codex compatibility root",
            ),
        ]
        if self.workspace_root is not None:
            specs.insert(
                2,
                (
                    "workspace.agents",
                    self.workspace_root / ".agents" / "skills",
                    RootScope.WORKSPACE,
                    "workspace skill discovery",
                ),
            )
        codex_skill_root = self.codex_home / "skills"
        if codex_skill_root not in {item[1] for item in specs}:
            specs.append(
                (
                    "global.codex-home",
                    codex_skill_root,
                    RootScope.GLOBAL,
                    "CODEX_HOME compatibility root",
                )
            )
        return tuple(specs)

    def discover_capability_roots(self) -> tuple[CapabilityRoot, ...]:
        roots: list[CapabilityRoot] = []
        seen: set[str] = set()
        for root_id, path, scope, source in self._candidate_specs():
            try:
                root = canonicalize_root(path, root_id=root_id, scope=scope, source=source)
            except PathSafetyError:
                resolved = path.resolve(strict=False)
                root = CapabilityRoot(
                    root_id,
                    scope,
                    str(resolved),
                    source=source,
                    readable=False,
                    mutable=False,
                    confidence=ObservationStatus.UNKNOWN,
                    canonical_path=str(resolved),
                    security_status="REJECTED",
                )
            canonical = root.canonical_path or root.path
            if canonical in seen:
                continue
            seen.add(canonical)
            roots.append(root)
            if len(roots) >= self.limits.max_roots:
                break
        return tuple(roots)

    def discover_capabilities(
        self,
        roots: Iterable[CapabilityRoot] | None = None,
        *,
        expected_fingerprint: str | None = None,
    ) -> CapabilityInventory:
        selected_roots = roots if roots is not None else self.discover_capability_roots()
        return self.discovery.scan(selected_roots, expected_fingerprint=expected_fingerprint)

    def inspect_host(self) -> HostSnapshot:
        roots = self.discover_capability_roots()
        inventory = self.discover_capabilities(roots)
        identity = {
            "adapter": "CodexHostAdapter",
            "adapter_version": "P3-1",
            "os": platform.system(),
            "python": platform.python_version(),
            "codex_runtime": "UNKNOWN",
        }
        root_signature = "|".join(
            f"{item.root_id}:{item.canonical_path}:{item.readable}:{item.security_status}"
            for item in roots
        )
        fingerprint = digest_bytes(
            (
                "|".join(f"{key}={value}" for key, value in sorted(identity.items()))
                + root_signature
                + inventory.fingerprint
            ).encode()
        )
        limitations = self.describe_limitations() + tuple(inventory.errors[:16])
        return HostSnapshot(
            "codex-host-local",
            "P3-1",
            inventory.observed_at,
            identity,
            "UNKNOWN",
            roots,
            str(self.project_root),
            str(self.workspace_root) if self.workspace_root is not None else None,
            ("codex.config.presence-only",),
            len(inventory.capabilities),
            self.describe_tools(),
            self.describe_providers(),
            limitations,
            ObservationStatus.OBSERVED,
            fingerprint,
            ObservationStatus.OBSERVED,
            {
                "skill_discovery": ObservationStatus.VERIFIED_OFFICIAL,
                "agents_openai_metadata": ObservationStatus.VERIFIED_OFFICIAL,
                "official_ancestor_root_semantics": ObservationStatus.VERIFIED_OFFICIAL,
                "official_symlink_support": ObservationStatus.VERIFIED_OFFICIAL,
                "legacy_codex_skill_root": ObservationStatus.INFERRED,
                "adapter_ancestor_discovery": ObservationStatus.UNSUPPORTED_BY_HOST,
                "adapter_symlink_policy": ObservationStatus.INFERRED,
                "host_load_observation": ObservationStatus.UNSUPPORTED_BY_HOST,
                "provider_tool_execution": ObservationStatus.UNSUPPORTED_BY_HOST,
                "codex_runtime_version": ObservationStatus.UNKNOWN,
            },
        )

    def inspect_capability(self, capability_id: str) -> CapabilityRecord:
        if not isinstance(capability_id, str) or not capability_id or "\x00" in capability_id:
            raise HostAdapterError("capability ID is invalid")
        inventory = self.discover_capabilities()
        matches = tuple(
            item for item in inventory.capabilities if item.capability_id == capability_id
        )
        if not matches:
            raise HostAdapterError("capability was not discovered")
        if len(matches) > 1:
            raise HostAdapterError("capability has multiple discovered records; resolve first")
        return matches[0]

    def observe_load_state(self, capability_id: str) -> LoadObservation:
        if not isinstance(capability_id, str) or not capability_id or "\x00" in capability_id:
            raise HostAdapterError("capability ID is invalid")
        return LoadObservation(
            capability_id,
            ObservationStatus.UNAVAILABLE,
            False,
            "Codex host load causality is not exposed by this adapter",
            self.discovery.observed_at,
        )

    def describe_tools(self) -> HostFeatureDescription:
        return HostFeatureDescription(
            "tools",
            ObservationStatus.UNAVAILABLE,
            (),
            ("tool inventory is not a tool-execution or authorization signal",),
        )

    def describe_providers(self) -> HostFeatureDescription:
        return HostFeatureDescription(
            "providers",
            ObservationStatus.UNAVAILABLE,
            (),
            ("provider discovery is deferred; no provider credentials are read",),
        )

    def describe_limitations(self) -> tuple[str, ...]:
        return (
            "Codex runtime version is not observed through a public local adapter",
            "host-loaded state is unavailable; discovery and context preparation are not loading",
            "scripts, binaries, providers, MCP, shell and network are never executed",
            "global and system roots are read-only dependencies",
        )


def public_root(
    root: CapabilityRoot,
    *,
    workspace_root: str | Path | None = None,
    home_dir: str | Path | None = None,
) -> dict[str, object]:
    value = cast(dict[str, object], public_data(root))
    value["path"] = redact_path(
        root.path, workspace_root=workspace_root, home_dir=home_dir, root_id=root.root_id
    )
    value["canonical_path"] = redact_path(
        root.canonical_path or root.path,
        workspace_root=workspace_root,
        home_dir=home_dir,
        root_id=root.root_id,
    )
    return value


def public_snapshot(
    snapshot: HostSnapshot,
    *,
    workspace_root: str | Path | None = None,
    home_dir: str | Path | None = None,
) -> dict[str, object]:
    value = cast(dict[str, object], public_data(snapshot))
    value["schema_version"] = "P3-HOST-1"
    value["roots"] = [
        public_root(item, workspace_root=workspace_root, home_dir=home_dir)
        for item in snapshot.roots
    ]
    value["project_root"] = (
        redact_path(
            snapshot.project_root,
            workspace_root=workspace_root,
            home_dir=home_dir,
            root_id="PROJECT",
        )
        if snapshot.project_root
        else None
    )
    value["workspace_root"] = (
        redact_path(
            snapshot.workspace_root,
            workspace_root=workspace_root,
            home_dir=home_dir,
            root_id="WORKSPACE",
        )
        if snapshot.workspace_root
        else None
    )
    return value


def public_inventory(
    inventory: CapabilityInventory,
    *,
    workspace_root: str | Path | None = None,
    home_dir: str | Path | None = None,
) -> dict[str, object]:
    value = cast(dict[str, object], public_data(inventory))
    value["schema_version"] = "P3-INVENTORY-1"
    value["roots"] = [
        public_root(item, workspace_root=workspace_root, home_dir=home_dir)
        for item in inventory.roots
    ]
    capabilities = []
    for record in inventory.capabilities:
        item = public_data(record)
        item["path"] = redact_path(
            record.path, workspace_root=workspace_root, home_dir=home_dir, root_id=record.root_id
        )
        item["provenance"]["source_repository"] = f"root://{record.root_id}"
        capabilities.append(item)
    value["capabilities"] = capabilities
    return value
