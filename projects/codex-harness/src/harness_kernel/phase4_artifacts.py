"""Project-local, symlink-aware artifact capture for Phase 4 host results."""

from __future__ import annotations

import hashlib
import os
import stat
import uuid
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
        except ValueError as exc:
            raise ArtifactCaptureError("artifact path cannot be inspected") from exc
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
    except (OSError, ValueError) as exc:
        raise ArtifactCaptureError("artifact cannot be inspected") from exc
    if metadata is not None and stat.S_ISLNK(metadata.st_mode):
        raise ArtifactCaptureError("artifact path is a symlink")
    try:
        resolved = location_path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ArtifactCaptureError("artifact cannot be resolved") from exc
    if not resolved.is_relative_to(workspace_path):
        raise ArtifactCaptureError("artifact path escapes workspace")
    return resolved


def _validated_workspace(workspace: Path) -> Path:
    if not workspace.is_absolute() or any(part in {".", ".."} for part in workspace.parts):
        raise ArtifactCaptureError("workspace must be an absolute canonical path")
    try:
        metadata = workspace.lstat()
    except (FileNotFoundError, OSError, ValueError) as exc:
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
        except (OSError, ValueError):
            return True
        if stat.S_ISLNK(metadata.st_mode):
            return True
    return False


def _mkdir_safe(path: Path, workspace: Path) -> None:
    descriptor = _open_confined_directory(path, workspace)
    os.close(descriptor)


def _open_confined_directory(path: Path, workspace: Path) -> int:
    """Open/create a directory below workspace using descriptor-relative no-follow steps."""

    workspace_resolved = _validated_workspace(workspace)
    if any(part in {".", ".."} for part in path.parts):
        raise ArtifactCaptureError("artifact directory contains traversal")
    if not path.is_absolute() or not path.is_relative_to(workspace_resolved):
        raise ArtifactCaptureError("artifact directory escapes workspace")
    relative = path.relative_to(workspace_resolved)
    if any(not part for part in relative.parts):
        raise ArtifactCaptureError("artifact directory contains an empty component")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ArtifactCaptureError("artifact directories cannot be secured on this platform")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(workspace_resolved, flags)
        for part in relative.parts:
            next_descriptor: int | None = None
            try:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                with suppress(FileExistsError):
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
            try:
                metadata = os.fstat(next_descriptor)
            except OSError:
                with suppress(OSError):
                    os.close(next_descriptor)
                raise
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(next_descriptor)
                raise ArtifactCaptureError("artifact directory is unsafe")
            os.close(descriptor)
            descriptor = next_descriptor
        if descriptor is None:  # pragma: no cover - workspace open always assigns it
            raise ArtifactCaptureError("artifact directory cannot be opened")
        return descriptor
    except ArtifactCaptureError:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        raise ArtifactCaptureError("artifact directory cannot be opened safely") from exc


def _atomic_write_at(directory_fd: int, name: str, content: bytes) -> None:
    """Write one regular file without reopening a pathname outside its pinned directory."""

    if not name or Path(name).name != name or "\x00" in name:
        raise ArtifactCaptureError("artifact filename is unsafe")
    try:
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        metadata = None
    if metadata is not None and (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise ArtifactCaptureError("artifact target is not a unique regular file")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    temporary_name: str | None = None
    descriptor: int | None = None
    try:
        for _ in range(8):
            candidate = f".{name}.{uuid.uuid4().hex}.tmp"
            try:
                descriptor = os.open(candidate, flags, 0o600, dir_fd=directory_fd)
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if descriptor is None or temporary_name is None:
            raise ArtifactCaptureError("artifact temporary file could not be created")
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise ArtifactCaptureError("artifact temporary file could not be written")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(
            temporary_name,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
        temporary_name = None
    except OSError as exc:
        raise ArtifactCaptureError("artifact could not be written atomically") from exc
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        if temporary_name is not None:
            with suppress(OSError):
                os.unlink(temporary_name, dir_fd=directory_fd)


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
    target_name = f"{request.invocation_id}.host-response.txt"
    target = artifact_dir / target_name
    directory_fd = _open_confined_directory(artifact_dir, workspace)
    try:
        _atomic_write_at(directory_fd, target_name, encoded)
        directory_identity = os.fstat(directory_fd)
    finally:
        with suppress(OSError):
            os.close(directory_fd)
    try:
        current_identity = artifact_dir.lstat()
    except OSError as exc:
        raise ArtifactCaptureError("artifact directory changed during capture") from exc
    if (current_identity.st_dev, current_identity.st_ino) != (
        directory_identity.st_dev,
        directory_identity.st_ino,
    ):
        raise ArtifactCaptureError("artifact directory changed during capture")
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
    directory_fd = _open_confined_directory(path.parent, Path(workspace))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path.name, flags, dir_fd=directory_fd)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ArtifactCaptureError("artifact is not a unique regular file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            data = handle.read(max_bytes + 1)
    except ArtifactCaptureError:
        raise
    except OSError as exc:
        raise ArtifactCaptureError("artifact could not be read safely") from exc
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        with suppress(OSError):
            os.close(directory_fd)
    if len(data) > max_bytes:
        raise ArtifactCaptureError("artifact exceeds its verification bound")
    return data
