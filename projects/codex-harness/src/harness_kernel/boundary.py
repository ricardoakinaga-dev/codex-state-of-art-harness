"""Project-local path and atomic persistence primitives for Phase 2."""

from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .errors import ContractError
from .serialization import MAX_JSON_BYTES, from_json, to_json


class BoundaryError(ValueError):
    """Raised when an input or output would cross the project boundary."""


@dataclass(frozen=True, slots=True)
class ProjectBoundary:
    """Confine all reads and writes to one existing project directory."""

    root: Path | str
    max_file_bytes: int = MAX_JSON_BYTES

    def __post_init__(self) -> None:
        root = Path(self.root)
        try:
            resolved = root.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise BoundaryError("project root is unavailable") from exc
        if not resolved.is_dir():
            raise BoundaryError("project root must be a directory")
        if (
            not isinstance(self.max_file_bytes, int)
            or isinstance(self.max_file_bytes, bool)
            or self.max_file_bytes < 1
        ):
            raise BoundaryError("file size limit must be a positive integer")
        object.__setattr__(self, "root", resolved)

    @staticmethod
    def _validate_relative(value: str) -> str:
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise BoundaryError("project path is invalid")
        normalized = value.replace("\\", "/")
        path = Path(normalized)
        if path.is_absolute() or normalized.startswith("/"):
            raise BoundaryError("absolute paths are not allowed")
        if any(part == ".." for part in normalized.split("/")):
            raise BoundaryError("parent traversal is not allowed")
        return normalized

    def resolve(self, relative: str, *, allow_missing: bool = False) -> Path:
        """Resolve a project-relative path and reject symlink escapes."""

        normalized = self._validate_relative(relative)
        root = Path(self.root)
        candidate = root / normalized
        try:
            resolved = candidate.resolve(strict=not allow_missing)
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise BoundaryError("path is outside or unavailable in the project") from exc
        return resolved

    def read_bytes(self, relative: str, *, max_bytes: int | None = None) -> bytes:
        limit = self.max_file_bytes if max_bytes is None else max_bytes
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise BoundaryError("file size limit must be a positive integer")
        path = self.resolve(relative)
        if not path.is_file():
            raise BoundaryError("project path is not a regular file")
        try:
            with path.open("rb") as handle:
                data = handle.read(limit + 1)
        except (OSError, ValueError) as exc:
            raise BoundaryError("project file could not be read") from exc
        if len(data) > limit:
            raise BoundaryError("project file exceeds its size limit")
        return data

    def read_json(self, relative: str, *, max_bytes: int | None = None) -> object:
        """Read JSON with duplicate-key and non-finite-number rejection."""

        try:
            return from_json(self.read_bytes(relative, max_bytes=max_bytes), dict)
        except (ContractError, TypeError, ValueError) as exc:
            raise BoundaryError("project JSON is invalid") from exc

    def _target_for_write(self, relative: str) -> Path:
        normalized = self._validate_relative(relative)
        target = Path(self.root).joinpath(*Path(normalized).parts)
        parent = Path(self.root)
        for component in Path(normalized).parent.parts:
            if component == ".":
                continue
            parent = parent / component
            try:
                metadata = parent.lstat()
            except FileNotFoundError:
                try:
                    parent.mkdir()
                    metadata = parent.lstat()
                except (OSError, RuntimeError, ValueError) as exc:
                    raise BoundaryError("project write directory is unavailable") from exc
            except (OSError, RuntimeError, ValueError) as exc:
                raise BoundaryError("project write directory is unavailable") from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise BoundaryError("refusing a symlinked write directory")
            if not stat.S_ISDIR(metadata.st_mode):
                raise BoundaryError("project write parent is not a directory")
        try:
            if stat.S_ISLNK(target.lstat().st_mode):
                raise BoundaryError("refusing to replace a symlink output")
        except FileNotFoundError:
            pass
        except (OSError, RuntimeError, ValueError) as exc:
            raise BoundaryError("project output is unavailable") from exc
        return target

    def atomic_write_bytes(self, relative: str, data: bytes) -> Path:
        """Atomically replace a project-local file without following output links."""

        if not isinstance(data, bytes):
            raise BoundaryError("atomic bytes writes require bytes")
        if len(data) > self.max_file_bytes:
            raise BoundaryError("project output exceeds its size limit")
        target = self._target_for_write(relative)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=target.parent, prefix=f".{target.name}.", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            temporary = None
            directory_fd = os.open(str(target.parent), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return target
        except (OSError, ValueError) as exc:
            raise BoundaryError("project output could not be committed atomically") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def atomic_write_json(self, relative: str, value: Mapping[str, object] | list[object]) -> Path:
        payload = to_json(value).encode("utf-8")
        return self.atomic_write_bytes(relative, payload)

    def append_jsonl(
        self,
        relative: str,
        value: Mapping[str, object],
        *,
        max_records: int = 1_024,
    ) -> Path:
        """Append one bounded JSON object by atomically replacing the local log."""

        if not isinstance(value, Mapping):
            raise BoundaryError("JSONL records must be objects")
        if not isinstance(max_records, int) or isinstance(max_records, bool) or max_records < 1:
            raise BoundaryError("JSONL record limit must be positive")
        target = self._target_for_write(relative)
        existing = b""
        if target.exists():
            existing = self.read_bytes(relative)
        lines = [line for line in existing.splitlines() if line.strip()]
        if len(lines) >= max_records:
            raise BoundaryError("JSONL record limit exceeded")
        for line in lines:
            try:
                parsed = from_json(line, dict)
            except (ContractError, TypeError, ValueError) as exc:
                raise BoundaryError("existing JSONL log is corrupt") from exc
            if not isinstance(parsed, Mapping):
                raise BoundaryError("existing JSONL record is not an object")
        encoded = to_json(value).encode("utf-8") + b"\n"
        return self.atomic_write_bytes(relative, existing + encoded)
