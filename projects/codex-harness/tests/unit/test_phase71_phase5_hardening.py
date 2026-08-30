from __future__ import annotations

import argparse
import json
import shutil
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from phase5_support import (
    HOST_DIGEST,
    MANIFEST_DIGEST,
    PACKAGE_DIGEST,
    make_fingerprint,
    make_task,
    valid_html,
)

import harness_kernel.phase5_artifacts as artifacts_module
import harness_kernel.phase5_execution as execution_module
import harness_kernel.phase5_finalization as finalization_module
import harness_kernel.phase5_verification as verification_module
from harness_kernel.phase4_artifacts import ArtifactCaptureError as Phase4ArtifactCaptureError
from harness_kernel.phase4_evidence import EvidenceWriter
from harness_kernel.phase4_models import (
    HostInvocationResult,
    HostLoadObservation,
    HostPreparation,
    InvocationResultStatus,
)
from harness_kernel.phase5_artifacts import (
    ArtifactCaptureError,
    ResponseArtifact,
    artifact_is_stale,
    artifact_public_data,
    extract_response_artifact,
    materialize_response_artifact,
    validate_artifact_path,
)
from harness_kernel.phase5_execution import BuilderResponse, CompositionRunner
from harness_kernel.phase5_finalization import (
    artifact_from_receipt,
    finalize,
    needs_repair,
    prepare_review,
    render_records,
    validate_receipt_binding,
    version_suffix,
)
from harness_kernel.phase5_models import (
    FIXED_GRAPH,
    ArtifactPacket,
    Finding,
    FindingSeverity,
    Phase5Budget,
    Phase5Role,
    Phase5Status,
    RenderRecord,
    StructuralVerification,
    VisualCritique,
)
from harness_kernel.phase5_paths import Phase5CliError
from harness_kernel.phase5_pilot import load_task, write_public_json
from harness_kernel.phase5_policy import (
    Phase5Allowlist,
    Phase5PolicyError,
    build_builder_request,
    build_fingerprint,
    evaluate_eligibility,
)
from harness_kernel.phase5_verification import (
    build_structural_verification,
    make_blind_packet,
    parse_blind_critique,
    png_dimensions,
)

ZERO_DIGEST = "sha256:" + "0" * 64
RECEIPT_PACKAGE = "sha256:" + "1" * 64
RECEIPT_MANIFEST = "sha256:" + "2" * 64
RECEIPT_CONTEXT = "sha256:" + "3" * 64


def _envelope(html: str = valid_html(), filename: str = "index.html") -> str:
    return json.dumps({"artifact_filename": filename, "artifact_html": html})


def _png(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)


def _artifact(
    task,
    *,
    version: str = "artifact_v1",
    html: str | None = None,
    invocation_id: str = "INV-P5-HARDENING",
    parent_artifact_digest: str | None = None,
) -> ArtifactPacket:
    content = valid_html() if html is None else html
    response = extract_response_artifact(_envelope(content))
    return materialize_response_artifact(
        response,
        task,
        version=version,
        artifact_id="ART-P5-V" + version[-1],
        invocation_id=invocation_id,
        parent_artifact_digest=parent_artifact_digest,
    )


def _raw_artifact(task, html: str, *, version: str = "artifact_v1") -> ArtifactPacket:
    path = Path(task.artifact_root) / version / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return ArtifactPacket.from_content(
        artifact_id="ART-P5-RAW-" + version[-1],
        version=version,
        path=str(path),
        content=html,
        producer_capability="design-director",
        invocation_id="INV-P5-RAW",
        task=task,
    )


def _renders(tmp_path: Path, version: str = "artifact_v1") -> tuple[RenderRecord, ...]:
    desktop = tmp_path / f"{version}-desktop.png"
    mobile = tmp_path / f"{version}-mobile.png"
    desktop.write_bytes(_png(1440, 900))
    mobile.write_bytes(_png(390, 844))
    return (
        RenderRecord.from_file(
            "render-desktop-" + version,
            version,
            desktop,
            (1440, 900),
            root=tmp_path,
            captured_at=10,
        ),
        RenderRecord.from_file(
            "render-mobile-" + version,
            version,
            mobile,
            (390, 844),
            root=tmp_path,
            captured_at=10,
        ),
    )


def _browser_observation(width: int = 1440, height: int = 900) -> dict[str, object]:
    return {
        "viewport": {"width": width, "height": height},
        "document_width": width,
        "viewport_width": width,
        "body_height": height,
        "h1_count": 1,
        "focusable_count": 1,
        "landmarks": [
            {"tag": "header", "count": 1},
            {"tag": "main", "count": 1},
            {"tag": "footer", "count": 1},
        ],
        "external_resources": [],
    }


def _browser_observations() -> tuple[dict[str, object], ...]:
    return (_browser_observation(), _browser_observation(390, 844))


def _critic(packet, *, verdict: str = "PASS", findings=(), **extra) -> dict[str, object]:
    payload: dict[str, object] = {
        "benchmark_id": packet.benchmark_id,
        "run_id": packet.run_id,
        "inspection_id": "INS-P5-HARDENING",
        "artifact_digest": packet.artifact.digest,
        "packet_digest": packet.packet_digest,
        "independence": "INDEPENDENT",
        "blinded": True,
        "builder_rationale_withheld": True,
        "self_score_withheld": True,
        "verdict": verdict,
        "findings": list(findings),
        "top_corrections": ["Fix the highest-severity finding"] if findings else [],
        "evidence_missing": [],
    }
    payload.update(extra)
    return payload


def _verifier(_task, artifact, *, version, status: Phase5Status = Phase5Status.PASS):
    return StructuralVerification(
        "VER-P5-HARDENING",
        version,
        artifact.digest,
        status,
        ("artifact_digest",),
        (),
        (),
        created_at=10,
    )


def _builder_response(
    *,
    invocation_id: str = "INV-P5-BUILDER",
    status: Phase5Status = Phase5Status.PASS,
    message: str | None = None,
    error_code: str | None = None,
) -> BuilderResponse:
    return BuilderResponse(
        status,
        invocation_id,
        _envelope() if message is None and status is Phase5Status.PASS else message,
        True,
        "HOST_LOAD_UNOBSERVABLE",
        error_code,
    )


class _Adapter:
    def __init__(
        self,
        *,
        preparation: HostPreparation | None = None,
        errors: tuple[str, ...] = (),
        result: HostInvocationResult | None = None,
        prepare_error: Exception | None = None,
        request_error: Exception | None = None,
    ) -> None:
        self.preparation = preparation or HostPreparation(True, "supported")
        self.errors = errors
        self.result = result
        self.prepare_error = prepare_error
        self.request_error = request_error
        self.requests: list[tuple[object, object, object]] = []

    def prepare_invocation(self, request):
        if self.prepare_error is not None:
            raise self.prepare_error
        return self.preparation

    def validate_invocation(self, request):
        return self.errors

    def request_invocation(self, request, *, budget, cancel_event):
        self.requests.append((request, budget, cancel_event))
        if self.request_error is not None:
            raise self.request_error
        assert self.result is not None
        return self.result


def _host_result(
    status: InvocationResultStatus,
    *,
    final_message: str | None = _envelope(),
    turn_id: str | None = "TURN-P5",
    error_code: str | None = None,
) -> HostInvocationResult:
    return HostInvocationResult(
        status=status,
        thread_id=None,
        session_id=None,
        turn_id=turn_id,
        host_version="test-host",
        events=(),
        final_message=final_message,
        load_observation=HostLoadObservation.OBSERVED,
        invocation_observed=True,
        execution_observed=True,
        denied_approvals=0,
        cancellation_status="NOT_REQUESTED",
        error_code=error_code,
        started_at=1,
        completed_at=2,
    )


