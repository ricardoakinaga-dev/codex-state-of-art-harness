# ExecPlan — PHASE4-001 Real Capability Invocation Boundary

## Purpose / Big Picture

Extend the frozen Phase 2 deterministic kernel and the frozen Phase 3
read-only discovery boundary with one controlled, explicitly authorized
Codex `app-server` invocation path. The result must prove the complete
preflight, exact-byte binding, bounded host request, result normalization,
artifact capture, verification and evidence chain for a narrow pilot. It must
not become arbitrary Skill, shell, script, provider, MCP, network or subagent
execution.

The strongest permitted result is `PASS_WITH_LIMITATIONS` at host support
Level B when the official host executes a turn but exposes no distinct Skill
load-causality event. `AAA_VERIFIED` is never an allowed claim.

## Progress

- [x] Recovered the Phase 3 freeze and recorded the additive Phase 4 scope.
- [x] Read the complete Phase 4 requirements, architecture and relevant ADRs.
- [x] Verified the local Codex `0.150.1` app-server JSON-RPC handshake,
      `skills/list`, ephemeral `thread/start`, `turn/start`, and official
      `skill` input item without modifying global files.
- [x] Confirmed a real Skill turn can return a bounded assistant result.
- [ ] Freeze P4-QB-1, policy registry, allowlist and TDD RED suite.
- [ ] Implement immutable contracts, policy/preflight and context manifest.
- [ ] Implement the Codex app-server adapter and lifecycle engine.
- [ ] Implement artifact capture, verification, assurance and evidence.
- [ ] Run dry-run, controlled pilot and all negative pilots.
- [ ] Run full regressions, security review, benchmark and exact-packet review.
- [ ] Reconcile state and freeze the exact Phase 4 packet.

## Surprises & Discoveries

- The installed Codex app-server exposes the official JSON-RPC surface needed
  for a real invocation: `initialize`, `skills/list`, `thread/start`,
  `turn/start`, `turn/completed`, and the typed `skill` user-input item.
- A real bounded turn emitted `userMessage`, `reasoning` and `agentMessage`
  items and completed successfully, but no event identifies that the Skill
  file was actually loaded. Phase 4 therefore records host invocation as
  observed and Skill-load causality as unobservable/partial.
- `design-director` is currently synthesized/third-party/partial under the
  Phase 3 inventory and has scripts; `verification-loop` is invalid/rejected.
  Neither may be forced into `PILOT_EXECUTABLE`. A tiny project-local,
  script-free fixture is the only controlled-real fallback, with this reason
  recorded in the packet.
- The app-server may emit MCP startup-status notifications even when the
  pilot policy denies MCP. They are telemetry, not permission or execution
  evidence.

## Decision Log

- Keep Phase 2 and Phase 3 payloads frozen; all Phase 4 code is additive.
- Use the official app-server JSON-RPC process only through a fixed argv,
  `shell=False`, restricted environment, ephemeral thread, read-only or
  workspace-bounded sandbox, denied network and denied approvals by default.
- Bind authorization to capability ID, version, scope and exact package
  fingerprint, then revalidate immediately before the host request.
- Use an explicit project-local execution allowlist. Discovery, routing or
  metadata load never grants execution permission.
- Capture the assistant result as a clearly typed host-response artifact when
  the pilot produces no filesystem artifact; do not claim that it is a
  design asset or a host-written file.
- Mark timeout/cancellation unsupported when the host cannot prove the
  corresponding state. Never convert an unknown host signal into PASS.

## Outcomes & Retrospective

To be completed after the final evidence packet. It must state the support
level, real invocation count, exact pilot fingerprints, global mutation
result, verification result, independent findings and deferred work.

## Context and Orientation

The frozen Phase 2 contracts are in `src/harness_kernel/`; Phase 3 owns
read-only discovery in `phase3_*`. Phase 4 adds focused `phase4_*` modules and
does not change installed Skills or the global Codex configuration. The
project-local `config/`, `tests/fixtures/phase4/`, `evidence/phase-4/` and
`.agent/` trees are the only writable surfaces for this phase.

## Scope and Constraints

- Allowed: one exact, approved capability through the official app-server;
  dry-run and prepare-only modes; bounded context; explicit authorization;
  receipt/telemetry/artifacts/verification; cancellation and timeout paths;
  project-local CLI and evidence.
- Forbidden: arbitrary execution, arbitrary scripts or shell, unrestricted
  network, MCP, providers, subagents, global mutation, package rewriting,
  installation/deletion, production deployment and Skill modernization.
- No new runtime dependency unless a later measurement proves it necessary.
- No raw credentials, full personal paths, or untrusted host payloads in
  public evidence.

## Architecture and Interfaces

- `phase4_models.py`: immutable enums and records for modes, policy,
  authorization, context, host events, receipts, artifacts, verification and
  assurance.
- `phase4_policy.py`: strict project-local policy registry, exact allowlist,
  path/budget checks, stale/fingerprint revalidation and preflight.
