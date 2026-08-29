from __future__ import annotations

import json

import pytest
from phase5_support import make_task, valid_html

from harness_kernel.phase5_artifacts import (
    ArtifactCaptureError,
    extract_response_artifact,
    materialize_response_artifact,
    validate_artifact_path,
)


def _envelope(html: str, filename: str = "index.html") -> str:
    return json.dumps({"artifact_filename": filename, "artifact_html": html})


def test_extract_response_artifact_requires_one_bounded_html_envelope() -> None:
    artifact = extract_response_artifact(_envelope(valid_html()))
    assert artifact.filename == "index.html"
    assert artifact.html.startswith("<!doctype html>")
    with pytest.raises(ArtifactCaptureError):
        extract_response_artifact("```html\n" + valid_html() + "\n```")
    with pytest.raises(ArtifactCaptureError):
        extract_response_artifact(_envelope("<html><script>alert(1)</script></html>"))


def test_artifact_rejects_remote_urls_traversal_and_oversized_output() -> None:
    with pytest.raises(ArtifactCaptureError):
        extract_response_artifact(_envelope("<html><img src='https://remote.invalid/x'></html>"))
    with pytest.raises(ArtifactCaptureError):
        extract_response_artifact(_envelope(valid_html(), "../escape.html"))
    with pytest.raises(ArtifactCaptureError):
        extract_response_artifact(_envelope("<!doctype html>" + "x" * 200_000))


def test_materialize_is_confined_and_has_stable_lineage(tmp_path) -> None:
    task = make_task(tmp_path)
    extracted = extract_response_artifact(_envelope(valid_html()))
    packet = materialize_response_artifact(
        extracted,
        task,
        version="artifact_v1",
        artifact_id="ART-P5-V1",
        invocation_id="INV-P5-1",
    )
    assert packet.path.startswith(task.artifact_root)
    assert packet.version == "artifact_v1"
    assert packet.size_bytes > 100
    assert packet.path.endswith("artifact_v1/index.html")
    assert validate_artifact_path(packet.path, task.workspace) == packet.path
    with pytest.raises(ArtifactCaptureError):
        validate_artifact_path("/tmp/outside.html", task.workspace)
