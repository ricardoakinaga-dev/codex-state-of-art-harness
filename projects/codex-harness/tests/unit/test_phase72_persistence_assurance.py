from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from test_contracts import all_records
from test_phase71_persistence_hardening import _persisted_run, _store

import harness_kernel.persistence as persistence_module
from harness_kernel.boundary import BoundaryError, ProjectBoundary
from harness_kernel.models import ArtifactRecord, TelemetryEventType
from harness_kernel.persistence import RunStore
from harness_kernel.providers import digest_output
from harness_kernel.serialization import to_dict, to_json
from harness_kernel.telemetry import create_event


def _artifact_for_store(run_id: str = "RUN-P7-2-ARTIFACT") -> ArtifactRecord:
    base = all_records()[5]
    output = {"bounded": True}
    return replace(
        base,
        run_id=run_id,
        content=replace(
            base.content,
            locator=f".harness/state/runs/{run_id}/{base.artifact_id}.json",
            digest=digest_output(output),
            size_bytes=len(to_json(output).encode("utf-8")),
        ),
    )


def _rewrite_json(boundary: ProjectBoundary, relative: str, value: object) -> None:
    assert isinstance(value, dict)
    boundary.atomic_write_json(relative, value)


def test_run_store_rejects_invalid_identifiers_and_record_shapes(tmp_path: Path) -> None:
    boundary, store = _store(tmp_path)

    with pytest.raises(BoundaryError, match="run identifier"):
        store._run_path("../escape")
    with pytest.raises(BoundaryError, match="run identifier"):
        store.write_evidence("../escape", [])
    with pytest.raises(BoundaryError, match="identity"):
        store.write_evidence("RUN-PERSIST-INPUT", [{"run_id": "OTHER"}])
    with pytest.raises(BoundaryError, match="run identifier"):
        store.write_artifact_records("../escape", [])
    with pytest.raises(BoundaryError, match="identity"):
        store.write_artifact_records("RUN-PERSIST-INPUT", [{"run_id": "OTHER"}])


def test_run_store_rejects_untrusted_artifact_inputs(tmp_path: Path) -> None:
    _boundary, store = _store(tmp_path)
    artifact = _artifact_for_store()
    output = {"bounded": True}

    with pytest.raises(BoundaryError, match="ArtifactRecord"):
        store.write_artifact(object(), output)  # type: ignore[arg-type]
    with pytest.raises(BoundaryError, match="locator"):
        store.write_artifact(
            replace(artifact, content=replace(artifact.content, locator="")),
            output,
        )
    with pytest.raises(BoundaryError, match="identity"):
        store.write_artifact(replace(artifact, artifact_id=""), output)
    with pytest.raises(BoundaryError, match="owning invocation"):
        store.write_artifact(
            replace(artifact, producer=replace(artifact.producer, invocation_id=None)),
            output,
        )
    with pytest.raises(BoundaryError, match="digest"):
        store.write_artifact(
            replace(artifact, content=replace(artifact.content, digest="sha256:" + "0" * 64)),
            output,
        )
    with pytest.raises(BoundaryError, match="size"):
        store.write_artifact(
            replace(artifact, content=replace(artifact.content, size_bytes=999_999)),
            output,
        )


def test_recovery_rejects_invalid_artifact_record_and_identity(tmp_path: Path) -> None:
    runtime = _persisted_run(tmp_path, "RUN-PERSIST-ARTIFACT-VALIDATION")
    boundary = ProjectBoundary(tmp_path)
    relative = f".harness/evidence/runs/{runtime.summary.run_id}-artifacts.json"
    payload = boundary.read_json(relative)
    assert isinstance(payload, dict)
    records = payload["records"]
    assert isinstance(records, list) and isinstance(records[0], dict)

    invalid = {**records[0], "title": ""}
    _rewrite_json(boundary, relative, {**payload, "records": [invalid]})
    recovery = RunStore(boundary).recover(runtime.summary.run_id)
    assert recovery.reason == "persisted artifact record violates its contract"

    runtime = _persisted_run(tmp_path, "RUN-PERSIST-ARTIFACT-IDENTITY")
    boundary = ProjectBoundary(tmp_path)
    relative = f".harness/evidence/runs/{runtime.summary.run_id}-artifacts.json"
    payload = boundary.read_json(relative)
    assert isinstance(payload, dict)
    records = payload["records"]
    assert isinstance(records, list) and isinstance(records[0], dict)
    _rewrite_json(
        boundary,
        relative,
        {**payload, "records": [{**records[0], "run_id": "RUN-OTHER"}]},
    )
    recovery = RunStore(boundary).recover(runtime.summary.run_id)
    assert recovery.reason == "persisted artifact identity does not match its run"


