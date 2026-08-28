from __future__ import annotations

from harness_kernel.authority import (
    AuthorityAction,
    AuthorityScope,
    check_decision,
    check_transition,
)
from harness_kernel.models import LifecycleState


def scope(*decisions: AuthorityAction | str, actor: str = "reviewer") -> AuthorityScope:
    return AuthorityScope(
        owner="builder",
        actor=actor,
        scopes=("task:TASK-1",),
        decisions=tuple(decisions),
    )


def test_block_retry_and_replan_require_declared_scope_and_power() -> None:
    authority = scope(AuthorityAction.BLOCK, AuthorityAction.RETRY, AuthorityAction.REPLAN)

    assert check_decision(authority, AuthorityAction.BLOCK, required_scope=("task:TASK-1",)).allowed
    assert check_decision(authority, AuthorityAction.RETRY, required_scope=("task:TASK-1",)).allowed
    assert check_decision(
        authority, AuthorityAction.REPLAN, required_scope=("task:TASK-1",)
    ).allowed

    missing = check_decision(authority, AuthorityAction.BLOCK, required_scope=("task:TASK-2",))
    assert not missing.allowed
    assert missing.code == "MISSING_SCOPE"


def test_finalize_rejects_self_approval_and_missing_evidence() -> None:
    authority = scope(AuthorityAction.FINALIZE, actor="builder")

    self_approval = check_decision(
        authority,
        AuthorityAction.FINALIZE,
        required_scope=("task:TASK-1",),
        evidence_refs=("EVID-1",),
    )
    no_evidence = check_decision(
        scope(AuthorityAction.FINALIZE),
        AuthorityAction.FINALIZE,
        required_scope=("task:TASK-1",),
    )

    assert not self_approval.allowed
    assert self_approval.code == "SELF_APPROVAL"
    assert not no_evidence.allowed
    assert no_evidence.code == "MISSING_EVIDENCE"


def test_unauthorized_and_invalid_lifecycle_transitions_are_rejected() -> None:
    authority = scope(AuthorityAction.REPLAN, AuthorityAction.FINALIZE)

    allowed = check_transition(
        LifecycleState.BLOCKED,
        LifecycleState.ROUTED,
        authority,
        required_scope=("task:TASK-1",),
    )
    invalid = check_transition(
        LifecycleState.NEW,
        LifecycleState.DELIVERED,
        authority,
        required_scope=("task:TASK-1",),
    )

    assert allowed.allowed
    assert not invalid.allowed
    assert invalid.code == "INVALID_TRANSITION"


def test_transition_out_of_scope_is_not_authorized_even_when_edge_is_valid() -> None:
    result = check_transition(
        LifecycleState.NEW,
        LifecycleState.CLASSIFIED,
        scope(AuthorityAction.REPLAN),
        required_scope=("task:TASK-2",),
    )

    assert not result.allowed
    assert result.code == "MISSING_SCOPE"
