# Real backend pilot report

Pilot: `pilots/backend-appointment-api/`, a disposable fictional Veterinary
Appointment API using Python 3.12 standard library and SQLite. The pilot binds
only to loopback and uses synthetic actors, clients, patients and providers.

## Executed path

1. Phase 3 discovery found the project-local native package and retained the
   exact vNext fingerprint.
2. Phase 3 safe load prepared bounded instruction context; host package load was
   not asserted and is reported as `HOST_LOAD_UNOBSERVABLE`.
3. Phase 4 `InvocationEngine.prepare` authorized only the pilot workspace write
   roots (`app/` and `migrations/`) and denied network, shell, MCP and
   credentials.
4. The real app-server builder made an actual source change in
   `app/validation.py`. The first material result was invalidated after source
   inspection found the wrong predicate; one bounded lead repair corrected the
   source and added a regression test.
5. Fresh pilot tests, static checks, repeated concurrency checks and a CLI
   subprocess smoke test passed.
6. A fresh real read-only verification-loop-vNext adapter received the immutable
   task, criteria, source digest, test/migration/security evidence and builder
   receipt. It completed all four required procedures and observed no workspace
   delta.

## Final pilot behavior

The API exposes POST create and GET read-back routes with stable envelopes,
strict JSON/header validation, UTC normalization, authorization abstraction,
transactional `BEGIN IMMEDIATE` writes, provider/start uniqueness,
same-key idempotent replay, conflict persistence, ordered checksum-bound
migrations, bounded retries, and redacted JSONL observability.

Final pilot evidence is under
`pilots/backend-appointment-api/` and the detailed structured packet is under
`evidence/phase-7/pilots/backend-engineering/`.

Result: `PASS_WITH_LIMITATIONS`; this is a candidate pilot result, not a
production service assessment.
