from __future__ import annotations

from dataclasses import replace

from test_contracts import all_records

from harness_kernel.evidence import (
    evidence_is_fresh,
    evidence_satisfies_claim,
    mark_evidence_stale,
    validate_evidence_links,
)
from harness_kernel.models import (
    Claim,
    ClaimStatus,
    EvidenceResult,
    FreshnessStatus,
)


def test_claim_procedure_and_evidence_form_a_valid_trace() -> None:
    evidence = all_records()[6]
    verification = all_records()[7]
    claim = verification.claims[0]
    procedure = verification.procedures[0]

    result = validate_evidence_links((claim,), (procedure,), (evidence,))

    assert result.is_valid
    assert evidence_satisfies_claim(claim, (procedure,), (evidence,))
    assert evidence_is_fresh(evidence)


def test_links_reject_unknown_ids_and_mismatched_claims() -> None:
    evidence = all_records()[6]
    procedure = all_records()[7].procedures[0]
    claim = Claim(
        claim_id="CLAIM-UNKNOWN",
        text="unresolved claim",
        required=True,
        status=ClaimStatus.PASS,
        evidence_refs=(evidence.evidence_id,),
        limitation_refs=(),
    )

    result = validate_evidence_links((claim,), (procedure,), (evidence,))

    assert not result.is_valid
    assert any(finding.code.value == "INVALID_REFERENCE" for finding in result.findings)


def test_pass_evidence_requires_executed_procedure_and_freshness() -> None:
    evidence = all_records()[6]
    stale = replace(
        evidence,
        procedure=replace(evidence.procedure, executed=False),
        freshness=replace(evidence.freshness, status=FreshnessStatus.STALE),
        result=EvidenceResult.PASS,
    )

    result = validate_evidence_links(
        (all_records()[7].claims[0],),
        (all_records()[7].procedures[0],),
        (stale,),
    )

    assert not result.is_valid
    assert any(finding.code.value == "INVARIANT_VIOLATION" for finding in result.findings)


def test_staling_evidence_is_immutable_and_preserves_a_limitation() -> None:
    evidence = all_records()[6]

    stale = mark_evidence_stale(evidence, "ART-1 changed")

    assert evidence.freshness.status is FreshnessStatus.FRESH
    assert stale.freshness.status is FreshnessStatus.STALE
    assert stale.freshness.invalidated_by == ("ART-1 changed",)
    assert stale.limitations == ("ART-1 changed",)
