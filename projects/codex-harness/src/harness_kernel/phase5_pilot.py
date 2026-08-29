"""Project-local input and evidence helpers for the Phase 5 pilot."""

from __future__ import annotations

import json
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from .phase4_evidence import EvidenceError, EvidenceWriter
from .phase5_models import (
    AcceptanceCriteria,
    Phase5Task,
    VisualBrief,
    public_data,
)


class Phase5PilotInputError(ValueError):
    """Raised when a Phase 5 task or evidence input is unsafe."""


_TASK_FIELDS = {
    "schema_version",
    "task_id",
    "run_id",
    "title",
    "request",
    "workspace",
    "artifact_root",
    "brief",
    "criteria",
    "created_at",
}
_BRIEF_FIELDS = {
    "outcome",
    "audience",
    "job",
    "thesis",
    "medium",
    "primary_action",
    "exact_copy",
    "must_include",
    "must_avoid",
    "responsive_intent",
    "accessibility_intent",
    "asset_role",
}
_CRITERIA_FIELDS = {
    "required_sections",
    "required_copy",
    "render_viewports",
    "dimensions",
    "forbidden_signals",
    "max_artifact_bytes",
}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise Phase5PilotInputError(f"{label} must be an object")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise Phase5PilotInputError(f"{label} must be a non-empty string")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise Phase5PilotInputError(f"{label} must be a list")
    result: list[str] = []
    for item in value:
        item_value = _string(item, label)
        if item_value not in result:
            result.append(item_value)
    return tuple(result)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise Phase5PilotInputError(f"{label} must be a non-negative integer")
    return value


def _safe_components(path: Path) -> None:
    if not path.is_absolute():
        raise Phase5PilotInputError("path must be absolute")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise Phase5PilotInputError("path cannot be inspected") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise Phase5PilotInputError("symlink path components are not accepted")


def resolve_task_path(raw: object, *, base: Path, label: str) -> Path:
    value = _string(raw, label)
    candidate = Path(value)
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise Phase5PilotInputError(f"{label} contains an unsafe path component")
    resolved = candidate if candidate.is_absolute() else base / candidate
    try:
        result = resolved.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise Phase5PilotInputError(f"{label} cannot be resolved") from exc
    _safe_components(result)
    return result


def _read_json(path: Path, *, max_bytes: int = 512 * 1024) -> Mapping[str, object]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise Phase5PilotInputError("JSON input must be a regular file")
        if metadata.st_size > max_bytes:
            raise Phase5PilotInputError("JSON input exceeds its bound")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Phase5PilotInputError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Phase5PilotInputError("JSON input cannot be read safely") from exc
    return _mapping(payload, "JSON input")


def _validate_fields(payload: Mapping[str, object], allowed: set[str], label: str) -> None:
    if set(payload).difference(allowed):
        raise Phase5PilotInputError(f"{label} contains unsupported fields")


