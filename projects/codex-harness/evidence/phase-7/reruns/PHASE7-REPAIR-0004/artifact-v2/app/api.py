"""Loopback-only HTTP API for the disposable appointment service."""

from __future__ import annotations

import json
import socket
import threading
import time
from datetime import UTC
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import gettempdir
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from .db import Database
from .observability import JsonlLogger
from .service import AppointmentService, ServiceResult
from .validation import (
    MAX_BODY_BYTES,
    PayloadTooLargeError,
    ValidationError,
    parse_json_body,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


class _PilotHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class AppointmentApplication:
    """Application object returned by :func:`create_app`.

    ``start`` runs a background loopback server for integration tests. ``serve``
    is the blocking equivalent used by ``python -m app``.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        log_path: str | Path | None = None,
        migrations_dir: str | Path | None = None,
        auto_migrate: bool = True,
    ) -> None:
        self.database = Database(db_path, migrations_dir=migrations_dir)
        if auto_migrate:
            self.database.migrate()
        self.service = AppointmentService(self.database, auto_migrate=False)
        if log_path is None:
            if self.database.path is not None:
                log_path = self.database.path.with_suffix(".jsonl")
            else:
                log_path = Path(gettempdir()) / "backend-appointment-api.jsonl"
        self.logger = JsonlLogger(log_path)
        self._server: _PilotHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._observability_failure_lock = threading.Lock()
        self._observability_failures = 0

    @property
    def observability_failures(self) -> int:
        with self._observability_failure_lock:
            return self._observability_failures

    def record_observability_failure(self) -> None:
        with self._observability_failure_lock:
            self._observability_failures += 1

    @property
    def server_address(self) -> tuple[str, int] | None:
        server = self._server
        if server is None:
            return None
        address = server.server_address
        return str(address[0]), int(address[1])

    @property
    def port(self) -> int:
        address = self.server_address
        if address is None:
            raise RuntimeError("application is not started")
        return address[1]

    @property
    def base_url(self) -> str:
        return f"http://{DEFAULT_HOST}:{self.port}"

    def _new_server(self, host: str, port: int) -> _PilotHTTPServer:
        _require_loopback(host)
        if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65_535:
            raise ValueError("port must be an integer between 0 and 65535")
        handler = _handler_factory(self)
        return _PilotHTTPServer((host, port), handler)

    def start(self, host: str = DEFAULT_HOST, port: int = 0) -> AppointmentApplication:
        with self._lock:
            if self._server is not None:
                raise RuntimeError("application is already running")
            self._server = self._new_server(host, port)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="appointment-api",
                daemon=True,
            )
            self._thread.start()
        return self

    def serve(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        with self._lock:
            if self._server is not None:
                raise RuntimeError("application is already running")
            server = self._new_server(host, port)
            self._server = server
        try:
            server.serve_forever()
        finally:
            with self._lock:
                if self._server is server:
                    self._server = None
            server.server_close()
            self.database.close_thread_connection()

    def stop(self) -> None:
        with self._lock:
            server = self._server
            thread = self._thread
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        with self._lock:
            if self._server is server:
                self._server = None
            self._thread = None
        self.database.close()

    def close(self) -> None:
        self.stop()


def create_app(
    db_path: str | Path,
    *,
    log_path: str | Path | None = None,
    migrations_dir: str | Path | None = None,
    auto_migrate: bool = True,
) -> AppointmentApplication:
    """Build a migrated application without binding a socket."""

    return AppointmentApplication(
        db_path,
        log_path=log_path,
        migrations_dir=migrations_dir,
        auto_migrate=auto_migrate,
    )


def _require_loopback(host: str) -> None:
    if host == "localhost":
        return
    try:
        address = socket.inet_pton(socket.AF_INET, host)
    except (OSError, TypeError):
        address = None
    if address is not None and host == "127.0.0.1":
        return
    try:
        address6 = socket.inet_pton(socket.AF_INET6, host)
    except (OSError, TypeError):
        address6 = None
    if address6 is None or host != "::1":
        raise ValueError("the pilot only binds to localhost")


def _handler_factory(application: AppointmentApplication) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "AppointmentPilot/1"
        sys_version = ""

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def do_DELETE(self) -> None:  # noqa: N802
            self._dispatch("DELETE")

        def do_PUT(self) -> None:  # noqa: N802
            self._dispatch("PUT")

        def do_PATCH(self) -> None:  # noqa: N802
            self._dispatch("PATCH")

        def log_message(self, format: str, *args: object) -> None:
            return

        def _dispatch(self, method: str) -> None:
            started = time.perf_counter()
            request_id = f"req_{uuid4().hex}"
            status = 500
            result: ServiceResult | None = None
            route = "unknown"
            actor_present = False
            idempotency_present = False
            try:
                path = urlsplit(self.path).path
                if method == "POST" and path == "/api/v1/appointments":
                    route = "/api/v1/appointments"
                    result, actor_present, idempotency_present = self._post(request_id)
                elif method == "GET" and path.startswith("/api/v1/appointments/"):
                    route = "/api/v1/appointments/{id}"
                    appointment_id = unquote(path.removeprefix("/api/v1/appointments/"))
                    if not appointment_id or "/" in appointment_id:
                        result = _error_result(404, "NOT_FOUND", "Route was not found.", request_id)
                    else:
                        result, actor_present = self._get(appointment_id, request_id)
                else:
                    result = _error_result(404, "NOT_FOUND", "Route was not found.", request_id)
                status = result.status_code
            except ValidationError:
                result = _error_result(
                    400, "VALIDATION_ERROR", "Request validation failed.", request_id
                )
                status = result.status_code
            except Exception:
                result = _error_result(500, "INTERNAL_ERROR", "Internal server error.", request_id)
                status = result.status_code
            outcome = "failure"
            failure_class: str | None = None
            if result.replayed:
                outcome = "replay"
            elif result.body.get("success") is True:
                outcome = "success"
            else:
                failure_class = _failure_class(result)
            try:
                application.logger.write(
                    {
                        "timestamp": _utc_now(),
                        "request_id": request_id,
                        "method": method,
                        "route": route,
                        "status": status,
                        "outcome": outcome,
                        "failure_class": failure_class,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                        "actor_present": actor_present,
                        "idempotency_present": idempotency_present,
                    }
                )
            except OSError:
                application.record_observability_failure()
            try:
                self._send_result(result)
            finally:
                application.database.close_thread_connection()

        def _post(self, request_id: str) -> tuple[ServiceResult, bool, bool]:
            try:
                actor = self._single_header("X-Actor-Id")
                key = self._single_header("Idempotency-Key")
            except ValidationError:
                self.close_connection = True
                return (
                    _error_result(
                        400, "VALIDATION_ERROR", "Request validation failed.", request_id
                    ),
                    False,
                    False,
                )
            actor_present = actor is not None
            idempotency_present = key is not None
            if actor is None:
                self.close_connection = True
                return (
                    _error_result(401, "UNAUTHORIZED", "Actor is not recognized.", request_id),
                    False,
                    idempotency_present,
                )
            if key is None:
                self.close_connection = True
                return (
                    _error_result(
                        400, "VALIDATION_ERROR", "Request validation failed.", request_id
                    ),
                    actor_present,
                    False,
                )
            try:
                body = self._read_body()
                parsed = parse_json_body(body)
            except PayloadTooLargeError:
                self.close_connection = True
                return (
                    _error_result(
                        413, "PAYLOAD_TOO_LARGE", "Request body is too large.", request_id
                    ),
                    actor_present,
                    idempotency_present,
                )
            except ValidationError:
                self.close_connection = True
                return (
                    _error_result(
                        400, "VALIDATION_ERROR", "Request validation failed.", request_id
                    ),
                    actor_present,
                    idempotency_present,
                )
            return (
                application.service.create_appointment(
                    actor,
                    key,
                    parsed,
                    request_id=request_id,
                ),
                actor_present,
                idempotency_present,
            )

        def _get(self, appointment_id: str, request_id: str) -> tuple[ServiceResult, bool]:
            try:
                actor = self._single_header("X-Actor-Id")
            except ValidationError:
                self.close_connection = True
                return (
                    _error_result(
                        400, "VALIDATION_ERROR", "Request validation failed.", request_id
                    ),
                    False,
                )
            if actor is None:
                self.close_connection = True
                return (
                    _error_result(401, "UNAUTHORIZED", "Actor is not recognized.", request_id),
                    False,
                )
            return (
                application.service.get_appointment(
                    appointment_id,
                    actor,
                    request_id=request_id,
                ),
                True,
            )

        def _single_header(self, name: str) -> str | None:
            values = self.headers.get_all(name, [])
            if len(values) > 1:
                raise ValidationError("duplicate request header")
            return values[0] if values else None

        def _read_body(self) -> bytes:
            # This server only implements fixed-length request framing. Reject
            # Transfer-Encoding even when Content-Length is also present so an
            # intermediary and this handler cannot disagree about body bounds.
            transfer_encoding = self._single_header("Transfer-Encoding")
            if transfer_encoding is not None:
                self.close_connection = True
                raise ValidationError("Transfer-Encoding is not supported")
            content_length = self._single_header("Content-Length")
            if content_length is None:
                self.close_connection = True
                raise ValidationError("Content-Length is required")
            if not content_length.isdecimal():
                self.close_connection = True
                raise ValidationError("Content-Length is invalid")
            try:
                length = int(content_length, 10)
            except ValueError as exc:
                self.close_connection = True
                raise ValidationError("Content-Length is invalid") from exc
            if length < 0:
                self.close_connection = True
                raise ValidationError("Content-Length is invalid")
            if length > MAX_BODY_BYTES:
                self.close_connection = True
                raise PayloadTooLargeError("request body exceeds the maximum size")
            content_type = self._single_header("Content-Type")
            if (
                content_type is not None
                and content_type.split(";", 1)[0].strip().lower() != "application/json"
            ):
                self.close_connection = True
                raise ValidationError("Content-Type must be application/json")
            body = self.rfile.read(length)
            if len(body) != length:
                self.close_connection = True
                raise ValidationError("request body is incomplete")
            return body

        def _send_result(self, result: ServiceResult) -> None:
            payload = json.dumps(
                result.body,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(result.status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def _failure_class(result: ServiceResult) -> str | None:
    error = result.body.get("error")
    code: object = error.get("code") if isinstance(error, dict) else None
    if isinstance(code, str):
        return code
    return None


def _error_result(status: int, code: str, message: str, request_id: str) -> ServiceResult:
    return ServiceResult(
        status,
        {
            "success": False,
            "data": None,
            "error": {"code": code, "message": message},
            "meta": {"request_id": request_id},
        },
    )


def _utc_now() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