def _policy_payload(fingerprint) -> dict[str, object]:
    builder = {
        "capability_id": fingerprint.capability_id,
        "version": fingerprint.version,
        "scope": fingerprint.scope,
        "canonical_path": fingerprint.canonical_path,
        "package_fingerprint": fingerprint.package_fingerprint,
        "manifest_fingerprint": fingerprint.manifest_fingerprint,
        "provenance": fingerprint.provenance,
        "trust": fingerprint.trust,
        "compatibility": fingerprint.compatibility,
        "package_status": fingerprint.package_status,
        "load_eligibility": fingerprint.load_eligibility,
        "files": list(fingerprint.files),
        "scripts": list(fingerprint.scripts),
        "dependencies": list(fingerprint.dependencies),
        "scripts_metadata_only": True,
        "status": "APPROVED_RESPONSE_ONLY",
        "execution_approved": True,
        "allowed_mode": "RESPONSE_ONLY_BUILDER",
        "allow_tools": False,
        "allow_scripts": False,
        "allow_shell": False,
        "allow_network": False,
        "allow_mcp": False,
        "allow_providers": False,
        "allow_credentials": False,
        "reason": "response-only test policy",
    }
    budget = Phase5Budget()
    budgets = {
        name: getattr(budget, name)
        for name in (
            "max_builder_invocations",
            "max_structural_verifications",
            "max_visual_critiques",
            "max_repairs",
            "max_render_versions",
            "max_artifact_bytes",
            "max_context_bytes",
            "max_evidence_records",
        )
    }
    return {
        "schema_version": "P5-POLICY-1",
        "policy_id": "phase5-hardening",
        "builder": builder,
        "secondary": {"status": "BLOCKED", "blocker": "EXTERNAL_VERIFIER_NOT_ELIGIBLE"},
        "graph": list(FIXED_GRAPH),
        "budgets": budgets,
    }


def _identity() -> dict[str, object]:
    return {
        "capability_id": "design-director",
        "capability_version": "0.1.0",
        "package_fingerprint": RECEIPT_PACKAGE,
        "manifest_fingerprint": RECEIPT_MANIFEST,
        "authorization_id": "AUTH-P5-HARDENING",
        "context_digest": RECEIPT_CONTEXT,
    }


def _finalization_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    task_path = project / "tests/fixtures/phase5/design-pilot/task.json"
    task_path.parent.mkdir(parents=True)
    (task_path.parent / "workspace/artifacts").mkdir(parents=True)
    source = Path(__file__).parents[1] / "fixtures/phase5/design-pilot/task.json"
    shutil.copyfile(source, task_path)
    return project


def _receipt(task, artifact: ArtifactPacket, *, repair: bool = False, parent: str | None = None):
    return {
        "schema_version": "P5-REPAIR-RECEIPT-1" if repair else "P5-BUILDER-RECEIPT-1",
        "task_id": task.task_id,
        "run_id": task.run_id,
        "status": "PASS",
        "attempt_count": 1,
        "attempts": [{"invocation_id": artifact.invocation_id}],
        "artifact_id": artifact.artifact_id,
        "artifact_version": artifact.version,
        "artifact_path": artifact.path,
        "artifact_digest": artifact.digest,
        "parent_artifact_digest": parent,
        "producer_capability": "design-director",
        **_identity(),
        "repair_correction": "repair" if repair else None,
    }


def _write_identity(writer: EvidenceWriter, task, *, repair: bool = False) -> None:
    write_public_json(
        writer,
        "eligibility.json",
        {
            "status": "PASS",
            "fingerprint": {
                "capability_id": "design-director",
                "version": "0.1.0",
                "package_fingerprint": RECEIPT_PACKAGE,
                "manifest_fingerprint": RECEIPT_MANIFEST,
            },
        },
    )
    prefix = "builder-repair-" if repair else "builder-"
    write_public_json(
        writer,
        prefix + "authorization.json",
        {
            "authorization_id": "AUTH-P5-HARDENING",
            "task_id": task.task_id,
            "run_id": task.run_id,
            "capability_id": "design-director",
            "capability_version": "0.1.0",
            "package_fingerprint": RECEIPT_PACKAGE,
        },
    )
    write_public_json(
        writer,
        prefix + "context-manifest.json",
        {
            "task_id": task.task_id,
            "capability_id": "design-director",
            "package_fingerprint": RECEIPT_PACKAGE,
            "digest": RECEIPT_CONTEXT,
        },
    )


def _write_render_inputs(
    project: Path,
    evidence: Path,
    artifact: ArtifactPacket,
    *,
    version: str = "artifact_v1",
) -> tuple[Path, Path, tuple[RenderRecord, ...]]:
    render_root = evidence / version.replace("_", "-")
    render_root.mkdir(parents=True, exist_ok=True)
    desktop = render_root / "desktop.png"
    mobile = render_root / "mobile.png"
    desktop.write_bytes(_png(1440, 900))
    mobile.write_bytes(_png(390, 844))
    common = {
        "artifact_version": artifact.version,
        "artifact_digest": artifact.digest,
        "capture_method": "playwright_native",
        "capture_id": "CAP-P5-HARDENING",
        "url": "http://127.0.0.1:8765/index.html",
        "browser": {
            "engine": "Chromium",
            "version": "152.0.7977.64",
            "executable": "/opt/chrome/chrome",
            "executable_digest": ZERO_DIGEST,
        },
        "document_width": 1440,
        "viewport_width": 1440,
        "body_height": 900,
        "h1_count": 1,
        "focusable_count": 1,
        "landmarks": [
            {"tag": "header", "count": 1},
            {"tag": "main", "count": 1},
            {"tag": "footer", "count": 1},
        ],
        "external_resources": [],
    }
    desktop_metrics = {**common, "viewport": {"width": 1440, "height": 900}}
    mobile_metrics = {
        **common,
        "viewport": {"width": 390, "height": 844},
        "document_width": 390,
        "viewport_width": 390,
    }
    (render_root / "desktop-metrics.json").write_text(json.dumps(desktop_metrics), encoding="utf-8")
    (render_root / "mobile-metrics.json").write_text(json.dumps(mobile_metrics), encoding="utf-8")
    return (
        desktop,
        mobile,
        render_records(project, evidence, desktop, mobile, artifact_version=version),
    )


def _finalization_args(
    desktop: Path,
    mobile: Path,
    critique: Path,
    *,
    version: str = "artifact_v1",
    console_errors: Path | None = None,
    network_failures: Path | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        task=None,
        evidence_dir=None,
        desktop=desktop,
        mobile=mobile,
        critique=critique,
        console_errors=console_errors,
        network_failures=network_failures,
        artifact_version=version,
    )


@pytest.mark.parametrize(
    ("filename", "html", "digest"),
    (
        ("wrong.html", valid_html(), ZERO_DIGEST),
        ("index.html", "", ZERO_DIGEST),
        ("index.html", "plain text", ZERO_DIGEST),
        ("index.html", valid_html(), "bad-digest"),
    ),
)
def test_response_artifact_rejects_invalid_frozen_records(filename, html, digest) -> None:
    with pytest.raises(ArtifactCaptureError):
        ResponseArtifact(filename, html, digest)


@pytest.mark.parametrize(
    "response",
    (
        None,
        "",
        "\x00",
        "not-json",
        json.dumps({"artifact_filename": "index.html", "artifact_html": valid_html(), "extra": 1}),
        json.dumps({"artifact_filename": "wrong.html", "artifact_html": valid_html()}),
        json.dumps({"artifact_filename": "index.html", "artifact_html": 7}),
    ),
)
def test_extract_response_artifact_fails_closed_on_protocol_and_shape_errors(response) -> None:
    with pytest.raises(ArtifactCaptureError):
        extract_response_artifact(response)  # type: ignore[arg-type]


