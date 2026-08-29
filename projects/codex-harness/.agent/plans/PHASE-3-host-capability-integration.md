# ExecPlan — PHASE3-001 Host Capability Integration

## Purpose / Big Picture

Bridge the frozen Phase 2 project-local deterministic kernel to the real
Codex capability environment through a read-only, bounded and honest host
adapter. The outcome is an inspectable inventory, safe declarative loader,
trust/compatibility/resolution layer, registry/router bridge, load plan and
evidence packet. It is not a Skill installer, host executor, provider, MCP,
shell, network or production runtime.

## Progress

- [x] (2026-08-28) Recovery and Phase 2 freeze inspection completed.
- [x] (2026-08-28) P3-QB-1, ADR-012 and additive Phase 2 supersession recorded.
- [x] (2026-08-28) TDD RED suite and known-bad eval fixtures recorded.
- [x] (2026-08-29) Host adapter, discovery, parser, loader, trust,
      compatibility, resolution, integration and telemetry implemented.
- [x] (2026-08-29) CLI/doctor, eval fixtures, evidence scaffolding and
      benchmark path added.
- [x] (2026-08-29) Full regression, security scan, canonical evidence refresh,
      review-driven hardening and Dewey's fresh exact-packet review completed;
      the control-only final handoff gate is recorded.

## Surprises & Discoveries

- The actual host exposed 43 inspected capabilities across five discovered
  root classes; two root classes are unavailable in this process.
- Two `engineering-framework` packages have divergent bytes. Resolution
  blocks that capability because a version pin alone cannot distinguish the
  equal-ID/equal-version bytes; an explicit hash/path reconciliation is needed.
- Host runtime/tool/provider causality is not observable from this adapter;
  the implementation reports `UNKNOWN` or `UNAVAILABLE` instead of inferring
  it.
- Non-sensitive metadata-only bytes are hashed with bounded reads while
  sensitive bytes remain unreadable; unresolved sensitive duplicate identity
  is blocked conservatively rather than treated as equal.
- The installed project-local `harness` CLI entry point changes one historical
  `pyproject.toml` byte; this is explicitly documented as a bounded Phase 3
  supersession with a new manifest and review, while the Phase 2 kernel remains
  unchanged.

## Decision Log

- Keep all host access read-only and bounded; no install, delete, execute,
  import, provider, MCP, shell, network or credential lookup is in scope.
- Preserve Phase 2 exact evidence as historical authority and add a separate
  Phase 3 manifest/review packet.
- Use explicit precedence `pin > project > workspace > approved shared >
  global > system > external`, with duplicate divergence blocking selection;
  a version pin alone cannot distinguish equal-ID/equal-version divergent
  bytes and therefore does not override that block.

## Outcomes & Retrospective

The additive implementation now has a coherent host boundary, declarative
loader and registry/router bridge. The current local result is
`PASS_WITH_LIMITATIONS`: 308 tests pass at 82% combined coverage, the
reproducible P3 benchmark covers 100 temporary capabilities, Dewey approved
the exact 119-entry packet with zero Critical/High/Medium/Low findings, host
loading and execution remain unclaimed, and the remaining environmental
limitations are explicit.

## Context and Orientation

The frozen Phase 2 kernel lives in `src/harness_kernel/` and remains the
regression authority. Phase 3 modules use immutable records and feed only
observed metadata into the existing registry/router contracts. The real host
is inspected only through `phase3_host.py`; all package content is treated as
untrusted data.

## Scope and Constraints

- All implementation remains under `projects/codex-harness/`.
- The Phase 2 evidence packet is immutable historical evidence. New additive
  files get a Phase 3 manifest and review; old hashes are never rewritten.
- Host inspection accepts explicit roots and known local Codex roots. It reads
  regular metadata only, follows no escaping link, and writes only project
  local Phase 3 evidence/cache when explicitly requested.
- Package content is untrusted data. No script, executable, import, MCP,
  provider, network request, shell command or credential lookup is allowed.
- Unknown host behavior stays `UNKNOWN` or `UNAVAILABLE`.

## Architecture and Interfaces

The extension is split into focused modules:

- `phase3_models.py`: frozen enums and records for host, roots, capabilities,
  manifests, provenance, trust, compatibility, resolution, loading and events.
- `phase3_paths.py`: canonical path/root policy, redaction and bounded walking.
- `phase3_parser.py`: bounded front matter/instruction metadata parser with no
  YAML execution or arbitrary object construction.
- `phase3_discovery.py`: host/project root inventory, package discovery,
  hashes, native manifest inspection and synthesized manifests.
- `phase3_loader.py`: L0–L4 declarative progressive loading and reference
  containment; scripts/assets/providers remain metadata-only.
- `phase3_host.py`: read-only `CodexHostAdapter`, sanitized snapshots and
  observation boundary.
- `phase3_trust.py`: provenance, compatibility, portability and staleness.
- `phase3_resolution.py`: duplicate analysis, precedence, dependencies,
  conflicts and deterministic selection.
- `phase3_integration.py`: bridge observed manifests into the existing
  immutable registry and minimum route policy without execution.
- `phase3_telemetry.py`: honest phase-3 lifecycle and host-stage events.
- `phase3_benchmarks.py`: reproducible local P3-BENCH-1 operations over a
  temporary 100-capability declarative fixture scenario.
