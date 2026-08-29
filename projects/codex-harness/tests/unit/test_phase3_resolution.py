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
