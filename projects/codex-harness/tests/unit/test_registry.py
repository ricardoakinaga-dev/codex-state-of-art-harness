from __future__ import annotations

from dataclasses import replace

import pytest
from test_contracts import all_records

from harness_kernel.models import (
    CapabilityManifest,
    CapabilityStatus,
    InstallationScope,
    RecordStatus,
    RegistryOrigin,
)
from harness_kernel.registry import (
    CapabilityRegistry,
    InvalidManifestError,
    RegistryConflictError,
    parse_semver,
    satisfies,
)


def manifest(
    capability_id: str,
    version: str = "1.0.0",
    *,
    dependencies: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
    status: CapabilityStatus = CapabilityStatus.CANDIDATE,
    record_status: RecordStatus = RecordStatus.CURRENT,
) -> CapabilityManifest:
    base = next(item for item in all_records() if isinstance(item, CapabilityManifest))
    return replace(
        base,
        capability_id=capability_id,
        version=version,
        status=status,
        record=replace(base.record, status=record_status),
        dependencies=replace(base.dependencies, capabilities=dependencies),
        composition=replace(base.composition, conflicts_with=conflicts),
    )


def test_semver_precedence_and_ranges_are_deterministic() -> None:
    assert parse_semver("1.0.0-alpha") < parse_semver("1.0.0")
    assert parse_semver("1.2.3+one") == parse_semver("1.2.3+two")
    assert satisfies("1.8.0", ">=1.0.0,<2.0.0")
    assert satisfies("2.0.0", "^1.8.0") is False
    assert satisfies("1.2.9", "~1.2.0")


def test_registry_is_immutable_and_finds_highest_usable_version() -> None:
    empty = CapabilityRegistry()
    one = empty.register(manifest("alpha", "1.0.0"))
    two = one.register(manifest("alpha", "1.2.0"))

    assert empty.list() == ()
    assert one.list()[0].version == "1.0.0"
    assert two.find("alpha").version == "1.2.0"  # type: ignore[union-attr]
    assert two.find("alpha", ">=1.0.0,<1.2.0").version == "1.0.0"  # type: ignore[union-attr]


def test_duplicate_id_and_version_is_a_conflict() -> None:
    registry = CapabilityRegistry().register(manifest("alpha"))

    with pytest.raises(RegistryConflictError):
        registry.register(manifest("alpha"))


def test_manifest_preserves_explicit_isolation_and_provenance_metadata() -> None:
    value = manifest("isolated")

    assert value.provenance.origin is RegistryOrigin.PROJECT
    assert value.provenance.precedence == 200
    assert value.provenance.installation_scope is InstallationScope.PROJECT
    assert value.provenance.project_scope == "codex-state-of-art-harness"
    assert value.provenance.source_repository
    assert value.provenance.source_hash.startswith("sha256:")


@pytest.mark.parametrize(
    ("field", "value", "diagnostic"),
    (
        ("source_hash", "not-a-digest", "INVALID_SOURCE_HASH"),
        ("project_scope", "", "MISSING_PROJECT_SCOPE"),
        ("source_repository", "", "MISSING_SOURCE_REPOSITORY"),
    ),
)
def test_registry_rejects_incomplete_isolation_provenance(
    field: str, value: str, diagnostic: str
) -> None:
    candidate = manifest(
        "invalid-isolation",
    )
    candidate = replace(candidate, provenance=replace(candidate.provenance, **{field: value}))

    with pytest.raises(InvalidManifestError) as error:
        CapabilityRegistry().register(candidate)

    assert any(item.code == diagnostic for item in error.value.diagnostics)


def test_registry_rejects_noncanonical_origin_precedence() -> None:
    candidate = manifest("invalid-precedence")
    candidate = replace(
        candidate,
        provenance=replace(candidate.provenance, origin=RegistryOrigin.UPSTREAM, precedence=200),
    )

    with pytest.raises(InvalidManifestError) as error:
        CapabilityRegistry().register(candidate)

    assert any(item.code == "INVALID_ORIGIN_PRECEDENCE" for item in error.value.diagnostics)


