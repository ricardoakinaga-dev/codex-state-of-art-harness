# Backend appointment API pilot

This is a bounded, disposable Veterinary Appointment API implemented with
Python 3.12's standard library only. It is a Phase 7 fixture, not a
production-ready identity, tenancy, or scheduling system. It binds to
`127.0.0.1` only and uses a temporary SQLite database and JSONL log in the
examples below.

## Stable test surface

The preferred test surface does not require a socket:

```python
from pathlib import Path

from app.service import create_appointment, get_appointment, seed_demo_data

db_path = Path("/tmp/appointment-pilot.sqlite3")
seed_demo_data(db_path)

created = create_appointment(
    db_path,
    "actor-1",
    "demo-key-1",
    {
        "client_id": "client-1",
        "patient_id": "patient-1",
        "provider_id": "provider-1",
        "starts_at": "2026-09-01T10:00:00Z",
        "duration_minutes": 30,
    },
)
appointment_id = created.body["data"]["appointment_id"]
fetched = get_appointment(db_path, appointment_id, "actor-1")
assert created.status_code == 201
assert fetched.status_code == 200
```

`AppointmentService(db_path)` exposes the same `create_appointment` and
`get_appointment` methods. `seed_demo_data` inserts only synthetic records:
`actor-1`, `client-1`, `patient-1`, and `provider-1`. Patient names are stored
as data, including text that resembles a prompt injection; the service never
executes or interprets that text.

For loopback integration tests, `app.api.create_app(db_path)` returns an
`AppointmentApplication` with `start(host="127.0.0.1", port=0)`, `stop()`,
`serve()`, `port`, and `base_url`:

```python
from app.api import create_app

application = create_app(db_path, log_path="/tmp/appointment-pilot.jsonl")
application.start()
try:
    print(application.base_url)
    # Send requests to application.port with http.client or urllib.
finally:
    application.stop()
```

## HTTP contract

The API exposes exactly these useful routes:

```text
POST /api/v1/appointments
GET  /api/v1/appointments/{appointment_id}
```

POST requires `X-Actor-Id` and `Idempotency-Key`; GET requires `X-Actor-Id` for
the active actor that owns the appointment's client. Its JSON body must contain
exactly these fields:

```json
{
  "client_id": "client-1",
  "patient_id": "patient-1",
  "provider_id": "provider-1",
  "starts_at": "2026-09-01T10:00:00Z",
  "duration_minutes": 30
}
```

`starts_at` must be a UTC ISO-8601 timestamp and `duration_minutes` must be an
integer from 15 through 120. Bodies are limited to 16 KiB; header values are
bounded; duplicate JSON keys and `NaN`/`Infinity` are rejected. Unknown JSON
fields are rejected. The service normalizes equivalent UTC timestamp forms
before hashing and applying the provider/start unique constraint.

Every response is an envelope with the same shape:

```json
{
  "success": true,
  "data": {"appointment_id": "apt_...", "status": "BOOKED"},
  "error": null,
  "meta": {"request_id": "req_..."}
}
```

Errors use `success: false`, `data: null`, and a stable error `code` and safe
`message`. The supported codes are `VALIDATION_ERROR`, `UNAUTHORIZED`,
`FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `IDEMPOTENCY_KEY_REUSE`,
`PAYLOAD_TOO_LARGE`, and `INTERNAL_ERROR`.

The first request for an idempotency key commits its appointment and saved
response atomically. A same-actor, same-key request with the same normalized
payload replays the saved result data while assigning the current request's
correlation ID. Reusing that key with another payload is
`IDEMPOTENCY_KEY_REUSE`. A provider/start collision is `CONFLICT`, including
under bounded concurrent requests; a conflict result is also recorded for
safe same-key replay.

## Migrations and schema

`migrations/001_initial.sql` is applied in numeric order by
`app.migrations.MigrationRunner`. Each regular migration file is size- and
filename-bounded, hashed with SHA-256, and recorded in `schema_migrations`.
Rerunning an unchanged migration is a no-op. Changing the bytes or name of an
already-applied version fails closed. SQL statements run inside an explicit
transaction; `migrate(fail_after=N)` is a test-only injected failure point and
must leave no partial migration record or schema.

The schema contains `schema_migrations`, `actors`, `clients`, `patients`,
`providers`, `appointments`, and `idempotency_keys`. Each connection enables
foreign keys and a 250 ms busy timeout. Appointment writes use `BEGIN
IMMEDIATE` with only two bounded lock retries. SQL values are always bound
parameters. The provider/start slot and actor/key idempotency invariants are
also enforced by SQLite constraints.

## Run locally

From this directory:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m app --port 8000
```

The CLI migrates the temporary default database and seeds synthetic demo data.
Use `--db PATH`, `--log PATH`, `--port PORT`, or `--no-demo-data` to override
that disposable setup. `--host` accepts only `127.0.0.1`, `localhost`, or
`::1`.

JSONL events contain request correlation, route template, status, outcome,
failure class, duration, and header-presence booleans. They never contain the
request body, idempotency key, actor value, patient/client/provider value, or
database exception details.
