from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_phase71_phase6_hardening import (
    PACKAGE_DIGEST,
    make_artifact,
    make_artifact_ref,
    make_evidence,
    make_evidence_ref,
    make_input,
    make_plan,
    make_result,
    make_task,
)

import harness_kernel.phase6_checks as checks
import harness_kernel.phase6_composition as composition
import harness_kernel.phase6_host as host
import harness_kernel.phase6_models as models
import harness_kernel.phase6_verifier as verifier
from harness_kernel.phase6_composition import (
    Phase6CompositionError,
    Phase6VerificationRun,
)
from harness_kernel.phase6_host import (
    Phase6HostError,
    discover_vnext_package,
    prepare_vnext_preflight,
)
from harness_kernel.phase6_models import (
    ArtifactRef,
    Claim,
    CriterionResult,
    Evidence,
    EvidenceKind,
    EvidenceRef,
    Finding,
    FindingSeverity,
    FreshnessStatus,
    ProcedureResult,
    ProcedureSpec,
    StopCondition,
    VerificationOutput,
    VerificationRole,
    VerificationStatus,
)
from harness_kernel.phase6_stop import StopDecision, evaluate_stop
from harness_kernel.phase6_telemetry import (
    Phase6EventType,
    Phase6TelemetryError,
    Phase6TelemetryEvent,
)

PROJECT_ROOT = Path(__file__).parents[2]
OTHER_DIGEST = "sha256:" + "9" * 64


def input_with_artifact(tmp_path: Path) -> tuple[object, object, object]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    artifact = make_artifact_ref(str(workspace))
    template = make_evidence()
    evidence_ref = make_evidence_ref(template)
    verification_input = make_input(
        tmp_path,
        artifacts=(artifact,),
        evidence_refs=(evidence_ref,),
    )
    evidence = replace(
        template,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
    )
    return verification_input, artifact, evidence


def test_models_reject_unconfined_paths_and_publicize_path_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workspace must be an absolute"):
        make_input(tmp_path, workspace="relative/workspace")
    with pytest.raises(ValueError, match="workspace must be an absolute"):
        make_input(tmp_path, workspace=str(tmp_path / ".." / "escape"))
    assert models.public_data(Path("/tmp/phase6-artifact")) == "/tmp/phase6-artifact"


def test_model_digest_and_binding_boundaries_fail_closed(tmp_path: Path) -> None:
    verification_input, _, evidence = input_with_artifact(tmp_path)
    spec = ProcedureSpec("PROC-DIGEST", "C-1", "digest boundary")
    result = make_result(verification_input, evidence=(evidence,), status=VerificationStatus.FAIL)
    criterion = result.as_criterion_result(
        verification_input.claims[0], status=VerificationStatus.FAIL
    )
    output = verifier.verify_input(
        verification_input,
        (make_result(verification_input, evidence=(evidence,)),),
    )

    with pytest.raises(ValueError, match="procedure digest does not match"):
        replace(spec, digest=OTHER_DIGEST)
    with pytest.raises(ValueError, match="evidence digest does not match"):
        replace(evidence, digest=OTHER_DIGEST)
    with pytest.raises(ValueError, match="procedure result digest does not match"):
        replace(result, digest=OTHER_DIGEST)
    with pytest.raises(ValueError, match="criterion result digest does not match"):
        replace(criterion, digest=OTHER_DIGEST)
    with pytest.raises(ValueError, match="report digest does not match"):
        replace(output, report_digest=OTHER_DIGEST)
    with pytest.raises(ValueError, match="evidence binding fields must be complete"):
        Evidence(
            evidence_id="EVID-INCOMPLETE",
            criterion_id="C-1",
            run_id=verification_input.run_id,
        )


