# ADR-014 — Phase 5 Design Director Composition Pilot

## Status

Accepted for the bounded Phase 5 pilot. This ADR is additive to the frozen
Phase 2, Phase 3 and Phase 4 packets. It does not authorize Skill
modernization, arbitrary orchestration, production use, or a global mutation.

## Context

The frozen Phase 4 boundary proves that the official Codex app-server can
receive one exact Skill input and return a bounded host response, but it does
not prove that a Skill writes a visual artifact or that Skill-load causality is
observable. The next useful experiment is therefore a narrow vertical slice:
route one design task to the installed `design-director`, materialize only a
strictly validated response-derived HTML artifact in a project fixture, render
it at desktop and mobile sizes, and send a blind packet to a separate
verifier/critic.

The current host inventory reports `design-director` as a synthesized local
package with a third-party trust assessment, partial compatibility and
metadata-only script handling. `verification-loop` is currently invalid and
rejected by Phase 3. Those observations cannot be silently upgraded into
general execution permission.

## Decision

Implement a specialized, fixed Phase 5 composition graph:

```text
DESIGN_BUILDER
  → STRUCTURAL_VERIFICATION
  → VISUAL_CRITIQUE
  → OPTIONAL_REPAIR (at most one)
  → FINAL_VERIFICATION
  → ASSURANCE
```

The graph is not a general workflow engine. It has one fixed task profile,
one primary capability, typed handoffs, explicit role ownership, immutable
acceptance criteria and finite invocation budgets. A builder may design and
produce a response-derived artifact; it may not verify, lower the quality bar,
approve its own work, or alter policy. Verification and critique may inspect
only the artifact and blind packet. Repair belongs to the builder and always
invalidates prior artifact-bound verification.

The primary capability is eligible only when all of the following are true at
the moment of the run:

- the exact ID, version, scope, canonical path, package fingerprint and
  manifest fingerprint match the project allowlist;
- the package is rediscovered and revalidated immediately before invocation;
- the requested route is the explicitly approved response-only builder mode;
- no dependency, duplicate divergence, stale byte, rejected trust state or
  incompatible status blocks the route;
- package scripts, providers, tools, network, MCP, shell, credentials and
  subagents remain denied and are not executed;
- the host executable/interpreter binding and the project fixture are safe and
  bounded.

This is a narrow eligibility decision, not a promotion of the installed Skill
to native or generally trusted status. If any condition fails, the route is
`BLOCKED` and the evidence records the exact reason. The external
`verification-loop` capability is not forced into the route; its current
invalid/rejected assessment records `EXTERNAL_VERIFIER_NOT_ELIGIBLE` and the
Harness-native structural verifier plus an independently separated critic are
the allowed fallback.

The builder must return one bounded JSON envelope containing a complete
standalone HTML document. The Harness validates and writes that response into
the isolated fixture. This is an artifact derived from a real host response,
not a claim that the host wrote a file. Only HTML/CSS/SVG and local fixture
content are accepted; scripts, remote URLs, event-handler attributes,
credentials, path traversal and oversized output are rejected.

The visual contract requires a fictional premium veterinary emergency center
hero with product-specific copy, semantic HTML, deliberate type/color/spacing
tokens, an original code-native visual mark, desktop/mobile layout behavior,
visible focus, no invented proof, and no generic startup-template treatment.
The artifact is rendered through the available browser boundary at 1440×900
and 390×844. A current native screenshot is required for any visual approval.

## Consequences

Positive consequences:

- The experiment measures whether composition adds value beyond the existing
  native verification path without weakening the Phase 4 authority boundary.
- Artifact lineage, stale invalidation, reviewer independence and repair cost
  are explicit and auditable.
- The installed design-director remains an immutable external input; no global
  Skill or configuration is rewritten.
- A useful visual artifact can be evaluated even though the current host does
  not expose host-written files or distinct Skill-load causality.
- A blocked secondary capability degrades to a named, bounded native fallback
  rather than an invented multi-capability claim.

Costs and limitations:

- Response-derived HTML is narrower than arbitrary frontend implementation and
  cannot prove host file-write behavior.
- Browser capture, model output and host load causality remain external or
  partially observable dependencies.
- The result is pilot evidence (`PILOT_COMPOSITION_EVIDENCE`), not causal proof
  that the composition graph improves every task or every Skill.
- The frozen Phase 4 packet must be re-regressed because new source and tests
  change the repository, but its historical evidence is never rewritten.

## Rejected alternatives

- Editing or copying the installed `design-director`: rejected because it
  destroys provenance and violates the read-only package boundary.
- Executing package scripts or arbitrary shell to manufacture a design:
  rejected because it would be a different capability path.
- Treating `verification-loop` metadata as executable: rejected by its current
  invalid/rejected Phase 3 status.
- Allowing a dynamic graph, unlimited retries or builder self-approval:
  rejected because the pilot needs a finite, reviewable causal boundary.
- Deploying the fixture through a hosting connector: rejected because this is a
  local evidence pilot and production state is out of scope.

