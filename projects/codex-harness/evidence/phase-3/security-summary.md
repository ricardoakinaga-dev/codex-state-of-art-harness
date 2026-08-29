# Security summary

Status: `PASS_WITH_LIMITATIONS` within the Phase 3 boundary.

- Root, traversal, NUL, symlink/alias, loop, hard-link, depth, count and byte
  boundaries are validated and adversarially tested; canonical root aliases are
  deduplicated before discovery.
- Front matter/JSON parsing fails closed on malformed, duplicate, nested,
  oversized, non-finite or unknown structured data.
- Capability content is untrusted data. There is no dynamic import/eval,
  subprocess, shell, network, credential read, provider call, MCP call or
  script execution in Phase 3.
- Inventory snapshots are revalidated before resolution and content disclosure;
  changed package bytes, metadata, file sets and unsafe aliases fail closed.
- L3 reference disclosure is allowlisted by the discovered package inventory;
  an arbitrary file inside a package is not automatically approved.
- Public inventory, CLI and telemetry redact raw home/workspace paths and
  sensitive values, including compound and long-prefix secret key names.
  Sensitive files are not content-read.
- Same-size differing non-sensitive script/asset bytes now produce different
  bounded hashes and block divergent duplicate resolution.
- Direct and walked hard-link aliases are rejected, including benignly named
  files that point at an external inode.
- `pip-audit` is unavailable in this environment; it is recorded as
  unavailable, not as a passing scanner result.

Global Codex configuration, credentials, installed Skills and provider state
were not mutated.
