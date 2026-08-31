"""Bounded, deterministic stop decisions for Phase 6 verification runs."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .phase6_models import (
    CriterionResult,
    FreshnessStatus,
    StopCondition,
    VerificationInput,
    VerificationStatus,
    digest_payload,
)


@dataclass(frozen=True, slots=True)
class StopDecision:
    condition: StopCondition | str | None
    reason: str
    unresolved_criteria: tuple[str, ...] = ()
    missing_tools: tuple[str, ...] = ()
    missing_artifacts: tuple[str, ...] = ()
    observed_procedures: int = 0
    observed_evidence: int = 0
    run_id: str | None = None
    task_id: str | None = None
    input_digest: str | None = None
    should_stop: bool = field(init=False)
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.condition, str) and not isinstance(self.condition, StopCondition):
            object.__setattr__(self, "condition", StopCondition(self.condition))
        if self.condition is not None and not isinstance(self.condition, StopCondition):
            raise ValueError("stop condition is invalid")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("stop reason is required")
        object.__setattr__(self, "unresolved_criteria", tuple(self.unresolved_criteria))
        object.__setattr__(self, "missing_tools", tuple(self.missing_tools))
        object.__setattr__(self, "missing_artifacts", tuple(self.missing_artifacts))
        if (
            not isinstance(self.observed_procedures, int)
            or isinstance(self.observed_procedures, bool)
            or not isinstance(self.observed_evidence, int)
            or isinstance(self.observed_evidence, bool)
            or self.observed_procedures < 0
            or self.observed_evidence < 0
        ):
            raise ValueError("stop observations must be non-negative")
        if (self.run_id is None) != (self.task_id is None) or (self.input_digest is None) != (
            self.run_id is None
        ):
            raise ValueError("stop decision identity fields must be complete")
        for name, value in (("run_id", self.run_id), ("task_id", self.task_id)):
            if value is not None and (
                not isinstance(value, str)
                or not value
                or "\x00" in value
                or ".." in value.replace("\\", "/").split("/")
            ):
                raise ValueError(f"stop decision {name} is invalid")
        if self.input_digest is not None and (
            not isinstance(self.input_digest, str)
            or len(self.input_digest) != 71
            or not self.input_digest.startswith("sha256:")
            or any(char not in "0123456789abcdef" for char in self.input_digest[7:])
        ):
            raise ValueError("stop decision input_digest is invalid")
        object.__setattr__(self, "should_stop", self.condition is not None)
        object.__setattr__(
            self,
            "digest",
            digest_payload(
                {
                    "condition": self.condition,
                    "reason": self.reason,
                    "unresolved_criteria": self.unresolved_criteria,
                    "missing_tools": self.missing_tools,
                    "missing_artifacts": self.missing_artifacts,
                    "observed_procedures": self.observed_procedures,
                    "observed_evidence": self.observed_evidence,
                    "run_id": self.run_id,
                    "task_id": self.task_id,
                    "input_digest": self.input_digest,
                    "should_stop": self.should_stop,
                }
            ),
        )


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value and value not in result:
            result.append(value)
    return tuple(result)


def _signature(result: CriterionResult) -> tuple[str, str, tuple[str, ...]]:
    return (
        result.criterion_id,
        result.status.value,
        tuple(item.evidence_id for item in result.evidence),
    )


def _decision(
    verification_input: VerificationInput,
    condition: StopCondition | None,
    reason: str,
    unresolved: tuple[str, ...],
    tools: tuple[str, ...],
    artifacts: tuple[str, ...],
    observed_procedures: int,
    observed_evidence: int,
) -> StopDecision:
    return StopDecision(
        condition,
        reason,
        unresolved,
        tools,
        artifacts,
        observed_procedures,
        observed_evidence,
        verification_input.run_id,
        verification_input.task_id,
        verification_input.digest,
    )


def evaluate_stop(
    verification_input: VerificationInput,
    results: Sequence[CriterionResult] = (),
    *,
    missing_tools: Iterable[str] = (),
    missing_artifacts: Iterable[str] = (),
    stale_input: bool = False,
    human_override: bool | str = False,
    no_progress: bool = False,
    repeated_procedure_failure: bool = False,
    previous_results: Sequence[CriterionResult] = (),
    elapsed_seconds: float | int | None = None,
) -> StopDecision:
    """Evaluate stop conditions in a fail-closed and bounded order."""

    if not isinstance(verification_input, VerificationInput):
        raise ValueError("verification input is invalid")
    current = tuple(results)
    tools = _unique(missing_tools)
    artifacts = _unique(missing_artifacts)
    if elapsed_seconds is not None:
        if isinstance(elapsed_seconds, bool) or not isinstance(elapsed_seconds, (int, float)):
            raise ValueError("elapsed_seconds must be a non-negative real number")
        if not math.isfinite(float(elapsed_seconds)) or elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be a non-negative real number")
    unresolved = tuple(
        criterion
        for criterion in verification_input.required_criteria
        if criterion not in {item.criterion_id for item in current}
        or next(item for item in current if item.criterion_id == criterion).status
        in {
            VerificationStatus.NOT_RUN,
            VerificationStatus.UNKNOWN,
            VerificationStatus.BLOCKED,
            VerificationStatus.STALE,
        }
    )
    if human_override:
        return _decision(
            verification_input,
            StopCondition.HUMAN_OVERRIDE,
            "human override requested",
            unresolved,
            tools,
            artifacts,
            len(current),
            _evidence_count(current),
        )
    if verification_input.freshness is not FreshnessStatus.FRESH or stale_input:
        return _decision(
            verification_input,
            StopCondition.STALE_INPUT,
            "verification input is stale",
            unresolved,
            tools,
            artifacts,
            len(current),
            _evidence_count(current),
        )
    if any(item.status is VerificationStatus.STALE for item in current):
        return _decision(
            verification_input,
            StopCondition.STALE_INPUT,
            "required evidence or procedure receipt is stale",
            unresolved,
            tools,
            artifacts,
            len(current),
            _evidence_count(current),
        )
    if tools:
        return _decision(
            verification_input,
            StopCondition.MISSING_REQUIRED_TOOL,
            "a required tool is unavailable",
            unresolved,
            tools,
            artifacts,
            len(current),
            _evidence_count(current),
        )
    if artifacts:
        return _decision(
            verification_input,
            StopCondition.MISSING_REQUIRED_ARTIFACT,
            "a required artifact is unavailable",
            unresolved,
            tools,
            artifacts,
            len(current),
            _evidence_count(current),
        )
    if (
        elapsed_seconds is not None
        and elapsed_seconds >= verification_input.budgets.max_duration_seconds
    ):
        return _decision(
            verification_input,
            StopCondition.BUDGET_EXHAUSTED,
            "verification total duration budget exhausted",
            unresolved,
            tools,
            artifacts,
            len(current),
            _evidence_count(current),
        )
    if (
        len(current) > verification_input.budgets.max_procedures
        or _evidence_count(current) > verification_input.budgets.max_evidence_records
        or any(
            item.procedure_result is not None
            and item.procedure_result.attempts
            > verification_input.budgets.max_attempts_per_procedure
            for item in current
        )
    ):
        return _decision(
            verification_input,
            StopCondition.BUDGET_EXHAUSTED,
            "verification budget exhausted",
            unresolved,
            tools,
            artifacts,
            len(current),
            _evidence_count(current),
        )
    if any(item.status is VerificationStatus.FAIL for item in current):
        return _decision(
            verification_input,
            StopCondition.BLOCKING_FAILURE_FOUND,
            "a required criterion failed",
            unresolved,
            tools,
            artifacts,
            len(current),
            _evidence_count(current),
        )
    if any(item.status is VerificationStatus.BLOCKED for item in current):
        return _decision(
            verification_input,
            StopCondition.BLOCKING_FAILURE_FOUND,
            "a required criterion is blocked",
            unresolved,
            tools,
            artifacts,
            len(current),
            _evidence_count(current),
        )
    if repeated_procedure_failure:
        return _decision(
            verification_input,
            StopCondition.REPEATED_PROCEDURE_FAILURE,
            "a procedure failed repeatedly",
            unresolved,
            tools,
            artifacts,
            len(current),
            _evidence_count(current),
        )
    if no_progress or (
        previous_results
        and current
        and tuple(_signature(item) for item in previous_results)
        == tuple(_signature(item) for item in current)
    ):
        return _decision(
            verification_input,
            StopCondition.NO_PROGRESS,
            "verification state made no progress",
            unresolved,
            tools,
            artifacts,
            len(current),
            _evidence_count(current),
        )
    if current and not unresolved:
        return _decision(
            verification_input,
            StopCondition.ALL_REQUIRED_CRITERIA_RESOLVED,
            "all required criteria are resolved",
            (),
            tools,
            artifacts,
            len(current),
            _evidence_count(current),
        )
    return _decision(
        verification_input,
        None,
        "verification may continue",
        unresolved,
        tools,
        artifacts,
        len(current),
        _evidence_count(current),
    )


def _evidence_count(results: Sequence[CriterionResult]) -> int:
    return sum(len(item.evidence) for item in results)


decide_stop = evaluate_stop
