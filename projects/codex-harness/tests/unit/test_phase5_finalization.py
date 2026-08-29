from __future__ import annotations

import argparse
import json
import shutil
import struct
from pathlib import Path

import pytest
from phase5_support import valid_html

from harness_kernel.phase4_evidence import EvidenceWriter
from harness_kernel.phase5_artifacts import extract_response_artifact, materialize_response_artifact
from harness_kernel.phase5_finalization import (
    artifact_from_receipt,
    finalize,
    prepare_review,
    render_records,
)
from harness_kernel.phase5_models import ArtifactPacket, BlindPacket, Phase5Status, Phase5Task
from harness_kernel.phase5_paths import Phase5CliError
from harness_kernel.phase5_pilot import load_task, write_public_json
from harness_kernel.phase5_verification import make_blind_packet

IDENTITY_PACKAGE = "sha256:" + "1" * 64
IDENTITY_MANIFEST = "sha256:" + "2" * 64
IDENTITY_CONTEXT = "sha256:" + "3" * 64


def _project(tmp_path: Path) -> Path:
    source_root = Path(__file__).parents[1]
    project = tmp_path / "project"
    task_target = project / "tests/fixtures/phase5/design-pilot/task.json"
    task_target.parent.mkdir(parents=True)
    (task_target.parent / "workspace/artifacts").mkdir(parents=True)
    (project / "config").mkdir()
    shutil.copyfile(
        source_root / "fixtures/phase5/design-pilot/task.json",
        task_target,
    )
    shutil.copyfile(
        Path(__file__).parents[2] / "config/phase5-composition-policy.json",
        project / "config/phase5-composition-policy.json",
    )
    return project


def _png(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)


def _artifact(
    task: Phase5Task, version: str, invocation_id: str, parent: str | None = None
) -> ArtifactPacket:
    return materialize_response_artifact(
        extract_response_artifact(
            json.dumps({"artifact_filename": "index.html", "artifact_html": valid_html()})
        ),
        task,
        version=version,
        artifact_id="ART-P5-V" + version[-1],
        invocation_id=invocation_id,
        parent_artifact_digest=parent,
    )


def _receipt(
    artifact: ArtifactPacket, *, repair: bool = False, parent: str | None = None
) -> dict[str, object]:
    prefix = "REPAIR-" if repair else ""
    return {
        "schema_version": "P5-REPAIR-RECEIPT-1" if repair else "P5-BUILDER-RECEIPT-1",
        "task_id": artifact.task_id,
        "run_id": "RUN-P5-DESIGN-001",
        "status": "PASS",
        "attempt_count": 1,
        "attempts": [{"invocation_id": artifact.invocation_id}],
        "artifact_id": artifact.artifact_id,
        "artifact_version": artifact.version,
        "artifact_path": artifact.path,
        "artifact_digest": artifact.digest,
        "parent_artifact_digest": parent,
        "producer_capability": "design-director",
        "capability_id": "design-director",
        "capability_version": "0.1.0",
        "package_fingerprint": IDENTITY_PACKAGE,
        "manifest_fingerprint": IDENTITY_MANIFEST,
        "authorization_id": "AUTH-TEST-" + prefix.rstrip("-") if prefix else "AUTH-TEST",
        "context_digest": IDENTITY_CONTEXT,
        "repair_correction": "Recompose the 390px header to avoid three-line status crowding."
        if repair
        else None,
    }


def _write_identity(writer: EvidenceWriter, task: Phase5Task, *, repair: bool = False) -> None:
    prefix = "REPAIR-" if repair else ""
    write_public_json(
        writer,
        "eligibility.json",
        {
            "status": "PASS",
            "fingerprint": {
                "capability_id": "design-director",
                "version": "0.1.0",
                "package_fingerprint": IDENTITY_PACKAGE,
                "manifest_fingerprint": IDENTITY_MANIFEST,
            },
        },
    )
    write_public_json(
        writer,
        "builder-repair-authorization.json" if repair else "builder-authorization.json",
        {
            "authorization_id": "AUTH-TEST-" + prefix.rstrip("-") if prefix else "AUTH-TEST",
            "task_id": task.task_id,
            "run_id": task.run_id,
            "capability_id": "design-director",
            "capability_version": "0.1.0",
            "package_fingerprint": IDENTITY_PACKAGE,
        },
    )
    write_public_json(
        writer,
        "builder-repair-context-manifest.json" if repair else "builder-context-manifest.json",
        {
            "task_id": task.task_id,
            "capability_id": "design-director",
            "package_fingerprint": IDENTITY_PACKAGE,
            "digest": IDENTITY_CONTEXT,
        },
    )


