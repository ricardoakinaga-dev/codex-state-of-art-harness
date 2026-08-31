# Phase 7.3 Host Reproducibility Analysis

The unpinned safe-PATH probe is retained as `HOST_PATH_UNRESOLVED`; it is not
interpreted as a candidate failure. The current cycle uses the explicit,
absolute Codex and Node pins recorded in `host-bootstrap-manifest.json`.

- Codex wrapper: `/home/ricardo/.nvm/versions/node/v22.22.2/bin/codex`
- resolved Codex JavaScript: `/home/ricardo/.nvm/versions/node/v22.22.2/lib/node_modules/@openai/codex/bin/codex.js`
- Node: `/home/ricardo/.nvm/versions/node/v22.22.2/bin/node`
- versions: `codex-cli 0.151.0`, `node v22.22.2`
- executable digest: `sha256:134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477`
- interpreter digest: `sha256:81925c0995b5c1427b5d538e6a90ca2fdc4daffb786b09af749beaf7369d4e90`

The preflight is `RESOLVED_READ_ONLY_VERSION_PROBE`; the authoritative
builder → repair → verifier receipt is `real-cycle-report-005.json`. This
does not establish host equivalence or skill-load observability, and no
production-host, release or syscall-isolation claim is made.