def test_models_reject_stale_or_mismatched_evidence_in_pass_results(tmp_path: Path) -> None:
    verification_input, _, evidence = input_with_artifact(tmp_path)
    stale = replace(evidence, freshness=FreshnessStatus.STALE, digest="")
    result = ProcedureResult(
        spec=ProcedureSpec("PROC-C-1", "C-1", "current evidence"),
        status=VerificationStatus.PASS,
        executed=True,
        evidence=(stale,),
        attempts=1,
    )
    with pytest.raises(ValueError, match="PASS needs current evidence"):
        CriterionResult(
            criterion_id="C-1",
            claim=Claim("C-1", "current"),
            procedure=result.spec,
            procedure_result=result,
            evidence=(stale,),
            status=VerificationStatus.PASS,
        )

    wrong_criterion = replace(evidence, criterion_id="C-OTHER", digest="")
    with pytest.raises(ValueError, match="not bound to the criterion"):
        CriterionResult(
            criterion_id="C-1",
            claim=Claim("C-1", "bound"),
            procedure=ProcedureSpec("PROC-C-1", "C-1", "bound"),
            evidence=(wrong_criterion,),
            status=VerificationStatus.FAIL,
        )
    with pytest.raises(ValueError, match="evidence IDs must be unique"):
        CriterionResult(
            criterion_id="C-1",
            claim=Claim("C-1", "unique"),
            procedure=ProcedureSpec("PROC-C-1", "C-1", "unique"),
            evidence=(evidence, evidence),
            status=VerificationStatus.FAIL,
        )
    finding = Finding(
        finding_id="F-ARTIFACT",
        severity=FindingSeverity.HIGH,
        criterion_id="C-1",
        observation="artifact mismatch",
        artifact_ref="ART-1",
    )
    assert finding.artifact_ref == "ART-1"
    with pytest.raises(ValueError, match="finding artifact_ref"):
        replace(finding, artifact_ref="../escape")


def test_model_helpers_report_freshness_and_artifact_integrity_fail_closed(tmp_path: Path) -> None:
    verification_input, _, evidence = input_with_artifact(tmp_path)
    result = make_result(verification_input, evidence=(evidence,)).as_criterion_result(
        verification_input.claims[0], status=VerificationStatus.PASS
    )
    assert models._artifact_digest_verified(verification_input, (result,)) is True

    no_artifact = replace(evidence, artifact_refs=(), artifact_digest=None, digest="")
    no_artifact_result = replace(result, evidence=(no_artifact,), digest="")
    assert models._artifact_digest_verified(verification_input, (no_artifact_result,)) is False

    wrong_digest = replace(evidence, artifact_digest=OTHER_DIGEST, digest="")
    wrong_digest_result = replace(result, evidence=(wrong_digest,), digest="")
    assert models._artifact_digest_verified(verification_input, (wrong_digest_result,)) is False

    stale_ref = replace(verification_input.evidence_refs[0], freshness=FreshnessStatus.STALE)
    stale_input = replace(verification_input, evidence_refs=(stale_ref,), digest="")
    assert models._output_freshness(stale_input, ()) is FreshnessStatus.STALE
    unknown_ref = replace(verification_input.evidence_refs[0], freshness=FreshnessStatus.UNKNOWN)
    unknown_input = replace(verification_input, evidence_refs=(unknown_ref,), digest="")
    assert models._output_freshness(unknown_input, ()) is FreshnessStatus.UNKNOWN
    unknown_evidence = replace(evidence, freshness=FreshnessStatus.UNKNOWN, digest="")
    unknown_result = make_result(
        verification_input,
        evidence=(unknown_evidence,),
        status=VerificationStatus.FAIL,
        executed=False,
    ).as_criterion_result(verification_input.claims[0], status=VerificationStatus.FAIL)
    assert models._output_freshness(verification_input, (unknown_result,)) is (
        FreshnessStatus.UNKNOWN
    )

    with pytest.raises(ValueError, match="verification input digest"):
        replace(verification_input, digest=OTHER_DIGEST)


def test_verification_input_rejects_bound_reference_identity_mismatches(tmp_path: Path) -> None:
    verification_input, _, _ = input_with_artifact(tmp_path)
    reference = verification_input.evidence_refs[0]
    with pytest.raises(ValueError, match="evidence run_id is not bound"):
        replace(
            verification_input,
            evidence_refs=(replace(reference, run_id="RUN-OTHER"),),
            digest="",
        )
    with pytest.raises(ValueError, match="evidence task_id is not bound"):
        replace(
            verification_input,
            evidence_refs=(replace(reference, task_id="TASK-OTHER"),),
            digest="",
        )


