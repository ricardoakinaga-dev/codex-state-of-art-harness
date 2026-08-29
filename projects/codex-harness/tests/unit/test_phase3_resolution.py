from __future__ import annotations

from pathlib import Path

import pytest

from harness_kernel.phase3_discovery import CapabilityDiscovery
from harness_kernel.phase3_models import (
    CapabilityRoot,
    Phase3Limits,
    ResolutionStatus,
    RootScope,
)
from harness_kernel.phase3_resolution import ResolutionEngine, ResolutionError


def skill(root: Path, name: str, *, description: str = "same") -> None:
    package = root / name
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\nversion: 1.0.0\n---\nbody\n",
        encoding="utf-8",
    )


def inventory_for(*roots: tuple[Path, RootScope]) -> object:
    return CapabilityDiscovery(Phase3Limits()).scan(
        tuple(
            CapabilityRoot(f"root-{index}", scope, str(path), source="fixture")
            for index, (path, scope) in enumerate(roots)
        )
    )


def test_divergent_same_version_is_blocked(tmp_path: Path) -> None:
    project = tmp_path / "project"
    global_root = tmp_path / "global"
    project.mkdir()
    global_root.mkdir()
    skill(project, "same-id", description="project bytes")
    skill(global_root, "same-id", description="global bytes")

    result = ResolutionEngine().resolve(
        inventory_for((project, RootScope.PROJECT), (global_root, RootScope.GLOBAL)),
        "same-id",
    )

    assert result.status is ResolutionStatus.BLOCKED
    assert result.selected == ()
    assert "CAPABILITY_DIVERGENCE" in result.blockers


def test_project_precedes_identical_global_copy(tmp_path: Path) -> None:
    project = tmp_path / "project"
    global_root = tmp_path / "global"
    project.mkdir()
    global_root.mkdir()
    skill(project, "same-id")
    skill(global_root, "same-id")
    (global_root / "same-id" / "SKILL.md").write_bytes(
        (project / "same-id" / "SKILL.md").read_bytes()
    )

    result = ResolutionEngine().resolve(
        inventory_for((project, RootScope.PROJECT), (global_root, RootScope.GLOBAL)),
        "same-id",
    )

    assert result.status is ResolutionStatus.RESOLVED
    assert result.selected[0].scope is RootScope.PROJECT


def test_dependency_cycle_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for name, dependency in (("a", "b"), ("b", "a")):
        package = root / name
        package.mkdir()
        (package / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: cycle\nversion: 1.0.0\n"
            f"dependencies:\n  - {dependency}\n---\nbody\n",
            encoding="utf-8",
        )

    result = ResolutionEngine().resolve(
        inventory_for((root, RootScope.PROJECT)),
        "a",
    )

    assert result.status is ResolutionStatus.BLOCKED
    assert any(item.status.value == "CYCLE" for item in result.dependencies)


