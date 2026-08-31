from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from test_contracts import all_records

import harness_kernel.telemetry as telemetry_module
from harness_kernel.authority import AuthorityScope, check_invocation_authority
from harness_kernel.benchmarks import _load_manifest
from harness_kernel.errors import FailureCategory, FailureDetail
from harness_kernel.graph import _normalized_failure, validate_execution_graph
from harness_kernel.models import (
    ClaimStatus,
    Confidence,
    FindingSeverity,
    GateSummary,
    InvocationStatus,
)
from harness_kernel.phase5_benchmarks import CompositionBenchmark, Phase5BenchmarkError
from harness_kernel.providers import (
    DeterministicSuccessProvider,
    ProviderAvailability,
    ProviderDescriptor,
    ProviderRegistration,
    ProviderRegistry,
)
from harness_kernel.registry import (
    CapabilityRegistry,
    _dependency_parts,
    _manifest_diagnostics,
)
from harness_kernel.stops import (
    BudgetUsage,
    StopBudget,
    detect_no_progress,
)
from harness_kernel.telemetry import event_digest
from harness_kernel.validation import ValidationCode, validate
from harness_kernel.verification import VerificationOutcome, aggregate_verification


def _authority() -> AuthorityScope:
    return AuthorityScope(
        owner="builder",
        actor="reviewer",
        scopes=("task:TASK-1", "capability:validator"),
        decisions=("TRANSITION",),
    )


def test_invocation_authority_fails_closed_for_invalid_authority_and_timestamp() -> None:
    with pytest.raises(TypeError, match="AuthorityScope"):
        check_invocation_authority(
            cast(AuthorityScope, object()),
            task_id="TASK-1",
            invocation_id="INV-1",
            capability_id="validator",
            operation="execute",
            required_scope=(),
            at="2026-08-28T12:00:00Z",
        )

    result = check_invocation_authority(
        _authority(),
        task_id="TASK-1",
        invocation_id="INV-1",
        capability_id="validator",
        operation="execute",
        required_scope=("task:TASK-1",),
        at="",
    )

    assert not result.allowed
    assert result.code == "INVALID_AUTHORITY_TIME"


def test_benchmark_manifest_loader_rejects_non_regular_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="regular file"):
        _load_manifest(tmp_path / "missing-manifest.json")


@pytest.mark.parametrize("code", (None, ""))
def test_failure_detail_rejects_missing_codes(code: object) -> None:
    with pytest.raises(ValueError, match="failure code"):
        FailureDetail(
            category=FailureCategory.PROVIDER,
            code=cast(str, code),
            message="provider failed",
        )


@pytest.mark.parametrize("message", (None, ""))
def test_failure_detail_rejects_missing_messages(message: object) -> None:
    with pytest.raises(ValueError, match="failure message"):
        FailureDetail(
            category=FailureCategory.PROVIDER,
            code="PROVIDER_FAILED",
            message=cast(str, message),
        )


