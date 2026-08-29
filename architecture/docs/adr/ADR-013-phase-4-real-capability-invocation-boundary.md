# ADR-013 — Phase 4 Real Capability Invocation Boundary

## Status

Accepted for the bounded Phase 4 pilot. This ADR does not authorize arbitrary
execution or change the frozen Phase 2/Phase 3 contracts.

## Context

Phase 2 delivers a deterministic project-local execution kernel. Phase 3
delivers read-only discovery, declarative loading plans, trust,
compatibility, resolution and a router bridge. Neither phase executes an
installed Codex Skill or claims host-load causality.

The next architectural question is whether one real capability can be
invoked through the supported Codex host boundary while preserving exact
provenance, authorization, isolation, observability and verification. It
belongs in Phase 4 because it crosses from describing capability bytes to
requesting a host-managed turn and therefore requires a new trust and
rollback boundary.

## Decision

Build one additive `CapabilityInvocationAdapter` backed by the official Codex
app-server JSON-RPC protocol. The adapter owns protocol details; the Harness
owns policy, exact package binding, preflight, budgets, receipts, artifact
validation, verification and assurance.

Every controlled request binds capability ID, version, scope, package
fingerprint, task/run IDs, context digest, authorization expiry and explicit
mode. The package is revalidated immediately before the host request. No
authorization or approved pilot means no host request.

The host command is resolved to absolute Codex and interpreter paths, with
both SHA-256 fingerprints bound into the controlled-real policy and
authorization and rechecked immediately before process creation. The exact
argv is retained, including repeated option tokens. Any host event identifying
tool, shell, file, network, MCP, provider, credential or subagent activity is a
fail-closed violation of this pilot, even if the host labels the event
completed. The package is also revalidated after host completion; a mutation
during the turn is a fail-closed TOCTOU failure.

The initial policy denies shell, scripts, network, MCP, providers, credentials,
arbitrary tools, file changes and subagents. The pilot uses an ephemeral host
thread and an isolated project workspace. The only host input capability is a
named, exact `skill` item plus a bounded task message. Host approval requests
are declined by default.

The preferred `design-director` and `verification-loop` candidates are not
automatically executable. Current Phase 3 evidence marks `design-director`
as synthesized/third-party/partial and script-bearing, and
`verification-loop` as invalid/rejected. If they remain ineligible, a small
project-local, script-free fixture is the explicit fallback. This is not a
copy or modernization of either installed Skill.

The host emits turn/item lifecycle events and accepts the typed `skill` input,
but a current local probe emitted no distinct Skill-load event. The adapter
counts and summarizes every parsed protocol message for the complete client
session, including messages consumed while waiting for setup responses, and
fails closed on any MCP event. Phase 4 may claim real host invocation and
execution only to the extent the receipt shows them; it must record Skill-load
causality as partial/unobservable rather than fabricating `HOST_LOAD_OBSERVED`.

## Consequences

Positive consequences:

- Real host semantics are exercised through a supported integration surface.
- Exact-byte authorization and project-local policy prevent discovery from
  becoming execution permission.
- Host executable and interpreter provenance are independently pinned and
  receipt-verified; archived attempt evidence is hash-bound before it affects
  aggregate attempt counts.
- The lifecycle and receipt make each consequential transition auditable.
- Dry-run, prepare-only and blocked paths are safe defaults; controlled-real
  requires explicit opt-in and fingerprint confirmation.
- Phase 2/3 remain independently regression-testable and historically
  frozen.

Costs and limitations:

- The host process and model response are external runtime dependencies.
- A real turn may be observed without proving that the Skill file influenced
  the model; Level B is the strongest honest outcome absent a load event.
- Host-owned internal state may exist, but the Harness must detect/document
  project and global before/after effects (including global `.codex/skills`)
  and never write installed packages.
- Cancellation, tool calls and host-side artifacts may be unsupported; those
  cases become explicit limitations or blocked results.

## Relationship to future work

- Skill modernization remains deferred. Installed Skills are read-only inputs.
- Directors may later receive a richer artifact workflow only after this
  boundary has independent evidence; this pilot does not edit a Director.
- MCP/providers/subagents remain denied and are not inferred from metadata.
- Rollback means discarding project-local Phase 4 artifacts/evidence and
  disabling the project policy entry; no global package or configuration
  rollback is needed because this phase does not mutate them.

## Rejected alternatives

- Running Skill scripts or arbitrary shell to simulate host behavior: rejected
  because it would erase the security boundary and fake host causality.
- Copying installed Skills into the repository: rejected because it creates a
  shadow package and invalidates exact external provenance.
- Driving an interactive CLI with keystrokes: rejected because it is not a
  reliable, explicit or auditable host invocation contract.
- Treating `skills/list` or a successful turn as proof of Skill loading:
  rejected because discovery/turn completion do not expose that causal fact.