- `phase4_host.py`: `CapabilityInvocationAdapter` and Codex app-server
  JSON-RPC implementation. Host-specific protocol details remain here.
- `phase4_execution.py`: lifecycle/state machine, replay guard, dry-run,
  prepare-only and controlled-real orchestration.
- `phase4_evidence.py`: safe project-local artifact/evidence writes, public
  redaction and non-self-referential review manifest helpers.
- `phase4_cli.py`: explicit `invoke` entrypoint; real mode requires both
  `--controlled-real` and an exact fingerprint confirmation.

## Milestones

### M0 — Rebaseline and contracts

Create ADR-013, P4-QB-1, state/backlog transition, allowlist schema and RED
tests before production code.

### M1 — Policy and preflight

Implement exact capability binding, revalidation, trust/compatibility,
workspace/path safety, context budget, forbidden capability declarations and
typed authorization.

### M2 — Host boundary and lifecycle

Implement the fixed Codex app-server adapter, approval denial, bounded event
collection, timeout/cancel handling, host causality classification and the
explicit lifecycle.

### M3 — Result/evidence/verification

Capture only validated project-local artifacts, bind them to the receipt and
immutable acceptance criteria, calculate verification/assurance and generate
sanitized evidence.

### M4 — Pilots and closeout

Run dry-run, safe fallback controlled-real, blocked preferred pilots and all
negative scenarios; run quality gates, independent exact-packet review and
freeze.

## Plan of Work

1. Write RED tests for every contract and negative boundary.
2. Implement the smallest immutable models and policy functions.
3. Implement and unit-test the fake transport seam before the real adapter.
4. Implement the real adapter and run a narrow app-server smoke in a
   temporary/project fixture.
5. Implement the lifecycle engine, result/artifact/verification chain and
   CLI.
6. Run the real host pilot only after dry-run and security tests pass.
7. Generate exact evidence, ask a fresh read-only reviewer to inspect it,
   remediate material findings and rerun all gates.

## Concrete Steps

1. Add P4-QB-1, ADR-013, allowlist schema, fixture layout and control ledger
   records without touching Phase 2/3 evidence.
2. Add unit/integration/eval tests; run the expected RED collection command.
3. Implement contracts, policy and context; make all policy-negative tests
   green.
4. Implement the injected transport and Codex app-server adapter; verify
   fixed command, handshake, skill input, event normalization and approval
   denial.
5. Implement orchestration, safe artifact writes, verification, assurance,
   replay and CLI JSON/human output.
6. Run the Phase 4 pilots and record host observations, including the lack of
   a distinct load event.
7. Run full pytest/coverage/Ruff/mypy/security scans and P4-BENCH-1.
8. Build the exact review manifest, obtain independent review, reconcile the
   append-only state and write `PHASE4-FROZEN.md` only if P4-QB-1 permits it.

## Validation and Acceptance

P4-QB-1 is blocking. It requires Phase 2 and Phase 3 regressions, exact
fingerprint binding, no-execution-without-authorization, project boundary,
no global mutation, honest host causality, timeout/cancel semantics,
artifact/verification binding, policy-negative pilots, security scan,
coverage >=80%, Ruff/mypy, benchmark, independent exact-packet review and
either a valid controlled pilot or an explicit official-host limitation.

## Risks and Human Decisions

- The app-server protocol is official and observed, but model/provider output
  and Skill-load causality are host-managed and may vary. Record the actual
  result and keep Level B/C claims evidence-based.
- A controlled real turn can consume account quota. The pilot is deliberately
  one short, script-free, no-tool turn in an isolated workspace.
- Any host request for command, file, network, MCP, provider or credential
  permission is denied unless a future policy explicitly and independently
  approves it; this phase does not grant such permission.

## Idempotence and Recovery

Dry-run and preflight are repeatable. Controlled-real retries are disabled by
default and duplicate invocation IDs are rejected. If interrupted, recover
from this plan, `.agent/state.json`, append-only ledgers and the latest
evidence; do not rewrite historical Phase 2/3 packets. A changed capability
must be rediscovered and reauthorized.

## Artifacts and Evidence

The final packet lives under `evidence/phase-4/` and includes the host matrix,
execution policy, pilot allowlist, receipts, artifact/verification/telemetry/
security/coverage/benchmark reports, Phase 2/3 regressions, exact review
manifest/attestation, readiness, final report and freeze marker. The external
Skill itself is never copied into the repository.

## Verification Commands

```text
PYTHONPATH=src .venv/bin/pytest -q -p no:cacheprovider
PYTHONPATH=src .venv/bin/coverage run -m pytest -q
PYTHONPATH=src .venv/bin/coverage report --fail-under=80
PYTHONPATH=src .venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/ruff check src tests
PYTHONPATH=src .venv/bin/mypy --no-incremental src
PYTHONPATH=src .venv/bin/python -m harness_kernel.phase4_cli invoke ... --dry-run --json
```
