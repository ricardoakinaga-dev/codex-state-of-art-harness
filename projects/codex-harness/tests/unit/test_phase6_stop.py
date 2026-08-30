from __future__ import annotations

from dataclasses import replace

import pytest
from test_phase6_models import make_input
from test_phase6_verifier import pass_result

from harness_kernel.phase6_models import (
    Claim,
    ProcedureResult,
    ProcedureSpec,
    StopCondition,
    VerificationBudget,
    VerificationStatus,
)
from harness_kernel.phase6_stop import StopDecision, evaluate_stop
from harness_kernel.phase6_verifier import verify_input


def test_stop_when_all_required_criteria_are_resolved(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    output = verify_input(verification_input, (pass_result(verification_input),))
    decision = evaluate_stop(verification_input, output.criterion_results)
    assert decision.condition is StopCondition.ALL_REQUIRED_CRITERIA_RESOLVED
    assert decision.should_stop is True
    assert decision.run_id == verification_input.run_id
    assert decision.task_id == verification_input.task_id
    assert decision.input_digest == verification_input.digest
    assert decision.digest.startswith("sha256:")


def test_unbound_stop_decision_is_still_structurally_distinct() -> None:
    decision = StopDecision(None, "not enough observations")
    assert decision.should_stop is False
    assert decision.run_id is None
    assert decision.digest.startswith("sha256:")


def test_stop_decision_rejects_partial_identity() -> None:
    with pytest.raises(ValueError):
        StopDecision(None, "invalid", run_id="RUN-1")


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    (
        ({"missing_tools": ("browser",)}, StopCondition.MISSING_REQUIRED_TOOL),
        ({"missing_artifacts": ("ART-1",)}, StopCondition.MISSING_REQUIRED_ARTIFACT),
        ({"stale_input": True}, StopCondition.STALE_INPUT),
        ({"human_override": True}, StopCondition.HUMAN_OVERRIDE),
        ({"no_progress": True}, StopCondition.NO_PROGRESS),
        ({"repeated_procedure_failure": True}, StopCondition.REPEATED_PROCEDURE_FAILURE),
    ),
)
def test_typed_stop_conditions_are_observable(tmp_path, kwargs, expected) -> None:
    verification_input = make_input(tmp_path)
    decision = evaluate_stop(verification_input, (), **kwargs)
    assert decision.condition is expected
    assert decision.reason


def test_budget_exhaustion_precedes_an_unbounded_run(tmp_path) -> None:
    verification_input = replace(
        make_input(tmp_path),
        budgets=VerificationBudget(max_procedures=1),
        digest="",
    )
    results = (
        ProcedureResult(
            spec=ProcedureSpec("PROC-1", "C-1", "first"),
            status=VerificationStatus.NOT_RUN,
        ),
        ProcedureResult(
            spec=ProcedureSpec("PROC-2", "C-2", "second"),
            status=VerificationStatus.NOT_RUN,
        ),
    )
    decision = evaluate_stop(verification_input, results)
    assert decision.condition is StopCondition.BUDGET_EXHAUSTED


def test_blocking_failure_is_distinct_from_continue(tmp_path) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    failed = replace(pass_result(verification_input), status=VerificationStatus.FAIL, digest="")
    decision = evaluate_stop(
        verification_input,
        (
            failed.as_criterion_result(
                Claim(criterion_id="C-1", text="failed"), status=VerificationStatus.FAIL
            ),
        ),
    )
    assert decision.condition is StopCondition.BLOCKING_FAILURE_FOUND
    continuing = evaluate_stop(verification_input, ())
    assert continuing.condition is None
    assert continuing.should_stop is False


@pytest.mark.parametrize("elapsed_seconds", (float("nan"), float("inf"), float("-inf")))
def test_stop_rejects_non_finite_elapsed_time(tmp_path, elapsed_seconds) -> None:
    verification_input = make_input(tmp_path, criteria=("C-1",))
    with pytest.raises(ValueError, match="elapsed_seconds"):
        evaluate_stop(verification_input, (), elapsed_seconds=elapsed_seconds)
