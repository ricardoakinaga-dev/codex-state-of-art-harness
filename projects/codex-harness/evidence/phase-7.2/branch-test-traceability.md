# Phase 7.2 Branch-to-Test Traceability

The JSON file is authoritative. Every current residual arc is listed; no residual is silently excluded.

- residual branches: `792`
- high-risk residual branches: `0`
- exact arcs still deferred: `791`
- test result semantics: referenced tests passed when marked `PASS`
- coverage semantics: `RESIDUAL_BRANCH_NOT_DIRECTLY_COVERED` means the exact arc remains absent from fresh coverage

## Closure policy

A regression or neighboring behavioral test is useful evidence, but it does not close an uncovered source-to-target arc by itself. Material branches therefore remain `DEFERRED_BLOCKING_PROMOTION` until direct execution or independently reviewable proof is recorded; recorded proof states are preserved explicitly.

## Category reports

- `category-artifact-integrity.md`
- `category-authorization.md`
- `category-cancellation.md`
- `category-concurrency.md`
- `category-dependency-failure.md`
- `category-evidence-staleness.md`
- `category-failure-routing.md`
- `category-filesystem.md`
- `category-host-auth.md`
- `category-idempotency.md`
- `category-ledger-locking.md`
- `category-migration.md`
- `category-no-progress.md`
- `category-oscillation.md`
- `category-other.md`
- `category-other-high-risk.md`
- `category-partial-execution.md`
- `category-persistence.md`
- `category-recovery.md`
- `category-retry.md`
- `category-rollback.md`
- `category-scope-control.md`
- `category-security-boundary.md`
- `category-state-transition.md`
- `category-telemetry-integrity.md`
- `category-timeout.md`
- `category-transaction.md`
