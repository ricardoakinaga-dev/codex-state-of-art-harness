"""Small inspectable project-local stores with atomic writes and recovery."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from .boundary import BoundaryError, ProjectBoundary
from .errors import ContractError
from .models import ArtifactRecord, RunSummary, TelemetryEvent
from .providers import digest_output
from .serialization import from_dict, from_json, to_dict, to_json
from .telemetry import TelemetryLog
from .validation import validate

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")
_TERMINAL_RUN_STATES = frozenset(
    {
        "DELIVERED",
        "SUCCEEDED",
        "FAILED",
        "DRY_RUN",
        "STOPPED",
        "BLOCKED",
        "CANCELLED",
        "TIMED_OUT",
        "PARTIAL",
    }
)
_KNOWN_RUN_STATES = _TERMINAL_RUN_STATES | frozenset(
    {
        "NEW",
        "CLASSIFIED",
        "ROUTED",
        "PLANNED",
        "EXECUTING",
        "RUNNING",
        "VERIFYING",
        "REVIEWING",
        "REPAIRING",
        "ASSURING",
        "PASSED",
    }
)


class RecoveryStatus(StrEnum):
    FINISHED = "FINISHED"
    UNFINISHED = "UNFINISHED"
    CORRUPT = "CORRUPT"
    MISSING = "MISSING"


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    run_id: str
    status: RecoveryStatus
    reason: str


@dataclass(frozen=True, slots=True)
class RunStore:
    """Persist run snapshots, owned artifacts, lifecycle and telemetry locally."""

    boundary: ProjectBoundary
    run_directory: str = ".harness/state/runs"
    evidence_directory: str = ".harness/evidence/runs"
    telemetry_directory: str = ".harness/telemetry/runs"
    lifecycle_directory: str = ".harness/state/lifecycle"
    diagnostic_directory: str = ".harness/state/diagnostics"

    def _run_path(self, run_id: str) -> str:
        if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
            raise BoundaryError("run identifier is invalid")
        return f"{self.run_directory}/{run_id}.json"

    def write_record(self, run_id: str, record: Mapping[str, object]) -> None:
        if not isinstance(record, Mapping):
            raise BoundaryError("run record must be an object")
        if record.get("run_id") != run_id:
            raise BoundaryError("run record identity does not match its path")
        relative = self._run_path(run_id)
        if self.boundary.resolve(relative, allow_missing=True).exists():
            try:
                existing = self.boundary.read_json(relative)
            except BoundaryError as exc:
                raise BoundaryError("existing run record is corrupt") from exc
            if existing != dict(record):
                raise BoundaryError("run record collision cannot overwrite existing data")
            return
        self.boundary.atomic_write_json(relative, dict(record))

    def write_summary(self, summary: object) -> None:
        if not isinstance(summary, RunSummary):
            raise BoundaryError("summary must be a RunSummary")
        if not validate(summary).is_valid:
            raise BoundaryError("summary violates its contract")
        value = to_dict(summary)
        run_id = value.get("run_id")
        if not isinstance(run_id, str):
            raise BoundaryError("summary must contain a run_id")
        self.write_record(run_id, value)

    def load_record(self, run_id: str) -> dict[str, object]:
        value = self.boundary.read_json(self._run_path(run_id))
        if not isinstance(value, Mapping):
            raise BoundaryError("run record is not an object")
        if value.get("run_id") != run_id:
            raise BoundaryError("run record identity does not match its path")
        return dict(value)

    def write_evidence(self, run_id: str, records: Sequence[Mapping[str, object]]) -> None:
        if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
            raise BoundaryError("run identifier is invalid")
        for record in records:
            if not isinstance(record, Mapping) or record.get("run_id") != run_id:
                raise BoundaryError("evidence record identity does not match its run")
        value = {"run_id": run_id, "records": [dict(record) for record in records]}
        relative = f"{self.evidence_directory}/{run_id}.json"
        if self.boundary.resolve(relative, allow_missing=True).exists():
            try:
                existing = self.boundary.read_json(relative)
            except BoundaryError as exc:
                raise BoundaryError("existing evidence record is corrupt") from exc
            if existing != value:
                raise BoundaryError("evidence record collision cannot overwrite existing data")
            return
        self.boundary.atomic_write_json(relative, value)

    def write_artifact(self, artifact: ArtifactRecord, output: object) -> None:
        """Write an artifact body only at its declared project-local locator."""

        if not isinstance(artifact, ArtifactRecord):
            raise BoundaryError("artifact must be an ArtifactRecord")
        locator = artifact.content.locator
        if not isinstance(locator, str) or not locator.strip():
            raise BoundaryError("artifact content needs a project-local locator")
        encoded = to_json(output).encode("utf-8")
        if artifact.content.digest != digest_output(output):
            raise BoundaryError("artifact digest does not match its content")
        if artifact.content.size_bytes is not None and artifact.content.size_bytes != len(encoded):
            raise BoundaryError("artifact size does not match its content")
        target = self.boundary.resolve(locator, allow_missing=True)
        if target.exists():
            try:
                existing = self.boundary.read_bytes(locator)
            except BoundaryError as exc:
                raise BoundaryError("existing artifact body is corrupt") from exc
            if existing != encoded:
                raise BoundaryError("artifact collision cannot overwrite existing data")
            return
        self.boundary.atomic_write_bytes(locator, encoded)

    def write_artifact_records(self, run_id: str, records: Sequence[Mapping[str, object]]) -> None:
        """Persist artifact metadata separately from its content body."""

        if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
            raise BoundaryError("run identifier is invalid")
        for record in records:
            if not isinstance(record, Mapping) or record.get("run_id") != run_id:
                raise BoundaryError("artifact record identity does not match its run")
        value = {"run_id": run_id, "records": [dict(record) for record in records]}
        relative = f"{self.evidence_directory}/{run_id}-artifacts.json"
        if self.boundary.resolve(relative, allow_missing=True).exists():
            try:
                existing = self.boundary.read_json(relative)
            except BoundaryError as exc:
                raise BoundaryError("existing artifact metadata is corrupt") from exc
            if existing != value:
                raise BoundaryError("artifact metadata collision cannot overwrite existing data")
            return
        self.boundary.atomic_write_json(relative, value)

    def append_telemetry(self, run_id: str, event: Mapping[str, object]) -> None:
        if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
            raise BoundaryError("run identifier is invalid")
        if not isinstance(event, Mapping):
            raise BoundaryError("telemetry record must be an object")
        if event.get("run_id") != run_id:
            raise BoundaryError("telemetry identity does not match its run")
        try:
            typed_event = from_dict(event, TelemetryEvent)
        except (ContractError, TypeError, ValueError) as exc:
            raise BoundaryError("telemetry record violates its contract") from exc
        normalized_event = to_dict(typed_event)
        relative = f"{self.telemetry_directory}/{run_id}.jsonl"
        log = TelemetryLog()
        duplicate: Mapping[str, object] | None = None
        if self.boundary.resolve(relative, allow_missing=True).exists():
            raw = self.boundary.read_bytes(relative)
            for line in raw.splitlines():
                if not line.strip():
                    continue
                try:
                    parsed_event = from_json(line, TelemetryEvent)
                    log = log.append(parsed_event)
                except (ContractError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise BoundaryError("existing JSONL log is corrupt") from exc
                parsed = to_dict(parsed_event)
                if parsed_event.event_id == typed_event.event_id:
                    duplicate = parsed
        if duplicate is not None:
            if dict(duplicate) == normalized_event:
                return
            raise BoundaryError("telemetry event collision cannot overwrite existing data")
        if len(log.events) >= 1_024:
            raise BoundaryError("JSONL record limit exceeded")
        try:
            log.append(typed_event)
        except (TypeError, ValueError) as exc:
            raise BoundaryError("telemetry event cannot be appended to its chain") from exc
        self.boundary.append_jsonl(relative, normalized_event, max_records=1_024)

    def append_lifecycle(self, run_id: str, event: Mapping[str, object]) -> None:
        """Append a bounded, idempotent invocation lifecycle record."""

        if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
            raise BoundaryError("run identifier is invalid")
        if not isinstance(event, Mapping) or event.get("run_id") != run_id:
            raise BoundaryError("lifecycle identity does not match its run")
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not _ID.fullmatch(event_id):
            raise BoundaryError("lifecycle event identifier is invalid")
        relative = f"{self.lifecycle_directory}/{run_id}.jsonl"
        if self.boundary.resolve(relative, allow_missing=True).exists():
            raw = self.boundary.read_bytes(relative)
            for line in raw.splitlines():
                if not line.strip():
                    continue
                try:
                    parsed = json.loads(line)
                except (ValueError, TypeError) as exc:
                    raise BoundaryError("existing lifecycle log is corrupt") from exc
                if not isinstance(parsed, Mapping):
                    raise BoundaryError("existing lifecycle record is not an object")
                if parsed.get("event_id") == event_id:
                    if dict(parsed) == dict(event):
                        return
                    raise BoundaryError("lifecycle event collision cannot overwrite existing data")
        self.boundary.append_jsonl(relative, event, max_records=1_024)

    def write_diagnostic(self, run_id: str, channel: str, code: str) -> None:
        """Record a bounded persistence-channel failure without exposing details."""

        if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
            raise BoundaryError("run identifier is invalid")
        if not isinstance(channel, str) or not _ID.fullmatch(channel):
            raise BoundaryError("diagnostic channel is invalid")
        if not isinstance(code, str) or not _ID.fullmatch(code):
            raise BoundaryError("diagnostic code is invalid")
        relative = f"{self.diagnostic_directory}/{run_id}-{channel}.json"
        self.boundary.atomic_write_json(
            relative,
            {"run_id": run_id, "channel": channel, "code": code},
        )

    def recover(self, run_id: str) -> RecoveryResult:
        try:
            record = self.load_record(run_id)
        except BoundaryError as exc:
            path = self.boundary.resolve(self._run_path(run_id), allow_missing=True)
            status = RecoveryStatus.CORRUPT if path.exists() else RecoveryStatus.MISSING
            return RecoveryResult(run_id, status, str(exc))
        if record.get("schema_version") is not None:
            try:
                summary = from_dict(record, RunSummary)
            except (ContractError, TypeError, ValueError):
                return RecoveryResult(
                    run_id, RecoveryStatus.CORRUPT, "typed run summary is invalid"
                )
            if summary.run_id != run_id:
                return RecoveryResult(
                    run_id, RecoveryStatus.CORRUPT, "run summary identity mismatch"
                )
            state = getattr(summary.lifecycle_state, "value", summary.lifecycle_state)
        else:
            state = record.get("lifecycle_state") or record.get("status")
            if record.get("run_id") != run_id or state not in _KNOWN_RUN_STATES:
                return RecoveryResult(
                    run_id, RecoveryStatus.CORRUPT, "legacy run snapshot is invalid"
                )
        if state in _TERMINAL_RUN_STATES:
            return RecoveryResult(run_id, RecoveryStatus.FINISHED, "terminal run snapshot")
        return RecoveryResult(run_id, RecoveryStatus.UNFINISHED, "non-terminal run snapshot")
