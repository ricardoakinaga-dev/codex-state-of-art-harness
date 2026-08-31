CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY CHECK (version > 0),
    name TEXT NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 128),
    checksum TEXT NOT NULL CHECK (length(checksum) = 64),
    applied_at TEXT NOT NULL CHECK (length(applied_at) >= 20)
);

CREATE TABLE clients (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 64),
    display_name TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 120),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE actors (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 64),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE patients (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 64),
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 240),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE providers (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 64),
    display_name TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 120),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE appointments (
    id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 64),
    actor_id TEXT NOT NULL REFERENCES actors(id) ON DELETE RESTRICT,
    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE RESTRICT,
    provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
    starts_at TEXT NOT NULL CHECK (length(starts_at) BETWEEN 20 AND 32),
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes BETWEEN 15 AND 120),
    status TEXT NOT NULL CHECK (status IN ('BOOKED')),
    created_at TEXT NOT NULL CHECK (length(created_at) >= 20)
);

CREATE UNIQUE INDEX idx_appointments_provider_start
    ON appointments(provider_id, starts_at);

CREATE TABLE idempotency_keys (
    actor_id TEXT NOT NULL REFERENCES actors(id) ON DELETE RESTRICT,
    key TEXT NOT NULL CHECK (length(key) BETWEEN 1 AND 128),
    request_hash TEXT NOT NULL CHECK (length(request_hash) = 64),
    appointment_id TEXT REFERENCES appointments(id) ON DELETE SET NULL,
    response_status INTEGER NOT NULL CHECK (response_status BETWEEN 200 AND 599),
    response_json TEXT NOT NULL CHECK (length(response_json) BETWEEN 2 AND 16384),
    created_at TEXT NOT NULL CHECK (length(created_at) >= 20),
    PRIMARY KEY (actor_id, key)
);
