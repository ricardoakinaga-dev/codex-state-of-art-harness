from __future__ import annotations

import json
import shutil
from argparse import Namespace
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from phase5_support import HOST_DIGEST, make_fingerprint, make_task, valid_html
from test_contracts import all_records, profile

from harness_kernel import cli as cli_module
from harness_kernel import phase4_cli, phase5_cli, phase5_policy
from harness_kernel.models import (
    CapabilityManifest,
    CapabilityPrimaryType,
    CapabilityScope,
    CapabilityStatus,
    Complexity,
    OmittedReasonCode,
    RecordStatus,
    RegistryOrigin,
    RouteKind,
    RouteStatus,
    SourceType,
    TaskDomain,
)
from harness_kernel.phase4_models import ExecutionMode
from harness_kernel.phase5_artifacts import ArtifactCaptureError
from harness_kernel.phase5_execution import BuilderResponse
from harness_kernel.phase5_models import (
    ArtifactPacket,
    Phase5Budget,
    Phase5Role,
    Phase5Status,
    RenderRecord,
    public_data,
)
from harness_kernel.phase5_policy import (
    Phase5Allowlist,
    build_builder_request,
    evaluate_eligibility,
)
from harness_kernel.phase5_verification import make_blind_packet
from harness_kernel.registry import CapabilityRegistry
from harness_kernel.routing import minimum_route
from harness_kernel.serialization import from_dict
from harness_kernel.validation import ValidationCode, ValidationResult

PROJECT_ROOT = Path(__file__).parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parents[1]
_DIGEST_ZERO = "sha256:" + "0" * 64


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(PROJECT_ROOT / ".harness", project / ".harness")
    shutil.copytree(WORKSPACE_ROOT / "architecture", project / "architecture")
    return project


def _manifest(project: Path) -> CapabilityManifest:
    path = project / ".harness" / "registry" / "manifests" / "harness-kernel.json"
    return cast(CapabilityManifest, from_dict(json.loads(path.read_text()), CapabilityManifest))


def _capability(
    capability_id: str,
    primary_type: CapabilityPrimaryType,
    *,
    domains: tuple[str, ...] = ("ENGINEERING",),
    triggers: tuple[str, ...] = (),
    status: CapabilityStatus = CapabilityStatus.ACTIVE,
) -> CapabilityManifest:
    base = next(item for item in all_records() if isinstance(item, CapabilityManifest))
    return replace(
        base,
        capability_id=capability_id,
        primary_type=primary_type,
        status=status,
        record=replace(base.record, status=RecordStatus.CURRENT),
        scope=CapabilityScope(
            domains=domains,
            activates_when=triggers,
            do_not_activate_when=(),
            minimum_task_class=Complexity.SMALL,
        ),
    )


def _phase5_allowlist(fingerprint):
    return Phase5Allowlist(
        builder=fingerprint,
        builder_manifest_fingerprint=fingerprint.manifest_fingerprint,
        approved_status="APPROVED_RESPONSE_ONLY",
    )


def _phase5_preflight(
    tmp_path: Path,
    *,
    fingerprint=None,
    eligibility=None,
    binding=None,
    selected_record=None,
):
    task_root = tmp_path / f"phase5-case-{len(tuple(tmp_path.iterdir()))}"
    task_root.mkdir()
    fingerprint = make_fingerprint(tmp_path) if fingerprint is None else fingerprint
    task = make_task(task_root)
    allowlist = _phase5_allowlist(fingerprint)
    return phase5_cli.PilotPreflight(
        task=task,
        allowlist=allowlist,
        adapter=cast(Any, object()),
        host_adapter=cast(Any, object()),
        selected_record=selected_record,
        fingerprint=fingerprint,
        eligibility=(
            evaluate_eligibility(fingerprint, allowlist, Phase5Role.DESIGN_BUILDER)
            if eligibility is None
            else eligibility
        ),
        secondary={},
        resolution_status="SELECTED",
        resolution_blockers=(),
        binding=(
            (
                ("/usr/bin/python",),
                "/usr/bin/python",
                HOST_DIGEST,
                (),
                "/usr/bin/python",
                HOST_DIGEST,
            )
            if binding is None
            else binding
        ),
    )


def _packet_fixture(tmp_path: Path):
    task = make_task(tmp_path)
    artifact_path = Path(task.artifact_root) / "index.html"
    html = valid_html()
    artifact_path.write_text(html, encoding="utf-8")
    artifact = ArtifactPacket.from_content(
        artifact_id="ART-P5-V1",
        version="artifact_v1",
        path=str(artifact_path),
        content=html,
        producer_capability="design-director",
        invocation_id="INV-P5-1",
        task=task,
    )
    render_root = tmp_path / "renders"
    render_root.mkdir()
    render_path = render_root / "desktop.png"
    render_path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + (1440).to_bytes(4, "big") + (900).to_bytes(4, "big")
    )
    render = RenderRecord.from_file(
        "RENDER-DESKTOP",
        "artifact_v1",
        render_path,
        (1440, 900),
        root=render_root,
    )
    packet = make_blind_packet(task, artifact, (render,))
    return task, artifact, render, packet, json.loads(json.dumps(public_data(packet)))