@pytest.mark.parametrize("attempt", (0, True))
def test_failure_detail_rejects_invalid_attempts(attempt: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        FailureDetail(
            category=FailureCategory.PROVIDER,
            code="PROVIDER_FAILED",
            message="provider failed",
            attempt=cast(int, attempt),
        )


def test_graph_normalizes_only_terminal_failure_states() -> None:
    assert _normalized_failure("NODE-1", InvocationStatus.REQUESTED) is None


def test_graph_rejects_blank_provider_and_artifact_references() -> None:
    graph = all_records()[2]
    assert hasattr(graph, "nodes")
    node = graph.nodes[0]  # type: ignore[union-attr]

    blank_provider = replace(node, provider_id=" ")
    provider_result = validate_execution_graph(replace(graph, nodes=(blank_provider,)))  # type: ignore[arg-type]
    assert not provider_result.is_valid
    assert any(finding.path.endswith("provider_id") for finding in provider_result.findings)

    blank_artifact = replace(node, artifact_refs=(" ",))
    artifact_result = validate_execution_graph(replace(graph, nodes=(blank_artifact,)))  # type: ignore[arg-type]
    assert not artifact_result.is_valid
    assert any(finding.path.endswith("artifact_refs") for finding in artifact_result.findings)


def test_graph_rejects_unknown_merge_policy() -> None:
    graph = all_records()[2]
    result = validate_execution_graph(replace(graph, merge_policy="UNKNOWN"))  # type: ignore[arg-type]

    assert not result.is_valid
    assert any(finding.path == "$.merge_policy" for finding in result.findings)


def test_provider_descriptor_rejects_blank_execution_mode_and_security_label() -> None:
    with pytest.raises(ValueError, match="execution mode"):
        ProviderDescriptor(
            provider_id="local.test",
            version="1.0.0",
            capability_ids=("local.test",),
            operations=("execute",),
            execution_mode=" ",
        )

    with pytest.raises(ValueError, match="security characteristics"):
        ProviderDescriptor(
            provider_id="local.test",
            version="1.0.0",
            capability_ids=("local.test",),
            operations=("execute",),
            security_characteristics=(" ",),
        )


def test_provider_registry_rejects_duplicate_and_nonlocal_registrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = DeterministicSuccessProvider()
    registration = ProviderRegistration(
        provider.descriptor,
        provider,
        ProviderAvailability.AVAILABLE,
    )

    with pytest.raises(ValueError, match="provider IDs must be unique"):
        ProviderRegistry((registration, registration))

    nonlocal_descriptor = provider.descriptor
    object.__setattr__(nonlocal_descriptor, "local_only", False)
    monkeypatch.setattr(
        DeterministicSuccessProvider,
        "descriptor",
        property(lambda _provider: nonlocal_descriptor),
    )
    nonlocal_registration = ProviderRegistration(
        nonlocal_descriptor,
        provider,
        ProviderAvailability.AVAILABLE,
    )

    with pytest.raises(ValueError, match="project-local"):
        ProviderRegistry((nonlocal_registration,))


def test_registry_diagnostics_report_missing_inspection_timestamp() -> None:
    manifest = all_records()[3]
    malformed = replace(
        manifest,
        provenance=replace(manifest.provenance, inspected_at=""),  # type: ignore[union-attr]
    )

    diagnostics = _manifest_diagnostics(malformed)  # type: ignore[arg-type]

    assert any(item.code == "MISSING_INSPECTION_PROVENANCE" for item in diagnostics)


def test_registry_parses_dependency_forms_and_normalizes_iterable_input() -> None:
    assert _dependency_parts("capability@opaque") == ("capability@opaque", "*")
    assert _dependency_parts("capability>=1.0.0") == ("capability", ">=1.0.0")

    manifest = all_records()[3]
    source = [manifest]
    registry = CapabilityRegistry(manifests=source)  # type: ignore[arg-type]

    assert registry.manifests == tuple(source)
    assert isinstance(registry.manifests, tuple)


def test_stop_budget_and_usage_reject_invalid_limits_and_nested_signatures() -> None:
    with pytest.raises(ValueError, match="stop budgets"):
        StopBudget(max_iterations=cast(int, "many"))
    with pytest.raises(ValueError, match="stop cost"):
        StopBudget(max_cost=-1)
    with pytest.raises(ValueError, match="budget usage"):
        BudgetUsage(iterations=cast(int, "many"))
    with pytest.raises(ValueError, match="budget cost"):
        BudgetUsage(cost=-1)

    assert detect_no_progress((["same"], ["same"]))


def test_telemetry_digest_rejects_non_mapping_canonical_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(telemetry_module, "to_primitive", lambda _value: [])

    with pytest.raises(TypeError, match="canonicalized"):
        event_digest(cast(Any, object()))


def test_validation_reports_high_confidence_route_without_evidence() -> None:
    route = all_records()[1]
    invalid = replace(route, record=replace(route.record, evidence_refs=()))  # type: ignore[union-attr]

    result = validate(invalid)

    assert ValidationCode.MISSING_EVIDENCE in {finding.code for finding in result.findings}


def test_validation_reports_non_typed_manifest_provenance() -> None:
    manifest = all_records()[3]
    invalid = replace(manifest, provenance=cast(Any, object()))

    result = validate(invalid)

    assert any(
        finding.code is ValidationCode.INVALID_TYPE and finding.path == "$.provenance"
        for finding in result.findings
    )


def test_validation_reports_blank_invocation_provider_id() -> None:
    invocation = all_records()[4]
    invalid = replace(invocation, provider_id=" ")

    result = validate(invalid)

    assert any(finding.path == "$.provider_id" for finding in result.findings)


def test_validation_reports_pass_claim_without_evidence() -> None:
    report = all_records()[7]
    claim = replace(report.claims[0], status=ClaimStatus.PASS, evidence_refs=())  # type: ignore[union-attr]
    invalid = replace(report, claims=(claim,))

    result = validate(invalid)

    assert any(finding.path.endswith("evidence_refs") for finding in result.findings)


def test_validation_reports_material_critique_without_evidence() -> None:
    report = all_records()[8]
    finding = replace(report.findings[0], severity=FindingSeverity.HIGH)  # type: ignore[union-attr]
    invalid = replace(report, findings=(finding,))

    result = validate(invalid)

    assert any(finding.path.endswith("evidence_refs") for finding in result.findings)


def test_validation_reports_scored_dimension_without_evidence() -> None:
    report = all_records()[9]
    dimension = replace(report.dimensions[0], confidence=Confidence.HIGH, evidence_refs=())  # type: ignore[union-attr]
    invalid = replace(report, dimensions=(dimension,))

    result = validate(invalid)

    assert any(finding.path.startswith("$.dimensions[0]") for finding in result.findings)


@pytest.mark.parametrize(
    "gate_summary", (GateSummary((), ("GATE-1",), (), ()), GateSummary((), (), (), ("GATE-1",)))
)
def test_validation_rejects_delivered_summary_with_failed_or_blocked_gates(
    gate_summary: GateSummary,
) -> None:
    summary = all_records()[11]
    invalid = replace(summary, gate_summary=gate_summary)

    result = validate(invalid)

    assert any(finding.path == "$.gate_summary" for finding in result.findings)


def test_verification_rejects_evidence_with_wrong_correlation() -> None:
    report = all_records()[7]
    evidence = replace(all_records()[6], task_id="TASK-OTHER")
    outcome = VerificationOutcome(
        report=report,
        evidence=(evidence,),
        procedure=report.procedures[0],
    )

    with pytest.raises(ValueError, match="evidence correlation"):
        aggregate_verification((outcome,), task_id="TASK-1", run_id="RUN-1")


def test_phase5_benchmark_requires_the_pilot_evidence_label() -> None:
    with pytest.raises(Phase5BenchmarkError, match="evidence label"):
        CompositionBenchmark(
            benchmark_id="P5-BENCH-TEST",
            evidence_label="UNTRUSTED_COMPARISON",
            baseline_score=1,
            composition_score=2,
            baseline_defects=0,
            composition_defects=0,
            baseline_latency_ms=1,
            composition_latency_ms=1,
            builder_invocations=1,
            verifier_invocations=1,
            critic_invocations=1,
            repair_invocations=0,
            baseline_reviewer="BASELINE",
            composition_reviewer="INDEPENDENT",
        )