def test_extract_response_artifact_distinguishes_response_and_html_bounds() -> None:
    with pytest.raises(ArtifactCaptureError, match="response exceeds"):
        extract_response_artifact(_envelope(), max_bytes=1)
    oversized_html = "<!doctype html>" + "x" * 60
    with pytest.raises(ArtifactCaptureError, match="HTML artifact"):
        extract_response_artifact(_envelope(oversized_html), max_bytes=70)


def test_artifact_path_rejects_relative_traversal_escape_and_symlink(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(ArtifactCaptureError, match="absolute"):
        validate_artifact_path("relative/index.html", workspace)
    with pytest.raises(ArtifactCaptureError, match="traversal"):
        validate_artifact_path(str(workspace / ".." / "escape.html"), workspace)
    with pytest.raises(ArtifactCaptureError, match="escapes"):
        validate_artifact_path(str(tmp_path / "escape.html"), workspace)
    target = workspace / "real.html"
    target.write_text("x", encoding="utf-8")
    link = workspace / "link.html"
    link.symlink_to(target)
    with pytest.raises(ArtifactCaptureError, match="symlinks"):
        validate_artifact_path(link, workspace)


def test_artifact_path_reports_inspection_and_resolution_failures(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    candidate = workspace / "index.html"
    original_lstat = Path.lstat

    def failing_lstat(path: Path):
        if path == candidate:
            raise OSError("permission denied")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", failing_lstat)
    with pytest.raises(ArtifactCaptureError, match="inspected"):
        validate_artifact_path(candidate, workspace)

    monkeypatch.undo()
    original_resolve = Path.resolve

    def failing_resolve(path: Path, *args, **kwargs):
        if path == candidate:
            raise RuntimeError("resolution loop")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", failing_resolve)
    with pytest.raises(ArtifactCaptureError, match="resolved"):
        validate_artifact_path(candidate, workspace)


def test_materialization_rejects_bad_record_and_preserves_atomic_failure(
    tmp_path: Path, monkeypatch
) -> None:
    task = make_task(tmp_path)
    extracted = extract_response_artifact(_envelope())
    with pytest.raises(ArtifactCaptureError, match="record"):
        materialize_response_artifact(
            object(), task, version="artifact_v1", artifact_id="ART", invocation_id="INV"
        )  # type: ignore[arg-type]

    original_open = artifacts_module._open_confined_directory
    calls = 0

    def fail_second_open(path: Path, workspace: Path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise Phase4ArtifactCaptureError("second open failed")
        return original_open(path, workspace)

    monkeypatch.setattr(artifacts_module, "_open_confined_directory", fail_second_open)
    with pytest.raises(ArtifactCaptureError, match="opened safely"):
        materialize_response_artifact(
            extracted,
            task,
            version="artifact_v1",
            artifact_id="ART-P5-OPEN",
            invocation_id="INV-P5-OPEN",
        )

    monkeypatch.undo()

    def fail_atomic(*args, **kwargs):
        raise Phase4ArtifactCaptureError("write failed")

    monkeypatch.setattr(artifacts_module, "_atomic_write_at", fail_atomic)
    with pytest.raises(ArtifactCaptureError, match="atomically"):
        materialize_response_artifact(
            extracted,
            task,
            version="artifact_v1",
            artifact_id="ART-P5-ATOMIC",
            invocation_id="INV-P5-ATOMIC",
        )


def test_materialization_and_public_projection_preserve_lineage_and_staleness(
    tmp_path: Path,
) -> None:
    task = make_task(tmp_path)
    packet = _artifact(task)
    assert artifact_is_stale(packet, packet.digest) is False
    assert artifact_is_stale(packet, ZERO_DIGEST) is True
    with pytest.raises(ArtifactCaptureError):
        artifact_is_stale(packet, "invalid")
    public = artifact_public_data(packet)
    assert public["artifact_id"] == packet.artifact_id
    assert public["parent_artifact_digest"] is None
    with pytest.raises(TypeError):
        public["artifact_id"] = "mutated"  # type: ignore[index]


@pytest.mark.parametrize(
    "kwargs",
    (
        {"status": "bad"},
        {"invocation_id": ""},
        {"invocation_id": "bad\x00id"},
        {"final_message": ""},
        {"final_message": "bad\x00message"},
        {"host_invoked": 1},
        {"load_observation": ""},
        {"error_code": ""},
        {"error_code": "bad\x00code"},
    ),
)
def test_builder_response_contract_rejects_invalid_status_and_diagnostics(kwargs) -> None:
    with pytest.raises(ValueError):
        BuilderResponse(
            status=kwargs.get("status", Phase5Status.PASS),
            invocation_id=kwargs.get("invocation_id", "INV"),
            final_message=kwargs.get("final_message", _envelope()),
            host_invoked=kwargs.get("host_invoked", True),
            load_observation=kwargs.get("load_observation", "OBSERVED"),
            error_code=kwargs.get("error_code"),
        )


@pytest.mark.parametrize(
    ("status", "message", "expected"),
    (
        (InvocationResultStatus.SUCCESS, _envelope(), Phase5Status.PASS),
        (InvocationResultStatus.SUCCESS, None, Phase5Status.FAIL),
        (InvocationResultStatus.PARTIAL, _envelope(), Phase5Status.PASS),
        (InvocationResultStatus.PARTIAL, None, Phase5Status.FAIL),
        (InvocationResultStatus.BLOCKED, _envelope(), Phase5Status.BLOCKED),
        (InvocationResultStatus.FAILURE, _envelope(), Phase5Status.FAIL),
        (InvocationResultStatus.TIMED_OUT, None, Phase5Status.FAIL),
        (InvocationResultStatus.CANCELLED, None, Phase5Status.FAIL),
        (InvocationResultStatus.UNKNOWN, None, Phase5Status.FAIL),
        (InvocationResultStatus.PREPARED, None, Phase5Status.FAIL),
    ),
)
def test_host_result_status_is_preserved_as_bounded_builder_state(
    status, message, expected
) -> None:
    response = execution_module._builder_response_from_host(
        _host_result(status, final_message=message, turn_id=None)
    )
    assert response.status is expected
    assert response.invocation_id == "INV-P5-HOST-UNKNOWN"
    assert response.host_invoked is True


def test_invoke_host_builder_failures_are_terminal_and_budget_is_forwarded(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    fingerprint = make_fingerprint(tmp_path)
    request = build_builder_request(
        task,
        fingerprint,
        host_executable_digest=HOST_DIGEST,
        host_interpreter_digest=HOST_DIGEST,
        attempt=1,
    )
    budget = Phase5Budget()

    prepared_failure = execution_module.invoke_host_builder(
        _Adapter(prepare_error=RuntimeError("prepare")), request, budget=budget
    )
    assert prepared_failure.status is Phase5Status.BLOCKED
    assert prepared_failure.error_code == "HOST_PREPARATION_FAILURE"

    unsupported = execution_module.invoke_host_builder(
        _Adapter(preparation=HostPreparation(False, "unsupported")), request, budget=budget
    )
    assert unsupported.error_code == "HOST_INVOCATION_UNSUPPORTED"

    denied = execution_module.invoke_host_builder(
        _Adapter(errors=("POLICY_DENIED",)), request, budget=budget
    )
    assert denied.error_code == "POLICY_DENIED"

    adapter_failure = execution_module.invoke_host_builder(
        _Adapter(request_error=RuntimeError("adapter")), request, budget=budget
    )
    assert adapter_failure.status is Phase5Status.FAIL
    assert adapter_failure.error_code == "HOST_ADAPTER_FAILURE"

    adapter = _Adapter(result=_host_result(InvocationResultStatus.SUCCESS))
    success = execution_module.invoke_host_builder(adapter, request, budget=budget)
    assert success.status is Phase5Status.PASS
    assert len(adapter.requests) == 1
    forwarded_budget = adapter.requests[0][1]
    assert forwarded_budget.max_context_bytes == budget.max_context_bytes
    assert forwarded_budget.max_tool_calls == 0
    assert forwarded_budget.max_output_bytes == budget.max_artifact_bytes


def test_make_host_builder_rebinds_unexpected_host_turn_id_to_authorized_request(
    tmp_path: Path,
) -> None:
    task = make_task(tmp_path)
    fingerprint = make_fingerprint(tmp_path)
    adapter = _Adapter(result=_host_result(InvocationResultStatus.SUCCESS, turn_id="HOST-TURN"))
    builder = execution_module.make_host_builder(
        adapter,
        task,
        fingerprint,
        host_executable_digest=HOST_DIGEST,
        host_interpreter_digest=HOST_DIGEST,
    )
    response = builder(task, 1)
    assert response.status is Phase5Status.PASS
    assert response.invocation_id.startswith("INV-P5-")
    assert response.invocation_id != "HOST-TURN"


def test_normalize_critic_rejects_unbound_or_nonindependent_outputs(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    artifact = _artifact(task)
    packet = make_blind_packet(task, artifact, ())
    with pytest.raises(ValueError, match="not a mapping"):
        execution_module._normalize_critic(object(), packet, 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="missing"):
        execution_module._normalize_critic({"verdict": "PASS"}, packet, 1)
    bad_task = _critic(packet)
    bad_task["run_id"] = "OTHER"
    with pytest.raises(ValueError, match="task packet"):
        execution_module._normalize_critic(bad_task, packet, 1)
    bad_artifact = _critic(packet)
    bad_artifact["artifact_digest"] = ZERO_DIGEST
    with pytest.raises(ValueError, match="artifact"):
        execution_module._normalize_critic(bad_artifact, packet, 1)
    blocked = _critic(packet)
    blocked["independence"] = "SELF"
    with pytest.raises(ValueError, match="independent"):
        execution_module._normalize_critic(blocked, packet, 1)


def test_composition_failure_paths_do_not_call_critic_or_materialize_untrusted_output(
    tmp_path: Path, monkeypatch
) -> None:
    task = make_task(tmp_path)
    critic_calls = 0

    def critic(_packet):
        nonlocal critic_calls
        critic_calls += 1
        return {}

    def invalid_builder(_task, attempt):
        return _builder_response(invocation_id=f"INV-{attempt}", message="not-json")

    result = CompositionRunner().run(
        task, builder=invalid_builder, critic=critic, verifier=_verifier
    )
    assert result.status is Phase5Status.BLOCKED
    assert result.receipt.builder_invocations == 2
    assert result.assurance.blockers == ("ARTIFACT_RESPONSE_INVALID",)
    assert critic_calls == 0
    assert not list(Path(task.artifact_root).rglob("index.html"))

    def materialize_failure(*args, **kwargs):
        raise ArtifactCaptureError("confined write failed")

    monkeypatch.setattr(execution_module, "materialize_response_artifact", materialize_failure)
    result = CompositionRunner().run(
        task,
        builder=lambda _task, _attempt: _builder_response(),
        critic=critic,
        verifier=_verifier,
    )
    assert result.status is Phase5Status.BLOCKED
    assert result.assurance.blockers == ("BUILDER_UNAVAILABLE",)
    assert critic_calls == 0


def test_composition_uses_failed_structural_verification_and_blocks_repairless_critic(
    tmp_path: Path,
) -> None:
    task = make_task(tmp_path)
    finding = {
        "id": "V-HIGH",
        "location": "hero",
        "expected": "safe CTA",
        "observed": "missing CTA",
        "severity": "HIGH",
        "status": "OPEN",
    }
    result = CompositionRunner().run(
        task,
        builder=lambda _task, _attempt: _builder_response(),
        critic=lambda packet: _critic(packet, verdict="PASS", findings=[finding]),
        verifier=lambda task, artifact, *, version: _verifier(
            task, artifact, version=version, status=Phase5Status.FAIL
        ),
        repair_builder=None,
    )
    assert result.status is Phase5Status.FAIL
    assert result.structural is not None
    assert result.final_verification is result.structural
    assert result.repair_plan is not None
    assert result.receipt.repair_invocations == 0
    assert "OPTIONAL_REPAIR" in result.receipt.events


def test_composition_marks_failed_and_invalid_repairs_without_rollback_to_v1(
    tmp_path: Path,
) -> None:
    task = make_task(tmp_path)
    finding = {
        "id": "V-REPAIR",
        "location": "hero",
        "expected": "specific visual",
        "observed": "generic visual",
        "severity": "MEDIUM",
        "status": "OPEN",
    }
    calls: list[str] = []

    def repair_builder(_task, _attempt, _correction):
        calls.append("repair")
        return _builder_response(
            invocation_id="INV-P5-REPAIR",
            message="not-json",
        )

    result = CompositionRunner().run(
        task,
        builder=lambda _task, _attempt: _builder_response(),
        repair_builder=repair_builder,
        critic=lambda packet: _critic(packet, verdict="FAIL", findings=[finding]),
        verifier=_verifier,
    )
    assert calls == ["repair"]
    assert result.status is Phase5Status.FAIL
    assert result.artifact is not None and result.artifact.version == "artifact_v1"
    assert result.receipt.artifact_versions == ("artifact_v1",)
    assert result.receipt.stale_evidence == ()


def test_composition_handles_none_verifier_result_and_records_pending_browser_verification(
    tmp_path: Path,
) -> None:
    task = make_task(tmp_path)
    finding = {
        "id": "V-NONE",
        "location": "hero",
        "expected": "specific visual",
        "observed": "generic visual",
        "severity": "HIGH",
        "status": "OPEN",
    }
    result = CompositionRunner().run(
        task,
        builder=lambda _task, _attempt: _builder_response(),
        critic=lambda packet: _critic(packet, verdict="FAIL", findings=[finding]),
        verifier=lambda *_args, **_kwargs: None,  # type: ignore[return-value]
        repair_builder=lambda _task, _attempt, _correction: _builder_response(
            invocation_id="INV-P5-REPAIR-NONE"
        ),
    )
    assert result.status is Phase5Status.FAIL
    assert result.final_verification is None
    assert "FINAL_BROWSER_VERIFICATION_REQUIRED" in result.assurance.limitations


def test_policy_mapping_round_trip_and_safe_file_errors(tmp_path: Path) -> None:
    fingerprint = make_fingerprint(tmp_path)
    payload = _policy_payload(fingerprint)
    policy = Phase5Allowlist.from_mapping(payload)
    assert policy.builder.capability_id == fingerprint.capability_id
    assert policy.secondary_status == "BLOCKED"
    assert policy.secondary_blocker == "EXTERNAL_VERIFIER_NOT_ELIGIBLE"
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(payload), encoding="utf-8")
    assert Phase5Allowlist.from_json(policy_path) == policy
    with pytest.raises(Phase5PolicyError):
        Phase5Allowlist.from_json(tmp_path / "missing.json")
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{", encoding="utf-8")
    with pytest.raises(Phase5PolicyError):
        Phase5Allowlist.from_json(bad_json)
    scalar = tmp_path / "scalar.json"
    scalar.write_text("[]", encoding="utf-8")
    with pytest.raises(Phase5PolicyError):
        Phase5Allowlist.from_json(scalar)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda p: p.update(schema_version="bad"),
        lambda p: p.pop("graph"),
        lambda p: p.update(graph=["DESIGN_BUILDER"]),
        lambda p: p.update(budgets={"max_repairs": 1}),
        lambda p: p["budgets"].update(max_repairs=2),
        lambda p: p.update(builder=object()),
        lambda p: p["builder"].update(unknown=True),
    ),
)
def test_policy_mapping_rejects_schema_budget_graph_and_identity_tampering(
    tmp_path: Path, mutation
) -> None:
    fingerprint = make_fingerprint(tmp_path)
    payload = _policy_payload(fingerprint)
    mutation(payload)
    with pytest.raises(Phase5PolicyError):
        Phase5Allowlist.from_mapping(payload)


@pytest.mark.parametrize(
    "field",
    (
        "status",
        "execution_approved",
        "allowed_mode",
        "allow_tools",
        "allow_scripts",
        "allow_shell",
        "allow_network",
        "allow_mcp",
        "allow_providers",
        "allow_credentials",
        "scripts_metadata_only",
        "reason",
    ),
)
def test_builder_action_policy_denies_every_host_side_effect(tmp_path: Path, field: str) -> None:
    fingerprint = make_fingerprint(tmp_path)
    payload = _policy_payload(fingerprint)
    values: dict[str, object] = {
        "status": "BLOCKED",
        "execution_approved": False,
        "allowed_mode": "CONTROLLED_REAL",
        "allow_tools": True,
        "allow_scripts": True,
        "allow_shell": True,
        "allow_network": True,
        "allow_mcp": True,
        "allow_providers": True,
        "allow_credentials": True,
        "scripts_metadata_only": False,
        "reason": "",
    }
    payload["builder"][field] = values[field]  # type: ignore[index]
    with pytest.raises(Phase5PolicyError):
        Phase5Allowlist.from_mapping(payload)


def test_policy_helpers_reject_invalid_text_lists_booleans_and_package_allowlist(
    tmp_path: Path,
) -> None:
    fingerprint = make_fingerprint(tmp_path)
    payload = _policy_payload(fingerprint)
    for key, value in (
        ("files", "not-list"),
        ("scripts", ["good", "\x00"]),
        ("dependencies", [""]),
    ):
        candidate = _policy_payload(fingerprint)
        candidate["builder"][key] = value  # type: ignore[index]
        with pytest.raises(Phase5PolicyError):
            Phase5Allowlist.from_mapping(candidate)
    candidate = _policy_payload(fingerprint)
    candidate["builder"]["scripts_metadata_only"] = "yes"  # type: ignore[index]
    with pytest.raises(Phase5PolicyError):
        Phase5Allowlist.from_mapping(candidate)
    with pytest.raises(Phase5PolicyError):
        Phase5Allowlist(
            builder=SimpleNamespace(capability_id="other"),  # type: ignore[arg-type]
            builder_manifest_fingerprint=MANIFEST_DIGEST,
            approved_status="APPROVED_RESPONSE_ONLY",
        )
    mismatched = make_fingerprint(tmp_path)
    with pytest.raises(Phase5PolicyError):
        Phase5Allowlist(
            builder=mismatched,
            builder_manifest_fingerprint=ZERO_DIGEST,
            approved_status="APPROVED_RESPONSE_ONLY",
        )
    with pytest.raises(Phase5PolicyError):
        Phase5Allowlist(
            builder=fingerprint,
            builder_manifest_fingerprint=fingerprint.manifest_fingerprint,
            approved_status="",
        )
    assert payload["builder"]["scripts_metadata_only"] is True


def test_build_fingerprint_projects_immutable_phase3_observation(tmp_path: Path) -> None:
    record = SimpleNamespace(
        capability_id="design-director",
        version="0.1.0",
        scope=SimpleNamespace(value="PROJECT"),
        path=str(tmp_path / "design-director"),
        content_hash=PACKAGE_DIGEST,
        manifest={"name": "design-director"},
        provenance=SimpleNamespace(source_type="LOCAL"),
        trust=SimpleNamespace(level=SimpleNamespace(value="PROJECT_TRUSTED")),
        compatibility=SimpleNamespace(status=SimpleNamespace(value="COMPATIBLE")),
        status=SimpleNamespace(value="INSPECTED"),
        load_eligibility="ELIGIBLE_DECLARATIVE_METADATA_ONLY",
        files=(SimpleNamespace(relative_path="SKILL.md"),),
        scripts=("metadata.json",),
        dependencies=(),
    )
    fingerprint = build_fingerprint(record)
    assert fingerprint.files == ("SKILL.md",)
    assert fingerprint.scripts_metadata_only is True
    assert fingerprint.manifest_fingerprint.startswith("sha256:")


def test_evaluate_eligibility_reports_every_identity_and_policy_blocker(tmp_path: Path) -> None:
    fingerprint = make_fingerprint(tmp_path)
    allowlist = Phase5Allowlist(
        fingerprint,
        fingerprint.manifest_fingerprint,
        "APPROVED_RESPONSE_ONLY",
    )
    changed = fingerprint
    changed = changed.__class__(
        capability_id="other",
        version="9.9.9",
        scope="GLOBAL",
        canonical_path=str(tmp_path / "other"),
        package_fingerprint=ZERO_DIGEST,
        manifest_fingerprint=ZERO_DIGEST,
        provenance=fingerprint.provenance,
        trust="REJECTED",
        compatibility="INCOMPATIBLE",
        package_status="STALE",
        load_eligibility="BLOCKED_BY_POLICY",
        files=(),
        scripts=("run.py",),
        dependencies=("dependency",),
        scripts_metadata_only=False,
    )
    report = evaluate_eligibility(changed, allowlist, Phase5Role.DESIGN_BUILDER, now=123)
    assert report.status is Phase5Status.BLOCKED
    assert report.evaluated_at == 123
    assert {
        "CAPABILITY_ID_MISMATCH",
        "VERSION_MISMATCH",
        "SCOPE_MISMATCH",
        "CANONICAL_PATH_MISMATCH",
        "PACKAGE_FINGERPRINT_MISMATCH",
        "MANIFEST_FINGERPRINT_MISMATCH",
        "PACKAGE_STATUS_BLOCKED",
        "TRUST_REJECTED",
        "COMPATIBILITY_INCOMPATIBLE",
        "LOAD_ELIGIBILITY_BLOCKED",
        "DEPENDENCY_NOT_APPROVED",
        "PACKAGE_SCRIPTS_PRESENT",
    }.issubset(report.blockers)

    metadata_only = (
        fingerprint.__class__(
            **{**fingerprint.__dict__, "scripts": ("metadata.json",), "scripts_metadata_only": True}
        )
        if hasattr(fingerprint, "__dict__")
        else None
    )
    if metadata_only is None:
        from dataclasses import replace

        metadata_only = replace(fingerprint, scripts=("metadata.json",), scripts_metadata_only=True)
    metadata_report = evaluate_eligibility(
        metadata_only, allowlist, Phase5Role.DESIGN_BUILDER, now=124
    )
    assert "PACKAGE_SCRIPTS_METADATA_ONLY_AND_DISABLED" in metadata_report.reasons

    fallback = evaluate_eligibility(fingerprint, allowlist, Phase5Role.STRUCTURAL_VERIFIER, now=125)
    assert fallback.route == "NATIVE_HARNESS_FALLBACK"
    assert fallback.blockers == ("SECONDARY_CAPABILITY_NOT_ELIGIBLE",)

    denied_allowlist = Phase5Allowlist(
        fingerprint,
        fingerprint.manifest_fingerprint,
        "BLOCKED",
    )
    denied = evaluate_eligibility(fingerprint, denied_allowlist, Phase5Role.DESIGN_BUILDER)
    assert "BUILDER_POLICY_NOT_APPROVED" in denied.blockers


def test_builder_prompt_and_request_bind_repair_scope_and_authorization(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    fingerprint = make_fingerprint(tmp_path)
    request = build_builder_request(
        task,
        fingerprint,
        host_executable_digest=HOST_DIGEST,
        host_interpreter_digest=HOST_DIGEST,
        attempt=2,
        now=100,
        repair_instruction="Fix only the mobile CTA spacing.",
    )
    assert "Bounded repair instruction" in request.task
    assert request.authorization.issued_at == 100
    assert request.authorization.expires_at == 220
    assert request.authorization.filesystem_policy["mode"] == "READ_ONLY"
    assert request.authorization.network_policy == "DENY"
    with pytest.raises(Phase5PolicyError):
        build_builder_request(
            task,
            fingerprint,
            host_executable_digest=HOST_DIGEST,
            host_interpreter_digest=HOST_DIGEST,
            attempt=0,
        )
    with pytest.raises(Phase5PolicyError):
        build_builder_request(
            task,
            fingerprint,
            host_executable_digest=HOST_DIGEST,
            host_interpreter_digest=HOST_DIGEST,
            attempt=1,
            repair_instruction="",
        )
    with pytest.raises(Phase5PolicyError):
        build_builder_request(
            task,
            fingerprint,
            host_executable_digest=HOST_DIGEST,
            host_interpreter_digest=HOST_DIGEST,
            attempt=1,
            repair_instruction="x" * 4_097,
        )


def test_png_dimensions_and_render_validation_report_corruption_staleness_and_viewport(
    tmp_path: Path,
) -> None:
    compact = tmp_path / "compact.png"
    compact.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">II", 390, 844))
    assert png_dimensions(compact) == (390, 844)
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not-png")
    with pytest.raises(ValueError, match="not a PNG"):
        png_dimensions(bad)
    incomplete = tmp_path / "incomplete.png"
    incomplete.write_bytes(b"\x89PNG\r\n\x1a\n123")
    with pytest.raises(ValueError, match="incomplete"):
        png_dimensions(incomplete)
    zero = tmp_path / "zero.png"
    zero.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">II", 0, 1))
    with pytest.raises(ValueError, match="invalid"):
        png_dimensions(zero)
    with pytest.raises(ValueError, match="read"):
        png_dimensions(tmp_path / "missing.png")

    task_root = tmp_path / "task"
    task_root.mkdir()
    task = make_task(task_root)
    artifact = _artifact(task)
    renders = _renders(Path(task.workspace))
    bad_render = RenderRecord.from_file(
        "bad-render", "artifact_v1", bad, (1440, 900), root=tmp_path
    )
    assert (
        verification_module._validate_render(
            task, artifact, bad_render, render_root=tmp_path
        ).finding_id
        == "S-RENDER-INVALID"
    )
    stale_render = RenderRecord.from_file(
        "stale-render", "artifact_v2", renders[0].path, (1440, 900), root=Path(task.workspace)
    )
    assert (
        verification_module._validate_render(
            task, artifact, stale_render, render_root=Path(task.workspace)
        ).finding_id
        == "S-RENDER-STALE"
    )
    wrong_viewport = RenderRecord.from_file(
        "wrong-render", "artifact_v1", renders[0].path, (1, 1), root=Path(task.workspace)
    )
    assert (
        verification_module._validate_render(
            task, artifact, wrong_viewport, render_root=Path(task.workspace)
        ).finding_id
        == "S-RENDER-VIEWPORT"
    )


