from __future__ import annotations

from harness_kernel.stops import (
    BudgetUsage,
    FailureObservation,
    ProgressSnapshot,
    StopBudget,
    StopCondition,
    StopEngine,
    detect_no_progress,
    detect_oscillation,
    detect_repeated_failure,
    evaluate_stop,
)


def snapshot(key: str, iteration: int) -> ProgressSnapshot:
    return ProgressSnapshot(iteration=iteration, criteria=(key,), evidence_refs=(key,))


def test_all_operational_stop_conditions_are_detectable() -> None:
    assert (
        evaluate_stop(iteration=3, budget=StopBudget(max_iterations=3)).condition
        is StopCondition.MAX_ITERATIONS
    )
    assert (
        evaluate_stop(progress_history=(snapshot("same", 1), snapshot("same", 2))).condition
        is StopCondition.NO_PROGRESS
    )
    failures = (FailureObservation(cause="same", input_fingerprint="fixture"),) * 2
    assert evaluate_stop(failure_history=failures).condition is StopCondition.REPEATED_FAILURE
    assert (
        evaluate_stop(
            progress_history=tuple(
                snapshot(key, i) for i, key in enumerate(("a", "b", "a", "b"), 1)
            )
        ).condition
        is StopCondition.OSCILLATION
    )
    assert (
        evaluate_stop(usage=BudgetUsage(tokens=10), budget=StopBudget(max_tokens=10)).condition
        is StopCondition.BUDGET_EXHAUSTION
    )
    assert (
        evaluate_stop(missing_tools=("runtime-host-load",)).condition is StopCondition.MISSING_TOOL
    )
    assert (
        evaluate_stop(blocked_dependencies=("ART-1",)).condition is StopCondition.BLOCKED_DEPENDENCY
    )
    assert (
        evaluate_stop(human_override="user requested stop").condition
        is StopCondition.HUMAN_OVERRIDE
    )


def test_acceptable_residual_risk_is_success_stop_only_after_required_passes() -> None:
    decision = evaluate_stop(
        required_passed=True,
        current_evidence=True,
        artifact_integrated=True,
        residual_risk_acceptable=True,
    )

    assert decision.condition is StopCondition.ACCEPTABLE_RESIDUAL_RISK


def test_progress_helpers_are_deterministic_and_engine_is_immutable() -> None:
    history = (snapshot("a", 1), snapshot("a", 2))
    failures = (
        FailureObservation(cause="timeout", input_fingerprint="fixture"),
        FailureObservation(cause="timeout", input_fingerprint="fixture"),
    )

    assert detect_no_progress(history)
    assert detect_repeated_failure(failures)
    assert detect_oscillation(("a", "b", "a", "b"))

    engine = StopEngine()
    extended = engine.record_progress(snapshot("a", 1))
    assert engine.progress_history == ()
    assert extended.progress_history == (snapshot("a", 1),)
