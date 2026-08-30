# Backend pilot summary

The isolated veterinary appointment pilot exercised API validation, structured
errors, authorization abstraction, SQLite constraints, transactional writes,
idempotency, concurrency, migration checksum/rollback behavior, redacted
observability and prompt-injection-as-data handling.

The real builder path produced an invalidated v1, then one bounded repair
produced v2. Fresh pilot evidence is green: 20 tests, 91% line coverage, Ruff,
strict mypy, five repeated concurrency checks and a CLI subprocess smoke test.
The real read-only verifier completed the four required criteria and observed
no workspace mutation.

Decision: `PASS_WITH_LIMITATIONS`, `P7_LEVEL_B`, `VERIFIED_CANDIDATE` only
within the project-local Phase 7 scope. No Level C, stable, production,
security-approval, migration, causal-improvement or AAA claim is made.
