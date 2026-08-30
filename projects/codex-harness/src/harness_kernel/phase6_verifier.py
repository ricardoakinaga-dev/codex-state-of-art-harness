"""Criterion-level pure verifier for Phase 6 input and procedure receipts."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace

from .phase6_checks import Phase6CheckError, read_confined_bytes
from .phase6_models import (
    Claim,
    CriterionResult,
    Evidence,
    EvidenceRef,
    FreshnessStatus,
    ProcedureResult,
    ProcedureSpec,
    VerificationConfidence,
    VerificationInput,
    VerificationOutput,
    VerificationProfile,
    VerificationRole,
    VerificationStatus,
    canonical_json,
    evidence_content_digest,
    timestamp_is_current,
    verification_input_content_digest,
)
from .phase6_policy import (
    Phase6PolicyError,
    validate_input_policy,
    validate_procedure_policy,
    validate_reviewer,
)
from .phase6_stop import evaluate_stop


class Phase6VerificationError(ValueError):
    """Raised when a verifier receipt cannot be bound to its input."""


_QUALITATIVE_WORDS = frozenset(
    {
        "visual",
        "aesthetic",
        "taste",
        "composition",
        "typography",
        "color",
        "colour",
        "polish",
        "design",
    }
)


def _qualitative(profile: VerificationProfile, criterion_id: str) -> bool:
    return profile is VerificationProfile.VISUAL and any(
        word in criterion_id.casefold() for word in _QUALITATIVE_WORDS
    )


def _claim(verification_input: VerificationInput, criterion_id: str) -> Claim:
    declared = next(
        (item for item in verification_input.claims if item.criterion_id == criterion_id),
        None,
    )
    if declared is not None:
        if (
            verification_input.profile is VerificationProfile.VISUAL
            and _qualitative(verification_input.profile, criterion_id)
            and not declared.qualitative
        ):
            return Claim(
                criterion_id=declared.criterion_id,
                text=declared.text,
                required=declared.required,
                qualitative=True,
            )
        return declared
    return Claim(
        criterion_id=criterion_id,
        text=criterion_id,
        qualitative=_qualitative(verification_input.profile, criterion_id),
    )


def _not_run_procedure(criterion_id: str) -> ProcedureSpec:
    return ProcedureSpec(
        procedure_id=f"NOT-RUN-{criterion_id}",
        criterion_id=criterion_id,
        description="no deterministic procedure result was supplied",
    )


def _evidence_map(results: Iterable[ProcedureResult]) -> dict[str, Evidence]:
    evidence: dict[str, Evidence] = {}
    for result in results:
        for item in result.evidence:
            if item.evidence_id in evidence and evidence[item.evidence_id] != item:
                raise Phase6VerificationError("evidence IDs must not diverge within one run")
            evidence[item.evidence_id] = item
    return evidence


def _input_evidence_map(verification_input: VerificationInput) -> Mapping[str, EvidenceRef]:
    return {item.evidence_id: item for item in verification_input.evidence_refs}


def _validate_evidence(verification_input: VerificationInput, evidence: Sequence[Evidence]) -> None:
    artifacts = {item.artifact_id: item for item in verification_input.artifact_refs}
    declared_evidence = _input_evidence_map(verification_input)
    for item in evidence:
        if (
            item.run_id != verification_input.run_id
            or item.task_id != verification_input.task_id
            or item.input_digest != verification_input.digest
        ):
            raise Phase6VerificationError("evidence receipt is not bound to this input")
        if declared_evidence and item.evidence_id not in declared_evidence:
            raise Phase6VerificationError("procedure evidence is not declared by the input")
        declared = declared_evidence.get(item.evidence_id)
        if item.digest != evidence_content_digest(item):
            raise Phase6VerificationError("evidence digest does not match its content")
        if declared is not None and item.digest != declared.digest:
            raise Phase6VerificationError("evidence digest does not match the input")
        if (
            item.package_digest is not None
            and item.package_digest != verification_input.package_digest
        ):
            raise Phase6VerificationError("evidence package digest does not match the input")
        for artifact_id in item.artifact_refs:
            artifact = artifacts.get(artifact_id)
            if artifact is None:
                raise Phase6VerificationError("evidence artifact is not declared by the input")
            if item.artifact_digest is not None and item.artifact_digest != artifact.digest:
                raise Phase6VerificationError("evidence artifact digest does not match the input")
        if item.path is not None:
            if not item.artifact_refs:
                raise Phase6VerificationError("path-bound evidence must name an artifact")
            referenced_artifacts = tuple(artifacts[item_id] for item_id in item.artifact_refs)
            matching_artifacts = tuple(
                artifact for artifact in referenced_artifacts if artifact.path == item.path
            )
            if not matching_artifacts:
                raise Phase6VerificationError("evidence path is not bound to its artifact")
            try:
                _, content = read_confined_bytes(
                    item.path,
                    verification_input.workspace,
                    max_bytes=verification_input.budgets.max_report_bytes,
                )
            except Phase6CheckError as exc:
                raise Phase6VerificationError("evidence path cannot be revalidated") from exc
            actual_digest = "sha256:" + hashlib.sha256(content).hexdigest()
            if any(actual_digest != artifact.digest for artifact in matching_artifacts):
                raise Phase6VerificationError("evidence path content does not match its artifact")


def _reviewer_for(
    verification_input: VerificationInput,
    evidence: Sequence[Evidence],
    reviewer_id: str | None,
    reviewer_role: VerificationRole | str | None,
) -> tuple[str | None, VerificationRole | None]:
    evidence_reviewer_ids = {item.reviewer_id for item in evidence if item.reviewer_id is not None}
    evidence_reviewer_roles = {
        item.reviewer_role for item in evidence if item.reviewer_role is not None
    }
    selected_id = reviewer_id or (
        next(iter(evidence_reviewer_ids)) if len(evidence_reviewer_ids) == 1 else None
    )
    selected_role = reviewer_role or (
        next(iter(evidence_reviewer_roles)) if len(evidence_reviewer_roles) == 1 else None
    )
    if selected_id is None and selected_role is None:
        return None, None
    if selected_id is None or selected_role is None:
        raise Phase6VerificationError("reviewer identity and role must both be supplied")
    try:
        validated_id, validated_role = validate_reviewer(
            verifier=verification_input,
            reviewer_id=selected_id,
            reviewer_role=selected_role,
        )
    except Phase6PolicyError as exc:
        raise Phase6VerificationError(str(exc)) from exc
    return validated_id, VerificationRole(validated_role)


def _visual_status(
    status: VerificationStatus,
    evidence: Sequence[Evidence],
    reviewer_role: VerificationRole | None,
) -> tuple[VerificationStatus, str]:
    if status is VerificationStatus.STALE:
        return status, "stale visual evidence cannot be refreshed by this run"
    current_render = any(
        item.kind.value == "RENDER" and item.freshness is FreshnessStatus.FRESH for item in evidence
    )
    separate_reviewer = reviewer_role is VerificationRole.REVIEWER and any(
        item.reviewer_role is VerificationRole.REVIEWER and item.reviewer_id for item in evidence
    )
    if current_render and separate_reviewer:
        return status, ""
    return (
        VerificationStatus.BLOCKED,
        "qualitative visual judgment needs current render evidence and a separate reviewer",
    )


def _result_for(
    verification_input: VerificationInput,
    criterion_id: str,
    procedure_result: ProcedureResult | None,
    *,
    reviewer_role: VerificationRole | None,
) -> CriterionResult:
    claim = _claim(verification_input, criterion_id)
    if procedure_result is None:
        return CriterionResult(
            criterion_id=criterion_id,
            claim=claim,
            procedure=_not_run_procedure(criterion_id),
            status=VerificationStatus.NOT_RUN,
            reason="no procedure result was supplied",
        )
    if procedure_result.spec is None:
        raise Phase6VerificationError("procedure result is missing its spec")
    declared_evidence_ids = {item.evidence_id for item in verification_input.evidence_refs}
    evidence = tuple(
        item for item in procedure_result.evidence if item.evidence_id in declared_evidence_ids
    )
    effective_result = procedure_result
    if evidence != procedure_result.evidence:
        effective_result = replace(procedure_result, evidence=evidence, evidence_refs=(), digest="")
    status = procedure_result.status
    reason = procedure_result.error or procedure_result.observation
    if verification_input.freshness is FreshnessStatus.STALE:
        status = VerificationStatus.STALE
        reason = "verification input is stale"
    elif verification_input.freshness is FreshnessStatus.UNKNOWN:
        status = VerificationStatus.UNKNOWN
        reason = "verification input freshness is unknown"
    elif status is VerificationStatus.PASS:
        declared_map = {item.evidence_id: item for item in verification_input.evidence_refs}
        if not timestamp_is_current(procedure_result.observed_at, verification_input.observed_at):
            status = VerificationStatus.STALE
            reason = "PASS procedure receipt is stale"
        elif any(
            item.freshness is not FreshnessStatus.FRESH
            or not timestamp_is_current(item.observed_at, verification_input.observed_at)
            or declared_map[item.evidence_id].freshness is not FreshnessStatus.FRESH
            or not timestamp_is_current(
                declared_map[item.evidence_id].observed_at,
                verification_input.observed_at,
            )
            for item in evidence
        ):
            status = VerificationStatus.STALE
            reason = "PASS evidence is stale"
        elif not procedure_result.executed or not evidence:
            status = VerificationStatus.BLOCKED
            reason = "PASS requires an executed procedure and current evidence"
    if verification_input.profile is VerificationProfile.VISUAL and claim.qualitative:
        status, visual_reason = _visual_status(status, evidence, reviewer_role)
        if visual_reason:
            reason = visual_reason
    return CriterionResult(
        criterion_id=criterion_id,
        claim=claim,
        procedure=procedure_result.spec,
        procedure_result=effective_result,
        evidence=evidence,
        status=status,
        reason=reason,
        limitations=(reason,) if status is VerificationStatus.PARTIAL and reason else (),
        confidence=VerificationConfidence.HIGH
        if status is VerificationStatus.PASS
        else VerificationConfidence.MEDIUM,
    )


def _confidence(results: Sequence[CriterionResult]) -> VerificationConfidence:
    if not results:
        return VerificationConfidence.UNKNOWN
    statuses = {item.status for item in results}
    if statuses == {VerificationStatus.PASS}:
        return VerificationConfidence.HIGH
    if VerificationStatus.UNKNOWN in statuses or VerificationStatus.NOT_RUN in statuses:
        return VerificationConfidence.LOW
    return VerificationConfidence.MEDIUM


def _budget_blocked_output(
    verification_input: VerificationInput, reason: str
) -> VerificationOutput:
    results = tuple(
        _result_for(
            verification_input,
            criterion_id,
            None,
            reviewer_role=None,
        )
        for criterion_id in verification_input.required_criteria
    )
    return VerificationOutput.from_input(
        verification_input,
        results,
        stop_reason="BUDGET_EXHAUSTED",
        confidence=VerificationConfidence.LOW,
        blockers=(reason,),
    )


def _is_budget_policy_error(error: Phase6PolicyError) -> bool:
    return "budget" in str(error).casefold() or "exceed" in str(error).casefold()


def verify_input(
    verification_input: VerificationInput,
    procedure_results: Sequence[ProcedureResult] = (),
    *,
    reviewer_id: str | None = None,
    reviewer_role: VerificationRole | str | None = None,
    missing_tools: Iterable[str] = (),
    missing_artifacts: Iterable[str] = (),
    human_override: bool | str = False,
    no_progress: bool = False,
    repeated_procedure_failure: bool = False,
    elapsed_seconds: float | int | None = None,
) -> VerificationOutput:
    """Verify supplied procedure receipts without executing external actions."""

    if verification_input.digest != verification_input_content_digest(verification_input):
        raise Phase6VerificationError("verification input digest does not match its content")
    try:
        validate_input_policy(verification_input)
    except Phase6PolicyError as exc:
        if _is_budget_policy_error(exc):
            return _budget_blocked_output(verification_input, str(exc))
        raise Phase6VerificationError(str(exc)) from exc
    supplied = tuple(procedure_results)
    if len(supplied) > verification_input.budgets.max_procedures:
        return _budget_blocked_output(
            verification_input, "procedure results exceed the verification budget"
        )
    by_criterion: dict[str, ProcedureResult] = {}
    aggregate_evidence = 0
    aggregate_bytes = 0
    for result in supplied:
        if not isinstance(result, ProcedureResult):
            raise Phase6VerificationError("procedure results contain an invalid record")
        aggregate_evidence += len(result.evidence)
        aggregate_bytes += len(canonical_json(result).encode("utf-8"))
        if aggregate_evidence > verification_input.budgets.max_evidence_records:
            return _budget_blocked_output(
                verification_input, "procedure evidence exceeds the verification budget"
            )
        if aggregate_bytes > verification_input.budgets.max_report_bytes:
            return _budget_blocked_output(
                verification_input, "procedure receipts exceed the report byte budget"
            )
        if result.criterion_id in by_criterion:
            raise Phase6VerificationError("duplicate procedure result for a criterion")
        try:
            if result.spec is None:
                raise Phase6VerificationError("procedure result is missing its spec")
            if (
                result.run_id != verification_input.run_id
                or result.task_id != verification_input.task_id
                or result.input_digest != verification_input.digest
                or result.verifier_id != verification_input.capability_id
            ):
                raise Phase6VerificationError("procedure receipt is not bound to this input")
            validate_procedure_policy(result.spec, verification_input)
        except Phase6PolicyError as exc:
            raise Phase6VerificationError(str(exc)) from exc
        if result.attempts > verification_input.budgets.max_attempts_per_procedure:
            return _budget_blocked_output(
                verification_input, "procedure attempts exceed the verification budget"
            )
        _validate_evidence(verification_input, result.evidence)
        by_criterion[result.criterion_id] = result
    all_evidence = tuple(item for result in supplied for item in result.evidence)
    selected_reviewer_id, selected_reviewer_role = _reviewer_for(
        verification_input, all_evidence, reviewer_id, reviewer_role
    )
    results = tuple(
        _result_for(
            verification_input,
            criterion_id,
            by_criterion.get(criterion_id),
            reviewer_role=selected_reviewer_role,
        )
        for criterion_id in verification_input.required_criteria
    )
    decision = evaluate_stop(
        verification_input,
        results,
        missing_tools=missing_tools,
        missing_artifacts=missing_artifacts,
        stale_input=verification_input.freshness is not FreshnessStatus.FRESH,
        human_override=human_override,
        no_progress=no_progress,
        repeated_procedure_failure=repeated_procedure_failure,
        elapsed_seconds=elapsed_seconds,
    )
    return VerificationOutput.from_input(
        verification_input,
        results,
        stop_reason=decision.condition,
        confidence=_confidence(results),
        blockers=tuple(decision.missing_tools) + tuple(decision.missing_artifacts),
        reviewer_id=selected_reviewer_id,
        reviewer_role=selected_reviewer_role,
    )


def verify(
    verification_input: VerificationInput,
    procedure_results: Sequence[ProcedureResult] = (),
    **kwargs: object,
) -> VerificationOutput:
    return verify_input(verification_input, procedure_results, **kwargs)  # type: ignore[arg-type]


run_verification = verify_input
build_verification_output = verify_input
