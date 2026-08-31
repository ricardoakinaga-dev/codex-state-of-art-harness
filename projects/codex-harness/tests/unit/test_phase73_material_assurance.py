from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_phase2_adversarial import _graph as legacy_graph
from test_phase2_adversarial import _node as legacy_node
from test_phase4_host import FakeAppServerClient, _request
from test_phase71_phase4_hardening import _host_result
from test_phase71_phase6_hardening import (
    make_artifact_ref,
    make_evidence,
    make_evidence_ref,
    make_input,
    make_result,
)
from test_phase72_phase3_remaining_assurance import _inventory, _write_skill

import harness_kernel.phase4_host as phase4_host
import harness_kernel.phase6_checks as phase6_checks
import harness_kernel.phase6_host as phase6_host
import harness_kernel.phase6_verifier as phase6_verifier
import harness_kernel.phase7_host as phase7_host
import harness_kernel.registry as registry
import harness_kernel.validation as validation
from harness_kernel.classification import (
    DimensionAssessment,
    _assessment_value,
    _enum,
    _security_assessment,
    _tuple_strings,
    classify_task,
)
from harness_kernel.graph import execute_graph, validate_execution_graph
from harness_kernel.models import NodeBudget
from harness_kernel.phase3_discovery import CapabilityDiscovery, _load_json
from harness_kernel.phase3_models import (
    CapabilityKind,
    CapabilityLifecycle,
    ObservationStatus,
    Phase3Limits,
    RootScope,
)
from harness_kernel.phase3_resolution import ResolutionEngine, ResolutionError
from harness_kernel.phase3_telemetry import Phase3Telemetry, TelemetryError
from harness_kernel.phase4_models import Phase4Budget
from harness_kernel.phase4_policy import Phase4PolicyError, PilotRule
from harness_kernel.phase5_verification import parse_blind_critique
from harness_kernel.phase6_checks import run_deterministic_procedure
from harness_kernel.phase6_models import (
    Claim,
    CriterionResult,
    FreshnessStatus,
    ProcedureResult,
    ProcedureSpec,
    VerificationBudget,
    VerificationOutput,
    VerificationRole,
    VerificationStatus,
)
from harness_kernel.phase6_telemetry import (
    Phase6Telemetry,
    Phase6TelemetryError,
    Phase6TelemetryEvent,
)
from harness_kernel.phase6_verifier import Phase6VerificationError, verify_input
from harness_kernel.registry import parse_version_range

DIGEST = "sha256:" + "a" * 64


def test_validation_rejects_a_timezone_naive_timestamp() -> None:
    findings: list[object] = []

    validation._timestamp("2026-08-31T12:00:00", "$.timestamp", findings)  # type: ignore[arg-type]

    assert len(findings) == 1
    assert findings[0].code is validation.ValidationCode.INVALID_TIMESTAMP  # type: ignore[union-attr]
    assert "explicit timezone" in findings[0].message  # type: ignore[union-attr]


def test_phase3_host_existing_dir_rejects_missing_required_directory(tmp_path: Path) -> None:
    from harness_kernel.phase3_host import CodexHostAdapter, HostAdapterError

    with pytest.raises(HostAdapterError, match="project_root is unavailable"):
        CodexHostAdapter(project_root=tmp_path / "missing")


def test_phase4_policy_rejects_invalid_capability_identity() -> None:
    with pytest.raises(Phase4PolicyError, match="capability_id is invalid"):
        PilotRule("../escape", "1.0.0", DIGEST)


def test_phase3_telemetry_rejects_unknown_explicit_stage() -> None:
    with pytest.raises(TelemetryError, match="host stage event type is invalid"):
        Phase3Telemetry().record_event(
            "not-an-event",  # type: ignore[arg-type]
            "safe-capability",
            ObservationStatus.OBSERVED,
        )


def test_phase6_telemetry_rejects_unknown_event_type() -> None:
    with pytest.raises(Phase6TelemetryError, match="event_type is invalid"):
        Phase6TelemetryEvent(
            event_id="P73-EVT-INVALID",
            event_type="not-an-event",  # type: ignore[arg-type]
            run_id="RUN-P73",
            task_id="TASK-P73",
            capability_id="verification-loop-vnext",
            observed=True,
        )


def test_phase4_result_rejects_completion_before_start() -> None:
    with pytest.raises(ValueError, match="completed_at cannot precede started_at"):
        replace(
            _host_result(phase4_host.InvocationResultStatus.SUCCESS), completed_at=1_699_999_999
        )


