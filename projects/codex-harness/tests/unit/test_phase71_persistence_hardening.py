from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from typing import Any, cast

import pytest
from phase2_support import authorized_kernel
from test_contracts import all_records

from harness_kernel.boundary import BoundaryError, ProjectBoundary
from harness_kernel.execution import RunResult
from harness_kernel.models import (
    CapabilityDependencies,
    CapabilityManifest,
    CapabilityStatus,
    RecordStatus,
    TelemetryEvent,
    TelemetryEventType,
)
from harness_kernel.persistence import RecoveryStatus, RunStore
from harness_kernel.providers import (
    DeterministicSuccessProvider,
    ProviderRegistry,
    digest_output,
)
from harness_kernel.registry import (
    CapabilityRegistry,
    DiagnosticSeverity,
    InvalidManifestError,
    RegistryConflictError,
    RegistryDiagnostic,
    RegistryError,
    SemVer,
    SemVerError,
    compare_semver,
    parse_semver,
    parse_version_range,
    satisfies,
)
from harness_kernel.serialization import to_dict, to_json
from harness_kernel.telemetry import TelemetryLog, create_event

NOW = "2026-08-30T15:00:00Z"


def _manifest(
    capability_id: str,
    version: str = "1.0.0",
    *,
    dependencies: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
    status: CapabilityStatus = CapabilityStatus.CANDIDATE,
    record_status: RecordStatus = RecordStatus.CURRENT,
) -> CapabilityManifest:
    base = next(item for item in all_records() if isinstance(item, CapabilityManifest))
    return replace(
        base,
        capability_id=capability_id,
        version=version,
        status=status,
        record=replace(base.record, status=record_status),
        dependencies=replace(base.dependencies, capabilities=dependencies),
        composition=replace(base.composition, conflicts_with=conflicts),
    )


def _store(tmp_path: Path) -> tuple[ProjectBoundary, RunStore]:
    boundary = ProjectBoundary(tmp_path)
    return boundary, RunStore(boundary)


def _persisted_run(tmp_path: Path, run_id: str = "RUN-P7.1-PERSIST") -> RunResult:
    return authorized_kernel(
        tmp_path,
        providers=ProviderRegistry().register(DeterministicSuccessProvider()),
    ).run(
        "Change one local label and preserve the result",
        task_id=f"TASK-{run_id}",
        run_id=run_id,
        provider_id="local.success",
        persist=True,
    )


def _event(
    event_id: str,
    run_id: str,
    *,
    sequence: int = 1,
    previous_digest: str | None = None,
    reason: str | None = None,
) -> TelemetryEvent:
    return create_event(
        event_id=event_id,
        event_sequence=sequence,
        timestamp=NOW,
        task_id=f"TASK-{run_id}",
        run_id=run_id,
        event_type=TelemetryEventType.TASK_RECEIVED,
        previous_event_digest=previous_digest,
        reason=reason,
    )


def test_run_store_rejects_noncanonical_storage_and_invalid_record_identity(tmp_path: Path) -> None:
    boundary = ProjectBoundary(tmp_path)

    with pytest.raises(BoundaryError, match="canonical harness store"):
        RunStore(boundary, run_directory=".harness/other-runs")
    with pytest.raises(BoundaryError, match="run store requires"):
        RunStore(cast(Any, object()))

    store = RunStore(boundary)
    with pytest.raises(BoundaryError, match="must be an object"):
        store.write_record("RUN-IDENTITY", cast(Any, []))
    with pytest.raises(BoundaryError, match="identity"):
        store.write_record("RUN-IDENTITY", {"run_id": "OTHER"})
    assert not (tmp_path / ".harness/state/runs/RUN-IDENTITY.json").exists()


