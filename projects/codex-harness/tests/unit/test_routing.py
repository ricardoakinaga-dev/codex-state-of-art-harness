from __future__ import annotations

from dataclasses import replace

import pytest
from test_contracts import all_records, profile

from harness_kernel.classification import classify_task
from harness_kernel.models import (
    CapabilityManifest,
    CapabilityPrimaryType,
    CapabilityScope,
    CapabilityStatus,
    Complexity,
    Confidence,
    DataImpact,
    RecordStatus,
    ResearchNeed,
    Risk,
    RouteKind,
    RouteStatus,
    SecurityImpact,
    TaskDomain,
)
from harness_kernel.registry import CapabilityRegistry
from harness_kernel.routing import minimum_route
from harness_kernel.validation import validate


def capability(
    capability_id: str,
    primary_type: CapabilityPrimaryType,
    *,
    domains: tuple[str, ...] = ("ENGINEERING",),
    minimum: Complexity = Complexity.SMALL,
    triggers: tuple[str, ...] = (),
    status: CapabilityStatus = CapabilityStatus.ACTIVE,
) -> CapabilityManifest:
    base = next(item for item in all_records() if isinstance(item, CapabilityManifest))
    return replace(
        base,
        capability_id=capability_id,
        primary_type=primary_type,
        status=status,
        record=replace(base.record, status=RecordStatus.CURRENT),
        scope=CapabilityScope(
            domains=domains,
            activates_when=triggers,
            do_not_activate_when=(),
            minimum_task_class=minimum,
        ),
    )


def test_trivial_task_uses_valid_no_special_direct_route() -> None:
    task = replace(
        profile(),
        complexity=Complexity.TRIVIAL,
        risk=Risk.LOW,
        confidence=Confidence.HIGH,
        evidence=replace(profile().evidence, refs=("EVID-ROUTE-1",)),
        record=replace(profile().record, evidence_refs=("EVID-ROUTE-1",)),
    )

    decision = minimum_route(task, CapabilityRegistry(), decision_id="ROUTE-DIRECT-1")

    assert decision.route_status is RouteStatus.NO_SPECIAL_ROUTE
    assert decision.route_kind is RouteKind.DIRECT
    assert decision.selected == ()
    assert validate(decision).is_valid


def test_golden_local_edits_use_no_special_route_without_visual_overactivation() -> None:
    for index, objective in enumerate(("Change button label.", "Fix one CSS margin."), 1):
        task = classify_task(
            objective,
            task_id=f"TASK-GOLDEN-ROUTE-{index}",
            run_id=f"RUN-GOLDEN-ROUTE-{index}",
            evidence_refs=(f"EVID-GOLDEN-ROUTE-{index}",),
            created_at="2026-08-28T12:00:00Z",
        )

        decision = minimum_route(task, CapabilityRegistry(), decision_id=f"ROUTE-GOLDEN-{index}")

        assert decision.route_status is RouteStatus.NO_SPECIAL_ROUTE
        assert decision.route_kind is RouteKind.DIRECT


def test_registry_route_composes_specialist_and_required_verification() -> None:
    task = replace(
        profile(),
        task_id="TASK-ROUTE-API",
        domain=TaskDomain.API,
        complexity=Complexity.MEDIUM,
        risk=Risk.MEDIUM,
        security_impact=SecurityImpact.MEDIUM,
        data_impact=DataImpact.PERSISTENT,
    )
    registry = CapabilityRegistry()
    registry = registry.register(
        capability("api-specialist", CapabilityPrimaryType.SPECIALIST, domains=("API",))
    )
    registry = registry.register(
        capability("verification", CapabilityPrimaryType.VERIFICATION, domains=("API", "GENERAL"))
    )

    decision = minimum_route(task, registry, decision_id="ROUTE-COMPOSED-1")

    assert decision.route_status is RouteStatus.SELECTED
    assert decision.route_kind is RouteKind.COMPOSED
    assert {item.capability_id for item in decision.selected} == {"api-specialist", "verification"}
    assert validate(decision).is_valid


