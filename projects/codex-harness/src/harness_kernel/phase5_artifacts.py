"""Safe response-derived artifact capture for the Phase 5 visual pilot."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .phase5_models import ArtifactPacket, Phase5Task


class ArtifactCaptureError(ValueError):
    """Raised when an untrusted builder response cannot become an artifact."""


_FILENAME = "index.html"
_FORBIDDEN_HTML = re.compile(
    r"(?is)<\s*(?:script|iframe|object|embed|base)\b|javascript\s*:|\bon[a-z]+\s*=|"
    r"(?:https?|file|ftp)\s*://|(?<!:)//|@import\b|"
    r"url\s*\(\s*['\"]?(?:https?:|file:|ftp:|data:|//|/)|"
    r"\b(?:src|href)\s*=\s*['\"]\s*(?:https?:|file:|ftp:|//|data:|/)|"
    r"\bsrc\s*=\s*['\"]\s*/",
)


@dataclass(frozen=True, slots=True)
class ResponseArtifact:
    filename: str
    html: str
    response_digest: str

    def __post_init__(self) -> None:
        if self.filename != _FILENAME:
            raise ArtifactCaptureError("response artifact filename must be index.html")
        if not isinstance(self.html, str) or not self.html or "\x00" in self.html:
            raise ArtifactCaptureError("response artifact HTML is invalid")
        if not self.html.lstrip().lower().startswith(("<!doctype html", "<html")):
            raise ArtifactCaptureError("response artifact is not a complete HTML document")
        if _FORBIDDEN_HTML.search(self.html):
            raise ArtifactCaptureError(
                "response artifact contains a forbidden action or remote reference"
            )
        if not isinstance(self.response_digest, str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", self.response_digest
        ):
            raise ArtifactCaptureError("response digest is invalid")


def _safe_existing_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ArtifactCaptureError("artifact path cannot be inspected") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ArtifactCaptureError("artifact path cannot contain symlinks")


def validate_artifact_path(path: str | Path, workspace: str | Path) -> str:
    candidate = Path(path)
    root = Path(workspace)
    if not candidate.is_absolute() or not root.is_absolute():
        raise ArtifactCaptureError("artifact and workspace paths must be absolute")
    if any(part in {"", ".", ".."} for part in candidate.parts + root.parts):
        raise ArtifactCaptureError("artifact path contains traversal")
    _safe_existing_components(root)
    _safe_existing_components(candidate)
    try:
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ArtifactCaptureError("artifact path cannot be resolved") from exc
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ArtifactCaptureError("artifact path escapes the workspace") from exc
    return str(resolved_candidate)


def extract_response_artifact(response: str, *, max_bytes: int = 131_072) -> ResponseArtifact:
    if not isinstance(response, str) or not response or "\x00" in response:
        raise ArtifactCaptureError("builder response is invalid")
    encoded_response = response.encode("utf-8")
    if len(encoded_response) > max_bytes * 2:
        raise ArtifactCaptureError("builder response exceeds its bound")
    try:
        payload = json.loads(response)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactCaptureError("builder response must be one JSON object") from exc
    if not isinstance(payload, Mapping) or set(payload) != {"artifact_filename", "artifact_html"}:
        raise ArtifactCaptureError("builder response envelope is invalid")
    filename = payload.get("artifact_filename")
    html = payload.get("artifact_html")
    if filename != _FILENAME or not isinstance(html, str):
        raise ArtifactCaptureError("builder response does not contain index.html")
    if len(html.encode("utf-8")) > max_bytes:
        raise ArtifactCaptureError("HTML artifact exceeds its bound")
    response_digest = "sha256:" + hashlib.sha256(encoded_response).hexdigest()
    return ResponseArtifact(filename, html, response_digest)


def _ensure_directory(path: Path, workspace: Path) -> None:
    validate_artifact_path(path, workspace)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArtifactCaptureError("artifact directory cannot be created") from exc
    _safe_existing_components(path)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ArtifactCaptureError("artifact directory cannot be inspected") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ArtifactCaptureError("artifact root is not a directory")


def materialize_response_artifact(
    response_artifact: ResponseArtifact,
    task: Phase5Task,
    *,
    version: str,
    artifact_id: str,
    invocation_id: str,
    parent_artifact_digest: str | None = None,
) -> ArtifactPacket:
    if not isinstance(response_artifact, ResponseArtifact):
        raise ArtifactCaptureError("response artifact record is invalid")
    version_root = Path(task.artifact_root) / version
    target = version_root / response_artifact.filename
    _ensure_directory(version_root, Path(task.workspace))
    target_name = validate_artifact_path(target, task.workspace)
    packet = ArtifactPacket.from_content(
        artifact_id=artifact_id,
        version=version,
        path=target_name,
        content=response_artifact.html,
        producer_capability="design-director",
        invocation_id=invocation_id,
        task=task,
        parent_artifact_digest=parent_artifact_digest,
    )
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(version_root),
            prefix=".index.html.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(response_artifact.html)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target_name)
        temporary_name = None
    except OSError as exc:
        raise ArtifactCaptureError("artifact could not be materialized atomically") from exc
    finally:
        if temporary_name is not None:
            with suppress(OSError):
                Path(temporary_name).unlink(missing_ok=True)
    return packet


def artifact_is_stale(artifact: ArtifactPacket, observed_digest: str) -> bool:
    if not isinstance(observed_digest, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", observed_digest
    ):
        raise ArtifactCaptureError("observed artifact digest is invalid")
    return artifact.digest != observed_digest


def artifact_public_data(artifact: ArtifactPacket) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "artifact_id": artifact.artifact_id,
            "version": artifact.version,
            "path": artifact.path,
            "digest": artifact.digest,
            "size_bytes": artifact.size_bytes,
            "producer_capability": artifact.producer_capability,
            "invocation_id": artifact.invocation_id,
            "task_id": artifact.task_id,
            "acceptance_digest": artifact.acceptance_digest,
            "source_kind": artifact.source_kind,
            "parent_artifact_digest": artifact.parent_artifact_digest,
        }
    )
