from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from test_phase6_models import (
    ARTIFACT_DIGEST,
    MANIFEST_DIGEST,
    PACKAGE_DIGEST,
    make_input,
)

from harness_kernel.phase6_models import (
    Evidence,
    FreshnessStatus,
    ProcedureResult,
    ProcedureSpec,
    VerificationStatus,
)
from harness_kernel.phase6_verifier import verify_input


def pass_result(verification_input, criterion_id="C-1", *, evidence=None):
    criterion_index = verification_input.required_criteria.index(criterion_id) + 1
    evidence_id = f"EVID-{criterion_index}"
    evidence = evidence or Evidence(
        evidence_id=evidence_id,
        criterion_id=criterion_id,
        digest="",
        artifact_refs=("ART-1",),
        artifact_digest=ARTIFACT_DIGEST,
        package_digest=PACKAGE_DIGEST,
        freshness=FreshnessStatus.FRESH,
        observed_at=verification_input.observed_at,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
    )
    return ProcedureResult(
        spec=ProcedureSpec(
            procedure_id=f"PROC-{criterion_id}",
            criterion_id=criterion_id,
            description="deterministic current check",
        ),
        status=VerificationStatus.PASS,
        executed=True,
        evidence=(evidence,),
        attempts=1,
        observed_at=verification_input.observed_at,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
        verifier_id=verification_input.capability_id,
    )


def test_verifier_emits_one_bound_lineage_record_per_criterion(tmp_path) -> None:
    verification_input = make_input(tmp_path)
    output = verify_input(
        verification_input,
        (pass_result(verification_input, "C-1"), pass_result(verification_input, "C-2")),
    )
    assert output.input_digest == verification_input.digest
    assert output.run_id == verification_input.run_id
    assert output.package_digest == PACKAGE_DIGEST
    assert output.manifest_digest == MANIFEST_DIGEST
    assert output.passed == ("C-1", "C-2")
    assert output.failed == ()
    assert output.not_run == ()
    assert output.unknown == ()
    assert output.report_digest.startswith("sha256:")
    assert all(item.claim.criterion_id == item.criterion_id for item in output.criterion_results)


def test_output_contract_exposes_status_lineage_findings_and_next_action(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))

    output = verify_input(verification_input, (pass_result(verification_input),))

    assert output.status is VerificationStatus.PASS
    assert output.claims[0].criterion_id == "C-1"
    assert output.evidence_used == ("EVID-1",)
    assert output.procedures_run == ("PROC-C-1",)
    assert output.procedures_not_run == ()
    assert output.failures == ()
    assert output.unknowns == ()
    assert output.findings == ()
    assert output.artifact_digest_verified is True
    assert output.freshness_status is FreshnessStatus.FRESH
    assert output.recommended_next_action == "DELIVER_OR_PROCEED"


