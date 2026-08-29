from __future__ import annotations

from pathlib import Path

import pytest

from harness_kernel.phase3_discovery import CapabilityDiscovery
from harness_kernel.phase3_loader import LoaderError, SafeCapabilityLoader
from harness_kernel.phase3_models import (
    CapabilityRoot,
    DisclosureLevel,
    Phase3Limits,
    RootScope,
)
from harness_kernel.phase3_paths import digest_bytes


def test_loader_prepares_text_but_never_executes_scripts(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = root / "demo"
    (package / "references").mkdir(parents=True)
    (package / "scripts").mkdir()
    (package / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\nreferences:\n  - references/guide.md\n---\nbody\n",
        encoding="utf-8",
    )
    (package / "references" / "guide.md").write_text("reference", encoding="utf-8")
    (package / "scripts" / "run.sh").write_text("#!/bin/sh\necho unsafe\n", encoding="utf-8")
    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )
    record = inventory.capabilities[0]

    loaded = SafeCapabilityLoader(Phase3Limits()).load(record, DisclosureLevel.APPROVED_PACKAGE)

    assert loaded.context_prepared is True
    assert loaded.host_loaded is False
    assert loaded.host_load.status.value == "UNAVAILABLE"
    assert loaded.references[0].content == "reference"
    assert loaded.scripts[0].execution == "DISABLED_PHASE3"
    assert loaded.scripts[0].declared_purpose is None
    assert loaded.scripts[0].language == "shell"
    script_reference = (
        SafeCapabilityLoader(Phase3Limits())
        .load(
            record,
            DisclosureLevel.SELECTED_REFERENCES,
            selected_references=("scripts/run.sh",),
        )
        .references[0]
    )
    assert script_reference.content is None
    assert script_reference.binary is True
    assert script_reference.sha256 == digest_bytes(b"#!/bin/sh\necho unsafe\n")


def test_loader_blocks_reference_escape(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = root / "demo"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\nreferences:\n  - ../secret.md\n---\nbody\n",
        encoding="utf-8",
    )
    (root / "secret.md").write_text("secret", encoding="utf-8")
    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )

    loaded = SafeCapabilityLoader(Phase3Limits()).load(
        inventory.capabilities[0], DisclosureLevel.SELECTED_REFERENCES
    )

    assert loaded.references == ()
    assert any(
        "outside" in warning.lower() or "escape" in warning.lower() for warning in loaded.warnings
    )


def test_loader_applies_reference_file_bound(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = root / "demo"
    references = package / "references"
    references.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\nreferences:\n"
        "  - references/a.md\n  - references/b.md\n---\nbody\n",
        encoding="utf-8",
    )
    (references / "a.md").write_text("a", encoding="utf-8")
    (references / "b.md").write_text("b", encoding="utf-8")
    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )

    loaded = SafeCapabilityLoader(Phase3Limits(max_reference_files=1)).load(
        inventory.capabilities[0], DisclosureLevel.SELECTED_REFERENCES
    )

    assert len(loaded.references) == 1


def test_loader_applies_reference_depth_and_nested_script_surface_policy(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = root / "demo"
    references = package / "references" / "deep"
    scripts = package / "nested" / "scripts"
    references.mkdir(parents=True)
    scripts.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\nbody\n",
        encoding="utf-8",
    )
    (references / "guide.md").write_text("guide", encoding="utf-8")
    (scripts / "payload.md").write_text("do-not-read", encoding="utf-8")
    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )
    record = inventory.capabilities[0]
    loader = SafeCapabilityLoader(Phase3Limits(max_reference_depth=2))

    deep_reference = loader.load(
        record,
        DisclosureLevel.SELECTED_REFERENCES,
        selected_references=("references/deep/guide.md",),
    )
    nested_script = SafeCapabilityLoader().load(
        record,
        DisclosureLevel.SELECTED_REFERENCES,
        selected_references=("nested/scripts/payload.md",),
    )

    assert deep_reference.references == ()
    assert any("depth" in warning for warning in deep_reference.warnings)
    assert nested_script.references[0].content is None
    assert nested_script.references[0].binary is True


def test_loader_plan_does_not_claim_context_for_identity_or_routing(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = root / "demo"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text("---\nname: demo\n---\nbody\n", encoding="utf-8")
    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )
    record = inventory.capabilities[0]
    loader = SafeCapabilityLoader()

    identity = loader.plan(("demo",), (record,), DisclosureLevel.IDENTITY)
    routing = loader.plan(("demo",), (record,), DisclosureLevel.ROUTING_METADATA)
    context = loader.plan(("demo",), (record,), DisclosureLevel.INSTRUCTION_KERNEL)

    assert identity.prepared is False
    assert identity.statuses["demo"].value == "SELECTED"
    assert routing.prepared is False
    assert routing.statuses["demo"].value == "LOAD_PLANNED"
    assert context.prepared is True
    assert context.statuses["demo"].value == "CONTEXT_PREPARED"


def test_loader_identity_level_does_not_expose_routing_metadata(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = root / "demo"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        "---\nname: demo\ndescription: private routing\n"
        "activates_when: build\ndo_not_activate_when: never\n---\nbody\n",
        encoding="utf-8",
    )
    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )

    loaded = SafeCapabilityLoader().load(inventory.capabilities[0], DisclosureLevel.IDENTITY)

    assert dict(loaded.routing_metadata) == {}
    assert loaded.instruction_kernel is None
    assert loaded.context_prepared is False


def test_loader_bounds_reference_and_plan_iterables(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = root / "demo"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text("---\nname: demo\n---\nbody\n", encoding="utf-8")
    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (CapabilityRoot("project", RootScope.PROJECT, str(root), source="fixture"),)
    )
    record = inventory.capabilities[0]
    loader = SafeCapabilityLoader(Phase3Limits(max_reference_files=2, max_capabilities=2))

    def references():
        for index in range(10_000):
            yield f"references/{index}.md"

    loaded = loader.load(
        record, DisclosureLevel.SELECTED_REFERENCES, selected_references=references()
    )
    assert len(loaded.references) == 0
    assert any("count bound" in warning for warning in loaded.warnings)

    consumed = 0

    def repeated_references():
        nonlocal consumed
        for _ in range(10_000):
            consumed += 1
            yield "references/repeated.md"

    loader.load(
        record,
        DisclosureLevel.SELECTED_REFERENCES,
        selected_references=repeated_references(),
    )
    assert consumed <= 3

    def records():
        for _ in range(10_000):
            yield record

    with pytest.raises(LoaderError, match="record count bound"):
        loader.plan(("demo",), records(), DisclosureLevel.IDENTITY)
