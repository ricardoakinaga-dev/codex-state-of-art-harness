"""Critique and assurance boundaries over verification evidence."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from .evidence import validate_evidence_links
from .models import (
    ArtifactRecord,
    ClaimStatus,
    Confidence,
    CritiqueFinding,
    CritiqueReport,
    EvidenceRecord,
    FindingCategory,
    FindingConfidence,
    FindingDisposition,
    FindingSeverity,
    GateStatus,
    Independence,
    Provenance,
    QualityBand,
    QualityDecision,
    QualityDimension,
    QualityDimensionName,
    QualityGate,
    QualityReport,
    Recommendation,
    RecordEnvelope,
    RecordStatus,
    SchemaVersion,
    SourceType,
    StopRecommendation,
    VerificationReport,
    Verifier,
)
from .verification import verification_packet_digest


class AssuranceDecision(StrEnum):
    QUALITY_ACCEPTED = "QUALITY_ACCEPTED"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANDIDATE = "CANDIDATE"


@dataclass(frozen=True, slots=True)
class AssuranceResult:
    decision: AssuranceDecision
    quality_band: QualityBand
    reason: str
    quality_report: QualityReport | None = None


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _envelope(report: VerificationReport, timestamp: str) -> RecordEnvelope:
    return RecordEnvelope(
        status=RecordStatus.CURRENT,
        provenance=Provenance(SourceType.GENERATED, (report.report_id,), timestamp),
        evidence_refs=report.record.evidence_refs,
    )


def create_critique(
    verification: VerificationReport,
    *,
    quality_bar_ref: str = "P2-QB-1",
    reviewer_id: str = "local.critic",
    independence: Independence = Independence.SEPARATED_SELF,
    timestamp: str | None = None,
    evidence: Iterable[EvidenceRecord] = (),
    artifacts: Iterable[ArtifactRecord] = (),
) -> CritiqueReport:
    """Create a deterministic critique packet from verification claims."""

    created_at = timestamp or verification.created_at
    findings: list[CritiqueFinding] = []
    if _value(verification.recommendation) != Recommendation.PASS.value:
        findings.append(
            CritiqueFinding(
                finding_id=f"FIND-{verification.report_id}",
                severity=FindingSeverity.HIGH,
                category=FindingCategory.CORRECTNESS,
                statement="verification report contains a non-passing required claim",
                evidence_refs=verification.record.evidence_refs,
                affected_refs=(verification.report_id,),
                confidence=FindingConfidence.HIGH,
                disposition=FindingDisposition.OPEN,
                owner="assurance",
            )
        )
    evidence_values = tuple(evidence)
    artifact_values = tuple(artifacts)
    reviewer = Verifier(
        reviewer_id,
        independence,
        verification_packet_digest(
            verification,
            evidence=evidence_values,
            artifacts=artifact_values,
        ),
    )
    return CritiqueReport(
        schema_version=SchemaVersion.CRITIQUE_REPORT,
        report_id=f"CRIT-{verification.report_id}",
        task_id=verification.task_id,
        run_id=verification.run_id,
        record=_envelope(verification, created_at),
        reviewed_artifacts=verification.artifact_refs,
        reviewed_reports=(verification.report_id,),
        quality_bar_ref=quality_bar_ref,
        independence=independence,
        findings=tuple(findings),
        strengths=("verification claims were inspected against the declared acceptance refs",)
        if not findings
        else (),
        missing_evidence=tuple(verification.not_run) + tuple(verification.unknown),
        stop_recommendation=(
            StopRecommendation.CONTINUE if not findings else StopRecommendation.REPAIR
        ),
        residual_risk="LOW" if not findings else "HIGH",
        limitations=(),
        reviewer=reviewer,
        created_at=created_at,
    )


def assure_quality(
    verification: object,
    critique: object,
    *,
    quality_bar_ref: str = "P2-QB-1",
    require_independent: bool = False,
    evidence: Iterable[EvidenceRecord] | None = None,
    artifacts: Iterable[ArtifactRecord] | None = None,
) -> AssuranceResult:
    """Decide quality from verification and critique, never execution status alone."""

    if not isinstance(verification, VerificationReport) or not isinstance(critique, CritiqueReport):
        return AssuranceResult(
            AssuranceDecision.FAILED,
            QualityBand.FAILED,
            "assurance requires typed verification and critique reports",
        )
    if _value(verification.record.status) != RecordStatus.CURRENT.value:
        return AssuranceResult(
            AssuranceDecision.FAILED,
            QualityBand.FAILED,
            "verification report is stale or otherwise non-current",
        )
    if _value(critique.record.status) != RecordStatus.CURRENT.value:
        return AssuranceResult(
            AssuranceDecision.FAILED,
            QualityBand.FAILED,
            "critique report is stale or otherwise non-current",
        )
    if (critique.task_id, critique.run_id) != (verification.task_id, verification.run_id):
        return AssuranceResult(
            AssuranceDecision.FAILED,
            QualityBand.FAILED,
            "critique correlation does not match the verification packet",
        )
    if verification.report_id not in critique.reviewed_reports:
        return AssuranceResult(
            AssuranceDecision.FAILED,
            QualityBand.FAILED,
            "critique did not review the current verification report",
        )
    if set(critique.reviewed_artifacts) != set(verification.artifact_refs):
        return AssuranceResult(
            AssuranceDecision.FAILED,
            QualityBand.FAILED,
            "critique artifact scope does not match the verification packet",
        )
    if critique.reviewer.independence != critique.independence:
        return AssuranceResult(
            AssuranceDecision.FAILED,
            QualityBand.FAILED,
            "critique reviewer metadata is inconsistent",
        )
    if evidence is None or artifacts is None:
        return AssuranceResult(
            AssuranceDecision.BLOCKED,
            QualityBand.BLOCKED,
            "assurance requires the current evidence and artifact packet",
        )
    packet_bound = True
    if packet_bound:
        evidence_values = tuple(evidence or ())
        artifact_values = tuple(artifacts or ())
        if any(not isinstance(item, EvidenceRecord) for item in evidence_values) or any(
            not isinstance(item, ArtifactRecord) for item in artifact_values
        ):
            return AssuranceResult(
                AssuranceDecision.FAILED,
                QualityBand.FAILED,
                "assurance packet contains an untyped evidence or artifact record",
            )
        expected_packet_digest = verification_packet_digest(
            verification,
            evidence=evidence_values,
            artifacts=artifact_values,
        )
        if not critique.reviewer.blind_packet_digest:
            return AssuranceResult(
                AssuranceDecision.FAILED,
                QualityBand.FAILED,
                "packet-bound assurance requires a blind verification digest",
            )
        if critique.reviewer.blind_packet_digest != expected_packet_digest:
            return AssuranceResult(
                AssuranceDecision.FAILED,
                QualityBand.FAILED,
                "critique blind packet digest does not match the current packet",
            )
        if critique.quality_bar_ref != quality_bar_ref:
            return AssuranceResult(
                AssuranceDecision.BLOCKED,
                QualityBand.BLOCKED,
                "critique quality bar does not match the required assurance bar",
            )
        if not evidence_values or (verification.artifact_refs and not artifact_values):
            return AssuranceResult(
                AssuranceDecision.BLOCKED,
                QualityBand.BLOCKED,
                "assurance requires the current evidence and artifact packet",
            )
        if set(item.artifact_id for item in artifact_values) != set(verification.artifact_refs):
            return AssuranceResult(
                AssuranceDecision.FAILED,
                QualityBand.FAILED,
                "artifact packet does not match verification artifact references",
            )
        links = validate_evidence_links(
            verification.claims,
            verification.procedures,
            evidence_values,
            artifacts=artifact_values,
        )
        if not links.is_valid:
            return AssuranceResult(
                AssuranceDecision.FAILED,
                QualityBand.FAILED,
                "evidence packet failed the assurance link gate",
            )
    if require_independent and (
        _value(critique.independence) != Independence.INDEPENDENT.value
        or _value(critique.record.provenance.source_type) != SourceType.HUMAN.value
    ):
        return AssuranceResult(
            AssuranceDecision.BLOCKED,
            QualityBand.BLOCKED,
            "independent human critique evidence is required for this assurance decision",
        )
    if _value(verification.recommendation) == Recommendation.FAIL.value or any(
        claim.required and _value(claim.status) != ClaimStatus.PASS.value
        for claim in verification.claims
    ):
        return AssuranceResult(
            AssuranceDecision.FAILED,
            QualityBand.FAILED,
            "required verification claim failed",
        )
    if (
        _value(verification.recommendation) != Recommendation.PASS.value
        or verification.not_run
        or verification.unknown
    ):
        return AssuranceResult(
            AssuranceDecision.BLOCKED,
            QualityBand.BLOCKED,
            "verification contains not-run or unknown required scope",
        )
    if require_independent and _value(critique.independence) != Independence.INDEPENDENT.value:
        return AssuranceResult(
            AssuranceDecision.BLOCKED,
            QualityBand.BLOCKED,
            "independent critique is required for this assurance decision",
        )
    open_material = tuple(
        finding
        for finding in critique.findings
        if _value(finding.disposition) == FindingDisposition.OPEN.value
        and _value(finding.severity) in (FindingSeverity.CRITICAL.value, FindingSeverity.HIGH.value)
    )
    if open_material:
        return AssuranceResult(
            AssuranceDecision.REPAIR_REQUIRED,
            QualityBand.PARTIAL,
            "critique found an open material issue",
        )
    return AssuranceResult(
        AssuranceDecision.QUALITY_ACCEPTED,
        QualityBand.ACCEPTABLE,
        f"verification and critique satisfy {quality_bar_ref}",
    )


def build_quality_report(
    verification: VerificationReport,
    critique: CritiqueReport,
    assurance: AssuranceResult,
    *,
    profile: str = "P2-LOCAL",
    timestamp: str | None = None,
) -> QualityReport:
    """Materialize the assurance result as the existing quality contract."""

    created_at = timestamp or verification.created_at
    accepted = _value(assurance.decision) == AssuranceDecision.QUALITY_ACCEPTED.value
    gate_status = "PASS" if accepted else "BLOCKED"
    decision = QualityDecision.DELIVER if accepted else QualityDecision.STOP
    return QualityReport(
        schema_version=SchemaVersion.QUALITY_REPORT,
        report_id=f"QUAL-{verification.report_id}",
        task_id=verification.task_id,
        run_id=verification.run_id,
        record=_envelope(verification, created_at),
        profile=profile,
        artifact_refs=verification.artifact_refs,
        verification_ref=verification.report_id,
        critique_ref=critique.report_id,
        dimensions=(
            QualityDimension(
                dimension=QualityDimensionName.CORRECTNESS,
                score=1.0 if accepted else 0.0,
                confidence=Confidence.HIGH if accepted else Confidence.MEDIUM,
                evidence_refs=verification.record.evidence_refs,
                limitations=() if accepted else (assurance.reason,),
            ),
        ),
        gates=(
            QualityGate(
                gate_id="P2-EXECUTION",
                status=GateStatus(gate_status),
                required=True,
                evidence_refs=verification.record.evidence_refs,
            ),
        ),
        quality_band=assurance.quality_band,
        open_findings=tuple(
            item.finding_id
            for item in critique.findings
            if _value(item.disposition) == FindingDisposition.OPEN.value
        ),
        residual_risk="LOW" if accepted else "HIGH",
        decision=decision,
        decision_owner="local.assurance",
        created_at=created_at,
    )
