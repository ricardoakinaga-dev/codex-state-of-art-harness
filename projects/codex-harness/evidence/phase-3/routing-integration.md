# Registry and router integration

Observed selected metadata is converted into the existing immutable
`CapabilityManifest`/`CapabilityRegistry` contracts by
`Phase3RouterBridge`. The bridge preserves origin and provenance, maps the
Phase 3 scope/activation/stop metadata into existing contract fields, and calls
only the pure `minimum_route()` policy.

The evidence sample resolves `harness-kernel` as a selected `SPECIALIST`,
bridges it into the registry, and produces a load plan without execution. A
direct task remains direct; Phase 3 does not add an executor or alter Phase 2
provider semantics. The real divergent duplicate remains blocked before a
registry admission claim.
