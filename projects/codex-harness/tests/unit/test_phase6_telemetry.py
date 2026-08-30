from __future__ import annotations

import pytest
from test_phase6_models import make_input

from harness_kernel.phase6_composition import VerificationPlan
from harness_kernel.phase6_models import (
    Claim,
    ProcedureResult,
    ProcedureSpec,
    VerificationBudget,
    VerificationProfile,
    VerificationStatus,
)
from harness_kernel.phase6_telemetry import (
    Phase6EventType,
    Phase6Telemetry,
    Phase6TelemetryError,
    build_verification_telemetry,
)
from harness_kernel.phase6_verifier import verify_input


def test_telemetry_records_bound_lifecycle_without_false_completion(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    procedure = ProcedureSpec(
        procedure_id="PROC-NOT-RUN",
        criterion_id="C-1",
        description="unsupported procedure is intentionally not run",
        check="UNKNOWN_CHECK",
    )
    result = ProcedureResult(
        spec=procedure,
        status=VerificationStatus.NOT_RUN,
        executed=False,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
        verifier_id=verification_input.capability_id,
    )
    output = verify_input(verification_input, (result,))
    plan = VerificationPlan(
        verification_id=verification_input.verification_id,
        task_id=verification_input.task_id,
        run_id=verification_input.run_id,
        profile=VerificationProfile.FOCUSED,
        criteria_digest="sha256:" + "a" * 64,
        claims=(Claim(criterion_id="C-1", text="one criterion"),),
        procedures=(procedure,),
        expected_evidence=("C-1-EVIDENCE",),
        blocked_procedures=(),
        budget=VerificationBudget(),
    )

    telemetry = build_verification_telemetry(
        plan,
        verification_input,
        (result,),
        output,
    )
    event_types = tuple(event.event_type for event in telemetry.events)

    assert Phase6EventType.VERIFICATION_PROCEDURE_STARTED in event_types
    assert Phase6EventType.VERIFICATION_PROCEDURE_BLOCKED in event_types
    assert Phase6EventType.VERIFICATION_FINDING_CREATED in event_types
    assert Phase6EventType.VERIFICATION_PROCEDURE_COMPLETED not in event_types
    assert all(event.run_id == verification_input.run_id for event in telemetry.events)
    assert telemetry.digest.startswith("sha256:")


def test_telemetry_rejects_unobserved_completion_and_overflow(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    with pytest.raises(Phase6TelemetryError):
        Phase6Telemetry().record(
            Phase6EventType.VERIFICATION_PROCEDURE_COMPLETED,
            verification_input,
            observed=False,
        )
    with pytest.raises(Phase6TelemetryError):
        Phase6Telemetry(max_events=257)
    with pytest.raises(Phase6TelemetryError):
        Phase6Telemetry().record(
            Phase6EventType.VERIFICATION_CAPABILITY_SELECTED,
            verification_input,
            payload={"large": "x" * (16 * 1024)},
        )
    bounded = Phase6Telemetry(max_events=1).record(
        Phase6EventType.VERIFICATION_CAPABILITY_SELECTED,
        verification_input,
    )
    with pytest.raises(Phase6TelemetryError):
        bounded.record(Phase6EventType.VERIFICATION_FINALIZED, verification_input)