def _repair_artifact(task, version: str, *, parent_artifact_digest: str | None = None):
    artifact_root = Path(task.artifact_root) / version
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_root / "index.html"
    html = valid_html()
    artifact_path.write_text(html, encoding="utf-8")
    return ArtifactPacket.from_content(
        artifact_id=f"ART-{version.upper()}",
        version=version,
        path=str(artifact_path),
        content=html,
        producer_capability="design-director",
        invocation_id=f"INV-{version.upper()}",
        task=task,
        parent_artifact_digest=parent_artifact_digest,
    )


def _patch_repair_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
    preflight,
    evidence_root: Path,
) -> Namespace:
    monkeypatch.setattr(
        phase5_cli,
        "load_task",
        lambda *_args, **_kwargs: preflight.task,
    )
    monkeypatch.setattr(phase5_cli, "_task_path", lambda *_args: evidence_root / "task.json")
    monkeypatch.setattr(phase5_cli, "_policy_path", lambda *_args: evidence_root / "policy.json")
    monkeypatch.setattr(phase5_cli, "_evidence_path", lambda *_args: evidence_root)
    monkeypatch.setattr(phase5_cli, "_preflight", lambda *_args: preflight)
    monkeypatch.setattr(
        phase5_cli,
        "_preflight_route",
        lambda *_args, **_kwargs: {"status": Phase5Status.PASS, "blockers": ()},
    )
    return Namespace(
        task=Path("task.json"),
        policy=Path("policy.json"),
        evidence_dir=Path("evidence"),
        confirm_fingerprint=preflight.fingerprint.package_fingerprint,
        correction="tighten contrast",
        json_output=True,
    )


def _patch_repair_evidence(
    monkeypatch: pytest.MonkeyPatch,
    task,
    v1_artifact,
    *,
    repair_receipt: dict[str, object] | None = None,
    critique_benchmark_id: str | None = None,
    critique_run_id: str | None = None,
    critique_packet_digest: str | None = None,
    critique_artifact_digest: str | None = None,
) -> None:
    packet = SimpleNamespace(
        benchmark_id="P5-DESIGN-1",
        run_id=task.run_id,
        packet_digest="PACKET-DIGEST",
    )
    critique = SimpleNamespace(top_corrections=("tighten contrast",))

    def read_mapping(path: Path) -> dict[str, object]:
        if path.name == "builder-invocation-receipt.json":
            return {"attempt_count": 1}
        if path.name == "blind-packet-v1.json":
            return {
                "benchmark_id": packet.benchmark_id,
                "run_id": packet.run_id,
                "packet_digest": packet.packet_digest,
                "artifact_digest": v1_artifact.digest,
            }
        if path.name == "critique-v1.json":
            return {
                "benchmark_id": critique_benchmark_id or packet.benchmark_id,
                "run_id": critique_run_id or packet.run_id,
                "packet_digest": critique_packet_digest or packet.packet_digest,
                "artifact_digest": critique_artifact_digest or v1_artifact.digest,
            }
        if path.name == "builder-repair-receipt.json" and repair_receipt is not None:
            return repair_receipt
        return {}

    monkeypatch.setattr(phase5_cli, "read_json_mapping", read_mapping)
    monkeypatch.setattr(phase5_cli, "_validate_receipt_binding", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        phase5_cli,
        "_artifact_from_receipt",
        lambda _task, _receipt, **_kwargs: v1_artifact,
    )
    monkeypatch.setattr(phase5_cli, "_bound_packet_from_evidence", lambda *_args: packet)
    monkeypatch.setattr(phase5_cli, "parse_blind_critique", lambda *_args, **_kwargs: critique)
    monkeypatch.setattr(phase5_cli, "_needs_repair", lambda _critique: True)


def test_cli_path_and_diagnostic_helpers_fail_closed_without_echoing_input() -> None:
    for value in ("nul\x00path", "../outside", "a/../outside"):
        with pytest.raises(cli_module.CliError) as caught:
            cli_module._validate_path_text(value)
        assert caught.value.code == "PATH_INVALID"
        assert value not in caught.value.safe_message

    assert cli_module._safe_path("$.findings[0].message") == "$.findings[0].message"
    assert cli_module._safe_path("/secret/path") == "$"
    assert cli_module._safe_path("$.bad-key") == "$"
    assert cli_module._config_path_is_safe(".harness/config/kernel.json")
    assert not cli_module._config_path_is_safe("../outside")
    assert not cli_module._config_path_is_safe("/absolute")
    assert not cli_module._config_path_is_safe("")


