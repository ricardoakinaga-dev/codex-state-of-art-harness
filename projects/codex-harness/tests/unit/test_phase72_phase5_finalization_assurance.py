from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_phase5_finalization import (
    _artifact,
    _project,
    _receipt,
    _renders,
)

from harness_kernel import phase5_finalization
from harness_kernel.phase5_finalization import (
    _browser_metrics,
    artifact_from_receipt,
    render_records,
)
from harness_kernel.phase5_models import RenderRecord
from harness_kernel.phase5_paths import Phase5CliError
from harness_kernel.phase5_pilot import load_task


def test_artifact_receipt_identity_and_status_guards_are_exercised(tmp_path: Path) -> None:
    project = _project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    artifact = _artifact(task, "artifact_v1", "INV-P72")

    with pytest.raises(Phase5CliError, match="bound"):
        artifact_from_receipt(
            task,
            _receipt(artifact),
            expected_identity={"package_fingerprint": "sha256:" + "f" * 64},
        )
    for key, value, message in (
        ("producer_capability", "other", "producer"),
        ("status", "FAIL", "successful"),
        ("artifact_version", "artifact_v2", "version"),
    ):
        receipt = _receipt(artifact)
        receipt[key] = value
        with pytest.raises(Phase5CliError, match=message):
            artifact_from_receipt(task, receipt)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("artifact_path", None, "does not bind"),
        ("attempts", None, "does not bind"),
        ("attempts", [], "no invocation"),
        ("artifact_id", "", "artifact id"),
        ("attempt_count", True, "attempt count"),
    ),
)
def test_artifact_receipt_shape_guards_fail_closed(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    project = _project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    artifact = _artifact(task, "artifact_v1", "INV-P72")
    receipt = _receipt(artifact)
    receipt[field] = value
    with pytest.raises(Phase5CliError, match=message):
        artifact_from_receipt(task, receipt)


def test_artifact_receipt_attempt_count_and_v2_parent_guards_are_exercised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    artifact = _artifact(task, "artifact_v1", "INV-P72")
    receipt = _receipt(artifact)
    receipt["attempt_count"] = 2
    with pytest.raises(Phase5CliError, match="attempts"):
        artifact_from_receipt(task, receipt)

    v2 = _artifact(task, "artifact_v2", "INV-P72-V2", artifact.digest)
    v2_receipt = _receipt(v2, repair=True, parent=artifact.digest)
    monkeypatch.setattr(
        phase5_finalization.ArtifactPacket,
        "from_content",
        lambda **_kwargs: replace(v2, parent_artifact_digest=None),
    )
    with pytest.raises(Phase5CliError, match="parent"):
        artifact_from_receipt(task, v2_receipt, version="artifact_v2")


def test_render_and_browser_metric_evidence_cannot_escape_evidence_root(tmp_path: Path) -> None:
    project = _project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    artifact = _artifact(task, "artifact_v1", "INV-P72")
    evidence = project / "evidence/phase-5/pilots/design-director"
    evidence.mkdir(parents=True)
    outside = project / "untrusted-render.png"
    outside.write_bytes(b"png")
    mobile = evidence / "mobile.png"
    mobile.write_bytes(b"png")
    with pytest.raises(Phase5CliError, match="evidence directory"):
        render_records(project, evidence, outside, mobile)

    metric = outside.with_name("untrusted-render-metrics.json")
    metric.write_text("{}", encoding="utf-8")
    render = RenderRecord.from_file("R", "artifact_v1", outside, (1, 1), root=project)
    with pytest.raises(Phase5CliError, match="evidence directory"):
        _browser_metrics(project, evidence, (render,), artifact=artifact)


def test_v2_finalization_rejects_stale_v1_evidence_binding(tmp_path: Path) -> None:

    from test_phase5_finalization import _args, _critique, _write_identity

    from harness_kernel.phase4_evidence import EvidenceWriter
    from harness_kernel.phase5_finalization import finalize, render_records
    from harness_kernel.phase5_pilot import write_public_json
    from harness_kernel.phase5_verification import make_blind_packet

    project = _project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    evidence = project / "evidence/phase-5/pilots/design-director"
    writer = EvidenceWriter(evidence)
    artifact_v1 = _artifact(task, "artifact_v1", "INV-P72-V1")
    _write_identity(writer, task)
    write_public_json(writer, "builder-invocation-receipt.json", _receipt(artifact_v1))
    desktop_v1, mobile_v1 = _renders(project, task, "artifact-v1", artifact_v1)
    packet_v1 = make_blind_packet(
        task,
        artifact_v1,
        render_records(project, evidence, desktop_v1, mobile_v1),
    )
    critique_v1 = evidence / "critique-input-v1.json"
    write_public_json(writer, "critique-input-v1.json", _critique(artifact_v1, packet_v1))
    (desktop_v1.parent / "console-errors.json").write_text("[]\n")
    (desktop_v1.parent / "network-failures.json").write_text("[]\n")
    finalize(project, _args(desktop_v1, mobile_v1, critique_v1, version="artifact_v1"))

    stale = json.loads((evidence / "verification-v1.json").read_text(encoding="utf-8"))
    stale["artifact_digest"] = "sha256:" + "f" * 64
    (evidence / "verification-v1.json").write_text(json.dumps(stale), encoding="utf-8")
    artifact_v2 = _artifact(task, "artifact_v2", "INV-P72-V2", artifact_v1.digest)
    _write_identity(writer, task, repair=True)
    write_public_json(
        writer,
        "builder-repair-receipt.json",
        _receipt(artifact_v2, repair=True, parent=artifact_v1.digest),
    )
    desktop_v2, mobile_v2 = _renders(project, task, "artifact-v2", artifact_v2)
    packet_v2 = make_blind_packet(
        task,
        artifact_v2,
        render_records(
            project,
            evidence,
            desktop_v2,
            mobile_v2,
            artifact_version="artifact_v2",
        ),
    )
    critique_v2 = evidence / "critique-input-v2.json"
    write_public_json(writer, "critique-input-v2.json", _critique(artifact_v2, packet_v2))
    (desktop_v2.parent / "console-errors.json").write_text("[]\n")
    (desktop_v2.parent / "network-failures.json").write_text("[]\n")
    with pytest.raises(Phase5CliError, match="verification-v1"):
        finalize(project, _args(desktop_v2, mobile_v2, critique_v2, version="artifact_v2"))
