# Security summary

The bounded pilot is fail-closed: exact fingerprint and explicit execution approval are required; the app-server starts with `mcp_servers={}`, a read-only ephemeral thread, no network access, zero tool budget and approval denial. Shell, scripts, tools, network, MCP, providers, credentials, side effects and subagents are denied. Task/preflight/request bindings, persistent replay, event correlation, artifact paths and sanitized evidence are independently testable. Global state is checked through metadata-only before/after snapshots.
