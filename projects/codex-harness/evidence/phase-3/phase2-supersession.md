# Phase 2 Additive Supersession Record — P3-SUP-0001

Phase 2 remains frozen at the exact packet identified by
`evidence/phase-2/PHASE2-FROZEN.md`. Phase 3 adds new host-integration source,
tests, fixtures, documentation and evidence after that closeout. The old
manifest, attestation, readiness and gate are not edited or reused.

Phase 2 base source SHA: `d95568aa5e4821a3e1d38c718dac6eb473676cdd`.

The Phase 3 review manifest must record the Phase 2 base SHA and the exact
additive file set. Phase 3 must rerun the Phase 2 regression suite and must
preserve the Phase 2 limitations: no production, no `AAA_VERIFIED`, no
arbitrary execution and no causal host-load claim without instrumentation.

This record authorizes only the additive read-only boundary described by
`P3-QB-1` and ADR-012. It does not authorize installing, deleting, rewriting,
synchronizing or modernizing global Skills/configuration, or executing scripts,
providers, MCP, shell, network or credentials.

## Explicit frozen-file supersession

The Phase 3 CLI requirement needs an installed project-local command named
`harness`. The only historical Phase 2 payload file changed for that exposure
is `pyproject.toml`, with one additive `[project.scripts]` entry pointing to
`harness_kernel.phase3_cli:main`. No Phase 2 kernel source, Phase 2 test,
runtime behavior, dependency, global configuration or credential was changed.

Because `pyproject.toml` is named by the historical Phase 2 manifest, this is
an explicit legitimate Phase 3 extension under the freeze procedure above,
not a silent reuse of the Phase 2 attestation. The Phase 3 manifest records
the current bytes, the full Phase 2 regression suite is rerun, and all Phase 2
closeout artifacts remain unchanged as historical evidence at the frozen
`d95568aa5e4821a3e1d38c718dac6eb473676cdd` source boundary.
