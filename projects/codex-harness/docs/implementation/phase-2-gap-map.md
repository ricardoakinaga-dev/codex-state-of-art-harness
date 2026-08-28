# Phase 2 gap map

Status: final audit — `CONDITIONAL PASS` for the bounded local kernel; opened
2026-08-28 and reconciled after the final local verification round. The
independent review criterion remains unavailable and therefore no
`PHASE2-VERIFIED` gate is claimed.

This is the implementation map for the bounded, project-local deterministic execution kernel. It is deliberately separate from the older readiness reports: those reports are evidence inputs, not a substitute for this capability-by-capability reconciliation. `COMPLETE` means that the current code, tests, and executable evidence agree within the declared Phase 2 boundary; `PARTIAL` means that a meaningful slice exists but a required invariant, adversarial proof, host integration, or independent challenge is outside or still missing.

## Scope classification

| Area | Classification | Decision |
| --- | --- | --- |
| Local deterministic fixtures, direct execution, sequential DAGs, typed artifacts/evidence, bounded repair, persistence, recovery, telemetry, CLI | remain phase 2 | Must be complete and executable before the Phase 2 gate is closed. |
| Real Codex host loading, real Skills/subagents/MCP/shell/network/credentials, production deployment, hostile multi-process sandboxing, advanced concurrency | freeze later | Explicitly out of the Phase 2 acceptance surface; retain only as documented limitations. |
| Architecture vocabulary and future orchestration/quality concepts without host capability execution | acceptable early | Keep only where it is typed, bounded, honest, and does not imply host execution. |
| Any provider fallback, engine self-authorization, unverifiable success, hidden execution, or route activation based only on an incidental token | architectural violation | Must be rejected or fixed, not deferred. |

## Capability reconciliation

Evidence references use project-relative paths. `P2-*` tests are the executable proof set; the final row status may not be promoted without a fresh run after the last change.

