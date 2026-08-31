# Phase 7.2 Findings and Surgical Fixes

The findings register is authoritative for the focused defects investigated in this closure cycle. A fixed finding does not erase unrelated residual coverage arcs.

## Fixed or evidenced

- `P7.2-FINDING-001`: transport-auth source failures, zero-progress writes and partial-destination cleanup are fail-closed and tested.
- `P7.2-FINDING-002`: bounded-walk descriptor metadata failure is safe denial and tested.
- `P7.2-FINDING-003`: RunStore first-writer races use exclusive atomic creation and are tested.
- `P7.2-FINDING-004`: unavailable ledger locking and legacy replay-ledger upgrade are directly tested.
- `P7.2-FINDING-005`: the timeout concern is reclassified only for the current Phase 2 admission boundary; arbitrary hostile-provider isolation remains out of scope.
- `P7.2-FINDING-007`: persistence durability failures are no longer masked as idempotent first-writer races.
- `P7.2-FINDING-008`: empty telemetry chains and invalid legacy lifecycle state types fail closed during recovery.
- `P7.2-FINDING-009`: telemetry/lifecycle duplicate validation and append now share one directory lock.
- `P7.2-FINDING-010`: artifact/backend invalid path values are translated into bounded integrity failures.
- `P7.2-FINDING-011`: explicit repair stop accounting permits declared terminal checks while retaining the repair-call cap.
- `P7.2-FINDING-012`: CLI/policy type boundaries reject invalid and boolean attempts and preserve blocked envelopes.
- `P7.2-FINDING-013`: invalid typed stop conditions are rejected.
- `P7.2-FINDING-014`: zero-progress host writes return `FILE_WRITE_REJECTED` and clean up safely.
- `P7.2-FINDING-015`: invalid workspace and receipt-digest boundaries fail closed without untyped leakage.
- `P7.2-FINDING-016`: descriptor cleanup is unconditional and obsolete guards were removed.
- `P7.2-FINDING-017`: the Phase 5 final exhaustion edge is proven unreachable under the immutable invocation budget; see `phase5-cli-loop-proof.md`.

## Environment blocker

`P7.2-FINDING-006` is intentionally not hidden: the safe fixed host path cannot resolve a regular pinned `codex` executable, so the real builder/repair/verifier cycle is `BLOCKED_ENVIRONMENT`. No unpinned host or global installation was used.
