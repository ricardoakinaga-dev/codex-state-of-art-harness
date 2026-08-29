# ADR-012 — Rebaseline the roadmap for Phase 3 host capability integration

- Status: Accepted for the Phase 3 extension
- Date: 2026-08-28
- Scope: `projects/codex-harness/`
- Supersedes: the sequencing interpretation of `docs/38-implementation-roadmap.md` only
- Does not supersede: the Phase 2 exact packet, contracts, gate or freeze record

## Context

The original roadmap was written before the bounded implementation existed. It
places router, authority/state, verification, Director integration, registry
and telemetry in separate phases, while the current project already has a
frozen local deterministic kernel with those bounded concerns. Its explicit
remaining gap is the real Codex host boundary: read-only discovery, safe
metadata loading, provenance, trust, compatibility, resolution and honest host
load observability.

The official Codex documentation establishes that Skills are directories with
`SKILL.md` plus optional declarative resources, and that Codex discovers
metadata before reading full instructions. It also documents project/user
skill locations and non-merging duplicate names. Those facts are useful
authority for the adapter, but they do not provide a public host-load event
contract for this harness. Host-load causality therefore remains
`UNKNOWN`/`UNAVAILABLE` unless observed by an explicit adapter signal.

## Decision

Phase 3 rebaseline is an additive integration layer around the frozen kernel:

1. Keep Phase 2 execution, registry and router semantics intact.
2. Add a typed `CodexHostAdapter` that performs read-only host inspection,
   root discovery, capability inspection and load-state observation.
3. Build a sanitized `HostSnapshot`, root inventory and observed capability
   manifests from real and fixture paths without executing package content.
4. Resolve trust, compatibility, provenance, duplicates, dependencies,
   conflicts and precedence before bridging selected metadata to the existing
   registry/router.
5. Represent progressive disclosure and load planning separately from actual
   host loading. A planned or prepared context is never a loaded capability.
6. Keep project-local packages authoritative for this project, while treating
   global/system roots as read-only dependencies. No global file or config is
   written.
7. Use the Phase 3 quality bar, evidence packet, benchmark and independent
   review as the new gate. A Phase 2 payload change requires a formal
   supersession record and cannot reuse the Phase 2 attestation.

## Explicit precedence policy

For a capability ID, selection order is:

`explicit pin > project > workspace > approved shared > global > system > external`.

Within the same precedence class, verified/trusted and compatible records win,
then exact version pins, then the highest valid semantic version, then the
lexically smallest canonical path. This policy is owned by the Phase 3
resolver and is intentionally not inferred from the existing Phase 2 registry
origin integer ordering. Rejected, incompatible, stale, conflicted,
ambiguous or divergent records are never overridden by precedence.

## Consequences

The original roadmap remains useful as historical architecture context, but it
cannot be read as evidence that host integration exists. The new extension has
more modules and evidence than a local-only phase, but keeps the execution
kernel stable and makes the real boundary testable. Host-load causality,
provider execution, MCP, shell, network, credential access, installation and
production operation remain outside the Phase 3 authorization.

## Evidence

- `projects/codex-harness/docs/implementation/phase-3-quality-bar.md`
- `projects/codex-harness/evidence/phase-3/README.md`
- Official OpenAI documentation: `https://learn.chatgpt.com/docs/build-skills`
- Official OpenAI documentation: `https://learn.chatgpt.com/docs/agent-configuration/agents-md`
