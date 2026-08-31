# Phase 7.3 Risk Semantics

This file is the canonical meaning of risk counters. It is intentionally
separate from the inventory generator so a report cannot redefine a count to
make promotion appear available.

## Dimensions

- `classified`: every current residual branch assigned this risk level,
  regardless of closure.
- `open_actionable`: a classified branch whose materiality can affect candidate
  correctness, authority, persistence, recovery, integrity, false success,
  security or release honesty and whose closure is not proven.
- `promotion_blocking`: an open actionable branch explicitly marked
  `OPEN_PROMOTION_BLOCKER` or `BLOCKED_ENVIRONMENT_PROMOTION_BLOCKING`.
- `closed_tested`: closure state `TESTED_PASS` or `TESTED_FAIL_FIXED`.
- `closed_unreachable`: closure state `UNREACHABLE_PROVEN`.
- `closed_removed`: closure state `DEAD_CODE_REMOVED`.
- `accepted_residual`: a residual with evidence-backed
  `ACCEPTED_NON_MATERIAL` or `BLOCKED_ENVIRONMENT_NON_PROMOTION_BLOCKING`
  closure. It remains classified and visible; acceptance does not mean tested.

## Materiality

`MATERIAL_PROMOTION_RELEVANT` and
`MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE` are actionable until
their current closure evidence is recorded. `NON_MATERIAL_DEFENSIVE`,
`UNREACHABLE_BY_CONTRACT`, `DEAD_CODE`, `ENVIRONMENT_DEPENDENT`,
`PLATFORM_SPECIFIC` and `DOCUMENTATION_ONLY / DIAGNOSTIC_ONLY` may be accepted
only with a specific proof or contract reference; a generic “low importance”
label is invalid.

## Closure states

Every branch ends in exactly one of:

`TESTED_PASS`, `TESTED_FAIL_FIXED`, `UNREACHABLE_PROVEN`,
`DEAD_CODE_REMOVED`, `ACCEPTED_NON_MATERIAL`,
`BLOCKED_ENVIRONMENT_NON_PROMOTION_BLOCKING`,
`BLOCKED_ENVIRONMENT_PROMOTION_BLOCKING`, or `OPEN_PROMOTION_BLOCKER`.

The promotion invariant is:

```text
promotion_blocking_high == 0
and promotion_blocking_medium == 0
and no ledger entry has promotion_impact == BLOCK with status != CLOSED
```

No counter may be inferred from prose after the packet is generated. The
Phase 7.3 validator derives all counts from the current inventory and compares
them with the readiness, ledger and machine-readable count marker in the final
report.
