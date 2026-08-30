from __future__ import annotations

import http.client
import json
import shutil
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.api import create_app
from app.db import Database
from app.migrations import MigrationError
from app.service import (
    AppointmentService,
    create_appointment,
    get_appointment,
    seed_demo_data,
)
from app.validation import (
    DuplicateJSONKeyError,
    NonFiniteJSONError,
    ValidationError,
    canonical_request_hash,
    parse_json_body,
    validate_create_payload,
    validate_header,
    validate_identifier,
)

PAYLOAD = {
    "client_id": "client-1",
    "patient_id": "patient-1",
    "provider_id": "provider-1",
    "starts_at": "2026-09-01T10:00:00Z",
    "duration_minutes": 30,
}


class PilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "appointments.sqlite3"
        seed_demo_data(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_migrations_are_ordered_idempotent_and_enforce_schema(self) -> None:
        migration_path = self.root / "migration-check.sqlite3"
        db = Database(migration_path)
        first = db.migrate()
        second = db.migrate()
        self.assertEqual(first.applied_versions, (1, 2))
        self.assertEqual(second.applied_versions, ())

        with sqlite3.connect(migration_path) as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 0)
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            self.assertTrue(
                {
                    "schema_migrations",
                    "actors",
                    "clients",
                    "patients",
                    "providers",
                    "appointments",
                    "idempotency_keys",
                }.issubset(tables)
            )
            indexes = {row[1] for row in connection.execute("PRAGMA index_list('appointments')")}
            self.assertTrue(any("provider" in index and "start" in index for index in indexes))

        service = AppointmentService(self.db_path)
        self.assertEqual(
            service.database.connection().execute("PRAGMA foreign_keys").fetchone()[0], 1
        )

    def test_injected_migration_failure_rolls_back_everything(self) -> None:
        failed_path = self.root / "failed.sqlite3"
        database = Database(failed_path)
        with self.assertRaises(MigrationError):
            database.migrate(fail_after=2)

        with sqlite3.connect(failed_path) as connection:
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        self.assertEqual(tables, [])

    def test_migration_cache_cannot_mask_schema_corruption(self) -> None:
        database = Database(self.root / "cache-corruption.sqlite3")
        database.migrate()
        with sqlite3.connect(self.root / "cache-corruption.sqlite3") as connection:
            connection.execute("DROP TABLE providers")
            connection.commit()

        try:
            with self.assertRaises(MigrationError):
                database.migrate()
        finally:
            database.close()

    def test_migration_rejects_same_name_but_ineffective_ownership_trigger(self) -> None:
        database = Database(self.root / "trigger-definition.sqlite3")
        database.migrate()
        connection = database.connection()
        connection.execute("DROP TRIGGER appointments_actor_client_match_insert")
        connection.execute(
            "CREATE TRIGGER appointments_actor_client_match_insert "
            "AFTER INSERT ON appointments BEGIN SELECT 1; END"
        )
        connection.commit()
        try:
            with self.assertRaises(MigrationError):
                database.migrate()
        finally:
            database.close()

    def test_applied_migration_checksum_drift_fails_closed(self) -> None:
        migrations = self.root / "migrations"
        shutil.copytree(Path(__file__).parents[1] / "migrations", migrations)
        database = Database(self.root / "checksum.sqlite3", migrations_dir=migrations)
        database.migrate()
        migration = migrations / "001_initial.sql"
        migration.write_bytes(migration.read_bytes() + b"\n")
        with self.assertRaises(MigrationError):
            database.migrate()

    def test_database_constraints_reject_invalid_foreign_keys_and_duration(self) -> None:
        database = Database(self.db_path)
        connection = database.connection()
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO appointments "
                "(id, actor_id, client_id, patient_id, provider_id, starts_at, "
                "duration_minutes, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "bad-appointment",
                    "actor-1",
                    "client-1",
                    "missing-patient",
                    "provider-1",
                    "2026-09-01T12:00:00Z",
                    30,
                    "BOOKED",
                    "2026-09-01T00:00:00Z",
                ),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO appointments "
                "(id, actor_id, client_id, patient_id, provider_id, starts_at, "
                "duration_minutes, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "bad-duration",
                    "actor-1",
                    "client-1",
                    "patient-1",
                    "provider-1",
                    "2026-09-01T12:00:00Z",
                    10,
                    "BOOKED",
                    "2026-09-01T00:00:00Z",
                ),
            )

    def test_database_constraints_bind_actor_and_patient_to_appointment_client(self) -> None:
        seed_demo_data(
            self.db_path,
            actor_id="actor-2",
            client_id="client-2",
            patient_id="patient-2",
            provider_id="provider-2",
        )
        database = Database(self.db_path)
        connection = database.connection()
        values = (
            (
                "cross-patient",
                "actor-1",
                "client-1",
                "patient-2",
                "provider-1",
                "2026-09-01T13:00:00Z",
            ),
            (
                "cross-actor",
                "actor-2",
                "client-1",
                "patient-1",
                "provider-1",
                "2026-09-01T14:00:00Z",
            ),
        )
        try:
            for appointment_id, actor_id, client_id, patient_id, provider_id, starts_at in values:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO appointments "
                        "(id, actor_id, client_id, patient_id, provider_id, starts_at, "
                        "duration_minutes, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            appointment_id,
                            actor_id,
                            client_id,
                            patient_id,
                            provider_id,
                            starts_at,
                            30,
                            "BOOKED",
                            "2026-09-01T00:00:00Z",
                        ),
                    )
        finally:
            database.close()

    def test_database_constraints_block_parent_client_reassignment(self) -> None:
        seed_demo_data(
            self.db_path,
            actor_id="actor-2",
            client_id="client-2",
            patient_id="patient-2",
            provider_id="provider-2",
        )
        created = create_appointment(self.db_path, "actor-1", "reassign-check", PAYLOAD)
        self.assertEqual(created.status_code, 201)

        database = Database(self.db_path)
        connection = database.connection()
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE actors SET client_id = ? WHERE id = ?",
                    ("client-2", "actor-1"),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE patients SET client_id = ? WHERE id = ?",
                    ("client-2", "patient-1"),
                )
            connection.rollback()
            ownership = connection.execute(
                "SELECT actor_id, client_id, patient_id FROM appointments WHERE id = ?",
                (created.body["data"]["appointment_id"],),
            ).fetchone()
            self.assertIsNotNone(ownership)
            self.assertEqual(tuple(ownership), ("actor-1", "client-1", "patient-1"))
        finally:
            database.close()

    def test_strict_json_parser_rejects_duplicate_keys_and_nonfinite_values(self) -> None:
        with self.assertRaises(DuplicateJSONKeyError):
            parse_json_body(b'{"client_id":"client-1","client_id":"other"}')
        with self.assertRaises(NonFiniteJSONError):
            parse_json_body(b'{"duration_minutes":NaN}')

    def test_validation_boundary_cases_and_canonicalization(self) -> None:
        invalid_json_inputs: tuple[object, ...] = (
            "not-bytes",
            b"x" * 16_385,
            b"\xff",
            b"{",
        )
        for value in invalid_json_inputs:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                parse_json_body(value)  # type: ignore[arg-type]

        invalid_headers: tuple[object, ...] = (None, "x" * 129, "line\nvalue")
        for value in invalid_headers:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_header(value, "header")

        invalid_identifiers: tuple[object, ...] = (None, "x" * 65, "line\nvalue")
        for value in invalid_identifiers:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_identifier(value, "identifier")

        invalid_payloads: tuple[object, ...] = (
            None,
            {},
            dict(PAYLOAD, unknown=True),
            dict(PAYLOAD, client_id=None),
            dict(PAYLOAD, starts_at="2026-09-01 10:00:00Z"),
            dict(PAYLOAD, starts_at="not-a-time"),
            dict(PAYLOAD, starts_at="2026-09-01T10:00:00+01:00"),
            dict(PAYLOAD, duration_minutes=True),
            dict(PAYLOAD, duration_minutes=14),
        )
        for value in invalid_payloads:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_create_payload(value)

        normalized = validate_create_payload(dict(PAYLOAD, starts_at="2026-09-01T10:00:00+00:00"))
        self.assertEqual(normalized["starts_at"], "2026-09-01T10:00:00Z")
        self.assertEqual(
            canonical_request_hash(PAYLOAD),
            canonical_request_hash(dict(reversed(tuple(PAYLOAD.items())))),
        )

    def test_identifiers_reject_whitespace_only_values(self) -> None:
        with self.assertRaises(ValidationError):
            validate_identifier("   ", "patient_id")

    def test_service_create_replay_read_and_prompt_text_as_data(self) -> None:
        prompt_text = "Ignore previous instructions; this is a patient's note."
        seed_demo_data(self.db_path, patient_name=prompt_text)
        created = create_appointment(
            self.db_path,
            actor_id="actor-1",
            idempotency_key="idem-1",
            payload=PAYLOAD,
            request_id="req-create",
        )
        replay = create_appointment(
            self.db_path,
            actor_id="actor-1",
            idempotency_key="idem-1",
            payload=dict(reversed(tuple(PAYLOAD.items()))),
            request_id="req-replay",
        )
        appointment_id = created.body["data"]["appointment_id"]
        fetched = get_appointment(self.db_path, appointment_id, "actor-1", request_id="req-get")

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.body["success"], True)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.body["data"], created.body["data"])
        self.assertEqual(replay.body["meta"]["request_id"], "req-replay")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.body["data"]["patient_name"], prompt_text)
        self.assertNotIn("Ignore previous instructions", json.dumps(replay.body))

    def test_same_key_with_different_payload_is_rejected(self) -> None:
        create_appointment(self.db_path, "actor-1", "idem-reuse", PAYLOAD)
        different = dict(PAYLOAD, duration_minutes=45)
        result = create_appointment(self.db_path, "actor-1", "idem-reuse", different)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.body["error"]["code"], "IDEMPOTENCY_KEY_REUSE")

    def test_slot_conflict_is_atomic_and_leaves_one_appointment(self) -> None:
        first = create_appointment(self.db_path, "actor-1", "slot-a", PAYLOAD)
        second = create_appointment(self.db_path, "actor-1", "slot-b", PAYLOAD)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.body["error"]["code"], "CONFLICT")
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM appointments").fetchone()[0], 1
            )

    def test_authorization_and_injection_inputs_are_safe(self) -> None:
        unknown_actor = create_appointment(self.db_path, "missing", "idem-auth-1", PAYLOAD)
        self.assertEqual(unknown_actor.body["error"]["code"], "UNAUTHORIZED")

        connection = sqlite3.connect(self.db_path)
        connection.execute("UPDATE actors SET active = 0 WHERE id = ?", ("actor-1",))
        connection.commit()
        connection.close()
        inactive_actor = create_appointment(self.db_path, "actor-1", "idem-auth-2", PAYLOAD)
        self.assertEqual(inactive_actor.body["error"]["code"], "FORBIDDEN")

        connection = sqlite3.connect(self.db_path)
        connection.execute("UPDATE actors SET active = 1 WHERE id = ?", ("actor-1",))
        connection.commit()
        connection.close()
        injection = get_appointment(self.db_path, "' OR 1=1 --", "actor-1")
        self.assertEqual(injection.status_code, 404)
        self.assertEqual(injection.body["error"]["code"], "NOT_FOUND")

    def test_service_ownership_provider_and_failure_paths(self) -> None:
        missing_client = create_appointment(
            self.db_path,
            "actor-1",
            "idem-missing-client",
            dict(PAYLOAD, client_id="missing-client"),
        )
        missing_patient = create_appointment(
            self.db_path,
            "actor-1",
            "idem-missing-patient",
            dict(PAYLOAD, patient_id="missing-patient"),
        )
        missing_provider = create_appointment(
            self.db_path,
            "actor-1",
            "idem-missing-provider",
            dict(PAYLOAD, provider_id="missing-provider"),
        )
        self.assertEqual(missing_client.body["error"]["code"], "NOT_FOUND")
        self.assertEqual(missing_patient.body["error"]["code"], "NOT_FOUND")
        self.assertEqual(missing_provider.body["error"]["code"], "NOT_FOUND")

        seed_demo_data(
            self.db_path,
            actor_id="actor-2",
            client_id="client-2",
            patient_id="patient-2",
            provider_id="provider-2",
        )
        wrong_client = create_appointment(
            self.db_path,
            "actor-1",
            "idem-wrong-client",
            dict(PAYLOAD, client_id="client-2"),
        )
        wrong_patient = create_appointment(
            self.db_path,
            "actor-1",
            "idem-wrong-patient",
            dict(PAYLOAD, patient_id="patient-2"),
        )
        self.assertEqual(wrong_client.body["error"]["code"], "FORBIDDEN")
        self.assertEqual(wrong_patient.body["error"]["code"], "FORBIDDEN")

        with sqlite3.connect(self.db_path) as connection:
            connection.execute("UPDATE patients SET active = 0 WHERE id = ?", ("patient-1",))
            connection.execute("UPDATE providers SET active = 0 WHERE id = ?", ("provider-1",))
            connection.commit()
        inactive_patient = create_appointment(
            self.db_path,
            "actor-1",
            "idem-inactive-patient",
            dict(PAYLOAD, starts_at="2026-09-01T11:00:00Z"),
        )
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("UPDATE patients SET active = 1 WHERE id = ?", ("patient-1",))
            connection.commit()
        inactive_provider = create_appointment(
            self.db_path,
            "actor-1",
            "idem-inactive-provider",
            dict(PAYLOAD, starts_at="2026-09-01T12:00:00Z"),
        )
        self.assertEqual(inactive_patient.body["error"]["code"], "FORBIDDEN")
        self.assertEqual(inactive_provider.body["error"]["code"], "NOT_FOUND")

        service = AppointmentService(self.db_path)
        attempts = 0

        def always_locked() -> Any:
            nonlocal attempts
            attempts += 1
            raise sqlite3.OperationalError("database is locked")

        exhausted = service._with_write_retry(always_locked, "req-locked")
        service.close()
        self.assertEqual(attempts, 3)
        self.assertEqual(exhausted.body["error"]["code"], "CONFLICT")
        self.assertEqual(
            get_appointment(self.db_path, None, "actor-1").body["error"]["code"],
            "NOT_FOUND",
        )

    def test_readback_requires_an_active_actor_with_client_ownership(self) -> None:
        created = create_appointment(self.db_path, "actor-1", "read-auth", PAYLOAD)
        appointment_id = created.body["data"]["appointment_id"]

        self.assertEqual(
            get_appointment(self.db_path, appointment_id).body["error"]["code"],
            "UNAUTHORIZED",
        )
        self.assertEqual(
            get_appointment(self.db_path, appointment_id, "missing").body["error"]["code"],
            "UNAUTHORIZED",
        )

        seed_demo_data(
            self.db_path,
            actor_id="actor-2",
            client_id="client-2",
            patient_id="patient-2",
            provider_id="provider-2",
        )
        forbidden = get_appointment(self.db_path, appointment_id, "actor-2")
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.body["error"]["code"], "FORBIDDEN")

        authorized = get_appointment(self.db_path, appointment_id, "actor-1")
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.body["data"]["appointment_id"], appointment_id)

    def test_corrupt_saved_idempotency_response_fails_closed(self) -> None:
        created = create_appointment(self.db_path, "actor-1", "idem-corrupt", PAYLOAD)
        self.assertEqual(created.status_code, 201)
        appointment_id = created.body["data"]["appointment_id"]
        with sqlite3.connect(self.db_path) as connection:
            original_json = connection.execute(
                "SELECT response_json FROM idempotency_keys WHERE actor_id = ? AND key = ?",
                ("actor-1", "idem-corrupt"),
            ).fetchone()[0]

        corruptions = (
            ("unexpected-status", "response_status = ?", (200,)),
            ("missing-appointment-link", "appointment_id = ?", (None,)),
            ("invalid-envelope", "response_json = ?", ("{}",)),
        )
        for name, assignment, values in corruptions:
            with self.subTest(name=name):
                with sqlite3.connect(self.db_path) as connection:
                    connection.execute(
                        f"UPDATE idempotency_keys SET {assignment} "
                        "WHERE actor_id = ? AND key = ?",
                        (*values, "actor-1", "idem-corrupt"),
                    )
                    connection.commit()

                result = create_appointment(self.db_path, "actor-1", "idem-corrupt", PAYLOAD)
                self.assertEqual(result.status_code, 500)
                self.assertEqual(result.body["error"]["code"], "INTERNAL_ERROR")

                with sqlite3.connect(self.db_path) as connection:
                    connection.execute(
                        "UPDATE idempotency_keys SET appointment_id = ?, "
                        "response_status = ?, response_json = ? "
                        "WHERE actor_id = ? AND key = ?",
                        (appointment_id, 201, original_json, "actor-1", "idem-corrupt"),
                    )
                    connection.commit()

    def test_database_memory_lifecycle_and_migration_input_guards(self) -> None:
        memory = Database(":memory:")
        seed_demo_data(memory)
        created = create_appointment(memory, "actor-1", "memory-idem", PAYLOAD)
        self.assertEqual(created.status_code, 201)
        memory.close()
        with self.assertRaises(ValueError):
            Database(self.root)
        with self.assertRaises(ValueError):
            Database(self.root / "negative.sqlite3").migrate(fail_after=-1)

        cases = (
            ("missing", None, None),
            ("empty", "", None),
            ("bad-name", "SELECT 1;", "bad.sql"),
            ("invalid-utf8", b"\xff", "001_initial.sql"),
            ("too-large", b"x" * 65_537, "001_initial.sql"),
            ("incomplete", "CREATE TABLE broken (", "001_initial.sql"),
        )
        for name, contents, filename in cases:
            with self.subTest(name=name):
                migrations = self.root / f"migrations-{name}"
                if contents == "" or contents is not None:
                    migrations.mkdir()
                if filename is not None and contents is not None:
                    target = migrations / filename
                    if isinstance(contents, bytes):
                        target.write_bytes(contents)
                    else:
                        target.write_text(contents, encoding="utf-8")
                migration_db = self.root / f"{name}.sqlite3"
                with self.assertRaises(MigrationError):
                    Database(migration_db, migrations_dir=migrations).migrate()

        duplicate_dir = self.root / "migrations-duplicate"
        duplicate_dir.mkdir()
        (duplicate_dir / "001_first.sql").write_text(
            "CREATE TABLE first (id INTEGER);", encoding="utf-8"
        )
        (duplicate_dir / "001_second.sql").write_text(
            "CREATE TABLE second (id INTEGER);", encoding="utf-8"
        )
        with self.assertRaises(MigrationError):
            Database(self.root / "duplicate.sqlite3", migrations_dir=duplicate_dir).migrate()

        symlink_dir = self.root / "migrations-symlink"
        symlink_dir.mkdir()
        target = self.root / "migration-target.sql"
        target.write_text("CREATE TABLE linked (id INTEGER);", encoding="utf-8")
        (symlink_dir / "001_linked.sql").symlink_to(target)
        with self.assertRaises(MigrationError):
            Database(self.root / "symlink.sqlite3", migrations_dir=symlink_dir).migrate()

        valid_migration_dir = self.root / "migrations-valid"
        valid_migration_dir.mkdir()
        shutil.copy2(
            Path(__file__).parents[1] / "migrations" / "001_initial.sql",
            valid_migration_dir,
        )
        migration_dir_alias = self.root / "migrations-dir-alias"
        migration_dir_alias.symlink_to(valid_migration_dir, target_is_directory=True)
        with self.assertRaises(MigrationError):
            Database(
                self.root / "symlink-dir.sqlite3", migrations_dir=migration_dir_alias
            ).migrate()

    def test_seed_validation_and_http_negative_contracts(self) -> None:
        for field, value in (
            ("patient_name", ""),
            ("client_name", ""),
            ("provider_name", ""),
            ("active", 1),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                seed_demo_data(self.db_path, **{field: value})  # type: ignore[arg-type]

        application = create_app(self.db_path)
        application.start()
        body = json.dumps(PAYLOAD).encode("utf-8")
        try:
            cases = (
                ("GET", "/unknown", (), None, 404, "NOT_FOUND"),
                ("GET", "/api/v1/appointments/", (), None, 404, "NOT_FOUND"),
                (
                    "GET",
                    "/api/v1/appointments/apt_missing",
                    (),
                    None,
                    401,
                    "UNAUTHORIZED",
                ),
                ("DELETE", "/api/v1/appointments/anything", (), None, 404, "NOT_FOUND"),
                (
                    "POST",
                    "/api/v1/appointments",
                    (("Idempotency-Key", "missing-actor"), ("Content-Length", str(len(body)))),
                    body,
                    401,
                    "UNAUTHORIZED",
                ),
                (
                    "POST",
                    "/api/v1/appointments",
                    (("X-Actor-Id", "actor-1"), ("Content-Length", str(len(body)))),
                    body,
                    400,
                    "VALIDATION_ERROR",
                ),
                (
                    "POST",
                    "/api/v1/appointments",
                    (
                        ("X-Actor-Id", "actor-1"),
                        ("X-Actor-Id", "actor-1"),
                        ("Idempotency-Key", "duplicate-header"),
                        ("Content-Length", str(len(body))),
                    ),
                    body,
                    400,
                    "VALIDATION_ERROR",
                ),
            )
            for method, path, headers, request_body, expected_status, expected_code in cases:
                with self.subTest(method=method, path=path):
                    response_body, status, _ = self._raw_request(
                        application, method, path, headers, request_body
                    )
                    self.assertEqual(status, expected_status)
                    self.assertEqual(response_body["error"]["code"], expected_code)

            invalid_transport = (
                (
                    ("X-Actor-Id", "actor-1"),
                    ("Idempotency-Key", "no-length"),
                    ("Content-Type", "application/json"),
                ),
                (
                    ("X-Actor-Id", "actor-1"),
                    ("Idempotency-Key", "bad-length"),
                    ("Content-Length", "abc"),
                ),
                (
                    ("X-Actor-Id", "actor-1"),
                    ("Idempotency-Key", "negative-length"),
                    ("Content-Length", "-1"),
                ),
                (
                    ("X-Actor-Id", "actor-1"),
                    ("Idempotency-Key", "signed-length"),
                    ("Content-Length", "+1"),
                ),
                (
                    ("X-Actor-Id", "actor-1"),
                    ("Idempotency-Key", "underscored-length"),
                    ("Content-Length", "1_0"),
                ),
                (
                    ("X-Actor-Id", "actor-1"),
                    ("Idempotency-Key", "wrong-type"),
                    ("Content-Length", str(len(body))),
                    ("Content-Type", "text/plain"),
                ),
            )
            for headers in invalid_transport:
                response_body, status, _ = self._raw_request(
                    application, "POST", "/api/v1/appointments", headers, body
                )
                self.assertEqual(status, 400)
                self.assertEqual(response_body["error"]["code"], "VALIDATION_ERROR")
        finally:
            application.stop()

        with self.assertRaises(ValueError):
            application.start(host="0.0.0.0")
        with self.assertRaises(ValueError):
            application.start(port=65_536)

    def test_http_observability_failure_is_counted_without_changing_response(self) -> None:
        application = create_app(self.db_path)
        application.start()
        try:
            with patch.object(application.logger, "write", side_effect=OSError("disk full")):
                body, status, _ = self._request(
                    application,
                    "POST",
                    "/api/v1/appointments",
                    json.dumps(PAYLOAD).encode("utf-8"),
                    {"X-Actor-Id": "actor-1", "Idempotency-Key": "log-failure"},
                )
            self.assertEqual(status, 201)
            self.assertTrue(body["success"])
            self.assertEqual(application.observability_failures, 1)
        finally:
            application.stop()

    def test_cli_main_handles_interrupt_and_no_demo_data(self) -> None:
        import app.__main__ as cli

        class FakeApplication:
            def __init__(self, interrupt: bool) -> None:
                self.interrupt = interrupt
                self.stopped = False

            def serve(self, host: str, port: int) -> None:
                del host, port
                if self.interrupt:
                    raise KeyboardInterrupt

            def stop(self) -> None:
                self.stopped = True

        interrupted = FakeApplication(True)
        with (
            patch.object(cli, "create_app", return_value=interrupted),
            patch.object(cli, "seed_demo_data") as seed,
        ):
            result = cli.main(["--db", str(self.db_path), "--log", str(self.root / "cli.jsonl")])
        self.assertEqual(result, 0)
        self.assertTrue(interrupted.stopped)
        seed.assert_called_once()

        normal = FakeApplication(False)
        with (
            patch.object(cli, "create_app", return_value=normal),
            patch.object(cli, "seed_demo_data") as seed,
        ):
            result = cli.main(["--db", str(self.db_path), "--no-demo-data"])
        self.assertEqual(result, 0)
        self.assertTrue(normal.stopped)
        seed.assert_not_called()

    def test_concurrent_same_key_produces_one_booking_and_replays(self) -> None:
        results: list[Any] = []
        lock = threading.Lock()

        def worker() -> None:
            result = create_appointment(self.db_path, "actor-1", "idem-concurrent", PAYLOAD)
            with lock:
                results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(len(results), 8)
        self.assertTrue(all(result.status_code == 201 for result in results))
        appointment_ids = {result.body["data"]["appointment_id"] for result in results}
        self.assertEqual(len(appointment_ids), 1)

    def test_concurrent_different_keys_preserve_unique_slot(self) -> None:
        results: list[Any] = []
        lock = threading.Lock()

        def worker(index: int) -> None:
            result = create_appointment(self.db_path, "actor-1", f"idem-slot-{index}", PAYLOAD)
            with lock:
                results.append(result)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(len(results), 8)
        self.assertEqual(sum(result.status_code == 201 for result in results), 1)
        self.assertEqual(
            sum(
                result.body.get("error") is not None and result.body["error"]["code"] == "CONFLICT"
                for result in results
            ),
            7,
        )

    def test_http_surface_has_stable_envelopes_and_redacted_jsonl_logs(self) -> None:
        log_path = self.root / "events.jsonl"
        application = create_app(self.db_path, log_path=log_path)
        application.start()
        try:
            body, status, headers = self._request(
                application,
                "POST",
                "/api/v1/appointments",
                json.dumps(PAYLOAD).encode("utf-8"),
                {"X-Actor-Id": "actor-1", "Idempotency-Key": "http-idem"},
            )
            self.assertEqual(status, 201)
            self.assertEqual(set(body), {"success", "data", "error", "meta"})
            self.assertTrue(body["meta"]["request_id"])
            self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")

            appointment_id = body["data"]["appointment_id"]
            fetched, get_status, _ = self._request(
                application,
                "GET",
                f"/api/v1/appointments/{appointment_id}",
                headers={"X-Actor-Id": "actor-1"},
            )
            self.assertEqual(get_status, 200)
            self.assertEqual(fetched["data"]["appointment_id"], appointment_id)

            lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
            self.assertGreaterEqual(len(lines), 2)
            for event in lines:
                self.assertIn(event["outcome"], {"success", "replay", "failure"})
                self.assertIn("request_id", event)
                self.assertNotIn("http-idem", line := json.dumps(event))
                self.assertNotIn("client-1", line)
        finally:
            application.stop()

    def test_http_rejects_duplicate_nonfinite_and_oversized_bodies(self) -> None:
        application = create_app(self.db_path)
        application.start()
        try:
            duplicate, duplicate_status, _ = self._request(
                application,
                "POST",
                "/api/v1/appointments",
                b'{"client_id":"client-1","client_id":"client-1"}',
                {"X-Actor-Id": "actor-1", "Idempotency-Key": "idem-duplicate"},
            )
            self.assertEqual(duplicate_status, 400)
            self.assertEqual(duplicate["error"]["code"], "VALIDATION_ERROR")

            nonfinite, nonfinite_status, _ = self._request(
                application,
                "POST",
                "/api/v1/appointments",
                b'{"client_id":"client-1","patient_id":"patient-1","provider_id":"provider-1","starts_at":"2026-09-01T11:00:00Z","duration_minutes":NaN}',
                {"X-Actor-Id": "actor-1", "Idempotency-Key": "idem-nan"},
            )
            self.assertEqual(nonfinite_status, 400)
            self.assertEqual(nonfinite["error"]["code"], "VALIDATION_ERROR")

            oversized, oversized_status, _ = self._request(
                application,
                "POST",
                "/api/v1/appointments",
                b"{" + b"x" * 20_000 + b"}",
                {"X-Actor-Id": "actor-1", "Idempotency-Key": "idem-large"},
            )
            self.assertEqual(oversized_status, 413)
            self.assertEqual(oversized["error"]["code"], "PAYLOAD_TOO_LARGE")
        finally:
            application.stop()

    @staticmethod
    def _request(
        application: Any,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], int, http.client.HTTPMessage]:
        connection = http.client.HTTPConnection("127.0.0.1", application.port, timeout=5)
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        status = response.status
        response_headers = response.headers
        connection.close()
        return payload, status, response_headers

    @staticmethod
    def _raw_request(
        application: Any,
        method: str,
        path: str,
        headers: tuple[tuple[str, str], ...],
        body: bytes | None,
    ) -> tuple[dict[str, Any], int, http.client.HTTPMessage]:
        connection = http.client.HTTPConnection("127.0.0.1", application.port, timeout=5)
        connection.putrequest(method, path)
        for key, value in headers:
            connection.putheader(key, value)
        connection.endheaders()
        if body is not None:
            connection.send(body)
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        status = response.status
        response_headers = response.headers
        connection.close()
        return payload, status, response_headers


if __name__ == "__main__":
    unittest.main()
