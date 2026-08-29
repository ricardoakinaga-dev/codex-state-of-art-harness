# Host inspection report

Status: `PASS_WITH_LIMITATIONS` for the bounded read-only adapter. The
machine-readable snapshot is `host-inspection.json` and the detailed sanitized
inventory is `real-capability-inventory.json`.

- Adapter: `CodexHostAdapter`, `P3-1`; runtime version: `UNKNOWN`.
- Observed roots: 5; readable roots: project harness and the two user roots;
  unavailable project-agents/system roots remain recorded, not invented.
- Discovered records: 43; inspected: 38; rejected: 5.
- All roots are `READ_ONLY`/`mutable: false`; no writes, installs, imports,
  subprocesses, provider calls, MCP calls, shell or network operations occur.
- Official behavior labels are machine-readable: Skill discovery and optional
  `agents/openai.yaml` are `VERIFIED_OFFICIAL`; the legacy `.codex/skills`
  compatibility root is `INFERRED`; documented ancestor/symlink semantics are
  `VERIFIED_OFFICIAL`, while adapter ancestor traversal is
  `UNSUPPORTED_BY_HOST` and its symlink rejection is an `INFERRED` safety
  policy; host-load observation is `UNSUPPORTED_BY_HOST`; runtime version
  remains `UNKNOWN`.

Paths in committed evidence are root IDs or redacted placeholders. The adapter
does not equate directory discovery with host loading.