- `phase3_cli.py`: explicit read-only host/inventory/resolve/load-plan CLI.

## Milestones

### M0 — Baseline and control-plane rebaseline

Freeze the quality bar, ADR, supersession note, living plan and TDD RED
evidence before implementation.

### M1 — Bounded host discovery and declarative inventory

Implement safe roots, package parsing, manifest synthesis, hashes,
provenance, trust and compatibility observations.

### M2 — Resolution, loading, telemetry and router bridge

Implement duplicate/dependency/conflict policy, L0–L4 loading, honest events,
load plans and integration with the frozen registry/router.

### M3 — Verification and handoff

Run the complete test/tool/security/benchmark suite, obtain an independent
read-only review, reconcile control state and freeze the Phase 3 evidence.

## Plan of Work

1. Record recovery and supersession controls; create known-good and known-bad
   fixtures; write RED unit/integration/eval tests.
2. Implement immutable models and path safety. Run the security-focused RED →
   GREEN slice before broad discovery.
3. Implement parser, package inventory and manifest synthesis with byte,
   depth, file and reference bounds.
4. Implement host snapshot/root discovery and real read-only smoke. Redact
   personal paths and make unavailable signals explicit.
5. Implement compatibility, trust, stale fingerprints, duplicate blocking,
   dependency-cycle rejection, conflicts and documented precedence.
6. Implement progressive loader, telemetry and load plans. Verify that no
   event claims host-loaded unless a supplied observation says so.
7. Bridge selected metadata to `CapabilityRegistry`/`minimum_route`; prove
   direct-task non-activation and project-local override behavior.
8. Add CLI/doctor, evidence packet, benchmark and security report. Use an
   explicit `refresh` operation that only rescans and writes project-local
   artifacts.
9. Run full regression, coverage, Ruff, mypy, static security checks, real
   host inspection and the Phase 3 benchmark. Commission a fresh read-only
   reviewer after implementation; fix findings and rerun regressions.

## Concrete Steps

1. Reconcile the Phase 3 control plane and keep the implementation-ready gate
   bound to the active task.
2. Run focused Phase 3 tests, then the full regression suite with coverage.
3. Run CLI host smoke checks, security scans and the bounded benchmark.
4. Generate sanitized evidence, manifest, readiness and review artifacts.
5. Obtain independent critique, remediate material findings and rerun gates.

## Validation and Acceptance

Acceptance is P3-QB-1 in `docs/implementation/phase-3-quality-bar.md`:
Phase 2 regression must pass; all host signals must be provenance-labeled;
paths/files/bytes/depth must be bounded; unsafe links and malformed metadata
must fail closed; loading must be declarative and progressive; resolution and
trust must be deterministic; telemetry must not claim unobserved host load;
CLI refresh must remain project-local/read-only; and evidence must include
security, benchmark, coverage and independent review results.

## Risks and Human Decisions

- Real host package layouts and future Codex releases may add fields or roots;
  unknown values remain preserved as unknown, not silently upgraded.
- Divergent duplicates require an explicit hash/path reconciliation or human
  cleanup outside this task; Phase 3 does not mutate the host.
- `pip-audit` availability and host runtime causal signals are environmental
  limitations to report, not reasons to fabricate PASS.

## Idempotence and Recovery

All scans are repeatable and read-only. Re-run discovery after any host change;
stale fingerprints are rejected by resolution. If interrupted, recover from
`.agent/state.json`, `.agent/backlog.json`, the append-only ledgers and the
latest evidence artifacts before advancing status. Never rewrite Phase 2
history or claim a load that was not observed.

## Artifacts and Evidence

The Phase 3 packet is under `evidence/phase-3/` and contains the canonical
sanitized host snapshot/inventory, duplicate/compatibility/trust reports,
loader/router/telemetry evidence, test/coverage/lint/type/security/benchmark
results, independent review, readiness, a review manifest/attestation and the
final implementation report.

## Verification commands

```text
PYTHONPATH=src .venv/bin/pytest -q -p no:cacheprovider
PYTHONPATH=src .venv/bin/coverage run -m pytest -q
PYTHONPATH=src .venv/bin/coverage report --fail-under=80
PYTHONPATH=src .venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/ruff check src tests
PYTHONPATH=src .venv/bin/mypy --no-incremental src
PYTHONPATH=src .venv/bin/python -m harness_kernel.phase3_cli doctor --json
PYTHONPATH=src .venv/bin/python -m harness_kernel.phase3_cli host inspect --json
PYTHONPATH=src .venv/bin/python -m harness_kernel.phase3_cli host list --json
PYTHONPATH=src .venv/bin/python -m harness_kernel.phase3_cli host duplicates --json
PYTHONPATH=src .venv/bin/python -m harness_kernel.phase3_cli capabilities list --json
PYTHONPATH=src .venv/bin/python -m harness_kernel.phase3_cli capabilities inspect harness-kernel --explain --json
```

The final packet must include the exact commands/results, sanitized host
snapshot, inventory JSON, duplicate/compatibility/trust reports, loader and
router evidence, telemetry, security, coverage, benchmark, independent
review, readiness and implementation report. The strongest honest outcome is
`PASS_WITH_LIMITATIONS`.
