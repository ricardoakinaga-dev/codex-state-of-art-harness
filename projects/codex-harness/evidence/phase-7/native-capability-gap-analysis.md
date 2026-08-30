# Codex-native gap analysis

## Native capabilities already available

The Harness and Codex host already provide general instruction loading,
project-local discovery, safe metadata parsing, path/trust/compatibility
resolution, exact identity binding, Phase 4 preflight, app-server transport,
project-local workspace confinement, test/lint/typecheck execution by the lead,
and a separate read-only `verification-loop-vnext`. The architecture also
separates API design, coding standards, TDD, security review, orchestration,
assurance and release authority.

`backend-engineering-vnext` must not repeat generic advice such as “write clean
code”, “handle errors” or “use tests”. It should add only backend-specific
decisions that the native surfaces do not guarantee.

## Gap matrix

| Concern | Native/general surface | Backend-specific gap | vNext requirement |
| --- | --- | --- | --- |
| Repository inspection | Phase 3 discovery and project context | Identify service/use-case/data owners before a backend change | Boundary inventory in the implementation plan |
| API | `api-design` and general coding | Bind API behavior to persistence, auth, errors and idempotency | Route contract and API/data handoff |
| Persistence | General language/database tooling | Make consistency, constraints and transaction scope explicit | Data-boundary contract |
| Concurrency | No generic guarantee | Protect a booking/invariant under retries and races | Constraint + concurrency test |
| Migration | General file/command execution | Compatibility, data preservation and rollback risk | Migration contract and stop |
| Security | `security-review` final authority | Recognize backend triggers at the implementation boundary | Explicit security handoff, never self-approval |
| Reliability | General code can retry/wait | Retry only safe operations and bound dependencies | Timeout/retry/degradation policy |
| Observability | General logging | Correlate backend outcomes without PII/secrets | Structured event contract |
| Verification | `verification-loop-vnext` | Supply backend-specific evidence and fresh artifact identity | Immutable builder handoff |
| Scope adaptation | Orchestrator/engineering framework | Avoid full architecture rewrites for one endpoint | Task-scale profile and scope stop |

The value hypothesis is operational: the specialist should reduce missing
backend boundary decisions and false confidence on a real isolated feature.
Benchmark outputs are labeled `PILOT_MODERNIZATION_EVIDENCE`; this packet does
not claim causality or universal superiority.