def test_verification_output_rejects_unbound_evidence_and_forged_artifact_state(
    tmp_path: Path,
) -> None:
    verification_input, _, evidence = input_with_artifact(tmp_path)
    bad_digest = replace(evidence, observation="tampered", digest="")
    bad_digest_result = make_result(
        verification_input,
        evidence=(bad_digest,),
        status=VerificationStatus.FAIL,
    ).as_criterion_result(verification_input.claims[0], status=VerificationStatus.FAIL)
    with pytest.raises(ValueError, match="criterion evidence digest is not bound"):
        VerificationOutput.from_input(verification_input, (bad_digest_result,))

    unknown_artifact = replace(
        evidence,
        artifact_refs=("ART-UNKNOWN",),
        digest="",
    )
    unknown_input = replace(
        verification_input,
        evidence_refs=(
            EvidenceRef(
                evidence_id=unknown_artifact.evidence_id,
                digest=unknown_artifact.digest,
                package_digest=PACKAGE_DIGEST,
                run_id=verification_input.run_id,
                task_id=verification_input.task_id,
            ),
        ),
        digest="",
    )
    unknown_artifact = replace(
        unknown_artifact,
        input_digest=unknown_input.digest,
        run_id=unknown_input.run_id,
        task_id=unknown_input.task_id,
    )
    unknown_result = make_result(
        unknown_input,
        evidence=(unknown_artifact,),
        status=VerificationStatus.FAIL,
    ).as_criterion_result(unknown_input.claims[0], status=VerificationStatus.FAIL)
    with pytest.raises(ValueError, match="criterion evidence points to an unknown artifact"):
        VerificationOutput.from_input(unknown_input, (unknown_result,))

    failed = make_result(
        verification_input,
        status=VerificationStatus.FAIL,
        executed=False,
    ).as_criterion_result(verification_input.claims[0], status=VerificationStatus.FAIL)
    with pytest.raises(ValueError, match="artifact_digest_verified does not match"):
        VerificationOutput.from_input(
            verification_input,
            (failed,),
            artifact_digest_verified=True,
        )


def test_verification_output_rejects_pass_without_declared_evidence(tmp_path: Path) -> None:
    verification_input = make_input(tmp_path, artifacts=(), evidence_refs=())
    evidence = replace(
        make_evidence(),
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        input_digest=verification_input.digest,
    )
    result = make_result(verification_input, evidence=(evidence,))
    criterion = result.as_criterion_result(
        verification_input.claims[0], status=VerificationStatus.PASS
    )
    with pytest.raises(ValueError, match="PASS evidence is missing"):
        VerificationOutput.from_input(verification_input, (criterion,))

    forged_criterion = criterion
    object.__setattr__(forged_criterion, "evidence", ())
    with pytest.raises(ValueError, match="PASS requires declared evidence"):
        VerificationOutput.from_input(verification_input, (forged_criterion,))


def test_checks_reject_undeclared_artifacts_and_integrity_mismatches(tmp_path: Path) -> None:
    verification_input = make_input(tmp_path)
    missing = checks.check_artifact(verification_input, "ART-MISSING")
    assert missing.status is VerificationStatus.BLOCKED
    assert missing.executed is True

    no_target = ProcedureSpec(
        "PROC-NO-TARGET",
        "C-1",
        "missing artifact",
        check="FILE_DIGEST",
        parameters={"artifact_id": "ART-MISSING"},
    )
    assert checks.run_deterministic_procedure(verification_input, no_target).status is (
        VerificationStatus.BLOCKED
    )
    with pytest.raises(checks.Phase6CheckError, match="artifact_id procedure parameter"):
        checks._target_artifact(
            verification_input,
            ProcedureSpec(
                "PROC-BAD-ID",
                "C-1",
                "bad id",
                check="FILE_DIGEST",
                parameters={"artifact_id": 42},
            ),
        )

    expected_root = tmp_path / "expected"
    artifact = make_artifact_ref(str(expected_root / "workspace"))
    input_with_declared_artifact = make_input(expected_root, artifacts=(artifact,))
    expected_mismatch = ProcedureSpec(
        "PROC-EXPECTED",
        "C-1",
        "expected digest mismatch",
        check="FILE_DIGEST",
        parameters={"artifact_id": artifact.artifact_id, "expected_digest": OTHER_DIGEST},
    )
    result = checks.run_deterministic_procedure(input_with_declared_artifact, expected_mismatch)
    assert result.status is VerificationStatus.FAIL
    assert result.error == "procedure expected digest differs from the declared artifact"


