from __future__ import annotations

import json
from dataclasses import replace

import pytest
from test_contracts import all_records

from harness_kernel.errors import ContractValidationError, DeserializationError
from harness_kernel.models import (
    Claim,
    ClaimStatus,
    EvidenceProcedure,
    EvidenceResult,
    FreshnessStatus,
    GraphStatus,
    Recommendation,
    TelemetryEventType,
)
from harness_kernel.serialization import from_json, to_json
from harness_kernel.validation import ValidationCode, ValidationFinding, ValidationResult, validate


def finding_codes(value: object) -> set[str]:
    return {finding.code.value for finding in validate(value).findings}


def test_invalid_identifier_and_schema_version_are_reported_with_paths() -> None:
    original = all_records()[0]
    invalid = replace(original, task_id="bad id", schema_version="TP-999")

    result = validate(invalid)

    assert not result.is_valid
    assert {finding.path for finding in result.findings} >= {"$.task_id", "$.schema_version"}
    assert ValidationCode.INVALID_ID.value in finding_codes(invalid)
    assert ValidationCode.INVALID_VERSION.value in finding_codes(invalid)


def test_invalid_enum_and_record_envelope_status_are_rejected() -> None:
    original = all_records()[0]
    invalid = replace(
        original,
        domain="engineering",
        record=replace(original.record, status="current"),
    )

    result = validate(invalid)

    assert not result.is_valid
    assert ValidationCode.INVALID_ENUM.value in finding_codes(invalid)
    assert ValidationCode.INVALID_STATUS.value in finding_codes(invalid)


def test_evidence_pass_requires_executed_procedure_and_fresh_observation() -> None:
    original = all_records()[6]
    invalid_procedure = replace(original.procedure, executed=False)
    invalid = replace(
        original,
        procedure=invalid_procedure,
        freshness=replace(original.freshness, status=FreshnessStatus.STALE),
    )

    result = validate(invalid)

    assert not result.is_valid
    assert ValidationCode.INVARIANT_VIOLATION.value in finding_codes(invalid)
    assert any("procedure" in finding.path for finding in result.findings)


def test_verification_pass_cannot_hide_required_blocked_claim() -> None:
    original = all_records()[7]
    blocked_claim = Claim(
        claim_id="CLAIM-2",
        text="a required claim",
        required=True,
        status=ClaimStatus.BLOCKED,
        evidence_refs=(),
        limitation_refs=("missing evidence",),
    )
    invalid = replace(
        original,
        claims=original.claims + (blocked_claim,),
        recommendation=Recommendation.PASS,
    )

    result = validate(invalid)

    assert not result.is_valid
    assert ValidationCode.INVARIANT_VIOLATION.value in finding_codes(invalid)


def test_graph_rejects_unknown_edges_and_cycles() -> None:
    original = all_records()[2]
    first = original.nodes[0]
    second = replace(first, node_id="NODE-2", depends_on=("NODE-1",))
    edge = original.edges + (
        # Both dependency declarations and explicit edges are checked.
        __import__("harness_kernel.models", fromlist=["ExecutionEdge"]).ExecutionEdge(
            from_node="NODE-1", to_node="NODE-2", relation="DATA"
        ),
        __import__("harness_kernel.models", fromlist=["ExecutionEdge"]).ExecutionEdge(
            from_node="NODE-2", to_node="NODE-1", relation="CONTROL"
        ),
    )
    invalid = replace(original, nodes=(first, second), edges=edge, graph_status=GraphStatus.READY)

    result = validate(invalid)

    assert not result.is_valid
    assert ValidationCode.INVARIANT_VIOLATION.value in finding_codes(invalid)


def test_telemetry_loaded_and_delivery_events_require_evidence() -> None:
    original = all_records()[10]
    loaded = replace(original, event_type=TelemetryEventType.CAPABILITY_LOADED, evidence_refs=())
    delivery = replace(original, event_type=TelemetryEventType.DELIVERY, evidence_refs=())

    assert not validate(loaded).is_valid
    assert not validate(delivery).is_valid
    assert ValidationCode.MISSING_EVIDENCE.value in finding_codes(loaded)


