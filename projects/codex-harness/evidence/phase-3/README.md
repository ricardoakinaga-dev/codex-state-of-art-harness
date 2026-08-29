# Phase 3 Evidence — Host Capability Integration

This directory contains the evidence for `PHASE3-001`, the additive,
read-only bridge from the frozen Phase 2 local kernel to the Codex capability
environment. It must never be confused with the immutable Phase 2 packet in
`../phase-2/`.

## Authority and status

- Quality bar: `docs/implementation/phase-3-quality-bar.md` (`P3-QB-1`)
- Rebaseline ADR: `../../../../architecture/docs/adr/ADR-012-phase-roadmap-rebaseline-after-phase-2.md`
- Plan: `.agent/plans/PHASE-3-host-capability-integration.md`
- Phase 2 freeze: `../phase-2/PHASE2-FROZEN.md`
- Phase 2 base source SHA: `d95568aa5e4821a3e1d38c718dac6eb473676cdd`
- Final statuses allowed: `PASS_WITH_LIMITATIONS`, `CONDITIONAL_PASS`, `FAIL`

The evidence records what was observed, inferred, officially documented,
unavailable or unknown. Host discovery is not host loading; no capability is
reported as loaded without a real observation signal.

## Expected packet

The packet contains the host inspection, root discovery, sanitized inventory,
duplicate analysis, compatibility, trust, safe loader, routing integration,
telemetry, security, coverage, benchmark, independent review, readiness and
final implementation report. Paths are redacted or expressed as root IDs. No
credentials or global-state mutations are allowed.

Primary records:

- `host-inspection.json`, `real-inventory.json`, `duplicate-report.json`;
- `compatibility-report.json`, `trust-report.json`, `safe-loader.json`,
  `routing-integration.json`, `telemetry.json`;
- `benchmark-summary.json`, `coverage.md`, `security.md`;
- `review-manifest.json`, `review-attestation.json`, `readiness.json` and
  `independent-review.md`;
- `../../docs/implementation/phase-3-host-capability-integration-report.md`.