def test_run_record_collision_is_idempotent_and_preserves_persistent_state(tmp_path: Path) -> None:
    boundary, store = _store(tmp_path)
    run_id = "RUN-ATOMIC-RECORD"
    record = {"run_id": run_id, "status": "RUNNING", "attempt": 1}

    store.write_record(run_id, record)
    original = boundary.read_bytes(f".harness/state/runs/{run_id}.json")
    store.write_record(run_id, dict(record))

    with pytest.raises(BoundaryError, match="collision"):
        store.write_record(run_id, {**record, "attempt": 2})

    assert boundary.read_bytes(f".harness/state/runs/{run_id}.json") == original
    assert store.load_record(run_id) == record


def test_concurrent_idempotent_record_writers_leave_one_valid_snapshot(tmp_path: Path) -> None:
    _, store = _store(tmp_path)
    run_id = "RUN-CONCURRENT-RECORD"
    record = {"run_id": run_id, "status": "RUNNING", "payload": {"version": 1}}
    (tmp_path / ".harness/state/runs").mkdir(parents=True)
    barrier = Barrier(8)

    def write_same_record(_: int) -> str:
        barrier.wait()
        store.write_record(run_id, record)
        return "written"

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(executor.map(write_same_record, range(8)))

    assert results == ("written",) * 8
    assert store.load_record(run_id) == record
    assert len(list((tmp_path / ".harness/state/runs").glob(f"{run_id}.json"))) == 1


def test_evidence_and_artifact_metadata_collisions_preserve_bytes(tmp_path: Path) -> None:
    runtime = _persisted_run(tmp_path, "RUN-METADATA-COLLISION")
    boundary = ProjectBoundary(tmp_path)
    store = RunStore(boundary)
    run_id = runtime.summary.run_id

    evidence_relative = f".harness/evidence/runs/{run_id}.json"
    artifact_relative = f".harness/evidence/runs/{run_id}-artifacts.json"
    evidence_bytes = boundary.read_bytes(evidence_relative)
    artifact_bytes = boundary.read_bytes(artifact_relative)
    evidence_records = [to_dict(item) for item in runtime.evidence]
    artifact_records = [to_dict(item) for item in runtime.artifacts]

    store.write_evidence(run_id, evidence_records)
    store.write_artifact_records(run_id, artifact_records)
    assert boundary.read_bytes(evidence_relative) == evidence_bytes
    assert boundary.read_bytes(artifact_relative) == artifact_bytes

    with pytest.raises(BoundaryError, match="evidence record collision"):
        store.write_evidence(
            run_id,
            [{**evidence_records[0], "observation": "forged observation"}],
        )
    with pytest.raises(BoundaryError, match="artifact metadata collision"):
        store.write_artifact_records(
            run_id,
            [{**artifact_records[0], "title": "forged artifact"}],
        )

    assert boundary.read_bytes(evidence_relative) == evidence_bytes
    assert boundary.read_bytes(artifact_relative) == artifact_bytes


def test_artifact_replay_is_idempotent_but_conflict_cannot_replace_body(tmp_path: Path) -> None:
    runtime = _persisted_run(tmp_path, "RUN-ARTIFACT-COLLISION")
    boundary = ProjectBoundary(tmp_path)
    store = RunStore(boundary)
    artifact = runtime.artifacts[0]
    assert artifact.content.locator is not None
    original = boundary.read_bytes(artifact.content.locator)
    output = runtime.provider_results[-1].output

    store.write_artifact(artifact, output)
    conflicting_output = {"different": True}
    conflicting_artifact = replace(
        artifact,
        content=replace(
            artifact.content,
            digest=digest_output(conflicting_output),
            size_bytes=len(to_json(conflicting_output).encode()),
        ),
    )
    with pytest.raises(BoundaryError, match="artifact collision"):
        store.write_artifact(conflicting_artifact, conflicting_output)

    assert boundary.read_bytes(artifact.content.locator) == original
    assert json.loads(original) == output