def _viewports(value: object) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise Phase5PilotInputError("criteria.render_viewports must be a non-empty list")
    result: list[tuple[int, int]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise Phase5PilotInputError("each render viewport must contain width and height")
        width = _integer(item[0], "viewport width")
        height = _integer(item[1], "viewport height")
        if width < 1 or height < 1:
            raise Phase5PilotInputError("viewport dimensions must be positive")
        result.append((width, height))
    return tuple(result)


def load_task(path: str | Path, *, project_root: str | Path) -> Phase5Task:
    """Load a strict, path-bound task description from project-owned JSON."""

    candidate = Path(path)
    root = Path(project_root)
    if not candidate.is_absolute() or not root.is_absolute():
        raise Phase5PilotInputError("task path must be absolute")
    _safe_components(candidate)
    _safe_components(root)
    try:
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise Phase5PilotInputError("task/project root cannot be resolved") from exc
    if not resolved_root.is_dir():
        raise Phase5PilotInputError("project root must be a directory")
    if not resolved_candidate.is_relative_to(resolved_root):
        raise Phase5PilotInputError("task must remain inside project root")
    payload = _read_json(candidate)
    if payload.get("schema_version") != "P5-TASK-1":
        raise Phase5PilotInputError("unsupported Phase 5 task schema")
    _validate_fields(payload, _TASK_FIELDS, "task")
    brief_payload = _mapping(payload.get("brief"), "brief")
    criteria_payload = _mapping(payload.get("criteria"), "criteria")
    _validate_fields(brief_payload, _BRIEF_FIELDS, "brief")
    _validate_fields(criteria_payload, _CRITERIA_FIELDS, "criteria")
    exact_copy = _mapping(brief_payload.get("exact_copy"), "brief.exact_copy")
    exact_copy_strings: dict[str, str] = {}
    for key, value in exact_copy.items():
        exact_copy_strings[_string(key, "exact_copy key")] = _string(value, "exact_copy value")
    base = resolved_candidate.parent
    workspace = resolve_task_path(payload.get("workspace"), base=base, label="workspace")
    artifact_root = resolve_task_path(
        payload.get("artifact_root"), base=base, label="artifact_root"
    )
    if not workspace.is_dir():
        raise Phase5PilotInputError("task workspace must be an existing directory")
    if not workspace.is_relative_to(resolved_root):
        raise Phase5PilotInputError("task workspace must remain inside project root")
    if not artifact_root.is_relative_to(workspace):
        raise Phase5PilotInputError("artifact_root must remain inside workspace")
    return Phase5Task(
        task_id=_string(payload.get("task_id"), "task_id"),
        run_id=_string(payload.get("run_id"), "run_id"),
        title=_string(payload.get("title"), "title"),
        request=_string(payload.get("request"), "request"),
        workspace=str(workspace),
        artifact_root=str(artifact_root),
        brief=VisualBrief(
            outcome=_string(brief_payload.get("outcome"), "brief.outcome"),
            audience=_string(brief_payload.get("audience"), "brief.audience"),
            job=_string(brief_payload.get("job"), "brief.job"),
            thesis=_string(brief_payload.get("thesis"), "brief.thesis"),
            medium=_string(brief_payload.get("medium"), "brief.medium"),
            primary_action=_string(brief_payload.get("primary_action"), "brief.primary_action"),
            exact_copy=exact_copy_strings,
            must_include=_strings(brief_payload.get("must_include"), "brief.must_include"),
            must_avoid=_strings(brief_payload.get("must_avoid"), "brief.must_avoid"),
            responsive_intent=_string(
                brief_payload.get("responsive_intent"), "brief.responsive_intent"
            ),
            accessibility_intent=_string(
                brief_payload.get("accessibility_intent"), "brief.accessibility_intent"
            ),
            asset_role=_string(brief_payload.get("asset_role"), "brief.asset_role"),
        ),
        criteria=AcceptanceCriteria(
            required_sections=_strings(
                criteria_payload.get("required_sections"), "criteria.required_sections"
            ),
            required_copy=_strings(criteria_payload.get("required_copy"), "criteria.required_copy"),
            render_viewports=_viewports(criteria_payload.get("render_viewports")),
            dimensions=_strings(criteria_payload.get("dimensions"), "criteria.dimensions"),
            forbidden_signals=_strings(
                criteria_payload.get("forbidden_signals"), "criteria.forbidden_signals"
            ),
            max_artifact_bytes=_integer(
                criteria_payload.get("max_artifact_bytes"), "criteria.max_artifact_bytes"
            ),
        ),
        created_at=_integer(payload.get("created_at"), "created_at"),
    )


def read_json_mapping(path: str | Path) -> Mapping[str, object]:
    """Read a bounded object used for a critic or browser observation."""

    candidate = Path(path)
    if not candidate.is_absolute():
        raise Phase5PilotInputError("JSON input path must be absolute")
    _safe_components(candidate)
    return _read_json(candidate)


def write_public_json(writer: EvidenceWriter, relative: str, value: object) -> None:
    """Write a known, already-sanitized handoff without home-path redaction."""

    try:
        content = json.dumps(public_data(value), ensure_ascii=False, indent=2, sort_keys=True)
        writer.write_text(relative, content + "\n")
    except (EvidenceError, TypeError, ValueError) as exc:
        raise Phase5PilotInputError("evidence handoff cannot be serialized") from exc


def public_task(task: Phase5Task) -> dict[str, object]:
    value = public_data(task)
    if not isinstance(value, dict):
        raise Phase5PilotInputError("task serialization did not produce an object")
    value["schema_version"] = "P5-TASK-1"
    return cast(dict[str, object], value)
