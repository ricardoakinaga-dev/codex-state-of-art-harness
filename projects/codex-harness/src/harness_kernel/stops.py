"""Declarative stop-condition detection with immutable loop observations."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .models import Confidence, StopRecommendation


class StopCondition(StrEnum):
    MAX_ITERATIONS = "MAX_ITERATIONS"
    NO_PROGRESS = "NO_PROGRESS"
    REPEATED_FAILURE = "REPEATED_FAILURE"
    OSCILLATION = "OSCILLATION"
    BUDGET_EXHAUSTION = "BUDGET_EXHAUSTION"
    MISSING_TOOL = "MISSING_TOOL"
    BLOCKED_DEPENDENCY = "BLOCKED_DEPENDENCY"
    HUMAN_OVERRIDE = "HUMAN_OVERRIDE"
    ACCEPTABLE_RESIDUAL_RISK = "ACCEPTABLE_RESIDUAL_RISK"


@dataclass(frozen=True, slots=True)
class StopBudget:
    max_iterations: int | None = None
    max_tokens: int | None = None
    max_duration_ms: int | None = None
    max_tool_calls: int | None = None
    max_cost: float | None = None
    max_context_tokens: int | None = None

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_iterations,
            self.max_tokens,
            self.max_duration_ms,
            self.max_tool_calls,
            self.max_context_tokens,
        )
        if any(
            value is not None
            and (not isinstance(value, int) or isinstance(value, bool) or value < 0)
            for value in integer_limits
        ):
            raise ValueError("stop budgets must be non-negative integers")
        if self.max_cost is not None and self.max_cost < 0:
            raise ValueError("stop cost budget must be non-negative")


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    iterations: int = 0
    tokens: int = 0
    duration_ms: int = 0
    tool_calls: int = 0
    cost: float = 0.0
    context_tokens: int = 0

    def __post_init__(self) -> None:
        integer_usage = (
            self.iterations,
            self.tokens,
            self.duration_ms,
            self.tool_calls,
            self.context_tokens,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in integer_usage
        ):
            raise ValueError("budget usage must be non-negative integers")
        if self.cost < 0:
            raise ValueError("budget cost usage must be non-negative")


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    iteration: int
    criteria: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "criteria", tuple(self.criteria))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "artifact_refs", tuple(self.artifact_refs))

    @property
    def signature(self) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        return (self.criteria, self.evidence_refs, self.artifact_refs)


@dataclass(frozen=True, slots=True)
class FailureObservation:
    cause: str
    input_fingerprint: str = ""
    criterion: str = ""

    @property
    def signature(self) -> tuple[str, str, str]:
        return (self.cause, self.input_fingerprint, self.criterion)


@dataclass(frozen=True, slots=True)
class StopDecision:
    condition: StopCondition | None
    recommendation: StopRecommendation
    reason: str
    observed_after: int
    last_progress: str | None = None
    unresolved_gaps: tuple[str, ...] = ()
    owner: str | None = None
    confidence: Confidence = Confidence.HIGH

    @property
    def should_stop(self) -> bool:
        return self.condition is not None


def _signature(value: Any) -> Any:
    if isinstance(value, ProgressSnapshot):
        return value.signature
    if isinstance(value, FailureObservation):
        return value.signature
    if isinstance(value, (list, tuple)):
        return tuple(_signature(item) for item in value)
    return value


def detect_no_progress(history: Sequence[ProgressSnapshot | Any], window: int = 2) -> bool:
    """Detect consecutive rounds with unchanged criterion/evidence/artifact state."""

    if window < 2 or len(history) < window:
        return False
    signatures = tuple(_signature(item) for item in history[-window:])
    return all(signature == signatures[0] for signature in signatures[1:])


def detect_repeated_failure(
    failures: Sequence[FailureObservation | Any], threshold: int = 2
) -> bool:
    """Detect the same cause/input failure repeated consecutively."""

    if threshold < 2 or len(failures) < threshold:
        return False
    signatures = tuple(_signature(item) for item in failures[-threshold:])
    return all(signature == signatures[0] for signature in signatures[1:])


def detect_oscillation(history: Sequence[Any], cycles: int = 2, period: int = 2) -> bool:
    """Detect a repeating A/B-style fix-and-regress sequence."""

    if cycles < 2 or period < 2 or len(history) < cycles * period:
        return False
    signatures = tuple(_signature(item) for item in history[-cycles * period :])
    pattern = signatures[:period]
    return all(
        signatures[offset : offset + period] == pattern
        for offset in range(0, len(signatures), period)
    )


def _decision(
    condition: StopCondition,
    reason: str,
    observed_after: int,
    *,
    last_progress: str | None = None,
    gaps: Iterable[str] = (),
    owner: str | None = None,
    recommendation: StopRecommendation | None = None,
) -> StopDecision:
    recommendations = {
        StopCondition.MAX_ITERATIONS: StopRecommendation.STOP,
        StopCondition.NO_PROGRESS: StopRecommendation.REPAIR,
        StopCondition.REPEATED_FAILURE: StopRecommendation.REPAIR,
        StopCondition.OSCILLATION: StopRecommendation.REPAIR,
        StopCondition.BUDGET_EXHAUSTION: StopRecommendation.STOP,
        StopCondition.MISSING_TOOL: StopRecommendation.ESCALATE,
        StopCondition.BLOCKED_DEPENDENCY: StopRecommendation.ESCALATE,
        StopCondition.HUMAN_OVERRIDE: StopRecommendation.STOP,
        StopCondition.ACCEPTABLE_RESIDUAL_RISK: StopRecommendation.STOP,
    }
    return StopDecision(
        condition=condition,
        recommendation=recommendation or recommendations[condition],
        reason=reason,
        observed_after=observed_after,
        last_progress=last_progress,
        unresolved_gaps=tuple(gaps),
        owner=owner,
    )


def evaluate_stop(
    *,
    iteration: int | None = None,
    budget: StopBudget | None = None,
    usage: BudgetUsage | None = None,
    progress_history: Sequence[ProgressSnapshot | Any] = (),
    failure_history: Sequence[FailureObservation | Any] = (),
    missing_tools: Iterable[str] = (),
    blocked_dependencies: Iterable[str] = (),
    human_override: str | bool | None = None,
    required_passed: bool = False,
    current_evidence: bool = False,
    artifact_integrated: bool = False,
    residual_risk_acceptable: bool = False,
    no_progress_window: int = 2,
    repeated_failure_threshold: int = 2,
    oscillation_cycles: int = 2,
) -> StopDecision:
    """Evaluate stop conditions in a deterministic, safety-first order."""

    selected_budget = budget or StopBudget()
    selected_usage = usage or BudgetUsage()
    observed_after = (
        iteration
        if iteration is not None
        else max(selected_usage.iterations, len(progress_history))
    )
    if human_override:
        return _decision(
            StopCondition.HUMAN_OVERRIDE, "human override requested", observed_after, owner="human"
        )
    if (
        selected_budget.max_iterations is not None
        and observed_after >= selected_budget.max_iterations
    ):
        return _decision(
            StopCondition.MAX_ITERATIONS,
            "maximum iterations reached",
            observed_after,
            owner="orchestrator",
        )
    budget_exhausted = (
        (
            selected_budget.max_tokens is not None
            and selected_usage.tokens >= selected_budget.max_tokens
        )
        or (
            selected_budget.max_duration_ms is not None
            and selected_usage.duration_ms >= selected_budget.max_duration_ms
        )
        or (
            selected_budget.max_tool_calls is not None
            and selected_usage.tool_calls >= selected_budget.max_tool_calls
        )
        or (
            selected_budget.max_cost is not None and selected_usage.cost >= selected_budget.max_cost
        )
        or (
            selected_budget.max_context_tokens is not None
            and selected_usage.context_tokens >= selected_budget.max_context_tokens
        )
    )
    if budget_exhausted:
        return _decision(
            StopCondition.BUDGET_EXHAUSTION,
            "resource budget exhausted",
            observed_after,
            owner="authority",
        )
    missing = tuple(sorted({tool for tool in missing_tools if tool}))
    if missing:
        return _decision(
            StopCondition.MISSING_TOOL,
            "required tool is unavailable",
            observed_after,
            gaps=missing,
            owner="router",
        )
    blocked = tuple(sorted({dependency for dependency in blocked_dependencies if dependency}))
    if blocked:
        return _decision(
            StopCondition.BLOCKED_DEPENDENCY,
            "required dependency is blocked",
            observed_after,
            gaps=blocked,
            owner="orchestrator",
        )
    if detect_no_progress(progress_history, no_progress_window):
        last = _signature(progress_history[-1]) if progress_history else None
        return _decision(
            StopCondition.NO_PROGRESS,
            "progress window did not change",
            observed_after,
            last_progress=repr(last),
            owner="assurance",
        )
    if detect_repeated_failure(failure_history, repeated_failure_threshold):
        return _decision(
            StopCondition.REPEATED_FAILURE,
            "same failure repeated",
            observed_after,
            owner="assurance",
        )
    if detect_oscillation(progress_history, oscillation_cycles):
        return _decision(
            StopCondition.OSCILLATION,
            "progress alternates between repeated states",
            observed_after,
            owner="integrator",
        )
    if required_passed and current_evidence and artifact_integrated and residual_risk_acceptable:
        return _decision(
            StopCondition.ACCEPTABLE_RESIDUAL_RISK,
            "required scope passed with acceptable residual risk",
            observed_after,
            owner="assurance",
        )
    return StopDecision(
        condition=None,
        recommendation=StopRecommendation.CONTINUE,
        reason="no stop condition satisfied",
        observed_after=observed_after,
    )


@dataclass(frozen=True, slots=True)
class StopEngine:
    budget: StopBudget = StopBudget()
    progress_history: tuple[ProgressSnapshot, ...] = ()
    failure_history: tuple[FailureObservation, ...] = ()

    def record_progress(self, snapshot: ProgressSnapshot) -> StopEngine:
        return StopEngine(
            budget=self.budget,
            progress_history=(*self.progress_history, snapshot),
            failure_history=self.failure_history,
        )

    def record_failure(self, failure: FailureObservation) -> StopEngine:
        return StopEngine(
            budget=self.budget,
            progress_history=self.progress_history,
            failure_history=(*self.failure_history, failure),
        )

    def evaluate(self, **kwargs: Any) -> StopDecision:
        return evaluate_stop(
            budget=self.budget,
            progress_history=self.progress_history,
            failure_history=self.failure_history,
            **kwargs,
        )

    def should_stop(self, **kwargs: Any) -> bool:
        return self.evaluate(**kwargs).should_stop


Budgets = StopBudget
StopReason = StopCondition
