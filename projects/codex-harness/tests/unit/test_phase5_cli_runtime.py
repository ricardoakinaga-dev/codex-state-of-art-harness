from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pytest
from phase5_support import (
    HOST_DIGEST,
    MANIFEST_DIGEST,
    PACKAGE_DIGEST,
    make_fingerprint,
    valid_html,
)

from harness_kernel import phase5_cli as cli
from harness_kernel.phase4_evidence import EvidenceWriter
from harness_kernel.phase5_artifacts import extract_response_artifact, materialize_response_artifact
from harness_kernel.phase5_cli import PilotPreflight
from harness_kernel.phase5_execution import BuilderResponse
from harness_kernel.phase5_finalization import render_records
from harness_kernel.phase5_models import Phase5Status
from harness_kernel.phase5_pilot import load_task, write_public_json
from harness_kernel.phase5_policy import Phase5Allowlist
from harness_kernel.phase5_verification import make_blind_packet


def _project(tmp_path: Path) -> Path:
    source_root = Path(__file__).parents[1]
    project = tmp_path / "project"
    task_target = project / "tests/fixtures/phase5/design-pilot/task.json"
    task_target.parent.mkdir(parents=True)
    (task_target.parent / "workspace/artifacts").mkdir(parents=True)
    (project / "config").mkdir()
    shutil.copyfile(source_root / "fixtures/phase5/design-pilot/task.json", task_target)
    shutil.copyfile(
        Path(__file__).parents[2] / "config/phase5-composition-policy.json",
        project / "config/phase5-composition-policy.json",
    )
    return project


def _preflight(project: Path) -> PilotPreflight:
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    (project / "package").mkdir()
    fingerprint = make_fingerprint(project / "package")
    return PilotPreflight(
        task=task,
        allowlist=Phase5Allowlist(
            builder=fingerprint,
            builder_manifest_fingerprint=fingerprint.manifest_fingerprint,
            approved_status="APPROVED_RESPONSE_ONLY",
        ),
        adapter=cli.CodexHostAdapter(
            project_root=project,
            workspace_root=Path(task.workspace),
            home_dir=Path.home(),
        ),
        host_adapter=cli.Phase5AppServerAdapter(),
        selected_record=None,
        fingerprint=fingerprint,
        eligibility=None,
        secondary={"status": "BLOCKED"},
        resolution_status="RESOLVED",
        resolution_blockers=(),
        binding=(
            ("codex",),
            "/usr/bin/codex",
            HOST_DIGEST,
            (),
            "/usr/bin/python",
            HOST_DIGEST,
        ),
    )


def _seed_v1(project: Path) -> tuple[Path, Path, str]:
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    artifact = materialize_response_artifact(
        extract_response_artifact(
            json.dumps({"artifact_filename": "index.html", "artifact_html": valid_html()})
        ),
        task,
        version="artifact_v1",
        artifact_id="ART-P5-V1",
        invocation_id="INV-P5-V1",
    )
    evidence = project / "evidence/phase-5/pilots/design-director"
    writer = EvidenceWriter(evidence)
    context_digest = "sha256:" + "4" * 64
    write_public_json(
        writer,
        "eligibility.json",
        {
            "status": "PASS",
            "fingerprint": {
                "capability_id": "design-director",
                "version": "0.1.0",
                "package_fingerprint": PACKAGE_DIGEST,
                "manifest_fingerprint": MANIFEST_DIGEST,
            },
        },
    )
    write_public_json(
        writer,
        "builder-authorization.json",
        {
            "authorization_id": "AUTH-TEST",
            "task_id": task.task_id,
            "run_id": task.run_id,
            "capability_id": "design-director",
            "capability_version": "0.1.0",
            "package_fingerprint": PACKAGE_DIGEST,
        },
    )
    write_public_json(
        writer,
        "builder-context-manifest.json",
        {
            "task_id": task.task_id,
            "capability_id": "design-director",
            "package_fingerprint": PACKAGE_DIGEST,
            "digest": context_digest,
        },
    )
    write_public_json(
        writer,
        "builder-invocation-receipt.json",
        {
            "schema_version": "P5-BUILDER-RECEIPT-1",
            "task_id": task.task_id,
            "run_id": task.run_id,
            "status": "PASS",
            "attempt_count": 1,
            "attempts": [{"invocation_id": artifact.invocation_id}],
            "artifact_id": artifact.artifact_id,
            "artifact_version": artifact.version,
            "artifact_path": artifact.path,
            "artifact_digest": artifact.digest,
            "producer_capability": "design-director",
            "capability_id": "design-director",
            "capability_version": "0.1.0",
            "package_fingerprint": PACKAGE_DIGEST,
            "manifest_fingerprint": MANIFEST_DIGEST,
            "authorization_id": "AUTH-TEST",
            "context_digest": context_digest,
        },
    )
    artifact_evidence = evidence / "artifact-v1"
    artifact_evidence.mkdir(parents=True)
    desktop = artifact_evidence / "desktop.png"
    mobile = artifact_evidence / "mobile.png"
    png = b"\x89PNG\r\n\x1a\n" + (1440).to_bytes(4, "big") + (900).to_bytes(4, "big")
    desktop.write_bytes(png)
    mobile.write_bytes(png)
    desktop_records = render_records(project, evidence, desktop, mobile)
    packet = make_blind_packet(task, artifact, desktop_records)
    write_public_json(writer, "blind-packet-v1.json", packet)
    write_public_json(
        writer,
        "critique-v1.json",
        {
            "artifact_digest": artifact.digest,
            "benchmark_id": packet.benchmark_id,
            "run_id": packet.run_id,
            "inspection_id": "INS-P5-CLI",
            "packet_digest": packet.packet_digest,
            "independence": "INDEPENDENT",
            "blinded": True,
            "builder_rationale_withheld": True,
            "self_score_withheld": True,
            "verdict": "PASS_WITH_LIMITATIONS",
            "overall_score": 80,
            "dimension_scores": {"ART_DIRECTION": 8},
            "findings": [
                {
                    "id": "F-CLI-001",
                    "location": "mobile",
                    "expected": "compact header",
                    "observed": "crowding",
                    "severity": "MEDIUM",
                    "evidence": "mobile.png",
                    "status": "OPEN",
                }
            ],
            "top_corrections": ["Apply the bounded mobile header correction."],
        },
    )
    return desktop, mobile, "Apply the bounded mobile header correction."