def test_explicit_provider_is_selected_without_calling_it() -> None:
    task = replace(profile(), research_need=ResearchNeed.FRESHNESS_REQUIRED)
    registry = CapabilityRegistry().register(
        capability("official-provider", CapabilityPrimaryType.PROVIDER, domains=("ENGINEERING",))
    )

    decision = minimum_route(
        task,
        registry,
        explicit_provider="official-provider",
        decision_id="ROUTE-PROVIDER-1",
    )

    assert decision.route_status is RouteStatus.SELECTED
    assert decision.route_kind is RouteKind.PROVIDER
    assert decision.selected[0].capability_id == "official-provider"


def test_unavailable_provider_falls_back_or_blocks_explicitly() -> None:
    task = replace(profile(), research_need=ResearchNeed.FRESHNESS_REQUIRED)

    fallback = minimum_route(
        task,
        CapabilityRegistry(),
        explicit_provider="missing-provider",
        allow_fallback=True,
        decision_id="ROUTE-FALLBACK-1",
    )
    blocked = minimum_route(
        task,
        CapabilityRegistry(),
        explicit_provider="missing-provider",
        allow_fallback=False,
        decision_id="ROUTE-BLOCKED-1",
    )

    assert fallback.route_status is RouteStatus.FALLBACK
    assert fallback.route_kind is RouteKind.DEGRADED
    assert blocked.route_status is RouteStatus.BLOCKED


def test_unknown_material_profile_is_conditional_and_never_executes() -> None:
    task = classify_task(
        "Do the thing",
        task_id="TASK-ROUTE-UNKNOWN",
        run_id="RUN-ROUTE-UNKNOWN",
        created_at="2026-08-28T12:00:00Z",
    )

    decision = minimum_route(task, CapabilityRegistry(), decision_id="ROUTE-CONDITIONAL-1")

    assert decision.route_status is RouteStatus.CONDITIONAL
    assert decision.unresolved


def test_rejected_and_deprecated_explicit_capabilities_are_not_recoverable() -> None:
    task = classify_task(
        "Do the thing",
        task_id="TASK-ROUTE-REJECTED",
        run_id="RUN-ROUTE-REJECTED",
        created_at="2026-08-28T12:00:00Z",
    )
    rejected = capability(
        "rejected-capability", CapabilityPrimaryType.SPECIALIST, status=CapabilityStatus.REJECTED
    )
    deprecated = capability(
        "deprecated-capability",
        CapabilityPrimaryType.SPECIALIST,
        status=CapabilityStatus.DEPRECATED,
    )
    registry = CapabilityRegistry.from_manifests((rejected, deprecated))

    rejected_route = minimum_route(task, registry, explicit_capabilities=(rejected.capability_id,))
    deprecated_route = minimum_route(
        task, registry, explicit_capabilities=(deprecated.capability_id,)
    )

    assert rejected_route.route_status is RouteStatus.REJECTED
    assert deprecated_route.route_status is RouteStatus.REJECTED


@pytest.mark.parametrize(
    ("objective", "capability_id", "trigger"),
    (
        ("Change the text Security Settings", "security-review", "security"),
        ("Fix login page typo", "design-director", "login"),
        ("Update README", "engineering-director", "README"),
        ("Research button color", "deep-research", "research"),
        ("Fix CSS margin", "orchestrator", "CSS"),
        ("Create a secure-looking blue card", "security-review", "secure"),
        ("Fix API button label", "api-design", "API"),
    ),
)
def test_incidental_tokens_do_not_activate_forbidden_specialists(
    objective: str, capability_id: str, trigger: str
) -> None:
    task = classify_task(
        objective,
        task_id="TASK-ROUTE-NEGATIVE",
        run_id="RUN-ROUTE-NEGATIVE",
        evidence_refs=("EVID-ROUTE-NEGATIVE",),
        created_at="2026-08-28T12:00:00Z",
    )
    registry = CapabilityRegistry().register(
        capability(
            capability_id,
            CapabilityPrimaryType.SPECIALIST,
            domains=("GENERAL",),
            triggers=(trigger,),
        )
    )

    decision = minimum_route(task, registry, decision_id="ROUTE-NEGATIVE")

    assert capability_id not in {item.capability_id for item in decision.selected}
