"""Small inspectable project-local stores with atomic writes and recovery."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from .boundary import BoundaryCollisionError, BoundaryError, ProjectBoundary
from .errors import ContractError
from .models import (
    ArtifactRecord,
    ArtifactStatus,
    EvidenceRecord,
    InvocationStatus,
    RunSummary,
    TelemetryEvent,
)
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

    def __post_init__(self) -> None:
        if not isinstance(self.boundary, ProjectBoundary):
            raise BoundaryError("run store requires a ProjectBoundary")
        expected = {
            "run_directory": ".harness/state/runs",
            "evidence_directory": ".harness/evidence/runs",
            "telemetry_directory": ".harness/telemetry/runs",
            "lifecycle_directory": ".harness/state/lifecycle",
            "diagnostic_directory": ".harness/state/diagnostics",
        }
        for field, value in expected.items():
            if getattr(self, field) != value:
                raise BoundaryError(f"{field} must remain in the canonical harness store")

    def _run_path(self, run_id: str) -> str:
        if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
            raise BoundaryError("run identifier is invalid")
        return f"{self.run_directory}/{run_id}.json"

    def _write_once_json(
        self,
        relative: str,
        value: Mapping[str, object] | list[object],
        *,
        corrupt_message: str,
        collision_message: str,
    ) -> None:
        """Create immutable JSON state and resolve a concurrent first-writer race."""

        if self.boundary.resolve(relative, allow_missing=True).exists():
            try:
                existing = self.boundary.read_json(relative)
            except BoundaryError as exc:
                raise BoundaryError(corrupt_message) from exc
            if existing == value:
                return
            raise BoundaryError(collision_message)
        try:
            self.boundary.atomic_create_json(relative, value)
        except BoundaryCollisionError as exc:
            if not self.boundary.resolve(relative, allow_missing=True).exists():
                raise
            try:
                existing = self.boundary.read_json(relative)
            except BoundaryError as read_exc:
                raise BoundaryError(corrupt_message) from read_exc
            if existing == value:
                return
            raise BoundaryError(collision_message) from exc
        except BoundaryError:
            raise

    def _write_once_bytes(
        self,
        relative: str,
        value: bytes,
        *,
        corrupt_message: str,
        collision_message: str,
    ) -> None:
        """Create immutable byte state and preserve the first complete writer."""

        if self.boundary.resolve(relative, allow_missing=True).exists():
            try:
                existing = self.boundary.read_bytes(relative)
            except BoundaryError as exc:
                raise BoundaryError(corrupt_message) from exc
            if existing == value:
                return
            raise BoundaryError(collision_message)
        try:
            self.boundary.atomic_create_bytes(relative, value)
        except BoundaryCollisionError as exc:
            if not self.boundary.resolve(relative, allow_missing=True).exists():
                raise
            try:
                existing = self.boundary.read_bytes(relative)
            except BoundaryError as read_exc:
                raise BoundaryError(corrupt_message) from read_exc
            if existing == value:
                return
            raise BoundaryError(collision_message) from exc
        except BoundaryError:
            raise

    def write_record(self, run_id: str, record: Mapping[str, object]) -> None:
        if not isinstance(record, Mapping):
            raise BoundaryError("run record must be an object")
        if record.get("run_id") != run_id:
            raise BoundaryError("run record identity does not match its path")
        relative = self._run_path(run_id)
        self._write_once_json(
            relative,
            dict(record),
            corrupt_message="existing run record is corrupt",
            collision_message="run record collision cannot overwrite existing data",
        )

    def write_summary(self, summary: object) -> None:
        if not isinstance(summary, RunSummary):
            raise BoundaryError("summary must be a RunSummary")
        if not validate(summary).is_valid:
            raise BoundaryError("summary violates its contract")
        value = to_dict(summary)
        run_id = value.get("run_id")
        if not isinstance(run_id, str):
            raise BoundaryError("summary must contain a run_id")
        relative = self._run_path(run_id)
        if self.boundary.resolve(relative, allow_missing=True).exists():
            try:
                existing = self.boundary.read_json(relative)
                if not isinstance(existing, Mapping):
                    raise BoundaryError("existing run summary is not an object")
                existing_summary = from_dict(existing, RunSummary)
            except (BoundaryError, ContractError, TypeError, ValueError) as exc:
                raise BoundaryError("existing run summary is corrupt") from exc
            if existing_summary == summary:
                return
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
        self._write_once_json(
            relative,
            value,
            corrupt_message="existing evidence record is corrupt",
            collision_message="evidence record collision cannot overwrite existing data",
        )

    def write_artifact(self, artifact: ArtifactRecord, output: object) -> None:
        """Write an artifact body only in its owning run directory."""

        if not isinstance(artifact, ArtifactRecord):
            raise BoundaryError("artifact must be an ArtifactRecord")
        locator = artifact.content.locator
        if not isinstance(locator, str) or not locator.strip():
            raise BoundaryError("artifact content needs a project-local locator")
        if not _ID.fullmatch(artifact.artifact_id) or not _ID.fullmatch(artifact.run_id):
            raise BoundaryError("artifact identity is invalid")
        if artifact.producer.invocation_id is None:
            raise BoundaryError("persisted artifacts need an owning invocation")
        expected_locator = f"{self.run_directory}/{artifact.run_id}/{artifact.artifact_id}.json"
        if locator != expected_locator:
            raise BoundaryError("artifact locator must remain inside its owned run")
        encoded = to_json(output).encode("utf-8")
        if artifact.content.digest != digest_output(output):
            raise BoundaryError("artifact digest does not match its content")
        if artifact.content.size_bytes is not None and artifact.content.size_bytes != len(encoded):
            raise BoundaryError("artifact size does not match its content")
        self._write_once_bytes(
            locator,
            encoded,
            corrupt_message="existing artifact body is corrupt",
            collision_message="artifact collision cannot overwrite existing data",
        )

    def write_artifact_records(self, run_id: str, records: Sequence[Mapping[str, object]]) -> None:
        """Persist artifact metadata separately from its content body."""

        if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
            raise BoundaryError("run identifier is invalid")
        for record in records:
            if not isinstance(record, Mapping) or record.get("run_id") != run_id:
                raise BoundaryError("artifact record identity does not match its run")
        value = {"run_id": run_id, "records": [dict(record) for record in records]}
        relative = f"{self.evidence_directory}/{run_id}-artifacts.json"
        self._write_once_json(
            relative,
            value,
            corrupt_message="existing artifact metadata is corrupt",
            collision_message="artifact metadata collision cannot overwrite existing data",
        )

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

        def validate_append(existing: tuple[Mapping[str, object], ...]) -> bool:
            log = TelemetryLog()
            duplicate: Mapping[str, object] | None = None
            for parsed in existing:
                try:
                    parsed_event = from_dict(parsed, TelemetryEvent)
                    log = log.append(parsed_event)
                except (ContractError, TypeError, ValueError) as exc:
                    raise BoundaryError("existing JSONL log is corrupt") from exc
                if parsed_event.event_id == typed_event.event_id:
                    duplicate = to_dict(parsed_event)
            if duplicate is not None:
                if dict(duplicate) == normalized_event:
                    return True
                raise BoundaryError("telemetry event collision cannot overwrite existing data")
            if len(log.events) >= 1_024:
                raise BoundaryError("JSONL record limit exceeded")
            try:
                log.append(typed_event)
            except (TypeError, ValueError) as exc:
                raise BoundaryError("telemetry event cannot be appended to its chain") from exc
            return False

        self.boundary.append_jsonl(
            relative,
            normalized_event,
            max_records=1_024,
            append_validator=validate_append,
        )

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

        def validate_append(existing: tuple[Mapping[str, object], ...]) -> bool:
            for parsed in existing:
                if parsed.get("event_id") == event_id:
                    if dict(parsed) == dict(event):
                        return True
                    raise BoundaryError("lifecycle event collision cannot overwrite existing data")
            return False

        self.boundary.append_jsonl(
            relative,
            event,
            max_records=1_024,
            append_validator=validate_append,
        )

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

    def ensure_telemetry_log(self, run_id: str) -> None:
        if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
            raise BoundaryError("run identifier is invalid")
        relative = f"{self.telemetry_directory}/{run_id}.jsonl"
        if not self.boundary.resolve(relative, allow_missing=True).exists():
            self.boundary.atomic_write_bytes(relative, b"")

    def ensure_lifecycle_log(self, run_id: str) -> None:
        if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
            raise BoundaryError("run identifier is invalid")
        relative = f"{self.lifecycle_directory}/{run_id}.jsonl"
        if not self.boundary.resolve(relative, allow_missing=True).exists():
            self.boundary.atomic_write_bytes(relative, b"")

    def _verify_persisted_bundle(self, run_id: str, summary: RunSummary) -> None:
        """Verify every persisted dependency before reporting a terminal run."""

        relatives = (
            f"{self.evidence_directory}/{run_id}.json",
            f"{self.evidence_directory}/{run_id}-artifacts.json",
            f"{self.telemetry_directory}/{run_id}.jsonl",
            f"{self.lifecycle_directory}/{run_id}.jsonl",
        )
        if not all(self.boundary.resolve(item, allow_missing=True).exists() for item in relatives):
            raise BoundaryError("persisted run bundle is incomplete")

        artifact_value = self.boundary.read_json(relatives[1])
        if not isinstance(artifact_value, Mapping) or artifact_value.get("run_id") != run_id:
            raise BoundaryError("persisted artifact metadata identity is invalid")
        raw_artifacts = artifact_value.get("records")
        if not isinstance(raw_artifacts, list):
            raise BoundaryError("persisted artifact metadata is invalid")
        artifact_records: list[ArtifactRecord] = []
        for raw in raw_artifacts:
            if not isinstance(raw, Mapping):
                raise BoundaryError("persisted artifact record is invalid")
            try:
                artifact = from_dict(raw, ArtifactRecord)
            except (ContractError, TypeError, ValueError) as exc:
                raise BoundaryError("persisted artifact record violates its contract") from exc
            if not validate(artifact).is_valid:
                raise BoundaryError("persisted artifact record failed validation")
            if artifact.run_id != run_id:
                raise BoundaryError("persisted artifact identity does not match its run")
            expected_locator = f"{self.run_directory}/{run_id}/{artifact.artifact_id}.json"
            if artifact.content.locator != expected_locator:
                raise BoundaryError("persisted artifact locator is outside its owned run")
            body = self.boundary.read_bytes(artifact.content.locator)
            try:
                output = from_json(body, dict)
            except (ContractError, TypeError, ValueError) as exc:
                raise BoundaryError("persisted artifact body is invalid") from exc
            if digest_output(output) != artifact.content.digest:
                raise BoundaryError("persisted artifact body digest does not match metadata")
            if artifact.content.size_bytes != len(body):
                raise BoundaryError("persisted artifact body size does not match metadata")
            artifact_records.append(artifact)
        artifact_ids = tuple(item.artifact_id for item in artifact_records)
        artifact_by_id = {item.artifact_id: item for item in artifact_records}
        if len(set(artifact_ids)) != len(artifact_ids) or set(artifact_ids) != set(
            summary.artifacts
        ):
            raise BoundaryError("persisted artifact references do not match the run summary")
        if summary.lifecycle_state.value == "DELIVERED" and any(
            item.artifact_status is not ArtifactStatus.ACCEPTED for item in artifact_records
        ):
            raise BoundaryError("delivered run contains a non-accepted artifact")
        if (
            summary.lifecycle_state.value == "DELIVERED"
            and summary.delivery.artifact_ref not in set(artifact_ids)
        ):
            raise BoundaryError("delivered run is missing its persisted artifact")

        evidence_value = self.boundary.read_json(relatives[0])
        if not isinstance(evidence_value, Mapping) or evidence_value.get("run_id") != run_id:
            raise BoundaryError("persisted evidence identity is invalid")
        raw_evidence = evidence_value.get("records")
        if not isinstance(raw_evidence, list):
            raise BoundaryError("persisted evidence records are invalid")
        evidence_records: list[EvidenceRecord] = []
        for raw in raw_evidence:
            if not isinstance(raw, Mapping):
                raise BoundaryError("persisted evidence record is invalid")
            try:
                evidence = from_dict(raw, EvidenceRecord)
            except (ContractError, TypeError, ValueError) as exc:
                raise BoundaryError("persisted evidence record violates its contract") from exc
            if not validate(evidence).is_valid:
                raise BoundaryError("persisted evidence record failed validation")
            if evidence.run_id != run_id or any(
                artifact_id not in set(artifact_ids) for artifact_id in evidence.artifact_refs
            ):
                raise BoundaryError("persisted evidence references an unknown artifact")
            for artifact_id in evidence.artifact_refs:
                artifact = artifact_by_id[artifact_id]
                if evidence.provenance.content_digest != artifact.content.digest:
                    raise BoundaryError("persisted evidence digest does not match its artifact")
                if evidence.provenance.source_ref != artifact.provenance.tool_or_process:
                    raise BoundaryError("persisted evidence source does not match its artifact")
            evidence_records.append(evidence)
        evidence_ids = tuple(item.evidence_id for item in evidence_records)
        if len(set(evidence_ids)) != len(evidence_ids) or set(evidence_ids) != set(
            summary.evidence
        ):
            raise BoundaryError("persisted evidence references do not match the run summary")

        telemetry = TelemetryLog()
        raw_telemetry = self.boundary.read_bytes(relatives[2])
        for line in raw_telemetry.splitlines():
            if not line.strip():
                continue
            try:
                event = from_json(line, TelemetryEvent)
                telemetry = telemetry.append(event)
            except (ContractError, TypeError, ValueError) as exc:
                raise BoundaryError("persisted telemetry chain is corrupt") from exc
            if event.run_id != run_id or event.task_id != summary.task_id:
                raise BoundaryError("persisted telemetry correlation is invalid")
            if not set(event.artifact_refs).issubset(set(artifact_ids)) or not set(
                event.evidence_refs
            ).issubset(set(evidence_ids)):
                raise BoundaryError("persisted telemetry references are invalid")
        if not telemetry.verify_chain():
            raise BoundaryError("persisted telemetry chain is invalid")
        if not telemetry.events:
            raise BoundaryError("persisted telemetry chain is incomplete")

        lifecycle_ids: set[str] = set()
        raw_lifecycle = self.boundary.read_bytes(relatives[3])
        for line in raw_lifecycle.splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except (TypeError, ValueError) as exc:
                raise BoundaryError("persisted lifecycle log is corrupt") from exc
            if not isinstance(value, Mapping):
                raise BoundaryError("persisted lifecycle record is invalid")
            event_id = value.get("event_id")
            invocation_id = value.get("invocation_id")
            status = value.get("status")
            if (
                not isinstance(event_id, str)
                or not _ID.fullmatch(event_id)
                or event_id in lifecycle_ids
                or value.get("run_id") != run_id
                or value.get("task_id") != summary.task_id
                or not isinstance(invocation_id, str)
                or not _ID.fullmatch(invocation_id)
                or status not in {item.value for item in InvocationStatus}
            ):
                raise BoundaryError("persisted lifecycle correlation is invalid")
            lifecycle_ids.add(event_id)

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
            if not validate(summary).is_valid:
                return RecoveryResult(
                    run_id, RecoveryStatus.CORRUPT, "typed run summary failed validation"
                )
            if summary.run_id != run_id:
                return RecoveryResult(
                    run_id, RecoveryStatus.CORRUPT, "run summary identity mismatch"
                )
            try:
                self._verify_persisted_bundle(run_id, summary)
            except BoundaryError as exc:
                return RecoveryResult(run_id, RecoveryStatus.CORRUPT, str(exc))
            state = getattr(summary.lifecycle_state, "value", summary.lifecycle_state)
        else:
            state = record.get("lifecycle_state") or record.get("status")
            if (
                record.get("run_id") != run_id
                or not isinstance(state, str)
                or state not in _KNOWN_RUN_STATES
            ):
                return RecoveryResult(
                    run_id, RecoveryStatus.CORRUPT, "legacy run snapshot is invalid"
                )
        if state in _TERMINAL_RUN_STATES:
            return RecoveryResult(run_id, RecoveryStatus.FINISHED, "terminal run snapshot")
        return RecoveryResult(run_id, RecoveryStatus.UNFINISHED, "non-terminal run snapshot")
