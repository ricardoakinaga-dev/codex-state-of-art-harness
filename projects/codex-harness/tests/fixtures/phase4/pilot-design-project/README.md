# Phase 4 pilot workspace

This is a deliberately tiny, non-sensitive fixture for the controlled host
pilot. It contains no credentials, scripts, assets or external dependencies.
The fixture Skill is a declarative response capability and must never be
treated as proof that an installed production Skill is safe to execute.

The only expected pilot result is a host-response artifact containing
`PHASE4_SAFE_PILOT_ARTIFACT`. The app-server is run with an ephemeral thread,
no network, no tools and no file-change approval.
