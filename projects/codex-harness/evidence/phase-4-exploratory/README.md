# Phase 4 evidence packet

This packet records the bounded real-capability invocation pilot for
`PHASE4-001`. It is additive to the frozen Phase 2 and Phase 3 packets and
does not modify installed Skills, global configuration, MCP, providers,
subagents or external packages.

The supported outcome is `P4_LEVEL_B`: one real Codex app-server turn was
observed and its bounded host-response artifact verified, but the host did
not expose a distinct causal Skill-load event. The final status is therefore
`PASS_WITH_LIMITATIONS`, never `AAA_VERIFIED`.

The only controlled-real candidate was the project-local,
script-free `phase4-safe-pilot` fixture. `design-director` was retained as a
dry-run-only candidate because it is synthesized, third-party,
partial-compatible and script-bearing. `verification-loop` was rejected by
Phase 3 discovery as invalid. Neither preferred installed Skill was invoked.

The packet separates host facts, Harness observations, declared policy,
verification, assurance, benchmark data, regression data and review
attestation. Paths and secret-like values in generated JSON are sanitized.
