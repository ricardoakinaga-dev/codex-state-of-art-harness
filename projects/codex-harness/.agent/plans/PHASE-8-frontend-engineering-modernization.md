# ExecPlan — PHASE8 Frontend Engineering vNext Modernization

## Objective

Modernize the installed `frontend-patterns` guidance as an additive,
project-local Codex-native frontend specialist and prove it on one isolated,
fictional Veterinary Emergency Intake Dashboard. The current installed skill,
the upstream snapshot, and frozen Phase 2–7.3 packets are read-only
authorities. The result may remain a candidate with limitations; it must not
claim migration, production readiness, universal frontend superiority,
accessibility certification, or stable promotion.

## Authorities and frozen boundaries

- User specification: `/home/ricardo/.codex/attachments/7de8e2c5-7d4a-4f3c-8efe-5fa94390f8de/pasted-text-1.txt`.
- Current skill snapshot: `evidence/phase-8/current-frontend-patterns-snapshot.json`.
- Upstream/current analysis: `evidence/phase-8/upstream-analysis.md` and
  `evidence/phase-8/current-capability-analysis.md`.
- Quality bar: `evidence/phase-8/P8-QB-1.md`.
- Architecture decision: `../../architecture/docs/adr/ADR-017-frontend-engineering-vnext-modernization.md`.
- Frozen prior authorities: `evidence/phase-{2,3,4,5,6,7,7.1,7.2,7.3}/` and
  their freeze/readiness reports.
- Installed current skill: `/home/ricardo/.agents/skills/frontend-patterns/`;
  it is forensic input only and must not be edited.

## Scope

In scope: one project-local `frontend-engineering-vnext` specialist package;
typed declarative contracts; references for architecture/state/forms/
responsive/accessibility/performance/security handoff; deterministic package
validators and eval fixtures; a local no-dependency web pilot; real Phase 3
discovery; Phase 4 dry-run/prepare-only preflight; browser render and
interaction evidence at 1440×900, 1024×768, 768×1024 and 390×844; automated
and manual accessibility checks; independent visual critique; at most one
repair; fresh final verification; exact evidence, regression and manifest
closure.

The pilot uses the existing project web stack: HTML5, CSS, JavaScript ES2022,
the Python standard-library fixture server, and the available browser MCP.
No React/Vite/TypeScript dependency is introduced because the project has no
existing Node application or installed frontend dependency graph. This is a
deliberate architecture-preserving decision, not a framework preference.

## Non-goals

Do not edit or install the current skill; do not modify global Codex config;
do not add external network calls, analytics, third-party scripts, fonts or
assets; do not build a generic component library; do not replace the existing
Phase 2–7.3 packets; do not deploy; do not claim `PRODUCTION_READY`,
`AAA_VERIFIED`, `STABLE`, `SECURITY_APPROVED`, `ACCESSIBILITY_CERTIFIED`,
`WCAG_CERTIFIED`, `PIXEL_PERFECT`, `ALL_BROWSERS_VERIFIED`,
`ALL_VIEWPORTS_VERIFIED`, `UNIVERSAL_FRONTEND_SUPERIORITY`,
`CAUSAL_SUPERIORITY`, or `FULL_HOST_CAUSALITY`.

## Quality bar and owners

`P8-QB-1` is frozen before implementation. The lead owns the control plane,
evidence and integration. The package lane owns only
`.harness/capabilities/frontend-engineering-vnext/**`; the pilot lane owns
only `evidence/phase-8/pilots/frontend-engineering/app/**` and its pilot
tests/fixture; reviewers are read-only and receive a blind packet.

## Work sequence

1. Capture current package/upstream/native gap and freeze `P8-QB-1`.
2. Write RED contract/package/pilot tests before their implementations.
3. Implement the local capability package and deterministic validators/evals.
4. Implement the pilot with a local deterministic API, all required states,
   responsive layout and keyboard/a11y behavior.
5. Run package checks, Phase 3 discovery, Phase 4 preflight, build, syntax,
   lint, tests, browser interaction, native renders and evidence gates.
6. Obtain a fresh read-only visual critic. Apply no more than one material
   repair; after any repair rerender and rerun the full required verification.
7. Run independent capability/integration/security reviews, prior-phase
   regressions, exact manifest/attestation, readiness and freeze decision.

## Stop conditions

Stop or downgrade explicitly on `BLOCKING_TEST_FAILURE`, `MISSING_REQUIRED_TOOL`,
`MISSING_REQUIRED_CONTEXT`, `UNSAFE_INPUT`, `SECURITY_REVIEW_REQUIRED`,
`MISSING_RENDER`, `MISSING_INTERACTION_EVIDENCE`, `SCOPE_EXPANSION_REQUIRED`,
`NO_PROGRESS`, `REPEATED_FAILURE`, `OSCILLATION`, `BUDGET_EXHAUSTED`, or
`HUMAN_DECISION_REQUIRED`. Unknown or unavailable observations remain unknown;
they are never converted to PASS.

## Completion contract

The highest permitted result is an evidence-backed `PASS_WITH_LIMITATIONS` at
the directly observed support level, or an honest `CONDITIONAL_PASS`/
`BLOCKED` result. Phase 8 is frozen only after the current packet is internally
consistent, the render/source/artifact digests bind, the final verifier is
fresh, the independent reviews are recorded, and every limitation is named.
No next phase is implemented here.
