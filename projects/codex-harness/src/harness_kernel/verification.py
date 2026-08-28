"""Deterministic verification procedures and artifact/evidence proof links."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from .errors import FailureCategory, FailureDetail
from .models import (
    ArtifactRecord,
    Claim,
    ClaimStatus,
    Confidence,
    Coverage,
    EvidenceEnvironment,
    EvidenceFreshness,
    EvidenceKind,
    EvidenceProcedure,
    EvidenceProvenance,
    EvidenceRecord,
    EvidenceResult,
    FreshnessStatus,
    Independence,
    PrivacyClass,
    ProcedureStatus,
    Provenance,
    Recommendation,
    RecordEnvelope,
    RecordStatus,
    SchemaVersion,
    SourceType,
    VerificationProcedure,
    VerificationReport,
    Verifier,
)
from .providers import ProviderExecutionResult, ProviderResultStatus, digest_output

DEFAULT_TIMESTAMP = "2026-08-28T13:30:00Z"


def _text(value: object) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def _envelope(
    record_status: RecordStatus, timestamp: str, evidence: tuple[str, ...]
) -> RecordEnvelope:
    return RecordEnvelope(
        status=record_status,
        provenance=Provenance(SourceType.GENERATED, ("phase-2-runtime",), timestamp),
        evidence_refs=evidence,
    )


def artifact_content_matches(artifact: ArtifactRecord, content: object) -> bool:
    """Recompute an artifact digest; metadata alone never proves content."""

    try:
        return artifact.content.digest == digest_output(content)
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    report: VerificationReport
    evidence: tuple[EvidenceRecord, ...]
    procedure: VerificationProcedure
    failure: FailureDetail | None = None

    @property
    def passed(self) -> bool:
        return _text(self.report.recommendation) == Recommendation.PASS.value


def aggregate_verification(
    outcomes: Sequence[VerificationOutcome],
    *,
    task_id: str,
    run_id: str,
    acceptance_refs: Iterable[str] = (),
    timestamp: str = DEFAULT_TIMESTAMP,
    report_id: str | None = None,
) -> VerificationOutcome:
    """Merge per-invocation packets without hiding failed or unknown claims."""

    if not outcomes:
        raise ValueError("at least one verification outcome is required")
    claims = tuple(claim for outcome in outcomes for claim in outcome.report.claims)
    procedures = tuple(procedure for outcome in outcomes for procedure in outcome.report.procedures)
    evidence = tuple(item for outcome in outcomes for item in outcome.evidence)
    artifact_refs = tuple(
        dict.fromkeys(
            artifact_ref for outcome in outcomes for artifact_ref in outcome.report.artifact_refs
        )
    )
    passed = tuple(
        dict.fromkeys(claim.claim_id for claim in claims if claim.status is ClaimStatus.PASS)
    )
    failed = tuple(
        dict.fromkeys(claim.claim_id for claim in claims if claim.status is ClaimStatus.FAIL)
    )
    not_run = tuple(
        dict.fromkeys(claim.claim_id for claim in claims if claim.status is ClaimStatus.NOT_RUN)
    )
    unknown = tuple(
        dict.fromkeys(claim.claim_id for claim in claims if claim.status is ClaimStatus.UNKNOWN)
    )
    blockers = tuple(
        dict.fromkeys(blocker for outcome in outcomes for blocker in outcome.report.blockers)
    )
    limitations = tuple(
        dict.fromkeys(
            limitation for outcome in outcomes for limitation in outcome.report.limitations
        )
    )
    required = sum(1 for claim in claims if claim.required)
    evidenced = sum(
        1
        for claim in claims
        if claim.required and claim.status is ClaimStatus.PASS and claim.evidence_refs
    )
    all_required_pass = (
        required > 0 and evidenced == required and not failed and not not_run and not unknown
    )
    if all_required_pass:
        recommendation = Recommendation.PASS
    elif not failed and (not_run or unknown):
        recommendation = Recommendation.BLOCK
    else:
        recommendation = Recommendation.FAIL
    report = VerificationReport(
        schema_version=SchemaVersion.VERIFICATION_REPORT,
        report_id=report_id or f"VER-{run_id}",
        task_id=task_id,
        run_id=run_id,
        record=_envelope(
            RecordStatus.CURRENT,
            timestamp,
            tuple(item.evidence_id for item in evidence),
        ),
        artifact_refs=artifact_refs,
        acceptance_refs=tuple(dict.fromkeys(acceptance_refs)),
        claims=claims,
        procedures=procedures,
        passed=passed,
        failed=failed,
        not_run=not_run,
        unknown=unknown,
        limitations=limitations,
        coverage=Coverage(
            required_claims=required,
            evidenced_claims=evidenced,
            percentage=(100.0 * evidenced / required) if required else 0.0,
        ),
        confidence=Confidence.HIGH if all_required_pass else Confidence.MEDIUM,
        blockers=blockers,
        recommendation=recommendation,
        verifier=Verifier("local.verifier", Independence.SEPARATED_SELF),
        created_at=timestamp,
    )
    failure = None
    if recommendation is not Recommendation.PASS:
        failure = FailureDetail(
            category=FailureCategory.VERIFICATION,
            code="AGGREGATED_VERIFICATION_FAILED",
            message="one or more required execution claims were not verified",
            refs=(report.report_id,),
        )
    procedure = VerificationProcedure(
        procedure_id=f"PROC-{report.report_id}",
        description="aggregate per-invocation verification packets",
        status=(
            ProcedureStatus.SKIPPED
            if not_run and not passed and not failed and not unknown
            else ProcedureStatus.EXECUTED
        ),
        result=(
            EvidenceResult.PASS
            if recommendation is Recommendation.PASS
            else EvidenceResult.NOT_RUN
            if not_run and not failed and not unknown
            else EvidenceResult.FAIL
        ),
        evidence_refs=tuple(item.evidence_id for item in evidence),
    )
    return VerificationOutcome(report, evidence, procedure, failure)


def verify_provider_result(
    invocation: object,
    provider_result: ProviderExecutionResult,
    artifact: ArtifactRecord | None,
    *,
    acceptance_refs: tuple[str, ...] = ("P2-EXECUTION",),
    timestamp: str = DEFAULT_TIMESTAMP,
    claim_id: str | None = None,
    verifier_id: str = "local.verifier",
) -> VerificationOutcome:
    """Verify a structured provider result with a fresh evidence record."""

    invocation_id = str(getattr(invocation, "invocation_id", "INV-UNKNOWN"))
    task_id = str(getattr(invocation, "task_id", "TASK-UNKNOWN"))
    run_id = str(getattr(invocation, "run_id", "RUN-UNKNOWN"))
    claim_key = claim_id or f"CLAIM-{invocation_id}"
    procedure_key = f"PROC-{invocation_id}"
    evidence_key = f"EVID-{invocation_id}"
    failure_code = provider_result.failure.code if provider_result.failure is not None else None
    not_executed = failure_code in {
        "NOT_EXECUTED",
        "DRY_RUN_NOT_EXECUTED",
        "STOP_BEFORE_RUN",
        "GRAPH_NODE_NOT_EXECUTED",
        "DEPENDENCY_FAILED",
        "GRAPH_INVOCATION_BUDGET",
        "INVOCATION_BUDGET_EXHAUSTED",
        "CANCELLED_BEFORE_PROVIDER",
        "TIMEOUT_BEFORE_PROVIDER",
    }
    passed = (
        provider_result.status is ProviderResultStatus.SUCCEEDED
        and artifact is not None
        and provider_result.output is not None
        and artifact_content_matches(artifact, provider_result.output)
    )
    result = (
        EvidenceResult.PASS
        if passed
        else EvidenceResult.NOT_RUN
        if not_executed
        else EvidenceResult.FAIL
    )
    procedure = VerificationProcedure(
        procedure_id=procedure_key,
        description="verify provider result contract and artifact digest",
        status=ProcedureStatus.SKIPPED if not_executed else ProcedureStatus.EXECUTED,
        result=result,
        evidence_refs=(evidence_key,),
    )
    observation = (
        "provider output contract and artifact digest matched"
        if passed
        else "provider execution did not run, so the output contract could not be verified"
        if not_executed
        else "provider output did not satisfy the artifact or execution contract"
    )
    evidence = EvidenceRecord(
        schema_version=SchemaVersion.EVIDENCE_RECORD,
        evidence_id=evidence_key,
        task_id=task_id,
        run_id=run_id,
        record=_envelope(RecordStatus.CURRENT, timestamp, (evidence_key,)),
        claim_ref=claim_key,
        evidence_kind=EvidenceKind.OBSERVATION,
        procedure=EvidenceProcedure(
            procedure_id=procedure_key,
            description=procedure.description,
            command_or_method="deterministic provider contract verifier",
            executed=not not_executed,
        ),
        result=result,
        observation=observation,
        artifact_refs=(artifact.artifact_id,) if artifact is not None else (),
        environment=EvidenceEnvironment(
            host="project-local", version="phase-2", fixture="provider", tool=verifier_id
        ),
        observed_at=timestamp,
        freshness=EvidenceFreshness(FreshnessStatus.FRESH, ()),
        provenance=EvidenceProvenance(
            source_type=SourceType.PROVIDER,
            source_ref=provider_result.provider_id,
            content_digest=provider_result.output_digest,
        ),
        limitations=(),
        confidence=Confidence.HIGH if passed else Confidence.MEDIUM,
        privacy_class=PrivacyClass.INTERNAL,
        owner=verifier_id,
    )
    claim = Claim(
        claim_id=claim_key,
        text="the selected provider produced an output satisfying the declared contract",
        required=True,
        status=(
            ClaimStatus.PASS
            if passed
            else ClaimStatus.NOT_RUN
            if not_executed
            else ClaimStatus.FAIL
        ),
        evidence_refs=(evidence_key,),
        limitation_refs=(
            ()
            if passed
            else ("provider execution was not run",)
            if not_executed
            else ("provider result failed contract verification",)
        ),
    )
    report = VerificationReport(
        schema_version=SchemaVersion.VERIFICATION_REPORT,
        report_id=f"VER-{invocation_id}",
        task_id=task_id,
        run_id=run_id,
        record=_envelope(RecordStatus.CURRENT, timestamp, (evidence_key,)),
        artifact_refs=(artifact.artifact_id,) if artifact is not None else (),
        acceptance_refs=tuple(acceptance_refs),
        claims=(claim,),
        procedures=(procedure,),
        passed=(claim_key,) if passed else (),
        failed=() if passed or not_executed else (claim_key,),
        not_run=(claim_key,) if not_executed else (),
        unknown=(),
        limitations=(
            ()
            if passed
            else ("provider execution was not run",)
            if not_executed
            else ("provider output was not accepted as verified",)
        ),
        coverage=Coverage(1, 1 if passed else 0, 100.0 if passed else 0.0),
        confidence=Confidence.HIGH if passed else Confidence.MEDIUM,
        blockers=(
            ()
            if passed
            else ("provider-result-not-run",)
            if not_executed
            else ("provider-result-contract",)
        ),
        recommendation=(
            Recommendation.PASS
            if passed
            else Recommendation.BLOCK
            if not_executed
            else Recommendation.FAIL
        ),
        verifier=Verifier(verifier_id, Independence.SEPARATED_SELF),
        created_at=timestamp,
    )
    failure = None
    if not passed:
        failure = FailureDetail(
            category=FailureCategory.VERIFICATION,
            code="VERIFICATION_NOT_RUN" if not_executed else "VERIFICATION_FAILED",
            message=(
                "provider output could not be verified because execution did not run"
                if not_executed
                else "provider output failed deterministic verification"
            ),
            refs=(report.report_id, evidence_key),
        )
    return VerificationOutcome(report, (evidence,), procedure, failure)


def verification_packet_digest(report: VerificationReport) -> str:
    """Produce a stable blind-packet digest from report identity and claims."""

    material = "|".join(
        (
            report.report_id,
            report.task_id,
            report.run_id,
            *report.acceptance_refs,
            *report.passed,
            *report.failed,
            *report.not_run,
            *report.unknown,
        )
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(material).hexdigest()}"


def stale_verification(outcome: VerificationOutcome) -> VerificationOutcome:
    """Return a non-promotable copy when verification evidence becomes stale."""

    from .evidence import mark_evidence_stale

    evidence = tuple(
        mark_evidence_stale(item, "verification input changed") for item in outcome.evidence
    )
    report = replace(
        outcome.report,
        record=replace(outcome.report.record, status=RecordStatus.STALE),
        passed=(),
        failed=tuple(dict.fromkeys((*outcome.report.failed, *outcome.report.passed))),
        limitations=tuple(
            dict.fromkeys((*outcome.report.limitations, "verification evidence is stale"))
        ),
        coverage=replace(outcome.report.coverage, evidenced_claims=0, percentage=0.0),
        confidence=Confidence.LOW,
        blockers=tuple(dict.fromkeys((*outcome.report.blockers, "stale-evidence"))),
        recommendation=Recommendation.FAIL,
    )
    failure = FailureDetail(
        category=FailureCategory.VERIFICATION,
        code="STALE_EVIDENCE",
        message="verification evidence is stale and cannot support delivery",
        refs=(report.report_id,),
    )
    return VerificationOutcome(report, evidence, outcome.procedure, failure)
