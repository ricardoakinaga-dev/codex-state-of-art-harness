from __future__ import annotations

from pathlib import Path

import pytest

from harness_kernel.phase4_artifacts import (
    ArtifactCaptureError,
    read_artifact_bytes,
    validate_artifact_path,
)


def test_artifact_paths_reject_traversal_and_nested_symlinks(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "safe.txt").write_text("safe", encoding="utf-8")
    (workspace / "nested-link").symlink_to(outside, target_is_directory=True)
    workspace_alias = tmp_path / "workspace-alias"
    workspace_alias.symlink_to(workspace, target_is_directory=True)

    with pytest.raises(ArtifactCaptureError):
        validate_artifact_path(workspace / ".." / "outside.txt", workspace)
    with pytest.raises(ArtifactCaptureError):
        validate_artifact_path(workspace / "nested-link" / "escape.txt", workspace)
    with pytest.raises(ArtifactCaptureError):
        validate_artifact_path(workspace_alias / "safe.txt", workspace_alias)


def test_artifact_read_does_not_follow_final_symlink(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "target.txt"
    target.write_text("bounded", encoding="utf-8")
    link = workspace / "link.txt"
    link.symlink_to(target)

    assert read_artifact_bytes(target, workspace) == b"bounded"
    with pytest.raises(ArtifactCaptureError):
        read_artifact_bytes(link, workspace)