def test_registry_constructor_cannot_bypass_manifest_admission() -> None:
    candidate = manifest("invalid-constructor")
    candidate = replace(candidate, provenance=replace(candidate.provenance, source_hash="invalid"))

    with pytest.raises(InvalidManifestError):
        CapabilityRegistry(manifests=(candidate,))


def test_same_id_and_version_cannot_shadow_across_registry_origins() -> None:
    project = manifest("shadowed")
    upstream = replace(
        project,
        provenance=replace(
            project.provenance,
            origin=RegistryOrigin.UPSTREAM,
            precedence=50,
            project_scope=None,
            installation_scope=InstallationScope.GLOBAL,
        ),
    )
    registry = CapabilityRegistry().register(project)

    with pytest.raises(RegistryConflictError, match="origins"):
        registry.register(upstream)


def test_registry_origin_precedence_beats_version_across_sources() -> None:
    project = manifest("isolated-selection", "1.0.0")
    upstream = replace(
        manifest("isolated-selection", "9.0.0"),
        provenance=replace(
            project.provenance,
            origin=RegistryOrigin.UPSTREAM,
            precedence=50,
            project_scope=None,
            installation_scope=InstallationScope.GLOBAL,
        ),
    )
    registry = CapabilityRegistry.from_manifests((upstream, project))

    assert registry.find("isolated-selection").version == "1.0.0"  # type: ignore[union-attr]
    assert registry.find("isolated-selection", ">=9.0.0").version == "9.0.0"  # type: ignore[union-attr]


def test_inspection_reports_stale_and_missing_provenance_without_execution() -> None:
    stale = manifest("stale", record_status=RecordStatus.STALE)
    registry = CapabilityRegistry().register(stale)

    inspection = registry.inspect("stale")

    assert inspection.stale is True
    assert any(item.code == "STALE_MANIFEST" for item in inspection.diagnostics)
    assert registry.find("stale") is None


def test_dependency_resolution_is_topological_and_diagnoses_missing_and_cycles() -> None:
    registry = CapabilityRegistry()
    registry = registry.register(manifest("leaf", "1.0.0"))
    registry = registry.register(manifest("root", "1.0.0", dependencies=("leaf@^1.0.0",)))

    result = registry.resolve_dependencies("root")

    assert tuple(item.capability_id for item in result.resolved) == ("leaf", "root")
    assert result.ok

    missing = (
        CapabilityRegistry()
        .register(manifest("root", dependencies=("absent@^2.0.0",)))
        .resolve_dependencies("root")
    )
    assert not missing.ok
    assert any(item.code == "MISSING_DEPENDENCY" for item in missing.diagnostics)

    cyclic = CapabilityRegistry()
    cyclic = cyclic.register(manifest("a", dependencies=("b",)))
    cyclic = cyclic.register(manifest("b", dependencies=("a",)))
    cycle_result = cyclic.resolve_dependencies("a")
    assert not cycle_result.ok
    assert cycle_result.cycles == (("a", "b", "a"),)


def test_rejected_dependency_is_never_resolved_as_usable() -> None:
    registry = CapabilityRegistry()
    registry = registry.register(manifest("rejected", status=CapabilityStatus.REJECTED))
    registry = registry.register(manifest("root", dependencies=("rejected@^1.0.0",)))

    inspection = registry.inspect("rejected")
    result = registry.resolve_dependencies("root")

    assert inspection.usable is False
    assert not result.ok
    assert any(item.code == "REJECTED_DEPENDENCY" for item in result.diagnostics)


def test_registry_reports_declared_conflicts() -> None:
    registry = CapabilityRegistry().register(manifest("alpha", conflicts=("beta",)))
    registry = registry.register(manifest("beta"))

    diagnostics = registry.diagnose("alpha")

    assert any(item.code == "CAPABILITY_CONFLICT" for item in diagnostics)