def test_structural_verification_fails_closed_for_stale_artifact_criteria_and_bad_html(
    tmp_path: Path, monkeypatch
) -> None:
    task = make_task(tmp_path)
    artifact = _artifact(task)
    tampered_path = Path(artifact.path)
    tampered_path.write_text(valid_html().replace("Northline", "Tampered"), encoding="utf-8")
    stale_result = build_structural_verification(task, artifact, renders=())
    assert stale_result.status is Phase5Status.BLOCKED
    assert any(item.finding_id == "S-ARTIFACT-STALE" for item in stale_result.findings)

    fresh = _artifact(task, invocation_id="INV-P5-FRESH")
    stale_criteria = fresh.__class__(
        artifact_id=fresh.artifact_id,
        version=fresh.version,
        path=fresh.path,
        digest=fresh.digest,
        size_bytes=fresh.size_bytes,
        producer_capability=fresh.producer_capability,
        invocation_id=fresh.invocation_id,
        task_id=fresh.task_id,
        acceptance_digest=ZERO_DIGEST,
        source_kind=fresh.source_kind,
    )
    criteria_result = build_structural_verification(task, stale_criteria, renders=())
    assert criteria_result.status is Phase5Status.FAIL
    assert criteria_result.findings[0].finding_id == "S-CRITERIA-STALE"

    original_feed = verification_module._DocumentParser.feed

    def parser_failure(self, data):
        raise ValueError("malformed document")

    monkeypatch.setattr(verification_module._DocumentParser, "feed", parser_failure)
    parse_result = build_structural_verification(task, fresh, renders=())
    assert any(item.finding_id == "S-HTML-PARSE" for item in parse_result.findings)
    monkeypatch.setattr(verification_module._DocumentParser, "feed", original_feed)