@pytest.mark.parametrize(
    ("mutator", "message"),
    (
        (
            lambda item: {**item, "content": {**item["content"], "digest": "sha256:" + "0" * 64}},
            "digest does not match",
        ),
        (
            lambda item: {
                **item,
                "content": {
                    **item["content"],
                    "size_bytes": item["content"]["size_bytes"] + 1,
                },
            },
            "size does not match",
        ),
    ),
)
def test_recovery_rejects_tampered_artifact_metadata_and_preserves_bundle(
    tmp_path: Path,
    mutator: Callable[[dict[str, Any]], dict[str, Any]],
    message: str,
) -> None:
    runtime = _persisted_run(tmp_path, "RUN-ARTIFACT-TAMPER")
    boundary = ProjectBoundary(tmp_path)
    metadata_relative = f".harness/evidence/runs/{runtime.summary.run_id}-artifacts.json"
    artifact_locator = runtime.artifacts[0].content.locator
    assert artifact_locator is not None
    original_body = boundary.read_bytes(artifact_locator)
    payload = boundary.read_json(metadata_relative)
    assert isinstance(payload, dict)
    records = payload["records"]
    assert isinstance(records, list) and isinstance(records[0], dict)
    boundary.atomic_write_json(metadata_relative, {**payload, "records": [mutator(records[0])]})

    recovery = RunStore(boundary).recover(runtime.summary.run_id)

    assert recovery.status is RecoveryStatus.CORRUPT
    assert message in recovery.reason
    assert boundary.read_bytes(artifact_locator) == original_body


@pytest.mark.parametrize(
    ("relative_suffix", "mutator", "message"),
    (
        (
            "-artifacts.json",
            lambda payload: {**payload, "run_id": "RUN-WRONG"},
            "artifact metadata identity is invalid",
        ),
        (
            "-artifacts.json",
            lambda payload: {**payload, "records": {}},
            "artifact metadata is invalid",
        ),
        (
            ".json",
            lambda payload: {**payload, "run_id": "RUN-WRONG"},
            "evidence identity is invalid",
        ),
        (
            ".json",
            lambda payload: {**payload, "records": {}},
            "evidence records are invalid",
        ),
    ),
)
def test_recovery_rejects_bundle_identity_and_shape_substitution(
    tmp_path: Path,
    relative_suffix: str,
    mutator: Callable[[dict[str, Any]], dict[str, Any]],
    message: str,
) -> None:
    runtime = _persisted_run(tmp_path, "RUN-BUNDLE-SHAPE")
    boundary = ProjectBoundary(tmp_path)
    relative = f".harness/evidence/runs/{runtime.summary.run_id}{relative_suffix}"
    payload = boundary.read_json(relative)
    assert isinstance(payload, dict)
    boundary.atomic_write_json(relative, mutator(payload))

    recovery = RunStore(boundary).recover(runtime.summary.run_id)

    assert recovery.status is RecoveryStatus.CORRUPT
    assert recovery.reason == f"persisted {message}"


@pytest.mark.parametrize(
    ("mutator", "message"),
    (
        (
            lambda payload: {
                **payload,
                "records": [{**payload["records"][0], "artifact_refs": ["ART-UNKNOWN"]}],
            },
            "unknown artifact",
        ),
        (
            lambda payload: {
                **payload,
                "records": [
                    {
                        **payload["records"][0],
                        "provenance": {
                            **payload["records"][0]["provenance"],
                            "content_digest": "sha256:" + "f" * 64,
                        },
                    }
                ],
            },
            "digest does not match its artifact",
        ),
        (
            lambda payload: {
                **payload,
                "records": [
                    {
                        **payload["records"][0],
                        "provenance": {
                            **payload["records"][0]["provenance"],
                            "source_ref": "forged.provider",
                        },
                    }
                ],
            },
            "source does not match its artifact",
        ),
    ),
)
def test_recovery_rejects_evidence_reference_and_provenance_tampering(
    tmp_path: Path,
    mutator: Callable[[dict[str, Any]], dict[str, Any]],
    message: str,
) -> None:
    runtime = _persisted_run(tmp_path, "RUN-EVIDENCE-TAMPER")
    boundary = ProjectBoundary(tmp_path)
    relative = f".harness/evidence/runs/{runtime.summary.run_id}.json"
    payload = boundary.read_json(relative)
    assert isinstance(payload, dict)
    boundary.atomic_write_json(relative, mutator(payload))

    recovery = RunStore(boundary).recover(runtime.summary.run_id)

    assert recovery.status is RecoveryStatus.CORRUPT
    assert message in recovery.reason


