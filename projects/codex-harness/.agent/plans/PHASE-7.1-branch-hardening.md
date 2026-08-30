# Phase 7.1 ExecPlan — Backend vNext Branch Hardening

## Objective

Close the meaningful branch-coverage and failure-path assurance gap in the
project-local `backend-engineering-vnext` candidate. Preserve the Phase 7
feature surface and promote only if the current candidate survives evidence
that exercises failure, rollback, concurrency, idempotency, migration,
authorization, timeout and evidence-integrity behavior.

## Scope and freeze

- Task: `PHASE7.1-001`
- Feature freeze: `P7_1_FEATURE_FREEZE`
- In scope: tests, deterministic fixtures/utilities, test-proven bug fixes,
  bounded observability needed to verify behavior, coverage/evidence and an
  exact Phase 7.1 closeout.
- Out of scope: frontend modernization, new engineering domains, routing or
  Phase 2–6 architecture redesign, installed/global capability changes,
  production actions and expanded claims.
- Source changes require a `TESTED_BRANCH_FINDING_ID` and a regression test.

## Architecture understanding

The candidate is a project-local native package under
`.harness/capabilities/backend-engineering-vnext/`. The disposable pilot is
`pilots/backend-appointment-api/`; Harness behavior is implemented in
`src/harness_kernel/phase7_backend.py` and `src/harness_kernel/phase7_host.py`.
The exact Phase 7 input is `evidence/phase-7/closeout-rerun-0009/`; earlier
closeouts are historical. The existing combined suite is the regression
surface for Phases 2–7.

## Workstreams and ownership

| ID | Outcome | Ownership | Dependencies | Status |
| --- | --- | --- | --- | --- |
| P7.1-BASE | Reproducible baseline and feature freeze | Lead; `evidence/phase-7.1/baseline.json`, this plan and quality bar | Phase 7 closeout read | VERIFIED |
| P7.1-INV | Complete machine-readable branch inventory and risk map | Lead; `evidence/phase-7.1/branch-inventory.*`, `branch-risk-map.md` | P7.1-BASE | IN_PROGRESS |
| P7.1-FAIL | High-value failure-path tests and test-proven fixes | Lead plus disjoint test lanes; assigned files recorded per round | P7.1-INV | PENDING |
| P7.1-REG | Pilot, verifier, migration, security and Phase 2–7 regressions | Lead; generated evidence only | P7.1-FAIL | PENDING |
| P7.1-CLOSE | Exact packet, fresh independent review and promotion decision | Lead; `evidence/phase-7.1/` | P7.1-REG | PENDING |

Parallel read-only scouting is allowed for inventory and criticism. Writers
must not share files or mutable fixtures; the Lead integrates all changes.

## Frozen acceptance criteria

- `P7.1-01`: branch inventory is complete, reproducible and every remaining
  branch has a risk/category classification or an evidence-backed exclusion.
- `P7.1-02`: final branch coverage is at least 80.00%; preferred target is
  85.00%; line coverage remains at least 80.00%.
- `P7.1-03`: transaction, rollback, constraint, concurrency and idempotency
  invariants are tested against actual isolated persistent state.
- `P7.1-04`: migration failure/recovery and destructive-operation guards are
  tested; no partial migration state survives an atomic failure.
- `P7.1-05`: authorization/security handoff, dependency failure, retry,
  timeout, cancellation, partial result and missing-tool behavior fail closed.
- `P7.1-06`: stale evidence, artifact substitution, scope expansion,
  no-progress, repeated failure and oscillation are tested and stop safely.
- `P7.1-07`: complete tests, pilot, verifier composition, Phase 2–7
  regressions, Ruff, mypy and security controls remain green or are honestly
  classified as unavailable/limited.
- `P7.1-08`: exact evidence is rebound to the reviewed HEAD and a fresh
  read-only independent reviewer finds no actionable Critical/High/Medium
  issue before any promotion decision.

## Validation order

`inventory → risk classification → targeted RED tests → minimal fixes →
targeted GREEN → complete coverage → pilot/verifier/regression → lint/types/
security → exact packet → independent review → promotion decision`.

No promotion is allowed while P7.1-02 or a material failure-path gate fails.
