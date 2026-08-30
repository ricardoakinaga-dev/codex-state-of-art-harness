Load when: the task changes schema or data, introduces a multi-write workflow, depends on retries or timeouts, or makes a performance or observability claim.

## Migration safety

Declare the ordered migration set, filename/version rule, checksum policy,
apply behavior, repeat behavior, schema/data preservation checks,
compatibility with old and new application versions, lock or index risk, and
rollback or roll-forward posture. A repeated version with changed bytes is a
hard failure. A failed apply must not leave a partial migration record or
partially committed invariant.

Use a disposable fixture for destructive or rollback tests. Treat column
removal, table clearing, mass rewrites, type rewrites, irreversible transforms,
and large-lock operations as `UNSAFE_MIGRATION` until an authority and a
compatibility plan exist. A transaction rollback in a disposable database is
not evidence of a production down-migration.

## Reliability

Name dependency boundaries, timeout limits, retry conditions, cancellation or
cleanup behavior, partial-failure behavior, and safe degradation. Retry only
an operation whose duplicate effect is safe or whose idempotency is proven.
Do not add a circuit breaker, queue, cache, or fallback without a failure mode
and measurement that require it. Never leave an external wait unbounded.

## Performance and observability

Measure the relevant path before optimizing. Check bounded reads, index and
sort alignment, repeated queries, loading volume, and concurrency effects.
Record a local functional budget rather than implying a production SLO from a
fixture. Structured events should include request identity, operation,
outcome, failure class, and duration while omitting bodies, secrets,
credentials, and personal fields. A log assertion is evidence only when the
actual emitted record is observed.
