# Phase 8 promotion decision

## Decision

`CONDITIONAL_PASS`; support level `P8_LEVEL_A_CANDIDATE`. The project-local
frontend-engineering-vNext package and pilot are retained as a bounded
candidate only. They are not promoted, frozen, released or treated as
`VERIFIED_CANDIDATE`.

## Why this is conditional

The package identity, references, deterministic boundaries, eval catalog,
dependency-free pilot, browser render matrix, state captures, accessibility
baseline, interaction observations, contrast, idempotency, performance and
visual review are strong within the supplied local evidence. The official
Phase 4 host cannot load/write/observe the workspace under its enforced
read-only policy, so the required composition chain is not complete and P8
Level B is not met.

## What changed

The additive package adds explicit frontend scope, architecture preservation,
state contracts, responsive/accessibility contracts, evidence binding,
security handoff, deterministic procedures, 60 eval scenarios and a benchmark
matrix. The pilot adds a real local fixture and repairs contrast, form
semantics, idempotency and success-state presentation. No installed/global
skill or frozen phase packet was changed.

## What remains

The official host needs a safe observer/load authority that can be proven in
Phase 4. Runtime evidence also remains bounded to one Chromium instance and
does not execute every structural eval scenario or broad AT/security matrix.

## Promotion condition

Do not promote until a later phase provides native host-load causality, a fresh
read-only verifier that can observe the current packet, and the remaining
runtime/accessibility/security evidence required by the quality bar.
