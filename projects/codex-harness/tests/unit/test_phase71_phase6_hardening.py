from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from harness_kernel.phase5_models import AcceptanceCriteria, ArtifactPacket, Phase5Task, VisualBrief
from harness_kernel.phase6_composition import (
    HostProbe,
    Phase6CompositionError,
    VerificationPlan,
    build_verification_input,
    build_verification_plan,
    run_verification_plan,
    verification_public_data,
)
from harness_kernel.phase6_host import discover_vnext_package
from harness_kernel.phase6_models import (
    ArtifactRef,
    Claim,
    CriterionResult,
    Evidence,
    EvidenceKind,
    EvidenceRef,
    FindingSeverity,
    FreshnessStatus,
    ProcedureResult,
    ProcedureSpec,
    ReadOnlyPolicy,
    StopCondition,
    VerificationBudget,
    VerificationInput,
    VerificationOutput,
    VerificationProfile,
    VerificationRole,
    VerificationStatus,
)

PROJECT_ROOT = Path(__file__).parents[2]
PACKAGE_DIGEST = "sha256:" + "1" * 64
MANIFEST_DIGEST = "sha256:" + "2" * 64
ARTIFACT_DIGEST = "sha256:" + "3" * 64
OBSERVED_AT = "2026-08-29T12:00:00Z"


def assert_error(
    factory: Callable[[], object], message: str, error_type: type[ValueError] = ValueError
) -> None:
    with pytest.raises(error_type) as caught:
        factory()
    assert str(caught.value) == message


def digest_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def make_task(tmp_path: Path, *, dimensions: tuple[str, ...] = ("ART_DIRECTION",)) -> Phase5Task:
    workspace = tmp_path / "workspace"
    artifact_root = workspace / "artifacts"
    artifact_root.mkdir(parents=True)
    return Phase5Task(
        task_id="TASK-P6-71",
        run_id="RUN-P6-71",
        title="Phase 6 hardening fixture",
        request="Verify one immutable HTML artifact.",
        workspace=str(workspace),
        artifact_root=str(artifact_root),
        brief=VisualBrief(
            outcome="make the artifact verifiable",
            audience="reviewers",
            job="inspect the deterministic result",
            thesis="identity must remain bound",
            medium="HTML",
            primary_action="Call the triage team",
            exact_copy={"product": "PulsePaw"},
            must_include=(),
            must_avoid=(),
            responsive_intent="stable",
            accessibility_intent="semantic",
            asset_role="pilot",
        ),
        criteria=AcceptanceCriteria(dimensions=dimensions),
        created_at=1_756_000_000,
    )


def make_artifact(task: Phase5Task, *, content: str | None = None) -> ArtifactPacket:
    artifact_path = Path(task.artifact_root) / "index.html"
    artifact_content = content or "<!doctype html><html><main>PulsePaw</main></html>"
    artifact_path.write_text(artifact_content, encoding="utf-8")
    return ArtifactPacket.from_content(
        artifact_id="ART-1",
        version="artifact_v1",
        path=str(artifact_path),
        content=artifact_content,
        producer_capability="design-director",
        invocation_id="INV-BUILDER-1",
        task=task,
    )


def write_composition_files(
    task: Phase5Task, artifact: ArtifactPacket
) -> tuple[Path, Path, Path, Path]:
    root = Path(task.workspace).parent
    desktop, mobile = root / "desktop.png", root / "mobile.png"
    source, receipt = root / "builder-source.json", root / "builder-receipt.json"
    browser = root / "browser-manifest.json"
    desktop.write_bytes(b"desktop-render")
    mobile.write_bytes(b"mobile-render")
    source.write_bytes(b"source-receipt")
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "P6-BUILDER-HANDOFF-1",
                "task_id": task.task_id,
                "run_id": task.run_id,
                "status": "PASS",
                "artifact_id": artifact.artifact_id,
                "artifact_version": artifact.version,
                "artifact_path": artifact.path,
                "artifact_digest": artifact.digest,
                "artifact_size_bytes": artifact.size_bytes,
                "acceptance_digest": task.criteria.digest,
                "producer_capability": "design-director",
                "producer_invocation_id": artifact.invocation_id,
                "host_invocation_id": "INV-HOST-1",
                "source_receipt_digest": digest_bytes(source.read_bytes()),
                "source_receipt_path": str(source),
            }
        ),
        encoding="utf-8",
    )
    browser.write_text('{"capture":"current"}', encoding="utf-8")
    return desktop, mobile, receipt, browser