def test_cli_input_paths_and_configured_registry_directories_are_bounded(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    with pytest.raises(cli_module.CliError, match="input path is invalid"):
        cli_module._input_path("-", project)
    with pytest.raises(cli_module.CliError, match="regular file"):
        cli_module._input_path(".harness", project)

    manifest_paths = cli_module._manifest_files(project)
    assert manifest_paths

    capability_root = project / ".harness" / "capabilities"
    moved_capabilities = project / "capabilities-disabled"
    capability_root.rename(moved_capabilities)
    assert cli_module._manifest_files(project)

    config_path = project / ".harness" / "config" / "kernel.json"
    config = json.loads(config_path.read_text())
    config["registry"]["manifest_dir"] = ".harness/registry/missing"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(cli_module.CliError, match="project registry is unavailable"):
        cli_module._manifest_files(project)


def test_cli_manifest_reference_diagnostics_distinguish_unverifiable_and_missing(
    tmp_path: Path,
) -> None:
    project = _copy_project(tmp_path)
    manifest = _manifest(project)
    unverifiable = replace(
        manifest,
        dependencies=replace(
            manifest.dependencies,
            references=("https://example.invalid/reference", "/absolute/reference", "relative.md"),
        ),
    )
    failures = cli_module._manifest_reference_failures(unverifiable, tmp_path / "without-workspace")
    assert len(failures) == 2
    assert {item["code"] for item in failures} == {"MANIFEST_REFERENCE_UNVERIFIABLE"}

    missing = replace(
        manifest,
        dependencies=replace(
            manifest.dependencies,
            references=(
                "https://example.invalid/reference",
                "architecture/missing.md",
                "../escape",
            ),
        ),
    )
    failures = cli_module._manifest_reference_failures(missing, project)
    assert len(failures) == 2
    assert {item["code"] for item in failures} == {"MISSING_MANIFEST_REFERENCE"}


def test_cli_manifest_provenance_diagnostics_cover_source_and_project_scope(tmp_path: Path) -> None:
    project = _copy_project(tmp_path)
    manifest = _manifest(project)
    multiple_sources = replace(
        manifest,
        provenance=replace(manifest.provenance, source_refs=("one.md", "two.md")),
    )
    assert cli_module._manifest_provenance_failures(multiple_sources, project)[0]["code"] == (
        "SOURCE_HASH_UNVERIFIABLE"
    )

    stale = replace(manifest, provenance=replace(manifest.provenance, source_hash=_DIGEST_ZERO))
    assert cli_module._manifest_provenance_failures(stale, project)[0]["code"] == (
        "SOURCE_HASH_MISMATCH"
    )

    wrong_owner = replace(
        manifest,
        provenance=replace(manifest.provenance, project_scope="different-project"),
    )
    wrong_owner = replace(
        wrong_owner,
        provenance=replace(
            wrong_owner.provenance,
            source_hash=cli_module._manifest_source_hash(wrong_owner, project),
        ),
    )
    assert cli_module._manifest_provenance_failures(wrong_owner, project)[0]["code"] == (
        "PROJECT_SCOPE_MISMATCH"
    )

    official = replace(
        manifest,
        provenance=replace(
            manifest.provenance,
            source_type=SourceType.OFFICIAL,
            origin=RegistryOrigin.SYSTEM,
        ),
    )
    assert cli_module._manifest_provenance_failures(official, project) == ()


def test_cli_manifest_source_hash_defensive_branch_does_not_trust_malformed_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _copy_project(tmp_path)
    manifest = _manifest(project)
    monkeypatch.setattr(cli_module, "to_dict", lambda _value: {"provenance": None})
    with pytest.raises(ValueError, match="provenance is invalid"):
        cli_module._manifest_source_hash(manifest, project)


def test_cli_manifest_admission_rejects_invalid_config_and_unsafe_registry_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _copy_project(tmp_path)
    config_path = project / ".harness" / "config" / "kernel.json"
    config_path.write_text("{}", encoding="utf-8")
    with pytest.raises(cli_module.CliError, match="project configuration is invalid"):
        cli_module._manifest_files(project)

    config = json.loads((PROJECT_ROOT / ".harness" / "config" / "kernel.json").read_text())
    config["registry"]["manifest_dir"] = "../unsafe"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    config_result = cli_module._config_result(config)
    assert not config_result.valid
    assert any(
        finding.code is ValidationCode.INVALID_REFERENCE for finding in config_result.findings
    )
    monkeypatch.setattr(
        cli_module,
        "_config_result",
        lambda _value: ValidationResult(True, (), "KernelConfig"),
    )
    with pytest.raises(cli_module.CliError, match="project registry paths are invalid"):
        cli_module._manifest_files(project)


def test_cli_execution_limits_reject_an_invalid_default_provider_after_config_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _copy_project(tmp_path)
    config_path = project / ".harness" / "config" / "kernel.json"
    config = json.loads(config_path.read_text())
    config["execution"]["default_provider"] = "not a provider"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(
        cli_module,
        "_config_result",
        lambda _value: ValidationResult(True, (), "KernelConfig"),
    )
    with pytest.raises(cli_module.CliError, match="default provider is invalid"):
        cli_module._execution_limits(project)


def test_cli_main_envelopes_invalid_provider_identifier(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_module.main(["run", "bounded objective", "--provider", "../escape", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload == {
        "code": "INVALID_INPUT",
        "message": "provider id is invalid",
        "status": "ERROR",
    }


def test_cli_dry_run_routes_without_registry_failures_and_preserves_no_execution_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    exit_code = cli_module.main(["run", "validate a local contract", "--dry-run", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "DRY_RUN"
    assert payload["executed"] is False
    assert payload["telemetry_events"] >= 1


@pytest.mark.parametrize("failure_kind", ("reference", "provenance"))
def test_cli_registry_load_routes_admission_failures_to_public_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_kind: str
) -> None:
    project = _copy_project(tmp_path)
    manifest_path = project / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    manifest = _manifest(project)
    monkeypatch.setattr(cli_module, "_manifest_files", lambda _root: (manifest_path,))
    monkeypatch.setattr(cli_module, "_load_contract", lambda *_args, **_kwargs: manifest)
    finding = {
        "code": "MISSING_MANIFEST_REFERENCE"
        if failure_kind == "reference"
        else "SOURCE_HASH_MISMATCH",
        "path": "$.manifest",
        "message": "admission failed",
    }
    if failure_kind == "reference":
        monkeypatch.setattr(cli_module, "_manifest_reference_failures", lambda *_args: (finding,))
    else:
        monkeypatch.setattr(cli_module, "_manifest_reference_failures", lambda *_args: ())
        monkeypatch.setattr(cli_module, "_manifest_provenance_failures", lambda *_args: (finding,))

    registry, failures = cli_module._load_registry(project)

    assert registry.list() == ()
    assert failures == (finding,)


def test_cli_registry_load_accepts_clean_manifest_admission_without_failures(
    tmp_path: Path,
) -> None:
    project = _copy_project(tmp_path)
    registry, failures = cli_module._load_registry(project)
    assert registry.list()
    assert failures == ()


def test_cli_registry_load_does_not_promote_a_non_manifest_decoder_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli_module, "_manifest_files", lambda _root: (path,))
    monkeypatch.setattr(cli_module, "_load_contract", lambda *_args, **_kwargs: object())
    registry, failures = cli_module._load_registry(tmp_path)
    assert registry.list() == ()
    assert failures == ()


def test_cli_run_rejects_registry_failures_with_an_enveloped_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    monkeypatch.setattr(
        cli_module,
        "_load_registry",
        lambda _root: (CapabilityRegistry(), ({"code": "REGISTRY_FAILURE"},)),
    )

    exit_code = cli_module.main(["run", "validate a local contract", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload == {
        "code": "REGISTRY_INVALID",
        "message": "project capability registry failed admission",
        "status": "ERROR",
    }


def test_phase4_cli_helpers_preserve_path_scope_and_blocked_envelopes(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    assert phase4_cli._project_path(tmp_path, Path("nested"), "workspace") == nested.resolve()
    assert phase4_cli._has_symlink_component(nested.resolve()) is False
    assert phase4_cli._has_symlink_component(Path("nested")) is True

    payload = phase4_cli._missing_payload(ExecutionMode.PREPARE_ONLY, "safe-pilot", "SCOPE_BLOCKED")
    assert payload["status"] == "BLOCKED"
    assert payload["host_invoked"] is False
    human = phase4_cli._human_output({**payload, "limitations": ["evidence incomplete"]})
    assert "NO HOST EXECUTION" in human
    assert "SCOPE_BLOCKED" in human
    assert "evidence incomplete" in human


def test_phase4_cli_human_output_has_stable_minimal_envelope_without_optional_diagnostics() -> None:
    output = phase4_cli._human_output(
        {
            "mode": "DRY_RUN",
            "status": "PREPARED",
            "host_invoked": False,
        }
    )
    assert output.splitlines() == [
        "Mode: DRY_RUN",
        "Status: PREPARED",
        "NO HOST EXECUTION",
        "Host invoked: no",
    ]


def test_phase4_cli_main_converts_unrepresentable_type_errors_to_blocked_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(_arguments: Namespace) -> dict[str, object]:
        raise TypeError("internal type boundary failure")

    monkeypatch.setattr(phase4_cli, "_run_invoke", fail)
    exit_code = phase4_cli.main(
        ["invoke", "safe-pilot", "--task", "bounded", "--dry-run", "--json"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "BLOCKED"
    assert payload["host_invoked"] is False
    assert "internal type boundary failure" not in json.dumps(payload)


def test_phase5_cli_main_converts_unrepresentable_type_errors_to_blocked_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(phase5_cli, "_resolved_project_root", lambda _root: tmp_path)

    def fail(*_args, **_kwargs):
        raise TypeError("internal type boundary failure")

    monkeypatch.setattr(phase5_cli, "_pilot", fail)
    exit_code = phase5_cli.main(["--project-root", str(tmp_path), "pilot", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == Phase5Status.BLOCKED
    assert "internal type boundary failure" not in json.dumps(payload)


def test_phase5_policy_mapping_and_fingerprint_branches_are_explicit(tmp_path: Path) -> None:
    fingerprint = make_fingerprint(tmp_path)
    payload = {
        "schema_version": "P5-POLICY-1",
        "graph": list(phase5_policy.FIXED_GRAPH),
        "budgets": {
            "max_builder_invocations": 2,
            "max_structural_verifications": 2,
            "max_visual_critiques": 2,
            "max_repairs": 1,
            "max_render_versions": 2,
            "max_artifact_bytes": 131072,
            "max_context_bytes": 32768,
            "max_evidence_records": 64,
        },
        "builder": fingerprint,
        "builder_manifest_fingerprint": fingerprint.manifest_fingerprint,
        "approved_status": "APPROVED_RESPONSE_ONLY",
    }
    allowlist = Phase5Allowlist.from_mapping(payload)
    assert allowlist.builder is fingerprint

    mapping_builder = {
        **public_data(fingerprint),
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
        "scripts_metadata_only": True,
        "reason": "bounded mapping fixture",
    }
    mapping_payload = {**payload, "builder": mapping_builder}
    mapped = Phase5Allowlist.from_mapping(mapping_payload)
    assert mapped.builder.capability_id == fingerprint.capability_id
    with pytest.raises(phase5_policy.Phase5PolicyError, match="manifest fingerprint is required"):
        Phase5Allowlist.from_mapping({**payload, "builder_manifest_fingerprint": None})


def test_phase5_builder_attempt_rejects_boolean_as_a_retry_count(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    fingerprint = make_fingerprint(tmp_path)
    with pytest.raises(phase5_policy.Phase5PolicyError, match="attempt must be positive"):
        build_builder_request(
            task,
            fingerprint,
            host_executable_digest=HOST_DIGEST,
            host_interpreter_digest=HOST_DIGEST,
            attempt=True,
        )


def test_phase5_preflight_route_blocks_confirmation_and_host_binding_failures(
    tmp_path: Path,
) -> None:
    preflight = _phase5_preflight(tmp_path)
    not_real = phase5_cli._preflight_route(
        preflight, controlled_real=False, confirmed_fingerprint=None
    )
    assert not_real["status"] is Phase5Status.BLOCKED
    assert "REAL_MODE_CONFIRMATION_REQUIRED" in not_real["blockers"]

    missing_binding = _phase5_preflight(tmp_path, binding=None)
    # An explicit None must be distinguishable from the valid default binding.
    missing_binding = replace(missing_binding, binding=None)
    blocked = phase5_cli._preflight_route(
        missing_binding,
        controlled_real=True,
        confirmed_fingerprint=preflight.fingerprint.package_fingerprint,
    )
    assert "HOST_EXECUTABLE_UNAVAILABLE" in blocked["blockers"]

    no_interpreter = _phase5_preflight(
        tmp_path,
        binding=(("/usr/bin/python",), "/usr/bin/python", HOST_DIGEST, (), "/usr/bin/python", None),
    )
    blocked = phase5_cli._preflight_route(
        no_interpreter,
        controlled_real=True,
        confirmed_fingerprint=no_interpreter.fingerprint.package_fingerprint,
    )
    assert "HOST_INTERPRETER_UNAVAILABLE" in blocked["blockers"]

    mismatch = phase5_cli._preflight_route(
        preflight, controlled_real=True, confirmed_fingerprint=_DIGEST_ZERO
    )
    assert "FINGERPRINT_CONFIRMATION_MISMATCH" in mismatch["blockers"]


def test_phase5_preflight_route_requires_exact_resolution_and_eligibility(tmp_path: Path) -> None:
    fingerprint = make_fingerprint(tmp_path)
    no_selection = _phase5_preflight(tmp_path, fingerprint=fingerprint, eligibility=None)
    no_selection = replace(no_selection, selected_record=None, fingerprint=None, eligibility=None)
    route = phase5_cli._preflight_route(
        no_selection, controlled_real=True, confirmed_fingerprint=None
    )
    assert route["status"] is Phase5Status.BLOCKED
    assert "CAPABILITY_NOT_RESOLVED_EXACTLY" in route["blockers"]
    assert "BUILDER_ELIGIBILITY_UNAVAILABLE" in route["blockers"]

    blocked_eligibility = SimpleNamespace(
        status=Phase5Status.BLOCKED,
        blockers=("PACKAGE_FINGERPRINT_MISMATCH",),
    )
    preflight = _phase5_preflight(tmp_path, eligibility=blocked_eligibility)
    route = phase5_cli._preflight_route(
        preflight,
        controlled_real=True,
        confirmed_fingerprint=preflight.fingerprint.package_fingerprint,
    )
    assert route["status"] is Phase5Status.BLOCKED
    assert "PACKAGE_FINGERPRINT_MISMATCH" in route["blockers"]


def test_phase5_request_for_attempt_requires_host_and_interpreter_fingerprints(
    tmp_path: Path,
) -> None:
    valid = _phase5_preflight(tmp_path)
    request = phase5_cli._request_for_attempt(valid, 1, Phase5Budget())
    assert request.authorization.host_executable_digest == HOST_DIGEST
    assert request.authorization.host_interpreter_digest == HOST_DIGEST

    with pytest.raises(phase5_cli.Phase5CliError, match="exact builder or host binding"):
        phase5_cli._request_for_attempt(replace(valid, fingerprint=None), 1, Phase5Budget())
    with pytest.raises(phase5_cli.Phase5CliError, match="exact builder or host binding"):
        phase5_cli._request_for_attempt(replace(valid, binding=None), 1, Phase5Budget())
    no_interpreter = replace(
        valid,
        binding=(("/usr/bin/python",), "/usr/bin/python", HOST_DIGEST, (), "/usr/bin/python", None),
    )
    with pytest.raises(phase5_cli.Phase5CliError, match="interpreter fingerprint"):
        phase5_cli._request_for_attempt(no_interpreter, 1, Phase5Budget())


def test_phase5_builder_routes_missing_fingerprint_and_blocked_response_without_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = phase5_cli.EvidenceWriter(tmp_path / "evidence")
    valid = _phase5_preflight(tmp_path)
    with pytest.raises(phase5_cli.Phase5CliError, match="fingerprint is unavailable"):
        phase5_cli._run_builder(replace(valid, fingerprint=None), writer)

    request = phase5_cli._request_for_attempt(valid, 1, Phase5Budget())
    monkeypatch.setattr(phase5_cli, "_request_for_attempt", lambda *_args: request)
    monkeypatch.setattr(
        phase5_cli,
        "invoke_host_builder",
        lambda *_args, **_kwargs: BuilderResponse(
            Phase5Status.BLOCKED,
            request.invocation_id,
            None,
            False,
            "UNAVAILABLE",
            "HOST_UNAVAILABLE",
        ),
    )
    result = phase5_cli._run_builder(valid, writer)
    assert result["status"] is Phase5Status.BLOCKED
    assert result["builder_receipt"]["attempt_count"] == 1
    assert result["builder_receipt"]["artifact_digest"] is None


def test_phase5_secondary_summary_has_an_explicit_blocked_fallback() -> None:
    summary = phase5_cli._secondary_summary(None, None, cast(Any, object()))
    assert summary == {
        "capability_id": "verification-loop",
        "status": Phase5Status.BLOCKED.value,
        "blocker": "EXTERNAL_VERIFIER_NOT_ELIGIBLE",
        "observed": False,
    }


def test_phase5_builder_accepts_a_materialized_artifact_without_retrying(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = phase5_cli.EvidenceWriter(tmp_path / "evidence")
    preflight = _phase5_preflight(tmp_path)
    request = phase5_cli._request_for_attempt(preflight, 1, Phase5Budget())
    html = valid_html()
    extracted = SimpleNamespace(filename="index.html", html=html)
    artifact = _repair_artifact(preflight.task, "artifact_v1")
    monkeypatch.setattr(phase5_cli, "_request_for_attempt", lambda *_args: request)
    monkeypatch.setattr(
        phase5_cli,
        "invoke_host_builder",
        lambda *_args, **_kwargs: BuilderResponse(
            Phase5Status.PASS,
            request.invocation_id,
            html,
            True,
            "OBSERVED",
        ),
    )
    monkeypatch.setattr(
        phase5_cli, "extract_response_artifact", lambda *_args, **_kwargs: extracted
    )
    monkeypatch.setattr(
        phase5_cli, "materialize_response_artifact", lambda *_args, **_kwargs: artifact
    )

    result = phase5_cli._run_builder(preflight, writer)

    assert result["status"] is Phase5Status.PASS_WITH_LIMITATIONS
    assert result["artifact"]["artifact_id"] == artifact.artifact_id


def test_phase5_builder_exhausts_capture_retries_without_claiming_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = phase5_cli.EvidenceWriter(tmp_path / "evidence")
    preflight = _phase5_preflight(tmp_path)
    requests = []

    def request_for_attempt(_preflight, attempt: int, _budget: Phase5Budget):
        request = build_builder_request(
            preflight.task,
            preflight.fingerprint,
            host_executable_digest=HOST_DIGEST,
            host_interpreter_digest=HOST_DIGEST,
            attempt=attempt,
        )
        requests.append(request)
        return request

    monkeypatch.setattr(phase5_cli, "_request_for_attempt", request_for_attempt)
    monkeypatch.setattr(
        phase5_cli,
        "invoke_host_builder",
        lambda _adapter, request, **_kwargs: BuilderResponse(
            Phase5Status.PASS,
            request.invocation_id,
            "not-json-artifact",
            True,
            "OBSERVED",
        ),
    )
    monkeypatch.setattr(
        phase5_cli,
        "extract_response_artifact",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ArtifactCaptureError("invalid")),
    )

    result = phase5_cli._run_builder(preflight, writer)
    assert len(requests) == Phase5Budget().max_builder_invocations
    assert result["status"] is Phase5Status.BLOCKED
    assert result["builder_receipt"]["attempt_count"] == 2
    assert result["builder_receipt"]["artifact_id"] is None


@pytest.mark.parametrize(
    ("attempt_count", "expected"),
    ((True, "no successful attempt budget"), (2, "invocation budget is exhausted")),
)
def test_phase5_repair_rejects_invalid_or_exhausted_builder_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attempt_count: object,
    expected: str,
) -> None:
    preflight = _phase5_preflight(tmp_path)
    evidence_root = tmp_path / "repair-evidence"
    evidence_root.mkdir()
    arguments = _patch_repair_entrypoint(monkeypatch, preflight, evidence_root)
    (evidence_root / "builder-invocation-receipt.json").write_text(
        json.dumps({"attempt_count": attempt_count}),
        encoding="utf-8",
    )

    with pytest.raises(phase5_cli.Phase5CliError, match=expected):
        phase5_cli._repair(tmp_path, arguments)


def test_phase5_repair_requires_the_v1_receipt_before_any_repair_side_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preflight = _phase5_preflight(tmp_path)
    evidence_root = tmp_path / "repair-evidence"
    evidence_root.mkdir()
    arguments = _patch_repair_entrypoint(monkeypatch, preflight, evidence_root)

    with pytest.raises(phase5_cli.Phase5CliError, match="receipt is required"):
        phase5_cli._repair(tmp_path, arguments)
    assert not (evidence_root / "builder-repair-receipt.json").exists()


def test_phase5_repair_fails_closed_when_exact_host_binding_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preflight = _phase5_preflight(tmp_path)
    preflight = replace(preflight, binding=None)
    evidence_root = tmp_path / "repair-evidence"
    evidence_root.mkdir()
    arguments = _patch_repair_entrypoint(monkeypatch, preflight, evidence_root)
    v1_artifact = _repair_artifact(preflight.task, "artifact_v1")
    _patch_repair_evidence(monkeypatch, preflight.task, v1_artifact)
    (evidence_root / "builder-invocation-receipt.json").write_text(
        json.dumps({"attempt_count": 1}),
        encoding="utf-8",
    )

    with pytest.raises(phase5_cli.Phase5CliError, match="exact builder or host binding"):
        phase5_cli._repair(tmp_path, arguments)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    (
        ({"critique_benchmark_id": "wrong"}, "benchmark is not bound"),
        ({"critique_run_id": "wrong"}, "run is not bound"),
        ({"critique_packet_digest": _DIGEST_ZERO}, "packet digest is not bound"),
        ({"critique_artifact_digest": _DIGEST_ZERO}, "not bound to the current artifact"),
    ),
)
def test_phase5_repair_rejects_critique_evidence_bound_to_the_wrong_packet_or_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, str],
    expected: str,
) -> None:
    preflight = _phase5_preflight(tmp_path)
    evidence_root = tmp_path / "repair-evidence"
    evidence_root.mkdir()
    arguments = _patch_repair_entrypoint(monkeypatch, preflight, evidence_root)
    v1_artifact = _repair_artifact(preflight.task, "artifact_v1")
    _patch_repair_evidence(monkeypatch, preflight.task, v1_artifact, **kwargs)
    (evidence_root / "builder-invocation-receipt.json").write_text(
        json.dumps({"attempt_count": 1}),
        encoding="utf-8",
    )

    with pytest.raises(phase5_cli.Phase5CliError, match=expected):
        phase5_cli._repair(tmp_path, arguments)


def test_phase5_repair_rejects_an_existing_v2_receipt_with_the_wrong_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preflight = _phase5_preflight(tmp_path)
    evidence_root = tmp_path / "repair-evidence"
    evidence_root.mkdir()
    arguments = _patch_repair_entrypoint(monkeypatch, preflight, evidence_root)
    v1_artifact = _repair_artifact(preflight.task, "artifact_v1")
    v2_artifact = _repair_artifact(
        preflight.task,
        "artifact_v2",
        parent_artifact_digest=_DIGEST_ZERO,
    )
    _patch_repair_evidence(
        monkeypatch,
        preflight.task,
        v1_artifact,
        repair_receipt={
            "repair_correction": "tighten contrast",
            "status": "PASS",
            "artifact_version": "artifact_v2",
        },
    )
    monkeypatch.setattr(
        phase5_cli,
        "_artifact_from_receipt",
        lambda _task, _receipt, *, version="artifact_v1", expected_identity=None: (
            v1_artifact if version == "artifact_v1" else v2_artifact
        ),
    )
    (evidence_root / "builder-invocation-receipt.json").write_text(
        json.dumps({"attempt_count": 1}),
        encoding="utf-8",
    )
    (evidence_root / "builder-repair-receipt.json").write_text(
        json.dumps(
            {
                "repair_correction": "tighten contrast",
                "status": "PASS",
                "artifact_version": "artifact_v2",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(phase5_cli.Phase5CliError, match="not chained to artifact_v1"):
        phase5_cli._repair(tmp_path, arguments)


def test_phase5_repair_returns_fail_when_host_response_has_no_materializable_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    preflight = _phase5_preflight(tmp_path)
    evidence_root = tmp_path / "repair-evidence"
    evidence_root.mkdir()
    arguments = _patch_repair_entrypoint(monkeypatch, preflight, evidence_root)
    v1_artifact = _repair_artifact(preflight.task, "artifact_v1")
    _patch_repair_evidence(monkeypatch, preflight.task, v1_artifact)
    (evidence_root / "builder-invocation-receipt.json").write_text(
        json.dumps({"attempt_count": 1}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        phase5_cli,
        "invoke_host_builder",
        lambda *_args, **_kwargs: BuilderResponse(
            Phase5Status.FAIL,
            "INV-REPAIR-FAIL",
            None,
            False,
            "UNKNOWN",
            "HOST_FAILED",
        ),
    )

    result = phase5_cli._repair(tmp_path, arguments)

    assert result["status"] is Phase5Status.FAIL
    assert result["repair_receipt"]["artifact_id"] is None
    assert result["repair_receipt"]["error_code"] == "HOST_FAILED"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        (lambda value: value.update(benchmark_id="wrong"), "task identity is invalid"),
        (lambda value: value.update(run_id="wrong"), "task identity is invalid"),
        (lambda value: value["artifact"].update(digest=_DIGEST_ZERO), "artifact is not bound"),
        (lambda value: value.update(renders=[]), "has no renders"),
        (lambda value: value.update(renders=[None]), "render is invalid"),
        (
            lambda value: value["renders"][0].update(viewport={"width": 1}),
            "render binding is invalid",
        ),
        (
            lambda value: value["renders"][0].update(artifact_version="artifact_v2"),
            "render binding is invalid",
        ),
        (lambda value: value["renders"][0].update(digest=_DIGEST_ZERO), "render is stale"),
        (lambda value: value.update(packet_digest=_DIGEST_ZERO), "packet digest is stale"),
    ),
)
def test_phase5_blind_packet_revalidation_rejects_each_stale_or_mismatched_binding(
    tmp_path: Path, mutation, expected: str
) -> None:
    task, artifact, _render, _packet, payload = _packet_fixture(tmp_path)
    mutation(payload)
    with pytest.raises(phase5_cli.Phase5CliError, match=expected):
        phase5_cli._bound_packet_from_evidence(task, artifact, payload, tmp_path / "renders")


def test_phase5_blind_packet_revalidation_returns_the_exact_bound_packet(tmp_path: Path) -> None:
    task, artifact, _render, packet, payload = _packet_fixture(tmp_path)
    result = phase5_cli._bound_packet_from_evidence(task, artifact, payload, tmp_path / "renders")
    assert result == packet


def test_routing_deduplicates_duplicate_explicit_provider_and_capability_requests() -> None:
    task = replace(profile(), research_need=cast(Any, profile().research_need))
    provider = _capability("shared-provider", CapabilityPrimaryType.PROVIDER)
    decision = minimum_route(
        task,
        CapabilityRegistry.from_manifests((provider,)),
        explicit_provider=provider.capability_id,
        explicit_capabilities=(provider.capability_id,),
    )
    assert decision.route_status is RouteStatus.SELECTED
    assert decision.route_kind is RouteKind.PROVIDER
    assert tuple(item.capability_id for item in decision.selected) == (provider.capability_id,)


def test_routing_rejects_explicit_capability_that_is_out_of_profile_scope() -> None:
    task = replace(profile(), domain=TaskDomain.ENGINEERING)
    api_only = _capability("api-only", CapabilityPrimaryType.SPECIALIST, domains=("API",))
    decision = minimum_route(
        task,
        CapabilityRegistry.from_manifests((api_only,)),
        explicit_capabilities=(api_only.capability_id,),
    )
    assert decision.route_status is RouteStatus.REJECTED
    assert decision.selected == ()
    assert decision.omitted[0].reason_code is OmittedReasonCode.OUT_OF_SCOPE
    assert "CAPABILITY_SCOPE_MISMATCH" in decision.unresolved


def test_routing_invalid_profile_produces_a_valid_rejected_envelope() -> None:
    decision = minimum_route(cast(Any, object()), CapabilityRegistry())
    assert decision.route_status is RouteStatus.REJECTED
    assert decision.route_kind is RouteKind.DEGRADED
    assert decision.unresolved == ("INVALID_PROFILE",)