def test_run_builder_materializes_response_and_records_handoff(tmp_path, monkeypatch) -> None:
    project = _project(tmp_path)
    preflight = _preflight(project)
    evidence = project / "evidence/phase-5/pilots/design-director"
    writer = EvidenceWriter(evidence)
    response = BuilderResponse(
        Phase5Status.PASS,
        "INV-P5-FAKE",
        json.dumps({"artifact_filename": "index.html", "artifact_html": valid_html()}),
        True,
        "HOST_LOAD_UNOBSERVABLE",
    )
    monkeypatch.setattr(cli, "invoke_host_builder", lambda *_args, **_kwargs: response)
    result = cli._run_builder(preflight, writer)
    assert result["status"] == Phase5Status.PASS_WITH_LIMITATIONS
    assert (evidence / "artifact-v1/index.html").is_file()
    assert (
        json.loads((evidence / "builder-invocation-receipt.json").read_text())["attempt_count"] == 1
    )


def test_repair_is_one_shot_and_recovery_does_not_reinvoke_host(tmp_path, monkeypatch) -> None:
    project = _project(tmp_path)
    desktop, mobile, correction = _seed_v1(project)
    preflight = _preflight(project)
    monkeypatch.setattr(cli, "_preflight", lambda *_args: preflight)
    monkeypatch.setattr(
        cli,
        "_preflight_route",
        lambda *_args, **_kwargs: {"status": Phase5Status.PASS, "blockers": ()},
    )
    response = BuilderResponse(
        Phase5Status.PASS,
        "INV-P5-V2",
        json.dumps({"artifact_filename": "index.html", "artifact_html": valid_html()}),
        True,
        "HOST_LOAD_UNOBSERVABLE",
    )
    calls = 0

    def fake_invoke(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return response

    monkeypatch.setattr(cli, "invoke_host_builder", fake_invoke)
    arguments = argparse.Namespace(
        task=None,
        policy=None,
        evidence_dir=None,
        confirm_fingerprint=HOST_DIGEST,
        correction=correction,
    )
    first = cli._repair(project, arguments)
    second = cli._repair(project, arguments)
    assert first["status"] == Phase5Status.PASS_WITH_LIMITATIONS
    assert second["recovered"] is True
    assert calls == 1
    receipt = json.loads(
        (
            project / "evidence/phase-5/pilots/design-director/builder-repair-receipt.json"
        ).read_text()
    )
    assert (
        receipt["parent_artifact_digest"]
        == json.loads(
            (
                project / "evidence/phase-5/pilots/design-director/builder-invocation-receipt.json"
            ).read_text()
        )["artifact_digest"]
    )


def test_repair_blocked_route_never_calls_host(tmp_path, monkeypatch) -> None:
    project = _project(tmp_path)
    _seed_v1(project)
    preflight = _preflight(project)
    monkeypatch.setattr(cli, "_preflight", lambda *_args: preflight)
    monkeypatch.setattr(
        cli,
        "_preflight_route",
        lambda *_args, **_kwargs: {"status": Phase5Status.BLOCKED, "blockers": ("NOPE",)},
    )
    monkeypatch.setattr(
        cli, "invoke_host_builder", lambda *_args, **_kwargs: pytest.fail("host called")
    )
    arguments = argparse.Namespace(
        task=None,
        policy=None,
        evidence_dir=None,
        confirm_fingerprint=HOST_DIGEST,
        correction="Apply the bounded mobile header correction.",
    )
    result = cli._repair(project, arguments)
    assert result["status"] == Phase5Status.BLOCKED
    receipt = json.loads(
        (
            project / "evidence/phase-5/pilots/design-director/builder-repair-receipt.json"
        ).read_text()
    )
    assert receipt["attempt_count"] == 0
