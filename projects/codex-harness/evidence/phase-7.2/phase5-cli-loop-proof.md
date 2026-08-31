# Phase 7.2 Phase 5 CLI Loop Proof

Branch: `P7.2-BRANCH-f2e9d9298c4f3336`

The residual arc `phase5_cli.py:400 -> 415` is the natural exhaustion edge of
the bounded builder `for` loop. It is proven unreachable under the immutable
`Phase5Budget` contract:

1. `Phase5Budget.max_builder_invocations` is fixed at `2` and cannot be zero.
2. A non-`PASS` response or a missing final message takes the explicit `break`.
3. A valid extracted artifact takes the explicit `break`.
4. An artifact extraction failure continues only before the final attempt; on
   attempt `2`, `attempt == budget.max_builder_invocations` takes the explicit
   `break`.

Therefore every valid execution exits the loop through an explicit break
before the natural `for`-exhaustion edge. The final suite includes the direct
two-attempt invalid-artifact test in
`tests/unit/test_phase72_phase5_remaining_assurance.py`, and no production
input can make the loop budget zero or bypass those exits.

Closure state: `UNREACHABLE_PROVEN`.
