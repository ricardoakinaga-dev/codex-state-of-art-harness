# ADR-016 — Backend Engineering vNext Modernization

## Status

Accepted for the bounded Phase 7 modernization pilot. This decision is
additive to the frozen Phase 2–6 packets. It authorizes a project-local
candidate and an isolated fictional backend fixture; it does not authorize
editing or installing the current capability, production work, global state
changes, destructive migration, or an AAA claim.

## Context

The installed `backend-patterns` capability is a useful, compact pattern
reference, but its observed package is a legacy `SKILL.md` plus one agent
metadata file. It has no native package manifest, typed input/output
contracts, criterion-level evidence, bounded stop model, deterministic
procedures, migration safety contract, or explicit handoff to verification.
Its examples cover Node.js, Express, Next.js and Supabase while the Harness
must also reason about the actual repository/runtime and avoid importing a
favorite architecture by default.

The Harness already owns the surrounding concerns through separate
capabilities and contracts: `api-design` may specify or review an API,
`coding-standards` owns general code quality, `tdd-workflow` is an optional
testing overlay, `security-review` is the final security authority when its
triggers are met, and `verification-loop-vnext` performs factual read-only
verification. A backend specialist should connect those boundaries without
duplicating them.

## Decision

Create `projects/codex-harness/.harness/capabilities/backend-engineering-vnext`
as a `SPECIALIST` in the `BACKEND_ENGINEERING` domain. The package owns the
minimum backend-specific execution discipline needed to inspect, model, plan,
implement and hand off a real backend change:

- preserve existing sound architecture and name material boundaries;
- declare API, validation, authorization, error, persistence and transaction
  contracts when the task reaches those boundaries;
- use database constraints and explicit idempotency/concurrency behavior when
  an invariant can be violated by retries or races;
- plan migrations with compatibility and rollback evidence, stopping before a
  destructive operation without explicit authority;
- make reliability, performance and observability proportional to the risk;
- emit a structured implementation handoff for read-only verification;
- stop on unsafe migration, missing context/tooling, security handoff,
  repeated failure, scope expansion or no progress.

The package must not own visual design, frontend UX, final security assurance,
release approval, orchestration, generic coding advice, unrelated schema
migrations, or arbitrary tools. It may identify a security handoff, but it
cannot self-certify security. It may receive an API contract from `api-design`,
but it owns implementation within the agreed boundary. It may use the
TDD-oriented workflow as an overlay, but the package's minimum tests remain
risk-shaped rather than ceremony-driven.

The first pilot uses a disposable, fictional Veterinary Appointment API in the
existing Python 3.12 standard-library environment. The fixture exercises a
real HTTP boundary, SQLite persistence, migration, authorization abstraction,
transactional booking, idempotency, conflict constraints, tests and structured
observability without adding a framework or dependency solely for the
benchmark.

## Consequences

Positive consequences are a small high-signal router, explicit responsibility
boundaries, safer data/API decisions, evidence-backed handoff and measurable
composition with the existing verifier. The pilot also tests whether the
specialist improves real software delivery rather than merely producing a
longer instruction file.

Costs are additional contracts, evidence and a bounded host write surface.
The write surface is limited to the isolated fixture workspace, with network,
shell, MCP, providers, credentials and arbitrary scripts denied. The candidate
will remain `EXPERIMENTAL`, `CANDIDATE` or `VERIFIED_CANDIDATE` only as directly
supported by exact evidence; it will not become `STABLE` in this phase.

## Rollback and future migration

Rollback is removal of the additive project-local candidate and pilot fixture
from a future commit, or selection of the frozen current capability. No
installed/global package is edited, moved or replaced. The pilot migration is
disposable and must prove its own rollback/consistency behavior; it is not a
production schema migration. Any future migration of users from
`backend-patterns` requires a new authority decision, compatibility matrix,
behavioral comparison, exact review packet and an explicit deprecation plan.