def test_structural_verification_reports_all_material_html_and_render_findings(
    tmp_path: Path,
) -> None:
    task = make_task(tmp_path)
    bad_html = (
        "<html><body><h1>one</h1><h1>two</h1><script>alert(1)</script>placeholder</body></html>"
    )
    artifact = _raw_artifact(task, bad_html)
    desktop = Path(task.workspace) / "desktop.png"
    desktop.write_bytes(_png(1440, 900))
    render = RenderRecord.from_file(
        "desktop", "artifact_v1", desktop, (1440, 900), root=Path(task.workspace)
    )
    result = build_structural_verification(
        task,
        artifact,
        renders=(render,),
        render_root=task.workspace,
        console_errors=("console boom",),
        network_failures=("network boom",),
    )
    finding_ids = {item.finding_id for item in result.findings}
    assert {
        "S-SECTION-HEADER",
        "S-SECTION-FOOTER",
        "S-COPY-MISSING",
        "S-ACTION-TAG",
        "S-H1-COUNT",
        "S-LANG",
        "S-VIEWPORT-META",
        "S-REMOTE-ACTION",
        "S-FORBIDDEN-SIGNAL",
        "S-RENDER-VIEWPORT-MISSING",
        "S-CONSOLE-1",
        "S-NETWORK-1",
    }.issubset(finding_ids)
    assert result.status is Phase5Status.FAIL
    assert result.render_refs == ("desktop",)


