# Phase 1 independent adversarial review

**Scope:** bounded `projects/codex-harness/` kernel and project-isolation boundary.
**Mode:** read-only review followed by local regression retest.

## Initial findings and disposition

The independent review found no Critical issue. It identified three High
findings:

- the CLI loaded only registry copies and did not compare the canonical manifest
  under each isolated capability directory;
- dependency resolution could treat rejected/deprecated metadata as usable;
- the public benchmark writer could escape the project root.

All three were fixed. The loader now reads both project-local manifest locations,
deduplicates exact equivalents, blocks divergent ID/version copies, enforces the
registry file limit, recalculates a canonical hash over manifest metadata and
declared local source references, validates contract references, and binds
project origin to the configured project ID. Configured registry paths are
honored and confined to the project. Dependency resolution and inspection now
mark `REJECTED` and `DEPRECATED` capabilities unusable; the registry constructor
also applies the same admission checks as `register()`.

The review also identified Medium/Low gaps. They were closed by making origin
precedence primary over version selection, adding explicit regression coverage,
bounding route objectives, profile identifiers and telemetry event volume, and
confining benchmark output. Remote-source content verification and runtime
execution remain intentionally outside Phase 1.

## Retest evidence

The remediation suite covers canonical-manifest divergence, local hash
tampering, project-scope mismatch, rejected dependency resolution, constructor
admission, origin precedence, configured-path enforcement, registry file limits,
oversized route/telemetry input, invalid profile identifiers and benchmark
destination escape. The complete project suite (`99 passed`) and all
deterministic quality gates were rerun after the fixes. No Critical or High
finding remains open within the bounded scope.

## Verdict

`PASS_WITH_LIMITATIONS` for the Phase 1 Kernel only. This review does not prove
an executor, provider dispatch, Codex host integration, production readiness,
autonomous orchestration, or Skill modernization.
