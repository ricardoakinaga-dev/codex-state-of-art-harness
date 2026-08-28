"""Pure minimum-route policy for ``TaskProfile`` values.

This module only proposes a ``RouteDecision``.  Registry entries are metadata;
no capability, provider or tool is imported or invoked here.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .classification import DEFAULT_TIMESTAMP, normalize_task_profile
from .models import (
    CapabilityManifest,
    CapabilityPrimaryType,
    CapabilityStatus,
    Complexity,
    Confidence,
    ContextBudget,
    DataImpact,
    OmittedCapability,
    OmittedReasonCode,
    OptionalCapability,
    Provenance,
    RecordEnvelope,
    RecordStatus,
    ReferencePack,
    ResearchNeed,
    Risk,
    RouteBudget,
    RouteCompatibility,
    RouteDecision,
    RouteDecisionDetails,
    RouteKind,
    RouteStatus,
    SchemaVersion,
    SecurityImpact,
    SelectedCapability,
    SourceType,
    TaskDomain,
    TaskProfile,
    VisualImportance,
)
from .registry import CapabilityRegistry
from .validation import validate


class RoutePolicyError(ValueError):
    """Raised when a route policy cannot be represented safely."""


@dataclass(frozen=True, slots=True)
class MinimumRoutePolicy:
    """Declarative thresholds for the smallest justified route."""

    verification_minimum: Complexity = Complexity.MEDIUM
    max_skill_kernels: int | None = 3
    max_reference_pack: ReferencePack = ReferencePack.MINIMAL
    allow_fallback: bool = True
    default_parallelism_budget: int = 1
    native_tools: tuple[str, ...] = ()
    provider_constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.max_skill_kernels is not None and self.max_skill_kernels < 0:
            raise RoutePolicyError("max_skill_kernels cannot be negative")
        if self.default_parallelism_budget < 0:
            raise RoutePolicyError("parallelism budget cannot be negative")


RoutePolicy = MinimumRoutePolicy


_COMPLEXITY_ORDER = {
    Complexity.TRIVIAL: 0,
    Complexity.SMALL: 1,
    Complexity.MEDIUM: 2,
    Complexity.LARGE: 3,
    Complexity.CRITICAL: 4,
}
_RISK_ORDER = {Risk.LOW: 0, Risk.MEDIUM: 1, Risk.HIGH: 2, Risk.CRITICAL: 3, Risk.UNKNOWN: 4}
_TOKEN_PATTERN = re.compile(r"[A-Za-zÀ-ÿ0-9]+(?:[-'][A-Za-zÀ-ÿ0-9]+)*")


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _tokens(value: str) -> frozenset[str]:
    return frozenset(item.casefold() for item in _TOKEN_PATTERN.findall(value))


def _condition_hit(condition: str, text: str) -> bool:
    folded = text.casefold()
    if condition.casefold() in folded:
        return True
    words = _tokens(condition)
    return bool(words) and len(words & _tokens(text)) >= max(1, min(2, len(words)))


def _complexity_at_least(actual: Complexity, minimum: Complexity) -> bool:
    actual_value = Complexity(_value(actual))
    minimum_value = Complexity(_value(minimum))
    return _COMPLEXITY_ORDER[actual_value] >= _COMPLEXITY_ORDER[minimum_value]


def _profile_text(profile: TaskProfile) -> str:
    return " ".join((profile.objective, profile.requested_outcome, *profile.constraints))


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _safe_code(value: object) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._:/@-]+", "_", str(value)).strip("_")
    return cleaned or "UNRESOLVED"


def _safe_id(prefix: str, value: str) -> str:
    candidate = f"{prefix}-{value}"
    cleaned = re.sub(r"[^A-Za-z0-9._:/@-]+", "-", candidate).strip("-")
    return cleaned or f"{prefix}-UNSPECIFIED"


def _matching_manifest(manifest: CapabilityManifest, profile: TaskProfile, text: str) -> bool:
    domains = {_value(item).upper() for item in manifest.scope.domains}
    profile_domain = _value(profile.domain).upper()
    if domains and "GENERAL" not in domains and profile_domain not in domains:
        return False
    if _complexity_at_least(profile.complexity, manifest.scope.minimum_task_class) is False:
        return False
    if any(_condition_hit(condition, text) for condition in manifest.scope.do_not_activate_when):
        return False
    return not manifest.scope.activates_when or any(
        _condition_hit(condition, text) for condition in manifest.scope.activates_when
    )


def _candidates(
    registry: CapabilityRegistry, profile: TaskProfile, text: str
) -> tuple[CapabilityManifest, ...]:
    allowed = {
        CapabilityStatus.CANDIDATE.value,
        CapabilityStatus.EXPERIMENTAL.value,
        CapabilityStatus.VERIFIED.value,
        CapabilityStatus.ACTIVE.value,
    }
    values = [
        item
        for item in registry.list(
            include_stale=False,
            include_deprecated=False,
            include_rejected=False,
        )
        if _value(item.status) in allowed
        and _matching_manifest(item, profile, text)
        and registry.inspect(item.capability_id, item.version).usable
    ]
    return tuple(sorted(values, key=lambda item: (item.capability_id, item.version)))


def _pick(
    candidates: Iterable[CapabilityManifest], primary_types: Iterable[CapabilityPrimaryType]
) -> CapabilityManifest | None:
    wanted = {_value(item) for item in primary_types}
    matches = [item for item in candidates if _value(item.primary_type) in wanted]
    if not matches:
        return None
    capability_id = min(item.capability_id for item in matches)
    same_id = [item for item in matches if item.capability_id == capability_id]
    return max(same_id, key=lambda item: item.version)


def _selected(
    manifest: CapabilityManifest,
    reason: str,
    *,
    required: bool = True,
) -> SelectedCapability:
    role = (
        manifest.primary_type
        if isinstance(manifest.primary_type, CapabilityPrimaryType)
        else CapabilityPrimaryType(_value(manifest.primary_type))
    )
    return SelectedCapability(manifest.capability_id, role, reason, required)


def _omitted(
    capability_id: str, reason_code: OmittedReasonCode, explanation: str
) -> OmittedCapability:
    return OmittedCapability(capability_id, reason_code, explanation)


def _record(profile: TaskProfile, profile_ref: str, created_at: str) -> RecordEnvelope:
    evidence = tuple(profile.evidence.refs)
    return RecordEnvelope(
        status=RecordStatus.CURRENT,
        provenance=Provenance(SourceType.GENERATED, (profile_ref,), created_at),
        evidence_refs=evidence,
    )


def _invalid_route(
    profile: object,
    *,
    decision_id: str | None,
    authority_ref: str | None,
    created_at: str | None,
    reason: str,
) -> RouteDecision:
    raw_task_id = str(getattr(profile, "task_id", "TASK-REJECTED"))
    task_id = (
        raw_task_id
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}", raw_task_id)
        else "TASK-REJECTED"
    )
    run_id = str(getattr(profile, "run_id", "RUN-REJECTED"))
    profile_ref = _safe_id("PROFILE", task_id)
    created = created_at or DEFAULT_TIMESTAMP
    return RouteDecision(
        schema_version=SchemaVersion.ROUTE_DECISION,
        decision_id=decision_id or _safe_id("ROUTE", task_id),
        task_id=task_id,
        run_id=run_id,
        record=RecordEnvelope(
            status=RecordStatus.CURRENT,
            provenance=Provenance(SourceType.GENERATED, (profile_ref,), created),
            evidence_refs=(),
        ),
        profile_ref=profile_ref,
        route_status=RouteStatus.REJECTED,
        route_kind=RouteKind.DEGRADED,
        decision=RouteDecisionDetails(
            precedence_rule_ids=("SAFETY-FIRST",),
            activation_reasons=(),
            non_activation_reasons=(reason,),
            alternatives_considered=(),
        ),
        compatibility=RouteCompatibility((), (), ()),
        budget=RouteBudget(None, None, 0),
        context_budget=ContextBudget(None, ReferencePack.MINIMAL),
        confidence=Confidence.LOW,
        authority_ref=authority_ref or _safe_id("AUTH", task_id),
        created_at=created,
        omitted=(_omitted("invalid-profile", OmittedReasonCode.CONFLICT, reason),),
        quality_gates=("profile-validation",),
        unresolved=("INVALID_PROFILE",),
    )


def minimum_route(
    profile: TaskProfile,
    registry: CapabilityRegistry | Iterable[CapabilityManifest] | None = None,
    *,
    policy: MinimumRoutePolicy | None = None,
    decision_id: str | None = None,
    authority_ref: str | None = None,
    explicit_capabilities: Iterable[str] = (),
    requested_capabilities: Iterable[str] | None = None,
    explicit_provider: str | None = None,
    provider_id: str | None = None,
    allow_fallback: bool | None = None,
    available_tools: Iterable[str] = (),
    native_tools: Iterable[str] | None = None,
    provider_constraints: Iterable[str] = (),
    created_at: str | None = None,
) -> RouteDecision:
    """Emit the smallest safe route for a profile and registry snapshot."""

    selected_capability_ids = tuple(
        explicit_capabilities if requested_capabilities is None else requested_capabilities
    )
    requested_provider = explicit_provider or provider_id
    selected_policy = policy or MinimumRoutePolicy()
    fallback_allowed = selected_policy.allow_fallback if allow_fallback is None else allow_fallback
    try:
        normalized = normalize_task_profile(profile)
    except (TypeError, ValueError):
        return _invalid_route(
            profile,
            decision_id=decision_id,
            authority_ref=authority_ref,
            created_at=created_at,
            reason="profile cannot be normalized into the TaskProfile contract",
        )
    if not validate(normalized).is_valid:
        return _invalid_route(
            normalized,
            decision_id=decision_id,
            authority_ref=authority_ref,
            created_at=created_at,
            reason="profile fails the TaskProfile contract validation",
        )
    registry_value = (
        registry
        if isinstance(registry, CapabilityRegistry)
        else CapabilityRegistry.from_manifests(registry or ())
    )
    text = _profile_text(normalized)
    profile_ref = f"{normalized.task_id}@{_value(normalized.schema_version)}"
    created = created_at or normalized.created_at or DEFAULT_TIMESTAMP
    decision_key = decision_id or _safe_id("ROUTE", normalized.task_id)
    auth_key = authority_ref or _safe_id("AUTH-ROUTE", normalized.task_id)
    candidates = _candidates(registry_value, normalized, text)
    selected: list[SelectedCapability] = []
    optional: list[OptionalCapability] = []
    omitted: list[OmittedCapability] = []
    unresolved = list(normalized.classification_trace.unresolved)
    activation_reasons: list[str] = []
    non_activation_reasons: list[str] = []

    def add(manifest: CapabilityManifest, reason: str, required: bool = True) -> None:
        if manifest.capability_id not in {item.capability_id for item in selected}:
            selected.append(_selected(manifest, reason, required=required))
            activation_reasons.append(reason)

    if requested_provider:
        provider = registry_value.find(
            requested_provider, include_rejected=True, include_deprecated=True, include_stale=True
        )
        usable = (
            provider is not None
            and registry_value.inspect(provider.capability_id, provider.version).usable
        )
        if provider is None:
            omitted.append(
                _omitted(
                    requested_provider,
                    OmittedReasonCode.UNAVAILABLE,
                    "explicit provider is not registered",
                )
            )
            unresolved.append("PROVIDER_UNAVAILABLE")
        elif _value(provider.primary_type) != CapabilityPrimaryType.PROVIDER.value:
            omitted.append(
                _omitted(
                    requested_provider,
                    OmittedReasonCode.CONFLICT,
                    "explicit provider ID is not a provider manifest",
                )
            )
            unresolved.append("PROVIDER_TYPE_MISMATCH")
        elif _value(provider.status) == CapabilityStatus.REJECTED.value:
            omitted.append(
                _omitted(
                    requested_provider,
                    OmittedReasonCode.CONFLICT,
                    "explicit provider manifest is rejected",
                )
            )
            unresolved.append("PROVIDER_REJECTED")
        elif _value(provider.status) == CapabilityStatus.DEPRECATED.value:
            omitted.append(
                _omitted(
                    requested_provider,
                    OmittedReasonCode.UNAVAILABLE,
                    "explicit provider manifest is deprecated",
                )
            )
            unresolved.append("PROVIDER_DEPRECATED")
        elif not usable:
            omitted.append(
                _omitted(
                    requested_provider,
                    OmittedReasonCode.UNAVAILABLE,
                    "explicit provider manifest is stale or untrusted",
                )
            )
            unresolved.append("PROVIDER_UNAVAILABLE")
        elif not _matching_manifest(provider, normalized, text):
            omitted.append(
                _omitted(
                    requested_provider,
                    OmittedReasonCode.OUT_OF_SCOPE,
                    "provider scope does not match the profile",
                )
            )
            unresolved.append("PROVIDER_SCOPE_MISMATCH")
        else:
            add(provider, "explicit provider request was considered and passed scope checks")

    for capability_id in selected_capability_ids:
        manifest = registry_value.find(
            capability_id, include_rejected=True, include_deprecated=True, include_stale=True
        )
        if manifest is None:
            omitted.append(
                _omitted(
                    capability_id,
                    OmittedReasonCode.UNAVAILABLE,
                    "explicit capability is not registered",
                )
            )
            unresolved.append("CAPABILITY_UNAVAILABLE")
            continue
        inspection = registry_value.inspect(manifest.capability_id, manifest.version)
        if _value(manifest.status) == CapabilityStatus.REJECTED.value:
            omitted.append(
                _omitted(
                    capability_id, OmittedReasonCode.CONFLICT, "manifest is explicitly rejected"
                )
            )
            unresolved.append("CAPABILITY_REJECTED")
        elif _value(manifest.status) == CapabilityStatus.DEPRECATED.value:
            omitted.append(
                _omitted(
                    capability_id,
                    OmittedReasonCode.UNAVAILABLE,
                    "manifest is explicitly deprecated",
                )
            )
            unresolved.append("CAPABILITY_DEPRECATED")
        elif not inspection.usable:
            omitted.append(
                _omitted(
                    capability_id,
                    OmittedReasonCode.UNAVAILABLE,
                    "capability manifest is stale or lacks provenance",
                )
            )
            unresolved.append("CAPABILITY_UNAVAILABLE")
        elif not _matching_manifest(manifest, normalized, text):
            omitted.append(
                _omitted(
                    capability_id,
                    OmittedReasonCode.OUT_OF_SCOPE,
                    "explicit invocation does not satisfy capability scope",
                )
            )
            unresolved.append("CAPABILITY_SCOPE_MISMATCH")
        else:
            add(manifest, "explicit capability request was considered and passed scope checks")

    if not requested_provider and not selected_capability_ids:
        specialist = _pick(candidates, (CapabilityPrimaryType.SPECIALIST,))
        if specialist is not None and not (
            normalized.complexity is Complexity.TRIVIAL
            and normalized.risk is Risk.LOW
            and normalized.visual_importance is VisualImportance.NONE
            and normalized.research_need is ResearchNeed.NONE
        ):
            add(specialist, "exact domain specialist covers the task boundary")
        elif specialist is None and normalized.domain is not TaskDomain.GENERAL:
            omitted.append(
                _omitted(
                    f"domain:{_value(normalized.domain)}",
                    OmittedReasonCode.UNAVAILABLE,
                    "no usable domain specialist is registered",
                )
            )
            non_activation_reasons.append("domain-specialist-unavailable")

    requires_verification = (
        _complexity_at_least(normalized.complexity, selected_policy.verification_minimum)
        or _RISK_ORDER[normalized.risk] >= _RISK_ORDER[Risk.HIGH]
        or normalized.security_impact is not SecurityImpact.NONE
        or normalized.data_impact
        in (DataImpact.PERSISTENT, DataImpact.MIGRATION, DataImpact.SENSITIVE)
        or normalized.visual_importance in (VisualImportance.MATERIAL, VisualImportance.PRIMARY)
        or normalized.research_need is not ResearchNeed.NONE
    )
    if requires_verification and not requested_provider:
        verifier = _pick(
            candidates, (CapabilityPrimaryType.VERIFICATION, CapabilityPrimaryType.VALIDATOR)
        )
        if verifier is not None:
            add(verifier, "verification evidence is required by profile risk/complexity")
        else:
            optional.append(
                OptionalCapability(
                    "verification",
                    "when a verification capability is available",
                    "required evidence boundary is not registered",
                )
            )
            unresolved.append("VERIFICATION_UNAVAILABLE")

    if requested_provider and selected and requires_verification:
        verifier = _pick(
            candidates, (CapabilityPrimaryType.VERIFICATION, CapabilityPrimaryType.VALIDATOR)
        )
        if verifier is not None:
            add(verifier, "provider output still needs independent contract verification")

    if normalized.visual_importance is VisualImportance.PRIMARY:
        visual = _pick(
            candidates, (CapabilityPrimaryType.SPECIALIST, CapabilityPrimaryType.REVIEWER)
        )
        if visual is not None and visual.capability_id not in {
            item.capability_id for item in selected
        }:
            optional.append(
                OptionalCapability(
                    visual.capability_id,
                    "when rendered visual inspection is available",
                    "primary visual outcome requires render/critic evidence",
                )
            )
        else:
            optional.append(
                OptionalCapability(
                    "visual-review",
                    "when visual inspection is available",
                    "primary visual outcome requires render/critic evidence",
                )
            )

    unresolved_tuple = _dedupe(unresolved)
    if (
        normalized.confidence is Confidence.UNKNOWN
        and "CLASSIFICATION_UNCERTAIN" not in unresolved_tuple
    ):
        unresolved_tuple = unresolved_tuple + ("CLASSIFICATION_UNCERTAIN",)
    high_material_unknown = normalized.risk is Risk.UNKNOWN and normalized.complexity in (
        Complexity.LARGE,
        Complexity.CRITICAL,
    )
    if selected:
        if (
            requested_provider
            and all(item.role is CapabilityPrimaryType.PROVIDER for item in selected)
            or (
                requested_provider
                and selected[0].role is CapabilityPrimaryType.PROVIDER
                and len(selected) == 1
            )
        ):
            kind = RouteKind.PROVIDER
        elif len(selected) > 1:
            kind = RouteKind.COMPOSED
        else:
            kind = RouteKind.SPECIALIST
        status = RouteStatus.SELECTED
        fallback = None
    elif (
        normalized.complexity is Complexity.TRIVIAL
        and normalized.risk is Risk.LOW
        and normalized.visual_importance is not VisualImportance.PRIMARY
        and normalized.research_need is ResearchNeed.NONE
        and not selected_capability_ids
        and not requested_provider
    ):
        kind = RouteKind.DIRECT
        status = RouteStatus.NO_SPECIAL_ROUTE
        fallback = None
        non_activation_reasons.extend(("trivial-local-scope", "specialist-cost-exceeds-benefit"))
    elif unresolved_tuple and any(
        item in unresolved_tuple
        for item in (
            "PROVIDER_REJECTED",
            "PROVIDER_DEPRECATED",
            "CAPABILITY_REJECTED",
            "CAPABILITY_DEPRECATED",
        )
    ):
        kind = RouteKind.DEGRADED
        status = RouteStatus.REJECTED
        fallback = None
    elif unresolved_tuple and (
        normalized.confidence is Confidence.UNKNOWN or high_material_unknown
    ):
        kind = RouteKind.DEGRADED
        status = RouteStatus.CONDITIONAL
        fallback = "inspect-and-clarify-before-material-action"
    elif unresolved_tuple and any(
        item in unresolved_tuple
        for item in ("PROVIDER_SCOPE_MISMATCH", "CAPABILITY_SCOPE_MISMATCH")
    ):
        kind = RouteKind.DEGRADED
        status = RouteStatus.REJECTED
        fallback = None
    elif fallback_allowed:
        kind = RouteKind.DEGRADED
        status = RouteStatus.FALLBACK
        fallback = "direct-with-focused-verification"
        if not non_activation_reasons:
            non_activation_reasons.append("minimum-specialist-route-unavailable")
    else:
        kind = RouteKind.DEGRADED
        status = RouteStatus.BLOCKED
        fallback = None
        unresolved_tuple = _dedupe((*unresolved_tuple, "NO_SAFE_FALLBACK"))

    route_confidence = normalized.confidence
    if route_confidence is Confidence.UNKNOWN:
        route_confidence = Confidence.LOW
    if unresolved_tuple and route_confidence is Confidence.HIGH:
        route_confidence = Confidence.MEDIUM if normalized.evidence.refs else Confidence.LOW
    gates: list[str] = ["route-validation"]
    if status is not RouteStatus.NO_SPECIAL_ROUTE:
        gates.append("authorization")
    if requires_verification:
        gates.append("verification")
    parallelism = max(selected_policy.default_parallelism_budget, len(selected))
    native = tuple(
        native_tools
        if native_tools is not None
        else (*selected_policy.native_tools, *available_tools)
    )
    providers = tuple(provider_constraints) or selected_policy.provider_constraints
    alternatives = ["DIRECT", "SPECIALIST", "COMPOSED", "PROVIDER", "DEGRADED"]
    return RouteDecision(
        schema_version=SchemaVersion.ROUTE_DECISION,
        decision_id=decision_key,
        task_id=normalized.task_id,
        run_id=normalized.run_id,
        record=_record(normalized, profile_ref, created),
        profile_ref=profile_ref,
        route_status=status,
        route_kind=kind,
        decision=RouteDecisionDetails(
            precedence_rule_ids=(
                "SAFETY-FIRST",
                "EXPLICIT-REQUEST-CONSIDERED",
                "MINIMUM-ROUTE",
                "NO-OVERACTIVATION",
            ),
            activation_reasons=_dedupe(activation_reasons),
            non_activation_reasons=_dedupe(non_activation_reasons),
            alternatives_considered=tuple(alternatives),
        ),
        compatibility=RouteCompatibility(
            native_tools_considered=_dedupe(native),
            provider_constraints=_dedupe(providers),
            conflicts_checked=tuple(item.capability_id for item in selected),
        ),
        budget=RouteBudget(None, None, parallelism),
        context_budget=ContextBudget(
            selected_policy.max_skill_kernels, selected_policy.max_reference_pack
        ),
        confidence=route_confidence,
        authority_ref=auth_key,
        created_at=created,
        selected=tuple(selected),
        optional=tuple(optional),
        omitted=tuple(omitted),
        quality_gates=_dedupe(gates),
        fallback=fallback,
        unresolved=unresolved_tuple,
    )


route = minimum_route
route_task = minimum_route
minimum_route_policy = minimum_route
