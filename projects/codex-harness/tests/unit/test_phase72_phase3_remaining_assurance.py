from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness_kernel import phase3_cli, phase3_discovery
from harness_kernel.models import CapabilityStatus
from harness_kernel.phase3_discovery import (
    CapabilityDiscovery,
    _manifest_from_data,
    _validate_native_manifest,
)
from harness_kernel.phase3_host import CodexHostAdapter, HostAdapterError
from harness_kernel.phase3_integration import Phase3RouterBridge
from harness_kernel.phase3_loader import SafeCapabilityLoader
from harness_kernel.phase3_models import (
    CapabilityKind,
    CapabilityLifecycle,
    CapabilityRoot,
    DependencyStatus,
    DisclosureLevel,
    ObservationStatus,
    Phase3Limits,
    ResolutionStatus,
    RootScope,
    TrustLevel,
)
from harness_kernel.phase3_paths import digest_bytes
from harness_kernel.phase3_resolution import ResolutionEngine
from harness_kernel.phase3_telemetry import Phase3Telemetry
from harness_kernel.phase3_trust import assess_trust


def _write_skill(
    root: Path,
    directory: str,
    *,
    capability_id: str,
    version: str = "1.0.0",
    dependencies: tuple[str, ...] = (),
    body: str = "body",
) -> Path:
    package = root / directory
    package.mkdir(parents=True)
    dependency_block = ""
    if dependencies:
        dependency_block = "dependencies:\n" + "".join(
            f"  - {dependency}\n" for dependency in dependencies
        )
    (package / "SKILL.md").write_text(
        f"---\nname: {capability_id}\nversion: {version}\n"
        f"do_not_activate_when: never\n{dependency_block}---\n{body}\n",
        encoding="utf-8",
    )
    return package


def _inventory(*roots: tuple[Path, RootScope]):
    return CapabilityDiscovery(Phase3Limits()).scan(
        tuple(
            CapabilityRoot(
                f"root-{index}",
                scope,
                str(path),
                source="phase72-assurance",
            )
            for index, (path, scope) in enumerate(roots)
        )
    )


def test_native_manifest_rejects_non_mapping_security_metadata() -> None:
    errors = _validate_native_manifest(
        {
            "schema_version": "CM-1",
            "capability_id": "safe-capability",
            "display_name": "Safe Capability",
            "version": "1.0.0",
            "security": [],
        }
    )

    assert "native manifest security must be an object" in errors


def test_manifest_sanitizes_invalid_capability_id_before_record_creation() -> None:
    manifest, errors = _manifest_from_data(
        {"capability_id": "../escape", "version": "1.0.0"},
        package_name="safe-package",
        content_kind=CapabilityKind.NATIVE,
        source="manifest.json",
        skill_id=None,
        skill_description="",
        skill_values={},
        skill_lists={},
        skill_unknown_fields=(),
        skill_errors=(),
    )

    assert manifest.capability_id == "invalid-package"
    assert "capability ID is invalid" in errors


def test_inspection_fails_closed_if_manifest_adapter_violates_identity_invariant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "skills"
    _write_skill(root, "demo", capability_id="demo")
    invalid_manifest = SimpleNamespace(
        capability_id="",
        display_name="invalid",
        version="1.0.0",
        kind=CapabilityKind.SYNTHESIZED,
        description="",
        platform_limits=(),
        providers=(),
        tools=(),
        activates_when=(),
        do_not_activate_when=(),
        domains=(),
        dependencies=(),
        references=(),
        conflicts=(),
        gates=(),
        stop_conditions=(),
    )
    monkeypatch.setattr(
        phase3_discovery,
        "_manifest_from_data",
        lambda *_args, **_kwargs: (invalid_manifest, ()),
    )

    with pytest.raises(ValueError, match="capability_id"):
        CapabilityDiscovery().scan((CapabilityRoot("project", RootScope.PROJECT, str(root)),))


