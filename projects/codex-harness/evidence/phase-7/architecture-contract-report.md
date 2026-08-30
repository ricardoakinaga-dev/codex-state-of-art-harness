# Architecture contract — Phase 7 pilot

## Existing architecture inspection

The Harness is an existing Python 3.12 project with a stdlib-only runtime and
pytest/Ruff/mypy development tooling. Its core is modular (`harness_kernel`)
and already owns discovery, loading, resolution, host preflight, invocation,
evidence, composition and verification. The pilot does not replace those
modules or add a framework to them.

## Decision

Use a small isolated fixture with explicit layers only where the boundary is
real:

```text
HTTP transport → request validation/auth → appointment use case
               → SQLite transaction/repository → structured outcome log
```

The fixture has no generic repository framework, CQRS, event sourcing, service
mesh, cache or queue. SQLite is an appropriate disposable persistence boundary
because it makes constraints, transactions and concurrent race behavior
observable with the installed standard library.

| Boundary | Owner | Inputs | Outputs | Side effects | Failure contract |
| --- | --- | --- | --- | --- | --- |
| HTTP transport | pilot app | method, path, headers, JSON bytes | versioned JSON envelope | loopback response/log event | transport error status |
| auth/validation | appointment service | actor, idempotency key, request DTO | validated command or typed error | none | 400/401/403 |
| persistence | SQLite repository | validated command | appointment/idempotency row | one atomic transaction | conflict/not-found/persistence error |
| migration runner | pilot startup/test | migration files, DB | applied schema/checksum | schema migration table | fail closed and rollback |
| observability | pilot logger | bounded event fields | JSONL record | append local log | no secrets/body/PII |

This solves the pilot's data-integrity problem without forcing a new
architecture on the Harness. The only additive Harness change permitted for
the real builder boundary is a policy-aware app-server sandbox mode whose
default remains read-only.