@pytest.mark.parametrize(
    "mutation",
    (
        lambda observation: observation.update(viewport=(1, 1)),
        lambda observation: observation.update(document_width=2000),
        lambda observation: observation.update(document_width=0),
        lambda observation: observation.update(h1_count=2),
        lambda observation: observation.update(landmarks=[]),
        lambda observation: observation.update(external_resources=["remote"]),
        lambda observation: observation.update(external_resources="bad"),
    ),
)
def test_browser_observation_findings_preserve_each_failed_safety_dimension(
    tmp_path: Path, mutation
) -> None:
    task = make_task(tmp_path)
    artifact = _artifact(task)
    renders = _renders(tmp_path)
    observation = _browser_observation()
    mutation(observation)
    checks, findings = verification_module._browser_observation_findings(
        (renders[0],), (observation,), require=True
    )
    assert findings
    assert checks != [
        "browser_loadability",
        "browser_overflow",
        "browser_accessibility",
        "browser_confinement",
    ]
    result = build_structural_verification(
        task,
        artifact,
        renders=renders,
        render_root=tmp_path,
        browser_observations=_browser_observations(),
        require_browser_observations=True,
    )
    assert result.status is Phase5Status.PASS


def test_browser_observations_require_one_record_per_render_and_accept_tuple_viewport(
    tmp_path: Path,
) -> None:
    task = make_task(tmp_path)
    artifact = _artifact(task)
    renders = _renders(tmp_path)
    observation = _browser_observation()
    observation["viewport"] = (1440, 900)
    checks, findings = verification_module._browser_observation_findings(
        renders, (observation,), require=True
    )
    assert checks == []
    assert findings[0].finding_id == "S-BROWSER-EVIDENCE-MISSING"
    result = build_structural_verification(
        task,
        artifact,
        renders=renders,
        render_root=tmp_path,
        browser_observations=(observation,),
        require_browser_observations=True,
    )
    assert result.status is Phase5Status.FAIL


