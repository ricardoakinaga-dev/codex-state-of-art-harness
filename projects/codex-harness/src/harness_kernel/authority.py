"""Pure authority, scope and lifecycle-transition checks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
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
    operations: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    delegation_chain: tuple[str, ...] = ()
    subject_type: str = "INVOCATION"
    subject_id: str | None = None
    issued_at: str | None = None
    expires_at: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.owner, str) or not self.owner.strip():
            raise ValueError("authority owner is required")
        if not isinstance(self.actor, str) or not self.actor.strip():
            raise ValueError("authority actor is required")
        if not isinstance(self.subject_type, str) or not self.subject_type.strip():
            raise ValueError("authority subject type is required")
        object.__setattr__(self, "scopes", _strings(self.scopes))
        object.__setattr__(self, "decisions", tuple(_action(item) for item in self.decisions))
        object.__setattr__(self, "operations", _strings(self.operations))
        object.__setattr__(self, "conditions", _strings(self.conditions))
        object.__setattr__(self, "delegation_chain", _strings(self.delegation_chain))
        object.__setattr__(self, "subject_type", self.subject_type.strip().upper())
        if self.subject_id is not None:
            if not isinstance(self.subject_id, str) or not self.subject_id.strip():
                raise ValueError("authority subject id must be a non-empty string")
            object.__setattr__(self, "subject_id", self.subject_id.strip())


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


@dataclass(frozen=True, slots=True)
class AuthoritySnapshot:
    """The exact effective authority used for one invocation."""

    authority_id: str
    subject_type: str
    subject_id: str
    owner: str
    actor: str
    operation: str
    scopes: tuple[str, ...]
    conditions: tuple[str, ...]
    delegation_chain: tuple[str, ...]
    issued_at: str | None
    expires_at: str | None
    digest: str
    required_scope: tuple[str, ...] = ()


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


def _timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("authority timestamps must be zoned ISO-8601 strings")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("authority timestamps must include a timezone")
    return parsed


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


def check_invocation_authority(
    authority: AuthorityScope,
    *,
    task_id: str,
    invocation_id: str,
    capability_id: str,
    operation: str,
    required_scope: Iterable[str],
    at: str,
    required_conditions: Iterable[str] = (),
    delegation_ref: str | None = None,
) -> AuthorityCheck:
    """Check operation/subject/expiry authority before a provider is called."""

    if not isinstance(authority, AuthorityScope):
        raise TypeError("authority must be an AuthorityScope")
    requested_scope = _strings(required_scope)
    if any(
        not isinstance(value, str) or not value.strip()
        for value in (task_id, invocation_id, capability_id)
    ):
        return AuthorityCheck(
            False,
            "INVALID_SUBJECT",
            "invocation subject is incomplete",
            AuthorityAction.TRANSITION,
            authority.actor,
            authority.owner,
            requested_scope,
        )
    if not isinstance(operation, str) or not operation.strip():
        return AuthorityCheck(
            False,
            "MISSING_OPERATION",
            "invocation operation is required",
            AuthorityAction.TRANSITION,
            authority.actor,
            authority.owner,
            requested_scope,
        )
    if authority.subject_type != "INVOCATION":
        return AuthorityCheck(
            False,
            "INVALID_SUBJECT_TYPE",
            "invocation authority must target an invocation subject",
            AuthorityAction.TRANSITION,
            authority.actor,
            authority.owner,
            requested_scope,
        )
    try:
        observed_at = _timestamp(at)
        issued_at = _timestamp(authority.issued_at)
        expires_at = _timestamp(authority.expires_at)
    except (TypeError, ValueError):
        return AuthorityCheck(
            False,
            "INVALID_AUTHORITY_TIME",
            "authority timestamp is invalid",
            AuthorityAction.TRANSITION,
            authority.actor,
            authority.owner,
            requested_scope,
        )
    assert observed_at is not None
    if issued_at is not None and observed_at < issued_at:
        return AuthorityCheck(
            False,
            "AUTHORITY_NOT_YET_VALID",
            "authority is not effective at invocation time",
            AuthorityAction.TRANSITION,
            authority.actor,
            authority.owner,
            requested_scope,
        )
    if expires_at is not None and observed_at >= expires_at:
        return AuthorityCheck(
            False,
            "AUTHORITY_EXPIRED",
            "authority expired before invocation",
            AuthorityAction.TRANSITION,
            authority.actor,
            authority.owner,
            requested_scope,
        )
    if authority.subject_id is not None and authority.subject_id != invocation_id:
        return AuthorityCheck(
            False,
            "AUTHORITY_SUBJECT_MISMATCH",
            "authority subject does not match invocation",
            AuthorityAction.TRANSITION,
            authority.actor,
            authority.owner,
            requested_scope,
        )
    if authority.operations and operation not in authority.operations:
        return AuthorityCheck(
            False,
            "UNAUTHORIZED_OPERATION",
            "operation is outside the authority grant",
            AuthorityAction.TRANSITION,
            authority.actor,
            authority.owner,
            requested_scope,
        )
    if not authority.operations:
        return AuthorityCheck(
            False,
            "MISSING_OPERATION_GRANT",
            "authority has no operation grant",
            AuthorityAction.TRANSITION,
            authority.actor,
            authority.owner,
            requested_scope,
        )
    base = check_decision(
        authority,
        AuthorityAction.TRANSITION,
        required_scope=requested_scope,
    )
    if not base.allowed:
        return base
    missing_conditions = _covers(authority.conditions, _strings(required_conditions))
    if missing_conditions:
        return AuthorityCheck(
            False,
            "AUTHORITY_CONDITION_UNMET",
            "authority conditions are not satisfied",
            AuthorityAction.TRANSITION,
            authority.actor,
            authority.owner,
            requested_scope,
            missing_conditions,
        )
    if delegation_ref is not None and delegation_ref not in authority.delegation_chain:
        return AuthorityCheck(
            False,
            "DELEGATION_MISSING",
            "required delegation is not in the authority chain",
            AuthorityAction.TRANSITION,
            authority.actor,
            authority.owner,
            requested_scope,
        )
    return AuthorityCheck(
        True,
        "AUTHORIZED",
        "operation, subject, scope and expiry are authorized",
        AuthorityAction.TRANSITION,
        authority.actor,
        authority.owner,
        requested_scope,
    )


def authority_snapshot(
    authority: AuthorityScope,
    *,
    subject_id: str,
    operation: str,
    authority_id: str = "AUTH-SNAPSHOT",
    required_scope: Iterable[str] = (),
) -> AuthoritySnapshot:
    """Capture a canonical, hashable authority snapshot for evidence."""

    if authority.subject_type != "INVOCATION":
        raise ValueError("invocation authority snapshot has an invalid subject type")
    if (
        not isinstance(subject_id, str)
        or not subject_id.strip()
        or not isinstance(operation, str)
        or not operation.strip()
    ):
        raise ValueError("authority snapshot subject and operation are required")
    requested_scope = _strings(required_scope)
    values = {
        "authority_id": authority_id,
        "subject_type": authority.subject_type,
        "subject_id": subject_id,
        "owner": authority.owner,
        "actor": authority.actor,
        "operation": operation,
        "scopes": list(authority.scopes),
        "conditions": list(authority.conditions),
        "delegation_chain": list(authority.delegation_chain),
        "issued_at": authority.issued_at,
        "expires_at": authority.expires_at,
        "required_scope": list(requested_scope),
    }
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return AuthoritySnapshot(
        authority_id=authority_id,
        subject_type=authority.subject_type,
        subject_id=subject_id,
        owner=authority.owner,
        actor=authority.actor,
        operation=operation,
        scopes=authority.scopes,
        conditions=authority.conditions,
        delegation_chain=authority.delegation_chain,
        issued_at=authority.issued_at,
        expires_at=authority.expires_at,
        digest=f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        required_scope=requested_scope,
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
    if authority is None:
        return AuthorityCheck(
            False,
            "AUTHORITY_REQUIRED",
            "an explicit authority grant is required",
            _action(decision.action),
            decision.actor,
            decision.owner,
            _strings(decision.scope),
        )
    grant = authority
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