def test_recovery_rejects_an_artifact_locator_outside_the_owned_run(tmp_path: Path) -> None:
    runtime = _persisted_run(tmp_path, "RUN-PERSIST-ARTIFACT-LOCATOR")
    boundary = ProjectBoundary(tmp_path)
    relative = f".harness/evidence/runs/{runtime.summary.run_id}-artifacts.json"
    payload = boundary.read_json(relative)
    assert isinstance(payload, dict)
    records = payload["records"]
    assert isinstance(records, list) and isinstance(records[0], dict)
    record = records[0]
    content = record["content"]
    assert isinstance(content, dict)
    _rewrite_json(
        boundary,
        relative,
        {**payload, "records": [{**record, "content": {**content, "locator": "other.json"}}]},
    )

    recovery = RunStore(boundary).recover(runtime.summary.run_id)

    assert recovery.reason == "persisted artifact locator is outside its owned run"


def test_bundle_verification_rejects_summary_reference_mismatches(tmp_path: Path) -> None:
    runtime = _persisted_run(tmp_path, "RUN-PERSIST-SUMMARY-REFS")
    boundary = ProjectBoundary(tmp_path)
    store = RunStore(boundary)

    with pytest.raises(BoundaryError, match="artifact references"):
        store._verify_persisted_bundle(
            runtime.summary.run_id,
            replace(runtime.summary, artifacts=()),
        )
    with pytest.raises(BoundaryError, match="evidence references"):
        store._verify_persisted_bundle(
            runtime.summary.run_id,
            replace(runtime.summary, evidence=()),
        )


def test_bundle_verification_rejects_semantically_invalid_typed_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _persisted_run(tmp_path, "RUN-PERSIST-SEMANTIC-ARTIFACT")
    boundary = ProjectBoundary(tmp_path)
    store = RunStore(boundary)
    real_validate = persistence_module.validate

    def reject_artifact(value: object):
        if isinstance(value, ArtifactRecord):
            return type("Validation", (), {"is_valid": False})()
        return real_validate(value)

    monkeypatch.setattr(persistence_module, "validate", reject_artifact)
    with pytest.raises(BoundaryError, match="artifact record failed validation"):
        store._verify_persisted_bundle(runtime.summary.run_id, runtime.summary)

    runtime = _persisted_run(tmp_path, "RUN-PERSIST-SEMANTIC-EVIDENCE")
    boundary = ProjectBoundary(tmp_path)
    store = RunStore(boundary)

    def reject_evidence(value: object):
        if type(value).__name__ == "EvidenceRecord":
            return type("Validation", (), {"is_valid": False})()
        return real_validate(value)

    monkeypatch.setattr(persistence_module, "validate", reject_evidence)
    with pytest.raises(BoundaryError, match="evidence record failed validation"):
        store._verify_persisted_bundle(runtime.summary.run_id, runtime.summary)


def test_recovery_rejects_invalid_evidence_record_validation(tmp_path: Path) -> None:
    runtime = _persisted_run(tmp_path, "RUN-PERSIST-EVIDENCE-VALIDATION")
    boundary = ProjectBoundary(tmp_path)
    relative = f".harness/evidence/runs/{runtime.summary.run_id}.json"
    payload = boundary.read_json(relative)
    assert isinstance(payload, dict)
    records = payload["records"]
    assert isinstance(records, list) and isinstance(records[0], dict)
    _rewrite_json(
        boundary,
        relative,
        {**payload, "records": [{**records[0], "observation": ""}]},
    )

    recovery = RunStore(boundary).recover(runtime.summary.run_id)

    assert recovery.reason == "persisted evidence record violates its contract"


def test_bundle_verification_rejects_unknown_telemetry_references(tmp_path: Path) -> None:
    runtime = _persisted_run(tmp_path, "RUN-PERSIST-TELEMETRY-REF")
    boundary = ProjectBoundary(tmp_path)
    event = create_event(
        event_id="EVENT-PERSIST-UNKNOWN-REF",
        event_sequence=1,
        timestamp="2026-08-30T15:00:00Z",
        task_id=runtime.summary.task_id,
        run_id=runtime.summary.run_id,
        event_type=TelemetryEventType.TASK_RECEIVED,
        artifact_refs=("ART-UNKNOWN",),
    )
    relative = f".harness/telemetry/runs/{runtime.summary.run_id}.jsonl"
    boundary.atomic_write_bytes(relative, to_json(to_dict(event)).encode("utf-8") + b"\n")

    recovery = RunStore(boundary).recover(runtime.summary.run_id)

    assert recovery.reason == "persisted telemetry references are invalid"


def test_recovery_preserves_missing_and_corrupt_run_classification(tmp_path: Path) -> None:
    boundary, store = _store(tmp_path)
    store.write_record("RUN-PERSIST-CORRUPT", {"run_id": "RUN-PERSIST-CORRUPT", "status": []})
    corrupt = store.recover("RUN-PERSIST-CORRUPT")
    missing = store.recover("RUN-PERSIST-MISSING")

    assert corrupt.status.value == "CORRUPT"
    assert missing.status.value == "MISSING"
