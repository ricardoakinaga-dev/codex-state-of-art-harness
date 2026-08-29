from __future__ import annotations

from pathlib import Path

import pytest

from harness_kernel.phase3_models import Phase3Limits
from harness_kernel.phase3_paths import (
    PathSafetyError,
    bounded_file_metadata,
    bounded_walk,
    canonicalize_root,
    read_bounded_file,
    safe_relative_path,
)


def test_canonical_root_and_bounded_walk_are_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = root / "demo"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    (package / "references").mkdir()
    (package / "references" / "guide.md").write_text("guide", encoding="utf-8")

    canonical = canonicalize_root(root, root_id="project", scope="PROJECT")
    walked = bounded_walk(canonical, Phase3Limits())

    assert walked.files == ("demo/SKILL.md", "demo/references/guide.md")
    assert walked.total_bytes == len("---\nname: demo\n---\n") + len("guide")


def test_path_policy_rejects_traversal_absolute_and_nul(tmp_path: Path) -> None:
    root = canonicalize_root(tmp_path, root_id="root", scope="PROJECT")

    for candidate in ("../secret", "/etc/passwd", "nested/\x00file"):
        with pytest.raises(PathSafetyError):
            safe_relative_path(root, candidate)


def test_nested_symlink_and_escaping_reference_are_not_read(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = root / "demo"
    outside = tmp_path / "outside.md"
    package.mkdir(parents=True)
    outside.write_text("secret", encoding="utf-8")
    link = package / "references"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable")

    canonical = canonicalize_root(root, root_id="root", scope="PROJECT")
    walked = bounded_walk(canonical, Phase3Limits())

    assert walked.unsafe_paths == ("demo/references",)
    with pytest.raises(PathSafetyError):
        read_bounded_file(package, "../outside.md", max_bytes=100)


def test_symlink_root_and_base_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "file.txt").write_text("safe", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")

    with pytest.raises(PathSafetyError):
        bounded_walk(link, Phase3Limits())
    with pytest.raises(PathSafetyError):
        read_bounded_file(link, "file.txt", max_bytes=100)


def test_bounds_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    (root / "large.txt").write_text("x" * 20, encoding="utf-8")

    with pytest.raises(PathSafetyError):
        bounded_walk(
            canonicalize_root(root, root_id="root", scope="PROJECT"),
            Phase3Limits(max_total_bytes=10),
        )


def test_depth_bound_is_reported_instead_of_silently_truncating(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    nested = root / "one" / "two" / "three"
    nested.mkdir(parents=True)
    (nested / "SKILL.md").write_text("---\nname: deep\n---\n", encoding="utf-8")

    walked = bounded_walk(
        canonicalize_root(root, root_id="root", scope="PROJECT"),
        Phase3Limits(max_depth=1),
    )

    assert walked.files == ()
    assert walked.errors


def test_case_collision_and_hardlink_alias_are_reported(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    (root / "Readme.md").write_text("one", encoding="utf-8")
    (root / "README.md").write_text("two", encoding="utf-8")
    try:
        (root / "alias.md").hardlink_to(root / "Readme.md")
    except OSError:
        pytest.skip("hardlinks are unavailable")

    walked = bounded_walk(canonicalize_root(root, root_id="root", scope="PROJECT"), Phase3Limits())

    assert set(walked.unsafe_paths) == {"Readme.md", "alias.md"}


def test_sensitive_file_content_is_not_read(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    (root / ".env").write_text("TOKEN=do-not-read", encoding="utf-8")

    assert bounded_file_metadata(root, ".env")[0] > 0
    with pytest.raises(PathSafetyError, match="sensitive"):
        read_bounded_file(root, ".env", max_bytes=100)
