# P7-QB-1 — Backend Engineering Modernization Pilot Quality Bar

This bar is frozen before Phase 7 implementation. It applies only to the
project-local candidate and isolated fictional pilot. Passing it cannot imply
production readiness, universal host behavior, causal improvement, `AAA` or
`HARNESS_AAA_VERIFIED`.

| ID | Blocking criterion | Required evidence |
| --- | --- | --- |
| P7-01 | Phase 2, 3, 4, 5 and 6 frozen packets remain regression-green. | `phase2-regression.md` through `phase6-regression.md` |
| P7-02 | Current `backend-patterns` is inspected read-only with exact package identity and zero mutation. | `current-backend-patterns-snapshot.json`, `current-capability-analysis.md`, mutation snapshot |
| P7-03 | Upstream is inspected at an observed repository/revision, with differences and unknowns recorded. | `upstream-analysis.md` |
| P7-04 | Codex-native capabilities are separated from backend-specific gaps; generic advice is not copied as ownership. | `native-capability-gap-analysis.md`, architecture contract report |
| P7-05 | ADR, scope, ownership, non-responsibilities, budgets, stop conditions and rollback are explicit before build. | ADR-016, this bar, ExecPlan, implementation-ready gate |
| P7-06 | The vNext package is a valid native project-local `SPECIALIST` with manifest, provenance, compatibility, trust, contracts and bounded tool policy. | `vnext-package-report.md`, package manifest/fingerprint |
| P7-07 | `SKILL.md` is concise and routes to references/contracts rather than becoming a pattern encyclopedia. | package tree, size report, context-cost report |
| P7-08 | Activation and non-activation are narrow, scale-adaptive and reject trivial/documentation/frontend-only tasks. | negative routing evals and `eval-report.md` |
| P7-09 | Architecture preservation and boundary decisions are explicit; unnecessary framework/pattern ceremony is rejected. | architecture evals and `architecture-contract-report.md` |
| P7-10 | API method/path/schema/error/auth/idempotency/versioning behavior is explicit and stable. | `api-data-boundary-report.md`, route contract and API tests |
| P7-11 | Transport validation, domain validation, authorization and business-rule failures are distinct. | pilot tests, route contract, verifier evidence |
| P7-12 | Every multi-write workflow declares atomicity, rollback, retry and idempotency semantics. | implementation plan, migration/data reports, transaction tests |
| P7-13 | Database constraints protect material invariants and concurrent conflicting booking cannot double-write. | migration results, integrity/concurrency tests |
| P7-14 | Migration evidence covers apply, schema/data preservation, compatibility and safe rollback or an explicit disposable limitation. | `migration-safety-report.md`, `migration-results-v1.json` |
| P7-15 | Reliability, timeout/retry/dependency behavior and performance budget are proportional and evidenced. | `reliability-report.md`, benchmark and negative tests |
| P7-16 | Structured observability identifies request/outcome/failure class without secrets or sensitive payloads. | observability tests and pilot evidence |
| P7-17 | Security-aware implementation triggers a separate security handoff when auth, sensitive data or injection boundaries are material. | `security-handoff-report.md`, `security-summary.md`, security review/native scan |
| P7-18 | Tests are risk-shaped across unit, API/integration, migration, negative, idempotency and concurrency boundaries. | `test-strategy-report.md`, pilot test results |
| P7-19 | At least 40 meaningful eval cases are present when justified, including adversarial routing, stale evidence, prompt injection, tool escalation and artifact substitution. | `evals/scenarios.json`, `eval-report.md` |
| P7-20 | Native/current/upstream/vNext benchmark paths use the same normalized task and label observations as `PILOT_MODERNIZATION_EVIDENCE`. | `benchmark-report.md`, `benchmark-summary.json` |
| P7-21 | Real Phase 3 discovery and safe load observe the exact project-local package through the canonical host path. | discovery/load receipt and `real-backend-pilot-report.md` |
| P7-22 | Phase 4 preflight approves exact package bytes and bounded workspace-write authorization without manual bypass. | authorization, preflight and builder receipt |
| P7-23 | A real vNext builder invocation produces actual pilot code changes in the isolated workspace. | builder fingerprint/receipt, `artifact-v1/` |
| P7-24 | Real verification-loop-vNext receives immutable task, criteria, artifact/diff, tests, migration/API/data evidence and builder receipt; it remains read-only. | `verification-report-v1.json`, composition receipt |
| P7-25 | Optional independent backend/security critics are separate from the builder; at most one structured repair is allowed. | critic/security reports, repair plan, final verification |
| P7-26 | Any v2 change invalidates v1 verification and receives fresh final verification with rebound digests. | `artifact-v2/`, `final-verification.json` |
| P7-27 | Current installed/global mutation count is zero; no production, credential, arbitrary-shell, network, MCP or unapproved dependency mutation occurred. | security summary, before/after mutation snapshots |
| P7-28 | Combined Harness coverage is at least 80%; Ruff and strict mypy pass; pilot quality checks are recorded. | `coverage-report.md`, quality receipt |
| P7-29 | Security scan and dependency review find no unresolved Critical/High issue or false PASS. | `security-summary.md`, review packet |
| P7-30 | Independent capability and pilot/composition reviews inspect the exact packet without builder context and return an allowed status. | review reports, manifest, attestation |
| P7-31 | Exact manifest, closure, readiness, promotion decision, gate and freeze references reconcile to current bytes. | `review-manifest.json`, `review-attestation.json`, `readiness.json`, `PHASE7-FROZEN.md` |

## Support and decision rules

- `P7_LEVEL_A`: the candidate is independently `VERIFIED_CANDIDATE`.
- `P7_LEVEL_B`: A plus real backend-engineering-vNext and real
  verification-loop-vNext composition succeeds on the real isolated pilot.
- `P7_LEVEL_C`: B plus independent backend/security criticism, at most one
  repair and fresh final verification succeeds.

`PASS_WITH_LIMITATIONS` requires zero Critical/High findings, a
`VERIFIED_CANDIDATE` package, a real artifact, tests, real verifier composition,
all prior regressions and exact independent review. A legitimate non-safety
environment limitation uses `CONDITIONAL_PASS`; missing safety evidence,
unverifiable data integrity, role collision, or a critical false PASS is `FAIL`.
