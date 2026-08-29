# Context and cost report

Both builder requests used the exact task, acceptance criteria and selected
reference manifest. The authorization capped each context at 32,768 bytes and
the observed manifests estimated 16,384 bytes. No omitted references were
silently fetched, and the repair request appended one bounded critic-selected
correction with a 4,096-byte maximum.

The pilot used two builder invocations total: one v1 response and one v2
repair response. The recorded host load is
`HOST_LOAD_UNOBSERVABLE`; the official host surface does not expose a distinct
Skill-load causal event. Host-side action budgets nevertheless remained
finite, with one host call per authorization and zero tool calls. Browser
navigation observations used 38 ms for the minimal baseline and 58 ms for the
final artifact; these are local single-navigation measurements, not SLOs.

No context ballooning, unbounded retry, recursive repair, or cross-run context
reuse was accepted. The exact manifests are
`pilots/design-director/builder-context-manifest.json` and
`pilots/design-director/builder-repair-context-manifest.json`.
