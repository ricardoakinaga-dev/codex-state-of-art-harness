from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from harness_kernel.phase6_models import (
    ArtifactRef,
    Claim,
    Evidence,
    EvidenceRef,
    FreshnessStatus,
    ProcedureResult,
    ProcedureSpec,
    ReadOnlyPolicy,
    VerificationBudget,
    VerificationInput,
    VerificationProfile,
    VerificationRole,
    VerificationStatus,
    timestamp_is_current,
)

PACKAGE_DIGEST = "sha256:" + "1" * 64
MANIFEST_DIGEST = "sha256:" + "2" * 64
ARTIFACT_DIGEST = "sha256:" + "3" * 64
EVIDENCE_DIGEST = "sha256:" + "4" * 64


def make_input(tmp_path, *, criteria=("C-1", "C-2"), profile=VerificationProfile.FOCUSED):
    workspace = tmp_path / "workspace"
    artifacts = workspace / "artifacts"
    evidence = workspace / "evidence"
    artifacts.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(exist_ok=True)
    observed_at = "2026-08-29T12:00:00Z"
    evidence_refs = []
    for index, criterion_id in enumerate(criteria, start=1):
        evidence_id = f"EVID-{index}"
        template = Evidence(
            evidence_id=evidence_id,
            criterion_id=criterion_id,
            artifact_refs=("ART-1",),
            artifact_digest=ARTIFACT_DIGEST,
            package_digest=PACKAGE_DIGEST,
            observed_at=observed_at,
        )
        evidence_refs.append(
            EvidenceRef(
                evidence_id=evidence_id,
                path=str(evidence / f"{evidence_id}.json"),
                digest=template.digest,
                artifact_id="ART-1",
                artifact_digest=ARTIFACT_DIGEST,
                package_digest=PACKAGE_DIGEST,
                observed_at=observed_at,
            )
        )
    return VerificationInput(
        run_id="RUN-P6-001",
        task_id="TASK-P6-001",
        capability_id="verification-loop-vnext",
        package_digest=PACKAGE_DIGEST,
        manifest_digest=MANIFEST_DIGEST,
        workspace=str(workspace),
        artifact_refs=(
            ArtifactRef(
                artifact_id="ART-1",
                path=str(artifacts / "index.html"),
                digest=ARTIFACT_DIGEST,
                package_digest=PACKAGE_DIGEST,
            ),
        ),
        evidence_refs=tuple(evidence_refs),
        required_criteria=criteria,
        profile=profile,
        observed_at=observed_at,
    )


def test_phase6_enums_and_budget_are_explicit_and_bounded() -> None:
    assert VerificationStatus.PASS.value == "PASS"
    assert VerificationProfile.SECURITY_AWARE.value == "SECURITY_AWARE"
    assert VerificationRole.VERIFIER.value == "VERIFIER"
    assert ReadOnlyPolicy.READ_ONLY.value == "READ_ONLY"
    budget = VerificationBudget()
    assert budget.max_procedures == 32
    assert budget.max_duration_seconds == 120
    with pytest.raises(ValueError):
        VerificationBudget(max_procedures=33)
    with pytest.raises(ValueError):
        VerificationBudget(max_attempts_per_procedure=2)
    with pytest.raises(FrozenInstanceError):
        budget.max_procedures = 1  # type: ignore[misc]


def test_verification_input_freezes_nested_values_and_digest(tmp_path) -> None:
    parameters = {"expected": ["one", {"nested": True}]}
    spec = ProcedureSpec(
        procedure_id="PROC-1",
        criterion_id="C-1",
        description="inspect a deterministic fixture",
        parameters=parameters,
    )
    parameters["expected"].append("caller mutation")
    assert spec.parameters["expected"] == ("one", {"nested": True})
    assert spec.digest.startswith("sha256:")

    criteria = ["C-1", "C-2"]
    verification_input = make_input(tmp_path, criteria=criteria)
    criteria.append("C-3")
    assert verification_input.required_criteria == ("C-1", "C-2")
    assert verification_input.role is VerificationRole.VERIFIER
    assert verification_input.allowed_tools == ()
    assert verification_input.read_only_policy is ReadOnlyPolicy.READ_ONLY
    assert verification_input.digest.startswith("sha256:")
    with pytest.raises(FrozenInstanceError):
        verification_input.task_id = "TASK-OTHER"  # type: ignore[misc]


def test_procedure_parameters_are_depth_and_byte_bounded() -> None:
    with pytest.raises(ValueError):
        ProcedureSpec(
            procedure_id="PROC-LARGE",
            criterion_id="C-1",
            description="bounded parameters",
            parameters={"payload": "x" * (16 * 1024)},
        )

    nested: object = "leaf"
    for _ in range(18):
        nested = [nested]
    with pytest.raises(ValueError):
        ProcedureSpec(
            procedure_id="PROC-DEEP",
            criterion_id="C-1",
            description="bounded nesting",
            parameters={"nested": nested},
        )


