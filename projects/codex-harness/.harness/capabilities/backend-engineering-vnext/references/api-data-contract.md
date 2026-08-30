Load when: an API, domain command, persistence write, transaction, invariant, idempotency key, or concurrent mutation is part of the task.

## API contract

Bind method, versioned path, request schema, response schema, stable error
codes, authorization expectation, idempotency behavior, compatibility posture,
and pagination when relevant. Unknown fields, malformed structure, duplicate
members, non-finite numbers, oversized bodies, and invalid headers are
transport or input failures, not domain success.

Keep these classes distinct:

1. transport validation: the request cannot be decoded or does not fit the
   boundary;
2. domain validation: the decoded command violates field or use-case rules;
3. authorization: the actor is absent, inactive, or lacks resource access;
4. business conflict: a valid command cannot be accepted because state or an
   invariant conflicts;
5. persistence or dependency failure: the implementation cannot complete the
   operation and must expose only a stable safe error.

Use a stable envelope when the surrounding API has one. Do not expose query,
storage, stack, or dependency details through the public error. Preserve old
clients and old routes unless the frozen task explicitly changes them.

## Data contract

Name the read model, write model, ownership relation, required fields,
foreign-key relationships, indexes, check rules, uniqueness rules, and
transaction boundary. Database constraints protect invariants that must hold
even when application checks race or a retry repeats an operation.

For every multi-write workflow, record whether it is atomic, whether partial
state is allowed, what rolls back, which failures are retryable, and how the
caller recognizes a replay. An idempotency key is bound to the actor and a
canonical request digest; the same key with a different digest is a typed
reuse error. Do not blindly retry a non-idempotent mutation.

When concurrent writes can conflict, describe the race window and the
database or compare-and-swap invariant that closes it. A pre-check alone is
not sufficient when the invariant can be violated between read and write.

The implementation handoff must include API/data contract identity, observed
responses, persisted-state observations, relevant constraint evidence, test
results, and known limitations.
