# Test strategy — Phase 7 pilot

The pilot's rational target is 90% line coverage for its small application,
with coverage used as a floor rather than a quality proof. The risk-shaped
suite must cover:

| Layer | Required cases |
| --- | --- |
| Unit | validation, error mapping, canonical request hash, event redaction |
| API/contract | success envelope, invalid JSON/body, unknown route, stable errors |
| Database integration | foreign keys, checks, unique slot and idempotency constraints |
| Transaction | atomic appointment + idempotency write, injected rollback |
| Migration | apply, repeat, checksum drift, schema verification and failed apply |
| Idempotency | same request replay, different payload reuse, concurrent same key |
| Concurrency | concurrent different-key same-slot requests preserve one booking |
| Security | inactive/unknown actor, ownership/IDOR, SQL injection, secret/log scan |
| Observability | JSONL shape, correlation, outcome/failure class, no sensitive payload |
| E2E | migrate → loopback create → replay → conflict → read-back |

Harness tests additionally cover native manifest validation, narrow routing,
exact package identity, safe load, explicit write policy, sandbox mapping,
immutable handoff, stale evidence, artifact substitution, prompt injection,
tool escalation and scope expansion. The prior 519-test Phase 6 result is not
reused as Phase 7 evidence; the full Harness suite is rerun at closeout.

## Closeout observations

The final pilot run recorded 20 passed tests and 91% line coverage (845
statements, 77 missed), exceeding the 90% pilot floor. Ruff format/check and
strict mypy passed for the pilot. Five repeated concurrency-only runs each
recorded `2 passed, 18 deselected`; the real `python -m app` loopback subprocess
smoke also passed. Harness closeout recorded 534 passed and 81% line coverage,
with Ruff and strict mypy passing.

Branch coverage was measured separately at 77% as a diagnostic and is not
substituted for the configured line-coverage gate. The pilot's GET route has no
actor-authentication header by design of this disposable fixture, and its JSONL
logger is best-effort on filesystem write failure; both remain explicit
limitations.
