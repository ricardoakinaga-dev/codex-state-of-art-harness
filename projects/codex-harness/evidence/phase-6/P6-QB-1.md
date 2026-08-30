# P6-QB-1 — Verification Loop vNext Modernization Quality Bar

This bar is frozen before Phase 6 implementation. It applies only to the
additive project-local modernization candidate and does not authorize global
migration, installed-package mutation, arbitrary execution, production use,
AAA verification or release approval.

| ID | Required criterion | Required evidence |
| --- | --- | --- |
| P6-01 | Phase 2–5 frozen authorities remain preserved and regression-green | `phase2-regression.md`, `phase3-regression.md`, `phase4-regression.md`, `phase5-regression.md` |
| P6-02 | The installed current package has an exact read-only forensic identity and all ineligibility causes are explicit | `current-verification-loop-snapshot.json`, `current-ineligibility-analysis.md` |
| P6-03 | Upstream/fork refs, revisions, raw snapshots, provenance and comparison limitations are recorded | `upstream-analysis.md` |
| P6-04 | vNext is a valid project-local native package with identity, version, manifest, compatibility and provenance | `vnext-manifest.json`, `package-validation.json` |
| P6-05 | Activation, non-activation, profiles, role ownership and composition relations are explicit | package `SKILL.md`, `composition-contract.json`, evals |
| P6-06 | `VerificationInput` and `VerificationOutput` are immutable, bounded and schema-valid | contract tests and `contract-validation.json` |
| P6-07 | Every required criterion binds Claim → Procedure → Evidence → Status with freshness and confidence | verifier report, lineage tests, evidence ledger |
| P6-08 | VERIFIER, REVIEWER, BUILDER, DESIGN_DIRECTOR, ORCHESTRATOR and ASSURANCE authority boundaries cannot collide | role/authority tests and negative evals |
| P6-09 | Deterministic checks are read-only by default, path-confined, bounded and free of arbitrary shell/network/credential assumptions | `security-report.md`, security tests |
| P6-10 | All required stop conditions are typed, observable and enforced without unbounded loops | stop-policy tests and run receipts |
| P6-11 | FOCUSED, DOMAIN, FULL, VISUAL, STRUCTURAL, SECURITY_AWARE and COMPOSITION profiles are declared with gates | `profiles.json`, profile evals |
| P6-12 | Phase 3 discovers and safely loads the project-local package as native without changing global state | discovery/load/preflight evidence |
| P6-13 | Phase 4 preflight reaches `PILOT_EXECUTABLE` before any real verifier route; failures stop honestly | preflight receipt and negative evidence |
| P6-14 | At least 30 meaningful eval scenarios cover pass/fail/partial/blocked/stale, mutation, injection, flood and activation boundaries | `eval-report.json`, scenario fixtures |
| P6-15 | Native/current/upstream/vNext benchmarks measure correctness, coverage, false PASS, context and latency without causal overclaiming | `benchmark-report.json`, `benchmark-summary.md` |
| P6-16 | Composition reaches at least Level B and attempts Level C only with real eligible capabilities and fresh final verification | `composition-design.json`, `composition-value.json`, receipts |
| P6-17 | Artifact/evidence identity, stale invalidation, criteria mutation and role escalation block 100% of required negative cases | `coverage-report.json`, negative evals |
| P6-18 | Phase 2–5 regressions, combined coverage ≥80%, Ruff, strict mypy and security checks pass | quality reports |
| P6-19 | Fresh independent capability and composition reviews inspect the exact final packet | `independent-review.md`, `review-manifest.json`, attestation |
| P6-20 | No unresolved Critical/High finding remains; promotion is at most `VERIFIED` candidate and no migration occurs | `readiness.json`, `promotion-decision.json`, `PHASE6-FROZEN.md` |

## Required result states

Criterion and procedure states are `PASS`, `FAIL`, `PARTIAL`, `BLOCKED`,
`STALE`, `NOT_RUN` or `UNKNOWN`. A required criterion without current evidence
cannot be `PASS`. Missing tools/artifacts and stale inputs are blocking, not
advisory.

## Support levels

- `P6_LEVEL_A`: project-local vNext contracts and deterministic verification
  are proven with current evidence.
- `P6_LEVEL_B`: Level A plus a real bounded composition with the design
  director and a real vNext verifier.
- `P6_LEVEL_C`: Level B plus independent visual critique, bounded repair and a
  fresh final vNext verification/assurance path.

The maximum honest result is the level supported by direct evidence. Native
Harness code, a fallback verifier or a prose simulation cannot be relabeled as
an external vNext invocation.

## Mandatory limitations

The final packet must state host-load observability, runtime availability,
browser/visual scope, upstream freshness, dependency/tool limitations,
interactive coverage and all excluded production/AAA/causal claims. Historical
PASS records are never rewritten when new Phase 6 bytes make them stale.
