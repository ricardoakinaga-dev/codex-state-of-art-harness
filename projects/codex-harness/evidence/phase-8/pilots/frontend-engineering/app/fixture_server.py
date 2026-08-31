"""Deterministic same-origin fixture API and static server for the Phase 8 pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import parse_qs, urlparse


APP_ROOT = Path(__file__).resolve().parent
MAX_BODY_BYTES = 64 * 1024
SUBMISSIONS: dict[str, dict[str, Any]] = {}
SUBMISSIONS_LOCK = Lock()
QUEUE_ITEMS = (
    {"patient": "Miso", "species": "Cat", "urgency": "critical", "waiting": "08 min", "detail": "Breathing concern"},
    {"patient": "Juniper", "species": "Dog", "urgency": "urgent", "waiting": "14 min", "detail": "Acute pain"},
    {"patient": "Otis", "species": "Rabbit", "urgency": "soon", "waiting": "21 min", "detail": "Not eating"},
    {"patient": "Pip", "species": "Bird", "urgency": "routine", "waiting": "29 min", "detail": "Wing check"},
)
ALLOWED_SPECIES = frozenset({"dog", "cat", "rabbit", "bird"})
ALLOWED_URGENCIES = frozenset({"critical", "urgent", "soon", "routine"})


def queue_payload(scenario: str) -> dict[str, Any]:
    if scenario == "error":
        return {"status": "error", "message": "The local queue fixture is temporarily unavailable."}
    if scenario == "empty":
        return {"status": "success", "items": []}
    return {"status": "success", "items": [dict(item) for item in QUEUE_ITEMS]}


def validate_intake(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"ok": False, "errors": {"form": "Intake payload must be an object."}}
    errors: dict[str, str] = {}
    patient = payload.get("patient")
    species = payload.get("species")
    urgency = payload.get("urgency")
    notes = payload.get("notes", "")
    if not isinstance(patient, str) or not 2 <= len(patient.strip()) <= 60:
        errors["patient"] = "Patient name must be 2–60 characters."
    if not isinstance(species, str) or species not in ALLOWED_SPECIES:
        errors["species"] = "Choose a supported species."
    if not isinstance(urgency, str) or urgency not in ALLOWED_URGENCIES:
        errors["urgency"] = "Choose a supported urgency."
    if not isinstance(notes, str) or len(notes) > 180:
        errors["notes"] = "The handoff note is too long."
    return {"ok": not errors, "errors": errors}


def intake_payload(payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:10]
    return {"status": "accepted", "intake_id": f"INT-{digest.upper()}", "triage": "queued"}


def reserve_submission(payload: dict[str, Any], idempotency_key: str) -> tuple[dict[str, Any], bool]:
    """Atomically return an existing record or reserve one for this key."""

    with SUBMISSIONS_LOCK:
        existing = SUBMISSIONS.get(idempotency_key)
        if existing is not None:
            return dict(existing), False
        accepted = intake_payload(payload, idempotency_key)
        SUBMISSIONS[idempotency_key] = accepted
        return dict(accepted), True


class FixtureHandler(BaseHTTPRequestHandler):
    server_version = "NorthlineFixture/1.0"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: HTTPStatus, payload: object) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _path_parts(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urlparse(self.path)
        return parsed.path, parse_qs(parsed.query, keep_blank_values=True)

    def do_GET(self) -> None:  # noqa: N802
        path, query = self._path_parts()
        scenario = query.get("scenario", ["default"])[0]
        if path == "/api/queue":
            if scenario == "loading":
                time.sleep(0.25)
            payload = queue_payload(scenario)
            self._json(HTTPStatus.SERVICE_UNAVAILABLE if payload["status"] == "error" else HTTPStatus.OK, payload)
            return
        if path == "/api/health":
            self._json(HTTPStatus.OK, {"status": "ok", "fixture": "local"})
            return
        if path not in {"/", "/index.html", "/styles.css", "/app.js"}:
            self._json(HTTPStatus.NOT_FOUND, {"status": "error", "message": "Resource not found."})
            return
        file_name = "index.html" if path in {"", "/"} else path.lstrip("/")
        candidate = (APP_ROOT / file_name).resolve()
        if not candidate.is_relative_to(APP_ROOT) or not candidate.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"status": "error", "message": "Resource not found."})
            return
        payload = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        path, query = self._path_parts()
        if path != "/api/intakes":
            self._json(HTTPStatus.NOT_FOUND, {"status": "error", "message": "Endpoint not found."})
            return
        if query.get("scenario", ["default"])[0] == "submit-error":
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "message": "Triage is temporarily unavailable."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = MAX_BODY_BYTES + 1
        if length <= 0 or length > MAX_BODY_BYTES:
            self._json(HTTPStatus.BAD_REQUEST, {"status": "error", "message": "Request body is invalid."})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"status": "error", "message": "Request body is not valid JSON."})
            return
        validation = validate_intake(payload)
        if not validation["ok"]:
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"status": "error", "message": "Check the highlighted intake fields.", "errors": validation["errors"]})
            return
        key = self.headers.get("Idempotency-Key", "").strip()
        if not key or len(key) > 128:
            self._json(HTTPStatus.BAD_REQUEST, {"status": "error", "message": "Idempotency key is required."})
            return
        accepted, created = reserve_submission(payload, key)
        self._json(HTTPStatus.CREATED if created else HTTPStatus.OK, accepted if created else {**accepted, "status": "duplicate"})


def serve(port: int) -> None:
    if not 1024 <= port <= 65535:
        raise ValueError("port must be between 1024 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", port), FixtureHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the local Phase 8 frontend fixture")
    parser.add_argument("--port", type=int, default=4173)
    arguments = parser.parse_args()
    serve(arguments.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