def make_input(
    tmp_path: Path,
    *,
    criteria: tuple[str, ...] = ("C-1",),
    artifacts: tuple[ArtifactRef, ...] = (),
    evidence_refs: tuple[EvidenceRef, ...] = (),
    **overrides: object,
) -> VerificationInput:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    values: dict[str, object] = {
        "run_id": "RUN-P6-MODEL",
        "task_id": "TASK-P6-MODEL",
        "capability_id": "verification-loop-vnext",
        "package_digest": PACKAGE_DIGEST,
        "manifest_digest": MANIFEST_DIGEST,
        "workspace": str(workspace),
        "required_criteria": criteria,
        "artifact_refs": artifacts,
        "evidence_refs": evidence_refs,
        "observed_at": OBSERVED_AT,
    }
    values.update(overrides)
    return VerificationInput(**values)


def make_artifact_ref(workspace: str, *, artifact_id: str = "ART-1") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        path=str(Path(workspace) / f"{artifact_id}.html"),
        digest=ARTIFACT_DIGEST,
        package_digest=PACKAGE_DIGEST,
        observed_at=OBSERVED_AT,
        producer_id="design-director",
        producer_role=VerificationRole.DESIGN_DIRECTOR,
    )


def make_evidence(
    *,
    criterion_id: str = "C-1",
    evidence_id: str = "EVID-1",
    artifact_id: str | None = "ART-1",
    artifact_digest: str | None = ARTIFACT_DIGEST,
    package_digest: str | None = PACKAGE_DIGEST,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
    observed_at: str | int = OBSERVED_AT,
    kind: EvidenceKind = EvidenceKind.OBSERVATION,
    observation: str = "deterministic observation",
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        criterion_id=criterion_id,
        artifact_refs=(artifact_id,) if artifact_id is not None else (),
        artifact_digest=artifact_digest,
        package_digest=package_digest,
        observed_at=observed_at,
        freshness=freshness,
        kind=kind,
        observation=observation,
    )


def make_evidence_ref(
    evidence: Evidence,
    *,
    run_id: str = "RUN-P6-MODEL",
    task_id: str = "TASK-P6-MODEL",
) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=evidence.evidence_id,
        digest=evidence.digest,
        artifact_id=evidence.artifact_refs[0] if evidence.artifact_refs else None,
        artifact_digest=evidence.artifact_digest,
        package_digest=evidence.package_digest,
        observed_at=evidence.observed_at,
        freshness=evidence.freshness,
        run_id=run_id,
        task_id=task_id,
    )


def make_result(
    verification_input: VerificationInput,
    *,
    criterion_id: str = "C-1",
    status: VerificationStatus = VerificationStatus.PASS,
    executed: bool = True,
    evidence: tuple[Evidence, ...] = (),
    observation: str = "procedure observation",
) -> ProcedureResult:
    spec = ProcedureSpec(f"PROC-{criterion_id}", criterion_id, "deterministic test procedure")
    return ProcedureResult(
        spec=spec,
        status=status,
        executed=executed,
        evidence=evidence,
        attempts=1 if executed else 0,
        observed_at=verification_input.observed_at,
        observation=observation,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
        verifier_id=verification_input.capability_id,
    )


def make_criterion(
    verification_input: VerificationInput,
    *,
    criterion_id: str | None = None,
    status: VerificationStatus,
    evidence: tuple[Evidence, ...] = (),
    reason: str = "condition requires follow-up",
) -> CriterionResult:
    selected = criterion_id or verification_input.claims[0].criterion_id
    claim = next(item for item in verification_input.claims if item.criterion_id == selected)
    procedure = ProcedureSpec(f"PROC-{selected}", selected, "criterion procedure")
    return CriterionResult(
        criterion_id=selected,
        claim=claim,
        procedure=procedure,
        evidence=evidence,
        status=status,
        reason=reason,
    )


