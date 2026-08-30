from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_phase71_phase6_hardening import (
    MANIFEST_DIGEST,
    PACKAGE_DIGEST,
    digest_bytes,
    make_artifact,
    make_artifact_ref,
    make_evidence,
    make_evidence_ref,
    make_input,
    make_plan,
    make_task,
    write_composition_files,
)

import harness_kernel.phase6_composition as composition
import harness_kernel.phase6_host as host
import harness_kernel.phase6_verifier as verifier
from harness_kernel.phase4_models import (
    ExecutionMode,
    HostLoadObservation,
    InvocationResultStatus,
)
from harness_kernel.phase6_models import (
    ArtifactRef,
    Claim,
    Evidence,
    EvidenceKind,
    FreshnessStatus,
    ProcedureResult,
    ProcedureSpec,
    ReadOnlyPolicy,
    VerificationBudget,
    VerificationInput,
    VerificationProfile,
    VerificationRole,
    VerificationStatus,
)
from harness_kernel.phase6_policy import (
    ActivationDecision,
    Phase6PolicyError,
    activation_decision,
    profile_gates,
    profile_limits,
    profile_requires_reviewer,
    required_tools,
    validate_input_policy,
    validate_procedure_policy,
    validate_reviewer,
)
from harness_kernel.phase6_verifier import Phase6VerificationError, verify_input

PROJECT_ROOT = Path(__file__).parents[2]


def expect_error(factory, message: str, error_type: type[ValueError] = ValueError) -> None:
    with pytest.raises(error_type, match=f"^{message}$"):
        factory()


def forged(record: object, **changes: object) -> object:
    """Create an intentionally forged boundary record for fail-closed checks."""

    for name, value in changes.items():
        object.__setattr__(record, name, value)
    return record


def input_with_bound_evidence(
    tmp_path: Path,
    *,
    criterion_id: str = "C-1",
    profile: VerificationProfile | str = VerificationProfile.FOCUSED,
    artifact_path: Path | None = None,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
    evidence_kind: EvidenceKind = EvidenceKind.TEST,
) -> tuple[VerificationInput, Evidence, ArtifactRef]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    path = artifact_path or workspace / "ART-1.html"
    content = b"bound artifact"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    artifact_digest = digest_bytes(content)
    artifact = ArtifactRef(
        artifact_id="ART-1",
        path=str(path),
        digest=artifact_digest,
        package_digest=PACKAGE_DIGEST,
        observed_at="2026-08-29T12:00:00Z",
        producer_id="design-director",
        producer_role=VerificationRole.DESIGN_DIRECTOR,
    )
    template = Evidence(
        evidence_id="EVID-1",
        criterion_id=criterion_id,
        artifact_refs=(artifact.artifact_id,),
        artifact_digest=artifact.digest,
        package_digest=PACKAGE_DIGEST,
        observed_at="2026-08-29T12:00:00Z",
        freshness=freshness,
        kind=evidence_kind,
        path=artifact.path,
        observation="bounded evidence",
    )
    evidence_ref = make_evidence_ref(template)
    input_record = make_input(
        tmp_path,
        criteria=(criterion_id,),
        artifacts=(artifact,),
        evidence_refs=(evidence_ref,),
        profile=profile,
    )
    evidence = replace(
        template,
        run_id=input_record.run_id,
        task_id=input_record.task_id,
        input_digest=input_record.digest,
    )
    return input_record, evidence, artifact


def bound_result(
    verification_input: VerificationInput,
    *,
    criterion_id: str = "C-1",
    status: VerificationStatus = VerificationStatus.PASS,
    evidence: tuple[Evidence, ...] = (),
    executed: bool = True,
    observation: str = "procedure observation",
    error: str | None = None,
) -> ProcedureResult:
    spec = ProcedureSpec(
        procedure_id=f"PROC-{criterion_id}",
        criterion_id=criterion_id,
        description="bounded pipeline procedure",
    )
    return ProcedureResult(
        spec=spec,
        status=status,
        executed=executed,
        evidence=evidence,
        attempts=1 if executed else 0,
        observed_at=verification_input.observed_at,
        observation=observation,
        error=error,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
        verifier_id=verification_input.capability_id,
    )


def composition_fixture(tmp_path: Path, snapshot):
    task = make_task(tmp_path)
    artifact = make_artifact(task, content="<!doctype html><html><main>PulsePaw</main></html>")
    desktop, mobile, receipt, browser = write_composition_files(task, artifact)
    plan = composition.build_verification_plan(
        task,
        artifact,
        desktop_render=desktop,
        mobile_render=mobile,
        builder_receipt=receipt,
        browser_manifest=browser,
        snapshot=snapshot,
        verification_id="VERIFICATION-PIPELINE",
    )
    input_record = composition.build_verification_input(
        task,
        artifact,
        plan,
        desktop_render=desktop,
        mobile_render=mobile,
        builder_receipt=receipt,
        browser_manifest=browser,
        snapshot=snapshot,
        observed_at=1_756_000_000,
    )
    return task, artifact, plan, input_record, (desktop, mobile, receipt, browser)


def host_report_payload(
    task, artifact, plan, verification_input, expected_output
) -> dict[str, object]:
    return {
        "marker": "P6_VNEXT_REPORT",
        "ack_marker": "P6_VNEXT_HOST_ACK",
        "capability": "verification-loop-vnext",
        "role": "VERIFIER",
        "read_only": True,
        "self_approval": False,
        "task_id": task.task_id,
        "run_id": task.run_id,
        "verification_id": plan.verification_id,
        "criteria_digest": plan.criteria_digest,
        "input_digest": verification_input.digest,
        "package_digest": verification_input.package_digest,
        "manifest_digest": verification_input.manifest_digest,
        "artifact_id": artifact.artifact_id,
        "artifact_version": artifact.version,
        "artifact_digest": artifact.digest,
        "status": expected_output.status.value,
        "report_digest": None,
        "procedures_run": list(expected_output.procedures_run),
        "procedures_not_run": list(expected_output.procedures_not_run),
        "deferred_criteria": list(expected_output.deferred_criteria),
        "evidence_digests": {
            item.evidence_id: item.digest for item in verification_input.evidence_refs
        },
        "criteria": [
            {
                "criterion_id": result.criterion_id,
                "status": result.status.value,
                "procedure_id": result.procedure_id,
                "evidence_refs": list(result.evidence_refs),
            }
            for result in expected_output.criterion_results
        ],
    }


def host_preflight_fixture(tmp_path: Path, snapshot):
    raw_task, artifact, plan, input_record, _ = composition_fixture(tmp_path, snapshot)
    task = replace(raw_task, workspace=str(PROJECT_ROOT), artifact_root=str(PROJECT_ROOT))
    assert snapshot.record is not None
    isolated_record = replace(snapshot.record)
    isolated_inventory = replace(snapshot.inventory, capabilities=(isolated_record,))
    isolated_snapshot = replace(
        snapshot,
        record=isolated_record,
        inventory=isolated_inventory,
        digest="",
    )
    preflight = composition.prepare_vnext_host_preflight(
        task,
        artifact,
        snapshot=isolated_snapshot,
        policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
        plan=plan,
        verification_input=input_record,
        artifact_version=artifact.version,
        invocation_label="PIPELINE",
    )
    handoff = composition._host_handoff(input_record, plan, artifact=artifact)
    prompt = composition._host_prompt(handoff, artifact.version)
    return task, artifact, plan, input_record, preflight, prompt