def test_refs_are_confined_to_workspace_and_identity_is_strict(tmp_path) -> None:
    verification_input = make_input(tmp_path)
    assert verification_input.artifact_refs[0].path.endswith("/artifacts/index.html")
    with pytest.raises(ValueError):
        make_input(tmp_path, criteria=("../escape",))
    with pytest.raises(ValueError):
        VerificationInput(
            run_id="RUN\x00BAD",
            task_id="TASK-1",
            capability_id="verification-loop-vnext",
            package_digest=PACKAGE_DIGEST,
            manifest_digest=MANIFEST_DIGEST,
            workspace=verification_input.workspace,
            required_criteria=("C-1",),
        )
    with pytest.raises(ValueError):
        VerificationInput(
            run_id="RUN-1",
            task_id="TASK-1",
            capability_id="verification-loop-vnext",
            package_digest=PACKAGE_DIGEST,
            manifest_digest=MANIFEST_DIGEST,
            workspace=verification_input.workspace,
            artifact_refs=(
                ArtifactRef(
                    artifact_id="ART-1",
                    path=str(tmp_path / "outside.txt"),
                    digest=ARTIFACT_DIGEST,
                ),
            ),
            required_criteria=("C-1",),
        )
    with pytest.raises(ValueError):
        VerificationInput(
            run_id="RUN-1",
            task_id="TASK-1",
            capability_id="verification-loop-vnext",
            package_digest="not-a-digest",
            manifest_digest=MANIFEST_DIGEST,
            workspace=verification_input.workspace,
            required_criteria=("C-1",),
        )


def test_pass_lineage_requires_execution_and_current_evidence(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    claim = Claim(criterion_id="C-1", text="the artifact is structurally valid")
    spec = ProcedureSpec(
        procedure_id="PROC-1",
        criterion_id="C-1",
        description="run the structural check",
    )
    stale_evidence = Evidence(
        evidence_id="EVID-1",
        criterion_id="C-1",
        digest="",
        artifact_refs=("ART-1",),
        package_digest=PACKAGE_DIGEST,
        freshness=FreshnessStatus.STALE,
        observed_at=verification_input.observed_at,
    )
    result = ProcedureResult(
        spec=spec,
        status=VerificationStatus.PASS,
        executed=False,
        evidence=(stale_evidence,),
    )
    with pytest.raises(ValueError):
        result.as_criterion_result(claim, status=VerificationStatus.PASS)


def test_mixed_timestamp_formats_fail_closed() -> None:
    assert timestamp_is_current(10, 9) is True
    assert timestamp_is_current("2026-08-29T12:00:00Z", "2026-08-29T11:00:00Z") is True
    assert timestamp_is_current("2026-08-29T13:00:00+01:00", "2026-08-29T12:00:00Z") is True
    assert timestamp_is_current(10, "2026-08-29T11:00:00Z") is False
    assert timestamp_is_current("not-a-timestamp", "2026-08-29T11:00:00Z") is False


def test_timestamp_contract_requires_timezone_aware_iso8601_values(tmp_path) -> None:
    with pytest.raises(ValueError):
        VerificationInput(
            run_id="RUN-1",
            task_id="TASK-1",
            capability_id="verification-loop-vnext",
            package_digest=PACKAGE_DIGEST,
            manifest_digest=MANIFEST_DIGEST,
            workspace=str(tmp_path / "workspace"),
            required_criteria=("C-1",),
            observed_at="2026-08-29T12:00:00",
        )


def test_verification_input_enforces_evidence_reference_budget(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    refs = tuple(EvidenceRef(evidence_id=f"EVID-{index}") for index in range(257))
    with pytest.raises(ValueError, match="evidence_refs exceed the budget"):
        VerificationInput(
            run_id=verification_input.run_id,
            task_id=verification_input.task_id,
            capability_id=verification_input.capability_id,
            package_digest=PACKAGE_DIGEST,
            manifest_digest=MANIFEST_DIGEST,
            workspace=verification_input.workspace,
            required_criteria=("C-1",),
            evidence_refs=refs,
        )


def test_evidence_bindings_require_complete_identity_pairs(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    with pytest.raises(ValueError):
        EvidenceRef(
            evidence_id="EVID-INCOMPLETE",
            path=verification_input.evidence_refs[0].path,
            run_id=verification_input.run_id,
        )
    with pytest.raises(ValueError):
        Evidence(
            evidence_id="EVID-REVIEWER",
            criterion_id="C-1",
            digest=EVIDENCE_DIGEST,
            reviewer_role=VerificationRole.REVIEWER,
        )
