# 37 — Repository Structure Proposal

## Target

```text
harness/
├── core/              # envelopes, lifecycle, policy boundary
├── router/            # classifiers, registry queries, route decisions
├── directors/         # domain strategy and quality profiles
├── specialists/       # domain capability packages/adapters
├── verification/      # procedure/evidence/report interfaces
├── assurance/         # reviewers, gauntlet, stop controller
├── telemetry/         # event schema, correlation, redaction
├── evals/             # scenarios, fixtures, oracles, benchmarks
├── registry/           # manifests, versions, conflicts, provenance
├── contracts/          # canonical machine-readable schemas
├── adapters/           # Codex host/native tool/provider boundaries
├── state/              # durable run/ledger/recovery state
├── docs/               # narrative architecture and ADRs
└── tests/              # unit/integration/contract/e2e/eval checks
```

## Justificativa

- `core` owns invariants, not domain policy;
- `router` isolates classification/activation cost;
- `directors` own strategy per domain;
- `specialists` avoid a generic god module;
- `verification` and `assurance` are physically separable review boundaries;
- `telemetry` and `state` make continuity/causality explicit;
- `evals` prevent promotion by prose;
- `registry/contracts` create one source of truth for interfaces;
- `adapters` contain host/provider drift;
- `docs` preserves decision/proposal history.

## Dependency direction

```text
adapters → core
contracts → core/router/directors/specialists/verification
registry → router/directors/context
router → directors (proposal only)
directors → specialists/tools through graph/contracts
specialists → tools/adapters, not assurance authority
verification ← integrated artifacts/tools
assurance ← verification/review/evals
telemetry ← every boundary, owns no product behavior
state ← lifecycle/ledgers, owns no quality interpretation
```

No circular Director→Assurance→Builder dependency. `docs/` is authoritative for design intent but does not import runtime code.

## Monorepo versus packages

Begin as one repository/modules until ownership, permission, release or failure boundaries prove a package split. A separate service for every directory is overengineering. Split physical deployment only for security isolation, independent scale/reliability, team ownership or host/provider lifecycle.

## First vertical slice future

The first implementation slice should be: `TaskEnvelope → TaskProfile → RouteDecision → one capability invocation → EvidenceRecord → VerificationReport → RunSummary`, with no multi-agent fan-out. It proves the core public/evidence boundary before adding Directors or providers.

## Non-goals of this proposal

This tree is not created as runtime in the current phase. It does not prescribe language, database, queue, cloud, model, host hook, or deployment topology until a future SPEC proves the need.
