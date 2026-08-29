"""Bridge observed Phase 3 metadata into the existing Phase 2 router."""

from __future__ import annotations

from collections.abc import Iterable

from .models import (
    REGISTRY_ORIGIN_PRECEDENCE,
    CapabilityCompatibility,
    CapabilityComposition,
    CapabilityContracts,
    CapabilityDependencies,
    CapabilityManifest,
    CapabilityPrimaryType,
    CapabilityQuality,
    CapabilityScope,
    CapabilitySecurity,
    CapabilityStatus,
    Complexity,
    ContextCost,
    Deprecation,
    GateStatus,
    InstallationScope,
    ManifestProvenance,
    Provenance,
    RecordEnvelope,
    RecordStatus,
    RegistryOrigin,
    SchemaVersion,
    SourceType,
    TaskProfile,
)
from .phase3_models import CapabilityLifecycle, CapabilityRecord, Phase3Limits, RootScope
from .registry import CapabilityRegistry
from .routing import MinimumRoutePolicy, minimum_route


class IntegrationError(ValueError):
    """Raised when observed metadata cannot cross the Phase 2 registry boundary."""


_ORIGIN = {
    RootScope.PROJECT: RegistryOrigin.PROJECT,
    RootScope.WORKSPACE: RegistryOrigin.WORKSPACE,
    RootScope.GLOBAL: RegistryOrigin.GLOBAL,
    RootScope.SYSTEM: RegistryOrigin.SYSTEM,
    RootScope.VENDORED: RegistryOrigin.VENDORED,
    RootScope.EXTERNAL: RegistryOrigin.UPSTREAM,
    RootScope.UNKNOWN: RegistryOrigin.UPSTREAM,
}
_PRIMARY = {item.value: item for item in CapabilityPrimaryType}
_INSTALLATION_SCOPE = {
    RegistryOrigin.SYSTEM: InstallationScope.SYSTEM,
    RegistryOrigin.GLOBAL: InstallationScope.GLOBAL,
    RegistryOrigin.WORKSPACE: InstallationScope.WORKSPACE,
    RegistryOrigin.PROJECT: InstallationScope.PROJECT,
    RegistryOrigin.VENDORED: InstallationScope.PROJECT,
    RegistryOrigin.UPSTREAM: InstallationScope.GLOBAL,
}


def _origin(scope: RootScope) -> RegistryOrigin:
    return _ORIGIN.get(scope, RegistryOrigin.UPSTREAM)


def _primary(value: str) -> CapabilityPrimaryType:
    return _PRIMARY.get(value.upper(), CapabilityPrimaryType.SPECIALIST)


class Phase3RouterBridge:
    """Convert selected declarative records and invoke only the pure router."""

    def __init__(self, limits: Phase3Limits | None = None) -> None:
        self.limits = limits or Phase3Limits()

    def _bounded_records(self, records: Iterable[CapabilityRecord]) -> tuple[CapabilityRecord, ...]:
        selected: list[CapabilityRecord] = []
        for index, record in enumerate(records):
            if index >= self.limits.max_capabilities:
                raise IntegrationError("capability record count bound exceeded")
            selected.append(record)
        return tuple(selected)

    def manifest(self, record: CapabilityRecord) -> CapabilityManifest:
        if record.status in {
            CapabilityLifecycle.REJECTED,
            CapabilityLifecycle.INCOMPATIBLE,
            CapabilityLifecycle.STALE,
            CapabilityLifecycle.AMBIGUOUS,
        }:
            status = CapabilityStatus.REJECTED
        else:
            status = CapabilityStatus.CANDIDATE
        origin = _origin(record.scope)
        primary = _primary(record.manifest.primary_type)
        source_type = (
            SourceType.LOCAL if record.scope is not RootScope.EXTERNAL else SourceType.IMPORTED
        )
        domain_values = record.manifest.domains or ("GENERAL",)
        return CapabilityManifest(
            SchemaVersion.CAPABILITY_MANIFEST,
            record.capability_id,
            record.display_name,
            record.version,
            RecordEnvelope(
                RecordStatus.CURRENT,
                Provenance(
                    source_type, record.provenance.source_refs, record.provenance.observed_at
                ),
                (),
            ),
            primary,
            status,
            record.provenance.authority,
            CapabilityScope(
                domain_values,
                record.activates_when,
                record.do_not_activate_when,
                Complexity.SMALL,
            ),
            CapabilityContracts(
                ("TaskProfile", "declarative-metadata"),
                ("RouteDecision", "load-plan"),
                record.gates or ("P3-HOST-INSPECTION",),
                record.stop_conditions or ("INVALID_METADATA", "UNSUPPORTED_HOST"),
            ),
            CapabilityComposition((), ("router",), (), (), record.conflicts),
            CapabilityDependencies(
                record.dependencies,
                record.manifest.tools,
                record.manifest.providers,
                record.manifest.references,
            ),
            ManifestProvenance(
                source_type,
                record.provenance.source_refs,
                record.provenance.observed_at,
                record.provenance.source_repository,
                record.content_hash,
                origin,
                REGISTRY_ORIGIN_PRECEDENCE[origin],
                _INSTALLATION_SCOPE[origin],
                record.provenance.scope.value.lower(),
                record.provenance.forked_from,
            ),
            CapabilityCompatibility(
                record.manifest.platform_limits,
                record.compatibility.platform_limits,
            ),
            CapabilityQuality("P3-HOST-INSPECTION", (), (), GateStatus.NOT_RUN),
            CapabilitySecurity(
                ("read_declarative_metadata",),
                ("PROJECT_LOCAL" if record.scope is RootScope.PROJECT else "HOST_METADATA",),
                "Never read, store or emit secrets; no package execution.",
            ),
            ContextCost(
                max(1, len(record.description) // 4),
                None,
            ),
            Deprecation(None, None),
        )

    def registry(self, records: Iterable[CapabilityRecord]) -> CapabilityRegistry:
        bounded_records = self._bounded_records(records)
        manifests = tuple(self.manifest(record) for record in bounded_records)
        try:
            return CapabilityRegistry.from_manifests(manifests)
        except (TypeError, ValueError) as exc:
            raise IntegrationError("selected observed metadata failed registry admission") from exc

    def route(
        self,
        profile: TaskProfile,
        records: Iterable[CapabilityRecord] = (),
        *,
        policy: MinimumRoutePolicy | None = None,
    ) -> tuple[object, CapabilityRegistry]:
        selected = self._bounded_records(records)
        registry = self.registry(selected) if selected else CapabilityRegistry()
        decision = minimum_route(profile, registry, policy=policy)
        return decision, registry
