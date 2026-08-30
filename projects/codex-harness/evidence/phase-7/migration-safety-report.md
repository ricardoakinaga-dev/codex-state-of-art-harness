# Migration safety contract — Phase 7 pilot

The disposable fixture has one ordered migration, `001_initial.sql`, creating
the schema and constraints. The migration runner validates a safe numeric
filename, reads bounded regular files under the fixture root, applies each
migration in a transaction, records its SHA-256 in `schema_migrations`, and is
idempotent on a second run. An already-applied version with changed bytes is a
hard failure.

The runner verifies tables, foreign keys, check constraints, the appointment
slot unique index and the idempotency primary key after apply. A test database
is copied from an empty temporary path; no production or private data exists.
Injected failure before commit must leave no partially created migration
record. The compatibility posture is explicitly disposable: old application
code is not supported against a changed production schema, and no destructive
operation (`DROP`, `TRUNCATE`, mass rewrite or irreversible transform) is
included.

Rollback is transaction rollback on a failed first migration. There is no
production down-migration claim. If a future non-disposable migration is
requested, the capability must stop for a new authority and compatibility
plan rather than silently reusing this pilot evidence.