def make_plan(
    *,
    claims: tuple[Claim, ...] | tuple[object, ...] | None = None,
    procedures: tuple[ProcedureSpec, ...] | tuple[object, ...] | None = None,
    expected_evidence: tuple[str, ...] | None = None,
    **overrides: object,
) -> VerificationPlan:
    selected_claims: tuple[object, ...] = (
        (Claim("C-1", "C-1 is satisfied"),) if claims is None else claims
    )
    selected_procedures = (
        tuple(
            ProcedureSpec(f"PROC-{item.criterion_id}", item.criterion_id, "bounded procedure")
            for item in selected_claims
            if isinstance(item, Claim)
        )
        if procedures is None
        else procedures
    )
    selected_expected = (
        tuple(
            f"{item.criterion_id}-EVIDENCE" for item in selected_claims if isinstance(item, Claim)
        )
        if expected_evidence is None
        else expected_evidence
    )
    values: dict[str, object] = {
        "verification_id": "VERIFICATION-P6-71",
        "task_id": "TASK-P6-MODEL",
        "run_id": "RUN-P6-MODEL",
        "profile": VerificationProfile.COMPOSITION,
        "criteria_digest": PACKAGE_DIGEST,
        "claims": selected_claims,
        "procedures": selected_procedures,
        "expected_evidence": selected_expected,
        "blocked_procedures": (),
        "budget": VerificationBudget(),
    }
    values.update(overrides)
    return VerificationPlan(**values)


def test_claim_and_procedure_spec_fail_closed_at_identity_and_json_boundaries() -> None:
    claim = Claim(claim_id="C-CLAIM", text="claim text")
    assert claim.criterion_id == "C-CLAIM"
    assert claim.claim_id == "C-CLAIM"
    assert_error(lambda: Claim(), "claim criterion_id is required")
    assert_error(
        lambda: Claim(criterion_id="C-ONE", claim_id="C-TWO", text="claim text"),
        "claim_id and criterion_id must match",
    )
    cases = (
        ({"value": float("nan")}, "procedure parameters.value contains a non-finite number"),
        ({1: "invalid key"}, "procedure parameters has an invalid object key"),
        ({"value": object()}, "procedure parameters.value must contain JSON-shaped values"),
    )
    for parameters, message in cases:
        assert_error(
            lambda parameters=parameters: ProcedureSpec(
                procedure_id="PROC-JSON",
                criterion_id="C-1",
                description="bounded parameters",
                parameters=parameters,  # type: ignore[arg-type]
            ),
            message,
        )


def test_procedure_result_preserves_execution_and_evidence_invariants() -> None:
    spec = ProcedureSpec("PROC-1", "C-1", "deterministic procedure")
    evidence = make_evidence()
    cases: tuple[tuple[Callable[[], object], str], ...] = (
        (lambda: ProcedureResult(spec=object()), "procedure spec is invalid"),
        (lambda: ProcedureResult(), "procedure result needs a spec or procedure identity"),
        (
            lambda: ProcedureResult(spec=spec, executed=True, attempts=0),
            "an executed procedure must record an attempt",
        ),
        (
            lambda: ProcedureResult(spec=spec, evidence=(object(),)),
            "procedure evidence contains an invalid record",
        ),
        (
            lambda: ProcedureResult(spec=spec, evidence=(evidence, replace(evidence))),
            "procedure evidence IDs must be unique",
        ),
        (
            lambda: ProcedureResult(spec=spec, evidence=(evidence,), evidence_refs=("OTHER",)),
            "procedure evidence_refs must match evidence",
        ),
        (
            lambda: ProcedureResult(spec=spec, output=[]),
            "procedure output must be a mapping",
        ),
        (
            lambda: ProcedureResult(spec=spec, run_id="RUN-1"),
            "procedure binding fields must be complete",
        ),
    )
    for factory, message in cases:
        assert_error(factory, message)

    result = ProcedureResult(procedure_id="PROC-IMPLICIT", criterion_id="C-1")
    tool_spec = ProcedureSpec("PROC-TOOL", "C-1", "tool procedure", required_tool="render-observer")
    assert result.spec is not None
    assert result.spec.procedure_id == "PROC-IMPLICIT"
    assert tool_spec.tool == "render-observer"


