# Telemetry report

`telemetry.json` uses `P3-TELEMETRY-1` and exposes an explicit stage taxonomy
for host inspection, roots, parsing/synthesis, duplicates/divergence,
compatibility, trust, registration and observable/unobservable load in addition
to lifecycle events for discovery, selection, load planning, context
preparation, blocked state, host loading and execution.
The captured sample contains no `HOST_LOADED` or `EXECUTED` event. The API
rejects those runtime lifecycle events unless the observation is an actual
`OBSERVED` host signal; this adapter reports host load as
`UNSUPPORTED_BY_HOST`/`UNAVAILABLE`.

Telemetry records are immutable append results. Sensitive keys are redacted,
absolute paths are replaced by safe placeholders/digests, event counts are
bounded and no telemetry write is performed outside the project evidence
workflow.
