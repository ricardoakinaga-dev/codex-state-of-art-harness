# Trust and provenance report

The real inventory has 37 `THIRD_PARTY` records with `INFERRED` confidence,
five `REJECTED` records with `OBSERVED` validation evidence, and one
`PROJECT_TRUSTED` record with `OBSERVED` confidence. Every record retains root
scope, source references, source repository identity, package digest, observed
timestamp and authority label.

Trust is a selection input, not proof of execution safety. Rejected, stale,
ambiguous, incompatible or low-trust records cannot cross the loader/router
selection boundary. No official provenance is inferred from a familiar
directory name.