| Capability | Documented | Implemented | Tested | Evidence | Status | Action |
| --- | --- | --- | --- | --- | --- | --- |
| TaskProfile | yes | yes | yes | `src/harness_kernel/models.py`; `tests/unit/test_phase2_kernel.py` | COMPLETE | Re-run in final matrix. |
| Request normalization | yes | yes | yes | `src/harness_kernel/classification.py`, `boundary.py`; CLI validation tests | COMPLETE | Re-run malformed/oversized input cases. |
| Context handling | yes | partial | partial | `models.py`; execution tests | PARTIAL | Verify context references, scope, provenance, and absence of hidden host context. |
| Classification | yes | yes | yes | `classification.py`; profile and negative-routing tests | COMPLETE | Preserve the seven-case negative matrix in regression runs. |
| Domain / complexity / risk | yes | yes | yes | `classification.py`, `models.py`, profile tests | COMPLETE | Preserve deterministic scores and conservative defaults at boundary cases. |
| Visual / research / reversibility / parallelism signals | yes | yes | yes | classification/routing modules and routing tests | COMPLETE | Preserve explicit signal precedence and lexical-coincidence exclusions. |
| Candidate discovery | yes | yes | yes | `routing.py`, registry tests | COMPLETE | Re-run with unavailable and non-provider manifests. |
| Positive routing activation | yes | yes | yes | routing tests and route fixtures | COMPLETE | Preserve positive specialist activation tests. |
| Negative routing activation | yes | yes | yes | seven-case parameterized matrix in `test_routing.py` | COMPLETE | Preserve the mandatory negative examples. |
| Conflict handling | yes | yes | yes | `routing.py`, route tests | COMPLETE | Preserve competing-signal and tie-break assertions. |
| Minimal sufficient route | yes | yes | yes | route decision model and routing tests | COMPLETE | Preserve direct routing when no specialist is justified. |
| Route validation and explanation | yes | yes | yes | CLI route/profile tests; routing models | COMPLETE | Re-run after classifier changes. |
| Provider registry | yes | yes | yes | `providers.py`, registry tests | COMPLETE | Confirm local-only inventory and deterministic availability. |
| Authority and delegation | yes | yes | yes | `authority.py`, explicit-authority and adversarial tests | COMPLETE | Keep grants caller-owned; missing authority remains a first-class deny. |
| ExecutionGraph model | yes | yes | yes | `graph.py`, graph validation tests | COMPLETE | Re-run duplicate/cycle/dangling/budget cases. |
| Direct execution | yes | yes | yes | `execution.py`, execution-path tests | COMPLETE | Preserve as a first-class path while integrating remaining controls. |
| Sequential DAG execution | yes | yes | yes | `graph.py`, graph execution/adversarial tests | COMPLETE | Preserve ordering, partial preservation, and dependency blocking. |
| Graph lifecycle states | yes | yes | yes | `models.py`, graph executor, lifecycle tests | COMPLETE | Preserve documented lifecycle and terminal semantics. |
| Invocation lifecycle states | yes | yes | yes | `models.py`, execution telemetry and lifecycle tests | COMPLETE | Preserve legal transitions and impossible-transition rejection. |
| Artifacts and lineage | yes | yes | yes | `artifacts.py`, execution/adversarial evidence tests | COMPLETE | Preserve digest and lineage checks for success, partial, timeout, and repair. |
| Evidence and claim relationships | yes | yes | yes | `evidence.py`, `verification.py`, forged/stale tests | COMPLETE | Preserve typed claims, source refs, freshness, status, and rejection of unsupported success. |
| Verification facts | yes | yes | yes | `verification.py`, verification tests | COMPLETE | Preserve separation of observed facts, critique, and assurance. |
| Critique findings | yes | yes | partial | `assurance.py`, adversarial tests | PARTIAL | Runtime boundary is covered; independent external challenge remains unavailable. |
| Assurance decisions | yes | yes | partial | `assurance.py`, execution/adversarial tests | PARTIAL | Runtime boundary is covered; independent external challenge remains unavailable. |
| Bounded repair | yes | yes | yes | `execution.py`, repair tests | COMPLETE | Preserve hypothesis, finding, artifact version, expected improvement, result, and exhaustion. |
| Stop conditions | yes | yes | partial | `stops.py`, execution paths and bounded-stop tests | PARTIAL | Some exhaustive policy combinations remain future expansion; no production claim. |
| Timeout | yes | yes | yes | timeout tests | COMPLETE | Re-run direct and graph deadlines; inspect provider thread behavior. |
| Cancellation | yes | yes | yes | cancellation tests | COMPLETE | Re-run before-call and during-provider cases. |
| Retry | yes | yes | yes | retry tests | COMPLETE | Confirm bounded attempts and observable attempt lineage. |
| Token / duration / evidence / telemetry budgets | yes | yes | yes | `models.py`, execution-path and adversarial tests | COMPLETE | Preserve budget exhaustion as a non-success terminal outcome. |
| Telemetry | yes | yes | yes | `telemetry.py`, persistence/adversarial tests | COMPLETE | Preserve bounded append, identity, lifecycle consistency, redaction, and honest truncation. |
| Persistence | yes | yes | yes | `persistence.py`, execution/adversarial tests | COMPLETE | Preserve atomic owned writes and idempotent lifecycle append. |
| Recovery | yes | yes | yes | `persistence.py`, recovery/adversarial tests | COMPLETE | Preserve terminal, unfinished, missing, corrupt, and identity-mismatch distinctions. |
| CLI run / dry-run / explain / stop / cancel | yes | yes | yes | `cli.py`, CLI integration tests | COMPLETE | Preserve public exit classes and output honesty. |
| CLI doctor / quality | yes | yes | yes | CLI integration tests; `evidence/phase-2` | COMPLETE | Preserve metadata-only behavior and explicit non-goals. |
| Benchmarks | yes | yes | yes | `benchmarks.py`, fresh `benchmark-summary.json` | COMPLETE | Preserve methodology and local-only limitations. |
| Security boundary | yes | yes | yes | `boundary.py`, adversarial path/JSON/provider tests | COMPLETE | Preserve input, path, symlink, manifest, provider, and disclosure controls. |
| Project isolation | yes | yes | yes | `boundary.py`, CLI root tests | COMPLETE | Preserve project-local persistence for every public path. |
| Capability isolation | yes | yes | yes | provider/registry tests and local fixture tree | COMPLETE | Preserve exact provider selection with no fallback, import, or network path. |

## Final local gate

The historical checkpoint reported 12 direct-kernel tests passing and remains
unchanged as an append-only record. The final local round expanded the proof to
187 tests, 84% total coverage, passing Ruff and mypy, seven CLI integration
tests, a fresh `P2-BENCH-1` report, security scans, and a reconciled control
ledger. The independent critic was attempted but did not return a usable
report, so this map is `CONDITIONAL` and Phase 2 is not `VERIFIED`.

## Closure rule

Rows may move to `COMPLETE` only when source, tests, and fresh evidence agree. A documentation-only claim cannot close an implementation gap. A passing test that does not exercise the public or integrated path cannot close an integration gap. Out-of-scope future work remains explicitly limited and is not silently counted as complete.

The remaining conditional item is governance evidence, not an inferred runtime
capability: obtain a fresh independent read-only review, then either resolve
its Critical/High findings and request the final gate or keep the bounded
`CONDITIONAL PASS` with the same limitations.
