# Phase 7.3 Host Analysis

The historical safe-PATH probe failed with `HOST_PATH_UNRESOLVED` because
the regular Codex installation lives under the user's nvm path. That failure
is preserved as environment diagnosis, not suppressed.

The current controlled run supplies explicit absolute pins:

- Codex wrapper: `/home/ricardo/.nvm/versions/node/v22.22.2/bin/codex`
- resolved executable: `/home/ricardo/.nvm/versions/node/v22.22.2/lib/node_modules/@openai/codex/bin/codex.js`
- Node interpreter: `/home/ricardo/.nvm/versions/node/v22.22.2/bin/node`
- Codex: `codex-cli 0.151.0`
- Node: `v22.22.2`
- executable digest: `sha256:134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477`
- interpreter digest: `sha256:81925c0995b5c1427b5d538e6a90ca2fdc4daffb786b09af749beaf7369d4e90`

The resolved preflight is `RESOLVED_READ_ONLY_VERSION_PROBE`, and the real
builder → repair → verifier cycle is recorded in
`real-cycle-report-005.json`. No host-path waiver is required for this
candidate. Host skill-load event observability remains unavailable.
