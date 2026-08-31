# Phase 7.3 Medium-Risk Closure Summary

The current branch-aware final coverage contains `111` Medium residual arcs.
Every one has an explicit Phase 7.3 materiality and closure decision in
`medium-risk-inventory.json`; none remains in the historical
`DEFERRED_BLOCKING_PROMOTION` state.

| Decision | Count | Closure |
| --- | ---: | --- |
| MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE | 64 | TESTED_PASS |
| NON_MATERIAL_DEFENSIVE | 44 | ACCEPTED_NON_MATERIAL |
| UNREACHABLE_BY_CONTRACT | 3 | UNREACHABLE_PROVEN |
| Environment-blocked Medium | 0 | — |
| Open/actionable Medium | 0 | — |
| Promotion-blocking Medium | 0 | — |

The 64 material records are bound to exact source context, current
traceability and passing behavioral/regression evidence in
`material-medium-proof.json`. The proof matrix explicitly records zero direct
execution claims for residual arcs. Three Medium records are unreachable by
contract; 44 are defensive validation/normalization branches with explicit
exclusions for authority, evidence integrity, external I/O, filesystem,
persistence and side effects. No branch is accepted solely because it is hard
to cover.

The single High record is separately preserved as `UNREACHABLE_PROVEN` using
`evidence/phase-7.2/phase5-cli-loop-proof.md`. The machine-readable semantic
validator derives all promotion counts and rejects drift across the ledger,
readiness and final report.