def test_criterion_result_rejects_unbound_pass_lineage_and_exposes_observations(
    tmp_path: Path,
) -> None:
    input_record = make_input(tmp_path)
    claim = input_record.claims[0]
    spec = ProcedureSpec("PROC-1", "C-1", "criterion procedure")
    evidence = make_evidence()
    passing = ProcedureResult(
        spec=spec,
        status=VerificationStatus.PASS,
        executed=True,
        attempts=1,
        evidence=(evidence,),
        observation="procedure observation",
    )
    cases: tuple[tuple[Callable[[], object], str], ...] = (
        (
            lambda: CriterionResult("C-1", Claim("C-OTHER", "other"), spec),
            "criterion result claim is not bound",
        ),
        (
            lambda: CriterionResult("C-1", claim, object()),
            "criterion result procedure is invalid",
        ),
        (
            lambda: CriterionResult("C-1", claim, spec, evidence=(object(),)),
            "criterion result evidence is invalid",
        ),
        (
            lambda: CriterionResult("C-1", claim, spec, status=VerificationStatus.PASS),
            "PASS needs an executed procedure",
        ),
        (
            lambda: CriterionResult(
                "C-1",
                claim,
                spec,
                procedure_result=replace(passing, executed=False, attempts=0, digest=""),
                evidence=(evidence,),
                status=VerificationStatus.PASS,
            ),
            "PASS needs an executed procedure",
        ),
        (
            lambda: CriterionResult(
                "C-1",
                claim,
                spec,
                procedure_result=replace(passing, status=VerificationStatus.FAIL, digest=""),
                evidence=(evidence,),
                status=VerificationStatus.PASS,
            ),
            "PASS needs a passing procedure result",
        ),
    )
    for factory, message in cases:
        assert_error(factory, message)

    observed = passing.as_criterion_result(claim, status=VerificationStatus.PASS)
    failed = replace(
        passing,
        observation="",
        error="procedure failed",
        digest="",
    ).as_criterion_result(claim, status=VerificationStatus.FAIL)
    empty = replace(passing, observation="", error=None, digest="").as_criterion_result(
        claim, status=VerificationStatus.FAIL
    )
    assert observed.evidence == (evidence,)
    assert observed.observed == "procedure observation"
    assert failed.observed == "procedure failed"
    assert empty.observed == "no observation"


