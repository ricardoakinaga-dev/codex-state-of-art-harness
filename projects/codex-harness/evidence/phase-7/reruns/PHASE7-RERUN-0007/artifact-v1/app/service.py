"""Domain service for transactional appointment creation and read-back."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .db import Database
from .validation import (
    MAX_ID_LENGTH,
    ValidationError,
    canonical_request_hash,
    validate_create_payload,
    validate_header,
    validate_identifier,
)

MAX_WRITE_RETRIES = 5
RETRY_DELAYS_SECONDS = (0.02, 0.04, 0.08, 0.16, 0.32)


@dataclass(frozen=True, slots=True)
class ServiceResult:
    status_code: int
    body: dict[str, Any]
    replayed: bool = False


class AppointmentService:
    """Application service with a stable, network-free test surface."""

    def __init__(
        self,
        database: Database | str | Path,
        *,
        migrations_dir: str | Path | None = None,
        auto_migrate: bool = True,
    ) -> None:
        self._owns_database = not isinstance(database, Database)
        self.database = (
            Database(database, migrations_dir=migrations_dir)
            if not isinstance(database, Database)
            else database
        )
        if auto_migrate:
            self.database.migrate()

    def close(self) -> None:
        if self._owns_database:
            self.database.close()

    def create_appointment(
        self,
        actor_id: object,
        idempotency_key: object,
        payload: object,
        *,
        request_id: str | None = None,
    ) -> ServiceResult:
        request_id = _normalize_request_id(request_id)
        try:
            actor = validate_identifier(validate_header(actor_id, "X-Actor-Id"), "actor_id")
            key = validate_header(idempotency_key, "Idempotency-Key")
            normalized = validate_create_payload(payload)
            request_hash = canonical_request_hash(normalized)
        except ValidationError:
            return _error(400, "VALIDATION_ERROR", "Request validation failed.", request_id)

        try:
            return self._with_write_retry(
                lambda: self._create_once(actor, key, normalized, request_hash, request_id),
                request_id,
            )
        except sqlite3.IntegrityError:
            return _error(500, "INTERNAL_ERROR", "Internal server error.", request_id)
        except sqlite3.DatabaseError:
            return _error(500, "INTERNAL_ERROR", "Internal server error.", request_id)
        except Exception:
            return _error(500, "INTERNAL_ERROR", "Internal server error.", request_id)

    def _create_once(
        self,
        actor_id: str,
        idempotency_key: str,
        payload: dict[str, object],
        request_hash: str,
        request_id: str,
    ) -> ServiceResult:
        connection = self.database.connection()
        connection.execute("BEGIN IMMEDIATE")
        try:
            actor_row = connection.execute(
                "SELECT id, client_id, active FROM actors WHERE id = ?",
                (actor_id,),
            ).fetchone()
            if actor_row is None:
                result = _error(401, "UNAUTHORIZED", "Actor is not recognized.", request_id)
                connection.rollback()
                return result
            if int(actor_row["active"]) != 1:
                result = _error(403, "FORBIDDEN", "Actor is not active.", request_id)
                connection.rollback()
                return result

            saved = connection.execute(
                "SELECT request_hash, response_status, response_json "
                "FROM idempotency_keys WHERE actor_id = ? AND key = ?",
                (actor_id, idempotency_key),
            ).fetchone()
            if saved is not None:
                if str(saved["request_hash"]) != request_hash:
                    result = _error(
                        409,
                        "IDEMPOTENCY_KEY_REUSE",
                        "Idempotency key was used with a different request.",
                        request_id,
                    )
                    connection.rollback()
                    return result
                replay = _saved_result(saved, request_id)
                connection.rollback()
                return replay

            client_id = str(payload["client_id"])
            client_row = connection.execute(
                "SELECT id, active FROM clients WHERE id = ?",
                (client_id,),
            ).fetchone()
            if client_row is None:
                result = _error(404, "NOT_FOUND", "Client was not found.", request_id)
                connection.rollback()
                return result
            if int(client_row["active"]) != 1 or str(actor_row["client_id"]) != client_id:
                result = _error(
                    403, "FORBIDDEN", "Actor is not authorized for this client.", request_id
                )
                connection.rollback()
                return result

            patient_row = connection.execute(
                "SELECT id, client_id, name, active FROM patients WHERE id = ?",
                (str(payload["patient_id"]),),
            ).fetchone()
            if patient_row is None:
                result = _error(404, "NOT_FOUND", "Patient was not found.", request_id)
                connection.rollback()
                return result
            if str(patient_row["client_id"]) != client_id or int(patient_row["active"]) != 1:
                result = _error(
                    403, "FORBIDDEN", "Patient is not available to this actor.", request_id
                )
                connection.rollback()
                return result

            provider_row = connection.execute(
                "SELECT id, active FROM providers WHERE id = ?",
                (str(payload["provider_id"]),),
            ).fetchone()
            if provider_row is None or int(provider_row["active"]) != 1:
                result = _error(404, "NOT_FOUND", "Provider was not found.", request_id)
                connection.rollback()
                return result

            existing = connection.execute(
                "SELECT id FROM appointments WHERE provider_id = ? AND starts_at = ?",
                (str(payload["provider_id"]), str(payload["starts_at"])),
            ).fetchone()
            if existing is not None:
                result = _error(409, "CONFLICT", "Appointment slot is already booked.", request_id)
                self._insert_idempotency(
                    connection,
                    actor_id,
                    idempotency_key,
                    request_hash,
                    None,
                    result,
                )
                connection.commit()
                return result

            appointment_id = f"apt_{uuid.uuid4().hex}"
            created_at = _utc_now()
            connection.execute(
                "INSERT INTO appointments "
                "(id, actor_id, client_id, patient_id, provider_id, starts_at, "
                "duration_minutes, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    appointment_id,
                    actor_id,
                    client_id,
                    str(payload["patient_id"]),
                    str(payload["provider_id"]),
                    str(payload["starts_at"]),
                    cast(int, payload["duration_minutes"]),
                    "BOOKED",
                    created_at,
                ),
            )
            result = _success(
                201,
                {"appointment_id": appointment_id, "status": "BOOKED"},
                request_id,
            )
            self._insert_idempotency(
                connection,
                actor_id,
                idempotency_key,
                request_hash,
                appointment_id,
                result,
            )
            connection.commit()
            return result
        except BaseException:
            connection.rollback()
            raise

    @staticmethod
    def _insert_idempotency(
        connection: sqlite3.Connection,
        actor_id: str,
        key: str,
        request_hash: str,
        appointment_id: str | None,
        result: ServiceResult,
    ) -> None:
        response_json = json.dumps(
            result.body,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        connection.execute(
            "INSERT INTO idempotency_keys "
            "(actor_id, key, request_hash, appointment_id, response_status, response_json, "
            "created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                actor_id,
                key,
                request_hash,
                appointment_id,
                result.status_code,
                response_json,
                _utc_now(),
            ),
        )

    def _with_write_retry(
        self,
        operation: Callable[[], ServiceResult],
        request_id: str | None = None,
    ) -> ServiceResult:
        for attempt in range(MAX_WRITE_RETRIES + 1):
            try:
                return operation()
            except sqlite3.OperationalError as exc:
                if not _is_locked(exc):
                    raise
                # A retry must never inherit a transaction left open by the
                # failed attempt. Closing SQLite's thread-local connection
                # rolls it back and gives the next bounded attempt clean state.
                self.database.close_thread_connection()
                if attempt >= MAX_WRITE_RETRIES:
                    return _error(
                        409,
                        "CONFLICT",
                        "Database is busy; try the request again.",
                        request_id or _request_id(),
                    )
                time.sleep(RETRY_DELAYS_SECONDS[attempt])
        raise AssertionError("bounded retry loop did not return")

    def get_appointment(
        self,
        appointment_id: object,
        actor_id: object | None = None,
        *,
        request_id: str | None = None,
    ) -> ServiceResult:
        request_id = _normalize_request_id(request_id)
        try:
            identifier = validate_identifier(
                appointment_id, "appointment_id", max_length=MAX_ID_LENGTH
            )
        except ValidationError:
            return _error(404, "NOT_FOUND", "Appointment was not found.", request_id)
        if actor_id is None:
            return _error(401, "UNAUTHORIZED", "Actor is not recognized.", request_id)
        try:
            actor = validate_identifier(validate_header(actor_id, "X-Actor-Id"), "actor_id")
        except ValidationError:
            return _error(400, "VALIDATION_ERROR", "Request validation failed.", request_id)
        try:
            connection = self.database.connection()
            actor_row = connection.execute(
                "SELECT client_id, active FROM actors WHERE id = ?",
                (actor,),
            ).fetchone()
            if actor_row is None:
                return _error(401, "UNAUTHORIZED", "Actor is not recognized.", request_id)
            if int(actor_row["active"]) != 1:
                return _error(403, "FORBIDDEN", "Actor is not active.", request_id)
            row = connection.execute(
                "SELECT a.id, a.client_id, a.patient_id, p.name AS patient_name, "
                "a.provider_id, a.starts_at, a.duration_minutes, a.status, a.created_at "
                "FROM appointments AS a "
                "JOIN patients AS p ON p.id = a.patient_id "
                "WHERE a.id = ?",
                (identifier,),
            ).fetchone()
        except sqlite3.DatabaseError:
            return _error(500, "INTERNAL_ERROR", "Internal server error.", request_id)
        if row is None:
            return _error(404, "NOT_FOUND", "Appointment was not found.", request_id)
        if str(row["client_id"]) != str(actor_row["client_id"]):
            return _error(
                403,
                "FORBIDDEN",
                "Appointment is not available to this actor.",
                request_id,
            )
        return _success(
            200,
            {
                "appointment_id": str(row["id"]),
                "client_id": str(row["client_id"]),
                "patient_id": str(row["patient_id"]),
                "patient_name": str(row["patient_name"]),
                "provider_id": str(row["provider_id"]),
                "starts_at": str(row["starts_at"]),
                "duration_minutes": int(row["duration_minutes"]),
                "status": str(row["status"]),
                "created_at": str(row["created_at"]),
            },
            request_id,
        )


def _is_locked(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return "database is locked" in message or "database table is locked" in message


def _request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def _normalize_request_id(value: str | None) -> str:
    if value is None:
        return _request_id()
    try:
        return validate_header(value, "request_id")
    except ValidationError:
        return _request_id()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _success(status_code: int, data: dict[str, Any], request_id: str) -> ServiceResult:
    return ServiceResult(
        status_code=status_code,
        body={
            "success": True,
            "data": dict(data),
            "error": None,
            "meta": {"request_id": request_id},
        },
    )


def _error(status_code: int, code: str, message: str, request_id: str) -> ServiceResult:
    return ServiceResult(
        status_code=status_code,
        body={
            "success": False,
            "data": None,
            "error": {"code": code, "message": message},
            "meta": {"request_id": request_id},
        },
    )


def _saved_result(row: sqlite3.Row, request_id: str) -> ServiceResult:
    try:
        body = json.loads(str(row["response_json"]))
        if not isinstance(body, dict):
            raise ValueError
        if set(body) != {"success", "data", "error", "meta"}:
            raise ValueError
        if not isinstance(body["meta"], dict) or not isinstance(
            body["meta"].get("request_id"), str
        ):
            raise ValueError
        replay_body = {
            **body,
            "meta": {**cast(dict[str, Any], body["meta"]), "request_id": request_id},
        }
        return ServiceResult(int(row["response_status"]), replay_body, replayed=True)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise sqlite3.DatabaseError("stored idempotency response is invalid") from exc


def create_appointment(
    db_path: Database | str | Path,
    actor_id: object,
    idempotency_key: object,
    payload: object,
    *,
    request_id: str | None = None,
) -> ServiceResult:
    """Create an appointment without starting an HTTP server."""

    service = AppointmentService(db_path)
    try:
        return service.create_appointment(
            actor_id,
            idempotency_key,
            payload,
            request_id=request_id,
        )
    finally:
        service.close()


def get_appointment(
    db_path: Database | str | Path,
    appointment_id: object,
    actor_id: object | None = None,
    *,
    request_id: str | None = None,
) -> ServiceResult:
    """Read an appointment without starting an HTTP server."""

    service = AppointmentService(db_path)
    try:
        return service.get_appointment(appointment_id, actor_id, request_id=request_id)
    finally:
        service.close()


def seed_demo_data(
    db_path: Database | str | Path,
    *,
    actor_id: str = "actor-1",
    client_id: str = "client-1",
    patient_id: str = "patient-1",
    provider_id: str = "provider-1",
    patient_name: str = "Mochi",
    client_name: str = "Demo Client",
    provider_name: str = "Dr. Ada Lovelace",
    active: bool = True,
) -> dict[str, str]:
    """Insert synthetic fixture records for local tests and the CLI demo."""

    actor = validate_identifier(actor_id, "actor_id")
    client = validate_identifier(client_id, "client_id")
    patient = validate_identifier(patient_id, "patient_id")
    provider = validate_identifier(provider_id, "provider_id")
    if not isinstance(patient_name, str) or not 1 <= len(patient_name) <= 240:
        raise ValidationError("patient_name is out of bounds")
    if not isinstance(client_name, str) or not 1 <= len(client_name) <= 120:
        raise ValidationError("client_name is out of bounds")
    if not isinstance(provider_name, str) or not 1 <= len(provider_name) <= 120:
        raise ValidationError("provider_name is out of bounds")
    if not isinstance(active, bool):
        raise ValidationError("active must be boolean")

    service = AppointmentService(db_path)
    try:
        connection = service.database.connection()
        connection.execute("BEGIN IMMEDIATE")
        try:
            enabled = int(active)
            connection.execute(
                "INSERT INTO clients(id, display_name, active) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "display_name = excluded.display_name, active = excluded.active",
                (client, client_name, enabled),
            )
            connection.execute(
                "INSERT INTO actors(id, client_id, active) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "client_id = excluded.client_id, active = excluded.active",
                (actor, client, enabled),
            )
            connection.execute(
                "INSERT INTO patients(id, client_id, name, active) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "client_id = excluded.client_id, name = excluded.name, "
                "active = excluded.active",
                (patient, client, patient_name, enabled),
            )
            connection.execute(
                "INSERT INTO providers(id, display_name, active) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "display_name = excluded.display_name, active = excluded.active",
                (provider, provider_name, enabled),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    finally:
        service.close()
    return {
        "actor_id": actor,
        "client_id": client,
        "patient_id": patient,
        "provider_id": provider,
    }
