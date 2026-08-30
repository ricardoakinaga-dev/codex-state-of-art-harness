from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from test_phase6_models import ARTIFACT_DIGEST, make_input

from harness_kernel.phase6_checks import (
    Phase6CheckError,
    check_artifact,
    confined_file_exists,
    run_deterministic_procedure,
    validate_procedure_spec,
)
from harness_kernel.phase6_models import (
    ArtifactRef,
    ProcedureSpec,
    VerificationRole,
    VerificationStatus,
)


def test_artifact_check_is_read_only_bounded_and_deterministic(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    artifact_path = verification_input.artifact_refs[0].path
    content = b"<main>current artifact</main>"
    with open(artifact_path, "wb") as handle:
        handle.write(content)
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    object.__setattr__(verification_input.artifact_refs[0], "digest", digest)

    with open(artifact_path, "rb") as handle:
        before = handle.read()
    result = check_artifact(verification_input, "ART-1")
    with open(artifact_path, "rb") as handle:
        after = handle.read()
    assert result.status is VerificationStatus.PASS
    assert result.executed is True
    assert result.evidence
    assert before == after == content


def test_deterministic_procedure_rejects_shell_network_and_mutation(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    bad_specs = (
        ProcedureSpec(
            procedure_id="PROC-SHELL",
            criterion_id="C-1",
            description="run shell",
            check="shell",
        ),
        ProcedureSpec(
            procedure_id="PROC-NET",
            criterion_id="C-1",
            description="fetch URL",
            check="network",
        ),
        ProcedureSpec(
            procedure_id="PROC-WRITE",
            criterion_id="C-1",
            description="write result",
            read_only=False,
        ),
    )
    for spec in bad_specs:
        with pytest.raises(ValueError):
            validate_procedure_spec(spec, verification_input)


def test_missing_or_mismatched_artifact_is_never_a_pass(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    missing = check_artifact(verification_input, "ART-1")
    assert missing.status in {VerificationStatus.BLOCKED, VerificationStatus.FAIL}
    assert missing.executed is True

    spec = ProcedureSpec(
        procedure_id="PROC-1",
        criterion_id="C-1",
        description="check the declared artifact",
        check="FILE_DIGEST",
        parameters={"artifact_id": "ART-1", "expected_digest": ARTIFACT_DIGEST},
    )
    result = run_deterministic_procedure(verification_input, spec)
    assert result.status in {VerificationStatus.BLOCKED, VerificationStatus.FAIL}
    assert result.status is not VerificationStatus.PASS


def test_artifact_symlink_swap_is_blocked_at_read_time(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    outside = tmp_path / "outside.html"
    outside.write_text("<!doctype html><main>outside</main>", encoding="utf-8")
    artifact_path = verification_input.artifact_refs[0].path
    os.symlink(outside, artifact_path)

    result = check_artifact(verification_input, "ART-1", criterion_id="C-1")

    assert result.status is VerificationStatus.BLOCKED
    assert result.error


def test_artifact_hardlink_alias_is_blocked_at_read_time(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    outside = tmp_path / "outside.html"
    outside.write_text("<!doctype html><main>outside</main>", encoding="utf-8")
    artifact_path = verification_input.artifact_refs[0].path
    try:
        os.link(outside, artifact_path)
    except OSError as exc:
        pytest.skip(f"hardlinks unavailable in test workspace: {exc}")

    result = check_artifact(verification_input, "ART-1", criterion_id="C-1")

    assert result.status is VerificationStatus.BLOCKED
    assert result.error


def test_text_absent_returns_current_evidence_when_forbidden_text_is_missing(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    artifact_path = verification_input.artifact_refs[0].path
    content = b"<main>safe artifact</main>"
    with open(artifact_path, "wb") as handle:
        handle.write(content)
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    object.__setattr__(verification_input.artifact_refs[0], "digest", digest)
    spec = ProcedureSpec(
        procedure_id="PROC-ABSENT",
        criterion_id="C-1",
        description="reject forbidden placeholder text",
        check="TEXT_ABSENT",
        parameters={"artifact_id": "ART-1", "text": "placeholder"},
    )

    result = run_deterministic_procedure(verification_input, spec)

    assert result.status is VerificationStatus.PASS
    assert result.evidence
    assert result.evidence[0].observation == "declared text absent: True"


def test_path_exists_uses_confined_descriptor_metadata(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    artifact_path = verification_input.artifact_refs[0].path
    with open(artifact_path, "wb") as handle:
        handle.write(b"safe")
    object.__setattr__(
        verification_input.artifact_refs[0],
        "digest",
        "sha256:" + hashlib.sha256(b"safe").hexdigest(),
    )
    spec = ProcedureSpec(
        procedure_id="PROC-EXISTS",
        criterion_id="C-1",
        description="check regular-file existence",
        check="PATH_EXISTS",
        parameters={"artifact_id": "ART-1"},
    )

    result = run_deterministic_procedure(verification_input, spec)

    assert result.status is VerificationStatus.PASS
    assert confined_file_exists(artifact_path, verification_input.workspace) is True
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    os.unlink(artifact_path)
    os.symlink(outside, artifact_path)
    assert confined_file_exists(artifact_path, verification_input.workspace) is False


def test_json_and_unknown_procedures_are_fail_closed(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    artifact_path = verification_input.artifact_refs[0].path
    artifact_path_obj = Path(artifact_path)
    artifact_path_obj.write_text('{"ok": true}', encoding="utf-8")
    object.__setattr__(
        verification_input.artifact_refs[0],
        "digest",
        "sha256:" + hashlib.sha256(artifact_path_obj.read_bytes()).hexdigest(),
    )
    json_spec = ProcedureSpec(
        procedure_id="PROC-JSON",
        criterion_id="C-1",
        description="check JSON object",
        check="JSON_OBJECT",
        parameters={"artifact_id": "ART-1"},
    )
    unknown_spec = ProcedureSpec(
        procedure_id="PROC-UNKNOWN",
        criterion_id="C-1",
        description="check unsupported vocabulary",
        check="UNSUPPORTED_CHECK",
    )

    assert (
        run_deterministic_procedure(verification_input, json_spec).status is VerificationStatus.PASS
    )
    with pytest.raises(Phase6CheckError):
        run_deterministic_procedure(verification_input, unknown_spec)

    artifact_path_obj.write_text('{"value": NaN}', encoding="utf-8")
    nan_digest = "sha256:" + hashlib.sha256(artifact_path_obj.read_bytes()).hexdigest()
    nan_input = replace(
        verification_input,
        artifact_refs=(replace(verification_input.artifact_refs[0], digest=nan_digest),),
        evidence_refs=(),
        digest="",
    )

    assert run_deterministic_procedure(nan_input, json_spec).status is VerificationStatus.FAIL


def test_text_procedure_blocks_a_stale_declared_artifact_digest(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    artifact_path = Path(verification_input.artifact_refs[0].path)
    artifact_path.write_text("current marker", encoding="utf-8")
    procedure = ProcedureSpec(
        procedure_id="PROC-TEXT-DIGEST",
        criterion_id="C-1",
        description="check text on a bound artifact",
        check="TEXT_CONTAINS",
        parameters={"artifact_id": "ART-1", "text": "current"},
    )

    result = run_deterministic_procedure(verification_input, procedure)

    assert result.status is VerificationStatus.BLOCKED
    assert result.status is not VerificationStatus.PASS


def test_browser_capture_reopens_and_rehashes_confined_files(tmp_path) -> None:
    base_input = make_input(tmp_path, criteria=("browser",))
    workspace = Path(base_input.workspace)
    browser_dir = workspace / "browser"
    browser_dir.mkdir()
    source_path = workspace / "source.html"
    desktop_path = browser_dir / "desktop.jpg"
    mobile_path = browser_dir / "mobile.jpg"
    source_path.write_text("<!doctype html><main>safe</main>", encoding="utf-8")
    desktop_path.write_bytes(b"desktop-render")
    mobile_path.write_bytes(b"mobile-render")

    def digest(path: Path) -> str:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    package_digest = base_input.package_digest
    source = ArtifactRef(
        artifact_id="ART-SOURCE",
        path=str(source_path),
        digest=digest(source_path),
        size_bytes=source_path.stat().st_size,
        package_digest=package_digest,
        producer_id="design-director",
        producer_role=VerificationRole.DESIGN_DIRECTOR,
    )
    desktop = ArtifactRef(
        artifact_id="ART-DESKTOP",
        path=str(desktop_path),
        digest=digest(desktop_path),
        size_bytes=desktop_path.stat().st_size,
        package_digest=package_digest,
        producer_id="browser-capture",
        producer_role=VerificationRole.DESIGN_DIRECTOR,
    )
    mobile = ArtifactRef(
        artifact_id="ART-MOBILE",
        path=str(mobile_path),
        digest=digest(mobile_path),
        size_bytes=mobile_path.stat().st_size,
        package_digest=package_digest,
        producer_id="browser-capture",
        producer_role=VerificationRole.DESIGN_DIRECTOR,
    )
    capture_manifest_path = browser_dir / "browser-capture-manifest.json"
    capture_payload = {
        "schema_version": "P6-BROWSER-CAPTURE-1",
        "task_id": base_input.task_id,
        "run_id": base_input.run_id,
        "criteria_digest": "sha256:" + "5" * 64,
        "artifact_id": source.artifact_id,
        "artifact_version": source.version,
        "url": "http://127.0.0.1:8765/artifacts/source.html",
        "browser": {
            "url": "http://127.0.0.1:8765/artifacts/source.html",
            "task_id": base_input.task_id,
            "run_id": base_input.run_id,
            "criteria_digest": "sha256:" + "5" * 64,
            "artifact_id": source.artifact_id,
            "artifact_version": source.version,
        },
        "source": {
            "path": source.path,
            "bytes": source.size_bytes,
            "digest": source.digest,
            "served_bytes": source.size_bytes,
            "served_digest": source.digest,
            "served_matches_declared": True,
        },
        "captures": [
            {
                "path": desktop.path,
                "bytes": desktop.size_bytes,
                "digest": desktop.digest,
            },
            {
                "path": mobile.path,
                "bytes": mobile.size_bytes,
                "digest": mobile.digest,
            },
        ],
    }
    capture_manifest_path.write_text(json.dumps(capture_payload), encoding="utf-8")
    manifest = ArtifactRef(
        artifact_id="ART-MANIFEST",
        path=str(capture_manifest_path),
        digest=digest(capture_manifest_path),
        size_bytes=capture_manifest_path.stat().st_size,
        package_digest=package_digest,
        producer_id="browser-capture",
        producer_role=VerificationRole.DESIGN_DIRECTOR,
    )
    verification_input = replace(
        base_input,
        artifact_refs=(source, desktop, mobile, manifest),
        evidence_refs=(),
        digest="",
    )
    procedure = ProcedureSpec(
        procedure_id="PROC-BROWSER",
        criterion_id="browser",
        description="bind local browser renders",
        check="BROWSER_CAPTURE",
        parameters={
            "source_artifact_id": source.artifact_id,
            "desktop_artifact_id": desktop.artifact_id,
            "mobile_artifact_id": mobile.artifact_id,
            "task_id": verification_input.task_id,
            "run_id": verification_input.run_id,
            "criteria_digest": capture_payload["criteria_digest"],
            "artifact_id": manifest.artifact_id,
            "expected_digest": manifest.digest,
            "source_artifact_digest": source.digest,
            "desktop_digest": desktop.digest,
            "mobile_digest": mobile.digest,
        },
    )

    result = run_deterministic_procedure(verification_input, procedure)

    assert result.status is VerificationStatus.PASS
    assert result.evidence

    capture_payload["captures"][0]["path"] = str(tmp_path / "outside.jpg")
    (tmp_path / "outside.jpg").write_bytes(desktop_path.read_bytes())
    capture_manifest_path.write_text(json.dumps(capture_payload), encoding="utf-8")
    invalid_input = replace(
        verification_input,
        artifact_refs=(
            *verification_input.artifact_refs[:-1],
            replace(
                manifest,
                digest=digest(capture_manifest_path),
                size_bytes=capture_manifest_path.stat().st_size,
            ),
        ),
        digest="",
    )
    invalid_result = run_deterministic_procedure(invalid_input, procedure)

    assert invalid_result.status is VerificationStatus.FAIL

    capture_payload["captures"][0]["path"] = desktop.path
    capture_payload["url"] = "https://example.com:443/artifacts/source.html"
    capture_payload["browser"]["url"] = capture_payload["url"]
    capture_manifest_path.write_text(json.dumps(capture_payload), encoding="utf-8")
    unsafe_url_input = replace(
        verification_input,
        artifact_refs=(
            *verification_input.artifact_refs[:-1],
            replace(
                manifest,
                digest=digest(capture_manifest_path),
                size_bytes=capture_manifest_path.stat().st_size,
            ),
        ),
        digest="",
    )

    unsafe_url_result = run_deterministic_procedure(unsafe_url_input, procedure)

    assert unsafe_url_result.status is VerificationStatus.FAIL
