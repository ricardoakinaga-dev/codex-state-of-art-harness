# Architecture boundaries

## Preserve before extending

Inspect the repository's actual runtime, entry points, routes, build/test
scripts, component primitives, tokens, fonts, assets, data clients and
deployment assumptions before choosing a frontend stack. Keep the existing
boundary when it can satisfy the task. A framework, router, state library,
component kit or design-system layer is not a quality goal by itself.

For a proposed new dependency or abstraction record:

- the concrete problem the existing boundary cannot solve;
- the smallest alternative considered;
- dependency/license/runtime provenance;
- blast radius, maintenance cost and rollback path;
- build, browser and test evidence that the new boundary works.

## Ownership

The specialist owns executable frontend implementation inside the granted
workspace. `design-director` owns visual strategy and art direction;
`verification-loop-vnext` owns factual evidence and freshness;
`security-review` owns final security assurance; `e2e-testing` and
`tdd-workflow` provide optional test overlays; `coding-standards` provides
general code quality. No specialist changes the authority of another role.

## Composition rule

Prefer a single coherent vertical slice over a premature library. Define the
semantic surface and repeated decisions first. Extract a primitive only when
two or more consumers share anatomy, states, keyboard behavior and responsive
contract. Avoid component soup, prop booleans that encode unrelated modes,
and abstractions that hide the API or browser boundary.

## Deliverable

The implementation plan names the route, user/job, primary action, stack,
changed files, state ownership, contracts, required observers, tests,
responsive transformations, security handoff and stop conditions. A changed
stack or architecture requires a new acceptance decision and fresh evidence.