def test_revalidation_rejects_same_size_file_byte_drift(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = _write_skill(root, "demo", capability_id="demo", body="body")
    inventory = _inventory((root, RootScope.PROJECT))
    original = (package / "SKILL.md").read_bytes()
    changed = original.replace(b"body", b"BODY")
    assert len(changed) == len(original)
    (package / "SKILL.md").write_bytes(changed)

    fresh, reason = phase3_discovery.revalidate_capability(
        inventory.capabilities[0], Phase3Limits()
    )

    assert fresh is False
    assert "file bytes changed since discovery" in reason


def test_host_adapter_rejects_relative_project_root() -> None:
    with pytest.raises(HostAdapterError, match="project_root must be absolute"):
        CodexHostAdapter(project_root="relative-project-root")


def test_cli_duplicate_redaction_preserves_non_list_path_metadata(tmp_path: Path) -> None:
    adapter = CodexHostAdapter(project_root=tmp_path)

    values = phase3_cli._duplicates_public(adapter, ({"paths": "opaque"},))

    assert values == [{"paths": "opaque"}]


def test_router_bridge_rejects_rejected_observed_capability(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    _write_skill(root, "demo", capability_id="demo")
    record = _inventory((root, RootScope.PROJECT)).capabilities[0]

    manifest = Phase3RouterBridge().manifest(replace(record, status=CapabilityLifecycle.REJECTED))

    assert manifest.status is CapabilityStatus.REJECTED


def test_loader_hashes_non_sensitive_metadata_only_reference(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = _write_skill(root, "demo", capability_id="demo")
    scripts = package / "scripts"
    scripts.mkdir()
    payload = b"#!/bin/sh\nprintf safe\n"
    (scripts / "run.sh").write_bytes(payload)
    record = _inventory((root, RootScope.PROJECT)).capabilities[0]

    loaded = SafeCapabilityLoader().load(
        record,
        DisclosureLevel.SELECTED_REFERENCES,
        selected_references=("scripts/run.sh",),
    )

    assert loaded.references[0].binary is True
    assert loaded.references[0].sha256 == digest_bytes(payload)


def test_loader_keeps_sensitive_metadata_reference_unreadable(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = _write_skill(root, "demo", capability_id="demo")
    (package / ".env").write_text("TOKEN=not-readable", encoding="utf-8")
    record = _inventory((root, RootScope.PROJECT)).capabilities[0]
    decorated = replace(
        record,
        references=(".env",),
        manifest=replace(record.manifest, references=(".env",)),
    )

    loaded = SafeCapabilityLoader().load(
        decorated,
        DisclosureLevel.SELECTED_REFERENCES,
        selected_references=(".env",),
    )

    assert loaded.references[0].sha256 == "sha256:unavailable-metadata"
    assert loaded.references[0].content is None


def test_loader_exposes_provider_warning_only_as_metadata(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    _write_skill(root, "demo", capability_id="demo")
    record = _inventory((root, RootScope.PROJECT)).capabilities[0]
    decorated = replace(
        record,
        manifest=replace(record.manifest, providers=("provider-x",)),
    )

    loaded = SafeCapabilityLoader().load(decorated, DisclosureLevel.APPROVED_PACKAGE)

    assert any("provider metadata" in warning for warning in loaded.warnings)
    assert loaded.host_loaded is False


def test_loader_plan_routes_explicit_blockers_to_all_requested_ids(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    _write_skill(root, "demo", capability_id="demo")
    record = _inventory((root, RootScope.PROJECT)).capabilities[0]

    plan = SafeCapabilityLoader().plan(
        ("demo", "missing"),
        (record,),
        DisclosureLevel.IDENTITY,
        blockers=("UPSTREAM_BLOCKED",),
    )

    assert plan.selected == ()
    assert plan.statuses["demo"] is CapabilityLifecycle.BLOCKED
    assert plan.statuses["missing"] is CapabilityLifecycle.BLOCKED


def test_loader_plan_blocks_record_with_blocked_eligibility(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    _write_skill(root, "demo", capability_id="demo")
    record = _inventory((root, RootScope.PROJECT)).capabilities[0]

    plan = SafeCapabilityLoader().plan(
        ("demo",),
        (replace(record, load_eligibility="BLOCKED_POLICY"),),
        DisclosureLevel.IDENTITY,
    )

    assert plan.statuses["demo"] is CapabilityLifecycle.BLOCKED


def test_phase3_models_reject_root_traversal_and_non_absolute_record_path(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="traversal"):
        CapabilityRoot("project", RootScope.PROJECT, str(tmp_path / ".." / "escape"))

    root = tmp_path / "skills"
    _write_skill(root, "demo", capability_id="demo")
    record = _inventory((root, RootScope.PROJECT)).capabilities[0]
    with pytest.raises(ValueError, match="absolute"):
        replace(record, path="relative/package")


def test_resolution_honors_pin_to_a_divergent_version_blocker(tmp_path: Path) -> None:
    project = tmp_path / "project"
    global_root = tmp_path / "global"
    project.mkdir()
    global_root.mkdir()
    _write_skill(project, "demo", capability_id="demo", body="project")
    _write_skill(global_root, "demo", capability_id="demo", body="global")

    result = ResolutionEngine().resolve(
        _inventory((project, RootScope.PROJECT), (global_root, RootScope.GLOBAL)),
        "demo@1.0.0",
    )

    assert result.status is ResolutionStatus.BLOCKED
    assert "CAPABILITY_DIVERGENCE" in result.blockers


def test_resolution_records_already_selected_dependency(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_skill(root, "root", capability_id="root", dependencies=("dep-a", "dep-b"))
    _write_skill(root, "dep-a", capability_id="dep-a", dependencies=("shared",))
    _write_skill(root, "dep-b", capability_id="dep-b", dependencies=("shared",))
    _write_skill(root, "shared", capability_id="shared")

    result = ResolutionEngine().resolve(_inventory((root, RootScope.PROJECT)), "root")

    assert result.status is ResolutionStatus.RESOLVED
    assert any(
        item.status is DependencyStatus.RESOLVED and item.detail == "dependency already selected"
        for item in result.dependencies
    )


def _divergent_dependency_inventory(tmp_path: Path, dependency: str) -> object:
    root = tmp_path / "root"
    root.mkdir()
    _write_skill(root, "root", capability_id="root", dependencies=(dependency,))
    _write_skill(root, "dep-a", capability_id="dep", body="first")
    _write_skill(root, "dep-b", capability_id="dep", body="second")
    return _inventory((root, RootScope.PROJECT))


def test_resolution_rejects_pinned_divergent_dependency_version(tmp_path: Path) -> None:
    result = ResolutionEngine().resolve(
        _divergent_dependency_inventory(tmp_path, "dep@1.0.0"),
        "root",
    )

    assert result.status is ResolutionStatus.BLOCKED
    assert any(item.status is DependencyStatus.AMBIGUOUS for item in result.dependencies)
    assert "AMBIGUOUS_DEPENDENCY" in result.blockers


def test_resolution_rejects_unpinned_dependency_with_divergent_bytes(tmp_path: Path) -> None:
    result = ResolutionEngine().resolve(
        _divergent_dependency_inventory(tmp_path, "dep"),
        "root",
    )

    assert result.status is ResolutionStatus.BLOCKED
    assert any(item.status is DependencyStatus.AMBIGUOUS for item in result.dependencies)
    assert "AMBIGUOUS_DEPENDENCY" in result.blockers


def test_resolution_reports_missing_dependency_without_divergence(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_skill(root, "root", capability_id="root", dependencies=("missing",))

    result = ResolutionEngine().resolve(_inventory((root, RootScope.PROJECT)), "root")

    assert result.status is ResolutionStatus.BLOCKED
    assert any(item.status is DependencyStatus.MISSING for item in result.dependencies)
    assert "MISSING_DEPENDENCY" in result.blockers


def test_resolution_reports_stale_dependency_separately_from_missing(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_skill(root, "root", capability_id="root", dependencies=("dep",))
    dependency_package = _write_skill(root, "dep", capability_id="dep", body="one")
    inventory = _inventory((root, RootScope.PROJECT))
    (dependency_package / "SKILL.md").write_bytes(
        (dependency_package / "SKILL.md").read_bytes().replace(b"one", b"two")
    )

    result = ResolutionEngine().resolve(inventory, "root")

    assert result.status is ResolutionStatus.BLOCKED
    assert any(item.status is DependencyStatus.BLOCKED for item in result.dependencies)
    assert "STALE_DEPENDENCY" in result.blockers


def test_telemetry_redacts_relative_values_without_path_redaction() -> None:
    telemetry = Phase3Telemetry().record(
        "demo",
        # A relative value must still be retained as ordinary diagnostic data.
        # Absolute values take the path-redaction branch instead.
        CapabilityLifecycle.DISCOVERED,
        ObservationStatus.OBSERVED,
        data={"message": "relative-value"},
    )

    assert telemetry.events[0].data["message"] == "relative-value"


def test_trust_marks_workspace_and_vendored_roots_as_verified_local() -> None:
    for scope in (RootScope.WORKSPACE, RootScope.VENDORED):
        trust = assess_trust(scope, content_hash="sha256:" + "a" * 64)
        assert trust.level is TrustLevel.VERIFIED_LOCAL


def test_trust_does_not_promote_system_path_to_official() -> None:
    trust = assess_trust(
        RootScope.SYSTEM,
        content_hash="sha256:" + "a" * 64,
        source_type="LOCAL",
    )

    assert trust.level is TrustLevel.UNVERIFIED


def test_duplicate_renderer_preserves_non_list_diagnostics() -> None:
    from types import SimpleNamespace

    from harness_kernel.phase3_cli import _duplicates_public

    adapter = SimpleNamespace(
        project_root=Path("/tmp/project"),
        home_dir=Path("/tmp/home"),
    )
    rendered = _duplicates_public(adapter, ({"paths": "not-a-list"},))
    assert rendered == [{"paths": "not-a-list"}]
