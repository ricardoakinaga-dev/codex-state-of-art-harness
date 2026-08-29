# Phase 3 host capability integration report

## Scope and decision

Phase 3 adds a bounded, read-only bridge from the frozen Phase 2 local kernel
to the local Codex capability layout. The implementation discovers known roots,
parses declarative metadata, synthesizes observed manifests, evaluates trust
and compatibility, resolves duplicates/dependencies, prepares progressive load
plans, and bridges selected metadata into the existing registry/router.

It does not install or modify Skills, execute scripts/providers/MCP/shell,
perform network or credential access, import package code, or claim that a
discovered package is host-loaded. The final status is controlled by the
independent review, readiness record and verified gate in this packet; this
implementation report does not substitute for those controls.

## Implementation

The extension is split into immutable models, descriptor-relative path safety,
bounded discovery/parser/synthesis, trust and compatibility, deterministic
resolution, progressive safe loading, honest telemetry, host adaptation, CLI
doctor/inspection and Phase 2 registry/router integration. Files with sensitive
names, scripts, binaries and assets are metadata-only; text files below
`scripts/` and `assets/` are metadata-only even when their suffix is textual.
Selected references are bounded and contained beneath their package. Expected
inventory fingerprints mark records stale before selection. Deeply nested
structured metadata and oversized SemVer values fail closed before conversion
or selection.

## Evidence summary

- Real host: five root records, 43 discovered capabilities, 38 inspected and
  five rejected for activation metadata without a matching exclusion.
- Resolution: one divergent same-ID/version `engineering-framework` finding is
  blocking; a version pin alone cannot disambiguate divergent bytes.
- Safe loader: L0/L1 remain selection/planning only; L2–L4 prepare bounded
  declarative context; host loading and execution remain false/disabled.
- Verification: 290 tests passed, combined statement/branch coverage 82%,
  Ruff and mypy passed, static runtime/privacy scans passed, and `pip-audit`
  was unavailable and is recorded as such.
- Benchmark: `evidence/phase-3/benchmark-summary.json` records the local
  three-iteration baseline; it is not a production SLO.

## Limitations and handoff

The adapter cannot observe Codex runtime causality, provider/tool execution or
system roots unavailable to this process. The implementation does not claim
production readiness, arbitrary runtime execution, causal quality or
`AAA_VERIFIED`. Any source, test, host configuration or scope expansion
requires a new Phase 3 evidence manifest and independent review.
