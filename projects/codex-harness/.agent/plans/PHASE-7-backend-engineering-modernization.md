# ExecPlan — PHASE7-001 Backend Engineering vNext Modernization

## Purpose

Modernize the installed `backend-patterns` capability as an additive,
project-local Codex-native backend specialist and prove it on one isolated,
fictional backend feature. The current installed package and frozen Phase 2–6
packets are read-only authorities.

## Frozen authorities and inputs

- User requirements: `/home/ricardo/.codex/attachments/1bd02431-5cd8-4a0c-8200-b27a673e917b/pasted-text-1.txt`
- Quality bar: `evidence/phase-7/P7-QB-1.md`
- ADR: `../../architecture/docs/adr/ADR-016-backend-engineering-vnext-modernization.md`
- Current snapshot: `evidence/phase-7/current-backend-patterns-snapshot.json`
- Current analysis: `evidence/phase-7/current-capability-analysis.md`
- Upstream analysis: `evidence/phase-7/upstream-analysis.md`
- Frozen prior packets: `evidence/phase-{2,3,4,5,6}/` and their freeze/readiness reports
- Native architecture: `../../architecture/docs/03-capability-taxonomy.md`, `04-authority-model.md`, `06-routing-system.md`, `07-orchestration-model.md`, `09-specialist-model.md`, `10-capability-package-standard.md`, `11-skill-md-standard.md`, `12-composition-contracts.md`, `13-verification-system.md`, `15-stop-conditions.md`, `16-context-management.md`, `17-tool-selection.md`, `18-telemetry.md`, `20-eval-framework.md`, `21-quality-model.md`, `22-aaa-definition.md`, `23-security-model.md`, `24-failure-model.md`, `25-degradation-model.md`, `33-skill-modernization-program.md`, `34-modernization-template.md`, `38-implementation-roadmap.md`

## Scope and non-goals

In scope: one package at `.harness/capabilities/backend-engineering-vnext`,
typed immutable package/pilot contracts, deterministic local metadata checks,
40+ eval cases, four-way benchmark metadata, real Phase 3 discovery/load,
explicit Phase 4 workspace-write preflight, one real builder run, a bounded
stdlib-only backend pilot, real read-only verification-loop-vNext composition,
optional independent critics, one repair maximum, fresh final verification,
regressions, security checks and exact evidence closure.

Out of scope: installed/global Skill mutation, global config, production or
private repositories, arbitrary shell/network/MCP/provider/credential use,
unapproved dependencies, broad framework adoption, unrelated schema changes,
destructive migration, release approval, stable promotion, causal claims and
AAA verification.

## Role boundary

`backend-engineering-vnext` is a `SPECIALIST` and owns backend implementation
within the frozen task. `api-design` can specify/review the contract;
`coding-standards` and `tdd-workflow` remain orthogonal overlays;
`security-review` owns final security assurance when triggered;
`verification-loop-vnext` is a read-only factual verifier; `REVIEWER` and
`ASSURANCE` remain independent. The builder cannot approve its own work.

## Pilot contract

The pilot is a fictional Veterinary Appointment API using Python 3.12 and the
standard library already present in the project. It exposes a versioned create
appointment route, validates a client/patient relationship, authorizes an
actor, writes a client/patient/appointment-backed SQLite model transactionally,
enforces a database slot invariant, handles idempotency and conflict errors,
applies a bounded migration, emits redacted structured events, and supplies
unit/API/integration/migration/negative/concurrency tests. The database is
disposable and no real personal data is used.

## Work sequence and ownership

1. Lead freezes bar, ADR, baseline/snapshots, task, integration contracts and
   control-plane entry gate.
2. Package worker owns only `.harness/capabilities/backend-engineering-vnext/**`
   plus package-contract tests/eval fixtures.
3. Pilot worker owns only `pilots/backend-appointment-api/**` and pilot tests.
4. Harness integration worker owns only additive Phase 7 modules/scripts and
   their tests; changes to existing Phase 4 host/policy APIs are additive and
   must preserve default read-only behavior.
5. Lead runs real discovery, safe load, preflight and host invocations, then
   creates the exact evidence packet.
6. Fresh independent reviewers inspect the immutable packet; any finding is
   repaired once at most, followed by a complete fresh verification.

No two workers write the same file. Reviewers are read-only and receive no
builder rationale.

## Budgets and stop conditions

- package instruction kernel <=16 KiB; selected references <=64 KiB;
- deterministic procedures <=32, one attempt each, total <=120 seconds;
- real builder invocations <=2 only to account for one repair;
- verifier invocations <=2; repair <=1;
- pilot test/evidence output is bounded and disposable;
- network, MCP, credentials, providers and arbitrary shell are denied;
- stop on `BLOCKING_TEST_FAILURE`, `UNSAFE_MIGRATION`,
  `SECURITY_REVIEW_REQUIRED`, `MISSING_REQUIRED_CONTEXT`,
  `SCOPE_EXPANSION_REQUIRED`, `NO_PROGRESS`, `REPEATED_FAILURE`,
  `OSCILLATION`, `BUDGET_EXHAUSTED`, `HUMAN_DECISION_REQUIRED` or a stale
  required artifact.

## Verification commands

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/coverage run --branch --source=src/harness_kernel -m pytest -q -p no:cacheprovider
.venv/bin/coverage report --fail-under=80
.venv/bin/ruff format --check src tests
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Pilot commands, migration commands, package validators, discovery/load,
preflight, real host receipts and security scans must be recorded verbatim in
the Phase 7 evidence. A passing command is not evidence for a different
artifact or a stale invocation.

## Exit rule

The maximum allowed outcome is an evidence-backed `PASS_WITH_LIMITATIONS` at
the highest directly observed support level. If a legitimate host limitation
blocks a safety-neutral composition, record `CONDITIONAL_PASS`; if data
integrity/security/role separation cannot be verified, record `FAIL` and do not
promote. The installed package remains unchanged in every outcome.
