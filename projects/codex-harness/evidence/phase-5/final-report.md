# Phase 5 final report

## Decision

`PHASE5-001` is closed as `PASS_WITH_LIMITATIONS` at support level `A`.
The bounded pilot produced a real response-derived `artifact_v2`, native
desktop/mobile browser evidence, structural verification, blind visual review,
one bounded repair, final verification, independent engineering review and
independent visual review.

The exact final packet is bound by:

- artifact: `sha256:b85e7db1b2eb9e6c6f3adfa0a4dd39e0ee01bb955a73a7adec6936ec25483adb`
- blind packet: `sha256:787dbe50ee40db153a2c6b975b77493974096119044dab9dd7cdfe4b8086566b`
- final verification: `sha256:fb725968b77d4c657109b1d45288d9f1566280c3c6e1dde9e666f68197df9b94`
- review manifest: `sha256:88f5ad7e97a267f3d235ed0f7504cbcf428825594db3fd8cf47e99cb75ae51ed`
- payload closure: `sha256:0bc4aa985a55adbfbb5acc95f8c94a70d03f3ebaf8d867707cc47fa2bc36cb2a`

## Capability and boundary

`design-director@0.1.0` was inspected read-only and matched the exact package
fingerprint `sha256:564d610da9260d25cbcddfbb3f96f70fb9dabd643c46b4242c4b891d399eba95`
and manifest fingerprint
`sha256:402e36727b060eaf4ef740daf8ddfdcfce40cede7cb51ad48c14a582b9037c43`.
The route was response-only and denied tools, executable scripts, shell,
network, MCP, providers, credentials, subagents and host file changes.
`verification-loop` was independently observed as
`BLOCKED_INVALID_METADATA` / `EXTERNAL_VERIFIER_NOT_ELIGIBLE`; it was not
impersonated by a native fallback.

## Composition and quality

The fixed graph ran with 2 builder, 2 structural-verifier, 2 blind-critic and
1 repair invocation across `artifact_v1` and `artifact_v2`. The v1 packet was
retained and marked stale after the v2 artifact changed. The final structural
record passed artifact digest, semantic copy/landmarks, browser loadability,
overflow, accessibility and confinement checks.

The final visual review scored `87.5/100`. The composition benchmark recorded
`34 → 87` with `+53` observed score points and `+20 ms` local navigation cost.
This is labeled `PILOT_COMPOSITION_EVIDENCE`, not causal proof or a production
benchmark.

The complete project suite passed `424` tests with combined coverage at the
`80%` gate. Ruff format/lint and strict mypy passed. The static security
review and Phase 2–4 regression checks passed; `pip-audit` was unavailable.

## Independent review and residuals

Engineering review `IR-P5-DESIGN-001-20260829-FINAL-EXACT-02` and visual review
`IR-P5-DESIGN-001-20260829` both returned `PASS_WITH_LIMITATIONS`, with zero
Critical and zero High findings. Remaining issues are four Medium, two Low and
one polish item:
mobile lower-hero closure, intermediate breakpoint evidence, complete focus and
interaction evidence, mobile support-copy/footer treatment, and generic
utility typography. They are recorded without being promoted to a false pass.

## Excluded claims

This closeout does not claim `AAA`, `HARNESS_AAA_VERIFIED`, unconditional PASS,
production readiness, pixel-perfect/reference fidelity, complete interactive
accessibility certification, a production-valid telephone destination, or
causal superiority over the native baseline. Host-load causality remains
`HOST_LOAD_UNOBSERVABLE`.

No global configuration, installed capability package, MCP configuration,
provider, credential store, production system or external service was changed.
