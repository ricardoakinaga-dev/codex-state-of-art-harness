# Phase 7.3 Security Scanner Report

Status: UNAVAILABLE_WITH_FORMAL_WAIVER.

The authoritative availability capture is
security-scanner-inventory.json. It found zero of the twelve named or
equivalent scanners available in the pinned environment:

- pip-audit
- bandit
- semgrep
- trivy
- safety
- osv-scanner
- grype
- syft
- gitleaks
- detect-secrets
- snyk
- cargo-audit

No scanner was reported as PASS. No scanner was installed, no package
registry was contacted, and no network or global-state mutation was permitted.
The formal limitation is recorded in
waivers/WAIVER-SECURITY-SCANNERS.md; it does not waive unresolved material
High or Medium risk.

Available compensating controls were executed separately:

- Ruff check and format check over the project source, tests, and Phase 7.3
  evidence tooling.
- strict mypy over the same Python tooling.
- `/home/ricardo/.local/bin/uv pip check --python .venv/bin/python`: all 13 installed packages
  compatible.
- bounded repository secret-pattern scan: no matching file and no
  environment/key file found.
- the full deterministic pytest and branch-coverage run.

These controls reduce uncertainty but do not substitute for the unavailable
third-party scanners. The final promotion decision must retain this
limitation.