def test_blind_packet_and_critique_parser_cover_verdicts_safety_and_score_normalization(
    tmp_path: Path,
) -> None:
    task = make_task(tmp_path)
    artifact = _artifact(task)
    packet = make_blind_packet(task, artifact, _renders(tmp_path))
    assert packet.packet_digest.startswith("sha256:")
    base = _critic(packet, verdict="CONDITIONAL PASS", overall_score=88, dimension_scores={"A": 80})
    parsed = parse_blind_critique(base, packet_digest=packet.packet_digest)
    assert parsed.verdict is Phase5Status.PASS_WITH_LIMITATIONS
    assert parsed.dimension_scores["A"] == 8.0
    assert parsed.overall_score == 88.0
    assert parsed.is_independent is True
    for verdict, expected in (
        ("PASS", Phase5Status.PASS),
        ("PASS_WITH_LIMITATIONS", Phase5Status.PASS_WITH_LIMITATIONS),
        ("FAIL", Phase5Status.FAIL),
        ("STOP", Phase5Status.FAIL),
        ("UNKNOWN", Phase5Status.BLOCKED),
    ):
        parsed_verdict = parse_blind_critique(
            _critic(packet, verdict=verdict), packet_digest=packet.packet_digest
        )
        assert parsed_verdict.verdict is expected
    blocked = _critic(packet, verdict="PASS")
    blocked["blinded"] = False
    assert (
        parse_blind_critique(blocked, packet_digest=packet.packet_digest).verdict
        is Phase5Status.BLOCKED
    )
    no_digest = _critic(packet)
    no_digest.pop("packet_digest")
    with pytest.raises(ValueError):
        parse_blind_critique(no_digest, packet_digest=packet.packet_digest)


@pytest.mark.parametrize(
    "payload_mutation",
    (
        lambda p: p.update(packet_digest=1),
        lambda p: p.update(artifact_digest=None),
        lambda p: p.pop("blinded"),
        lambda p: p.update(blinded="yes"),
        lambda p: p.update(findings="bad"),
        lambda p: p.update(findings=["bad"]),
        lambda p: p.update(top_corrections="bad"),
        lambda p: p.update(evidence_missing="bad"),
        lambda p: p.update(dimension_scores={"x": True}),
    ),
)
def test_blind_critique_parser_rejects_malformed_untrusted_payloads(
    tmp_path: Path, payload_mutation
) -> None:
    task = make_task(tmp_path)
    packet = make_blind_packet(task, _artifact(task), ())
    payload = _critic(packet)
    payload_mutation(payload)
    with pytest.raises(ValueError):
        parse_blind_critique(payload, packet_digest=packet.packet_digest)
    with pytest.raises(ValueError):
        parse_blind_critique([], packet_digest=packet.packet_digest)  # type: ignore[arg-type]


def test_receipt_binding_and_artifact_reconstruction_reject_stale_or_substituted_evidence(
    tmp_path: Path,
) -> None:
    task = make_task(tmp_path)
    artifact = _artifact(task)
    identity = _identity()
    eligibility = {"status": Phase5Status.PASS, "fingerprint": identity | {"version": "0.1.0"}}
    authorization = {
        "authorization_id": identity["authorization_id"],
        "task_id": task.task_id,
        "run_id": task.run_id,
        "capability_id": "design-director",
        "capability_version": "0.1.0",
        "package_fingerprint": RECEIPT_PACKAGE,
    }
    context = {
        "task_id": task.task_id,
        "capability_id": "design-director",
        "package_fingerprint": RECEIPT_PACKAGE,
        "digest": RECEIPT_CONTEXT,
    }
    receipt = _receipt(task, artifact)
    assert (
        validate_receipt_binding(
            task, receipt, eligibility=eligibility, authorization=authorization, context=context
        )
        == identity
    )
    for section, key in (
        ("eligibility", "status"),
        ("authorization", "task_id"),
        ("context", "digest"),
        ("receipt", "capability_id"),
    ):
        bad_eligibility = dict(eligibility)
        bad_authorization = dict(authorization)
        bad_context = dict(context)
        bad_receipt = dict(receipt)
        target = {
            "eligibility": bad_eligibility,
            "authorization": bad_authorization,
            "context": bad_context,
            "receipt": bad_receipt,
        }[section]
        target[key] = "tampered"
        with pytest.raises(Phase5CliError):
            validate_receipt_binding(
                task,
                bad_receipt,
                eligibility=bad_eligibility,
                authorization=bad_authorization,
                context=bad_context,
            )

    with pytest.raises(Phase5CliError):
        artifact_from_receipt(task, {**receipt, "artifact_digest": ZERO_DIGEST})
    with pytest.raises(Phase5CliError):
        artifact_from_receipt(task, {**receipt, "attempt_count": True})
    with pytest.raises(Phase5CliError):
        artifact_from_receipt(task, {**receipt, "attempts": []})
    with pytest.raises(Phase5CliError):
        artifact_from_receipt(task, {**receipt, "attempts": [{"invocation_id": 1}]})
    with pytest.raises(Phase5CliError):
        artifact_from_receipt(
            task, {**receipt, "artifact_path": str(Path(task.workspace) / "wrong.html")}
        )


def test_finalization_input_helpers_reject_unsafe_files_and_versions(tmp_path: Path) -> None:
    assert finalization_module._read_string_list(None) == ()
    valid = tmp_path / "valid.json"
    valid.write_text('["console"]', encoding="utf-8")
    assert finalization_module._read_string_list(valid) == ("console",)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    with pytest.raises(Phase5CliError):
        finalization_module._read_string_list(invalid)
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(Phase5CliError):
        finalization_module._read_string_list(malformed)
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(Phase5CliError):
        finalization_module._read_string_list(directory)
    link = tmp_path / "link.json"
    link.symlink_to(valid)
    with pytest.raises(Phase5CliError):
        finalization_module._read_string_list(link)
    with pytest.raises(Phase5CliError):
        version_suffix("artifact_v3")
    assert version_suffix("artifact_v1") == "1"
    assert version_suffix("artifact_v2") == "2"
    assert (
        needs_repair(
            VisualCritique(
                "B",
                "R",
                "I",
                ZERO_DIGEST,
                "INDEPENDENT",
                True,
                True,
                True,
                ZERO_DIGEST,
                Phase5Status.PASS,
                90,
                "HIGH",
                {},
                (Finding("F", "hero", "x", "y", FindingSeverity.MEDIUM, "e"),),
                ("fix",),
                (),
            )
        )
        is True
    )


