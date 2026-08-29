# Host inspection

Command:

```text
PYTHONPATH=src .venv/bin/python -m harness_kernel.phase3_cli host inspect --json
```

Result: `P3-HOST-1`, `OBSERVED`, five root records and 43 discovered capability
records (38 inspected and five rejected by metadata safety). The adapter reports
`codex_runtime: UNKNOWN`, provider/tool discovery
as unavailable, and `host_loaded: false` is preserved as an unavailable load
causality signal. All discovered roots are marked `READ_ONLY` and
`mutable: false`.

Observed roots are `project.agents` (unavailable), `project.harness` (readable),
`global.agents` (readable), `global.codex` (readable), and `system.codex`
(unavailable). Persisted paths use `$WORKSPACE`, `$HOME`, or a redacted system
placeholder; no user home path or credential is part of this packet.

The adapter only calls bounded path and metadata inspection. It does not
install, refresh globally, import, execute, invoke providers/MCP, open a shell,
make a network request, or claim that discovery loaded a capability.