def test_explicit_version_pin_is_honored(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for version in ("1.0.0", "2.0.0"):
        package = root / f"demo-{version}"
        package.mkdir()
        (package / "SKILL.md").write_text(
            f"---\nname: demo\ndescription: {version}\nversion: {version}\n---\nbody\n",
            encoding="utf-8",
        )

    result = ResolutionEngine().resolve(inventory_for((root, RootScope.PROJECT)), "demo@1.0.0")

    assert result.status is ResolutionStatus.RESOLVED
    assert result.selected[0].version == "1.0.0"


def test_divergence_blocks_only_the_affected_version(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for directory, version, description in (
        ("demo-v1-project", "1.0.0", "project bytes"),
        ("demo-v1-global", "1.0.0", "global bytes"),
        ("demo-v2", "2.0.0", "clean bytes"),
    ):
        package = root / directory
        package.mkdir()
        (package / "SKILL.md").write_text(
            f"---\nname: demo\ndescription: {description}\nversion: {version}\n"
            "do_not_activate_when: never\n---\nbody\n",
            encoding="utf-8",
        )

    inventory = inventory_for((root, RootScope.PROJECT))
    engine = ResolutionEngine()
    pinned = engine.resolve(inventory, "demo@2.0.0")
    unpinned = engine.resolve(inventory, "demo")

    assert pinned.status is ResolutionStatus.RESOLVED
    assert pinned.selected[0].version == "2.0.0"
    assert unpinned.status is ResolutionStatus.RESOLVED
    assert unpinned.selected[0].version == "2.0.0"


def test_same_size_metadata_only_byte_divergence_blocks_resolution(tmp_path: Path) -> None:
    project = tmp_path / "project"
    global_root = tmp_path / "global"
    project.mkdir()
    global_root.mkdir()
    project_package = project / "demo"
    global_package = global_root / "demo"
    project_package.mkdir()
    global_package.mkdir()
    skill_bytes = (
        b"---\nname: demo\ndescription: same\nversion: 1.0.0\n"
        b"do_not_activate_when: never\n---\nbody\n"
    )
    (project_package / "SKILL.md").write_bytes(skill_bytes)
    (global_package / "SKILL.md").write_bytes(skill_bytes)
    (project_package / "scripts").mkdir()
    (global_package / "scripts").mkdir()
    (project_package / "scripts" / "payload.py").write_bytes(b"aa")
    (global_package / "scripts" / "payload.py").write_bytes(b"bb")

    inventory = inventory_for(
        (project, RootScope.PROJECT),
        (global_root, RootScope.GLOBAL),
    )
    engine = ResolutionEngine()
    findings = engine.duplicate_report(inventory)
    result = engine.resolve(inventory, "demo")

    assert any(item.category == "DIVERGENT_BYTES" for item in findings)
    assert result.status is ResolutionStatus.BLOCKED
    assert "CAPABILITY_DIVERGENCE" in result.blockers


def test_unreadable_sensitive_bytes_never_count_as_identical_duplicates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    global_root = tmp_path / "global"
    project.mkdir()
    global_root.mkdir()
    for root, secret in ((project, b"aa"), (global_root, b"bb")):
        package = root / "demo"
        package.mkdir()
        (package / "SKILL.md").write_bytes(
            b"---\nname: demo\ndescription: same\nversion: 1.0.0\n"
            b"do_not_activate_when: never\n---\nbody\n"
        )
        (package / ".env").write_bytes(b"TOKEN=" + secret)

    inventory = inventory_for(
        (project, RootScope.PROJECT),
        (global_root, RootScope.GLOBAL),
    )
    engine = ResolutionEngine()
    findings = engine.duplicate_report(inventory)
    result = engine.resolve(inventory, "demo")

    assert any(item.category == "UNVERIFIABLE_BYTES" for item in findings)
    assert result.status is ResolutionStatus.BLOCKED
    assert "CAPABILITY_UNVERIFIABLE_BYTES" in result.blockers


def test_dependency_depth_is_bounded(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for name, dependency in (
        ("root-cap", "level-one"),
        ("level-one", "level-two"),
        ("level-two", ""),
    ):
        package = root / name
        package.mkdir()
        dependency_line = f"dependencies: {dependency}\n" if dependency else ""
        (package / "SKILL.md").write_text(
            f"---\nname: {name}\nversion: 1.0.0\n{dependency_line}"
            "do_not_activate_when: never\n---\nbody\n",
            encoding="utf-8",
        )

    result = ResolutionEngine(Phase3Limits(max_dependency_depth=1)).resolve(
        inventory_for((root, RootScope.PROJECT)),
        "root-cap",
    )

    assert result.status is ResolutionStatus.BLOCKED
    assert "DEPENDENCY_DEPTH" in result.blockers


def test_duplicate_candidate_bound_is_enforced(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    skill(root, "first")
    skill(root, "second")
    inventory = inventory_for((root, RootScope.PROJECT))

    with pytest.raises(ResolutionError, match="duplicate candidate bound"):
        ResolutionEngine(Phase3Limits(max_duplicate_candidates=1)).duplicate_report(inventory)


def test_dependency_version_conflict_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for name, version in (("root-cap", "1.0.0"), ("dep", "1.0.0"), ("dep-v2", "2.0.0")):
        package = root / name
        package.mkdir()
        dependency = "dep@1.0.0" if name == "root-cap" else "dep@2.0.0" if name == "dep" else ""
        (package / "SKILL.md").write_text(
            f"---\nname: {('root-cap' if name == 'root-cap' else 'dep')}\n"
            f"description: {name}\nversion: {version}\n"
            f"{('dependencies: ' + dependency + chr(10)) if dependency else ''}---\nbody\n",
            encoding="utf-8",
        )

    result = ResolutionEngine().resolve(
        inventory_for((root, RootScope.PROJECT)),
        "root-cap",
    )

    assert result.status is ResolutionStatus.BLOCKED
    assert "DEPENDENCY_VERSION_CONFLICT" in result.blockers


def test_semver_release_precedes_prerelease(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for version in ("1.0.0-rc.1", "1.0.0"):
        package = root / version
        package.mkdir()
        (package / "SKILL.md").write_text(
            f"---\nname: demo\nversion: {version}\n---\nbody\n",
            encoding="utf-8",
        )

    result = ResolutionEngine().resolve(inventory_for((root, RootScope.PROJECT)), "demo")

    assert result.status is ResolutionStatus.RESOLVED
    assert result.selected[0].version == "1.0.0"


def test_resolution_rejects_invalid_or_oversized_semver_requests(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    skill(root, "demo")
    inventory = inventory_for((root, RootScope.PROJECT))
    engine = ResolutionEngine()

    with pytest.raises(ResolutionError, match="invalid"):
        engine.resolve(inventory, "demo@1.0.0-01")
    with pytest.raises(ResolutionError, match="invalid"):
        engine.resolve(inventory, "demo@01.0.0")
    with pytest.raises(ResolutionError, match="invalid"):
        engine.resolve(inventory, f"demo@{'9' * 5_000}.0.0")