def test_checks_revalidate_declared_file_size_and_digest(tmp_path: Path) -> None:
    path = tmp_path / "declared.txt"
    content = b"declared"
    path.write_bytes(content)
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    assert (
        checks._read_declared_file(
            str(path),
            str(tmp_path),
            expected_digest=digest,
            expected_bytes=len(content) + 1,
        )
        is None
    )
    assert (
        checks._read_declared_file(
            str(path),
            str(tmp_path),
            expected_digest=OTHER_DIGEST,
            expected_bytes=len(content),
        )
        is None
    )


def test_checks_fail_closed_on_a_missing_target_during_artifact_read(tmp_path: Path) -> None:
    verification_input = make_input(tmp_path)
    procedure = ProcedureSpec(
        "PROC-JSON-NO-TARGET",
        "C-1",
        "missing JSON artifact",
        check="JSON_OBJECT",
    )
    assert checks._read_artifact(verification_input, procedure) is None


def test_browser_capture_rejects_duplicate_capture_digests(tmp_path: Path) -> None:
    base_input = make_input(tmp_path, criteria=("browser",))
    workspace = Path(base_input.workspace)
    source_path = workspace / "source.html"
    desktop_path = workspace / "desktop.jpg"
    mobile_path = workspace / "mobile.jpg"
    manifest_path = workspace / "browser-manifest.json"
    source_path.write_text("<!doctype html><main>safe</main>", encoding="utf-8")
    desktop_path.write_bytes(b"desktop")
    mobile_path.write_bytes(b"mobile")

    def digest(path: Path) -> str:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    source = ArtifactRef(
        "ART-SOURCE",
        str(source_path),
        digest(source_path),
        package_digest=base_input.package_digest,
        size_bytes=source_path.stat().st_size,
    )
    desktop = ArtifactRef(
        "ART-DESKTOP",
        str(desktop_path),
        digest(desktop_path),
        package_digest=base_input.package_digest,
        size_bytes=desktop_path.stat().st_size,
    )
    mobile = ArtifactRef(
        "ART-MOBILE",
        str(mobile_path),
        digest(mobile_path),
        package_digest=base_input.package_digest,
        size_bytes=mobile_path.stat().st_size,
    )
    criteria_digest = "sha256:" + "5" * 64
    url = "http://127.0.0.1:8765/artifacts/source.html"
    payload = {
        "schema_version": "P6-BROWSER-CAPTURE-1",
        "task_id": base_input.task_id,
        "run_id": base_input.run_id,
        "criteria_digest": criteria_digest,
        "artifact_id": source.artifact_id,
        "artifact_version": source.version,
        "url": url,
        "browser": {
            "url": url,
            "task_id": base_input.task_id,
            "run_id": base_input.run_id,
            "criteria_digest": criteria_digest,
            "artifact_id": source.artifact_id,
            "artifact_version": source.version,
        },
        "source": {
            "path": source.path,
            "bytes": source.size_bytes,
            "digest": source.digest,
            "served_bytes": source.size_bytes,
            "served_digest": source.digest,
            "served_matches_declared": True,
        },
        "captures": [
            {"path": desktop.path, "bytes": desktop.size_bytes, "digest": desktop.digest},
            {"path": desktop.path, "bytes": desktop.size_bytes, "digest": desktop.digest},
        ],
    }
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest = ArtifactRef(
        "ART-MANIFEST",
        str(manifest_path),
        digest(manifest_path),
        package_digest=base_input.package_digest,
        size_bytes=manifest_path.stat().st_size,
    )
    verification_input = replace(
        base_input,
        artifact_refs=(source, desktop, mobile, manifest),
        digest="",
    )
    procedure = ProcedureSpec(
        "PROC-BROWSER-DUPLICATE",
        "browser",
        "reject duplicate browser capture",
        check="BROWSER_CAPTURE",
        parameters={
            "artifact_id": manifest.artifact_id,
            "expected_digest": manifest.digest,
            "source_artifact_id": source.artifact_id,
            "source_artifact_digest": source.digest,
            "desktop_artifact_id": desktop.artifact_id,
            "desktop_digest": desktop.digest,
            "mobile_artifact_id": mobile.artifact_id,
            "mobile_digest": mobile.digest,
            "task_id": verification_input.task_id,
            "run_id": verification_input.run_id,
            "criteria_digest": criteria_digest,
        },
    )
    result = checks.run_deterministic_procedure(verification_input, procedure)
    assert result.status is VerificationStatus.FAIL
    assert result.error == "browser capture manifest is not bound"


