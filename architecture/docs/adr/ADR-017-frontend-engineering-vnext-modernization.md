# ADR-017 — Frontend Engineering vNext Modernization

## Status

Accepted for the bounded Phase 8 modernization pilot. This ADR is additive to
the frozen Phase 2–7.3 packets. It does not authorize editing or installing
the current capability, global state changes, deployment, production use,
accessibility certification, or an AAA claim.

## Context

The installed `frontend-patterns` skill is useful React/Next.js guidance with
strong component, state, form, accessibility and performance examples. Its
observed package is a legacy `SKILL.md` plus agent metadata, without a native
manifest, typed input/output contract, criterion evidence, bounded stop model,
deterministic procedures, browser/render evidence contract, or explicit
security handoff. The local provenance snapshot also shows the installed bytes
and the captured upstream bytes are different, while neither carries a
portable versioned package identity.

The project already has a Python standard-library harness and proven static
HTML/CSS browser fixtures. It has no Node application manifest, local
`node_modules`, or importable Playwright JavaScript module. Introducing a
frontend framework solely for this pilot would create dependency and build
surface unrelated to the modernization question.

## Decision

Create `projects/codex-harness/.harness/capabilities/frontend-engineering-vnext`
as a project-local `SPECIALIST` in the `FRONTEND_ENGINEERING` domain. It owns
frontend implementation discipline within a bounded task:

- preserve sound existing architecture and select the smallest supported
  stack instead of imposing React, Next.js or a component library;
- establish semantic structure, tokens, layout geometry and component
  contracts only where the surface needs them;
- separate local/UI/URL/server/derived state and define loading, success,
  empty, error and retry behavior;
- treat keyboard, focus, labels, headings, names, non-color cues, contrast,
  reduced motion, touch targets and reflow as implementation criteria;
- bind responsive behavior to observed viewport evidence, including an
  intermediate width;
- use real tests, build/type/syntax/lint checks, browser interaction and
  native screenshots before visual claims;
- surface performance observations and a security-review handoff without
  self-approving either domain;
- hand off an immutable artifact/evidence packet to the read-only verifier.

The isolated pilot is a fictional Veterinary Emergency Intake Dashboard,
implemented in the existing web stack: HTML5, CSS and ES2022 JavaScript,
served by a deterministic local Python fixture. It has no external network,
third-party scripts, analytics, remote fonts, real personal data or production
backend. The fixture exposes deterministic queue loading, empty/error/retry
and intake success/error responses so the browser evidence covers the real
workflow rather than a static screenshot.

## Capability boundaries

`frontend-engineering-vnext` is not `design-director`: it owns executable
frontend engineering contracts and implementation, while design-director owns
visual strategy, art direction, visual direction and critique. It is not
`verification-loop-vnext`: the verifier owns factual evidence and freshness,
not implementation or visual judgment. It is not an orchestrator, reviewer,
assurance authority, security authority, release authority or generic coding
skill. `e2e-testing`, `tdd-workflow`, `coding-standards`, `security-review`,
`design-director` and `documentation-lookup` remain orthogonal overlays whose
activation and limitations are recorded explicitly.

## Composition and promotion

The bounded composition is:

```text
ROUTER → FRONTEND_ENGINEERING_SPECIALIST → DESIGN_DIRECTOR? →
VERIFICATION_LOOP_VNEXT → INDEPENDENT_VISUAL_REVIEW → REPAIR? →
VERIFICATION_LOOP_VNEXT → ASSURANCE
```

The optional design-director step is only for visual strategy; a visual critic
never edits and the builder never approves its own work. The package remains
`EXPERIMENTAL`, `CANDIDATE` or `VERIFIED_CANDIDATE` only as exact evidence
supports. It cannot become `STABLE` in Phase 8.

## Consequences

The pilot tests whether a narrow, evidence-shaped frontend specialist adds
useful contracts around an existing web stack without importing a framework,
dependency or design system. The cost is a larger evidence packet and an
explicit limitation around the absence of a TypeScript compiler and a
Playwright JS import in the local project; native browser MCP evidence is used
where available, and all unavailable checks remain marked as such.

## Rollback and future migration

Rollback is removal of the additive project-local package, pilot and Phase 8
evidence in a future change, or selection of the frozen current skill. No
installed/global package is edited or replaced. A future React/TypeScript
migration requires a new authority decision, dependency provenance, build
matrix, behavioral comparison, exact review packet and explicit migration
plan.
