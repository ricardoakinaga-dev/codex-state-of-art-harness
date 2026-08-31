# Phase 8 bounded repair 001

## Justification for exceeding the default repair count

The default visual repair iteration was already consumed. Two independent
read-only reviews then identified independent High findings in the final
pilot: insufficient contrast, ambiguous-response idempotency, and incomplete
server-error/form semantics. Leaving those defects known would violate the
Phase 8 quality bar, so this is an explicitly justified second repair window.

## Scope

- Keep the existing dependency-free HTML/CSS/ES2022 architecture.
- Darken only the affected text/action tokens and preserve the visual system.
- Keep one idempotency key for one logical draft across retry attempts.
- Make the fixture's check-and-store operation atomic for threaded requests.
- Bind required fields and the optional notes server error to named controls.
- Remove the dead profile button without adding a new interaction surface.
- Add regression assertions before implementation, then rerun all required
  browser, build, accessibility, lint, test and verification checks.

## Explicit non-goals

No framework, dependency, global skill, host adapter, release state, or
production/security/accessibility certification change is authorized by this
repair. The Phase 4 host-composition limitation remains a separate finding.

## Exit criteria

The repair is complete only when the focused RED/GREEN tests, fresh final
renders, source/artifact/browser bindings, accessibility checks and final
read-only verification are regenerated. The repair count is recorded as two
iterations total, with this entry documenting the justified exception.