def test_verifier_rejects_evidence_binding_package_and_artifact_forgery(tmp_path: Path) -> None:
    verification_input, _, evidence = input_with_artifact(tmp_path)

    wrong_run = replace(evidence, run_id="RUN-OTHER", digest="")
    with pytest.raises(verifier.Phase6VerificationError, match="not bound to this input"):
        verifier.verify_input(
            verification_input,
            (make_result(verification_input, evidence=(wrong_run,)),),
        )

    undeclared = replace(evidence, evidence_id="EVID-OTHER", digest="")
    with pytest.raises(verifier.Phase6VerificationError, match="not declared by the input"):
        verifier.verify_input(
            verification_input,
            (make_result(verification_input, evidence=(undeclared,)),),
        )

    wrong_package = replace(evidence, package_digest=OTHER_DIGEST, digest="")
    package_input = replace(
        verification_input,
        evidence_refs=(
            EvidenceRef(
                evidence_id=wrong_package.evidence_id,
                digest=wrong_package.digest,
                artifact_id=None,
                package_digest=None,
                run_id=verification_input.run_id,
                task_id=verification_input.task_id,
            ),
        ),
        digest="",
    )
    wrong_package = replace(
        wrong_package,
        input_digest=package_input.digest,
        run_id=package_input.run_id,
        task_id=package_input.task_id,
    )
    with pytest.raises(verifier.Phase6VerificationError, match="package digest"):
        verifier.verify_input(
            package_input,
            (make_result(package_input, evidence=(wrong_package,)),),
        )

    wrong_artifact = replace(evidence, artifact_digest=OTHER_DIGEST, digest="")
    artifact_input = replace(
        verification_input,
        evidence_refs=(
            EvidenceRef(
                evidence_id=wrong_artifact.evidence_id,
                digest=wrong_artifact.digest,
                artifact_id=None,
                artifact_digest=None,
                package_digest=PACKAGE_DIGEST,
                run_id=verification_input.run_id,
                task_id=verification_input.task_id,
            ),
        ),
        digest="",
    )
    wrong_artifact = replace(
        wrong_artifact,
        input_digest=artifact_input.digest,
        run_id=artifact_input.run_id,
        task_id=artifact_input.task_id,
    )
    with pytest.raises(verifier.Phase6VerificationError, match="artifact digest"):
        verifier.verify_input(
            artifact_input,
            (make_result(artifact_input, evidence=(wrong_artifact,)),),
        )

    unknown_artifact = replace(evidence, artifact_refs=("ART-UNKNOWN",), digest="")
    unknown_artifact_input = replace(
        verification_input,
        evidence_refs=(
            EvidenceRef(
                evidence_id=unknown_artifact.evidence_id,
                digest=unknown_artifact.digest,
                artifact_id=None,
                artifact_digest=None,
                package_digest=PACKAGE_DIGEST,
                run_id=verification_input.run_id,
                task_id=verification_input.task_id,
            ),
        ),
        digest="",
    )
    unknown_artifact = replace(
        unknown_artifact,
        input_digest=unknown_artifact_input.digest,
        run_id=unknown_artifact_input.run_id,
        task_id=unknown_artifact_input.task_id,
    )
    with pytest.raises(verifier.Phase6VerificationError, match="artifact is not declared"):
        verifier.verify_input(
            unknown_artifact_input,
            (make_result(unknown_artifact_input, evidence=(unknown_artifact,)),),
        )


