from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
from phase5_support import make_task, valid_html

from harness_kernel.phase5_artifacts import extract_response_artifact, materialize_response_artifact
from harness_kernel.phase5_execution import BuilderResponse, CompositionRunner
from harness_kernel.phase5_models import Phase5Status, RenderRecord
from harness_kernel.phase5_paths import Phase5CliError, safe_project_path
from harness_kernel.phase5_pilot import load_task, public_task
from harness_kernel.phase5_verification import (
    build_structural_verification,
    make_blind_packet,
    parse_blind_critique,
)


def _png(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)


def _artifact(task, version: str = "artifact_v1"):
    return materialize_response_artifact(
        extract_response_artifact(
            json.dumps({"artifact_filename": "index.html", "artifact_html": valid_html()})
        ),
        task,
        version=version,
        artifact_id="ART-P5-V" + version[-1],
        invocation_id="INV-P5-" + version,
    )


def _renders(tmp_path: Path, version: str = "artifact_v1") -> tuple[RenderRecord, ...]:
    desktop = tmp_path / f"{version}-desktop.png"
    mobile = tmp_path / f"{version}-mobile.png"
    desktop.write_bytes(_png(1440, 900))
    mobile.write_bytes(_png(390, 844))
    return (
        RenderRecord.from_file(
            f"render-desktop-{version}", version, desktop, (1440, 900), root=tmp_path
        ),
        RenderRecord.from_file(
            f"render-mobile-{version}", version, mobile, (390, 844), root=tmp_path
        ),
    )


def _browser_observations() -> tuple[dict[str, object], ...]:
    landmarks = [
        {"tag": "header", "count": 1},
        {"tag": "main", "count": 1},
        {"tag": "footer", "count": 1},
    ]
    return (
        {
            "viewport": {"width": 1440, "height": 900},
            "document_width": 1440,
            "viewport_width": 1440,
            "body_height": 900,
            "h1_count": 1,
            "landmarks": landmarks,
            "focusable_count": 1,
            "external_resources": [],
        },
        {
            "viewport": {"width": 390, "height": 844},
            "document_width": 390,
            "viewport_width": 390,
            "body_height": 900,
            "h1_count": 1,
            "landmarks": landmarks,
            "focusable_count": 1,
            "external_resources": [],
        },
    )


def _verifier(_task, artifact, *, version):
    from harness_kernel.phase5_models import StructuralVerification

    return StructuralVerification(
        "VER-HARDENING",
        version,
        artifact.digest,
        Phase5Status.PASS,
        ("test_verifier",),
        (),
        (),
    )


def test_public_task_serialization_is_revalidatable(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    payload = public_task(task)
    assert payload["schema_version"] == "P5-TASK-1"
    assert payload["task_id"] == task.task_id


def test_task_loader_rejects_workspace_outside_bound_project(tmp_path: Path) -> None:
    source = Path(__file__).parents[1] / "fixtures/phase5/design-pilot/task.json"
    task_path = tmp_path / "task.json"
    task_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError):
        load_task(task_path, project_root=tmp_path / "different-project")


def test_render_record_rejects_symlink_before_read(tmp_path: Path) -> None:
    real = tmp_path / "real.png"
    link = tmp_path / "render.png"
    real.write_bytes(_png(390, 844))
    link.symlink_to(real)
    with pytest.raises(ValueError):
        RenderRecord.from_file("render", "artifact_v1", link, (390, 844), root=tmp_path)


