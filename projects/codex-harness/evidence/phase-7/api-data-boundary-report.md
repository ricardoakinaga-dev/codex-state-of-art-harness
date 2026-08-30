# API and data boundary contract — Phase 7 pilot

## API

The normalized task owns one create flow and one read-back flow:

```text
POST /api/v1/appointments
GET  /api/v1/appointments/{appointment_id}
```

Required request headers for POST are `X-Actor-Id` and `Idempotency-Key`.
The JSON body is an object with `client_id`, `patient_id`, `provider_id`,
`starts_at` (UTC ISO-8601), and `duration_minutes` (15–120). Unknown fields,
duplicate JSON keys, non-finite numbers and oversized bodies are rejected.

Successful responses use:

```json
{"success": true, "data": {"appointment_id": "...", "status": "BOOKED"}, "error": null, "meta": {"request_id": "..."}}
```

Error responses use the same envelope with `success=false`, `data=null`, and
an error object containing only a stable `code` and safe `message`. The bounded
codes are `VALIDATION_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`,
`CONFLICT`, `IDEMPOTENCY_KEY_REUSE`, `PAYLOAD_TOO_LARGE` and
`INTERNAL_ERROR`. Database details never cross the transport boundary.

## Data and authorization

The minimal model is `actors`, `clients`, `patients`, `providers`,
`appointments`, `idempotency_keys` and `schema_migrations`. A client owns its
patients through `patients.client_id`; the actor must be active and authorized
for the client. Provider and patient must be active/known. No real identity,
JWT, tenant or external credential system is introduced.

The appointment uniqueness invariant is `(provider_id, starts_at)`. The
idempotency invariant is `(actor_id, key)` with a request hash. Same key and
same hash returns the saved response; same key and different hash returns
`IDEMPOTENCY_KEY_REUSE`. Different keys for the same slot result in one
`BOOKED` response and one `CONFLICT`, including under concurrent requests.

The API is additive to the fixture and has no existing client compatibility
obligation. The versioned path makes the compatibility assumption explicit.