def test_verifier_rechecks_input_digest_and_stale_visual_status(tmp_path: Path) -> None:
    verification_input, _, _ = input_with_artifact(tmp_path)
    object.__setattr__(verification_input, "task_id", "TASK-FORGED")
    with pytest.raises(verifier.Phase6VerificationError, match="input digest"):
        verifier.verify_input(verification_input, ())
    status, reason = verifier._visual_status(
        VerificationStatus.STALE,
        (),
        VerificationRole.REVIEWER,
    )
    assert status is VerificationStatus.STALE
    assert "cannot be refreshed" in reason


def test_stop_decision_validates_failure_routing_identity_and_types(tmp_path: Path) -> None:
    verification_input = make_input(tmp_path)
    converted = StopDecision("NO_PROGRESS", "no progress")
    assert converted.condition is StopCondition.NO_PROGRESS
    with pytest.raises(ValueError, match="stop condition"):
        StopDecision(123, "invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="stop reason"):
        StopDecision(None, "")
    with pytest.raises(ValueError, match="stop observations"):
        StopDecision(None, "invalid", observed_procedures=-1)
    with pytest.raises(ValueError, match="input_digest"):
        StopDecision(
            None,
            "invalid digest",
            run_id="RUN-1",
            task_id="TASK-1",
            input_digest="not-a-digest",
        )
    with pytest.raises(ValueError, match="stop decision run_id"):
        StopDecision(
            None,
            "invalid identity",
            run_id="..",
            task_id="TASK-1",
            input_digest=PACKAGE_DIGEST,
        )
    with pytest.raises(ValueError, match="verification input is invalid"):
        evaluate_stop(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="elapsed_seconds"):
        evaluate_stop(verification_input, (), elapsed_seconds=True)
    with pytest.raises(ValueError, match="elapsed_seconds"):
        evaluate_stop(verification_input, (), elapsed_seconds="slow")  # type: ignore[arg-type]
    filtered = evaluate_stop(
        verification_input,
        (),
        missing_tools=(None, "browser", "browser"),  # type: ignore[arg-type]
    )
    assert filtered.missing_tools == ("browser",)


def test_composition_rejects_forged_plan_handoff_and_run_digests(
    tmp_path: Path, monkeypatch
) -> None:
    plan = make_plan(
        procedures=(
            ProcedureSpec(
                "PROC-C-1",
                "C-1",
                "bounded procedure",
                check="FILE_DIGEST",
            ),
        )
    )
    with pytest.raises(Phase6CompositionError, match="plan digest"):
        replace(plan, digest=OTHER_DIGEST)

    task = make_task(tmp_path / "handoff")
    artifact = make_artifact(task)
    receipt_path = tmp_path / "handoff" / "fake-receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        composition,
        "read_confined_bytes",
        lambda path, root, *, max_bytes: (receipt_path.parent, b"{}"),
    )
    with pytest.raises(Phase6CompositionError, match="builder handoff exceeds"):
        composition._load_builder_handoff(
            receipt_path,
            root=tmp_path / "handoff",
            task=task,
            artifact=artifact,
        )

    verification_input = make_input(
        tmp_path / "run",
        artifacts=(make_artifact_ref(str(tmp_path / "run" / "workspace")),),
        verification_id=plan.verification_id,
        acceptance_criteria_ref=plan.criteria_digest,
        profile=plan.profile,
        claims=plan.claims,
        budgets=plan.budget,
    )
    run = composition.run_verification_plan(plan, verification_input)
    forged_input = run.verification_input
    object.__setattr__(forged_input, "acceptance_criteria_ref", OTHER_DIGEST)
    with pytest.raises(Phase6CompositionError, match="criteria digest"):
        Phase6VerificationRun(
            run.plan,
            forged_input,
            run.procedure_results,
            run.output,
            run.telemetry,
            run.elapsed_ms,
        )
    object.__setattr__(forged_input, "acceptance_criteria_ref", plan.criteria_digest)

    output = run.output
    object.__setattr__(output, "input_digest", OTHER_DIGEST)
    with pytest.raises(Phase6CompositionError, match="output is not bound"):
        Phase6VerificationRun(
            run.plan,
            run.verification_input,
            run.procedure_results,
            output,
            run.telemetry,
            run.elapsed_ms,
        )
    object.__setattr__(output, "input_digest", run.verification_input.digest)
    with pytest.raises(Phase6CompositionError, match="run digest"):
        replace(run, digest=OTHER_DIGEST)


