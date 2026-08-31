# Phase 7.3 Real-Cycle Attempt History

Earlier attempts are retained as diagnostics and are not used as the final
promotion receipt:

- `real-cycle-final-001`: host invocation completed, but the adapter failed
  while serializing an out-of-root temporary project reference.
- `real-cycle-final-002`: builder and repair passed; verifier rejected a known
  B023/formatting defect in the disposable artifact.
- `real-cycle-final-003`: builder, repair, Ruff check, mypy and fixed tests
  passed; verifier rejected one remaining formatter finding.
- `real-cycle-final-004`: builder, repair and verifier passed after a
  disposable normalization, but the run was superseded by the final pinned
  rerun.
- `real-cycle-final-005`: final pinned builder, repair and verifier cycle
  passed with limitations; it is the authoritative attempt.

Only `real-cycle-report-005.json` feeds the Phase 7.3 promotion risk ledger.
The supersession map is authoritative in `closeout-index.json`.
