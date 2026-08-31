# Waiver: Optional Security Scanners Unavailable

- waiver ID: WAIVER-P7.3-SECURITY-SCANNERS-001
- scope: Phase 7.3 promotion packet only
- status: ACCEPTED_WITH_LIMITATIONS
- created: 2026-08-30
- expires: 2026-09-30

## Limitation

The pinned local environment does not provide pip-audit, Bandit, Semgrep,
Trivy, or the equivalent probes recorded in
security-scanner-inventory.json. The packet therefore makes no scanner PASS
claim and does not convert unavailability into a successful security result.

## Eligibility basis

The project declares no runtime dependencies, uv pip check passes for the
13-package development environment, and the package candidates are
project-local with network, shell, MCP, provider, credential, and
installed/global mutation denied. Ruff, strict mypy, deterministic tests,
coverage, and the bounded repository secret-pattern scan are available as
compensating controls.

## Boundaries

This waiver is limited to optional scanner execution. It does not waive
authentication, authorization, filesystem, persistence, evidence-integrity,
material risk closure, or any unresolved High/Medium promotion blocker. It is
not production security approval and must be rejected if the independent
reviewer finds a candidate correctness or authority defect.

## Expiry action

Before expiry, install or provide pinned scanner binaries in a separately
controlled environment and rerun the inventory. If that cannot be done, the
candidate must be re-reviewed; this waiver must not become a permanent PASS.
