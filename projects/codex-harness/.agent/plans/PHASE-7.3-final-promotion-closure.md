# Phase 7.3 — Final Promotion Closure

## Objective

Close the remaining Phase 7 promotion uncertainty for the project-local
`backend-engineering-vNext` candidate. Promote only when the Phase 7.3 quality
bar is supported by current evidence; otherwise retain
`KEEP_CANDIDATE_NOT_PROMOTED` with explicit blockers.

## Authoritative inputs and baseline

- User specification: `pasted-text-1.txt`.
- Phase 7.2 packet: `evidence/phase-7.2/`.
- Earlier authorities: `evidence/phase-7.1/` and
  `evidence/phase-7/closeout-rerun-0009/`.
- Current baseline: `evidence/phase-7.3/baseline.json` and
  `evidence/phase-7.3/baseline-coverage.json`.
- Baseline HEAD: `f69b350f23ff0cd9ad5d22192f3ae7febdd8fa5e`.

## Scope and feature freeze

`P7_3_FEATURE_FREEZE` is active after baseline capture. Every source or test
change must map to a concrete `P7.3-FINDING-*` or to the Phase 7.3 evidence
contract. No feature, architecture, provider, frontend, installed Skill,
global configuration, production, deployment, or migration change is in scope.

## Workstreams and ownership

| ID | Outcome | Ownership | Dependencies | Validation |
| --- | --- | --- | --- | --- |
| W1 | Explicit risk semantics, Medium classification, count validator | Lead / `scripts/phase73_*`, `tests/unit/test_phase73_*` | baseline and frozen bar | RED → GREEN unit tests; inventory/readiness/report consistency |
| W2 | Focused material Medium closure | Lead, then one bounded owner per source subsystem; no simultaneous shared-file writers | W1 classification map | targeted behavioral tests; affected regression |
| W3 | Host reproducibility and current real cycle | Lead / `scripts/run_phase73_real_cycle.py`, isolated evidence roots | W1; host preflight | pinned metadata; real PASS or criteria-complete waiver |
| W4 | Scanner/dependency/static controls | Lead / Phase 7.3 evidence scripts and reports | W1 | fresh availability probes; available scanners; honest waivers |
| W5 | Integrated packet, independent review, decision | Lead + fresh read-only reviewer | W2–W4 | full suite, coverage, regressions, manifest, attestation, review |

## Frozen Quality Bar

The required bar is `evidence/phase-7.3/P7.3-QB-1.md`. It is frozen before
implementation and is not lowered to fit results. A known-bad inventory,
readiness mismatch, open actionable risk, unresolved critical/high scanner
finding, invalid waiver, stale fingerprint or missing independent review fails
the relevant gate.

## Required order

1. Baseline and feature freeze.
2. Normalize risk semantics and generate the exact current Medium inventory.
3. Classify every Medium branch and build the promotion risk ledger.
4. Add focused tests and fix only test-proven defects.
5. Analyze/pin the host; run the real cycle or produce a non-promotion-blocking waiver.
6. Recheck scanners, run available tools, review dependencies and static security.
7. Run fresh full tests, coverage, pilot/verifier and Phase 2–7.2 regressions.
8. Freeze the exact packet, obtain fresh independent review, then decide promotion.

## Stop rules

- Any material Medium, actionable High or promotion-blocking risk remains open:
  do not promote.
- Unavailable tooling is `UNAVAILABLE`, never `PASS`; waiver criteria must be
  explicit and expiring.
- Never use prior real execution as current execution. Historical evidence is
  valid only when exact candidate fingerprints remain bound and the waiver says
  `CURRENT_REAL_CYCLE_NOT_RERUN`.
- Never mutate installed `backend-patterns`, global Codex configuration or
  `verification-loop-vNext` while running this phase.

## Definition of done

All required P7.3-QB-1 gates have current evidence, the exact packet is
internally consistent, a fresh independent reviewer accepts it, and the final
promotion state is either a defensible `VERIFIED_CANDIDATE` or an honest
`KEEP_CANDIDATE_NOT_PROMOTED`/`REWORK` decision with every blocker named.