def test_project_path_rejects_symlink_before_resolution(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    link = tmp_path / "link.json"
    real.write_text("{}", encoding="utf-8")
    link.symlink_to(real)
    with pytest.raises(Phase5CliError):
        safe_project_path(tmp_path, link, "fixture", must_exist=True)


def test_structural_verifier_requires_native_browser_observations_when_requested(
    tmp_path: Path,
) -> None:
    task = make_task(tmp_path)
    artifact = _artifact(task)
    result = build_structural_verification(
        task,
        artifact,
        renders=_renders(tmp_path),
        render_root=tmp_path,
        require_browser_observations=True,
    )
    assert result.status == Phase5Status.FAIL
    assert any(item.finding_id == "S-BROWSER-EVIDENCE-MISSING" for item in result.findings)


def test_structural_verifier_records_browser_safety_checks(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    artifact = _artifact(task)
    result = build_structural_verification(
        task,
        artifact,
        renders=_renders(tmp_path),
        render_root=tmp_path,
        browser_observations=_browser_observations(),
        require_browser_observations=True,
    )
    assert result.status == Phase5Status.PASS
    assert {
        "browser_loadability",
        "browser_overflow",
        "browser_accessibility",
        "browser_confinement",
    }.issubset(result.checks)


def test_structural_verifier_binds_renders_to_the_declared_evidence_root(
    tmp_path: Path,
) -> None:
    task = make_task(tmp_path)
    artifact = _artifact(task)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png(1440, 900))
    forged = RenderRecord.from_file(
        "render-outside",
        "artifact_v1",
        outside,
        (1440, 900),
        root=tmp_path,
    )
    result = build_structural_verification(
        task,
        artifact,
        renders=(forged,),
        render_root=evidence_root,
    )
    assert any(item.finding_id == "S-RENDER-INVALID" for item in result.findings)


def test_runner_does_not_spend_a_third_builder_call_on_repair(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    calls: list[int] = []

    def builder(_task, attempt):
        calls.append(attempt)
        if attempt == 1:
            return BuilderResponse(
                Phase5Status.PASS,
                "INV-P5-BAD",
                "not-json",
                True,
                "HOST_LOAD_UNOBSERVABLE",
            )
        return BuilderResponse(
            Phase5Status.PASS,
            "INV-P5-GOOD",
            json.dumps({"artifact_filename": "index.html", "artifact_html": valid_html()}),
            True,
            "HOST_LOAD_UNOBSERVABLE",
        )

    def critic(packet):
        return {
            "benchmark_id": packet.benchmark_id,
            "run_id": packet.run_id,
            "inspection_id": "INS-P5-BUDGET",
            "artifact_digest": packet.artifact.digest,
            "packet_digest": packet.packet_digest,
            "independence": "INDEPENDENT",
            "blinded": True,
            "builder_rationale_withheld": True,
            "self_score_withheld": True,
            "verdict": "FAIL",
            "findings": [
                {
                    "id": "F-BUDGET",
                    "location": "hero",
                    "expected": "specific visual",
                    "observed": "generic visual",
                    "severity": "HIGH",
                    "status": "OPEN",
                }
            ],
            "top_corrections": ["Fix the visual"],
        }

    result = CompositionRunner().run(
        task,
        builder=builder,
        critic=critic,
        verifier=_verifier,
    )
    assert calls == [1, 2]
    assert result.receipt.builder_invocations == 2
    assert result.receipt.repair_invocations == 0


def test_runner_blocks_success_without_a_structural_verifier(tmp_path: Path) -> None:
    task = make_task(tmp_path)

    def builder(_task, _attempt):
        return BuilderResponse(
            Phase5Status.PASS,
            "INV-P5-NO-VERIFIER",
            json.dumps({"artifact_filename": "index.html", "artifact_html": valid_html()}),
            True,
            "HOST_LOAD_UNOBSERVABLE",
        )

    result = CompositionRunner().run(
        task,
        builder=builder,
        critic=lambda _packet: {"verdict": "PASS"},
    )
    assert result.status == Phase5Status.BLOCKED
    assert result.assurance.support_level == "NONE"


def test_runner_marks_failed_repair_as_fail(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    calls = 0

    def builder(_task, _attempt):
        nonlocal calls
        calls += 1
        if calls == 1:
            return BuilderResponse(
                Phase5Status.PASS,
                "INV-P5-V1",
                json.dumps({"artifact_filename": "index.html", "artifact_html": valid_html()}),
                True,
                "HOST_LOAD_UNOBSERVABLE",
            )
        return BuilderResponse(
            Phase5Status.BLOCKED,
            "INV-P5-REPAIR-BLOCKED",
            None,
            False,
            "UNAVAILABLE",
            "REPAIR_BLOCKED",
        )

    def repair_builder(_task, _attempt, _correction):
        return BuilderResponse(
            Phase5Status.BLOCKED,
            "INV-P5-REPAIR-BLOCKED",
            None,
            False,
            "UNAVAILABLE",
            "REPAIR_BLOCKED",
        )

    def critic(packet):
        return {
            "benchmark_id": packet.benchmark_id,
            "run_id": packet.run_id,
            "inspection_id": "INS-P5-REPAIR",
            "artifact_digest": packet.artifact.digest,
            "packet_digest": packet.packet_digest,
            "independence": "INDEPENDENT",
            "blinded": True,
            "builder_rationale_withheld": True,
            "self_score_withheld": True,
            "verdict": "FAIL",
            "findings": [
                {
                    "id": "F-REPAIR",
                    "location": "hero",
                    "expected": "specific visual",
                    "observed": "generic visual",
                    "severity": "MEDIUM",
                    "status": "OPEN",
                }
            ],
            "top_corrections": ["Fix the visual"],
        }

    result = CompositionRunner().run(
        task,
        builder=builder,
        repair_builder=repair_builder,
        critic=critic,
        verifier=_verifier,
    )
    assert calls == 1
    assert result.status == Phase5Status.FAIL


def test_blind_critique_rejects_a_mismatched_bound_packet() -> None:
    with pytest.raises(ValueError):
        parse_blind_critique(
            {
                "packet_digest": "sha256:" + "1" * 64,
                "artifact_digest": "sha256:" + "2" * 64,
                "independence": "INDEPENDENT",
                "blinded": True,
                "builder_rationale_withheld": True,
                "self_score_withheld": True,
                "verdict": "PASS",
                "findings": [],
            },
            packet_digest="sha256:" + "3" * 64,
            require_packet_digest=True,
        )


def test_blind_critique_requires_explicit_safety_flags() -> None:
    with pytest.raises(ValueError):
        parse_blind_critique(
            {
                "packet_digest": "sha256:" + "1" * 64,
                "artifact_digest": "sha256:" + "2" * 64,
                "independence": "INDEPENDENT",
                "verdict": "PASS",
                "findings": [],
            },
            packet_digest="sha256:" + "1" * 64,
            require_packet_digest=True,
        )


def test_response_artifact_rejects_protocol_relative_and_css_external_refs() -> None:
    for html in (
        "<!doctype html><html><body><link href='//remote.invalid/style.css'></body></html>",
        (
            "<!doctype html><html><head><style>"
            "body{background:url('//remote.invalid/x')}"
            "</style></head><body></body></html>"
        ),
        "<!doctype html><html><body><link href='/remote.css'></body></html>",
        (
            "<!doctype html><html><head><style>"
            "body{background:url('/remote.png')}"
            "</style></head><body></body></html>"
        ),
    ):
        with pytest.raises(ValueError):
            extract_response_artifact(
                json.dumps({"artifact_filename": "index.html", "artifact_html": html})
            )


def test_blind_packet_digest_binds_render_content(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    artifact = _artifact(task)
    renders = _renders(tmp_path)
    first = make_blind_packet(task, artifact, renders)
    desktop = tmp_path / "artifact_v1-desktop.png"
    desktop.write_bytes(_png(1440, 900) + b"changed")
    changed_renders = (
        RenderRecord.from_file(
            "render-desktop-artifact_v1",
            "artifact_v1",
            desktop,
            (1440, 900),
            root=tmp_path,
        ),
        renders[1],
    )
    second = make_blind_packet(task, artifact, changed_renders)
    assert first.packet_digest != second.packet_digest