def _renders(
    project: Path, task: Phase5Task, version: str, artifact: ArtifactPacket
) -> tuple[Path, Path]:
    evidence = project / "evidence/phase-5/pilots/design-director" / version.replace("_", "-")
    evidence.mkdir(parents=True)
    desktop = evidence / "desktop.png"
    mobile = evidence / "mobile.png"
    desktop.write_bytes(_png(1440, 900))
    mobile.write_bytes(_png(390, 844))
    metrics = {
        "artifact_version": artifact.version,
        "artifact_digest": artifact.digest,
        "capture_method": "playwright_native",
        "capture_id": "CAP-P5-TEST",
        "url": "http://127.0.0.1:8765/index.html",
        "browser": {
            "engine": "Chromium",
            "version": "152.0.7977.64",
            "executable": "/opt/google/chrome/chrome",
            "executable_digest": "sha256:" + "4" * 64,
        },
        "viewport": {"width": 1440, "height": 900},
        "document_width": 1440,
        "viewport_width": 1440,
        "body_height": 900,
        "h1_count": 1,
        "landmarks": [
            {"tag": "header", "count": 1},
            {"tag": "main", "count": 1},
            {"tag": "footer", "count": 1},
        ],
        "focusable_count": 1,
        "external_resources": [],
    }
    (evidence / "desktop-metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    mobile_metrics = dict(metrics)
    mobile_metrics["viewport"] = {"width": 390, "height": 844}
    mobile_metrics["document_width"] = 390
    mobile_metrics["viewport_width"] = 390
    (evidence / "mobile-metrics.json").write_text(json.dumps(mobile_metrics), encoding="utf-8")
    return desktop, mobile


def _critique(
    artifact: ArtifactPacket, packet: BlindPacket, *, verdict: str = "PASS"
) -> dict[str, object]:
    return {
        "benchmark_id": packet.benchmark_id,
        "run_id": packet.run_id,
        "inspection_id": "INS-P5-TEST",
        "artifact_digest": artifact.digest,
        "packet_digest": packet.packet_digest,
        "independence": "INDEPENDENT",
        "blinded": True,
        "builder_rationale_withheld": True,
        "self_score_withheld": True,
        "verdict": verdict,
        "overall_score": 88,
        "evidence_confidence": "HIGH",
        "dimension_scores": {"ART_DIRECTION": 8.8},
        "findings": [],
        "top_corrections": [],
        "evidence_missing": [],
    }


def _args(desktop: Path, mobile: Path, critique: Path, *, version: str) -> argparse.Namespace:
    return argparse.Namespace(
        task=None,
        evidence_dir=None,
        desktop=desktop,
        mobile=mobile,
        critique=critique,
        console_errors=desktop.parent / "console-errors.json",
        network_failures=desktop.parent / "network-failures.json",
        artifact_version=version,
    )


def test_prepare_and_finalize_v1_are_version_bound(tmp_path: Path) -> None:
    project = _project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    artifact = _artifact(task, "artifact_v1", "INV-TEST-V1")
    evidence = project / "evidence/phase-5/pilots/design-director"
    writer = EvidenceWriter(evidence)
    _write_identity(writer, task)
    write_public_json(writer, "builder-invocation-receipt.json", _receipt(artifact))
    desktop, mobile = _renders(project, task, "artifact-v1", artifact)
    renders = render_records(project, evidence, desktop, mobile)
    packet = make_blind_packet(task, artifact, renders)
    critique_path = evidence / "independent.json"
    write_public_json(writer, "independent.json", _critique(artifact, packet))
    (desktop.parent / "console-errors.json").write_text("[]\n")
    (desktop.parent / "network-failures.json").write_text("[]\n")
    review = prepare_review(project, _args(desktop, mobile, critique_path, version="artifact_v1"))
    assert review["status"] == Phase5Status.PASS
    result = finalize(project, _args(desktop, mobile, critique_path, version="artifact_v1"))
    assert result["status"] == Phase5Status.PASS_WITH_LIMITATIONS
    assert result["support_level"] == "A"
    assert (evidence / "verification-v1.json").is_file()
    assert (evidence / "review-request-v1.json").is_file()


def test_finalize_v2_retains_v1_and_records_repair_graph(tmp_path: Path) -> None:
    project = _project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    evidence = project / "evidence/phase-5/pilots/design-director"
    writer = EvidenceWriter(evidence)
    artifact_v1 = _artifact(task, "artifact_v1", "INV-TEST-V1")
    _write_identity(writer, task)
    write_public_json(writer, "builder-invocation-receipt.json", _receipt(artifact_v1))
    desktop_v1, mobile_v1 = _renders(project, task, "artifact-v1", artifact_v1)
    renders_v1 = render_records(project, evidence, desktop_v1, mobile_v1)
    critique_v1_path = evidence / "critique-input-v1.json"
    write_public_json(
        writer,
        "critique-input-v1.json",
        _critique(artifact_v1, make_blind_packet(task, artifact_v1, renders_v1)),
    )
    (desktop_v1.parent / "console-errors.json").write_text("[]\n")
    (desktop_v1.parent / "network-failures.json").write_text("[]\n")
    finalize(project, _args(desktop_v1, mobile_v1, critique_v1_path, version="artifact_v1"))
    artifact_v2 = _artifact(task, "artifact_v2", "INV-TEST-V2", artifact_v1.digest)
    _write_identity(writer, task, repair=True)
    write_public_json(
        writer,
        "builder-repair-receipt.json",
        _receipt(artifact_v2, repair=True, parent=artifact_v1.digest),
    )
    desktop_v2, mobile_v2 = _renders(project, task, "artifact-v2", artifact_v2)
    renders_v2 = render_records(
        project, evidence, desktop_v2, mobile_v2, artifact_version="artifact_v2"
    )
    critique_v2_path = evidence / "critique-input-v2.json"
    write_public_json(
        writer,
        "critique-input-v2.json",
        _critique(artifact_v2, make_blind_packet(task, artifact_v2, renders_v2)),
    )
    (desktop_v2.parent / "console-errors.json").write_text("[]\n")
    (desktop_v2.parent / "network-failures.json").write_text("[]\n")
    result = finalize(
        project, _args(desktop_v2, mobile_v2, critique_v2_path, version="artifact_v2")
    )
    receipt = json.loads((evidence / "composition-receipt.json").read_text())
    assert result["status"] == Phase5Status.PASS_WITH_LIMITATIONS
    assert receipt["artifact_versions"] == ["artifact_v1", "artifact_v2"]
    assert "OPTIONAL_REPAIR" in receipt["events"]
    assert receipt["stale_evidence"] == ["verification-v1", "critique-v1"]
    final_verification = json.loads((evidence / "final-verification.json").read_text())
    verification_v2 = json.loads((evidence / "verification-v2.json").read_text())
    assert final_verification["verification_id"] != verification_v2["verification_id"]
    assert final_verification["digest"] != verification_v2["digest"]


def test_finalization_rejects_non_independent_critic_and_unbound_v2(tmp_path: Path) -> None:
    project = _project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    artifact = _artifact(task, "artifact_v1", "INV-TEST-V1")
    bad_receipt = _receipt(artifact)
    bad_receipt["artifact_version"] = "artifact_v2"
    with pytest.raises(Phase5CliError):
        artifact_from_receipt(task, bad_receipt, version="artifact_v2")
    wrong_task_receipt = _receipt(artifact)
    wrong_task_receipt["task_id"] = "TASK-P5-OTHER"
    with pytest.raises(Phase5CliError):
        artifact_from_receipt(task, wrong_task_receipt)
    evidence = project / "evidence/phase-5/pilots/design-director"
    writer = EvidenceWriter(evidence)
    _write_identity(writer, task)
    write_public_json(writer, "builder-invocation-receipt.json", _receipt(artifact))
    desktop, mobile = _renders(project, task, "artifact-v1", artifact)
    renders = render_records(project, evidence, desktop, mobile)
    packet = make_blind_packet(task, artifact, renders)
    critique_path = evidence / "bad-critic.json"
    bad_critic = _critique(artifact, packet)
    bad_critic["independence"] = "UNKNOWN"
    write_public_json(writer, "bad-critic.json", bad_critic)
    (desktop.parent / "console-errors.json").write_text("[]\n")
    (desktop.parent / "network-failures.json").write_text("[]\n")
    with pytest.raises(Phase5CliError):
        finalize(project, _args(desktop, mobile, critique_path, version="artifact_v1"))


def test_finalize_rejects_browser_metrics_without_native_provenance(tmp_path: Path) -> None:
    project = _project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    artifact = _artifact(task, "artifact_v1", "INV-TEST-V1")
    evidence = project / "evidence/phase-5/pilots/design-director"
    writer = EvidenceWriter(evidence)
    _write_identity(writer, task)
    write_public_json(writer, "builder-invocation-receipt.json", _receipt(artifact))
    desktop, mobile = _renders(project, task, "artifact-v1", artifact)
    packet = make_blind_packet(task, artifact, render_records(project, evidence, desktop, mobile))
    critique_path = evidence / "critique-input.json"
    write_public_json(writer, "critique-input.json", _critique(artifact, packet))
    desktop_metrics = desktop.parent / "desktop-metrics.json"
    metrics = json.loads(desktop_metrics.read_text(encoding="utf-8"))
    metrics.pop("browser", None)
    desktop_metrics.write_text(json.dumps(metrics), encoding="utf-8")
    (desktop.parent / "console-errors.json").write_text("[]\n")
    (desktop.parent / "network-failures.json").write_text("[]\n")
    with pytest.raises(Phase5CliError):
        finalize(project, _args(desktop, mobile, critique_path, version="artifact_v1"))
