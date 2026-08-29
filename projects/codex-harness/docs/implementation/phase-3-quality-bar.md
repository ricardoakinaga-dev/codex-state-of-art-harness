# Phase 3 Quality Bar — P3-QB-1

## Decision

This bar governs the Phase 3 host-capability integration extension. The
Phase 2 exact packet remains a historical `PASS_WITH_LIMITATIONS` result at
the reviewed source SHA recorded in `evidence/phase-2/PHASE2-FROZEN.md`.
Phase 3 is an additive, read-only boundary. It may add new modules, tests,
fixtures, documentation and evidence, but it may not rewrite the Phase 2
evidence, manifest, attestation or gate. Any additive change under the
Phase 2 source/test roots is covered by the Phase 3 supersession record and a
new review manifest; it does not retroactively change the Phase 2 claim.

## Observable acceptance criteria

Every required criterion below needs current evidence. `PASS_WITH_LIMITATIONS`
is the strongest permitted status when a host signal or security scanner is
unavailable; `UNKNOWN` must not be promoted to `PASS`.

| ID | Dimension | Required evidence | Priority |
| --- | --- | --- | --- |
| P3-01 | Phase 2 regression | Clean Phase 2 and full-suite run; the 232-test baseline remains green; no Phase 2 frozen artifact was rewritten | P0 |
| P3-02 | Host adapter | Typed adapter exposes inspection/discovery/metadata observation only; no mutation method; real snapshot records identity, roots, counts, limitations and confidence without secrets | P0 |
| P3-03 | Root and path safety | Tests reject absolute paths, traversal, NUL, symlink escape, alias collision, loops, unbounded depth/bytes and duplicate canonical roots | P0 |
| P3-04 | Discovery and inventory | Real host roots and project-local fixtures produce deterministic machine-readable inventory with sanitized paths, hashes, scope and provenance | P0 |
| P3-05 | Safe parser and synthesis | Bounded `SKILL.md` parser extracts only declarative metadata; malformed/unknown fields remain visible as `UNKNOWN`; native, synthesized, legacy and invalid status are distinct | P0 |
| P3-06 | Safe loader | Progressive L0–L4 loading is explicit and bounded; references stay inside package; binary content is metadata-only; scripts, providers and MCP are never executed | P0 |
| P3-07 | Compatibility and trust | Host/platform compatibility, portability debt, trust level, provenance and staleness are explicit; incompatible/rejected/stale records cannot be selected | P0 |
| P3-08 | Duplicates and resolution | Same ID/version with divergent bytes is blocked; aliases/forks/versions are reported; precedence is documented, deterministic and tested; dependency cycles fail | P0 |
| P3-09 | Registry/router bridge | Selected observed manifests bridge into the existing immutable registry and `minimum_route()` without changing its execution semantics; direct tasks stay direct | P0 |
| P3-10 | Observability honesty | Discovered, selected, load-planned, context-prepared, host-loaded and executed are separate states/events; no host-loaded claim without observation | P0 |
| P3-11 | Read-only CLI/doctor | Host inspect, roots, list, inspect, duplicates, compatibility, refresh, resolve and load-plan commands are bounded/read-only and never touch global state | P0 |
| P3-12 | Security and privacy | Prompt-injection content is data; no dynamic import/eval/subprocess/network/credential reads; output paths are redacted; bounds and structured errors are tested | P0 |
| P3-13 | Project isolation | Project-local capabilities are first-class; global roots are read-only dependencies; refresh/cache/evidence writes remain under `.harness/` | P0 |
| P3-14 | Quality and handoff | Unit/integration/adversarial/property/golden/eval coverage, Ruff, mypy, benchmark, security report, independent review, readiness and implementation report are current | P0 |

## Boundaries and fixtures

The known-bad suite must cover traversal, absolute paths, NUL, nested and
escaping symlinks, loops, malformed front matter, oversized files, huge
reference trees, script metadata, duplicate IDs, divergent bytes, dependency
cycles, missing `do-not-activate`, always-activate text, fake official
provenance, unsupported hosts and incompatible platforms. These cases must
fail closed and must never run the referenced script/provider/MCP/network.

The real-host smoke is inspection-only. It may observe the current Codex
installation layout and local metadata, but the result must distinguish
`OBSERVED`, `OFFICIAL_DOCUMENTED`, `INFERRED`, `UNAVAILABLE` and `UNKNOWN`.
The implementation must not claim that a capability is loaded merely because
its directory or `SKILL.md` was discovered.

## Measurement rules

- All paths in persisted evidence are workspace-relative, root IDs, or
  redacted placeholders such as `$HOME`; raw home paths, credentials and
  environment values are not persisted.
- All content reads use explicit byte/file/depth/count limits and regular-file
  checks. A package is untrusted data, not executable instructions.
- The benchmark records host snapshot, root discovery, package discovery,
  parse, synthesis, duplicate analysis, compatibility, trust, registry bridge
  and load-plan timings. It is a local engineering baseline, not an SLO.
- Coverage must remain at least 80% for the project test configuration. A
  missing `pip-audit` or host load signal is reported as unavailable, never as
  a passing scan or successful load.

## Permitted final statuses

Only these statuses are valid for the Phase 3 packet:

- `PASS_WITH_LIMITATIONS`
- `CONDITIONAL_PASS`
- `FAIL`

`AAA_VERIFIED`, production-ready and causal-quality claims are out of scope.
