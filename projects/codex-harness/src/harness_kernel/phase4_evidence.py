"""Sanitized serialization and project-local evidence helpers for Phase 4."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

from .phase4_artifacts import ArtifactCaptureError, _atomic_write_at, _open_confined_directory
from .phase4_models import ExecutionOutcome, canonical_json, digest_payload, public_data


class EvidenceError(ValueError):
    """Raised when an evidence path or payload is unsafe."""


_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|password|passwd|secret|bearer)\b"
    r"\s*[:=]\s*)([^\s,;]+)"
)
_TOKEN_PATTERN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,})\b")
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|password|passwd|secret|bearer|private[_-]?key)"
)


def _redact_string(value: str, *, workspace: Path | None, home: Path | None) -> str:
    result = value
    if workspace is not None:
        result = result.replace(str(workspace), "$WORKSPACE")
    if home is not None:
        result = result.replace(str(home), "$HOME")
    result = _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", result)
    return _TOKEN_PATTERN.sub("[REDACTED_TOKEN]", result)


def redact_paths(value: object, *, workspace: str | Path | None = None) -> object:
    workspace_path = Path(workspace).resolve() if workspace is not None else None
    home_path = Path.home().resolve()
    if isinstance(value, str):
        return _redact_string(value, workspace=workspace_path, home=home_path)
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]"
            if _SENSITIVE_KEY_PATTERN.search(str(key))
            else redact_paths(item, workspace=workspace_path)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact_paths(item, workspace=workspace_path) for item in value]
    return value


def public_outcome(
    outcome: ExecutionOutcome, *, workspace: str | Path | None = None
) -> dict[str, object]:
    value = redact_paths(public_data(outcome), workspace=workspace)
    if not isinstance(value, dict):
        raise EvidenceError("outcome serialization did not produce an object")
    value["schema_version"] = "P4-OUTCOME-1"
    return value


def _safe_relative(root: Path, relative: str | Path) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or "\x00" in str(candidate):
        raise EvidenceError("evidence path must be relative")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise EvidenceError("evidence path contains an unsafe component")
    root_resolved = root.resolve(strict=True)
    target = root_resolved / candidate
    if not target.is_relative_to(root_resolved):
        raise EvidenceError("evidence path escapes root")
    return target


class EvidenceWriter:
    """Write only bounded, atomic files below a project-owned evidence root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        if not self.root.is_absolute():
            raise EvidenceError("evidence root must be absolute")
        workspace = self.root
        while True:
            try:
                workspace.lstat()
                break
            except FileNotFoundError:
                if workspace.parent == workspace:
                    raise EvidenceError("evidence root cannot be created") from None
                workspace = workspace.parent
            except OSError as exc:
                raise EvidenceError("evidence root cannot be inspected") from exc
        try:
            descriptor = _open_confined_directory(self.root, workspace)
        except ArtifactCaptureError as exc:
            raise EvidenceError("evidence root is unsafe") from exc
        try:
            self.root = self.root.resolve(strict=True)
        finally:
            os.close(descriptor)

    def write_text(
        self, relative: str | Path, content: str, *, max_bytes: int = 512 * 1024
    ) -> Path:
        if not isinstance(content, str) or "\x00" in content:
            raise EvidenceError("evidence text is invalid")
        encoded = content.encode("utf-8")
        return self.write_bytes(relative, encoded, max_bytes=max_bytes)

    def write_bytes(
        self, relative: str | Path, content: bytes, *, max_bytes: int = 512 * 1024
    ) -> Path:
        if not isinstance(content, bytes):
            raise EvidenceError("evidence bytes are invalid")
        encoded = content
        if len(encoded) > max_bytes:
            raise EvidenceError("evidence text exceeds its bound")
        target = _safe_relative(self.root, relative)
        try:
            directory_fd = _open_confined_directory(target.parent, self.root)
        except ArtifactCaptureError as exc:
            raise EvidenceError("evidence directory is unsafe") from exc
        try:
            _atomic_write_at(directory_fd, target.name, encoded)
            directory_identity = os.fstat(directory_fd)
        except ArtifactCaptureError as exc:
            raise EvidenceError("evidence file could not be written") from exc
        finally:
            with suppress(OSError):
                os.close(directory_fd)
        try:
            current_identity = target.parent.lstat()
        except OSError as exc:
            raise EvidenceError("evidence directory changed during write") from exc
        if (current_identity.st_dev, current_identity.st_ino) != (
            directory_identity.st_dev,
            directory_identity.st_ino,
        ):
            raise EvidenceError("evidence directory changed during write")
        return target

    def write_json(
        self, relative: str | Path, value: object, *, max_bytes: int = 512 * 1024
    ) -> Path:
        try:
            content = (
                json.dumps(
                    redact_paths(public_data(value)),
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            )
        except (TypeError, ValueError, RecursionError) as exc:
            raise EvidenceError("evidence JSON cannot be serialized safely") from exc
        return self.write_text(relative, content, max_bytes=max_bytes)


def build_review_manifest(
    root: str | Path,
    payload_paths: tuple[str, ...],
    *,
    bound_files: tuple[tuple[str, str | Path], ...] = (),
) -> dict[str, object]:
    evidence_root = Path(root).resolve(strict=True)
    entries: list[dict[str, object]] = []
    for relative in sorted(set(payload_paths)):
        path = _safe_relative(evidence_root, relative)
        if not path.is_file() or path.is_symlink():
            raise EvidenceError(f"payload evidence file is unavailable: {relative}")
        data = path.read_bytes()
        entries.append(
            {
                "scope": "evidence",
                "path": relative,
                "size_bytes": len(data),
                "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
            }
        )
    for label, candidate in sorted(bound_files, key=lambda item: item[0]):
        if (
            not label
            or Path(label).is_absolute()
            or any(part in {"", ".", ".."} for part in Path(label).parts)
        ):
            raise EvidenceError("bound repository file label is unsafe")
        path = Path(candidate)
        try:
            metadata = path.lstat()
        except (FileNotFoundError, OSError) as exc:
            raise EvidenceError(f"bound repository file is unavailable: {label}") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise EvidenceError(f"bound repository file is not regular: {label}")
        data = path.read_bytes()
        entries.append(
            {
                "scope": "repository",
                "path": label,
                "size_bytes": len(data),
                "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
            }
        )
    closure = "sha256:" + hashlib.sha256(canonical_json(entries).encode("utf-8")).hexdigest()
    return {
        "schema_version": "P4-REVIEW-MANIFEST-1",
        "entries": entries,
        "entry_count": len(entries),
        "payload_closure": closure,
    }


def snapshot_tree(roots: tuple[str | Path, ...], *, max_entries: int = 4096) -> dict[str, object]:
    """Fingerprint all reachable metadata while keeping serialized samples bounded."""

    if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries <= 0:
        raise EvidenceError("snapshot entry bound is invalid")
    entries: list[dict[str, object]] = []
    root_records: list[dict[str, object]] = []
    root_entries: dict[str, list[dict[str, object]]] = {}
    truncated = False
    scanned_entry_count = 0
    for raw_root in roots:
        root = Path(raw_root)
        root_label = _redact_string(str(root), workspace=None, home=Path.home().resolve())
        root_record: dict[str, object]
        try:
            root_metadata = root.lstat()
        except FileNotFoundError:
            root_record = {"root": root_label, "status": "MISSING"}
            root_records.append(root_record)
            root_entries[root_label] = []
            continue
        except OSError:
            root_record = {"root": root_label, "status": "UNAVAILABLE"}
            root_records.append(root_record)
            root_entries[root_label] = []
            continue
        if stat.S_ISLNK(root_metadata.st_mode):
            root_record = {"root": root_label, "status": "SYMLINK_REJECTED"}
            root_records.append(root_record)
            root_entries[root_label] = []
            continue
        if stat.S_ISREG(root_metadata.st_mode):
            root_record = {"root": root_label, "status": "OBSERVED_FILE"}
            root_records.append(root_record)
            root_entries[root_label] = [
                {
                    "root": root_label,
                    "relative": ".",
                    "mode": stat.S_IFMT(root_metadata.st_mode),
                    "size_bytes": root_metadata.st_size,
                    "mtime_ns": root_metadata.st_mtime_ns,
                    "status": "FILE",
                }
            ]
            scanned_entry_count += 1
            file_record = root_entries[root_label][0]
            if len(entries) < max_entries:
                entries.append(file_record)
            else:
                truncated = True
            continue
        if not stat.S_ISDIR(root_metadata.st_mode):
            root_record = {"root": root_label, "status": "NOT_DIRECTORY"}
            root_records.append(root_record)
            root_entries[root_label] = []
            continue
        root_record = {"root": root_label, "status": "OBSERVED"}
        root_records.append(root_record)
        root_entries[root_label] = []
        pending = [root]
        while pending:
            current = pending.pop()
            try:
                children = sorted(os.scandir(current), key=lambda item: item.name, reverse=True)
            except OSError:
                record: dict[str, object] = {
                    "root": root_label,
                    "relative": str(current.relative_to(root)),
                    "status": "UNAVAILABLE",
                }
                root_entries[root_label].append(record)
                scanned_entry_count += 1
                if len(entries) < max_entries:
                    entries.append(record)
                else:
                    truncated = True
                continue
            for child in children:
                try:
                    metadata = child.stat(follow_symlinks=False)
                except OSError:
                    record = {
                        "root": root_label,
                        "relative": str(Path(child.name)),
                        "status": "UNAVAILABLE",
                    }
                    root_entries[root_label].append(record)
                    scanned_entry_count += 1
                    if len(entries) < max_entries:
                        entries.append(record)
                    else:
                        truncated = True
                    continue
                relative = str(Path(child.path).relative_to(root))
                record = {
                    "root": root_label,
                    "relative": relative,
                    "mode": stat.S_IFMT(metadata.st_mode),
                    "size_bytes": metadata.st_size,
                    "mtime_ns": metadata.st_mtime_ns,
                }
                if stat.S_ISLNK(metadata.st_mode):
                    record["status"] = "SYMLINK_NOT_FOLLOWED"
                elif stat.S_ISDIR(metadata.st_mode):
                    record["status"] = "DIRECTORY"
                    pending.append(Path(child.path))
                else:
                    record["status"] = "FILE"
                root_entries[root_label].append(record)
                scanned_entry_count += 1
                if len(entries) < max_entries:
                    entries.append(record)
                else:
                    truncated = True
    payload: dict[str, object] = {
        "schema_version": "P4-STATE-SNAPSHOT-1",
        "roots": root_records,
        "entries": sorted(entries, key=lambda item: (str(item["root"]), str(item["relative"]))),
        "entry_count": len(entries),
        "scanned_entry_count": scanned_entry_count,
        "truncated": truncated,
    }
    root_entry_digests: dict[str, str] = {}
    for root_label in sorted(root_entries):
        matching_root = next(item for item in root_records if item.get("root") == root_label)
        root_entry_list: list[dict[str, object]] = root_entries[root_label]
        root_entry_digests[root_label] = digest_payload(
            {
                "root": matching_root,
                "entries": root_entry_list,
            }
        )
    payload["root_entry_digests"] = root_entry_digests
    payload["metadata_digest"] = digest_payload(payload)
    return payload
