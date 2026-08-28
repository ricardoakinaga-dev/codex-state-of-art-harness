"""Pure authority, scope and lifecycle-transition checks."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from .models import LifecycleState


class AuthorityAction(StrEnum):
    BLOCK = "BLOCK"
    RETRY = "RETRY"
    REPLAN = "REPLAN"
    FINALIZE = "FINALIZE"
    APPROVE = "APPROVE"
    TRANSITION = "TRANSITION"
    DOWNGRADE = "DOWNGRADE"

    def __str__(self) -> str:
        return self.value


DecisionAction = AuthorityAction


@dataclass(frozen=True, slots=True)
class AuthorityScope:
    """A bounded actor grant; it is not an external/system authority."""

    owner: str
    actor: str
    scopes: tuple[str, ...] = ()
    decisions: tuple[AuthorityAction | str, ...] = ()
    subject_owner: str | None = None
    human: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "scopes", _strings(self.scopes))
        object.__setattr__(self, "decisions", tuple(_action(item) for item in self.decisions))


ActorScope = AuthorityScope
OwnerScope = AuthorityScope


@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    """Declarative decision record that can be checked without applying it."""

    action: AuthorityAction | str
    owner: str
    actor: str
    scope: tuple[str, ...] = ()
    reason: str = ""
    task_id: str = ""
    decision_id: str = ""
    subject_owner: str | None = None
    target_state: LifecycleState | str | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", _action(self.action))
        object.__setattr__(self, "scope", _strings(self.scope))
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs))


@dataclass(frozen=True, slots=True)
class AuthorityCheck:
    allowed: bool
    code: str
    reason: str
    action: AuthorityAction | str
    actor: str
    owner: str
    required_scope: tuple[str, ...] = ()
    missing_scope: tuple[str, ...] = ()

    @property
    def authorized(self) -> bool:
        return self.allowed

    @property
    def ok(self) -> bool:
        return self.allowed


def _strings(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise TypeError("authority scopes and evidence references must be strings")
        value = value.strip()
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _action(value: AuthorityAction | str) -> AuthorityAction:
    if isinstance(value, AuthorityAction):
        return value
    if isinstance(value, str):
        try:
            return AuthorityAction(value.upper())
        except ValueError as exc:
            raise ValueError(f"unknown authority action: {value!r}") from exc
    raise TypeError("authority action must be an AuthorityAction or string")


def _state(value: LifecycleState | str) -> LifecycleState:
    if isinstance(value, LifecycleState):
        return value
    if isinstance(value, str):
        try:
            return LifecycleState(value.upper())
        except ValueError as exc:
            raise ValueError(f"unknown lifecycle state: {value!r}") from exc
    raise TypeError("lifecycle state must be a LifecycleState or string")


def _covers(granted: tuple[str, ...], requested: tuple[str, ...]) -> tuple[str, ...]:
    if not requested:
        return ()
    missing: list[str] = []
    for requirement in requested:
        covered = any(
            grant == "*"
            or grant == requirement
            or (grant.endswith(":*") and requirement.startswith(grant[:-1]))
            for grant in granted
        )
        if not covered:
            missing.append(requirement)
    return tuple(missing)


def check_decision(
    authority: AuthorityScope,
    action: AuthorityAction | str,
    *,
    required_scope: Iterable[str] = (),
    subject_owner: str | None = None,
    evidence_refs: Iterable[str] = (),
    human_required: bool = False,
) -> AuthorityCheck:
    """Check an action grant without changing state or performing the action."""

    if not isinstance(authority, AuthorityScope):
        raise TypeError("authority must be an AuthorityScope")
    requested_action = _action(action)
    required = _strings(required_scope)
    evidence = _strings(evidence_refs)
    if not authority.owner.strip() or not authority.actor.strip():
        return AuthorityCheck(
            False,
            "INVALID_ACTOR",
            "owner and actor are required",
            requested_action,
            authority.actor,
            authority.owner,
            required,
        )
    if not required:
        return AuthorityCheck(
            False,
            "MISSING_SCOPE",
            "every decision needs an explicit resource scope",
            requested_action,
            authority.actor,
            authority.owner,
            required,
        )
    missing = _covers(authority.scopes, required)
    if missing:
        return AuthorityCheck(
            False,
            "MISSING_SCOPE",
            "actor scope does not cover the requested resource",
            requested_action,
            authority.actor,
            authority.owner,
            required,
            missing,
        )
    if requested_action not in {_action(item) for item in authority.decisions}:
        return AuthorityCheck(
            False,
            "UNAUTHORIZED_DECISION",
            "actor is not granted this decision",
            requested_action,
            authority.actor,
            authority.owner,
            required,
        )
    subject = subject_owner or authority.subject_owner or authority.owner
    if (
        requested_action in (AuthorityAction.APPROVE, AuthorityAction.FINALIZE)
        and authority.actor == subject
    ):
        return AuthorityCheck(
            False,
            "SELF_APPROVAL",
            "an owner/builder cannot approve or finalize its own work",
            requested_action,
            authority.actor,
            authority.owner,
            required,
        )
    if requested_action in (AuthorityAction.FINALIZE, AuthorityAction.APPROVE) and not evidence:
        return AuthorityCheck(
            False,
            "MISSING_EVIDENCE",
            "approval/finalization needs current evidence references",
            requested_action,
            authority.actor,
            authority.owner,
            required,
        )
    if human_required and not authority.human:
        return AuthorityCheck(
            False,
            "HUMAN_AUTHORITY_REQUIRED",
            "this decision requires explicit human authority",
            requested_action,
            authority.actor,
            authority.owner,
            required,
        )
    return AuthorityCheck(
        True,
        "AUTHORIZED",
        "actor has the declared decision and scope",
        requested_action,
        authority.actor,
        authority.owner,
        required,
    )


def check_block(authority: AuthorityScope, *, required_scope: Iterable[str] = ()) -> AuthorityCheck:
    return check_decision(authority, AuthorityAction.BLOCK, required_scope=required_scope)


def check_retry(authority: AuthorityScope, *, required_scope: Iterable[str] = ()) -> AuthorityCheck:
    return check_decision(authority, AuthorityAction.RETRY, required_scope=required_scope)


def check_replan(
    authority: AuthorityScope, *, required_scope: Iterable[str] = ()
) -> AuthorityCheck:
    return check_decision(authority, AuthorityAction.REPLAN, required_scope=required_scope)


def check_finalize(
    authority: AuthorityScope,
    *,
    required_scope: Iterable[str] = (),
    evidence_refs: Iterable[str] = (),
    human_required: bool = False,
) -> AuthorityCheck:
    return check_decision(
        authority,
        AuthorityAction.FINALIZE,
        required_scope=required_scope,
        evidence_refs=evidence_refs,
        human_required=human_required,
    )


_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.NEW: frozenset({LifecycleState.CLASSIFIED, LifecycleState.BLOCKED}),
    LifecycleState.CLASSIFIED: frozenset({LifecycleState.ROUTED, LifecycleState.BLOCKED}),
    LifecycleState.ROUTED: frozenset({LifecycleState.PLANNED, LifecycleState.EXECUTING}),
    LifecycleState.PLANNED: frozenset({LifecycleState.EXECUTING, LifecycleState.BLOCKED}),
    LifecycleState.EXECUTING: frozenset(
        {
            LifecycleState.VERIFYING,
            LifecycleState.BLOCKED,
            LifecycleState.FAILED,
            LifecycleState.CANCELLED,
        }
    ),
    LifecycleState.VERIFYING: frozenset(
        {LifecycleState.REVIEWING, LifecycleState.REPAIRING, LifecycleState.FAILED}
    ),
    LifecycleState.REVIEWING: frozenset(
        {LifecycleState.REPAIRING, LifecycleState.ASSURING, LifecycleState.BLOCKED}
    ),
    LifecycleState.REPAIRING: frozenset({LifecycleState.VERIFYING, LifecycleState.FAILED}),
    LifecycleState.ASSURING: frozenset(
        {LifecycleState.PASSED, LifecycleState.PARTIAL, LifecycleState.BLOCKED}
    ),
    LifecycleState.BLOCKED: frozenset(
        {LifecycleState.ROUTED, LifecycleState.PLANNED, LifecycleState.FAILED}
    ),
    LifecycleState.FAILED: frozenset({LifecycleState.ROUTED}),
    LifecycleState.PARTIAL: frozenset({LifecycleState.REPAIRING, LifecycleState.DELIVERED}),
    LifecycleState.PASSED: frozenset({LifecycleState.DELIVERED}),
    LifecycleState.DELIVERED: frozenset(),
    LifecycleState.CANCELLED: frozenset(),
}


def _transition_action(current: LifecycleState, target: LifecycleState) -> AuthorityAction:
    if target is LifecycleState.BLOCKED:
        return AuthorityAction.BLOCK
    if current is LifecycleState.BLOCKED or current is LifecycleState.FAILED:
        return AuthorityAction.REPLAN
    if target is LifecycleState.DELIVERED:
        return AuthorityAction.FINALIZE
    return AuthorityAction.TRANSITION


def check_transition(
    current: LifecycleState | str,
    target: LifecycleState | str,
    authority: AuthorityScope,
    *,
    required_scope: Iterable[str] = (),
    evidence_refs: Iterable[str] = (),
    human_required: bool = False,
    action: AuthorityAction | str | None = None,
) -> AuthorityCheck:
    """Validate a documented lifecycle edge and the authority for that edge."""

    try:
        source, destination = _state(current), _state(target)
    except (TypeError, ValueError) as exc:
        return AuthorityCheck(
            False,
            "INVALID_STATE",
            str(exc),
            AuthorityAction.TRANSITION,
            authority.actor,
            authority.owner,
        )
    if destination not in _TRANSITIONS.get(source, frozenset()):
        chosen = _action(action) if action is not None else AuthorityAction.TRANSITION
        return AuthorityCheck(
            False,
            "INVALID_TRANSITION",
            "lifecycle edge is not declared by the state model",
            chosen,
            authority.actor,
            authority.owner,
            _strings(required_scope),
        )
    chosen_action = (
        _action(action) if action is not None else _transition_action(source, destination)
    )
    return check_decision(
        authority,
        chosen_action,
        required_scope=required_scope,
        evidence_refs=evidence_refs,
        human_required=human_required,
    )


def authorize_decision(
    decision: AuthorityDecision,
    authority: AuthorityScope | None = None,
    *,
    human_required: bool = False,
) -> AuthorityCheck:
    """Check a decision record against a grant; never apply it."""

    if not isinstance(decision, AuthorityDecision):
        raise TypeError("decision must be an AuthorityDecision")
    grant = authority or AuthorityScope(
        owner=decision.owner,
        actor=decision.actor,
        scopes=decision.scope,
        decisions=(decision.action,),
        subject_owner=decision.subject_owner,
    )
    return check_decision(
        grant,
        decision.action,
        required_scope=decision.scope,
        subject_owner=decision.subject_owner,
        evidence_refs=decision.evidence_refs,
        human_required=human_required,
    )


check_authority = check_decision
authorize = authorize_decision
can_block = check_block
can_retry = check_retry
can_replan = check_replan
can_finalize = check_finalize
validate_transition = check_transition