def test_verifier_blocks_missing_stale_and_unexecuted_pass_evidence(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1", "C-2", "C-3"))
    stale_template = Evidence(
        evidence_id="EVID-1",
        criterion_id="C-1",
        digest="",
        artifact_refs=("ART-1",),
        artifact_digest=ARTIFACT_DIGEST,
        package_digest=PACKAGE_DIGEST,
        freshness=FreshnessStatus.STALE,
        observed_at=verification_input.observed_at,
    )
    stale_ref = replace(
        verification_input.evidence_refs[0],
        freshness=FreshnessStatus.STALE,
        digest=stale_template.digest,
    )
    verification_input = replace(
        verification_input,
        evidence_refs=(stale_ref, *verification_input.evidence_refs[1:]),
        digest="",
    )
    stale = replace(
        stale_template,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
    )
    output = verify_input(
        verification_input,
        (
            pass_result(verification_input, "C-1", evidence=stale),
            replace(pass_result(verification_input, "C-2"), executed=False, digest=""),
        ),
    )
    statuses = {item.criterion_id: item.status for item in output.criterion_results}
    assert statuses["C-1"] is VerificationStatus.STALE
    assert statuses["C-2"] is VerificationStatus.BLOCKED
    assert statuses["C-3"] is VerificationStatus.NOT_RUN
    assert output.stop_reason is not None


def test_verifier_blocks_evidence_ref_with_old_observation_timestamp(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    old_reference = replace(verification_input.evidence_refs[0], observed_at="2026-08-28T12:00:00Z")
    stale_input = replace(verification_input, evidence_refs=(old_reference,), digest="")

    output = verify_input(stale_input, (pass_result(stale_input),))

    assert output.status is VerificationStatus.STALE
    assert output.criterion_results[0].status is VerificationStatus.STALE
    assert output.freshness_status is FreshnessStatus.STALE


def test_verifier_preserves_unknown_input_freshness(tmp_path) -> None:
    verification_input = replace(
        make_input(tmp_path, criteria=("C-1",)),
        freshness=FreshnessStatus.UNKNOWN,
        digest="",
    )

    output = verify_input(verification_input, (pass_result(verification_input),))

    assert output.status is VerificationStatus.UNKNOWN
    assert output.freshness_status is FreshnessStatus.UNKNOWN


def test_verifier_blocks_stale_pass_procedure_receipt(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    stale_result = replace(
        pass_result(verification_input),
        observed_at="2020-01-01T00:00:00Z",
        digest="",
    )

    output = verify_input(verification_input, (stale_result,))

    assert output.status is VerificationStatus.STALE
    assert output.freshness_status is FreshnessStatus.STALE


def test_verifier_turns_budget_stop_into_a_blocked_output(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))

    output = verify_input(
        verification_input,
        (pass_result(verification_input),),
        elapsed_seconds=verification_input.budgets.max_duration_seconds,
    )

    assert output.status is VerificationStatus.BLOCKED
    assert output.stop_reason.value == "BUDGET_EXHAUSTED"
    assert output.recommended_next_action == "RESOLVE_BLOCKERS_AND_RERUN"


def test_verifier_revalidates_path_bound_evidence_before_pass(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    artifact_path = Path(verification_input.artifact_refs[0].path)
    artifact_path.write_bytes(b"bound artifact")
    artifact_digest = "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    artifact = replace(verification_input.artifact_refs[0], digest=artifact_digest)
    evidence_ref = replace(
        verification_input.evidence_refs[0],
        path=str(artifact_path),
        artifact_digest=artifact_digest,
    )
    evidence_template = Evidence(
        evidence_id="EVID-1",
        criterion_id="C-1",
        artifact_refs=("ART-1",),
        artifact_digest=artifact_digest,
        package_digest=PACKAGE_DIGEST,
        freshness=FreshnessStatus.FRESH,
        path=str(artifact_path),
        observed_at=verification_input.observed_at,
    )
    evidence_ref = replace(evidence_ref, digest=evidence_template.digest)
    bound_input = replace(
        verification_input,
        artifact_refs=(artifact,),
        evidence_refs=(evidence_ref,),
        digest="",
    )
    evidence = replace(
        evidence_template,
        run_id=bound_input.run_id,
        task_id=bound_input.task_id,
        input_digest=bound_input.digest,
    )
    result = pass_result(bound_input, evidence=evidence)

    output = verify_input(bound_input, (result,))
    assert output.status is VerificationStatus.PASS

    artifact_path.write_bytes(b"tampered artifact")
    with pytest.raises(ValueError, match="evidence path content"):
        verify_input(bound_input, (result,))


def test_verifier_rejects_duplicate_criteria_and_wrong_identity(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    duplicate = pass_result(verification_input, "C-1")
    with pytest.raises(ValueError):
        verify_input(verification_input, (duplicate, duplicate))
    wrong_package = replace(
        pass_result(verification_input),
        evidence=(
            replace(
                pass_result(verification_input).evidence[0],
                package_digest="sha256:" + "9" * 64,
                digest="",
            ),
        ),
        digest="",
    )
    with pytest.raises(ValueError):
        verify_input(verification_input, (wrong_package,))


def test_qualitative_visual_claim_requires_current_render_and_separate_reviewer(tmp_path) -> None:
    verification_input = make_input(
        tmp_path,
        criteria=("visual-quality",),
        profile="VISUAL",
    )
    output = verify_input(verification_input, ())
    assert output.criterion_results[0].status in {
        VerificationStatus.NOT_RUN,
        VerificationStatus.BLOCKED,
    }
    render = Evidence(
        evidence_id="EVID-1",
        criterion_id="visual-quality",
        digest="",
        artifact_refs=("ART-1",),
        artifact_digest=ARTIFACT_DIGEST,
        package_digest=PACKAGE_DIGEST,
        freshness=FreshnessStatus.FRESH,
        kind="RENDER",
        reviewer_id="independent-reviewer",
        reviewer_role="REVIEWER",
        observed_at=verification_input.observed_at,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
    )
    visual_ref = replace(verification_input.evidence_refs[0], digest=render.digest)
    verification_input = replace(
        verification_input,
        evidence_refs=(visual_ref,),
        digest="",
    )
    render = replace(
        render,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
    )
    reviewed = verify_input(
        verification_input,
        (pass_result(verification_input, "visual-quality", evidence=render),),
        reviewer_id="independent-reviewer",
        reviewer_role="REVIEWER",
    )
    assert reviewed.criterion_results[0].status is VerificationStatus.PASS


def test_output_binding_cannot_be_forged_after_creation(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    output = verify_input(verification_input, (pass_result(verification_input),))
    with pytest.raises(ValueError):
        replace(output, input_digest="sha256:" + "9" * 64)


def test_verifier_rejects_replayed_procedure_receipts_and_unknown_criteria(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    replayed = replace(
        pass_result(verification_input),
        run_id="RUN-OTHER",
        digest="",
    )
    with pytest.raises(ValueError):
        verify_input(verification_input, (replayed,))

    unknown = ProcedureResult(
        spec=ProcedureSpec(
            procedure_id="PROC-UNKNOWN",
            criterion_id="C-OTHER",
            description="criterion outside the frozen input",
        ),
        status=VerificationStatus.NOT_RUN,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
        verifier_id=verification_input.capability_id,
    )
    with pytest.raises(ValueError):
        verify_input(verification_input, (unknown,))


def test_verifier_surfaces_declared_missing_boundary_as_blocker(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))

    output = verify_input(
        verification_input,
        (),
        missing_tools=("render-observer",),
        missing_artifacts=("ART-MISSING",),
    )

    assert output.status is VerificationStatus.BLOCKED
    assert output.blockers == ("render-observer", "ART-MISSING")
    assert output.recommended_next_action == "RESOLVE_BLOCKERS_AND_RERUN"
