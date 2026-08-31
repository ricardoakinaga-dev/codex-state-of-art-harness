# ExecPlan — PHASE8.1 Frontend Runtime and Host Composition Closure

## Purpose / Big Picture

Close the bounded promotion gap left by Phase 8. The outcome is a fresh,
project-local evidence packet that exercises the real frontend pilot in a
bounded browser, evaluates promotion-relevant behavior at runtime, runs the
project-local verification-loop-vNext with a structured handoff, and reports
official host-load limitations without inventing causality. Promotion is an
evidence decision, not a target that may be manufactured.

## Progress

- [x] 2026-08-31 12:18 - Recovered Phase 8 as the authoritative prior packet and captured `evidence/phase-8.1/baseline.json` before Phase 8.1 mutation.
- [x] 2026-08-31 12:18 - Declared `P8_1_FEATURE_FREEZE`; frontend package feature changes require a linked `P8.1-FINDING-*`.
- [x] 2026-08-31 12:18 - Reconstructed the inherited one High and three promotion-blocking Medium findings and froze `evidence/phase-8.1/P8.1-QB-1.md`.
- [x] 2026-08-31 12:29 - Probed the supported app-server schema and fresh initialize/skills-list/read-only-thread exchange; public host-load and native browser-observer causality remain unobservable.
- [x] 2026-08-31 — Built the smallest safe runtime fixtures/adapters, executed the fresh frontend run and bound the composed artifact to `P81-COMPOSE-009`.
- [x] 2026-08-31 — Executed the fresh runtime/browser evals and verifier handoff: 33/33 runtime evals and 20/20 verifier checks.
- [x] 2026-08-31 — Obtained independent frontend, visual and capability reviews; reconciled the authoritative packet references and received three `PASS_WITH_LIMITATIONS` verdicts.
- [x] 2026-08-31 — Ran the integrated closeout, produced the final gate/readiness/attestation and set the next gate to the explicitly scoped commit/push.

## Surprises & Discoveries

- Phase 8's prior declared frontend fingerprint is `sha256:d96f162a4400520036a770ece08bd4ace9c3bf3e9e10b3144bdef22b50ea1823`; the current validator observed `sha256:c0cd7c9611a89bdb730b2ba73a06212f4b3d432e06ed4f9792550ff7dacd9342`. This is recorded as a reconciliation gap, not silently resolved.
- The current Phase 4 adapter hard-codes a read-only thread and turn sandbox and rejects `WORKSPACE_WRITE`; the host capability investigation must determine whether a safe supported path exists before changing that adapter.
- The worktree contains pre-existing untracked `.playwright-mcp/` and `projects/codex-state-of-art-harness/`; neither is part of this phase and both must remain untouched and out of the packet.

## Decision Log

- 2026-08-31 — Use a new task `PHASE8.1-001` rather than reopen `PHASE8-001`; Phase 8 is a historical candidate packet and the user supplied a distinct closure scope.
- 2026-08-31 — Keep frontend-engineering-vNext and verification-loop-vNext source packages frozen unless a concrete Phase 8.1 finding proves a bug requires mutation; any such change invalidates prior artifact evidence and creates a new fingerprint.
- 2026-08-31 — Treat the literal host Skill-load event as unknown until the official boundary exposes it. A bounded alternative chain may be considered only when every required digest, identity, timeline and mutation guard is independently observed.
- 2026-08-31 — Use synthetic loopback data only. No external network, credentials, global installation, production mutation, deployment, or unsupported host reverse engineering is authorized.

## Outcomes & Retrospective

The bounded packet is `PASS_WITH_LIMITATIONS` and
`READY_WITH_LIMITATIONS`. The exact composed artifact is `P81-COMPOSE-009`
with tree digest
`sha256:bfd899129937a6c615389796e6d85972ebe7f4572392b362e9e37b256bc3e044`.
Independent frontend, visual and capability reviews all passed with the same
bounded limitations. The official host skill-load event remains unobservable,
so this is a verified candidate with limitations, not full host causality,
production readiness, release approval or security approval. The next safe
phase is native browser-observer/host-load integration; the immediate
control-plane gate is commit/push of only the scoped files.

## Context and Orientation

