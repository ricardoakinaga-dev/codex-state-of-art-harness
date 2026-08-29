"""Pure evidence-link and freshness primitives for the Phase 1 kernel."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from .models import (
    ArtifactRecord,
    Claim,
    ClaimStatus,
    EvidenceRecord,
    EvidenceResult,
    FreshnessStatus,
    ProcedureStatus,
    RecordStatus,
    VerificationProcedure,
)
from .validation import ValidationCode, ValidationFinding, ValidationResult, validate


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    """A resolved claim -> procedure -> evidence relationship."""

    claim_id: str
    procedure_id: str
    evidence_id: str


def _value(value: object) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def _items[T](values: Iterable[T] | Mapping[str, T]) -> tuple[T, ...]:
    if isinstance(values, Mapping):
        return tuple(values.values())
    return tuple(values)


def _finding(code: ValidationCode, path: str, message: str) -> ValidationFinding:
    return ValidationFinding(code=code, path=path, message=message)


def _index(
    values: Iterable[Any] | Mapping[str, Any],
    identifier: str,
    path: str,
    findings: list[ValidationFinding],
) -> dict[str, Any]:
    indexed: dict[str, Any] = {}
    for index, value in enumerate(_items(values)):
        key = getattr(value, identifier, None)
        if not isinstance(key, str) or not key.strip():
            findings.append(
                _finding(
                    ValidationCode.INVALID_ID,
                    f"{path}[{index}].{identifier}",
                    "identifier is required",
                )
            )
            continue
        if key in indexed:
            findings.append(
                _finding(
                    ValidationCode.INVARIANT_VIOLATION,
                    f"{path}[{index}].{identifier}",
                    "identifiers must be unique",
                )
            )
            continue
        indexed[key] = value
    return indexed


def _concrete_observation(value: str) -> bool:
    normalized = value.strip().casefold()
    if not normalized:
        return False
    return not normalized.startswith(("prediction:", "explanation:", "expected:", "should "))


def _is_passing_evidence(
    evidence: EvidenceRecord, procedures: Mapping[str, VerificationProcedure]
) -> bool:
    procedure = procedures.get(evidence.procedure.procedure_id)
    return bool(
        _value(evidence.result) == EvidenceResult.PASS.value
        and evidence.procedure.executed
        and procedure is not None
        and _value(procedure.status) == ProcedureStatus.EXECUTED.value
        and _value(procedure.result) == EvidenceResult.PASS.value
        and _value(evidence.freshness.status) == FreshnessStatus.FRESH.value
        and _concrete_observation(evidence.observation)
    )


def validate_evidence_links(
    claims: Iterable[Claim] | Mapping[str, Claim],
    procedures: Iterable[VerificationProcedure] | Mapping[str, VerificationProcedure],
    evidence: Iterable[EvidenceRecord] | Mapping[str, EvidenceRecord],
    *,
    artifacts: Iterable[ArtifactRecord] | Mapping[str, ArtifactRecord] | None = None,
) -> ValidationResult:
    """Validate claim/procedure/evidence links and optional artifact digests."""

    findings: list[ValidationFinding] = []
    claim_items = _items(claims)
    procedure_items = _items(procedures)
    evidence_items = _items(evidence)
    artifact_items = _items(artifacts) if artifacts is not None else ()
    claim_index = _index(claim_items, "claim_id", "$.claims", findings)
    procedure_index = _index(procedure_items, "procedure_id", "$.procedures", findings)
    evidence_index = _index(evidence_items, "evidence_id", "$.evidence", findings)
    artifact_index = _index(artifact_items, "artifact_id", "$.artifacts", findings)

    for evidence_id, item in sorted(evidence_index.items()):
        base = validate(item)
        findings.extend(base.findings)
        claim = claim_index.get(item.claim_ref)
        if claim is None:
            findings.append(
                _finding(
                    ValidationCode.INVALID_REFERENCE,
                    "$.evidence[].claim_ref",
                    "evidence points to an unknown claim",
                )
            )
        procedure = procedure_index.get(item.procedure.procedure_id)
        if procedure is None:
            findings.append(
                _finding(
                    ValidationCode.INVALID_REFERENCE,
                    "$.evidence[].procedure.procedure_id",
                    "evidence points to an unknown procedure",
                )
            )
        if _value(item.result) == EvidenceResult.PASS.value and not _is_passing_evidence(
            item, procedure_index
        ):
            findings.append(
                _finding(
                    ValidationCode.INVARIANT_VIOLATION,
                    f"$.evidence[{evidence_id}].result",
                    "PASS evidence needs an executed fresh procedure and concrete observation",
                )
            )
        if (
            _value(item.freshness.status) == FreshnessStatus.STALE.value
            and not item.freshness.invalidated_by
        ):
            findings.append(
                _finding(
                    ValidationCode.INVARIANT_VIOLATION,
                    f"$.evidence[{evidence_id}].freshness",
                    "stale evidence needs an invalidation reason",
                )
            )
        if (
            _value(item.freshness.status) == FreshnessStatus.FRESH.value
            and item.freshness.invalidated_by
        ):
            findings.append(
                _finding(
                    ValidationCode.INVARIANT_VIOLATION,
                    f"$.evidence[{evidence_id}].freshness",
                    "fresh evidence cannot have invalidation reasons",
                )
            )
        if claim is not None and item.evidence_id not in claim.evidence_refs:
            findings.append(
                _finding(
                    ValidationCode.INVALID_REFERENCE,
                    "$.claims[].evidence_refs",
                    "claim does not link the evidence record",
                )
            )
        if procedure is not None and item.evidence_id not in procedure.evidence_refs:
            findings.append(
                _finding(
                    ValidationCode.INVALID_REFERENCE,
                    "$.procedures[].evidence_refs",
                    "procedure does not link the evidence record",
                )
            )
        if artifacts is not None:
            for artifact_id in item.artifact_refs:
                artifact = artifact_index.get(artifact_id)
                if artifact is None:
                    findings.append(
                        _finding(
                            ValidationCode.INVALID_REFERENCE,
                            f"$.evidence[{evidence_id}].artifact_refs",
                            "evidence points to an unknown artifact",
                        )
                    )
                    continue
                content_digest = item.provenance.content_digest
                if content_digest is None:
                    findings.append(
                        _finding(
                            ValidationCode.INVARIANT_VIOLATION,
                            f"$.evidence[{evidence_id}].provenance.content_digest",
                            "artifact-linked evidence needs a content digest",
                        )
                    )
                elif content_digest != artifact.content.digest:
                    findings.append(
                        _finding(
                            ValidationCode.INVARIANT_VIOLATION,
                            f"$.evidence[{evidence_id}].provenance.content_digest",
                            "evidence content digest does not match the artifact digest",
                        )
                    )
                if item.provenance.source_ref != artifact.provenance.tool_or_process:
                    findings.append(
                        _finding(
                            ValidationCode.INVARIANT_VIOLATION,
                            f"$.evidence[{evidence_id}].provenance.source_ref",
                            "evidence source does not match the artifact producer",
                        )
                    )

    linked_evidence: set[str] = set()
    for claim_id, claim in sorted(claim_index.items()):
        for evidence_id in claim.evidence_refs:
            linked_evidence.add(evidence_id)
            item = evidence_index.get(evidence_id)
            if item is None:
                findings.append(
                    _finding(
                        ValidationCode.INVALID_REFERENCE,
                        f"$.claims[{claim_id}].evidence_refs",
                        "claim points to an unknown evidence record",
                    )
                )
            elif item.claim_ref != claim_id:
                findings.append(
                    _finding(
                        ValidationCode.INVALID_REFERENCE,
                        f"$.claims[{claim_id}].evidence_refs",
                        "evidence claim_ref does not match the claim",
                    )
                )
        if _value(claim.status) == ClaimStatus.PASS.value:
            if not claim.evidence_refs:
                findings.append(
                    _finding(
                        ValidationCode.MISSING_EVIDENCE,
                        f"$.claims[{claim_id}].evidence_refs",
                        "PASS claim needs evidence",
                    )
                )
            elif not any(
                item is not None and _is_passing_evidence(item, procedure_index)
                for item in (evidence_index.get(ref) for ref in claim.evidence_refs)
            ):
                findings.append(
                    _finding(
                        ValidationCode.INVARIANT_VIOLATION,
                        f"$.claims[{claim_id}].status",
                        "PASS claim needs a linked passing fresh evidence",
                    )
                )

    for procedure_id, procedure in sorted(procedure_index.items()):
        for evidence_id in procedure.evidence_refs:
            item = evidence_index.get(evidence_id)
            if item is None:
                findings.append(
                    _finding(
                        ValidationCode.INVALID_REFERENCE,
                        f"$.procedures[{procedure_id}].evidence_refs",
                        "procedure points to an unknown evidence record",
                    )
                )
            elif item.procedure.procedure_id != procedure_id:
                findings.append(
                    _finding(
                        ValidationCode.INVALID_REFERENCE,
                        f"$.procedures[{procedure_id}].evidence_refs",
                        "evidence procedure_id does not match the procedure",
                    )
                )
        if (
            _value(procedure.status) == ProcedureStatus.EXECUTED.value
            and _value(procedure.result) == EvidenceResult.PASS.value
            and not procedure.evidence_refs
        ):
            findings.append(
                _finding(
                    ValidationCode.MISSING_EVIDENCE,
                    f"$.procedures[{procedure_id}].evidence_refs",
                    "executed passing procedure needs evidence",
                )
            )

    for evidence_id in sorted(set(evidence_index) - linked_evidence):
        findings.append(
            _finding(
                ValidationCode.INVALID_REFERENCE,
                f"$.evidence[{evidence_id}]",
                "evidence is not linked by a claim",
            )
        )

    return ValidationResult(
        valid=not findings, findings=tuple(findings), record_type="EvidenceLinks"
    )


def evidence_is_fresh(evidence: EvidenceRecord) -> bool:
    """Return whether an evidence record is current and not invalidated."""

    return (
        _value(evidence.freshness.status) == FreshnessStatus.FRESH.value
        and not evidence.freshness.invalidated_by
    )


def evidence_satisfies_claim(
    claim: Claim,
    procedures: Iterable[VerificationProcedure] | Mapping[str, VerificationProcedure],
    evidence: Iterable[EvidenceRecord] | Mapping[str, EvidenceRecord],
) -> bool:
    """Return true only when a linked evidence record can support the claim."""

    procedure_index = _index(procedures, "procedure_id", "$.procedures", [])
    evidence_index = _index(evidence, "evidence_id", "$.evidence", [])
    if _value(claim.status) != ClaimStatus.PASS.value:
        return False
    return any(
        item is not None
        and item.claim_ref == claim.claim_id
        and _is_passing_evidence(item, procedure_index)
        for item in (evidence_index.get(ref) for ref in claim.evidence_refs)
    )


def mark_evidence_stale(evidence: EvidenceRecord, *reasons: str) -> EvidenceRecord:
    """Return a stale copy while preserving the original record."""

    normalized = tuple(
        reason.strip() for reason in reasons if isinstance(reason, str) and reason.strip()
    )
    if not normalized:
        raise ValueError("at least one invalidation reason is required")
    invalidated_by = tuple(dict.fromkeys((*evidence.freshness.invalidated_by, *normalized)))
    limitations = tuple(dict.fromkeys((*evidence.limitations, *normalized)))
    freshness = replace(
        evidence.freshness, status=FreshnessStatus.STALE, invalidated_by=invalidated_by
    )
    record = replace(evidence.record, status=RecordStatus.STALE)
    return replace(evidence, record=record, freshness=freshness, limitations=limitations)


# Compatibility aliases keep the primitive vocabulary discoverable.
validate_evidence_chain = validate_evidence_links
validate_claim_procedure_evidence = validate_evidence_links
is_evidence_fresh = evidence_is_fresh
stale_evidence = mark_evidence_stale