def test_phase4_string_collection_normalizes_none() -> None:
    assert phase4_host._as_tuple(()) == () if hasattr(phase4_host, "_as_tuple") else True
    from harness_kernel.phase4_models import _as_tuple

    assert _as_tuple(None) == ()


def test_phase7_host_cleanup_terminates_a_process_still_alive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_root = tmp_path / "tests"
    test_root.mkdir()

    class LiveProcess:
        stdout = object()
        returncode = None

        def poll(self) -> None:
            return None

    class EmptySelector:
        def register(self, *_args: object) -> None:
            return None

        def get_map(self) -> dict[object, object]:
            return {}

        def close(self) -> None:
            return None

    process = LiveProcess()
    terminated: list[object] = []
    monkeypatch.setattr(phase7_host, "_fixed_test_command", lambda _root: ["fake"])
    monkeypatch.setattr(phase7_host.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(phase7_host.selectors, "DefaultSelector", EmptySelector)
    monkeypatch.setattr(
        phase7_host,
        "_terminate_process",
        lambda current: terminated.append(current),
    )

    observation = phase7_host.run_fixed_pytest(test_root)

    assert observation.exit_code == 124
    assert terminated == [process]


def test_phase3_models_normalize_optional_collections_without_mutation() -> None:
    from harness_kernel.phase3_models import _as_tuple, _map_proxy

    assert _as_tuple(None) == ()
    assert dict(_map_proxy(None)) == {}


def test_phase3_discovery_rejects_non_object_manifest_json() -> None:
    assert _load_json(b"[]") == (None, "manifest JSON must be an object")


def test_phase3_discovery_preserves_legacy_skill_contract(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    package = root / "legacy"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_text("# Legacy\nUse as data only.\n", encoding="utf-8")

    inventory = CapabilityDiscovery(Phase3Limits()).scan(
        (
            __import__("harness_kernel.phase3_models", fromlist=["CapabilityRoot"]).CapabilityRoot(
                "legacy-root", RootScope.PROJECT, str(root)
            ),
        )
    )

    record = next(item for item in inventory.capabilities if item.path == str(package))
    assert record.kind is CapabilityKind.LEGACY
    assert record.status is CapabilityLifecycle.REJECTED


def test_phase3_resolution_rejects_invalid_request_and_explicit_pin(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    _write_skill(root, "demo", capability_id="demo")
    inventory = _inventory((root, RootScope.PROJECT))
    engine = ResolutionEngine()

    with pytest.raises(ResolutionError, match="capability request is invalid"):
        engine.resolve(inventory, "../escape")
    with pytest.raises(ResolutionError, match="explicit version pin is invalid"):
        engine.resolve(inventory, "demo", explicit_pins={"demo": "not-semver"})


def test_phase3_resolution_rejects_malformed_unversioned_and_empty_requests(
    tmp_path: Path,
) -> None:
    root = tmp_path / "skills"
    _write_skill(root, "demo", capability_id="demo")
    inventory = _inventory((root, RootScope.PROJECT))
    engine = ResolutionEngine()

    for request in ("", "bad id", "bad\x00id"):
        with pytest.raises(ResolutionError, match="capability request is invalid"):
            engine.resolve(inventory, request)


def test_registry_blank_range_is_explicitly_unbounded() -> None:
    assert parse_version_range("") == parse_version_range("*")


def test_registry_bounds_fail_closed_for_wildcards_and_non_string_versions() -> None:
    with pytest.raises(registry.SemVerError, match="version must be a string"):
        registry.SemVer.parse(1)  # type: ignore[arg-type]
    with pytest.raises(registry.SemVerError, match="no upper bound"):
        registry._next_bound((None, None, None))
    assert registry._next_bound((1, 2, 3)) == registry.SemVer(1, 2, 4)
    assert registry._caret_bounds((None, None, None))[1] == registry.SemVer(1, 0, 0)
    assert registry._tilde_bounds((None, None, None))[1] == registry.SemVer(1, 0, 0)
    with pytest.raises(registry.SemVerError, match="invalid semver"):
        registry.SemVer.parse("1.0.0-a..b")


def test_graph_rejects_negative_budgets_and_invalid_limits_before_execution() -> None:
    graph = legacy_graph(legacy_node("NODE-1"))
    invalid_node = replace(graph.nodes[0], budget=replace(graph.nodes[0].budget, tokens=-1))
    invalid_graph = replace(graph, nodes=(invalid_node,))
    result = validate_execution_graph(invalid_graph)
    assert not result.is_valid
    assert any("node tokens must be non-negative" in item.message for item in result.findings)

    invalid_duration = replace(
        graph.nodes[0], budget=replace(graph.nodes[0].budget, duration_ms=-1)
    )
    invalid_node_graph = replace(graph, nodes=(invalid_duration,))
    result = validate_execution_graph(invalid_node_graph)
    assert any("node duration must be non-negative" in item.message for item in result.findings)

    invalid_graph_budget = replace(graph, graph_budget=NodeBudget(tokens=-1, duration_ms=-1))
    result = validate_execution_graph(invalid_graph_budget)
    assert any("graph tokens must be non-negative" in item.message for item in result.findings)
    assert any("graph duration must be non-negative" in item.message for item in result.findings)

    invalid_max_nodes = validate_execution_graph(graph, max_nodes=0)
    assert any(
        "max_nodes must be a positive integer" in item.message
        for item in invalid_max_nodes.findings
    )

    with pytest.raises(ValueError, match="max_invocations"):
        execute_graph(graph, lambda node: node.node_id, max_invocations=-1)
    with pytest.raises(ValueError, match="max_duration_ms"):
        execute_graph(graph, lambda node: node.node_id, max_duration_ms=-1)


def test_graph_invocation_budget_blocks_the_unexecuted_node() -> None:
    graph = legacy_graph(legacy_node("NODE-1"), legacy_node("NODE-2"))
    outcomes = execute_graph(graph, lambda node: node.node_id, max_invocations=1)

    assert outcomes[0].status.value == "SUCCEEDED"
    assert outcomes[1].status.value == "BLOCKED"
    assert outcomes[1].failure is not None
    assert outcomes[1].failure.code == "GRAPH_INVOCATION_BUDGET"


def test_phase6_optional_text_and_public_projection_handle_none_and_primitives() -> None:
    import harness_kernel.phase6_models as models

    assert models._optional_text(None, "optional") is None
    assert models._optional_text("kept", "optional") == "kept"
    assert models._public(42) == 42
    assert models._public(None) is None


def test_verification_output_without_input_keeps_claims_and_not_run_status() -> None:
    output = VerificationOutput(
        input_digest=DIGEST,
        run_id="RUN-P73-OUTPUT",
        task_id="TASK-P73-OUTPUT",
        capability_id="verification-loop-vnext",
        package_digest=DIGEST,
        manifest_digest=DIGEST,
        criterion_results=(),
        status=VerificationStatus.UNKNOWN,
        claims=(),
        input=None,
    )

    assert output.status is VerificationStatus.NOT_RUN
    assert output.claims == ()
    assert output.freshness_status is FreshnessStatus.UNKNOWN


def test_verification_output_without_input_cannot_claim_pass(tmp_path: Path) -> None:
    evidence = make_evidence()
    verification_input = make_input(
        tmp_path,
        artifacts=(make_artifact_ref(str(tmp_path / "workspace")),),
        evidence_refs=(make_evidence_ref(evidence),),
    )
    procedure_result = make_result(verification_input, evidence=(evidence,))
    criterion = procedure_result.as_criterion_result(
        verification_input.claims[0],
        status=VerificationStatus.PASS,
    )

    with pytest.raises(ValueError, match="PASS output requires a bound verification input"):
        VerificationOutput(
            input_digest=DIGEST,
            run_id="RUN-P73-PASS",
            task_id="TASK-P73-PASS",
            capability_id="verification-loop-vnext",
            package_digest=DIGEST,
            manifest_digest=DIGEST,
            criterion_results=(criterion,),
            input=None,
        )


def test_verification_output_preserves_supplied_claims_without_input() -> None:
    claim = Claim("C-P73-SUPPLIED", "bounded claim")
    output = VerificationOutput(
        input_digest=DIGEST,
        run_id="RUN-P73-SUPPLIED",
        task_id="TASK-P73-SUPPLIED",
        capability_id="verification-loop-vnext",
        package_digest=DIGEST,
        manifest_digest=DIGEST,
        criterion_results=(),
        claims=(claim,),
        input=None,
    )

    assert output.claims == (claim,)
    assert output.status is VerificationStatus.NOT_RUN


def test_verification_output_freshness_without_input_is_unknown() -> None:
    import harness_kernel.phase6_models as models

    assert models._output_freshness(None, ()) is FreshnessStatus.UNKNOWN


def test_phase6_model_helpers_preserve_optional_and_opaque_values() -> None:
    import harness_kernel.phase4_models as phase4_models
    import harness_kernel.phase6_models as phase6_models

    assert phase6_models._optional_text("kept", "optional") == "kept"
    assert isinstance(phase6_models._public(object()), str)
    frozen = phase4_models._freeze_mapping(None)
    assert dict(frozen) == {}
    with pytest.raises(TypeError):
        frozen["blocked"] = "mutation"  # type: ignore[index]


def test_verification_output_rejects_invalid_reviewer_role() -> None:
    with pytest.raises(ValueError, match="reviewer must be an identified REVIEWER"):
        VerificationOutput(
            input_digest=DIGEST,
            run_id="RUN-P73-ROLE",
            task_id="TASK-P73-ROLE",
            capability_id="verification-loop-vnext",
            package_digest=DIGEST,
            manifest_digest=DIGEST,
            criterion_results=(),
            reviewer_id="independent-reviewer",
            reviewer_role=VerificationRole.VERIFIER,
            input=None,
        )


def test_verification_output_rejects_reviewer_who_produced_artifact(tmp_path: Path) -> None:
    artifact = make_artifact_ref(str(tmp_path / "workspace"))
    evidence = make_evidence()
    verification_input = make_input(
        tmp_path,
        artifacts=(artifact,),
        evidence_refs=(make_evidence_ref(evidence),),
    )
    result = make_result(verification_input, evidence=(evidence,))
    criterion = result.as_criterion_result(
        verification_input.claims[0], status=VerificationStatus.PASS
    )

    with pytest.raises(ValueError, match="reviewer cannot be the artifact producer"):
        VerificationOutput.from_input(
            verification_input,
            (criterion,),
            reviewer_id=artifact.producer_id,
            reviewer_role=VerificationRole.REVIEWER,
        )


def test_verification_output_enforces_the_report_byte_budget(tmp_path: Path) -> None:
    verification_input = make_input(
        tmp_path,
        budgets=VerificationBudget(max_report_bytes=1),
    )
    criterion = make_result(
        verification_input,
        status=VerificationStatus.BLOCKED,
        executed=False,
    ).as_criterion_result(
        verification_input.claims[0],
        status=VerificationStatus.BLOCKED,
    )

    with pytest.raises(ValueError, match="report byte budget"):
        VerificationOutput.from_input(verification_input, (criterion,))


def test_verification_output_rejects_an_unbound_procedure_result() -> None:
    procedure = ProcedureSpec("PROC-P73-BOUND", "C-P73-BOUND", "bounded procedure")
    mismatched = ProcedureResult(
        spec=ProcedureSpec("PROC-P73-OTHER", "C-P73-BOUND", "different procedure")
    )

    with pytest.raises(ValueError, match="procedure result is not bound"):
        CriterionResult(
            criterion_id="C-P73-BOUND",
            claim=Claim("C-P73-BOUND", "bounded claim"),
            procedure=procedure,
            procedure_result=mismatched,
        )


def test_procedure_result_without_spec_cannot_be_projected_to_a_criterion() -> None:
    result = ProcedureResult(procedure_id="PROC-P73", criterion_id="C-P73")
    object.__setattr__(result, "spec", None)

    with pytest.raises(ValueError, match="missing its spec"):
        result.as_criterion_result(Claim("C-P73", "claim"))


def test_criterion_result_without_procedure_is_not_observed() -> None:
    criterion = CriterionResult(
        criterion_id="C-P73-OBS",
        claim=Claim("C-P73-OBS", "claim"),
        procedure=ProcedureSpec("PROC-P73-OBS", "C-P73-OBS", "procedure"),
    )

    assert criterion.observed == "not observed"


def test_phase6_checks_return_blocked_for_missing_declared_artifacts(tmp_path: Path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-P73",))
    checks = (
        ("PATH_EXISTS", {}),
        ("TEXT_CONTAINS", {"text": "needle"}),
        ("TEXT_ABSENT", {"text": "needle"}),
        ("JSON_OBJECT", {}),
        (
            "BROWSER_CAPTURE",
            {
                "source_artifact_id": "SOURCE",
                "desktop_artifact_id": "DESKTOP",
                "mobile_artifact_id": "MOBILE",
            },
        ),
    )
    for index, (name, parameters) in enumerate(checks, start=1):
        procedure = ProcedureSpec(
            f"PROC-P73-{index}",
            "C-P73",
            f"missing {name}",
            check=name,
            parameters={"artifact_id": "MISSING", **parameters},
        )
        result = run_deterministic_procedure(verification_input, procedure)
        assert result.status is VerificationStatus.BLOCKED


def test_phase6_browser_capture_requires_source_and_render_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = make_artifact_ref(str(tmp_path / "workspace"), artifact_id="MANIFEST")
    verification_input = make_input(
        tmp_path,
        criteria=("C-P73",),
        artifacts=(target,),
    )
    monkeypatch.setattr(
        phase6_checks,
        "_read_artifact",
        lambda _input, _procedure: (target, b"{}"),
    )
    procedure = ProcedureSpec(
        "PROC-P73-BROWSER-REFS",
        "C-P73",
        "browser references",
        check="BROWSER_CAPTURE",
        parameters={
            "artifact_id": target.artifact_id,
            "source_artifact_id": "SOURCE",
            "desktop_artifact_id": "DESKTOP",
            "mobile_artifact_id": "MOBILE",
        },
    )

    result = run_deterministic_procedure(verification_input, procedure)

    assert result.status is VerificationStatus.BLOCKED
    assert result.error == "browser capture artifact references are incomplete"


def test_phase6_browser_capture_blocks_when_a_capture_cannot_be_reopened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    digest = "sha256:" + "b" * 64
    target = make_artifact_ref(str(workspace), artifact_id="MANIFEST")
    source = replace(make_artifact_ref(str(workspace), artifact_id="SOURCE"), size_bytes=1)
    desktop = replace(make_artifact_ref(str(workspace), artifact_id="DESKTOP"), size_bytes=1)
    mobile = replace(make_artifact_ref(str(workspace), artifact_id="MOBILE"), size_bytes=1)
    verification_input = make_input(
        tmp_path,
        criteria=("C-P73",),
        artifacts=(target, source, desktop, mobile),
    )
    payload = {
        "schema_version": "P6-BROWSER-CAPTURE-1",
        "task_id": verification_input.task_id,
        "run_id": verification_input.run_id,
        "criteria_digest": DIGEST,
        "artifact_id": source.artifact_id,
        "artifact_version": source.version,
        "url": "http://127.0.0.1:8000/",
        "browser": {
            "url": "http://127.0.0.1:8000/",
            "task_id": verification_input.task_id,
            "run_id": verification_input.run_id,
            "criteria_digest": DIGEST,
            "artifact_id": source.artifact_id,
            "artifact_version": source.version,
        },
        "source": {
            "path": source.path,
            "digest": source.digest,
            "bytes": source.size_bytes,
            "served_digest": source.digest,
            "served_bytes": source.size_bytes,
            "served_matches_declared": True,
        },
        "captures": [{"path": str(workspace / "missing.png"), "digest": digest, "bytes": 1}],
    }
    manifest = json.dumps(payload).encode("utf-8")
    monkeypatch.setattr(
        phase6_checks,
        "_read_artifact",
        lambda _input, _procedure: (target, manifest),
    )
    calls = 0

    def reopen_declared(*_args: object, **_kwargs: object) -> tuple[Path, bytes] | None:
        nonlocal calls
        calls += 1
        return (Path(source.path), b"x") if calls == 1 else None

    monkeypatch.setattr(phase6_checks, "_read_declared_file", reopen_declared)
    procedure = ProcedureSpec(
        "PROC-P73-BROWSER-CAPTURE",
        "C-P73",
        "browser capture",
        check="BROWSER_CAPTURE",
        parameters={
            "artifact_id": target.artifact_id,
            "task_id": verification_input.task_id,
            "run_id": verification_input.run_id,
            "criteria_digest": DIGEST,
            "expected_digest": target.digest,
            "source_artifact_id": source.artifact_id,
            "source_artifact_digest": source.digest,
            "desktop_artifact_id": desktop.artifact_id,
            "desktop_digest": desktop.digest,
            "mobile_artifact_id": mobile.artifact_id,
            "mobile_digest": mobile.digest,
        },
    )

    result = run_deterministic_procedure(verification_input, procedure)

    assert calls == 2
    assert result.status is VerificationStatus.FAIL
    assert result.error == "browser capture manifest is not bound"


def test_phase6_verifier_rejects_result_without_spec(tmp_path: Path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-P73",))
    result = make_result(verification_input, criterion_id="C-P73", status=VerificationStatus.FAIL)
    object.__setattr__(result, "spec", None)

    with pytest.raises(Phase6VerificationError, match="missing its spec"):
        verify_input(verification_input, (result,))


def test_phase6_verifier_result_projection_rejects_missing_spec(tmp_path: Path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-P73-RESULT",))
    result = make_result(
        verification_input,
        criterion_id="C-P73-RESULT",
        status=VerificationStatus.FAIL,
    )
    object.__setattr__(result, "spec", None)

    with pytest.raises(Phase6VerificationError, match="missing its spec"):
        phase6_verifier._result_for(
            verification_input,
            "C-P73-RESULT",
            result,
            reviewer_role=None,
        )


def test_phase6_verifier_claims_declared_visual_criterion(tmp_path: Path) -> None:
    import harness_kernel.phase6_verifier as verifier

    verification_input = make_input(
        tmp_path,
        criteria=("C-1",),
    )
    claim = verifier._claim(verification_input, "C-1")
    assert claim.criterion_id == "C-1"


def test_phase6_telemetry_and_phase4_host_event_normalize_protocol_inputs() -> None:
    event = phase4_host.CodexAppServerAdapter()._event_from_message(
        {
            "method": "skill/loaded",
            "params": {"skillName": "verification-loop-vnext"},
        },
        sequence=0,
    )
    assert event.detail == "verification-loop-vnext"


def test_phase6_telemetry_record_rejects_invalid_event_type(tmp_path: Path) -> None:
    verification_input = make_input(tmp_path)

    with pytest.raises(Phase6TelemetryError, match="event_type is invalid"):
        Phase6Telemetry().record("not-an-event", verification_input)  # type: ignore[arg-type]


def test_phase6_host_discovery_reports_missing_instruction_kernel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        phase6_host.SafeCapabilityLoader,
        "load",
        lambda _self, _record, _level: SimpleNamespace(
            context_prepared=False,
            instruction_kernel=None,
            host_load=SimpleNamespace(status=SimpleNamespace(value="HOST_LOAD_UNOBSERVABLE")),
        ),
    )

    snapshot = phase6_host.discover_vnext_package(Path(__file__).parents[2])

    assert "INSTRUCTION_KERNEL_UNAVAILABLE" in snapshot.blockers
    assert snapshot.instruction_loaded is False


def test_phase4_host_client_fails_closed_without_a_resolved_binding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter = phase4_host.CodexAppServerAdapter()
    monkeypatch.setattr(adapter, "_resolved_host_binding", lambda: None)

    with pytest.raises(phase4_host.HostProtocolError, match="HOST_EXECUTABLE_UNAVAILABLE"):
        adapter._client(tmp_path)


def test_phase4_subprocess_read_requires_stdout() -> None:
    client = object.__new__(phase4_host._SubprocessClient)
    client._process = SimpleNamespace(stdout=None)

    with pytest.raises(phase4_host.HostProtocolError, match="stdout is unavailable"):
        client._read(1)


def test_phase4_subprocess_read_rejects_process_exit_before_response() -> None:
    client = object.__new__(phase4_host._SubprocessClient)
    client._process = SimpleNamespace(stdout=SimpleNamespace(fileno=lambda: 1), poll=lambda: 1)
    client._stdout_buffer = b""
    client.max_line_bytes = 1024

    with pytest.raises(phase4_host.HostProtocolError, match="exited before returning"):
        client._read(1)


def test_phase7_host_helpers_fail_closed_when_policy_or_kernel_context_is_missing(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    verifier = phase7_host.BackendVerifierAppServerAdapter()
    with pytest.raises(ValueError, match="filesystem policy is not host-bound"):
        verifier._policy_for_request(request)

    builder = phase7_host.BackendBuilderAppServerAdapter()
    params = {"input": [{"type": "text", "text": "request"}]}
    assert builder._with_instruction_kernel(params) == params

    loop = phase7_host.VerificationLoopVNextAppServerAdapter(
        trusted_authorization=request.authorization,
    )
    turn_params = loop._turn_params(request, "thread")
    assert isinstance(turn_params["input"], list)


def test_phase7_builder_write_without_tool_context_is_explicitly_denied(
    tmp_path: Path,
) -> None:
    adapter = phase7_host.BackendBuilderAppServerAdapter(
        transport_factory=lambda: FakeAppServerClient(),
    )
    event_paths = adapter._event_paths_context.set(set())
    try:
        result = adapter._handle_host_request(
            {
                "id": "CALL-P73",
                "method": "item/tool/call",
                "params": {
                    "callId": "CALL-P73",
                    "tool": phase7_host.HOST_WRITE_FILE_TOOL,
                    "arguments": {"path": "app/output.py", "content": "pass\n"},
                },
            },
            SimpleNamespace(respond=lambda *_args: None),
            [],
            Phase4Budget(timeout_seconds=1, max_host_events=8),
        )
    finally:
        adapter._event_paths_context.reset(event_paths)

    assert result == (True, "HOST_TOOL_CONTEXT_MISSING")


def test_phase7_verifier_package_discovery_without_configured_package_is_false(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    verifier = phase7_host.BackendVerifierAppServerAdapter(
        filesystem_policy=phase7_host.build_backend_filesystem_policy(tmp_path),
        project_root=tmp_path,
        package_path=None,
    )
    assert verifier._skill_is_discovered({}, request) is False


def test_classification_explicit_security_hint_is_preserved() -> None:
    from harness_kernel.classification import Confidence, SecurityImpact

    result = _security_assessment(
        "inspect one local file",
        {"security_impact": "LOW"},
        (),
        Confidence.MEDIUM,
    )
    assert result.value is SecurityImpact.LOW
    assert result.confidence is Confidence.HIGH


def test_classification_explicit_dimensions_are_normalized_as_contract_data() -> None:
    profile = classify_task(
        "Implement a bounded local task",
        task_id="TASK-P73-CLASSIFICATION",
        run_id="RUN-P73-CLASSIFICATION",
        evidence_refs=("EVID-P73-CLASSIFICATION",),
        created_at="2026-08-31T12:00:00Z",
        hints={
            "domain": "engineering",
            "complexity": "small",
            "risk": "low",
            "security_impact": "none",
            "data_impact": "local",
            "user_impact": "internal",
            "visual_importance": "none",
            "research_need": "none",
            "parallelism_potential": "none",
            "reversibility": "easy",
            "blast_radius": "module",
            "confidence": "high",
        },
    )

    assert profile.complexity.value == "SMALL"
    assert profile.data_impact.value == "LOCAL"
    assert profile.visual_importance.value == "NONE"
    assert profile.research_need.value == "NONE"
    assert profile.parallelism_potential.value == "NONE"
    assert profile.reversibility.value == "EASY"
    assert profile.user_impact.value == "INTERNAL"
    assert profile.confidence.value == "HIGH"


def test_classification_helpers_fail_closed_at_type_and_optional_collection_boundaries() -> None:
    from harness_kernel.models import Complexity

    assert _tuple_strings(None) == ()
    with pytest.raises(TypeError, match="expected Complexity or string"):
        _enum(Complexity, object())
    assessment = DimensionAssessment(
        dimension="complexity",
        value="not-an-enum",
        reason="test",
        confidence="HIGH",
    )
    with pytest.raises(TypeError, match="must contain Complexity"):
        _assessment_value(assessment, Complexity)


def test_phase5_blind_critique_normalizes_dimension_mapping() -> None:
    payload = {
        "packet_digest": DIGEST,
        "artifact_digest": DIGEST,
        "blinded": True,
        "builder_rationale_withheld": True,
        "self_score_withheld": True,
        "independence": "INDEPENDENT",
        "verdict": "PASS",
        "dimension_scores": {"clarity": 80},
    }

    critique = parse_blind_critique(payload, packet_digest=DIGEST)

    assert critique.dimension_scores["clarity"] == 8.0


def test_phase5_blind_critique_treats_non_mapping_scores_as_empty() -> None:
    payload = {
        "packet_digest": DIGEST,
        "artifact_digest": DIGEST,
        "blinded": True,
        "builder_rationale_withheld": True,
        "self_score_withheld": True,
        "independence": "INDEPENDENT",
        "verdict": "PASS",
        "dimension_scores": [],
    }

    critique = parse_blind_critique(payload, packet_digest=DIGEST)

    assert critique.dimension_scores == {}
