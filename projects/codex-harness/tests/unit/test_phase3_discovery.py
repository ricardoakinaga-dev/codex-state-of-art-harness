from __future__ import annotations

from pathlib import Path

import pytest

from harness_kernel.phase3_discovery import CapabilityDiscovery, DiscoveryError
from harness_kernel.phase3_models import (
    CapabilityKind,
    CapabilityRoot,
    ObservationStatus,
    Phase3Limits,
    RootScope,
)
from harness_kernel.phase3_resolution import ResolutionEngine


def write_skill(root: Path, name: str, *, version: str = "0.1.0") -> Path:
    package = root / name
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} capability\nversion: {version}\n"
        "activates_when:\n  - use this capability\n"
        "do_not_activate_when:\n  - never use this capability\n---\n# Workflow\nSafe text.\n",
        encoding="utf-8",
    )
    return package


def test_discovery_synthesizes_manifest_and_inventory(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    package = write_skill(root, "demo")
    (package / "references").mkdir()
    (package / "references" / "guide.md").write_text("guide", encoding="utf-8")

    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (
            CapabilityRoot(
                root_id="project",
                scope=RootScope.PROJECT,
                path=str(root),
                source="fixture",
            ),
        )
    )

    assert inventory.capabilities[0].capability_id == "demo"
    assert inventory.capabilities[0].kind is CapabilityKind.SYNTHESIZED
    assert inventory.capabilities[0].content_hash.startswith("sha256:")
    assert inventory.capabilities[0].references == ("references/guide.md",)
    assert inventory.capabilities[0].manifest.field_provenance["name"] == "OBSERVED"


def test_native_manifest_and_invalid_package_are_distinct(tmp_path: Path) -> None:
    root = tmp_path / "capabilities"
    native = root / "native"
    invalid = root / "invalid"
    native.mkdir(parents=True)
    invalid.mkdir(parents=True)
    (native / "manifest.json").write_text(
        '{"schema_version":"CM-1","capability_id":"native","display_name":"Native",'
        '"version":"1.0.0","primary_type":"SPECIALIST","status":"CANDIDATE",'
        '"scope":{"domains":["ENGINEERING"],"activates_when":["native task"],'
        '"do_not_activate_when":["never native task"],"minimum_task_class":"SMALL"},'
        '"provenance":{"aliases":["native-alias"],"forked_from":"upstream/native"},'
        '"dependencies":{"capabilities":[],"tools":[],"providers":[],"references":[]},'
        '"composition":{"conflicts_with":[]},"compatibility":{"platform_limits":[]}}',
        encoding="utf-8",
    )
    (invalid / "SKILL.md").write_bytes(b"---\nname: \xff\n---\n")

    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )
    by_id = {item.capability_id: item for item in inventory.capabilities}

    assert by_id["native"].kind is CapabilityKind.NATIVE
    assert by_id["native"].provenance.aliases == ("native-alias",)
    categories = {item.category for item in ResolutionEngine().duplicate_report(inventory)}
    assert {"ALIAS", "FORKED_SOURCE"}.issubset(categories)
    assert by_id["invalid"].kind is CapabilityKind.INVALID
    assert by_id["invalid"].status.value in {"INVALID", "REJECTED"}


def test_incomplete_native_manifest_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "capabilities"
    package = root / "incomplete"
    package.mkdir(parents=True)
    (package / "manifest.json").write_text("{}", encoding="utf-8")

    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )

    record = inventory.capabilities[0]
    assert record.kind is CapabilityKind.INVALID
    assert record.status.value == "REJECTED"
    assert record.trust.level.value == "REJECTED"


def test_sensitive_package_files_are_metadata_only(tmp_path: Path) -> None:
    root = tmp_path / "capabilities"
    package = write_skill(root, "safe-metadata")
    (package / ".env").write_text("TOKEN=do-not-read", encoding="utf-8")

    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )
    sensitive = next(
        item for item in inventory.capabilities[0].files if item.relative_path == ".env"
    )

    assert sensitive.observation is ObservationStatus.UNAVAILABLE
    assert sensitive.kind == "sensitive_metadata"
    assert "do-not-read" not in str(inventory.capabilities[0])


def test_script_and_asset_text_files_are_metadata_only(tmp_path: Path) -> None:
    root = tmp_path / "capabilities"
    package = write_skill(root, "surface-boundary")
    (package / "scripts").mkdir()
    (package / "assets").mkdir()
    (package / "scripts" / "payload.md").write_text("do-not-read", encoding="utf-8")
    (package / "assets" / "payload.yaml").write_text("secret: do-not-read", encoding="utf-8")

    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )
    files = {item.relative_path: item for item in inventory.capabilities[0].files}

    assert files["scripts/payload.md"].observation is ObservationStatus.UNAVAILABLE
    assert files["scripts/payload.md"].kind == "metadata_only"
    assert files["assets/payload.yaml"].observation is ObservationStatus.UNAVAILABLE
    assert files["assets/payload.yaml"].kind == "metadata_only"


def test_discovery_rejects_deeply_nested_native_json(tmp_path: Path) -> None:
    root = tmp_path / "capabilities"
    package = root / "deep-native"
    package.mkdir(parents=True)
    nested = "[" * 20_000 + "]" * 20_000
    (package / "manifest.json").write_text(
        "{"
        + '"schema_version":"CM-1","capability_id":"deep-native",'
        + '"display_name":"Deep","version":"1.0.0",'
        + f'"scope":{{"domains":{nested}}}'
        + "}",
        encoding="utf-8",
    )

    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )

    assert inventory.capabilities[0].status.value == "REJECTED"
    assert inventory.capabilities[0].kind is CapabilityKind.INVALID


def test_discovery_bounds_root_iterables_before_materializing_them(tmp_path: Path) -> None:
    root = tmp_path / "capabilities"
    root.mkdir()

    def roots():
        for index in range(10_000):
            yield CapabilityRoot(f"root-{index}", RootScope.PROJECT, str(root), source="fixture")

    with pytest.raises(DiscoveryError, match="root count bound"):
        CapabilityDiscovery(Phase3Limits(max_roots=2)).scan(roots())


def test_scan_wide_bounds_cover_root_and_package_rewalks(tmp_path: Path) -> None:
    root = tmp_path / "capabilities"
    package = write_skill(root, "bounded")
    (package / "extra.txt").write_text("extra", encoding="utf-8")

    inventory = CapabilityDiscovery(Phase3Limits(max_total_files=2)).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )

    assert inventory.capabilities == ()
    assert any("scan-wide" in error for error in inventory.errors)


def test_expected_inventory_fingerprint_marks_records_stale(tmp_path: Path) -> None:
    root = tmp_path / "capabilities"
    write_skill(root, "staleable")
    roots = (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    discovery = CapabilityDiscovery(Phase3Limits())

    fresh = discovery.scan(roots)
    stale = discovery.scan(roots, expected_fingerprint="sha256:not-the-current-snapshot")

    assert fresh.capabilities[0].status.value == "INSPECTED"
    assert stale.capabilities[0].status.value == "STALE"
    assert stale.capabilities[0].load_eligibility == "BLOCKED_STALE_FINGERPRINT"
    assert any("stale" in error for error in stale.errors)
