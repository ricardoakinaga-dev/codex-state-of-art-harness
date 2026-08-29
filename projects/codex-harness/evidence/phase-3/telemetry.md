# Honest lifecycle telemetry

`P3-TELEMETRY-1` distinguishes discovery, selection, load planning, context
preparation, blocked state, host loading and execution. The captured telemetry
packet has five events: `CAPABILITY_DISCOVERED`, `CAPABILITY_SELECTED`,
`CAPABILITY_LOAD_PLANNED`, `CAPABILITY_CONTEXT_PREPARED` and
`CAPABILITY_BLOCKED`; it has zero `HOST_LOADED` or `EXECUTED` events.

The telemetry API rejects a `HOST_LOADED` event unless the caller supplies an
`OBSERVED` host signal. Sensitive keys are redacted and absolute paths are
replaced with `$HOME`, `$WORKSPACE`, `$PATH/<digest>`, or a redacted marker.
Telemetry records are frozen and append by returning a new value.
