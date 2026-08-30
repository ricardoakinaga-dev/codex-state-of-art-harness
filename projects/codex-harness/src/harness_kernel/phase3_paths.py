"""Fail-closed filesystem primitives for Phase 3 host inspection."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections import deque
from contextlib import suppress
from pathlib import Path, PurePosixPath

from .phase3_models import CapabilityRoot, Phase3Limits, RootScope, WalkResult


class PathSafetyError(ValueError):
    """Raised when a host path cannot be proven safe to inspect."""


def _validate_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PathSafetyError(f"{label} is invalid")
    return value


def canonicalize_root(
    path: str | Path,
    *,
    root_id: str,
    scope: RootScope | str,
    source: str = "",
    allow_missing: bool = True,
) -> CapabilityRoot:
    """Create a root record after rejecting aliases and non-directories."""

    raw = Path(_validate_text(str(path), "root path"))
    if not raw.is_absolute():
        raise PathSafetyError("host root paths must be absolute")
    try:
        raw_metadata = raw.lstat()
    except FileNotFoundError:
        if not allow_missing:
            raise PathSafetyError("root is unavailable") from None
        resolved = raw.resolve(strict=False)
        return CapabilityRoot(
            root_id,
            scope,
            str(resolved),
            source=source,
            readable=False,
            mutable=False,
            confidence="OBSERVED",
            canonical_path=str(resolved),
            security_status="UNAVAILABLE",
        )
    except OSError as exc:
        raise PathSafetyError("root metadata is unavailable") from exc
    if stat.S_ISLNK(raw_metadata.st_mode):
        raise PathSafetyError("symlink roots are not accepted")
    if not stat.S_ISDIR(raw_metadata.st_mode):
        raise PathSafetyError("root must be a directory")
    try:
        resolved = raw.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PathSafetyError("root cannot be canonicalized") from exc
    if not resolved.is_dir():
        raise PathSafetyError("root must resolve to a directory")
    readable = os.access(resolved, os.R_OK | os.X_OK)
    return CapabilityRoot(
        root_id,
        scope,
        str(raw),
        source=source,
        readable=readable,
        mutable=False,
        confidence="OBSERVED",
        canonical_path=str(resolved),
        security_status="VALIDATED" if readable else "UNREADABLE",
    )


def _root_path(root: CapabilityRoot | str | Path) -> Path:
    if isinstance(root, CapabilityRoot):
        configured = Path(_validate_text(root.path, "root path"))
        claimed = Path(_validate_text(root.canonical_path or root.path, "canonical root path"))
        if not claimed.is_absolute():
            raise PathSafetyError("canonical root path must be absolute")
        try:
            if configured.resolve(strict=False) != claimed.resolve(strict=False):
                raise PathSafetyError("canonical root path does not match claimed root")
        except (OSError, RuntimeError) as exc:
            raise PathSafetyError("root cannot be canonicalized") from exc
        value = configured
    else:
        value = Path(_validate_text(str(root), "root path"))
    path = value if isinstance(value, Path) else Path(_validate_text(str(value), "root path"))
    if not path.is_absolute():
        raise PathSafetyError("base path must be absolute")
    return path


def canonical_root_key(root: CapabilityRoot | str | Path) -> str:
    """Return the canonical comparison key for a validated root reference."""

    try:
        return str(_root_path(root).resolve(strict=False))
    except (OSError, RuntimeError, ValueError) as exc:
        raise PathSafetyError("root cannot be canonicalized") from exc


def _validated_base(base: Path, *, missing_ok: bool = False) -> Path | None:
    """Validate the base directory without following a final symlink."""

    try:
        metadata = base.lstat()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise PathSafetyError("base package is unavailable") from None
    except OSError as exc:
        raise PathSafetyError("base package metadata is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise PathSafetyError("symlink base directories are not inspected")
    if not stat.S_ISDIR(metadata.st_mode):
        raise PathSafetyError("base package must be a directory")
    try:
        resolved = base.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PathSafetyError("base package cannot be canonicalized") from exc
    if not resolved.is_dir():
        raise PathSafetyError("base package must resolve to a directory")
    return resolved


def _relative_parts(relative: str) -> tuple[str, ...]:
    normalized = _validate_text(relative, "relative path").replace("\\", "/")
    if normalized.startswith("/"):
        raise PathSafetyError("absolute paths are not allowed")
    parts = tuple(PurePosixPath(normalized).parts)
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise PathSafetyError("relative path contains traversal or empty components")
    return parts


def safe_relative_path(root: CapabilityRoot | str | Path, relative: str) -> str:
    """Return a normalized relative path only if it stays under ``root``."""

    parts = _relative_parts(relative)
    base = _root_path(root)
    candidate = base.joinpath(*parts)
    try:
        candidate.resolve(strict=False).relative_to(base.resolve(strict=False))
    except (OSError, RuntimeError, ValueError) as exc:
        raise PathSafetyError("relative path escapes its root") from exc
    return "/".join(parts)


def is_metadata_only_surface(relative: str) -> bool:
    """Return whether a file is below a scripts/assets metadata boundary."""

    parts = _relative_parts(relative)
    return any(part.casefold() in {"scripts", "assets"} for part in parts[:-1])


_SENSITIVE_NAME = re.compile(
    r"(?:^\.env(?:\..*)?$|(?:secret|token|password|credential)|"
    r"(?:^|[._-])(?:id_rsa|id_ed25519|private[_-]?key)(?:$|[._-])|"
    r"\.(?:pem|key|p12|pfx|kdbx)$)",
    re.I,
)


def is_sensitive_relative_path(relative: str) -> bool:
    """Return whether a relative path is too likely to contain credentials."""

    parts = _relative_parts(relative)
    return any(_SENSITIVE_NAME.search(part) for part in parts)


def _directory_flags() -> int:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if not all(hasattr(os, name) for name in required) or os.open not in os.supports_dir_fd:
        raise PathSafetyError("secure directory traversal is unavailable")
    directory_flag = os.O_DIRECTORY
    nofollow_flag = os.O_NOFOLLOW
    return os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | directory_flag | nofollow_flag


def _open_directory(value: str | Path, *, parent_fd: int | None = None) -> int:
    flags = _directory_flags()
    try:
        if parent_fd is None:
            descriptor = os.open(str(value), flags)
        else:
            descriptor = os.open(str(value), flags, dir_fd=parent_fd)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise PathSafetyError("directory cannot be opened safely") from exc
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise PathSafetyError("only directories may be opened")
    except BaseException:
        with suppress(OSError):
            os.close(descriptor)
        raise
    return descriptor


def _open_relative(
    base: Path,
    parts: tuple[str, ...],
    *,
    flags: int,
    expected_base_identity: tuple[int, int] | None = None,
) -> int:
    validated_base = _validated_base(base)
    assert validated_base is not None
    current = _open_directory(validated_base)
    try:
        if expected_base_identity is not None:
            metadata = os.fstat(current)
            identity = (metadata.st_dev, metadata.st_ino)
            if identity != expected_base_identity:
                raise PathSafetyError("base directory changed during safe open")
        for part in parts[:-1]:
            child = _open_directory(part, parent_fd=current)
            with suppress(OSError):
                os.close(current)
            current = child
        try:
            descriptor = os.open(parts[-1], flags, dir_fd=current)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise PathSafetyError("path cannot be opened safely") from exc
        return descriptor
    finally:
        with suppress(OSError):
            os.close(current)


def read_bounded_file(
    base: str | Path,
    relative: str,
    *,
    max_bytes: int,
    expected_base_identity: tuple[int, int] | None = None,
) -> bytes:
    """Read a regular, non-sensitive file through descriptor-relative opens."""

    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise PathSafetyError("max_bytes must be a positive integer")
    validated_base = _validated_base(Path(base))
    assert validated_base is not None
    base_metadata = validated_base.lstat()
    safe_base_identity = expected_base_identity or (base_metadata.st_dev, base_metadata.st_ino)
    parts = _relative_parts(relative)
    if is_sensitive_relative_path(relative):
        raise PathSafetyError("sensitive file content is not readable")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor: int | None = None
    payload = b""
    try:
        descriptor = _open_relative(
            Path(base),
            parts,
            flags=flags,
            expected_base_identity=safe_base_identity,
        )
        opened_metadata = os.fstat(descriptor)
        if not stat.S_ISREG(opened_metadata.st_mode):
            raise PathSafetyError("only regular files may be read")
        if opened_metadata.st_nlink > 1:
            raise PathSafetyError("hard link aliases are not readable")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            payload = handle.read(max_bytes + 1)
    except PathSafetyError:
        raise
    except OSError as exc:
        raise PathSafetyError("file cannot be read") from exc
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
    if len(payload) > max_bytes:
        raise PathSafetyError("file exceeds its bound")
    return payload


def bounded_file_metadata(
    base: str | Path,
    relative: str,
    *,
    expected_base_identity: tuple[int, int] | None = None,
) -> tuple[int, bool]:
    """Inspect size/executable metadata without reading file content."""

    validated_base = _validated_base(Path(base))
    assert validated_base is not None
    base_metadata = validated_base.lstat()
    safe_base_identity = expected_base_identity or (base_metadata.st_dev, base_metadata.st_ino)
    parts = _relative_parts(relative)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = _open_relative(
            Path(base),
            parts,
            flags=flags,
            expected_base_identity=safe_base_identity,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PathSafetyError("only regular files may be inspected")
        if metadata.st_nlink > 1:
            raise PathSafetyError("hard link aliases are not inspectable")
        return metadata.st_size, bool(metadata.st_mode & 0o111)
    except FileNotFoundError:
        raise PathSafetyError("file is unavailable") from None
    except OSError as exc:
        raise PathSafetyError("file metadata is unavailable") from exc
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)


def bounded_walk(root: CapabilityRoot | str | Path, limits: Phase3Limits) -> WalkResult:
    """Walk directories without following links, with deterministic bounds."""

    base = _root_path(root)
    validated_base = _validated_base(base, missing_ok=True)
    if validated_base is None:
        return WalkResult((), errors=("root is unavailable",))
    base = validated_base
    try:
        root_fd = _open_directory(base)
    except FileNotFoundError:
        return WalkResult((), errors=("root is unavailable",))
    queue: deque[tuple[int, str, int]] = deque([(root_fd, "", 0)])
    visited: set[tuple[int, int]] = set()
    files: list[str] = []
    unsafe: list[str] = []
    errors: list[str] = []
    seen_casefold: set[str] = set()
    seen_file_inodes: set[tuple[int, int]] = set()
    seen_file_paths: dict[tuple[int, int], str] = {}
    total_bytes = 0
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        while queue:
            directory_fd, prefix, depth = queue.popleft()
            try:
                metadata = os.fstat(directory_fd)
                inode = (metadata.st_dev, metadata.st_ino)
                if inode in visited:
                    unsafe.append(prefix or ".")
                    continue
                visited.add(inode)
                scan_fd = os.dup(directory_fd)
                try:
                    with os.scandir(scan_fd) as iterator:
                        entries: list[tuple[str, os.stat_result | None, str | None]] = []
                        for item in sorted(iterator, key=lambda value: value.name):
                            try:
                                entries.append((item.name, item.stat(follow_symlinks=False), None))
                            except OSError as exc:
                                entries.append((item.name, None, type(exc).__name__))
                except OSError as exc:
                    errors.append(f"{prefix or '.'}: {type(exc).__name__}")
                    continue
                finally:
                    with suppress(OSError):
                        os.close(scan_fd)
                for entry_name, entry_stat, entry_error in entries:
                    relative = f"{prefix}/{entry_name}" if prefix else entry_name
                    case_key = relative.casefold()
                    if case_key in seen_casefold:
                        unsafe.append(relative)
                        if entry_stat is not None and stat.S_ISREG(entry_stat.st_mode):
                            collision_inode = (entry_stat.st_dev, entry_stat.st_ino)
                            original = seen_file_paths.get(collision_inode)
                            if original is not None and original not in unsafe:
                                unsafe.append(original)
                            seen_file_inodes.add(collision_inode)
                            seen_file_paths.setdefault(collision_inode, relative)
                        continue
                    seen_casefold.add(case_key)
                    if entry_stat is None:
                        errors.append(f"{relative}: {entry_error or 'OSError'}")
                        continue
                    mode = entry_stat.st_mode
                    if stat.S_ISLNK(mode):
                        unsafe.append(relative)
                        continue
                    if stat.S_ISDIR(mode):
                        if depth >= limits.max_depth:
                            errors.append(f"{relative}: depth bound")
                            continue
                        try:
                            child_fd = _open_directory(entry_name, parent_fd=directory_fd)
                        except FileNotFoundError:
                            errors.append(f"{relative}: FileNotFoundError")
                            continue
                        except PathSafetyError:
                            unsafe.append(relative)
                            continue
                        queue.append((child_fd, relative, depth + 1))
                        continue
                    if not stat.S_ISREG(mode):
                        errors.append(f"{relative}: non-regular entry")
                        continue
                    if entry_stat.st_nlink > 1:
                        unsafe.append(relative)
                        continue
                    descriptor: int | None = None
                    try:
                        descriptor = os.open(entry_name, file_flags, dir_fd=directory_fd)
                        opened = os.fstat(descriptor)
                        if not stat.S_ISREG(opened.st_mode):
                            errors.append(f"{relative}: non-regular entry")
                            continue
                    except OSError:
                        unsafe.append(relative)
                        continue
                    finally:
                        if descriptor is not None:
                            with suppress(OSError):
                                os.close(descriptor)
                    file_inode = (opened.st_dev, opened.st_ino)
                    if file_inode in seen_file_inodes:
                        unsafe.append(relative)
                        original = seen_file_paths.get(file_inode)
                        if original is not None and original not in unsafe:
                            unsafe.append(original)
                        continue
                    seen_file_inodes.add(file_inode)
                    seen_file_paths[file_inode] = relative
                    if len(files) >= limits.max_total_files:
                        raise PathSafetyError("file count bound exceeded")
                    next_total = total_bytes + opened.st_size
                    if next_total > limits.max_total_bytes:
                        raise PathSafetyError("total byte bound exceeded")
                    files.append(relative)
                    total_bytes = next_total
            finally:
                with suppress(OSError):
                    os.close(directory_fd)
    finally:
        while queue:
            descriptor, _, _ = queue.popleft()
            with suppress(OSError):
                os.close(descriptor)
    return WalkResult(tuple(files), tuple(unsafe), tuple(errors), total_bytes)


def digest_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def digest_file(base: str | Path, relative: str, *, max_bytes: int) -> tuple[bytes, str]:
    payload = read_bounded_file(base, relative, max_bytes=max_bytes)
    return payload, digest_bytes(payload)


def redact_path(
    path: str | Path,
    *,
    workspace_root: str | Path | None = None,
    home_dir: str | Path | None = None,
    root_id: str | None = None,
) -> str:
    """Produce a stable public path token without leaking host directories."""

    try:
        value = Path(path).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return "$REDACTED_PATH"
    for label, root in (("$WORKSPACE", workspace_root), ("$HOME", home_dir)):
        if root is None:
            continue
        try:
            anchor = Path(root).resolve(strict=False)
            relative = value.relative_to(anchor)
        except (OSError, RuntimeError, ValueError):
            continue
        return f"{label}/{relative.as_posix()}" if str(relative) != "." else label
    if root_id:
        return f"${root_id}/" + hashlib.sha256(str(value).encode()).hexdigest()[:12]
    return "$EXTERNAL/" + hashlib.sha256(str(value).encode()).hexdigest()[:12]
