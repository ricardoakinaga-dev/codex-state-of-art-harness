from __future__ import annotations

import json
import struct
from pathlib import Path

from phase5_support import make_task, valid_html

from harness_kernel.phase5_artifacts import extract_response_artifact, materialize_response_artifact
from harness_kernel.phase5_models import Phase5Status, RenderRecord
from harness_kernel.phase5_verification import (
    build_structural_verification,
    parse_blind_critique,
    png_dimensions,
)


def _png(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)


def test_structural_verifier_checks_html_copy_sections_and_render_bindings(tmp_path) -> None:
    task = make_task(tmp_path)
    artifact = materialize_response_artifact(
        extract_response_artifact(
            json.dumps({"artifact_filename": "index.html", "artifact_html": valid_html()})
        ),
        task,
        version="artifact_v1",
        artifact_id="ART-P5-V1",
        invocation_id="INV-P5-1",
    )
    desktop = Path(task.workspace) / "desktop.png"
    mobile = Path(task.workspace) / "mobile.png"
    desktop.write_bytes(_png(1440, 900))
    mobile.write_bytes(_png(390, 844))
    renders = (
        RenderRecord.from_file(
            "render-desktop", "artifact_v1", desktop, (1440, 900), root=Path(task.workspace)
        ),
        RenderRecord.from_file(
            "render-mobile", "artifact_v1", mobile, (390, 844), root=Path(task.workspace)
        ),
    )
    result = build_structural_verification(task, artifact, renders=renders)
    assert result.status == Phase5Status.PASS
    assert result.artifact_digest == artifact.digest
    assert result.render_refs == ("render-desktop", "render-mobile")


def test_structural_verifier_rejects_console_network_and_missing_render(tmp_path) -> None:
    task = make_task(tmp_path)
    html = valid_html().replace("Northline", "placeholder")
    artifact = materialize_response_artifact(
        extract_response_artifact(
            json.dumps({"artifact_filename": "index.html", "artifact_html": html})
        ),
        task,
        version="artifact_v1",
        artifact_id="ART-P5-V1",
        invocation_id="INV-P5-1",
    )
    result = build_structural_verification(
        task,
        artifact,
        renders=(),
        console_errors=("uncaught exception",),
        network_failures=("https://remote.invalid",),
    )
    assert result.status in {Phase5Status.FAIL, Phase5Status.BLOCKED}
    assert any(f.severity.value in {"CRITICAL", "HIGH"} for f in result.findings)


def test_blind_critique_parser_rejects_builder_rationale_and_binds_packet() -> None:
    packet = {
        "benchmark_id": "P5-DESIGN-1",
        "run_id": "RUN-P5-1",
        "inspection_id": "INS-P5-1",
        "artifact_digest": "sha256:" + "1" * 64,
        "artifact": ["artifact_v1/index.html", "desktop.png", "mobile.png"],
        "acceptance_criteria": ["hero is product-specific"],
        "builder_rationale_withheld": True,
        "self_score_withheld": True,
        "blinded": True,
        "packet_digest": "sha256:" + "2" * 64,
        "independence": "INDEPENDENT",
        "verdict": "CONDITIONAL PASS",
        "overall_score": 84.0,
        "evidence_confidence": "HIGH",
        "dimension_scores": {"PRODUCT_SPECIFICITY": 8.0},
        "findings": [],
        "top_corrections": [],
        "evidence_missing": [],
    }
    critique = parse_blind_critique(packet, packet_digest="sha256:" + "2" * 64)
    assert critique.blinded is True
    assert critique.is_independent is True
    bad = dict(packet)
    bad["builder_rationale_withheld"] = False
    assert (
        parse_blind_critique(bad, packet_digest="sha256:" + "2" * 64).verdict
        == Phase5Status.BLOCKED
    )


def test_png_dimensions_require_a_native_capture_header(tmp_path) -> None:
    path = tmp_path / "render.png"
    path.write_bytes(_png(390, 844))
    assert png_dimensions(path) == (390, 844)