def test_render_records_and_browser_metrics_reject_substitution(tmp_path: Path) -> None:
    project = _finalization_project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    artifact = _artifact(task)
    evidence = project / "evidence/phase-5/pilots/design-director"
    evidence.mkdir(parents=True)
    desktop, mobile, renders = _write_render_inputs(project, evidence, artifact)
    assert len(renders) == 2
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png(1440, 900))
    with pytest.raises(Phase5CliError):
        render_records(project, evidence, outside, mobile)
    metrics = evidence / "artifact-v1/desktop-metrics.json"
    original = json.loads(metrics.read_text(encoding="utf-8"))
    for key, value in (
        ("artifact_version", "artifact_v2"),
        ("artifact_digest", ZERO_DIGEST),
        ("capture_method", "synthetic"),
        ("url", "https://remote.invalid"),
        ("viewport", {"width": 1, "height": 1}),
        ("browser", {}),
    ):
        candidate = dict(original)
        candidate[key] = value
        metrics.write_text(json.dumps(candidate), encoding="utf-8")
        with pytest.raises(Phase5CliError):
            finalization_module._browser_metrics(project, evidence, renders, artifact=artifact)
    metrics.write_text(json.dumps(original), encoding="utf-8")
    observed = finalization_module._browser_metrics(project, evidence, renders, artifact=artifact)
    assert len(observed) == 2


def test_artifact_v2_reconstruction_requires_parent_and_retains_lineage(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    v1 = _artifact(task, invocation_id="INV-P5-V1")
    v2 = _artifact(
        task,
        version="artifact_v2",
        invocation_id="INV-P5-V2",
        parent_artifact_digest=v1.digest,
    )
    receipt = _receipt(task, v2, repair=True, parent=v1.digest)
    assert (
        artifact_from_receipt(task, receipt, version="artifact_v2").parent_artifact_digest
        == v1.digest
    )
    with pytest.raises(Phase5CliError):
        artifact_from_receipt(
            task, {**receipt, "parent_artifact_digest": None}, version="artifact_v2"
        )
    with pytest.raises(Phase5CliError):
        artifact_from_receipt(
            task, {**receipt, "artifact_version": "artifact_v1"}, version="artifact_v2"
        )


def test_finalize_rejects_critic_packet_substitution_at_each_bound(tmp_path: Path) -> None:
    project = _finalization_project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    artifact = _artifact(task)
    evidence = project / "evidence/phase-5/pilots/design-director"
    evidence.mkdir(parents=True)
    writer = EvidenceWriter(evidence)
    _write_identity(writer, task)
    write_public_json(writer, "builder-invocation-receipt.json", _receipt(task, artifact))
    desktop, mobile, renders = _write_render_inputs(project, evidence, artifact)
    (desktop.parent / "console-errors.json").write_text("[]", encoding="utf-8")
    (desktop.parent / "network-failures.json").write_text("[]", encoding="utf-8")
    packet = make_blind_packet(task, artifact, renders)
    base = _critic(packet)
    for key, value in (
        ("benchmark_id", "OTHER"),
        ("run_id", "OTHER"),
        ("packet_digest", ZERO_DIGEST),
        ("artifact_digest", ZERO_DIGEST),
    ):
        candidate = dict(base)
        candidate[key] = value
        path = evidence / f"bad-{key}.json"
        write_public_json(writer, path.name, candidate)
        with pytest.raises(Phase5CliError):
            finalize(project, _finalization_args(desktop, mobile, path))


def test_finalize_preserves_failed_verification_and_records_pending_repair(tmp_path: Path) -> None:
    project = _finalization_project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    artifact = _artifact(task)
    evidence = project / "evidence/phase-5/pilots/design-director"
    evidence.mkdir(parents=True)
    writer = EvidenceWriter(evidence)
    _write_identity(writer, task)
    write_public_json(writer, "builder-invocation-receipt.json", _receipt(task, artifact))
    desktop, mobile, renders = _write_render_inputs(project, evidence, artifact)
    (desktop.parent / "console-errors.json").write_text('["console boom"]', encoding="utf-8")
    (desktop.parent / "network-failures.json").write_text("[]", encoding="utf-8")
    critique_path = evidence / "critic.json"
    packet = make_blind_packet(task, artifact, renders)
    write_public_json(
        writer,
        "critic.json",
        _critic(
            packet,
            verdict="PASS",
            findings=[
                {
                    "id": "V-OPEN",
                    "location": "hero",
                    "expected": "specific",
                    "observed": "generic",
                    "severity": "HIGH",
                    "status": "OPEN",
                }
            ],
        ),
    )
    result = finalize(
        project,
        _finalization_args(
            desktop,
            mobile,
            critique_path,
            console_errors=desktop.parent / "console-errors.json",
            network_failures=desktop.parent / "network-failures.json",
        ),
    )
    assert result["status"] is Phase5Status.FAIL
    assurance = json.loads((evidence / "assurance.json").read_text(encoding="utf-8"))
    assert "S-CONSOLE-1" in assurance["blockers"]


def test_finalize_v2_requires_retained_current_v1_evidence_and_parent_binding(
    tmp_path: Path,
) -> None:
    project = _finalization_project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    evidence = project / "evidence/phase-5/pilots/design-director"
    evidence.mkdir(parents=True)
    writer = EvidenceWriter(evidence)
    v1 = _artifact(task, invocation_id="INV-P5-V1")
    v2 = _artifact(
        task, version="artifact_v2", invocation_id="INV-P5-V2", parent_artifact_digest=v1.digest
    )
    _write_identity(writer, task)
    write_public_json(writer, "builder-invocation-receipt.json", _receipt(task, v1))
    _write_identity(writer, task, repair=True)
    write_public_json(
        writer, "builder-repair-receipt.json", _receipt(task, v2, repair=True, parent=v1.digest)
    )
    desktop, mobile, renders = _write_render_inputs(project, evidence, v2, version="artifact_v2")
    (desktop.parent / "console-errors.json").write_text("[]", encoding="utf-8")
    (desktop.parent / "network-failures.json").write_text("[]", encoding="utf-8")
    packet = make_blind_packet(task, v2, renders)
    critique_path = evidence / "critic-v2.json"
    write_public_json(writer, critique_path.name, _critic(packet))
    with pytest.raises(Phase5CliError, match="retained"):
        finalize(project, _finalization_args(desktop, mobile, critique_path, version="artifact_v2"))

    _write_identity(writer, task)
    write_public_json(writer, "builder-invocation-receipt.json", _receipt(task, v1))
    desktop_v1, mobile_v1, renders_v1 = _write_render_inputs(project, evidence, v1)
    write_public_json(writer, "verification-v1.json", {"artifact_digest": v1.digest})
    write_public_json(writer, "critique-v1.json", {"artifact_digest": v1.digest})
    bad_v2 = dict(_receipt(task, v2, repair=True, parent=ZERO_DIGEST))
    write_public_json(writer, "builder-repair-receipt.json", bad_v2)
    bad_v2["parent_artifact_digest"] = ZERO_DIGEST
    write_public_json(writer, "builder-repair-receipt.json", bad_v2)
    with pytest.raises(Phase5CliError, match="parent"):
        finalize(project, _finalization_args(desktop, mobile, critique_path, version="artifact_v2"))


def test_prepare_review_writes_blind_request_without_exposing_builder_context(
    tmp_path: Path,
) -> None:
    project = _finalization_project(tmp_path)
    task = load_task(project / "tests/fixtures/phase5/design-pilot/task.json", project_root=project)
    artifact = _artifact(task)
    evidence = project / "evidence/phase-5/pilots/design-director"
    evidence.mkdir(parents=True)
    writer = EvidenceWriter(evidence)
    write_public_json(writer, "builder-invocation-receipt.json", _receipt(task, artifact))
    desktop, mobile, renders = _write_render_inputs(project, evidence, artifact)
    result = prepare_review(project, _finalization_args(desktop, mobile, evidence / "unused.json"))
    request = json.loads((evidence / "review-request-v1.json").read_text(encoding="utf-8"))
    assert result["status"] is Phase5Status.PASS
    assert request["builder_rationale_withheld"] is True
    assert request["self_score_withheld"] is True
    assert "Exact copy JSON" not in json.dumps(request)
