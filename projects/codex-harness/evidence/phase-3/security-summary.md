# Security summary

Status: `PASS_WITH_LIMITATIONS` within the Phase 3 boundary.

- Root, traversal, NUL, symlink/alias, loop, depth, count and byte boundaries
  are validated and adversarially tested.
- Front matter/JSON parsing fails closed on malformed, duplicate, nested,
  oversized, non-finite or unknown structured data.
- Capability content is untrusted data. There is no dynamic import/eval,
  subprocess, shell, network, credential read, provider call, MCP call or
  script execution in Phase 3.
- Public inventory, CLI and telemetry redact raw home/workspace paths and
  sensitive values. Sensitive files are not content-read.
- Same-size differing non-sensitive script/asset bytes now produce different
  bounded hashes and block divergent duplicate resolution.
- `pip-audit` is unavailable in this environment; it is recorded as
  unavailable, not as a passing scanner result.

Global Codex configuration, credentials, installed Skills and provider state
were not mutated.
