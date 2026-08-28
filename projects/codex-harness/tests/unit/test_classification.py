from __future__ import annotations

from dataclasses import replace

from test_contracts import profile

from harness_kernel.classification import (
    classify_task,
    explain_classification,
    normalize_task_profile,
)
from harness_kernel.models import (
    BlastRadius,
    Complexity,
    Confidence,
    DataImpact,
    Risk,
    SecurityImpact,
    TaskDomain,
)


def test_classification_is_multidimensional_and_explainable() -> None:
    value = classify_task(
        "Add a public paginated REST endpoint with authorization and persistent user data",
        "API endpoint, tests and verification",
        task_id="TASK-CLASS-1",
        run_id="RUN-CLASS-1",
        evidence_refs=("EVID-CLASS-1",),
        source_refs=("request-1",),
        created_at="2026-08-28T12:00:00Z",
    )

    assert value.domain is TaskDomain.API
    assert value.complexity in (Complexity.MEDIUM, Complexity.LARGE)
    assert value.risk in (Risk.HIGH, Risk.CRITICAL)
    assert value.security_impact in (SecurityImpact.HIGH, SecurityImpact.CRITICAL)
    assert value.data_impact is DataImpact.PERSISTENT
    assert value.blast_radius in (BlastRadius.SERVICE, BlastRadius.PUBLIC)
    assert value.classification_trace.rule_ids
    assert value.evidence.refs == ("EVID-CLASS-1",)
    assert not any(item.islower() for item in value.classification_trace.rule_ids)

    assessments = explain_classification(value)
    assert {item.dimension for item in assessments} >= {
        "domain",
        "complexity",
        "risk",
        "security_impact",
        "data_impact",
        "visual_importance",
        "research_need",
        "parallelism_potential",
        "reversibility",
        "blast_radius",
    }
    assert all(item.reason and item.evidence_refs == ("EVID-CLASS-1",) for item in assessments)


def test_classification_escalates_known_bad_irreversible_security_input() -> None:
    value = classify_task(
        "Drop the production database and migrate credentials irreversibly",
        "destructive production migration",
        task_id="TASK-CLASS-BAD",
        run_id="RUN-CLASS-BAD",
        evidence_refs=("EVID-BAD",),
        created_at="2026-08-28T12:00:00Z",
    )

    assert value.complexity is Complexity.CRITICAL
    assert value.risk is Risk.CRITICAL
    assert value.security_impact is SecurityImpact.CRITICAL
    assert value.data_impact is DataImpact.MIGRATION
    assert "CLS-RISK-CRITICAL" in value.classification_trace.rule_ids


def test_classification_preserves_assumptions_and_is_deterministic() -> None:
    kwargs = dict(
        task_id="TASK-CLASS-DET",
        run_id="RUN-CLASS-DET",
        evidence_refs=("EVID-DET",),
        assumptions=("the requested output remains local",),
        created_at="2026-08-28T12:00:00Z",
    )
    first = classify_task(
        "Validate a local manifest without execution", "validation report", **kwargs
    )
    second = classify_task(
        "Validate a local manifest without execution", "validation report", **kwargs
    )

    assert first == second
    assert "the requested output remains local" in first.classification_trace.assumptions


def test_classify_task_forwards_options_and_dimension_overrides() -> None:
    value = classify_task(
        "Implement an API endpoint",
        "bounded verification result",
        task_id="TASK-CLASS-OPTIONS",
        run_id="RUN-CLASS-OPTIONS",
        constraints=("local only",),
        non_goals=("no deployment",),
        evidence_refs=("EVID-OPTIONS",),
        source_refs=("request-options",),
        assumptions=("the endpoint remains local",),
        created_at="2026-08-28T12:00:00Z",
        source_type="official",
        hints={"risk": "low"},
        domain="api",
        blast_radius="module",
    )

    assert value.domain is TaskDomain.API
    assert value.risk is Risk.LOW
    assert value.blast_radius is BlastRadius.MODULE
    assert value.record.provenance.source_type.value == "OFFICIAL"
    assert value.record.provenance.source_refs == ("request-options",)
    assert value.constraints == ("local only",)
    assert value.non_goals == ("no deployment",)


def test_normalization_converts_enum_strings_without_mutating_profile() -> None:
    original = replace(profile(), domain="engineering", risk="low", confidence="high")
    normalized = normalize_task_profile(original)

    assert normalized.domain is TaskDomain.ENGINEERING
    assert normalized.risk is Risk.LOW
    assert normalized.confidence is Confidence.HIGH
    assert original.domain == "engineering"
    assert original.classification_trace.assumptions == ()


def test_ambiguous_input_preserves_unresolved_instead_of_inventing_route_facts() -> None:
    value = classify_task(
        "Do the thing",
        task_id="TASK-CLASS-UNKNOWN",
        run_id="RUN-CLASS-UNKNOWN",
        created_at="2026-08-28T12:00:00Z",
    )

    assert value.confidence in (Confidence.LOW, Confidence.UNKNOWN)
    assert value.classification_trace.unresolved


def test_golden_local_edits_have_a_low_risk_minimal_classification() -> None:
    for index, objective in enumerate(("Change button label.", "Fix one CSS margin."), 1):
        value = classify_task(
            objective,
            task_id=f"TASK-GOLDEN-SIMPLE-{index}",
            run_id=f"RUN-GOLDEN-SIMPLE-{index}",
            evidence_refs=(f"EVID-GOLDEN-SIMPLE-{index}",),
            created_at="2026-08-28T12:00:00Z",
        )

        assert value.complexity is Complexity.TRIVIAL
        assert value.risk is Risk.LOW
        assert value.blast_radius is BlastRadius.LOCAL
