from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from test_phase4_policy import _discovered_record, _policy

from harness_kernel import phase3_discovery, phase4_policy
from harness_kernel.phase3_discovery import _manifest_from_data, _validate_native_manifest
from harness_kernel.phase3_models import (
    CapabilityKind,
    CapabilityRoot,
    Phase3Limits,
    RootScope,
    WalkResult,
)
from harness_kernel.phase4_models import ExecutionMode
from harness_kernel.phase4_policy import _safe_skill_path


def test_discovery_manifest_validates_semver_and_missing_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, errors = _manifest_from_data(
        {"version": "not-semver"},
        package_name="valid-package",
        content_kind=CapabilityKind.NATIVE,
        source="manifest.json",
        skill_id=None,
        skill_description="",
        skill_values={},
        skill_lists={},
        skill_unknown_fields=(),
        skill_errors=(),
    )
    assert manifest.version == "0.1.0"
    assert "manifest version is not semantic-version shaped" in errors

    class _IdentityPattern:
        @staticmethod
        def fullmatch(value: str):
            return True if value == "" else phase3_discovery._ID.fullmatch(value)

    monkeypatch.setattr(phase3_discovery, "_ID", _IdentityPattern())
    with pytest.raises(ValueError, match="capability_id"):
        _manifest_from_data(
            {},
            package_name="",
            content_kind=CapabilityKind.INVALID,
            source="package",
            skill_id=None,
            skill_description="",
            skill_values={},
            skill_lists={},
            skill_unknown_fields=(),
            skill_errors=(),
        )


def test_native_manifest_activation_metadata_requires_negative_guard() -> None:
    errors = _validate_native_manifest(
        {
            "schema_version": "CM-1",
            "capability_id": "safe-pilot",
            "display_name": "Safe Pilot",
            "version": "0.1.0",
            "scope": {"activates_when": ["build"], "do_not_activate_when": []},
        }
    )
    assert "native manifest do-not-activate metadata is missing" in errors


def test_revalidation_rejects_walk_errors_and_fingerprint_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "skills"
    package = root / "demo"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text("---\nname: demo\n---\nbody\n", encoding="utf-8")
    inventory = phase3_discovery.CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )
    record = inventory.capabilities[0]
    monkeypatch.setattr(
        phase3_discovery,
        "bounded_walk",
        lambda *_args, **_kwargs: WalkResult(
            files=tuple(item.relative_path for item in record.files), errors=("unreadable",)
        ),
    )
    fresh, reason = phase3_discovery.revalidate_capability(record, Phase3Limits())
    assert fresh is False
    assert "no longer clean" in reason

    monkeypatch.undo()
    stale = replace(record, content_hash="sha256:" + "f" * 64)
    fresh, reason = phase3_discovery.revalidate_capability(stale, Phase3Limits())
    assert fresh is False
    assert "fingerprint changed" in reason


def test_policy_registry_requires_matching_identity_and_skill_path_boundary(
    tmp_path: Path,
) -> None:
    record, _inventory, _resolution = _discovered_record(tmp_path)
    registry = _policy(record)
    assert registry.rule_for_record(record) is not None
    assert registry.rule_for_record(replace(record, content_hash="sha256:" + "f" * 64)) is None
    assert registry.rule_for_record(replace(record, capability_id="other")) is None

    outside_skill = replace(record, skill_md="../escape.md")
    skill_path, error = _safe_skill_path(outside_skill)
    assert skill_path is None
    assert error == "SKILL_SOURCE_ESCAPE"

    package_link = tmp_path / "package-link"
    package_link.symlink_to(Path(record.path), target_is_directory=True)
    link_record = replace(record, path=str(package_link))
    skill_path, error = _safe_skill_path(link_record)
    assert skill_path is None
    assert error == "SKILL_SOURCE_SYMLINK"


def test_preflight_rejects_undeclared_provider_at_the_execution_boundary(tmp_path: Path) -> None:
    record, inventory, resolution = _discovered_record(tmp_path)
    decorated = replace(record, manifest=replace(record.manifest, providers=("provider-x",)))
    result = phase4_policy.build_preflight(
        decorated,
        inventory,
        resolution,
        _policy(record),
        task_id="TASK-P72-PROVIDER",
        run_id="RUN-P72-PROVIDER",
        task="Produce a bounded response.",
        acceptance_criteria=("response is non-empty",),
        workspace=tmp_path,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=phase4_policy.Phase4Budget(),
    )
    assert result.allowed is False
    assert "FORBIDDEN_PROVIDER" in result.blockers
