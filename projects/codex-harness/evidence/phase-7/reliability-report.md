# Reliability and performance contract — Phase 7 pilot

The synchronous loopback API has no third-party dependency and therefore does
not add retries or a circuit breaker. SQLite connections use a bounded
`busy_timeout`; the booking transaction uses `BEGIN IMMEDIATE`, commits before
responding, and translates lock/constraint outcomes to stable conflict or
internal errors. The application never blindly retries a non-idempotent write.

The request body, header lengths, response bytes, log bytes, migration count,
test concurrency and server lifetime are bounded. A per-request correlation
ID and elapsed duration are recorded. The performance observation is a local
functional budget for the disposable fixture, not a production SLO: all
single-request and bounded concurrent scenarios must complete within the test
timeout, and no unbounded query/list endpoint exists.

The pilot does not add caching, queues or external calls because none solves
the requested booking boundary. Those concerns remain explicit non-goals and
would require their own timeout/retry/idempotency contract.
