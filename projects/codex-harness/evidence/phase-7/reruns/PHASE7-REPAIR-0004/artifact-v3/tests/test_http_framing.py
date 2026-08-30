"""Focused regression tests for strict HTTP request framing."""

from __future__ import annotations

import http.client
import json
import tempfile
import unittest
from pathlib import Path

from app import create_app, seed_demo_data


class HTTPRequestFramingTests(unittest.TestCase):
    def test_post_rejects_transfer_encoding_with_content_length(self) -> None:
        """Ambiguous framing fails closed without creating an appointment."""

        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "appointments.sqlite3"
            seed_demo_data(db_path)
            application = create_app(db_path)
            application.start()
            connection = http.client.HTTPConnection("127.0.0.1", application.port, timeout=5)
            body = json.dumps(
                {
                    "client_id": "client-1",
                    "patient_id": "patient-1",
                    "provider_id": "provider-1",
                    "starts_at": "2026-09-01T11:00:00Z",
                    "duration_minutes": 30,
                }
            ).encode("utf-8")
            try:
                connection.putrequest("POST", "/api/v1/appointments")
                connection.putheader("X-Actor-Id", "actor-1")
                connection.putheader("Idempotency-Key", "ambiguous-framing")
                connection.putheader("Content-Type", "application/json")
                connection.putheader("Content-Length", str(len(body)))
                connection.putheader("Transfer-Encoding", "chunked")
                connection.endheaders()
                connection.send(body)

                response = connection.getresponse()
                payload = json.loads(response.read().decode("utf-8"))

                self.assertEqual(response.status, 400)
                self.assertEqual(payload["error"]["code"], "VALIDATION_ERROR")
                row = (
                    application.database.connection()
                    .execute("SELECT COUNT(*) FROM appointments")
                    .fetchone()
                )
                self.assertEqual(row[0], 0)
            finally:
                connection.close()
                application.stop()


if __name__ == "__main__":
    unittest.main()
