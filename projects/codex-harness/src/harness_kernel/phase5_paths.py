"""Project-bound path helpers for the Phase 5 command surface."""

from __future__ import annotations

import stat
from pathlib import Path


class Phase5CliError(ValueError):
    """Raised when a Phase 5 CLI request cannot be represented safely."""


def resolved_project_root(value: Path) -> Path:
    try:
        root = value.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise Phase5CliError("project root is unavailable") from exc
    if not root.is_dir():
        raise Phase5CliError("project root is not a directory")
    return root


def safe_project_path(root: Path, value: Path, label: str, *, must_exist: bool = False) -> Path:
    candidate = value if value.is_absolute() else root / value
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise Phase5CliError(f"{label} contains an unsafe path component")
    _reject_symlink_components(root, label)
    _reject_symlink_components(candidate, label)
    try:
        resolved = candidate.resolve(strict=must_exist)
    except (OSError, RuntimeError) as exc:
        raise Phase5CliError(f"{label} is unavailable") from exc
    if not resolved.is_relative_to(root):
        raise Phase5CliError(f"{label} must remain inside project root")
    return resolved


def _reject_symlink_components(path: Path, label: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise Phase5CliError(f"{label} cannot be inspected") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise Phase5CliError(f"{label} cannot contain symlinks")


def task_path(root: Path, requested: Path | None) -> Path:
    return safe_project_path(
        root,
        requested or Path("tests/fixtures/phase5/design-pilot/task.json"),
        "task",
        must_exist=True,
    )


def policy_path(root: Path, requested: Path | None) -> Path:
    return safe_project_path(
        root,
        requested or Path("config/phase5-composition-policy.json"),
        "policy",
        must_exist=True,
    )


def evidence_path(root: Path, requested: Path | None) -> Path:
    return safe_project_path(
        root,
        requested or Path("evidence/phase-5/pilots/design-director"),
        "evidence directory",
    )
