from __future__ import annotations

from pathlib import Path

import pytest
from phase5_support import make_fingerprint, make_task

from harness_kernel.phase5_models import (
    ArtifactPacket,
    CapabilityFingerprint,
    EligibilityReport,
    Phase5Role,
    Phase5Status,
    RenderRecord,
    VisualCritique,
    public_data,
)

DIGEST = "sha256:" + "a" * 64


def _artifact_kwargs(task, *, version: str = "artifact_v1", path: str | None = None):
    return {
        "artifact_id": "ART-P72",
        "version": version,
        "path": path or str(Path(task.artifact_root) / version / "index.html"),
        "digest": DIGEST,
        "size_bytes": 1,
        "producer_capability": "design-director",
        "invocation_id": "INV-P72",
        "task_id": task.task_id,
        "acceptance_digest": task.criteria.digest,
        "source_kind": "HOST_RESPONSE_DERIVED",
    }


def test_phase5_model_digest_and_path_contracts_fail_closed(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    with pytest.raises(ValueError, match="digest"):
        ArtifactPacket(**{**_artifact_kwargs(task), "digest": "not-a-digest"})
    with pytest.raises(ValueError, match="absolute"):
        ArtifactPacket(**_artifact_kwargs(task, path="relative/index.html"))
    with pytest.raises(ValueError, match="version"):
        ArtifactPacket(**_artifact_kwargs(task, version="artifact_v3"))


def test_phase5_fingerprint_and_script_metadata_types_are_strict(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    kwargs = {
        "capability_id": "design-director",
        "version": "0.1.0",
        "scope": "PROJECT",
        "canonical_path": str(package),
        "package_fingerprint": DIGEST,
        "manifest_fingerprint": DIGEST,
        "provenance": "LOCAL",
        "trust": "TRUSTED",
        "compatibility": "COMPATIBLE",
        "package_status": "INSPECTED",
        "load_eligibility": "ELIGIBLE",
        "files": (),
        "scripts": (),
        "dependencies": (),
    }
    with pytest.raises(ValueError, match="manifest_fingerprint"):
        CapabilityFingerprint(**{**kwargs, "manifest_fingerprint": "bad"})
    with pytest.raises(ValueError, match="scripts_metadata_only"):
        CapabilityFingerprint(**{**kwargs, "scripts_metadata_only": 1})
    fingerprint_without_manifest = CapabilityFingerprint(**{**kwargs, "manifest_fingerprint": None})
    assert fingerprint_without_manifest.manifest_fingerprint is None


def test_phase5_eligibility_and_visual_critique_state_contracts(tmp_path: Path) -> None:
    fingerprint = make_fingerprint(tmp_path)
    with pytest.raises(ValueError, match="blockers"):
        EligibilityReport(
            capability_id="design-director",
            role=Phase5Role.DESIGN_BUILDER,
            status=Phase5Status.PASS,
            route="eligible",
            fingerprint=fingerprint,
            reasons=(),
            blockers=("STALE",),
            inspected_files=(),
            evaluated_at=1,
        )
    with pytest.raises(ValueError, match="blocked critic"):
        VisualCritique(
            benchmark_id="BENCH-P72",
            run_id="RUN-P72",
            inspection_id="INS-P72",
            artifact_digest=DIGEST,
            independence="BLOCKED",
            blinded=True,
            builder_rationale_withheld=True,
            self_score_withheld=True,
            packet_digest=DIGEST,
            verdict=Phase5Status.PASS,
            overall_score=None,
            evidence_confidence="LOW",
            dimension_scores={},
            findings=(),
            top_corrections=(),
            evidence_missing=(),
        )


def test_phase5_render_records_validate_version_and_absolute_inputs(tmp_path: Path) -> None:
    render = tmp_path / "render.png"
    render.write_bytes(b"png")
    with pytest.raises(ValueError, match="absolute"):
        RenderRecord.from_file("R", "artifact_v1", "render.png", (1, 1), root=tmp_path)
    with pytest.raises(ValueError, match="version"):
        RenderRecord(
            render_id="R",
            artifact_version="artifact_v3",
            path=str(render),
            viewport=(1, 1),
            digest=DIGEST,
            size_bytes=1,
        )


def test_phase5_public_data_serializes_paths_without_exposing_objects(tmp_path: Path) -> None:
    assert public_data(tmp_path / "evidence.json") == str(tmp_path / "evidence.json")