@pytest.mark.parametrize(
    ("kind", "replacement", "status", "message"),
    (
        ("telemetry", b"{}\n", RecoveryStatus.CORRUPT, "persisted telemetry chain is corrupt"),
        ("telemetry", b"\n", RecoveryStatus.CORRUPT, "persisted telemetry chain is incomplete"),
        ("lifecycle", b"[]\n", RecoveryStatus.CORRUPT, "persisted lifecycle record is invalid"),
        ("lifecycle", b"not-json\n", RecoveryStatus.CORRUPT, "persisted lifecycle log is corrupt"),
    ),
)
def test_recovery_handles_corrupt_or_blank_telemetry_and_lifecycle_without_deleting_files(
    tmp_path: Path,
    kind: str,
    replacement: bytes,
    status: RecoveryStatus,
    message: str,
) -> None:
    runtime = _persisted_run(tmp_path, "RUN-LOG-TAMPER")
    boundary = ProjectBoundary(tmp_path)
    relative = (
        f".harness/telemetry/runs/{runtime.summary.run_id}.jsonl"
        if kind == "telemetry"
        else f".harness/state/lifecycle/{runtime.summary.run_id}.jsonl"
    )
    boundary.atomic_write_bytes(relative, replacement)

    recovery = RunStore(boundary).recover(runtime.summary.run_id)

    assert recovery.status is status
    assert recovery.reason == message
    assert boundary.read_bytes(relative) == replacement


def test_recovery_classifies_legacy_terminal_unfinished_and_invalid_snapshots(
    tmp_path: Path,
) -> None:
    _, store = _store(tmp_path)

    store.write_record("RUN-LEGACY-OPEN", {"run_id": "RUN-LEGACY-OPEN", "status": "RUNNING"})
    store.write_record("RUN-LEGACY-DONE", {"run_id": "RUN-LEGACY-DONE", "status": "FAILED"})
    store.write_record("RUN-LEGACY-BAD", {"run_id": "RUN-LEGACY-BAD", "status": "UNKNOWN"})

    assert store.recover("RUN-LEGACY-OPEN").status is RecoveryStatus.UNFINISHED
    assert store.recover("RUN-LEGACY-DONE").status is RecoveryStatus.FINISHED
    bad = store.recover("RUN-LEGACY-BAD")
    assert bad.status is RecoveryStatus.CORRUPT
    assert bad.reason == "legacy run snapshot is invalid"
    assert store.recover("RUN-NOT-THERE").status is RecoveryStatus.MISSING


def test_run_store_append_lifecycle_is_idempotent_and_collision_safe(tmp_path: Path) -> None:
    boundary, store = _store(tmp_path)
    run_id = "RUN-LIFECYCLE-IDEM"
    event = {"run_id": run_id, "event_id": "EVENT-1", "status": "STARTED"}
    relative = f".harness/state/lifecycle/{run_id}.jsonl"

    store.append_lifecycle(run_id, event)
    original = boundary.read_bytes(relative)
    store.append_lifecycle(run_id, dict(event))
    with pytest.raises(BoundaryError, match="lifecycle event collision"):
        store.append_lifecycle(run_id, {**event, "status": "FINISHED"})

    assert boundary.read_bytes(relative) == original
    assert boundary.read_bytes(relative).splitlines() == [to_json(event).encode()]


