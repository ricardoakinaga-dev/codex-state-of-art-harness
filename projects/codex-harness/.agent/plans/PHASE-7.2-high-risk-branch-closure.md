# ExecPlan — PHASE7.2 High-Risk Branch Closure

## Objective

Close Phase 7.1 finding H-01 for the current project-local
`backend-engineering-vnext` candidate. Reconstruct the current 1,377 residual
branch arcs, determine which are materially safety-critical, prove or fix each
material branch through behavioral evidence, and only promote if the exact
packet receives fresh independent approval.

## Authorities and current state

- User specification: `/home/ricardo/.codex/attachments/6497beb4-5270-49c1-8d24-acbceda28cbd/pasted-text-1.txt`.
- Phase 7.1 authority: `evidence/phase-7.1/` files listed in
  `evidence/phase-7.2/baseline.json`.
- Phase 7 authority: `evidence/phase-7/closeout-rerun-0009/`.
- Current baseline: `evidence/phase-7.2/baseline.json`.
- Frozen bar: `evidence/phase-7.2/P7.2-QB-1.md`.

## Scope and feature freeze

`P7_2_FEATURE_FREEZE` is active. Every source/test/tooling modification must
map to a `P7.2-FINDING-*`. The phase may add focused tests, deterministic
fault/concurrency fixtures, observability, minimal test-proven source fixes,
dead-code removal with proof, and evidence. It must not add capabilities,
modernize frontend/security skills, redesign the backend package, broaden the
pilot, mutate installed/global state, deploy, push, or claim production/AAA
readiness.

## Workstreams and ownership

1. **Inventory/traceability (Lead only)** — `scripts/` additions for
   deterministic Phase 7.2 inventory and `evidence/phase-7.2/` controls.
2. **Kernel failure paths** — `src/harness_kernel/{boundary,persistence,
   execution,phase4_execution,phase4_host,phase4_models,phase4_policy,
   phase4_verification,phase4_evidence,phase3_paths,phase7_host,phase7_backend}.py`
   and their focused tests; sequence changes because these share contracts.
3. **State/evidence/telemetry paths** — remaining source/test surfaces for
   cancellation, partial/timeout/routing/recovery/state/evidence/telemetry;
   integrate sequentially after kernel contract findings.
4. **Pilot/regression (Lead only unless a disjoint worker is available)** —
   `pilots/backend-appointment-api/**`, real receipts and prior-phase reports.
5. **Independent review** — read-only fresh agent/context over the frozen exact
   packet; no implementation ownership.

Parallel work is restricted to read-only criticism or disjoint evidence
   analysis. Shared source, tests, configuration, `.agent` ledgers and runtime
   fixtures have one writer: the Lead.

## Critical path

`baseline → freeze → inventory → traceability → locking/auth/filesystem/
persistence → cancel/partial/timeout/routing → transaction/concurrency/
idempotency/migration/retry → recovery/state/integrity/telemetry/progress →
full verification → exact packet → independent review → H-01 decision`.

## Required outputs

All minimum Phase 7.2 closeout files named in the user specification, including
inventory, traceability, category reports, coverage/test/regression reports,
security summary, residual-risk review, exact manifest/attestation,
promotion-decision and readiness. Create `PHASE7.2-FROZEN.md` only after
promotion criteria are actually proven.

## Verification and recovery

Use isolated synthetic data and temporary coverage files. Run focused tests
before affected regressions and full suite after every material source fix.
Record unavailable scanners as `UNAVAILABLE`; never convert missing evidence to
PASS. Preserve the old Phase 7/7.1 packets and the stale `.agent/state.json`;
reconcile control-plane pointers only through append-only evidence after the
current Phase 7.2 result is known.

## Exit rule

`PROMOTE_TO_VERIFIED_CANDIDATE` requires H-01 closed, zero material high-risk
residuals, current full evidence, required regressions/static checks, and fresh
independent exact-packet PASS. Otherwise close honestly as
`KEEP_CANDIDATE_NOT_PROMOTED` or `REWORK` with every unresolved blocker named.

## Current closeout result

The authoritative attempt `P7.2-CLOSEOUT-001` closed as
`PASS_WITH_LIMITATIONS` / `KEEP_CANDIDATE_NOT_PROMOTED`. The final suite has
1,300 passing tests with 89.41218674729667% line coverage and
81.62577514154759% branch coverage. The inventory contains 1,363 residual
branches, including 493 material high-risk branches; exact residual closure
counts are zero and H-01 remains open. The real builder/repair/verifier cycle
is `BLOCKED_ENVIRONMENT` because the safe fixed host path cannot resolve the
pinned `codex` executable. The fresh independent review is `FAIL` / `REJECT`.
The packet is bound by `evidence/phase-7.2/review-manifest.json` and
`review-attestation.json`; `closeout-index.json` is intentionally excluded from
the manifest to avoid recursive hashing. No `PHASE7.2-FROZEN.md` is authorized.
