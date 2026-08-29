# Phase 4 — Real Capability Invocation Boundary

## Decision and scope

Phase 4 adds one additive, project-local invocation boundary around the frozen
Phase 2 kernel and frozen Phase 3 host-capability packet. It permits exactly one
explicitly approved, script-free fallback pilot through the official Codex
app-server JSON-RPC protocol. It does not authorize arbitrary Skill execution,
shell, scripts, network, MCP, providers, credentials, tools, subagents or
production deployment.

The preferred installed pilots remain negative controls. `design-director` is a
synthesized, global, third-party, partially compatible, script-bearing package
and is inspection-only. `verification-loop` is invalid and rejected. The
project-local `phase4-safe-pilot` fixture is the only controlled-real allowlist
entry.

## Architecture

The boundary is split into immutable models, exact policy/preflight, an official
host adapter, lifecycle execution, artifact capture, verification, evidence and
CLI modules under `src/harness_kernel/phase4_*`:

- `phase4_models.py` freezes authorization, task/context/request bindings,
  budgets, lifecycle, results, artifacts, receipts and assurance.
- `phase4_policy.py` revalidates the Phase 3 record, exact package fingerprint,
  project boundary, context budget and explicit execution permissions.
- `phase4_host.py` uses the documented `initialize → skills/list →
  thread/start → turn/start → event stream` app-server boundary. The thread is
  ephemeral/read-only, network access is disabled, the MCP server table is
  empty, Codex Apps are disabled with `features.apps=false`, every approval is
  declined, every parsed protocol message is counted and summarized for the
  session, and explicit thread/turn mismatches fail closed. Tool, shell, file,
  network, MCP, provider, credential and subagent action events fail closed even
  if a host reports them as completed. The resolved Codex executable and Node
  interpreter are absolute-path, SHA-256-pinned inputs; both digests are bound
  into the controlled-real policy/authorization and rehashed immediately before
  process creation. The full argv is retained without deduplicating repeated
  option tokens.
- `phase4_execution.py` enforces legal transitions, one controlled request,
  monotonic host deadlines, persistent project-local replay reservation and
  receipt binding.
- `phase4_artifacts.py` captures only bounded UTF-8 host output and rejects
  traversal, symlinked ancestors and final symlinks.
- `phase4_verification.py` checks host completion, acceptance criteria, artifact
  integrity, provenance, evidence references and the completed receipt chain.
- `phase4_evidence.py` writes atomically below the evidence root, redacts paths
and secret-like values, fingerprints repository inputs and records metadata-
only before/after state snapshots. Global-state checks cover the Codex
  `config.toml`, `auth.json` metadata, the global `.codex/skills` tree and the
  global `.agents` tree; continuously written Codex session history is explicitly
  outside that mutation scope.

## Host support and epistemic boundary

The official host supports the protocol and a real bounded turn. The observed
pilot returned a completed turn and a host response, but the public event stream
did not expose a correlated Skill-load event. The packet therefore reports
`P4_LEVEL_B` and `HOST_LOAD_UNOBSERVABLE`; it does not infer Skill-load causality
from discovery or turn success.

## Authorization, context and lifecycle

Controlled-real requires all of discovery, trust, compatibility, resolution,
exact fingerprint, explicit policy approval, explicit mode, bounded context,
observability, verification and stop conditions. The task digest, acceptance
criteria, workspace, Skill path, capability identity, package fingerprint, mode,
invocation ID and idempotency key are mutually bound. A prepared invocation
cannot be upgraded by changing its mode or task after preflight. Replay is
reserved atomically in a project-local ledger with an OS file lock and remains
blocked across engine restarts.

The receipt lifecycle is explicit: discovery, resolution, authorization,
context preparation, invocation request, host acknowledgement, execution,
result receipt, verification and closure, with terminal failure, timeout,
cancellation and blocked paths. No result is promoted to success without a
verified artifact and a receipt whose fields and digest are independently
  checked. The capability snapshot is revalidated after host completion as
  well as before the request, so a package mutation during the host turn is a
  fail-closed TOCTOU failure.

## Pilots and evidence

The exact fallback fingerprint, policy, fixture metadata, source, tests, ADR and
pre-review evidence are included in the Phase 4 review manifest. Historical
real-attempt packets referenced by the attempt ledger are also hash-bound as
repository evidence, so attempt counts never rely on unbound archived claims.
The dynamic publisher captures the host result, event telemetry, receipt,
authorization, context, artifact bytes, verification, benchmark measurements
and global metadata snapshots from the same final run. The packet is reviewed
separately and may only close as `PASS_WITH_LIMITATIONS`, `CONDITIONAL_PASS` or
`FAIL`.

## Security and verification

Inputs are schema-validated and fail closed. No user-provided path is trusted
outside the project root. The app-server process is fixed, uses no shell, has a
bounded JSONL protocol, starts a read-only ephemeral thread and uses both the
`mcp_servers={}` and `features.apps=false` configuration overrides. The
subprocess receives a temporary `HOME`, `CODEX_HOME` and `TMPDIR`; only the
host's existing `auth.json` is copied, and global Codex configuration is not
  loaded. The final observed stream contained zero MCP startup-status events;
  the machine-readable host matrix records official documentation, observed
  support, adapter support, confidence and limitations per capability.
Capability-declared scripts,
dependencies, tools, providers, side effects, shell, network, MCP and
credentials are denied for the real pilot. Evidence never includes credential
contents; the scoped global roots are fingerprinted by metadata only, while
volatile parent-session history is excluded and named in the packet.

## Benchmarks and limitations

`P4-BENCH-1` separates control-plane serialization/preparation, artifact read and
verification measurements from the single host wall-clock observation. These
are reproducibility measurements, not production SLOs.

Remaining limitations are the host's unobservable Skill-load causality, the
host-managed authentication/model boundary, bounded metadata snapshots and
the intentionally narrow script-free fixture. Tool/provider/MCP enablement,
arbitrary capability execution, distributed execution, global mutation safety
and production readiness remain excluded.

## ADRs and deferred work

The architecture decision is recorded in
`architecture/docs/adr/ADR-013-phase-4-real-capability-invocation-boundary.md`.
The next phase is deliberately not implemented. Future work may choose a Skill
modernization pilot, a host tool/provider boundary or a Director integration
only after a new scope, policy, evidence packet and independent review.