def test_concurrent_duplicate_lifecycle_events_have_one_persisted_side_effect(
    tmp_path: Path,
) -> None:
    boundary, store = _store(tmp_path)
    run_id = "RUN-CONCURRENT-LIFECYCLE"
    event = {"run_id": run_id, "event_id": "EVENT-CONCURRENT", "status": "STARTED"}
    store.ensure_lifecycle_log(run_id)
    barrier = Barrier(6)

    def append_same_event(_: int) -> str:
        barrier.wait()
        store.append_lifecycle(run_id, event)
        return "appended"

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = tuple(executor.map(append_same_event, range(6)))

    relative = f".harness/state/lifecycle/{run_id}.jsonl"
    assert results == ("appended",) * 6
    assert boundary.read_bytes(relative).splitlines() == [to_json(event).encode()]


def test_telemetry_replay_conflict_and_record_limit_preserve_existing_chain(tmp_path: Path) -> None:
    boundary, store = _store(tmp_path)
    run_id = "RUN-TELEMETRY-IDEM"
    first = _event("EVENT-1", run_id)
    second = _event("EVENT-2", run_id, sequence=2, previous_digest=first.integrity.event_digest)
    store.append_telemetry(run_id, to_dict(first))
    store.append_telemetry(run_id, to_dict(second))
    relative = f".harness/telemetry/runs/{run_id}.jsonl"
    original = boundary.read_bytes(relative)

    store.append_telemetry(run_id, to_dict(first))
    with pytest.raises(BoundaryError, match="telemetry event collision"):
        store.append_telemetry(run_id, to_dict(replace(first, reason="different")))

    assert boundary.read_bytes(relative) == original

    events = TelemetryLog()
    for sequence in range(1, 1_025):
        event = _event(
            f"EVENT-LIMIT-{sequence}",
            "RUN-TELEMETRY-LIMIT",
            sequence=sequence,
            previous_digest=events.last_digest,
        )
        events = events.append(event)
    limit_relative = ".harness/telemetry/runs/RUN-TELEMETRY-LIMIT.jsonl"
    boundary.atomic_write_bytes(
        limit_relative,
        b"".join(to_json(item).encode() + b"\n" for item in events.events),
    )
    limit_before = boundary.read_bytes(limit_relative)
    overflow = _event(
        "EVENT-LIMIT-1025",
        "RUN-TELEMETRY-LIMIT",
        sequence=1025,
        previous_digest=events.last_digest,
    )

    with pytest.raises(BoundaryError, match="record limit"):
        store.append_telemetry("RUN-TELEMETRY-LIMIT", to_dict(overflow))
    assert boundary.read_bytes(limit_relative) == limit_before


def test_ensure_logs_are_idempotent_and_invalid_ids_never_escape_store(tmp_path: Path) -> None:
    boundary, store = _store(tmp_path)

    store.ensure_telemetry_log("RUN-EMPTY")
    store.ensure_telemetry_log("RUN-EMPTY")
    store.ensure_lifecycle_log("RUN-EMPTY")
    store.ensure_lifecycle_log("RUN-EMPTY")
    assert boundary.read_bytes(".harness/telemetry/runs/RUN-EMPTY.jsonl") == b""
    assert boundary.read_bytes(".harness/state/lifecycle/RUN-EMPTY.jsonl") == b""

    for operation in (store.ensure_telemetry_log, store.ensure_lifecycle_log):
        with pytest.raises(BoundaryError, match="run identifier"):
            operation("../escape")


@pytest.mark.parametrize(
    ("left", "right"),
    (
        ("1.0.0-alpha", "1.0.0"),
        ("1.0.0-alpha.1", "1.0.0-alpha.beta"),
        ("1.0.0-alpha.1", "1.0.0-alpha.2"),
        ("1.0.0-alpha", "1.0.0-alpha.1"),
    ),
)
def test_semver_prerelease_ordering_is_deterministic(left: str, right: str) -> None:
    assert parse_semver(left) < parse_semver(right)
    assert compare_semver(left, right) == -1
    assert str(parse_semver("1.2.3-alpha.1+build.7")) == "1.2.3-alpha.1+build.7"
    assert parse_semver("1.2.3+one") == parse_semver("1.2.3+two")

    assert parse_semver("1.0.0-alpha").__lt__(object()) is NotImplemented


