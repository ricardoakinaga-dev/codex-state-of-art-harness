from __future__ import annotations

import pytest
from test_phase6_models import make_input

from harness_kernel.phase6_models import (
    ProcedureSpec,
    ReadOnlyPolicy,
    VerificationProfile,
    VerificationRole,
)
from harness_kernel.phase6_policy import (
    activation_decision,
    profile_gates,
    profile_requires_reviewer,
    required_tools,
    validate_input_policy,
    validate_procedure_policy,
    validate_reviewer,
)


def test_profiles_have_explicit_gates_and_input_policy_is_read_only(tmp_path) -> None:
    verification_input = make_input(tmp_path)
    assert "criterion" in profile_gates(VerificationProfile.FOCUSED)
    assert "artifact" in profile_gates(VerificationProfile.STRUCTURAL)
    assert "reviewer" in profile_gates(VerificationProfile.VISUAL)
    assert validate_input_policy(verification_input) == ()
    assert verification_input.read_only_policy is ReadOnlyPolicy.READ_ONLY


def test_activation_is_refused_for_non_verifier_or_non_verification_work(tmp_path) -> None:
    verification_input = make_input(tmp_path)
    assert activation_decision(verification_input, requested=True) == "ACTIVATE"
    assert activation_decision(verification_input, requested=False) == "DO_NOT_ACTIVATE"
    with pytest.raises(ValueError):
        validate_reviewer(
            verifier=verification_input,
            reviewer_id=verification_input.capability_id,
            reviewer_role=VerificationRole.REVIEWER,
        )
    with pytest.raises(ValueError):
        validate_reviewer(
            verifier=verification_input,
            reviewer_id="independent-reviewer",
            reviewer_role=VerificationRole.VERIFIER,
        )


def test_policy_rejects_mutating_tools_and_authority_collisions(tmp_path) -> None:
    verification_input = make_input(tmp_path)
    object.__setattr__(verification_input, "allowed_tools", ("shell",))
    with pytest.raises(ValueError):
        validate_input_policy(verification_input)
    object.__setattr__(verification_input, "allowed_tools", ("mystery-tool",))
    with pytest.raises(ValueError):
        validate_input_policy(verification_input)
    object.__setattr__(verification_input, "allowed_tools", ("render-observer",))
    assert validate_input_policy(verification_input) == ()
    object.__setattr__(verification_input, "allowed_tools", ())
    object.__setattr__(verification_input, "role", VerificationRole.ASSURANCE)
    with pytest.raises(ValueError):
        validate_input_policy(verification_input)


def test_profile_input_rejects_criteria_mutation_and_unknown_profile(tmp_path) -> None:
    verification_input = make_input(tmp_path, profile=VerificationProfile.DOMAIN)
    assert verification_input.profile is VerificationProfile.DOMAIN
    with pytest.raises(ValueError):
        profile_gates("NOT-A-PROFILE")


def test_policy_exposes_reviewer_and_tool_requirements_and_rejects_bad_procedures(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    assert profile_requires_reviewer(VerificationProfile.VISUAL) is True
    assert profile_requires_reviewer(VerificationProfile.FOCUSED) is False
    assert required_tools(verification_input) == ()
    with pytest.raises(ValueError):
        validate_procedure_policy("not-a-procedure", verification_input)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        validate_reviewer(
            verifier=verification_input,
            reviewer_id="../escaped",
            reviewer_role=VerificationRole.REVIEWER,
        )
    with pytest.raises(ValueError):
        validate_procedure_policy(
            ProcedureSpec(
                procedure_id="PROC-UNSAFE",
                criterion_id="C-1",
                description="non-deterministic check",
                deterministic=False,
            ),
            verification_input,
        )
