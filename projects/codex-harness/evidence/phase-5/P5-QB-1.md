# P5-QB-1 — Design Director Composition Pilot Quality Bar

The frozen quality bar is defined in
[`docs/implementation/phase-5-quality-bar.md`](../../docs/implementation/phase-5-quality-bar.md).
This copy is the root evidence pointer required by the Phase 5 packet.

The closeout requires current evidence for: frozen Phase 2–4 regressions;
exact package eligibility and fingerprints; immutable task and handoffs; a
fixed finite graph; a real builder response; structural and native browser
verification; blind visual review; at most one attributable repair; assurance;
path-safe/stale evidence; fail-closed negatives; a non-causal baseline
comparison; redacted telemetry; 80% combined coverage; Ruff; strict mypy; a
fresh independent visual and engineering review; and zero unresolved Critical
or High findings.

This pilot meets those requirements within the declared boundary at
`PASS_WITH_LIMITATIONS`, support `A`. Medium findings and unrun accessibility
paths remain explicit limitations; they are not silently converted into
passes. `AAA_CANDIDATE`, `HARNESS_AAA_VERIFIED`, and production claims are not
permitted by this bar.