def test_from_json_rejects_duplicate_keys_and_does_not_execute_payload() -> None:
    duplicate = '{"task_id":"TASK-1","task_id":"TASK-2"}'

    with pytest.raises(DeserializationError):
        from_json(duplicate, dict)

    payload = to_json(all_records()[0])
    decoded = json.loads(payload)
    decoded["__import__"] = "os"

    with pytest.raises(ContractValidationError):
        from_json(json.dumps(decoded), type(all_records()[0]))


def test_structured_validation_error_preserves_path_without_raw_input() -> None:
    original = all_records()[4]
    invalid = replace(
        original,
        invocation_status="AUTHORIZED",
        permissions=(),
        limits=replace(
            original.limits, token_budget=None, duration_budget_ms=None, tool_call_budget=None
        ),
    )

    result = validate(invalid)
    assert not result.is_valid
    with pytest.raises(ContractValidationError) as raised:
        result.raise_for_error()

    assert raised.value.code == "VALIDATION_ERROR"
    assert "permissions" in str(raised.value)
    assert "AUTHORIZED" not in str(raised.value)


def test_non_executed_procedure_cannot_claim_pass_even_when_result_is_pass() -> None:
    original = all_records()[6]
    invalid = replace(
        original,
        procedure=EvidenceProcedure(
            procedure_id="PROC-1",
            description="not run",
            command_or_method="pytest",
            executed=False,
        ),
        result=EvidenceResult.PASS,
    )

    assert not validate(invalid).is_valid


def test_string_enum_values_remain_valid_for_supported_records() -> None:
    records = (
        replace(all_records()[3], status="VERIFIED"),
        replace(all_records()[4], invocation_status="AUTHORIZED"),
        replace(all_records()[6], result="PASS"),
        replace(all_records()[7], recommendation="PASS"),
        replace(all_records()[9], quality_band="AAA_VERIFIED"),
        replace(all_records()[10], event_type="CAPABILITY_LOADED"),
        replace(all_records()[11], lifecycle_state="DELIVERED"),
    )

    assert all(validate(record).is_valid for record in records)


def test_string_enum_values_still_trigger_invariant_checks() -> None:
    manifest = all_records()[3]
    invalid_manifest = replace(
        manifest,
        status="VERIFIED",
        provenance=replace(manifest.provenance, source_refs=()),
    )

    invocation = all_records()[4]
    invalid_invocation = replace(
        invocation,
        invocation_status="AUTHORIZED",
        permissions=(),
    )

    evidence = all_records()[6]
    invalid_evidence = replace(
        evidence,
        procedure=replace(evidence.procedure, executed=False),
        result="PASS",
    )

    verification = all_records()[7]
    invalid_verification = replace(
        verification,
        recommendation="PASS",
        claims=(replace(verification.claims[0], status=ClaimStatus.BLOCKED),),
    )

    critique = replace(all_records()[8], independence="INDEPENDENT")

    quality = all_records()[9]
    invalid_quality = replace(
        quality,
        quality_band="AAA_VERIFIED",
        gates=(replace(quality.gates[0], status="FAIL"),),
    )

    telemetry = replace(all_records()[10], event_type="CAPABILITY_LOADED", evidence_refs=())

    summary = all_records()[11]
    invalid_summary = replace(
        summary,
        lifecycle_state="DELIVERED",
        delivery=replace(summary.delivery, artifact_ref=None),
    )

    for record, expected_code in (
        (invalid_manifest, ValidationCode.INVARIANT_VIOLATION),
        (invalid_invocation, ValidationCode.INVARIANT_VIOLATION),
        (invalid_evidence, ValidationCode.INVARIANT_VIOLATION),
        (invalid_verification, ValidationCode.INVARIANT_VIOLATION),
        (critique, ValidationCode.INVARIANT_VIOLATION),
        (invalid_quality, ValidationCode.INVARIANT_VIOLATION),
        (telemetry, ValidationCode.MISSING_EVIDENCE),
        (invalid_summary, ValidationCode.INVARIANT_VIOLATION),
    ):
        result = validate(record)
        assert not result.is_valid
        assert expected_code.value in finding_codes(record)


def test_validation_result_normalizes_iterable_findings_to_tuple() -> None:
    finding = ValidationFinding(code=ValidationCode.INVALID_TYPE, message="invalid")

    result = ValidationResult(valid=False, findings=[finding])

    assert result.findings == (finding,)
