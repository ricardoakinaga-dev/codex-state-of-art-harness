Load when: implementation is complete enough for factual verification, a repair is requested, or a backend result must cross the specialist boundary.

Emit one immutable handoff record with these fields:

- task, run, package, profile, and authority identities;
- frozen acceptance and criteria digest;
- implementation-plan identity and smallest-change decision;
- exact changed artifact and diff references with current digests;
- API, validation, authorization, error, data, transaction, migration,
  reliability, performance, and observability contract references that apply;
- tests and static observations actually run, plus required checks not run;
- persisted-state, response, event, migration, concurrency, and idempotency
  evidence when the boundary requires them;
- builder receipt and host write-root policy;
- security handoff status and separate owner when triggered;
- limitations, residual risk, confidence, and next owner.

The handoff is a report of implementation evidence, not approval. A
read-only verifier must receive the task, criteria, artifact/diff identity,
test evidence, migration evidence, API/data contracts, and builder receipt.
The verifier may return `PASS`, `PARTIAL`, `FAIL`, `BLOCKED`, `STALE`, or
`UNKNOWN`; it does not repair, redefine criteria, or authorize release.

If a repair changes any artifact, contract, test, migration, or evidence
identity, mark the prior result stale. The single permitted repair must have a
structured finding, a bounded plan, fresh observations, and a fresh final
verification with rebound digests.