def test_verification_input_rejects_identity_and_evidence_binding_failures(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact = make_artifact_ref(str(workspace))
    evidence_ref = make_evidence_ref(make_evidence())
    cases: tuple[tuple[Callable[[], object], str], ...] = (
        (
            lambda: make_input(tmp_path, criteria=()),
            "required_criteria must be a non-empty list or tuple",
        ),
        (
            lambda: make_input(tmp_path, criteria=("C-1", "C-1")),
            "required criteria must be unique",
        ),
        (lambda: make_input(tmp_path, claims="bad"), "claims must be a list or tuple"),
        (
            lambda: make_input(tmp_path, claims=(object(),)),
            "claims contain an invalid record",
        ),
        (
            lambda: make_input(tmp_path, artifacts=(object(),)),
            "artifact_refs contain an invalid record",
        ),
        (
            lambda: make_input(tmp_path, evidence_refs=(object(),)),
            "evidence_refs contain an invalid record",
        ),
        (
            lambda: make_input(tmp_path, artifacts=(artifact, artifact)),
            "artifact_refs must be unique",
        ),
        (
            lambda: make_input(tmp_path, evidence_refs=(evidence_ref, evidence_ref)),
            "evidence_refs must be unique",
        ),
        (
            lambda: make_input(
                tmp_path,
                artifacts=(replace(artifact, producer_id="verification-loop-vnext"),),
            ),
            "verifier cannot be the artifact producer",
        ),
        (
            lambda: make_input(
                tmp_path,
                artifacts=(replace(artifact, producer_role=VerificationRole.VERIFIER),),
            ),
            "a verifier-produced artifact cannot be self-verified",
        ),
        (
            lambda: make_input(
                tmp_path,
                artifacts=(replace(artifact, package_digest="sha256:" + "9" * 64),),
            ),
            "artifact package digest is not bound",
        ),
        (
            lambda: make_input(
                tmp_path,
                artifacts=(artifact,),
                evidence_refs=(replace(evidence_ref, artifact_id="ART-UNKNOWN"),),
            ),
            "evidence points to an unknown artifact",
        ),
        (
            lambda: make_input(
                tmp_path,
                artifacts=(artifact,),
                evidence_refs=(replace(evidence_ref, artifact_digest="sha256:" + "9" * 64),),
            ),
            "evidence artifact digest is not bound",
        ),
        (
            lambda: make_input(tmp_path, role=VerificationRole.REVIEWER),
            "verification input role must be VERIFIER",
        ),
        (
            lambda: make_input(tmp_path, read_only=False),
            "verification input must be read-only",
        ),
        (
            lambda: make_input(tmp_path, scope="GLOBAL"),
            "verification scope must be PROJECT",
        ),
        (
            lambda: make_input(tmp_path, authority="ORCHESTRATOR"),
            "verification authority must be VERIFIER",
        ),
    )
    for factory, message in cases:
        assert_error(factory, message)

    valid = make_input(
        tmp_path / "valid",
        criteria=("C-1", "C-2"),
        claims=(Claim("C-1", "one"), Claim("C-2", "two")),
    )
    assert valid.claims == (Claim("C-1", "one"), Claim("C-2", "two"))
    assert valid.read_only_policy is ReadOnlyPolicy.READ_ONLY
    assert valid.input_digest == valid.digest


def test_verification_output_derives_status_freshness_and_artifact_lineage(tmp_path: Path) -> None:
    actions = {
        VerificationStatus.NOT_RUN: "RUN_DECLARED_PROCEDURES",
        VerificationStatus.UNKNOWN: "OBTAIN_MISSING_EVIDENCE_AND_RERUN",
        VerificationStatus.PARTIAL: "DISCLOSE_LIMITATIONS_AND_COMPLETE_OPTIONAL_COVERAGE",
        VerificationStatus.FAIL: "RESOLVE_FINDINGS_AND_RERUN",
        VerificationStatus.BLOCKED: "RESOLVE_BLOCKERS_AND_RERUN",
        VerificationStatus.STALE: "REFRESH_ARTIFACT_AND_EVIDENCE_AND_RERUN",
    }
    for index, (status, action) in enumerate(actions.items(), start=1):
        current_input = make_input(tmp_path / status.value, criteria=(f"C-{index}",))
        result = make_criterion(
            current_input,
            criterion_id=f"C-{index}",
            status=status,
        )
        output = VerificationOutput.from_input(current_input, (result,))
        assert output.status is status
        assert output.recommended_next_action == action
        assert output.findings[0].severity is (
            FindingSeverity.MEDIUM
            if status
            in {
                VerificationStatus.NOT_RUN,
                VerificationStatus.UNKNOWN,
                VerificationStatus.PARTIAL,
            }
            else FindingSeverity.HIGH
        )
        assert output.procedures_not_run == (f"PROC-C-{index}",)

    artifact = make_artifact_ref(str(tmp_path / "pass" / "workspace"))
    evidence = make_evidence()
    evidence_ref = make_evidence_ref(evidence)
    pass_input = make_input(
        tmp_path / "pass",
        artifacts=(artifact,),
        evidence_refs=(evidence_ref,),
    )
    pass_result = make_result(pass_input, evidence=(evidence,))
    criterion = pass_result.as_criterion_result(
        pass_input.claims[0], status=VerificationStatus.PASS
    )
    passed = VerificationOutput.from_input(pass_input, (criterion,))
    assert passed.status is VerificationStatus.PASS
    assert passed.artifact_digest_verified is True
    assert passed.artifact_refs == ("ART-1",)
    assert passed.evidence_refs == ("EVID-1",)
    assert passed.freshness_status is FreshnessStatus.FRESH

    stale_ref = replace(evidence_ref, freshness=FreshnessStatus.STALE)
    stale_input = make_input(
        tmp_path / "stale",
        artifacts=(make_artifact_ref(str(tmp_path / "stale" / "workspace")),),
        evidence_refs=(stale_ref,),
    )
    stale_criterion = make_result(stale_input, evidence=(evidence,)).as_criterion_result(
        stale_input.claims[0], status=VerificationStatus.PASS
    )
    assert_error(
        lambda: VerificationOutput.from_input(stale_input, (stale_criterion,)),
        "PASS evidence is stale",
    )


def test_verification_output_rejects_forged_derived_fields_and_tracks_deferred_blockers(
    tmp_path: Path,
) -> None:
    input_record = make_input(tmp_path)
    result = make_criterion(input_record, status=VerificationStatus.FAIL)
    cases = (
        (("artifact_refs", ("ART-FORGED",)), "output artifact references are not bound to input"),
        (("evidence_refs", ("EVID-FORGED",)), "output evidence references are not bound to input"),
        (("status", VerificationStatus.PASS), "status does not match criterion statuses"),
        (("failures", ("C-FORGED",)), "failures does not match failed criteria"),
        (("evidence_used", ("EVID-FORGED",)), "evidence_used does not match criterion evidence"),
        (
            ("recommended_next_action", "DELIVER_OR_PROCEED"),
            "recommended_next_action does not match status",
        ),
    )
    for (field, value), message in cases:
        assert_error(
            lambda field=field, value=value: VerificationOutput.from_input(
                input_record, (result,), **{field: value}
            ),
            message,
        )

    evidence = make_evidence(artifact_id=None, artifact_digest=None)
    deferred_input = make_input(
        tmp_path / "deferred",
        deferred_criteria=("optional-review",),
        evidence_refs=(make_evidence_ref(evidence),),
    )
    passing = make_result(deferred_input, evidence=(evidence,)).as_criterion_result(
        deferred_input.claims[0], status=VerificationStatus.PASS
    )
    output = VerificationOutput.from_input(
        deferred_input,
        (passing,),
        stop_reason=StopCondition.BUDGET_EXHAUSTED,
    )
    assert output.status is VerificationStatus.BLOCKED
    assert output.deferred_procedures == ("NOT-RUN-optional-review",)
    assert output.procedures_not_run == ("NOT-RUN-optional-review",)
    assert output.blockers == ("verification budget exhausted",)


def test_composition_plan_validates_criteria_procedures_and_digests() -> None:
    c1, c2 = Claim("C-1", "first"), Claim("C-2", "second")
    p1, p2 = ProcedureSpec("PROC-1", "C-1", "first"), ProcedureSpec("PROC-2", "C-2", "second")
    cases: tuple[tuple[Callable[[], object], str], ...] = (
        (lambda: make_plan(profile="COMPOSITION"), "verification plan profile is invalid"),
        (lambda: make_plan(claims=()), "verification plan needs claims"),
        (lambda: make_plan(procedures=("PROC-1",)), "verification plan has an invalid procedure"),
        (
            lambda: make_plan(claims=(c1, c1), procedures=(p1, p1)),
            "verification plan criteria must be unique",
        ),
        (
            lambda: make_plan(
                claims=(c1, c2),
                procedures=(p1, ProcedureSpec("PROC-1", "C-2", "second")),
            ),
            "verification plan procedures must be unique",
        ),
        (
            lambda: make_plan(claims=(c1, c2), procedures=(p1,)),
            "each criterion must have exactly one procedure",
        ),
        (
            lambda: make_plan(claims=(c1,), procedures=(p2,)),
            "procedures must cover exactly the frozen criteria",
        ),
        (
            lambda: make_plan(expected_evidence=("C-1-EVIDENCE", "DUPLICATE")),
            "expected evidence must cover every criterion once",
        ),
        (
            lambda: make_plan(blocked_procedures=("PROC-MISSING",)),
            "blocked procedure is not in the plan",
        ),
        (
            lambda: make_plan(deferred_criteria=("C-1",)),
            "deferred criteria must be unique and non-required",
        ),
        (
            lambda: make_plan(package_digest="not-a-digest"),
            "package_digest is not a sha256 digest",
        ),
    )
    for factory, message in cases:
        assert_error(factory, message, Phase6CompositionError)

    valid = make_plan()
    assert valid.digest.startswith("sha256:")
    assert valid.criteria_digest == PACKAGE_DIGEST


@pytest.fixture(scope="module")
def vnext_snapshot():
    return discover_vnext_package(PROJECT_ROOT)


def test_build_verification_plan_binds_every_declared_file_procedure(
    tmp_path: Path, vnext_snapshot
) -> None:
    task = make_task(tmp_path, dimensions=("ART_DIRECTION", "LAYOUT"))
    artifact = make_artifact(task)
    desktop, mobile, receipt, browser = write_composition_files(task, artifact)
    plan = build_verification_plan(
        task,
        artifact,
        desktop_render=desktop,
        mobile_render=mobile,
        builder_receipt=receipt,
        browser_manifest=browser,
        snapshot=vnext_snapshot,
        verification_id="VERIFICATION-COMPOSITION-FIXTURE",
    )
    procedures = {item.criterion_id: item for item in plan.procedures}
    assert len(plan.claims) == 17
    assert procedures["artifact-identity"].parameters["expected_digest"] == artifact.digest
    assert procedures["desktop-render"].parameters["artifact_id"] == "ART-DESKTOP-RENDER"
    assert procedures["mobile-render"].parameters["artifact_id"] == "ART-MOBILE-RENDER"
    assert procedures["builder-receipt"].parameters["artifact_id"] == "ART-BUILDER-RECEIPT"
    browser_parameters = procedures["browser-capture-binding"].parameters
    assert browser_parameters["source_artifact_id"] == artifact.artifact_id
    assert browser_parameters["source_artifact_digest"] == artifact.digest
    assert browser_parameters["desktop_artifact_id"] == "ART-DESKTOP-RENDER"
    assert browser_parameters["mobile_artifact_id"] == "ART-MOBILE-RENDER"
    assert plan.deferred_criteria == ("qualitative-art-direction", "qualitative-layout")


def test_build_verification_input_rebinds_current_artifact_and_detects_drift(
    tmp_path: Path, vnext_snapshot
) -> None:
    task = make_task(tmp_path)
    artifact = make_artifact(task)
    desktop, mobile, receipt, browser = write_composition_files(task, artifact)
    plan = build_verification_plan(
        task,
        artifact,
        desktop_render=desktop,
        mobile_render=mobile,
        builder_receipt=receipt,
        browser_manifest=browser,
        snapshot=vnext_snapshot,
    )
    input_record = build_verification_input(
        task,
        artifact,
        plan,
        desktop_render=desktop,
        mobile_render=mobile,
        builder_receipt=receipt,
        browser_manifest=browser,
        snapshot=vnext_snapshot,
        observed_at=123,
    )
    assert input_record.observed_at == 123
    assert input_record.builder_host_invocation_ref == "INV-HOST-1"
    assert input_record.read_only_policy is ReadOnlyPolicy.MUTATION_DENIED
    assert tuple(item.artifact_id for item in input_record.artifact_refs) == (
        "ART-1",
        "ART-DESKTOP-RENDER",
        "ART-MOBILE-RENDER",
        "ART-BUILDER-RECEIPT",
        "ART-BROWSER-CAPTURE-MANIFEST",
    )
    Path(artifact.path).write_text(
        "<!doctype html><html><main>tampered</main></html>",
        encoding="utf-8",
    )
    assert_error(
        lambda: build_verification_input(
            task,
            artifact,
            plan,
            desktop_render=desktop,
            mobile_render=mobile,
            builder_receipt=receipt,
            browser_manifest=browser,
            snapshot=vnext_snapshot,
            observed_at=123,
        ),
        "artifact changed after the plan was frozen",
        Phase6CompositionError,
    )


def test_run_verification_plan_binds_receipts_and_rejects_identity_drift(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact_path = workspace / "index.html"
    content = b"<!doctype html><main>safe</main>"
    artifact_path.write_bytes(content)
    artifact_digest = digest_bytes(content)
    plan = make_plan(
        procedures=(
            ProcedureSpec(
                "PROC-ARTIFACT",
                "C-1",
                "compare artifact bytes",
                check="FILE_DIGEST",
                parameters={"artifact_id": "ART-1", "expected_digest": artifact_digest},
            ),
        ),
        expected_evidence=("C-1-EVIDENCE",),
        package_digest=PACKAGE_DIGEST,
        manifest_digest=MANIFEST_DIGEST,
    )
    input_record = make_input(
        tmp_path,
        artifacts=(
            ArtifactRef(
                "ART-1",
                str(artifact_path),
                artifact_digest,
                observed_at=OBSERVED_AT,
                producer_id="design-director",
                producer_role=VerificationRole.DESIGN_DIRECTOR,
            ),
        ),
        verification_id=plan.verification_id,
        acceptance_criteria_ref=plan.criteria_digest,
    )
    run = run_verification_plan(plan, input_record)
    report = verification_public_data(run)
    assert run.output.status is VerificationStatus.PASS
    assert run.procedure_results[0].plan_digest == plan.digest
    assert report["schema_version"] == "P6-VERIFICATION-RUN-1"
    assert report["digest"] == run.digest
    assert_error(
        lambda: run_verification_plan(
            plan,
            replace(input_record, required_criteria=("C-OTHER",), claims=(), digest=""),
        ),
        "verification input does not match the frozen plan",
        Phase6CompositionError,
    )
    assert_error(
        lambda: run_verification_plan(
            plan,
            replace(input_record, package_digest="sha256:" + "9" * 64, digest=""),
        ),
        "verification input capability identity does not match the plan",
        Phase6CompositionError,
    )


def test_host_probe_rejects_unobserved_pass_and_invalid_digest_contracts() -> None:
    values: dict[str, object] = {
        "status": VerificationStatus.BLOCKED,
        "invocation_id": "INV-HOST-1",
        "package_digest": PACKAGE_DIGEST,
        "host_invoked": False,
        "execution_observed": False,
        "host_load_observation": "UNAVAILABLE",
        "acknowledgement_valid": False,
        "report_valid": False,
        "response_digest": None,
        "receipt_digest": PACKAGE_DIGEST,
        "result_digest": None,
        "error_code": "HOST_RESULT_UNAVAILABLE",
        "limitations": ("host_report_is_not_local_factual_evidence",),
    }

    def build(**overrides: object) -> HostProbe:
        return HostProbe(**{**values, **overrides})

    cases: tuple[tuple[Callable[[], object], str], ...] = (
        (lambda: build(status="PASS"), "host probe status is invalid"),
        (lambda: build(host_invoked="yes"), "host probe booleans are invalid"),
        (lambda: build(response_digest="not-a-digest"), "response_digest is not a sha256 digest"),
        (lambda: build(result_digest="not-a-digest"), "result_digest is not a sha256 digest"),
        (
            lambda: build(
                status=VerificationStatus.PASS,
                execution_observed=True,
                acknowledgement_valid=True,
                report_valid=True,
                response_digest=PACKAGE_DIGEST,
                error_code=None,
            ),
            "PASS host probe lacks observed bound execution",
        ),
        (
            lambda: build(digest="sha256:" + "9" * 64),
            "host probe digest does not match its content",
        ),
    )
    for factory, message in cases:
        assert_error(factory, message, Phase6CompositionError)

    valid = build()
    assert valid.status is VerificationStatus.BLOCKED
    assert valid.digest.startswith("sha256:")
