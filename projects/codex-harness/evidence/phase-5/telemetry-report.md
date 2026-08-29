# Telemetry and privacy report

Every Phase 5 handoff identifies the task/run, capability, exact package and
manifest fingerprints, role, invocation, artifact version, parent lineage
when applicable, render viewport, verification/critique packet, and final
composition digest. The builder and repair receipts record host invocation
IDs, attempt counts, response status, and the explicit
`HOST_LOAD_UNOBSERVABLE` limitation.

The public evidence serializer redacts host paths where applicable. The
artifact path is retained only inside the project-bound authorization and
receipt records needed to prove confinement. No credential, token, secret,
provider payload, or unrestricted environment was recorded. Supplemental
browser logs contain only loopback navigation, clean console output, and
bounded metrics.

The real pilot consumed two builder, two structural-verifier, two critic, and
one repair invocation. It emitted no approved tool, shell, network, MCP,
provider, credential, or subagent event.