@pytest.fixture(scope="module")
def vnext_snapshot():
    return host.discover_vnext_package(PROJECT_ROOT)


def test_policy_profiles_and_activation_cover_every_declared_gate(tmp_path: Path) -> None:
    for profile in VerificationProfile:
        assert profile_gates(profile)
        assert profile_limits(profile)[0] >= 1
    assert profile_requires_reviewer(VerificationProfile.COMPOSITION) is True
    assert profile_requires_reviewer(VerificationProfile.FOCUSED) is False
    expect_error(
        lambda: profile_gates("UNKNOWN"),
        "unknown verification profile",
        Phase6PolicyError,
    )
    expect_error(
        lambda: profile_limits("UNKNOWN"),
        "unknown verification profile",
        Phase6PolicyError,
    )

    assert activation_decision(None) is ActivationDecision.BLOCKED
    assert activation_decision(None, requested=False) is ActivationDecision.DO_NOT_ACTIVATE
    valid = make_input(tmp_path / "phase71-policy-valid")
    assert activation_decision(valid) is ActivationDecision.ACTIVATE
    forged(valid, scope="GLOBAL")
    assert activation_decision(valid) is ActivationDecision.BLOCKED


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("role", VerificationRole.REVIEWER, "Phase 6 input role must be VERIFIER"),
        ("scope", "GLOBAL", "Phase 6 scope must be PROJECT"),
        ("authority", "ORCHESTRATOR", "Phase 6 authority must be VERIFIER"),
        ("read_only", False, "Phase 6 policy is read-only only"),
        ("read_only_policy", "MUTATES", "Phase 6 policy is read-only only"),
    ),
)
def test_policy_rejects_authority_and_mutation_boundary_forgery(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    input_record = make_input(tmp_path)
    forged(input_record, **{field: value})
    expect_error(lambda: validate_input_policy(input_record), message, Phase6PolicyError)


def test_policy_rejects_invalid_tool_vocabularies_duplicates_and_budgets(tmp_path: Path) -> None:
    for tool in ("shell", "mystery-tool", "network-provider"):
        input_record = make_input(tmp_path / tool.replace("-", "_"), allowed_tools=(tool,))
        expect_error(
            lambda input_record=input_record: validate_input_policy(input_record),
            "tool is not in the read-only allowlisted vocabulary",
            Phase6PolicyError,
        )

    duplicate = make_input(tmp_path / "duplicate")
    forged(duplicate, allowed_tools=("render-observer", "render-observer"))
    expect_error(
        lambda: validate_input_policy(duplicate),
        "allowed tools must be unique",
        Phase6PolicyError,
    )

    too_many = make_input(
        tmp_path / "profile-limit",
        criteria=tuple(f"C-{index}" for index in range(9)),
        profile=VerificationProfile.FOCUSED,
    )
    expect_error(
        lambda: validate_input_policy(too_many),
        "required criteria exceed the selected profile budget",
        Phase6PolicyError,
    )

    policy_limit = make_input(
        tmp_path / "policy-limit",
        criteria=("C-1", "C-2"),
    )
    forged(policy_limit, budgets=VerificationBudget(max_criteria=1))
    expect_error(
        lambda: validate_input_policy(policy_limit),
        "required criteria exceed the policy budget",
        Phase6PolicyError,
    )

    references = tuple(
        make_evidence_ref(
            make_evidence(evidence_id=f"EVID-{index}-" + "x" * 180, artifact_id=None),
        )
        for index in range(100)
    )
    oversized = make_input(tmp_path / "reference-limit", evidence_refs=references)
    expect_error(
        lambda: validate_input_policy(oversized),
        "evidence references exceed the selected profile budget",
        Phase6PolicyError,
    )
    assert required_tools(make_input(tmp_path / "tools")) == ()
    assert (
        validate_input_policy(
            make_input(
                tmp_path / "mutation-denied",
                read_only_policy=ReadOnlyPolicy.MUTATION_DENIED,
            )
        )
        == ()
    )


def test_policy_rejects_invalid_procedures_and_reviewer_collisions(tmp_path: Path) -> None:
    input_record = make_input(tmp_path / "procedure", criteria=("C-1",))
    expect_error(
        lambda: validate_procedure_policy("not-a-procedure", input_record),
        "procedure spec is invalid",
        Phase6PolicyError,
    )
    for procedure, message in (
        (
            ProcedureSpec("PROC-NONDET", "C-1", "non deterministic", deterministic=False),
            "procedures must be deterministic",
        ),
        (
            ProcedureSpec("PROC-WRITE", "C-1", "write", read_only=False),
            "procedures must be read-only",
        ),
        (
            ProcedureSpec("PROC-TOOL", "C-1", "tool", required_tool="render-observer"),
            "procedure requires a tool outside the allowlist",
        ),
        (
            ProcedureSpec("PROC-OTHER", "C-OTHER", "other"),
            "procedure criterion is not required by the input",
        ),
    ):
        expect_error(
            lambda procedure=procedure: validate_procedure_policy(procedure, input_record),
            message,
            Phase6PolicyError,
        )

    expect_error(
        lambda: validate_reviewer(
            verifier="not-input", reviewer_id="reviewer", reviewer_role=VerificationRole.REVIEWER
        ),
        "verifier input is invalid",
        Phase6PolicyError,
    )
    reviewer_cases = (
        ("reviewer", "NOT-ROLE", "reviewer role is invalid"),
        ("reviewer", VerificationRole.VERIFIER, "reviewer must have the REVIEWER role"),
        ("", VerificationRole.REVIEWER, "reviewer must be identified independently"),
        (
            input_record.capability_id,
            VerificationRole.REVIEWER,
            "reviewer must be identified independently",
        ),
        ("bad\x00reviewer", VerificationRole.REVIEWER, "reviewer identity is malformed"),
        ("../reviewer", VerificationRole.REVIEWER, "reviewer identity is malformed"),
    )
    for reviewer_id, reviewer_role, message in reviewer_cases:
        expect_error(
            lambda reviewer_id=reviewer_id, reviewer_role=reviewer_role: validate_reviewer(
                verifier=input_record,
                reviewer_id=reviewer_id,
                reviewer_role=reviewer_role,
            ),
            message,
            Phase6PolicyError,
        )
    producer_input = make_input(
        tmp_path / "producer",
        artifacts=(
            make_artifact_ref(
                str(tmp_path / "producer" / "workspace"),
                artifact_id="ART-1",
            ),
        ),
    )
    expect_error(
        lambda: validate_reviewer(
            verifier=producer_input,
            reviewer_id="design-director",
            reviewer_role=VerificationRole.REVIEWER,
        ),
        "reviewer cannot be the artifact producer",
        Phase6PolicyError,
    )
    assert validate_reviewer(
        verifier=input_record,
        reviewer_id="independent-reviewer",
        reviewer_role="REVIEWER",
    ) == ("independent-reviewer", "REVIEWER")


def test_verifier_handles_partial_failed_and_all_stop_conditions(tmp_path: Path) -> None:
    statuses = (
        (VerificationStatus.PARTIAL, "DISCLOSE_LIMITATIONS_AND_COMPLETE_OPTIONAL_COVERAGE"),
        (VerificationStatus.FAIL, "RESOLVE_FINDINGS_AND_RERUN"),
        (VerificationStatus.BLOCKED, "RESOLVE_BLOCKERS_AND_RERUN"),
    )
    for status, action in statuses:
        input_record = make_input(tmp_path / status.value, criteria=("C-1",))
        result = bound_result(input_record, status=status, observation=f"{status.value} observed")
        output = verify_input(input_record, (result,))
        assert output.status is status
        assert output.criterion_results[0].status is status
        assert output.criterion_results[0].observed == f"{status.value} observed"
        assert output.recommended_next_action == action
        assert output.findings[0].severity.value in {"HIGH", "MEDIUM"}

    input_record = make_input(tmp_path / "stop-flags", criteria=("C-1",))
    flags = (
        ({"human_override": True}, "HUMAN_OVERRIDE"),
        ({"no_progress": True}, "NO_PROGRESS"),
        ({"repeated_procedure_failure": True}, "REPEATED_PROCEDURE_FAILURE"),
        ({"missing_tools": ("render-observer",)}, "MISSING_REQUIRED_TOOL"),
        ({"missing_artifacts": ("ART-MISSING",)}, "MISSING_REQUIRED_ARTIFACT"),
        ({"elapsed_seconds": 120}, "BUDGET_EXHAUSTED"),
    )
    for kwargs, condition in flags:
        output = verify_input(input_record, (), **kwargs)
        assert output.stop_reason is not None
        assert output.stop_reason.value == condition
        assert output.status is VerificationStatus.BLOCKED

    previous_input = make_input(tmp_path / "previous", criteria=("C-1",))
    previous = bound_result(previous_input, status=VerificationStatus.PARTIAL)
    current = verify_input(previous_input, (previous,))
    assert current.stop_reason is not None
    no_progress = verifier.evaluate_stop(
        previous_input,
        (current.criterion_results[0],),
        previous_results=(current.criterion_results[0],),
    )
    assert no_progress.condition.value == "NO_PROGRESS"


def test_verifier_rejects_malformed_receipts_and_preserves_fail_closed_diagnostics(
    tmp_path: Path,
) -> None:
    input_record, evidence, _ = input_with_bound_evidence(tmp_path)
    result = bound_result(input_record, evidence=(evidence,))

    cases = (
        (
            lambda: verify_input(input_record, (object(),)),
            "procedure results contain an invalid record",
        ),
        (
            lambda: verify_input(input_record, (replace(result, run_id="OTHER", digest=""),)),
            "procedure receipt is not bound to this input",
        ),
        (
            lambda: verify_input(
                input_record,
                (bound_result(input_record, criterion_id="C-OTHER"),),
            ),
            "procedure criterion is not required by the input",
        ),
    )
    for factory, message in cases:
        expect_error(factory, message, Phase6VerificationError)

    duplicate = verify_input(input_record, (result,))
    with pytest.raises(Phase6VerificationError, match="duplicate procedure result"):
        verify_input(input_record, (result, result))
    assert duplicate.status is VerificationStatus.PASS
    assert duplicate.evidence_used == ("EVID-1",)

    forged_evidence = forged(replace(evidence), digest=PACKAGE_DIGEST)
    with pytest.raises(
        Phase6VerificationError,
        match="evidence digest does not match its content",
    ):
        verify_input(input_record, (bound_result(input_record, evidence=(forged_evidence,)),))


def test_verifier_rebinds_undeclared_evidence_and_maps_visual_review_paths(tmp_path: Path) -> None:
    input_record = make_input(tmp_path / "undeclared", criteria=("C-1",))
    evidence = replace(
        make_evidence(artifact_id=None),
        run_id=input_record.run_id,
        task_id=input_record.task_id,
        input_digest=input_record.digest,
    )
    result = bound_result(input_record, evidence=(evidence,))
    output = verify_input(input_record, (result,))
    assert output.criterion_results[0].status is VerificationStatus.BLOCKED
    assert output.criterion_results[0].procedure_result is not None
    assert output.criterion_results[0].procedure_result.evidence == ()
    assert (
        output.criterion_results[0].reason
        == "PASS requires an executed procedure and current evidence"
    )

    visual_input, visual_evidence, _ = input_with_bound_evidence(
        tmp_path / "visual",
        criterion_id="visual-composition",
        profile=VerificationProfile.VISUAL,
        evidence_kind=EvidenceKind.RENDER,
    )
    visual = verify_input(
        visual_input,
        (
            bound_result(
                visual_input,
                criterion_id="visual-composition",
                evidence=(visual_evidence,),
            ),
        ),
        reviewer_id="independent-reviewer",
        reviewer_role=VerificationRole.REVIEWER,
    )
    assert visual.status is VerificationStatus.BLOCKED
    assert "qualitative visual judgment" in visual.criterion_results[0].reason

    reviewed_evidence = replace(
        visual_evidence,
        reviewer_id="independent-reviewer",
        reviewer_role=VerificationRole.REVIEWER,
        digest="",
    )
    visual_ref = make_evidence_ref(reviewed_evidence)
    reviewed_input = replace(visual_input, evidence_refs=(visual_ref,), digest="")
    reviewed_evidence = replace(reviewed_evidence, input_digest=reviewed_input.digest)
    reviewed = verify_input(
        reviewed_input,
        (
            bound_result(
                reviewed_input,
                criterion_id="visual-composition",
                evidence=(reviewed_evidence,),
            ),
        ),
        reviewer_id="independent-reviewer",
        reviewer_role=VerificationRole.REVIEWER,
    )
    assert reviewed.status is VerificationStatus.PASS
    assert reviewed.reviewer_id == "independent-reviewer"


def test_verifier_covers_path_evidence_revalidation_and_reviewer_resolution(tmp_path: Path) -> None:
    input_record, evidence, artifact = input_with_bound_evidence(tmp_path / "path")
    passing = bound_result(input_record, evidence=(evidence,))
    assert verify_input(input_record, (passing,)).status is VerificationStatus.PASS

    wrong_path = replace(
        evidence,
        path=str(Path(input_record.workspace) / "other.html"),
        digest="",
    )
    wrong_path_ref = replace(
        input_record.evidence_refs[0],
        path=wrong_path.path,
        digest=wrong_path.digest,
    )
    wrong_path_input = replace(
        input_record,
        evidence_refs=(wrong_path_ref,),
        digest="",
    )
    wrong_path = replace(wrong_path, input_digest=wrong_path_input.digest)
    with pytest.raises(Phase6VerificationError, match="evidence path is not bound"):
        verify_input(
            wrong_path_input,
            (bound_result(wrong_path_input, evidence=(wrong_path,)),),
        )

    with pytest.raises(Phase6VerificationError, match="reviewer identity and role"):
        verify_input(
            input_record,
            (passing,),
            reviewer_id="independent-reviewer",
        )

    artifact_path = Path(artifact.path)
    artifact_path.unlink()
    with pytest.raises(Phase6VerificationError, match="evidence path cannot be revalidated"):
        verify_input(input_record, (bound_result(input_record, evidence=(evidence,)),))

    no_artifact_path = replace(evidence, artifact_refs=(), path=artifact.path, digest="")
    no_artifact_input = replace(
        input_record,
        evidence_refs=(
            replace(
                input_record.evidence_refs[0],
                artifact_id=None,
                artifact_digest=None,
            ),
        ),
        digest="",
    )
    no_artifact_path = replace(
        no_artifact_path,
        run_id=no_artifact_input.run_id,
        task_id=no_artifact_input.task_id,
        input_digest=no_artifact_input.digest,
    )
    no_artifact_ref = replace(
        no_artifact_input.evidence_refs[0],
        digest=no_artifact_path.digest,
    )
    no_artifact_input = replace(
        no_artifact_input,
        evidence_refs=(no_artifact_ref,),
        digest="",
    )
    no_artifact_path = replace(no_artifact_path, input_digest=no_artifact_input.digest)
    with pytest.raises(
        Phase6VerificationError,
        match="path-bound evidence must name an artifact",
    ):
        verify_input(
            no_artifact_input,
            (bound_result(no_artifact_input, evidence=(no_artifact_path,)),),
        )

    assert verifier._confidence(()) is verifier.VerificationConfidence.UNKNOWN
    assert verifier._evidence_map((passing,))["EVID-1"] == evidence
    divergent = replace(evidence, observation="divergent", digest="")
    divergent_result = bound_result(input_record, evidence=(divergent,))
    with pytest.raises(Phase6VerificationError, match="evidence IDs must not diverge"):
        verifier._evidence_map((passing, divergent_result))


def test_verifier_returns_blocked_output_for_each_receipt_budget_overflow(tmp_path: Path) -> None:
    for name, budget, result_factory in (
        (
            "procedure-count",
            VerificationBudget(max_procedures=1),
            lambda input_record: (
                bound_result(input_record),
                bound_result(input_record, criterion_id="C-2"),
            ),
        ),
        (
            "evidence-count",
            VerificationBudget(max_evidence_records=1),
            lambda input_record: (
                bound_result(
                    input_record,
                    evidence=(
                        make_evidence(evidence_id="E-1", artifact_id=None),
                        make_evidence(evidence_id="E-2", artifact_id=None),
                    ),
                ),
            ),
        ),
        (
            "report-bytes",
            VerificationBudget(max_report_bytes=8_192),
            lambda input_record: (bound_result(input_record, observation="x" * 10_000),),
        ),
    ):
        input_record = make_input(tmp_path / name, criteria=("C-1",), budgets=budget)
        if name == "report-bytes":
            probe = bound_result(input_record, observation="x" * 10_000)
            budget = VerificationBudget(
                max_report_bytes=len(verifier.canonical_json(probe).encode("utf-8")) - 1
            )
            input_record = make_input(tmp_path / name, criteria=("C-1",), budgets=budget)
        results = result_factory(input_record)
        output = verify_input(input_record, results)
        assert output.status is VerificationStatus.BLOCKED
        assert output.stop_reason.value == "BUDGET_EXHAUSTED"
        assert output.criterion_results[0].status is VerificationStatus.NOT_RUN

    input_record = make_input(tmp_path / "attempts", criteria=("C-1",))
    too_many_attempts = bound_result(input_record)
    forged(too_many_attempts, attempts=2)
    output = verify_input(input_record, (too_many_attempts,))
    assert output.status is VerificationStatus.BLOCKED
    assert output.stop_reason.value == "BUDGET_EXHAUSTED"


def test_verifier_maps_stale_unknown_unexecuted_and_missing_procedures(tmp_path: Path) -> None:
    for freshness, expected in (
        (FreshnessStatus.STALE, VerificationStatus.STALE),
        (FreshnessStatus.UNKNOWN, VerificationStatus.UNKNOWN),
    ):
        input_record = make_input(
            tmp_path / freshness.value,
            criteria=("C-1",),
            freshness=freshness,
        )
        output = verify_input(
            input_record,
            (bound_result(input_record, status=VerificationStatus.FAIL),),
        )
        assert output.criterion_results[0].status is expected
        assert output.status is expected

    input_record = make_input(tmp_path / "unexecuted", criteria=("C-1",))
    result = bound_result(input_record, executed=False, status=VerificationStatus.PASS)
    output = verify_input(input_record, (result,))
    assert output.status is VerificationStatus.BLOCKED
    assert "executed procedure" in output.criterion_results[0].reason

    stale_result = replace(
        bound_result(input_record),
        observed_at="2020-01-01T00:00:00Z",
        digest="",
    )
    stale_output = verify_input(input_record, (stale_result,))
    assert stale_output.criterion_results[0].status is VerificationStatus.STALE
    assert stale_output.freshness_status is FreshnessStatus.STALE


def test_composition_rejects_frozen_identity_and_file_drift(tmp_path: Path, vnext_snapshot) -> None:
    task, artifact, plan, input_record, files = composition_fixture(tmp_path, vnext_snapshot)
    desktop, mobile, receipt, browser = files
    no_identity = replace(
        vnext_snapshot,
        package_digest=None,
        manifest_digest=None,
        digest="",
    )
    expect_error(
        lambda: composition.build_verification_plan(
            task,
            artifact,
            desktop_render=desktop,
            mobile_render=mobile,
            builder_receipt=receipt,
            browser_manifest=browser,
            snapshot=no_identity,
        ),
        "vNext package identity is unavailable",
        composition.Phase6CompositionError,
    )
    expect_error(
        lambda: composition.build_verification_input(
            task,
            artifact,
            plan,
            desktop_render=desktop,
            mobile_render=mobile,
            builder_receipt=receipt,
            browser_manifest=browser,
            snapshot=no_identity,
        ),
        "vNext package identity is unavailable",
        composition.Phase6CompositionError,
    )

    expect_error(
        lambda: composition.build_verification_plan(
            task,
            replace(artifact, task_id="OTHER-TASK"),
            desktop_render=desktop,
            mobile_render=mobile,
            builder_receipt=receipt,
            browser_manifest=browser,
            snapshot=vnext_snapshot,
        ),
        "artifact is not bound to the frozen task criteria",
        composition.Phase6CompositionError,
    )
    Path(artifact.path).write_text(
        "<!doctype html><html><main>drift</main></html>", encoding="utf-8"
    )
    expect_error(
        lambda: composition.build_verification_plan(
            task,
            artifact,
            desktop_render=desktop,
            mobile_render=mobile,
            builder_receipt=receipt,
            browser_manifest=browser,
            snapshot=vnext_snapshot,
        ),
        "artifact bytes do not match the builder packet",
        composition.Phase6CompositionError,
    )

    artifact_path = Path(artifact.path)
    artifact_path.write_text("<!doctype html><html><main>PulsePaw</main></html>", encoding="utf-8")
    desktop.unlink()
    expect_error(
        lambda: composition.build_verification_plan(
            task,
            artifact,
            desktop_render=desktop,
            mobile_render=mobile,
            builder_receipt=receipt,
            browser_manifest=browser,
            snapshot=vnext_snapshot,
        ),
        "composition evidence file is unsafe or unavailable",
        composition.Phase6CompositionError,
    )
    assert input_record.package_digest == vnext_snapshot.package_digest


def test_composition_rejects_malformed_builder_handoff_variants(
    tmp_path: Path, vnext_snapshot
) -> None:
    cases = (
        (
            "invalid-json",
            lambda path, source: path.write_text("{", encoding="utf-8"),
            "builder handoff cannot be read as JSON",
        ),
        (
            "non-object",
            lambda path, source: path.write_text("[]", encoding="utf-8"),
            "builder handoff must be an object",
        ),
        (
            "unbound-status",
            lambda path, source: path.write_text(
                json.dumps({**json.loads(path.read_text(encoding="utf-8")), "status": "FAIL"}),
                encoding="utf-8",
            ),
            "builder handoff is not bound to the current artifact",
        ),
        (
            "missing-host",
            lambda path, source: path.write_text(
                json.dumps(
                    {
                        key: value
                        for key, value in json.loads(path.read_text(encoding="utf-8")).items()
                        if key != "host_invocation_id"
                    }
                ),
                encoding="utf-8",
            ),
            "builder host invocation identity is missing",
        ),
        (
            "bad-source-digest",
            lambda path, source: path.write_text(
                json.dumps(
                    {**json.loads(path.read_text(encoding="utf-8")), "source_receipt_digest": "bad"}
                ),
                encoding="utf-8",
            ),
            "source_receipt_digest is not a sha256 digest",
        ),
        (
            "missing-source-path",
            lambda path, source: path.write_text(
                json.dumps(
                    {**json.loads(path.read_text(encoding="utf-8")), "source_receipt_path": None}
                ),
                encoding="utf-8",
            ),
            "builder handoff source receipt path is missing",
        ),
    )
    for name, mutate, message in cases:
        case_root = tmp_path / name
        task, artifact, _, _, files = composition_fixture(case_root, vnext_snapshot)
        desktop, mobile, receipt, browser = files
        source = case_root / "builder-source.json"
        mutate(receipt, source)

        def build_plan(
            task=task,
            artifact=artifact,
            desktop=desktop,
            mobile=mobile,
            receipt=receipt,
            browser=browser,
        ):
            return composition.build_verification_plan(
                task,
                artifact,
                desktop_render=desktop,
                mobile_render=mobile,
                builder_receipt=receipt,
                browser_manifest=browser,
                snapshot=vnext_snapshot,
            )

        expect_error(
            build_plan,
            message,
            composition.Phase6CompositionError,
        )

    case_root = tmp_path / "stale-source"
    task, artifact, _, _, files = composition_fixture(case_root, vnext_snapshot)
    desktop, mobile, receipt, browser = files
    source = case_root / "builder-source.json"
    source.write_bytes(b"source receipt changed")
    expect_error(
        lambda: composition.build_verification_plan(
            task,
            artifact,
            desktop_render=desktop,
            mobile_render=mobile,
            builder_receipt=receipt,
            browser_manifest=browser,
            snapshot=vnext_snapshot,
        ),
        "builder handoff source receipt digest is stale",
        composition.Phase6CompositionError,
    )


def test_composition_plan_execution_covers_identity_budget_and_output_bounds(
    tmp_path: Path, monkeypatch
) -> None:
    claims = (Claim("C-1", "first"), Claim("C-2", "second"))
    procedures = (
        ProcedureSpec("PROC-1", "C-1", "first"),
        ProcedureSpec("PROC-2", "C-2", "second"),
    )
    plan = make_plan(
        claims=claims,
        procedures=procedures,
        expected_evidence=("C-1-EVIDENCE", "C-2-EVIDENCE"),
        package_digest=PACKAGE_DIGEST,
        manifest_digest=PACKAGE_DIGEST,
    )
    input_record = make_input(
        tmp_path / "identity",
        criteria=("C-1", "C-2"),
        verification_id=plan.verification_id,
        package_digest=PACKAGE_DIGEST,
        manifest_digest=PACKAGE_DIGEST,
        acceptance_criteria_ref=plan.criteria_digest,
    )
    expect_error(
        lambda: composition.run_verification_plan(
            plan,
            replace(input_record, verification_id="OTHER-VERIFICATION", digest=""),
        ),
        "verification input identity does not match the plan",
        composition.Phase6CompositionError,
    )
    expect_error(
        lambda: composition.run_verification_plan(
            plan,
            replace(input_record, deferred_criteria=("optional",), digest=""),
        ),
        "verification input identity does not match the plan",
        composition.Phase6CompositionError,
    )
    expect_error(
        lambda: composition.run_verification_plan(
            plan,
            replace(input_record, manifest_digest="sha256:" + "9" * 64, digest=""),
        ),
        "verification input capability identity does not match the plan",
        composition.Phase6CompositionError,
    )

    def failing_procedure(
        input_value: VerificationInput, procedure: ProcedureSpec
    ) -> ProcedureResult:
        return bound_result(
            input_value,
            criterion_id=procedure.criterion_id,
            status=VerificationStatus.FAIL,
            observation="bounded failure",
        )

    monkeypatch.setattr(composition, "run_deterministic_procedure", failing_procedure)
    clock = iter((0.0, 0.0, 0.0, 2.0, 2.0))
    monkeypatch.setattr(composition.time, "monotonic", lambda: next(clock, 2.0))
    budget_plan = replace(plan, budget=VerificationBudget(max_duration_seconds=1), digest="")
    budget_input = replace(input_record, budgets=budget_plan.budget, digest="")
    run = composition.run_verification_plan(budget_plan, budget_input)
    assert run.procedure_results[0].status is VerificationStatus.FAIL
    assert run.procedure_results[1].status is VerificationStatus.BLOCKED
    assert run.output.status is VerificationStatus.BLOCKED
    assert run.output.stop_reason.value == "BUDGET_EXHAUSTED"

    forged(run.verification_input, budgets=VerificationBudget(max_report_bytes=1))
    expect_error(
        lambda: composition.verification_public_data(run),
        "verification report exceeds its bounded output size",
        composition.Phase6CompositionError,
    )


def test_composition_ack_handoff_and_report_reject_malformed_telemetry(
    tmp_path: Path, vnext_snapshot
) -> None:
    task = make_task(tmp_path)
    artifact = make_artifact(task)
    artifact_ref = ArtifactRef(
        artifact_id=artifact.artifact_id,
        path=artifact.path,
        digest=artifact.digest,
        package_digest=PACKAGE_DIGEST,
        observed_at="2026-08-29T12:00:00Z",
        producer_id="design-director",
        producer_role=VerificationRole.DESIGN_DIRECTOR,
    )
    plan = make_plan(
        task_id=task.task_id,
        run_id=task.run_id,
        criteria_digest=task.criteria.digest,
        package_digest=PACKAGE_DIGEST,
        manifest_digest=MANIFEST_DIGEST,
    )
    input_record = make_input(
        tmp_path,
        criteria=("C-1",),
        artifacts=(artifact_ref,),
        run_id=task.run_id,
        task_id=task.task_id,
        verification_id=plan.verification_id,
        package_digest=PACKAGE_DIGEST,
        manifest_digest=MANIFEST_DIGEST,
        acceptance_criteria_ref=plan.criteria_digest,
    )
    expected = verify_input(input_record, ())
    payload = host_report_payload(task, artifact, plan, input_record, expected)
    valid_message = json.dumps(payload)
    assert composition._acknowledgement_valid(valid_message, task.criteria.digest, artifact.version)
    assert composition._acknowledgement_valid(
        "P6_VNEXT_HOST_ACK verification-loop-vnext VERIFIER "
        f"{task.criteria.digest} {artifact.version}",
        task.criteria.digest,
        artifact.version,
    )
    for message in (None, "", "not-json", "P6_VNEXT_HOST_ACK missing"):
        assert not composition._acknowledgement_valid(
            message,
            task.criteria.digest,
            artifact.version,
        )
    assert not composition._acknowledgement_valid("[]", task.criteria.digest, artifact.version)
    forged_payload = {**payload, "read_only": False}
    assert not composition._acknowledgement_valid(
        json.dumps(forged_payload), task.criteria.digest, artifact.version
    )

    assert composition._host_report_matches(
        valid_message,
        task=task,
        artifact=artifact,
        plan=plan,
        verification_input=input_record,
        expected_output=expected,
    )
    invalid_messages = (
        "",
        "not-json",
        "[]",
        json.dumps({**payload, "marker": "WRONG"}),
        json.dumps({**payload, "task_id": "OTHER-TASK"}),
        json.dumps({**payload, "criteria": []}),
    )
    for message in invalid_messages:
        assert not composition._host_report_matches(
            message,
            task=task,
            artifact=artifact,
            plan=plan,
            verification_input=input_record,
            expected_output=expected,
        )

    handoff = composition._host_handoff(input_record, plan, artifact=artifact)
    decoded = json.loads(handoff)
    assert decoded["artifact"]["content"] == Path(artifact.path).read_text(encoding="utf-8")
    assert decoded["capability"]["input_digest"] == input_record.digest
    missing_artifact_input = replace(input_record, artifact_refs=(), digest="")
    expect_error(
        lambda: composition._host_handoff(missing_artifact_input, plan, artifact=artifact),
        "host handoff is missing the builder artifact",
        composition.Phase6CompositionError,
    )
    stale_ref = replace(artifact_ref, digest="sha256:" + "9" * 64)
    stale_input = replace(input_record, artifact_refs=(stale_ref,), digest="")
    expect_error(
        lambda: composition._host_handoff(stale_input, plan, artifact=artifact),
        "host handoff artifact digest is stale",
        composition.Phase6CompositionError,
    )


def test_host_snapshot_preflight_and_policy_boundaries(
    tmp_path: Path, vnext_snapshot, monkeypatch
) -> None:
    record = vnext_snapshot.record
    assert record is not None
    expect_error(
        lambda: replace(vnext_snapshot, project_root="relative", digest=""),
        "project_root must be absolute",
        host.Phase6HostError,
    )
    expect_error(
        lambda: replace(vnext_snapshot, capability_id="", digest=""),
        "capability_id is required",
        host.Phase6HostError,
    )
    expect_error(
        lambda: replace(
            vnext_snapshot,
            record=replace(record, capability_id="other-capability"),
            digest="",
        ),
        "discovered record does not match capability_id",
        host.Phase6HostError,
    )
    expect_error(
        lambda: replace(vnext_snapshot, package_digest="bad", digest=""),
        "package_digest is invalid",
        host.Phase6HostError,
    )
    expect_error(
        lambda: replace(vnext_snapshot, manifest_digest="bad", digest=""),
        "manifest_digest is invalid",
        host.Phase6HostError,
    )
    expect_error(
        lambda: replace(vnext_snapshot, digest="sha256:" + "9" * 64),
        "host snapshot digest does not match its content",
        host.Phase6HostError,
    )

    missing = tmp_path / "missing-workspace"
    expect_error(
        lambda: host._root(missing, "workspace"),
        "workspace is unavailable",
        host.Phase6HostError,
    )
    file_path = tmp_path / "workspace-file"
    file_path.write_text("file", encoding="utf-8")
    expect_error(
        lambda: host._root(file_path, "workspace"),
        "workspace must be a directory",
        host.Phase6HostError,
    )
    assert host._manifest_digest(record).startswith("sha256:")
    assert host._manifest_digest(replace(record, manifest_path=None)) is None
    assert host._manifest_digest(replace(record, manifest_path="missing.json")) is None
    assert isinstance(host._policy(None, PROJECT_ROOT), host.ExecutionPolicyRegistry)
    assert isinstance(
        host._policy(PROJECT_ROOT / "config" / "missing-policy.json", PROJECT_ROOT),
        host.ExecutionPolicyRegistry,
    )
    outside_policy = tmp_path / "outside-policy.json"
    outside_policy.write_text("{}", encoding="utf-8")
    expect_error(
        lambda: host._policy(outside_policy, PROJECT_ROOT),
        "Phase 6 execution policy cannot be loaded safely",
        host.Phase6HostError,
    )

    valid_preflight = host.prepare_vnext_preflight(
        PROJECT_ROOT,
        snapshot=vnext_snapshot,
        task_id="TASK-HOST-BOUNDARY",
        run_id="RUN-HOST-BOUNDARY",
        task="Verify one bounded host request.",
        acceptance_criteria=("the host request remains read-only",),
        policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
        mode=ExecutionMode.CONTROLLED_REAL,
    )
    assert valid_preflight.allowed is True
    assert valid_preflight.prepared is not None
    expect_error(
        lambda: host.Phase6Preflight(
            snapshot=vnext_snapshot,
            mode="invalid",
            allowed=False,
            blockers=("BLOCKED",),
            warnings=(),
            prepared=None,
        ),
        "preflight mode is invalid",
        host.Phase6HostError,
    )
    expect_error(
        lambda: host.Phase6Preflight(
            snapshot=vnext_snapshot,
            mode=ExecutionMode.PREPARE_ONLY,
            allowed=True,
            blockers=(),
            warnings=(),
            prepared=None,
        ),
        "allowed preflight must carry a prepared invocation",
        host.Phase6HostError,
    )
    expect_error(
        lambda: host.Phase6Preflight(
            snapshot=vnext_snapshot,
            mode=ExecutionMode.CONTROLLED_REAL,
            allowed=False,
            blockers=("BLOCKED",),
            warnings=(),
            prepared=valid_preflight.prepared,
        ),
        "preflight status is not bound to Phase 4 preparation",
        host.Phase6HostError,
    )

    blocked_snapshot = replace(
        vnext_snapshot,
        record=None,
        package_digest=None,
        manifest_digest=None,
        blockers=("CAPABILITY_NOT_DISCOVERED",),
        digest="",
    )
    blocked_preflight = host.prepare_vnext_preflight(
        PROJECT_ROOT,
        snapshot=blocked_snapshot,
        task_id="TASK-HOST-BLOCKED",
        run_id="RUN-HOST-BLOCKED",
        task="Verify a blocked host request.",
        acceptance_criteria=("blocked before invocation",),
        policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
    )
    assert blocked_preflight.allowed is False
    assert blocked_preflight.prepared is None
    assert "CAPABILITY_NOT_DISCOVERED" in blocked_preflight.blockers
    assert "CAPABILITY_NOT_ELIGIBLE" in blocked_preflight.blockers
    assert blocked_preflight.host_invoked is False
    deduplicated = host.Phase6Preflight(
        snapshot=blocked_snapshot,
        mode=ExecutionMode.PREPARE_ONLY,
        allowed=False,
        blockers=("BLOCKED", "BLOCKED"),
        warnings=("WARN", "WARN"),
        prepared=None,
    )
    assert deduplicated.blockers == ("BLOCKED",)
    assert deduplicated.warnings == ("WARN",)
    expect_error(
        lambda: host.Phase6Preflight(
            snapshot=blocked_snapshot,
            mode=ExecutionMode.PREPARE_ONLY,
            allowed=False,
            blockers=("BLOCKED",),
            warnings=(),
            prepared=None,
            host_invoked=True,
        ),
        "preflight cannot claim host invocation",
        host.Phase6HostError,
    )
    expect_error(
        lambda: replace(blocked_preflight, digest="sha256:" + "9" * 64),
        "preflight digest does not match its content",
        host.Phase6HostError,
    )

    monkeypatch.setattr(host, "read_bounded_file", lambda *_args, **_kwargs: b"[]")
    expect_error(
        lambda: host._policy(
            PROJECT_ROOT / "config" / "phase6-execution-policy.json", PROJECT_ROOT
        ),
        "Phase 6 execution policy must be an object",
        host.Phase6HostError,
    )
    monkeypatch.setattr(host, "read_bounded_file", lambda *_args, **_kwargs: b"{}")
    expect_error(
        lambda: host._policy(
            PROJECT_ROOT / "config" / "phase6-execution-policy.json", PROJECT_ROOT
        ),
        "Phase 6 execution policy cannot be loaded safely",
        host.Phase6HostError,
    )

    def raise_policy_error(*_args, **_kwargs):
        raise host.Phase6HostError("policy unavailable")

    monkeypatch.setattr(host, "_policy", raise_policy_error)
    policy_blocked = host.prepare_vnext_preflight(
        PROJECT_ROOT,
        snapshot=vnext_snapshot,
        task_id="TASK-HOST-POLICY-BLOCKED",
        run_id="RUN-HOST-POLICY-BLOCKED",
        task="Verify policy failure remains fail closed.",
        acceptance_criteria=("policy failure blocks invocation",),
        policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
    )
    assert policy_blocked.allowed is False
    assert policy_blocked.prepared is None
    assert "EXECUTION_POLICY_UNAVAILABLE" in policy_blocked.blockers
    assert "policy unavailable" in policy_blocked.blockers


def test_host_adapter_rejects_forged_request_identity_and_malformed_telemetry(
    tmp_path: Path, monkeypatch
) -> None:
    def fresh_request():
        prepared = host.prepare_vnext_preflight(
            PROJECT_ROOT,
            task_id="TASK-HOST-ADAPTER",
            run_id="RUN-HOST-ADAPTER",
            task="Verify one bounded host request.",
            acceptance_criteria=("the request is local and read-only",),
            policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
            mode=ExecutionMode.CONTROLLED_REAL,
        ).prepared
        assert prepared is not None
        assert prepared.request is not None
        return prepared.request

    adapter = host.Phase6AppServerAdapter()
    valid_request = fresh_request()
    assert adapter._skill_is_discovered({"malformed": object()}, valid_request) is True

    wrong_skill = fresh_request()
    forged(wrong_skill, skill_name="other-capability")
    assert adapter._skill_is_discovered({}, wrong_skill) is False

    wrong_path = fresh_request()
    forged(wrong_path, skill_path=str(Path(wrong_path.skill_path).with_name("manifest.json")))
    assert adapter._skill_is_discovered({}, wrong_path) is False

    outside_workspace = fresh_request()
    forged(outside_workspace, workspace=str(tmp_path))
    assert adapter._skill_is_discovered({}, outside_workspace) is False

    malformed_manifest = fresh_request()
    monkeypatch.setattr(host, "read_bounded_file", lambda *_args, **_kwargs: b"{")
    assert adapter._skill_is_discovered({}, malformed_manifest) is False


def test_composition_validates_each_host_preflight_binding_without_side_effects(
    tmp_path: Path, vnext_snapshot
) -> None:
    mutations = (
        (
            "snapshot",
            "host preflight snapshot is not bound to discovery",
            lambda preflight: forged(preflight.snapshot, digest="sha256:" + "9" * 64),
        ),
        (
            "package",
            "host preflight package is not bound to discovery",
            lambda preflight: forged(preflight.snapshot, package_digest="sha256:" + "9" * 64),
        ),
        (
            "manifest",
            "host preflight manifest is not bound to discovery",
            lambda preflight: forged(preflight.snapshot, manifest_digest="sha256:" + "9" * 64),
        ),
        (
            "mode",
            "host preflight is not allowed for controlled real execution",
            lambda preflight: forged(preflight, mode=ExecutionMode.PREPARE_ONLY),
        ),
        (
            "allowed",
            "host preflight is not allowed for controlled real execution",
            lambda preflight: forged(preflight, allowed=False),
        ),
        (
            "prepared",
            "host preflight has no prepared invocation",
            lambda preflight: forged(preflight, prepared=None),
        ),
        (
            "fingerprint",
            "prepared capability fingerprint is not bound to discovery",
            lambda preflight: forged(preflight.prepared.record, content_hash="sha256:" + "9" * 64),
        ),
        (
            "authorization-task",
            "host preflight authorization identity is not bound",
            lambda preflight: forged(preflight.prepared.request.authorization, task_id="other"),
        ),
        (
            "authorization-run",
            "host preflight authorization identity is not bound",
            lambda preflight: forged(preflight.prepared.request.authorization, run_id="other"),
        ),
        (
            "authorization-capability",
            "host preflight capability is not bound",
            lambda preflight: forged(
                preflight.prepared.request.authorization, capability_id="other"
            ),
        ),
        (
            "authorization-package",
            "host preflight package fingerprint is not bound",
            lambda preflight: forged(
                preflight.prepared.request.authorization,
                package_fingerprint="sha256:" + "9" * 64,
            ),
        ),
        (
            "authorization-mode",
            "host preflight mode is not controlled real",
            lambda preflight: forged(
                preflight.prepared.request.authorization,
                requested_execution_mode=ExecutionMode.PREPARE_ONLY,
            ),
        ),
        (
            "context-task",
            "host preflight context identity is not bound",
            lambda preflight: forged(preflight.prepared.request.context, task_id="other"),
        ),
        (
            "context-capability",
            "host preflight context identity is not bound",
            lambda preflight: forged(preflight.prepared.request.context, capability_id="other"),
        ),
        (
            "context-package",
            "host preflight context package is not bound",
            lambda preflight: forged(
                preflight.prepared.request.context,
                package_fingerprint="sha256:" + "9" * 64,
            ),
        ),
        (
            "context-task-digest",
            "host preflight context task is not bound",
            lambda preflight: forged(
                preflight.prepared.request.context,
                task_digest="sha256:" + "9" * 64,
            ),
        ),
        (
            "context-criteria",
            "host preflight acceptance criteria are not exact",
            lambda preflight: forged(
                preflight.prepared.request.context, acceptance_criteria=("other",)
            ),
        ),
        (
            "request-task",
            "prepared host request is not exact",
            lambda preflight: forged(preflight.prepared.request, task="other"),
        ),
        (
            "request-criteria",
            "prepared host request is not exact",
            lambda preflight: forged(preflight.prepared.request, acceptance_criteria=("other",)),
        ),
        (
            "request-workspace",
            "prepared host workspace is not exact",
            lambda preflight: forged(preflight.prepared.request, workspace="/tmp/other"),
        ),
        (
            "request-skill",
            "prepared host capability path is not exact",
            lambda preflight: forged(preflight.prepared.request, skill_name="other"),
        ),
        (
            "request-path",
            "prepared host capability path is not exact",
            lambda preflight: forged(preflight.prepared.request, skill_path="/tmp/other/SKILL.md"),
        ),
        (
            "request-idempotency",
            "prepared host idempotency binding is invalid",
            lambda preflight: forged(preflight.prepared.request, idempotency_key="IDEM-forged"),
        ),
    )
    for index, (name, message, mutate) in enumerate(mutations):
        task, artifact, _plan, _input_record, preflight, prompt = host_preflight_fixture(
            tmp_path / f"validate-{index}-{name}", vnext_snapshot
        )
        artifact_before = Path(artifact.path).read_bytes()
        mutate(preflight)

        def validate_preflight(preflight=preflight, task=task, artifact=artifact, prompt=prompt):
            return composition._validate_host_preflight(
                preflight,
                task=task,
                snapshot=vnext_snapshot,
                version=artifact.version,
                label="PIPELINE",
                prompt=prompt,
            )

        expect_error(
            validate_preflight,
            message,
            composition.Phase6CompositionError,
        )
        assert Path(artifact.path).read_bytes() == artifact_before


def test_composition_maps_host_statuses_and_preserves_telemetry_limitations(
    tmp_path: Path, vnext_snapshot, monkeypatch
) -> None:
    task, artifact, plan, input_record, preflight, _prompt = host_preflight_fixture(
        tmp_path, vnext_snapshot
    )
    expected = verify_input(input_record, ())
    valid_message = json.dumps(host_report_payload(task, artifact, plan, input_record, expected))
    selected: list[SimpleNamespace] = []

    class FakeEngine:
        def __init__(self, *_args, **_kwargs):
            pass

        def execute_prepared(self, prepared):
            assert prepared is preflight.prepared
            return selected[0]

    monkeypatch.setattr(composition, "InvocationEngine", FakeEngine)

    def outcome(
        status: InvocationResultStatus,
        message: str | None,
        *,
        load: HostLoadObservation = HostLoadObservation.OBSERVED,
        invoked: bool = True,
        executed: bool = True,
        error: str | None = None,
        with_host_result: bool = True,
    ) -> SimpleNamespace:
        result = (
            SimpleNamespace(
                final_message=message,
                load_observation=load,
                execution_observed=executed,
                error_code=error,
            )
            if with_host_result
            else None
        )
        return SimpleNamespace(
            status=status,
            host_result=result,
            host_invoked=invoked,
            receipt=SimpleNamespace(
                invocation_id="INV-HOST-PIPELINE",
                receipt_digest=PACKAGE_DIGEST,
            ),
            verification=SimpleNamespace(digest=PACKAGE_DIGEST),
        )

    cases = (
        (
            outcome(InvocationResultStatus.SUCCESS, valid_message),
            VerificationStatus.PASS,
            True,
            True,
            False,
        ),
        (
            outcome(
                InvocationResultStatus.SUCCESS,
                "malformed telemetry",
                load=HostLoadObservation.UNOBSERVABLE,
            ),
            VerificationStatus.FAIL,
            False,
            False,
            True,
        ),
        (
            outcome(InvocationResultStatus.FAILURE, None, error="HOST_FAILED"),
            VerificationStatus.FAIL,
            False,
            False,
            False,
        ),
        (
            outcome(InvocationResultStatus.TIMED_OUT, None, error="HOST_TIMEOUT"),
            VerificationStatus.FAIL,
            False,
            False,
            False,
        ),
        (
            outcome(InvocationResultStatus.PARTIAL, None, error="HOST_PARTIAL"),
            VerificationStatus.PARTIAL,
            False,
            False,
            False,
        ),
        (
            outcome(
                InvocationResultStatus.BLOCKED,
                None,
                invoked=False,
                executed=False,
                with_host_result=False,
            ),
            VerificationStatus.BLOCKED,
            False,
            False,
            True,
        ),
        (
            outcome(InvocationResultStatus.CANCELLED, None, error="CANCELLED"),
            VerificationStatus.BLOCKED,
            False,
            False,
            False,
        ),
    )
    for selected_outcome, status, ack, report, limited in cases:
        selected[:] = [selected_outcome]
        probe, returned = composition.invoke_vnext_host_probe(
            task,
            artifact,
            snapshot=vnext_snapshot,
            policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
            plan=plan,
            verification_input=input_record,
            expected_output=expected,
            preflight=preflight,
            artifact_version=artifact.version,
            invocation_label="PIPELINE",
        )
        assert returned is selected_outcome
        assert probe.status is status
        assert probe.acknowledgement_valid is ack
        assert probe.report_valid is report
        assert ("host_skill_load_event_unobservable" in probe.limitations) is limited
        assert "host_report_is_not_local_factual_evidence" in probe.limitations

    invalid_snapshot = replace(
        vnext_snapshot, record=None, package_digest=None, manifest_digest=None, digest=""
    )
    expect_error(
        lambda: composition.invoke_vnext_host_probe(
            task,
            artifact,
            snapshot=invalid_snapshot,
            policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
            plan=plan,
            verification_input=input_record,
            expected_output=expected,
            preflight=preflight,
        ),
        "vNext capability is not exactly discovered",
        composition.Phase6CompositionError,
    )
    expect_error(
        lambda: composition.invoke_vnext_host_probe(
            task,
            artifact,
            snapshot=vnext_snapshot,
            policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
            plan=plan,
            verification_input=input_record,
            expected_output=expected,
            preflight=preflight,
            invocation_label="bad\x00label",
        ),
        "invocation_label is invalid",
        composition.Phase6CompositionError,
    )
    monkeypatch.setattr(composition, "_validate_host_preflight", lambda *_args, **_kwargs: None)
    no_prepared = replace(preflight, allowed=False, prepared=None, digest="")
    expect_error(
        lambda: composition.invoke_vnext_host_probe(
            task,
            artifact,
            snapshot=vnext_snapshot,
            policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
            plan=plan,
            verification_input=input_record,
            expected_output=expected,
            preflight=no_prepared,
        ),
        "host preflight has no prepared invocation",
        composition.Phase6CompositionError,
    )
