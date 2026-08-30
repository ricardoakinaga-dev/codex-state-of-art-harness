"""Pure activation, profile and authority policy for the Phase 6 verifier."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from .phase6_models import (
    ProcedureSpec,
    ReadOnlyPolicy,
    VerificationInput,
    VerificationProfile,
    VerificationRole,
    canonical_json,
)


class Phase6PolicyError(ValueError):
    """Raised when a Phase 6 policy boundary cannot be satisfied."""


class ActivationDecision(StrEnum):
    ACTIVATE = "ACTIVATE"
    DO_NOT_ACTIVATE = "DO_NOT_ACTIVATE"
    BLOCKED = "BLOCKED"


PROFILE_GATES: Mapping[VerificationProfile, tuple[str, ...]] = {
    VerificationProfile.FOCUSED: ("criterion", "procedure", "evidence"),
    VerificationProfile.DOMAIN: ("criterion", "procedure", "evidence", "domain"),
    VerificationProfile.FULL: ("criterion", "procedure", "evidence", "full-selected-suite"),
    VerificationProfile.VISUAL: ("criterion", "artifact", "render", "reviewer"),
    VerificationProfile.STRUCTURAL: ("criterion", "artifact", "schema", "runtime"),
    VerificationProfile.SECURITY_AWARE: (
        "criterion",
        "artifact",
        "trust-boundary",
        "read-only",
    ),
    VerificationProfile.COMPOSITION: (
        "criterion",
        "artifact",
        "evidence",
        "handoff",
        "reviewer",
    ),
}

# These are the profile-local ceilings from the project-local capability
# contract.  The global VerificationBudget remains the hard upper bound.
PROFILE_LIMITS: Mapping[VerificationProfile, tuple[int, int, int]] = {
    VerificationProfile.FOCUSED: (8, 8, 16_384),
    VerificationProfile.DOMAIN: (16, 16, 32_768),
    VerificationProfile.FULL: (64, 32, 65_536),
    VerificationProfile.VISUAL: (16, 16, 32_768),
    VerificationProfile.STRUCTURAL: (32, 24, 49_152),
    VerificationProfile.SECURITY_AWARE: (32, 32, 65_536),
    VerificationProfile.COMPOSITION: (32, 32, 65_536),
}

_FORBIDDEN_TOOL_WORDS = frozenset(
    {
        "shell",
        "subprocess",
        "network",
        "http",
        "mcp",
        "provider",
        "credential",
        "secret",
        "write",
        "mutate",
    }
)
_ALLOWED_TOOL_NAMES = frozenset({"render-observer"})


def profile_gates(profile: VerificationProfile | str) -> tuple[str, ...]:
    try:
        selected = (
            profile if isinstance(profile, VerificationProfile) else VerificationProfile(profile)
        )
    except ValueError as exc:
        raise Phase6PolicyError("unknown verification profile") from exc
    return PROFILE_GATES[selected]


def profile_limits(profile: VerificationProfile | str) -> tuple[int, int, int]:
    try:
        selected = (
            profile if isinstance(profile, VerificationProfile) else VerificationProfile(profile)
        )
    except ValueError as exc:
        raise Phase6PolicyError("unknown verification profile") from exc
    return PROFILE_LIMITS[selected]


def validate_input_policy(verification_input: VerificationInput) -> tuple[str, ...]:
    """Validate the authority and tool boundary without changing the input."""

    if not isinstance(verification_input, VerificationInput):
        raise Phase6PolicyError("verification input is invalid")
    if verification_input.role is not VerificationRole.VERIFIER:
        raise Phase6PolicyError("Phase 6 input role must be VERIFIER")
    if verification_input.scope != "PROJECT":
        raise Phase6PolicyError("Phase 6 scope must be PROJECT")
    if verification_input.authority != "VERIFIER":
        raise Phase6PolicyError("Phase 6 authority must be VERIFIER")
    if not verification_input.read_only or verification_input.read_only_policy not in {
        ReadOnlyPolicy.READ_ONLY,
        ReadOnlyPolicy.MUTATION_DENIED,
    }:
        raise Phase6PolicyError("Phase 6 policy is read-only only")
    invalid = tuple(
        tool
        for tool in verification_input.allowed_tools
        if tool not in _ALLOWED_TOOL_NAMES
        or any(word in tool.casefold() for word in _FORBIDDEN_TOOL_WORDS)
    )
    if invalid:
        raise Phase6PolicyError("tool is not in the read-only allowlisted vocabulary")
    if len(set(verification_input.allowed_tools)) != len(verification_input.allowed_tools):
        raise Phase6PolicyError("allowed tools must be unique")
    profile_gates(verification_input.profile)
    max_criteria, _, max_reference_bytes = profile_limits(verification_input.profile)
    if len(verification_input.required_criteria) > max_criteria:
        raise Phase6PolicyError("required criteria exceed the selected profile budget")
    if len(verification_input.required_criteria) > verification_input.budgets.max_criteria:
        raise Phase6PolicyError("required criteria exceed the policy budget")
    reference_bytes = len(canonical_json(verification_input.evidence_refs).encode("utf-8"))
    if reference_bytes > max_reference_bytes:
        raise Phase6PolicyError("evidence references exceed the selected profile budget")
    return ()


def validate_procedure_policy(
    procedure: ProcedureSpec, verification_input: VerificationInput
) -> tuple[str, ...]:
    if not isinstance(procedure, ProcedureSpec):
        raise Phase6PolicyError("procedure spec is invalid")
    validate_input_policy(verification_input)
    if not procedure.deterministic:
        raise Phase6PolicyError("procedures must be deterministic")
    if not procedure.read_only:
        raise Phase6PolicyError("procedures must be read-only")
    if (
        procedure.required_tool is not None
        and procedure.required_tool not in verification_input.allowed_tools
    ):
        raise Phase6PolicyError("procedure requires a tool outside the allowlist")
    if procedure.criterion_id not in verification_input.required_criteria:
        raise Phase6PolicyError("procedure criterion is not required by the input")
    return ()


def validate_reviewer(
    *, verifier: VerificationInput, reviewer_id: str, reviewer_role: VerificationRole | str
) -> tuple[str, str]:
    if not isinstance(verifier, VerificationInput):
        raise Phase6PolicyError("verifier input is invalid")
    try:
        role = (
            reviewer_role
            if isinstance(reviewer_role, VerificationRole)
            else VerificationRole(reviewer_role)
        )
    except ValueError as exc:
        raise Phase6PolicyError("reviewer role is invalid") from exc
    if role is not VerificationRole.REVIEWER:
        raise Phase6PolicyError("reviewer must have the REVIEWER role")
    if not isinstance(reviewer_id, str) or not reviewer_id or reviewer_id == verifier.capability_id:
        raise Phase6PolicyError("reviewer must be identified independently")
    if "\x00" in reviewer_id or ".." in reviewer_id.replace("\\", "/").split("/"):
        raise Phase6PolicyError("reviewer identity is malformed")
    producer_ids = {
        item.producer_id for item in verifier.artifact_refs if item.producer_id is not None
    }
    if reviewer_id in producer_ids:
        raise Phase6PolicyError("reviewer cannot be the artifact producer")
    return reviewer_id, role.value


def activation_decision(
    verification_input: VerificationInput | None, *, requested: bool = True
) -> ActivationDecision:
    if not requested:
        return ActivationDecision.DO_NOT_ACTIVATE
    if verification_input is None:
        return ActivationDecision.BLOCKED
    try:
        validate_input_policy(verification_input)
    except Phase6PolicyError:
        return ActivationDecision.BLOCKED
    return ActivationDecision.ACTIVATE


def profile_requires_reviewer(profile: VerificationProfile | str) -> bool:
    return "reviewer" in profile_gates(profile)


def required_tools(verification_input: VerificationInput) -> tuple[str, ...]:
    """Return the declared tools; policy never invents an implicit tool."""

    validate_input_policy(verification_input)
    return verification_input.allowed_tools


# Short aliases make Phase 3/4 adapters convenient without changing policy.
check_input_policy = validate_input_policy
activation_allowed = activation_decision
