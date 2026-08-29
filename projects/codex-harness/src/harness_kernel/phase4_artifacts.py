"""Project-local, symlink-aware artifact capture for Phase 4 host results."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from contextlib import suppress
from pathlib import Path

from .phase4_models import (
    ArtifactRecord,
    ArtifactType,
    CapabilityInvocationRequest,
    FactStatus,
    HostInvocationResult,
)


class ArtifactCaptureError(ValueError):
    """Raised when an artifact cannot be safely confined to the pilot workspace."""


def _assert_directory_tree(root: Path, target: Path) -> None:
    if not root.is_absolute() or not target.is_absolute():
        raise ArtifactCaptureError("artifact paths must be absolute")
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ArtifactCaptureError("artifact path escapes workspace") from exc
    if any(part in {".", ".."} for part in relative.parts):
        raise ArtifactCaptureError("artifact path contains traversal")
    current = root
    paths = (root, *(root / part for part in relative.parts))
    for current in paths:
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise ArtifactCaptureError("artifact path contains a symlink")
        if current != target and not stat.S_ISDIR(metadata.st_mode):
            raise ArtifactCaptureError("artifact parent is not a directory")


def validate_artifact_path(location: str | Path, workspace: str | Path) -> Path:
    workspace_path = _validated_workspace(Path(workspace))
    location_path = Path(location)
    if not location_path.is_absolute():
        raise ArtifactCaptureError("workspace and artifact paths must be absolute")
    _assert_directory_tree(workspace_path, location_path)
    try:
        metadata = location_path.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError as exc:
        raise ArtifactCaptureError("artifact cannot be inspected") from exc
    if metadata is not None and stat.S_ISLNK(metadata.st_mode):
        raise ArtifactCaptureError("artifact path is a symlink")
    try:
        resolved = location_path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ArtifactCaptureError("artifact cannot be resolved") from exc
    if not resolved.is_relative_to(workspace_path):
        raise ArtifactCaptureError("artifact path escapes workspace")
    return resolved


def _validated_workspace(workspace: Path) -> Path:
    if not workspace.is_absolute() or any(part in {".", ".."} for part in workspace.parts):
        raise ArtifactCaptureError("workspace must be an absolute canonical path")
    try:
        metadata = workspace.lstat()
    except (FileNotFoundError, OSError) as exc:
        raise ArtifactCaptureError("workspace cannot be resolved") from exc
    if stat.S_ISLNK(metadata.st_mode) or _has_symlink_component(workspace):
        raise ArtifactCaptureError("workspace contains a symlink")
    if not stat.S_ISDIR(metadata.st_mode):
        raise ArtifactCaptureError("workspace must be a directory")
    try:
        resolved = workspace.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ArtifactCaptureError("workspace cannot be resolved") from exc
    if resolved != workspace:
        raise ArtifactCaptureError("workspace is not canonical")
    return resolved


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            return True
        if stat.S_ISLNK(metadata.st_mode):
            return True
    return False


def _mkdir_safe(path: Path, workspace: Path) -> None:
    workspace_resolved = _validated_workspace(workspace)
    if any(part in {".", ".."} for part in path.parts):
        raise ArtifactCaptureError("artifact directory contains traversal")
    if not path.is_absolute() or not path.is_relative_to(workspace_resolved):
        raise ArtifactCaptureError("artifact directory escapes workspace")
    current = workspace_resolved
    relative = path.relative_to(workspace_resolved)
    for part in relative.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            current.mkdir()
            metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ArtifactCaptureError("artifact directory is unsafe")


def capture_host_response(
    request: CapabilityInvocationRequest,
    result: HostInvocationResult,
    *,
    timestamp: int,
    max_bytes: int,
) -> ArtifactRecord | None:
    if result.final_message is None:
        return None
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise ArtifactCaptureError("artifact byte bound is invalid")
    encoded = result.final_message.encode("utf-8")
    if len(encoded) == 0 or len(encoded) > max_bytes:
        raise ArtifactCaptureError("host response exceeds artifact bound")
    workspace = _validated_workspace(Path(request.workspace))
    artifact_dir = workspace / ".harness" / "phase4" / "artifacts"
    _mkdir_safe(artifact_dir, workspace)
    target = artifact_dir / f"{request.invocation_id}.host-response.txt"
    target = validate_artifact_path(target, workspace)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=artifact_dir,
            prefix=f".{request.invocation_id}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
    except OSError as exc:
        raise ArtifactCaptureError("host response artifact could not be written") from exc
    finally:
        if temporary_name is not None:
            with suppress(OSError):
                Path(temporary_name).unlink(missing_ok=True)
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    return ArtifactRecord(
        artifact_id=f"ART-{request.invocation_id}",
        producer_capability=request.skill_name,
        invocation_id=request.invocation_id,
        location=str(target),
        digest=digest,
        artifact_type=ArtifactType.HOST_RESPONSE,
        timestamp=timestamp,
        provenance=FactStatus.HARNESS_OBSERVED,
        dependencies=(request.invocation_id,),
        evidence_state="CAPTURED",
        size_bytes=len(encoded),
    )


def read_artifact_bytes(
    location: str | Path,
    workspace: str | Path,
    *,
    max_bytes: int = 512 * 1024,
) -> bytes:
    """Read one artifact without following a final symlink or leaving workspace."""

    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise ArtifactCaptureError("artifact byte bound is invalid")
    path = validate_artifact_path(location, workspace)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            data = handle.read(max_bytes + 1)
    except OSError as exc:
        raise ArtifactCaptureError("artifact could not be read safely") from exc
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
    if len(data) > max_bytes:
        raise ArtifactCaptureError("artifact exceeds its verification bound")
    return data
