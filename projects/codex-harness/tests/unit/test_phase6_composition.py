from __future__ import annotations

import hashlib

from harness_kernel.phase4_models import digest_payload
from harness_kernel.phase6_composition import (
    VerificationPlan,
    build_verification_input_from_existing,
    run_verification_plan,
)
from harness_kernel.phase6_models import (
    ArtifactRef,
    Claim,
    ProcedureSpec,
    VerificationBudget,
    VerificationInput,
    VerificationProfile,
    VerificationRole,
    VerificationStatus,
)


def test_verification_plan_rebinds_evidence_before_emitting_a_pass(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact_path = workspace / "index.html"
    content = b"<!doctype html><main>safe</main>"
    artifact_path.write_bytes(content)
    artifact_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    criteria_digest = digest_payload(("frozen-criteria",))
    claims = (
        Claim(criterion_id="artifact", text="artifact digest is current"),
        Claim(criterion_id="no-placeholder", text="placeholder is absent"),
    )
    procedures = (
        ProcedureSpec(
            procedure_id="PROC-ARTIFACT",
            criterion_id="artifact",
            description="compare artifact bytes",
            check="FILE_DIGEST",
            parameters={"artifact_id": "ART-1", "expected_digest": artifact_digest},
        ),
        ProcedureSpec(
            procedure_id="PROC-NO-PLACEHOLDER",
            criterion_id="no-placeholder",
            description="check forbidden text absence",
            check="TEXT_ABSENT",
            parameters={"artifact_id": "ART-1", "text": "placeholder"},
        ),
    )
    plan = VerificationPlan(
        verification_id="VERIFICATION-TEST",
        task_id="TASK-P6-TEST",
        run_id="RUN-P6-TEST",
        profile=VerificationProfile.COMPOSITION,
        criteria_digest=criteria_digest,
        claims=claims,
        procedures=procedures,
        expected_evidence=("artifact-EVIDENCE", "no-placeholder-EVIDENCE"),
        blocked_procedures=(),
        budget=VerificationBudget(),
    )
    verification_input = VerificationInput(
        verification_id=plan.verification_id,
        run_id=plan.run_id,
        task_id=plan.task_id,
        capability_id="verification-loop-vnext",
        package_digest="sha256:" + "1" * 64,
        manifest_digest="sha256:" + "2" * 64,
        workspace=str(workspace),
        required_criteria=tuple(item.criterion_id for item in claims),
        artifact_refs=(
            ArtifactRef(
                artifact_id="ART-1",
                path=str(artifact_path),
                digest=artifact_digest,
                version="artifact_v1",
                size_bytes=len(content),
                producer_id="design-director",
                producer_role=VerificationRole.DESIGN_DIRECTOR,
            ),
        ),
        profile=plan.profile,
        claims=claims,
        acceptance_criteria_ref=criteria_digest,
    )

    run = run_verification_plan(plan, verification_input)

    assert run.output.status is VerificationStatus.PASS
    assert run.output.artifact_digest_verified is True
    assert run.output.evidence_used == (
        "artifact-EVIDENCE",
        "no-placeholder-EVIDENCE",
    )
    assert run.output.procedures_not_run == ()
    assert run.output.report_digest.startswith("sha256:")
    assert run.digest.startswith("sha256:")


def test_existing_input_rebind_preserves_all_frozen_fields(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    input_record = VerificationInput(
        run_id="RUN-P6-REBIND",
        task_id="TASK-P6-REBIND",
        capability_id="verification-loop-vnext",
        package_digest="sha256:" + "1" * 64,
        manifest_digest="sha256:" + "2" * 64,
        workspace=str(workspace),
        required_criteria=("C-1",),
    )

    rebound = build_verification_input_from_existing(input_record, ())

    assert rebound.digest == input_record.digest
    assert rebound.required_criteria == input_record.required_criteria
    assert rebound.evidence_refs == ()


def test_verification_plan_blocks_when_total_duration_budget_is_exhausted(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact_path = workspace / "index.html"
    content = b"<!doctype html><main>safe</main>"
    artifact_path.write_bytes(content)
    artifact_digest = "sha256:" + hashlib.sha256(content).hexdigest()
    criteria_digest = digest_payload(("frozen-budget-criteria",))
    claim = Claim(criterion_id="artifact", text="artifact digest is current")
    procedure = ProcedureSpec(
        procedure_id="PROC-ARTIFACT",
        criterion_id="artifact",
        description="compare artifact bytes",
        check="FILE_DIGEST",
        parameters={"artifact_id": "ART-1", "expected_digest": artifact_digest},
    )
    plan = VerificationPlan(
        verification_id="VERIFICATION-BUDGET",
        task_id="TASK-P6-BUDGET",
        run_id="RUN-P6-BUDGET",
        profile=VerificationProfile.COMPOSITION,
        criteria_digest=criteria_digest,
        claims=(claim,),
        procedures=(procedure,),
        expected_evidence=("artifact-EVIDENCE",),
        blocked_procedures=(),
        budget=VerificationBudget(max_duration_seconds=1),
    )
    verification_input = VerificationInput(
        verification_id=plan.verification_id,
        run_id=plan.run_id,
        task_id=plan.task_id,
        capability_id="verification-loop-vnext",
        package_digest="sha256:" + "1" * 64,
        manifest_digest="sha256:" + "2" * 64,
        workspace=str(workspace),
        required_criteria=(claim.criterion_id,),
        artifact_refs=(
            ArtifactRef(
                artifact_id="ART-1",
                path=str(artifact_path),
                digest=artifact_digest,
                producer_id="design-director",
                producer_role=VerificationRole.DESIGN_DIRECTOR,
            ),
        ),
        profile=plan.profile,
        claims=(claim,),
        acceptance_criteria_ref=criteria_digest,
        budgets=plan.budget,
    )
    clock = iter((0.0, 0.0, 2.0, 2.0))
    monkeypatch.setattr(
        "harness_kernel.phase6_composition.time.monotonic",
        lambda: next(clock, 2.0),
    )

    run = run_verification_plan(plan, verification_input)

    assert run.output.status is VerificationStatus.BLOCKED
    assert run.output.stop_reason.value == "BUDGET_EXHAUSTED"
    assert run.procedure_results[0].status is VerificationStatus.BLOCKED
    assert run.procedure_results[0].error == "verification total duration budget exhausted"
