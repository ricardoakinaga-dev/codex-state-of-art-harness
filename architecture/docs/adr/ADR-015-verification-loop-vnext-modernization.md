# ADR-015 — Project-Local Verification Loop vNext

## Status

Accepted for the bounded Phase 6 modernization candidate. This ADR is
additive to the frozen Phase 2–5 packets. It does not authorize migration,
global installation, production use or an AAA claim.

## Context

The installed `verification-loop` is a small Claude-oriented instruction file
at `/home/ricardo/.agents/skills/verification-loop`. It has no native manifest,
typed input/output contract, criterion-level evidence binding, freshness model,
role separation, deterministic tool policy or explicit bounded stop contract.
Phase 3 therefore records it as invalid/rejected and Phase 5 correctly blocks
it as the secondary verifier. Upstream and fork snapshots provide useful
lineage but do not make the installed bytes Codex-native or executable.

The Harness already defines contracts for capability packages, composition,
verification, assurance, evals and modernization. A project-local candidate
can test the missing boundary without changing the original package.

## Decision

Create `projects/codex-harness/.harness/capabilities/verification-loop-vnext`
as a separate native package. Its kernel is a concise router and its detailed
behavior is expressed through project-local typed contracts, deterministic
read-only procedures, references and eval fixtures. The package identity is
bound to exact file and manifest digests before discovery, preflight or host
invocation.

The capability owns factual verification only:

- input identity, scope, criteria, artifact/evidence refs, tool policy and
  freshness;
- deterministic procedures and bounded reports;
- Claim → Procedure → Evidence → Status records per required criterion;
- explicit gaps, limitations, confidence and stop conditions.

It must not implement or claim:

- artifact creation, design direction, visual quality judgment, repair,
  orchestration, assurance or release authorization;
- arbitrary command execution, network/MCP/provider/credential use,
  subagents or mutation of the inspected workspace;
- builder self-approval or acceptance-criteria mutation.

The host route is conditional. Phase 3 must discover the project-local native
package, the safe loader must load only bounded metadata, and Phase 4 must
reach `PILOT_EXECUTABLE` with a read-only, exact-fingerprint authorization
before a real host invocation. If host causality or a required tool is
unavailable, the result is explicitly blocked/unknown and the route does not
pretend to be a real external capability.

## Consequences

Positive:

- The old package and its provenance remain intact.
- Verification becomes auditable at criterion, procedure and evidence level.
- Stale artifact lineage and role/authority collisions fail closed.
- Native deterministic checks can be regression-tested independently from
  qualitative review and assurance.
- The package can be compared against current, upstream and native baselines
  with context and failure cost visible.

Costs and limitations:

- The candidate duplicates no old text wholesale and therefore may not cover
  every ecosystem-specific command without an explicit adapter.
- Real host load remains an observation boundary and may be unavailable.
- Passing local evals supports candidate verification, not universal quality,
  production readiness, causal improvement or AAA.

## Rejected alternatives

- Editing the installed package: rejected because it destroys the forensic
  current reference and violates the additive modernization boundary.
- Copying the installed/upstream `SKILL.md` into the project package:
  rejected because it preserves portability debt without a native contract.
- Treating `eval-harness`, `gauntlet-loop` or a native fallback as the vNext
  verifier: rejected because those capabilities have separate ownership.
- Allowing a verifier to approve visual quality or release: rejected because
  review and assurance have distinct authority.