@pytest.mark.parametrize(
    ("value", "message"),
    (
        (-1, "components cannot be negative"),
        (True, "components must be integers"),
    ),
)
def test_semver_rejects_invalid_numeric_components(value: int, message: str) -> None:
    with pytest.raises(SemVerError, match=message):
        SemVer(value, 0, 0)


@pytest.mark.parametrize(
    "value",
    (
        "1.0.0-01",
        "1.0.0-a..b",
        "1.0.0+bad..build",
    ),
)
def test_semver_parser_rejects_invalid_or_incomplete_versions(value: str) -> None:
    with pytest.raises(SemVerError):
        SemVer.parse(value)
    with pytest.raises(SemVerError):
        parse_version_range(value)


def test_semver_ranges_cover_wildcard_caret_tilde_hyphen_and_comparators() -> None:
    assertions = (
        ("1.2.3", "1.2", True),
        ("1.3.0", "1.2", False),
        ("1.2.3", "1.2.x", True),
        ("2.0.0", "^1.2.0", False),
        ("0.2.5", "^0.2.0", True),
        ("0.3.0", "^0.2.0", False),
        ("0.0.5", "^0.0.5", True),
        ("0.0.6", "^0.0.5", False),
        ("1.2.9", "~1.2", True),
        ("1.3.0", "~1.2", False),
        ("1.5.0", "~1", True),
        ("2.0.0", "~1", False),
        ("1.5.0", "1.0.0 - 2.0.0", True),
        ("1.0.0", ">1.0.0", False),
        ("1.2.3", ">=1.2.3", True),
        ("1.2.3", "<=1.2.x", True),
        ("1.2.3", "<1.2.x", False),
        ("1.2.3", "1.x", True),
        ("2.0.0", "1.x", False),
        ("1.2.3", "latest", True),
    )
    for version, version_range, expected in assertions:
        assert satisfies(version, version_range) is expected, (version, version_range)

    semver = parse_semver("1.2.3")
    parsed = parse_version_range(semver)
    assert parsed.matches(semver)
    existing = parse_version_range(">=1.0.0")
    assert parse_version_range(existing) is existing


@pytest.mark.parametrize(
    ("value", "exception"),
    (
        ("1.2.3.4", SemVerError),
        ("1.02", SemVerError),
        (">", SemVerError),
        ("dep", RegistryError),
    ),
)
def test_registry_range_and_dependency_boundaries_fail_closed(
    value: str, exception: type[Exception]
) -> None:
    if value == "dep":
        registry = CapabilityRegistry().register(_manifest("root", dependencies=(" ",)))
        result = registry.resolve_dependencies("root")
        assert not result.ok
        assert any(item.code == "INVALID_DEPENDENCY_SPEC" for item in result.diagnostics)
    else:
        with pytest.raises(exception):
            parse_version_range(value)


@pytest.mark.parametrize(
    ("field", "value", "diagnostic"),
    (
        ("capability_id", "", "INVALID_CAPABILITY_ID"),
        ("version", "not-semver", "INVALID_VERSION"),
    ),
)
def test_registry_admission_rejects_identity_and_version_forgery(
    field: str, value: str, diagnostic: str
) -> None:
    candidate = _manifest("admission-failure")
    if field == "capability_id":
        candidate = replace(candidate, capability_id=value)
    else:
        candidate = replace(candidate, version=value)

    with pytest.raises(InvalidManifestError) as error:
        CapabilityRegistry().register(candidate)

    assert any(item.code == diagnostic for item in error.value.diagnostics)
    assert all(item.severity is DiagnosticSeverity.ERROR for item in error.value.diagnostics)