The repository is a brownfield Python harness with an existing Phase 2–8
control plane, a project-local frontend-engineering-vNext package, a project-
local verification-loop-vNext package, and a dependency-free HTML/CSS/ES2022
Veterinary Emergency Intake pilot served by a Python loopback fixture. Phase 8
proved package coherence and local browser quality but stopped at
`HOST_LOAD_UNOBSERVABLE`. The complete user specification is the attached
file referenced by this task; its required evidence directory is
`projects/codex-harness/evidence/phase-8.1/`.

## Scope and Constraints

In scope: baseline and finding reconciliation; host capability matrix;
formal host-composition interpretation; runtime-eval classification and
traceability; deterministic browser fixtures and observers; fresh frontend
and verifier invocations; workspace mutation/digest binding; responsive,
interaction, accessibility, contrast, idempotency, stale-response and URL
state checks where applicable; security/scanner availability evidence;
regressions; independent reviews; exact packet and promotion decision.

Out of scope: frontend redesign, unrelated feature work, security-review
modernization, another capability modernization, global or installed skill
changes, global Codex configuration, unsupported host reverse engineering,
production/release actions, real credentials, external network, and claims of
production readiness, security approval, accessibility certification, all
browsers, all viewports or full host causality.

## Architecture and Interfaces

The Phase 3 `CodexHostAdapter` performs read-only discovery. The Phase 4
`CodexAppServerAdapter` owns the official app-server JSON-RPC boundary and
currently records host invocation events while treating Skill-load causality
as unobservable. The Phase 4 policy and execution engine own authorization,
workspace confinement, replay protection, receipts and host-result handling.
The Phase 8 pilot owns its local fixture and browser-visible behavior. Phase
8.1 evidence scripts must consume these boundaries rather than create a
parallel unverifiable execution path. The project-local verifier receives a
structured handoff and remains read-only and separate from the builder.

## Milestones

### M1 — Recovery, baseline, and frozen bar

Demonstration: baseline, task, plan, feature-freeze declaration, current
finding ledger and `P8.1-QB-1` resolve and are linked from the control plane.
Exit: the current package identities and open findings are directly observed,
and the acceptance bar is frozen before implementation.

### M2 — Host/composition contract and runtime classification

Demonstration: capability matrix, interpretation, composition contract and
60-eval classification distinguish official host facts, harness facts,
inferences and unknowns. Exit: a bounded execution route and its failure
semantics are explicit; unsupported routes remain blocked.

### M3 — Fresh real frontend runtime packet

Demonstration: a clean isolated pilot workspace has pre/post digests, a fresh
frontend invocation receipt, actual build/check output, browser captures at
1440x900, 1024x768, 768x1024 and 390x844, and meaningful runtime assertions.
Exit: required browser scenarios pass or are explicitly blocked with evidence.

### M4 — Fresh verifier composition and attack tests

Demonstration: a current structured handoff, fresh verifier receipt,
composition proof, ordered timeline, and negative/attack tests for wrong
identity, stale evidence, alternate producer, manual mutation and mismatched
verifier artifacts. Exit: the proof is `PROVEN_WITH_HOST_LOAD_EVENT`,
`PROVEN_WITH_OBSERVABLE_ALTERNATIVE_CAUSALITY`, `PARTIAL` or `BLOCKED` honestly.

### M5 — Integrated review and decision

Demonstration: full regression, coverage, Ruff, mypy, security/scanner report,
fresh independent reviews, exact manifest/attestation, readiness and final
report. Exit: promote only if all required gates and proof conditions pass;
otherwise retain candidate status with explicit blockers.

## Plan of Work

1. Recover current state, inspect nested instruction scope, and preserve the
   unrelated untracked directories.
2. Recompute current frontend/verifier fingerprints and reconstruct the High
   and Medium ledgers from actual code, receipts, evals and reviews.
3. Define `P8.1-QB-1` with binary gates, targets, evidence methods, validity,
   priorities and baseline; do not lower the Phase 8 bar for convenience.
4. Investigate the supported Codex app-server and browser surfaces. If a
   safe writable host path is available, change only the necessary Phase 4
   boundary under a finding; otherwise build the strongest project-local
   observable chain and retain the host limitation.
5. Classify all structural evals and implement only promotion-relevant,
   deterministic runtime cases, including stale-response and URL state when
   applicable or a documented non-applicability proof.
