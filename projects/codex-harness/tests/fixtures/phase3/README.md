# Phase 3 representative fixtures

`scenarios.json` is the committed scenario catalog for the Phase 3 known-good
and known-bad matrix. Tests materialize each scenario in a temporary directory
so the repository, global Codex roots, credentials and provider state are never
modified. The catalog deliberately describes declarative inputs only; scripts,
assets, providers and MCP-shaped metadata are inventory surfaces and are never
executed.

The real-host smoke test separately exercises any installed `design-director`,
`engineering-framework` and cross-agent capability records that are actually
present on this machine. Their absence is reported as unavailable rather than
simulated.