@pytest.mark.parametrize(
    ("provenance_field", "value", "diagnostic"),
    (
        ("origin", "UNKNOWN", "INVALID_REGISTRY_ORIGIN"),
        ("precedence", True, "INVALID_ORIGIN_PRECEDENCE"),
        ("source_repository", "", "MISSING_SOURCE_REPOSITORY"),
        ("source_hash", "invalid", "INVALID_SOURCE_HASH"),
        ("installation_scope", "UNKNOWN", "INVALID_INSTALLATION_SCOPE"),
        ("forked_from", "", "INVALID_FORK_REFERENCE"),
    ),
)
def test_registry_admission_rejects_invalid_provenance_without_side_effects(
    provenance_field: str, value: object, diagnostic: str
) -> None:
    candidate = _manifest("provenance-failure")
    provenance = cast(Any, candidate.provenance)
    candidate = replace(candidate, provenance=replace(provenance, **{provenance_field: value}))

    with pytest.raises(InvalidManifestError) as error:
        CapabilityRegistry().register(candidate)

    assert any(item.code == diagnostic for item in error.value.diagnostics)
    assert CapabilityRegistry().list() == ()


def test_registry_inspection_reports_nonfatal_provenance_and_status_diagnostics() -> None:
    missing_record_provenance = _manifest("missing-record-provenance")
    missing_record_provenance = replace(
        missing_record_provenance,
        record=replace(
            missing_record_provenance.record,
            provenance=replace(
                missing_record_provenance.record.provenance,
                source_refs=(),
            ),
        ),
    )
    verified = replace(
        _manifest("verified-without-eval", status=CapabilityStatus.VERIFIED),
        quality=replace(_manifest("verified-without-eval").quality, eval_refs=()),
    )
    active = replace(
        _manifest("active-without-gates", status=CapabilityStatus.ACTIVE),
        contracts=replace(
            _manifest("active-without-gates").contracts,
            gates=(),
            stop_conditions=(),
        ),
    )
    registry = CapabilityRegistry.from_manifests((missing_record_provenance, active))

    for capability_id, expected in (
        ("missing-record-provenance", {"MISSING_RECORD_PROVENANCE"}),
        ("active-without-gates", {"ACTIVE_MISSING_GATES"}),
    ):
        inspection = registry.inspect(capability_id)
        assert expected <= {item.code for item in inspection.diagnostics}
        assert inspection.provenance_ok is True

    with pytest.raises(InvalidManifestError) as error:
        CapabilityRegistry().register(verified)
    assert {"INVALID_MANIFEST", "UNVERIFIED_PROVENANCE"} <= {
        item.code for item in error.value.diagnostics
    }


def test_registry_replacement_and_status_filters_are_immutable() -> None:
    original_manifest = _manifest("replaceable", "1.0.0")
    replacement = _manifest("replaceable", "1.0.0", status=CapabilityStatus.ACTIVE)
    original = CapabilityRegistry().register(original_manifest)
    updated = original.register(replacement, replace=True)

    original_found = original.find("replaceable")
    updated_found = updated.find("replaceable")
    assert original_found is not None and original_found.status is CapabilityStatus.CANDIDATE
    assert updated_found is not None and updated_found.status is CapabilityStatus.ACTIVE
    assert original.list() == (original_manifest,)
    assert updated.list(status=CapabilityStatus.ACTIVE) == (replacement,)

    stale = _manifest("stale-filter", record_status=RecordStatus.STALE)
    deprecated = _manifest("deprecated-filter", status=CapabilityStatus.DEPRECATED)
    rejected = _manifest("rejected-filter", status=CapabilityStatus.REJECTED)
    filtered = CapabilityRegistry.from_manifests((stale, deprecated, rejected))
    assert (
        filtered.list(include_stale=False, include_deprecated=False, include_rejected=False) == ()
    )
    assert filtered.find("stale-filter") is None
    assert filtered.find("stale-filter", include_stale=True) == stale
    assert filtered.find("deprecated-filter", include_deprecated=True) == deprecated
    assert filtered.find("rejected-filter", include_rejected=True) == rejected