def test_composition_rejects_unbounded_builder_handoff_and_unknown_host_capability(
    tmp_path: Path,
) -> None:
    snapshot = discover_vnext_package(PROJECT_ROOT)
    blocked_snapshot = replace(snapshot, record=None, package_digest=None, digest="")
    with pytest.raises(Phase6CompositionError, match="exactly discovered"):
        composition.prepare_vnext_host_preflight(
            object(),
            object(),
            snapshot=blocked_snapshot,
            policy_path=PROJECT_ROOT / "config" / "phase6-execution-policy.json",
            plan=object(),
            verification_input=object(),
        )


def test_host_snapshots_and_preflights_reject_forged_identity(tmp_path: Path) -> None:
    snapshot = discover_vnext_package(PROJECT_ROOT)
    assert replace(snapshot, digest=snapshot.digest).digest == snapshot.digest
    with pytest.raises(Phase6HostError, match="snapshot digest"):
        replace(snapshot, digest=OTHER_DIGEST)
    with pytest.raises(Phase6HostError, match="absolute"):
        prepare_vnext_preflight(
            "relative/project",
            task_id="TASK-P6",
            run_id="RUN-P6",
            task="bounded task",
            acceptance_criteria=("bounded",),
        )

    with pytest.raises(Phase6HostError, match="different project root"):
        prepare_vnext_preflight(
            tmp_path,
            snapshot=snapshot,
            task_id="TASK-P6",
            run_id="RUN-P6",
            task="bounded task",
            acceptance_criteria=("bounded",),
        )
    preflight = prepare_vnext_preflight(
        PROJECT_ROOT,
        snapshot=snapshot,
        task_id="TASK-P6-DIGEST",
        run_id="RUN-P6-DIGEST",
        task="bounded task",
        acceptance_criteria=("bounded",),
        policy_path=PROJECT_ROOT / "config" / "missing-phase6-policy.json",
    )
    assert replace(preflight, digest=preflight.digest).digest == preflight.digest
    with pytest.raises(Phase6HostError, match="preflight digest"):
        replace(preflight, digest=OTHER_DIGEST)


def test_host_discovery_keeps_exact_record_identity_when_unblocked(monkeypatch) -> None:
    snapshot = discover_vnext_package(
        PROJECT_ROOT,
        capability_id="backend-engineering-vnext",
    )
    assert snapshot.record is not None
    assert snapshot.package_digest == snapshot.record.content_hash

    blocked_record = replace(snapshot.record, status="BLOCKED")
    blocked_inventory = replace(
        snapshot.inventory,
        capabilities=(blocked_record,),
    )
    monkeypatch.setattr(
        host.CodexHostAdapter,
        "discover_capabilities",
        lambda self: blocked_inventory,
    )
    blocked = discover_vnext_package(
        PROJECT_ROOT,
        capability_id="backend-engineering-vnext",
    )
    assert "CAPABILITY_STATUS_BLOCKED" in blocked.blockers
    assert blocked.package_digest == blocked_record.content_hash


def test_telemetry_event_digest_is_not_forgeable(tmp_path: Path) -> None:
    verification_input = make_input(tmp_path)
    event = Phase6TelemetryEvent(
        event_id="P6-EVT-ASSURANCE",
        event_type=Phase6EventType.VERIFICATION_REPORT_CREATED,
        run_id=verification_input.run_id,
        task_id=verification_input.task_id,
        capability_id=verification_input.capability_id,
        observed=True,
    )
    with pytest.raises(Phase6TelemetryError, match="event digest"):
        replace(event, digest=OTHER_DIGEST)


def test_visual_evidence_kind_is_preserved_in_the_bound_model(tmp_path: Path) -> None:
    verification_input = make_input(tmp_path)
    evidence = make_evidence(
        evidence_id="EVID-RENDER",
        artifact_id=None,
        artifact_digest=None,
        kind=EvidenceKind.RENDER,
    )
    assert evidence.kind is EvidenceKind.RENDER
    assert verification_input.profile.value == "FOCUSED"