6. Prepare a clean isolated workspace, capture pre-run state, run the frontend
   path, observe workspace mutation independently, build/check the artifact,
   and capture fresh browser evidence and manifests.
7. Freeze the frontend artifact for verification, run a fresh
   verification-loop-vNext handoff, bind the proof and timeline, and attack
   every causal link with negative tests.
8. Repair only confirmed material findings. After each repair, rerun affected
   runtime evidence and the credible regression surface.
9. Run security and dependency checks, full suite and phase regressions,
   independent reviews, exact packet reconciliation, and final readiness.

## Concrete Steps

1. Validate JSON/JSONL control-plane inputs and resolve the new active task
   against the recovered Phase 8 history.
2. Inspect the actual `codex` executable, app-server help/protocol behavior,
   browser MCP availability, pilot source and verifier contract.
3. Add/update only Phase 8.1-owned evidence scripts, fixtures, tests and
   reports; keep source package fingerprints stable unless a finding demands a
   source fix.
4. Execute the real pilot and browser procedures with deterministic loopback
   data, pinned viewport/browser metadata, fresh timestamps and no external
   network.
5. Re-run the exact package validator, focused tests, browser assertions,
   verifier regression and full suite after material changes.
6. Have read-only independent reviewers inspect the actual packet and return
   criterion-level evidence, largest gap, severity, confidence and verdict.
7. Reconcile the manifest, attestation, gate, backlog, execution log,
   verification ledger and runtime state in canonical transaction order.

## Validation and Acceptance

`P8.1-QB-1` is the acceptance authority. Required targets include: fresh
authoritative inputs; feature-freeze compliance; current exact frontend and
verifier fingerprints; current High/Medium ledger; valid host interpretation;
fresh frontend/build/browser/runtime evidence; workspace mutation binding;
fresh verifier composition; valid timeline and attack tests; zero actionable
High/Medium/Critical findings; zero global/installed mutations; line and branch
coverage at least 80%; full tests and Phase 2–8 regressions green; Ruff and
mypy pass; bounded security acceptable; and fresh independent exact-packet
review. Each target must cite a current typed verification record or an
explicit, evidence-backed blocked/non-applicable result.

Known-bad harness checks must fail for wrong capability, workspace, source,
artifact, browser, verifier, stale screenshot, manual write and structural
runtime mislabel. A waiver may cover an unobservable host-load event, never an
unproven composition chain.

## Risks and Human Decisions

The primary risk is false promotion through an opaque host: a different
capability, stale artifact, manual mutation or unrelated verifier receipt may
look authoritative. Controls are exact fingerprints, task/run/invocation
IDs, workspace pre/post digests, changed-file capture, browser/artifact/source
digests, ordered monotonic timeline, a no-alternate-producer guard and
independent review. A remaining HIGH/CRITICAL residual acceptance or release
approval is a human boundary and must not be inferred. Security scanner
unavailability remains a limitation, not `SECURITY_APPROVED`.

## Idempotence and Recovery

All local fixture requests use synthetic data and bounded retry keys. A fresh
attempt gets a unique task/run/invocation identity and an isolated workspace;
replaying the same receipt must be rejected or identified as a replay. If a
run stops after workspace mutation, preserve its artifacts, inspect the
workspace and ledger, and resume only after idempotence and preconditions are
verified. Never delete the prior Phase 8 packet or the unrelated untracked
directories. If host capabilities remain unavailable, record `BLOCKED` or
`PARTIAL`, retain the candidate, and take the next safe evidence action.

## Artifacts and Evidence

Current artifacts are under `projects/codex-harness/evidence/phase-8.1/` and
must include the user-requested baseline, quality bar, finding ledger, host
capability matrix/interpretation, composition proof/timeline/receipt, runtime
classification/traceability/report, frontend/browser/verifier reports,
security/scanner/coverage/test/regression reports, independent reviews,
review manifest/attestation, promotion decision, readiness and final report.
The canonical control plane is `projects/codex-harness/.agent/`; its plan,
backlog, append-only execution log and verification ledger must point to the
same `PHASE8.1-001` scope. Exact packet manifests exclude their own mutable
control records to avoid recursive digests and include all immutable evidence
needed by the exact-packet reviewer.