def test_registry_missing_lookup_and_declared_conflicts_are_diagnostic_only() -> None:
    registry = CapabilityRegistry().register(_manifest("alpha", conflicts=("beta@^1.0.0",)))
    missing = registry.inspect("not-present")
    assert missing.manifest is None
    assert missing.valid is False
    assert missing.usable is False
    assert registry.diagnose("not-present")[0].code == "MISSING_MANIFEST"
    assert registry.diagnose("alpha") == registry.diagnose("alpha")
    assert not any(item.code == "CAPABILITY_CONFLICT" for item in registry.diagnose("alpha"))

    with pytest.raises(RegistryConflictError):
        registry.register(_manifest("alpha"))
    with pytest.raises(TypeError):
        registry.register(cast(Any, object()))
    with pytest.raises(TypeError):
        CapabilityRegistry(manifests=(cast(Any, object()),))

    diagnostic = RegistryDiagnostic("NOTE", "normalized", severity="warning")
    assert diagnostic.severity is DiagnosticSeverity.WARNING


def test_dependency_resolution_classifies_stale_deprecated_unsatisfied_and_missing() -> None:
    stale = _manifest("stale-child", record_status=RecordStatus.STALE)
    deprecated = _manifest("deprecated-child", status=CapabilityStatus.DEPRECATED)
    unsatisfied = replace(
        _manifest("unsatisfied-child"),
        provenance=replace(_manifest("unsatisfied-child").provenance, source_refs=()),
    )
    root = _manifest(
        "dependency-root",
        dependencies=(
            "stale-child@*",
            "deprecated-child@*",
            "unsatisfied-child@*",
            "missing-child@^2.0.0",
        ),
    )
    registry = CapabilityRegistry.from_manifests((stale, deprecated, unsatisfied, root))
    result = registry.resolve_dependencies("dependency-root")
    codes = {item.code for item in result.diagnostics}

    assert not result.ok
    assert {
        "STALE_DEPENDENCY",
        "DEPRECATED_DEPENDENCY",
        "UNSATISFIED_DEPENDENCY",
        "MISSING_DEPENDENCY",
    } <= codes
    assert result.resolved_ids == ("dependency-root",)


def test_dependency_resolution_is_dependency_first_deduplicated_and_conflict_aware() -> None:
    shared = replace(
        _manifest("shared"),
        dependencies=CapabilityDependencies(
            capabilities=(),
            tools=("python",),
            providers=("local.success",),
            references=("docs/shared",),
        ),
    )
    root = _manifest("root", dependencies=("shared", "shared"), conflicts=("shared",))
    registry = CapabilityRegistry.from_manifests((root, shared))

    result = registry.resolve_dependencies("root")

    assert result.ok is False
    assert result.resolved_ids == ("shared", "root")
    assert result.external_tools == ("python",)
    assert result.external_providers == ("local.success",)
    assert result.external_references == (
        "architecture/docs/contracts/CapabilityManifest.json.md",
        "docs/shared",
    )
    assert any(item.code == "CAPABILITY_CONFLICT" for item in result.diagnostics)


def test_dependency_resolution_reports_missing_root_and_accepts_manifest_root() -> None:
    registry = CapabilityRegistry().register(_manifest("root", dependencies=()))
    missing = registry.resolve_dependencies("unknown")
    assert missing.root == "unknown"
    assert missing.resolved == ()
    assert missing.diagnostics[0].code == "MISSING_ROOT"

    root_manifest = registry.find("root")
    assert root_manifest is not None
    resolved = registry.resolve_dependencies(root_manifest)
    assert resolved.ok
    assert resolved.resolved_ids == ("root",)
