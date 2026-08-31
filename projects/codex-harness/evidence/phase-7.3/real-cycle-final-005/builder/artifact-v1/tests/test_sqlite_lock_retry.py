from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.service import AppointmentService


class SQLiteLockRetryTests(unittest.TestCase):
    def test_extended_sqlite_locked_code_retries_without_message_matching(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AppointmentService(Path(temp_dir) / "appointments.sqlite3")
            attempts = 0
            sentinel = object()

            def transient_extended_lock() -> Any:
                nonlocal attempts
                attempts += 1
                if attempts <= 2:
                    error = sqlite3.OperationalError("opaque sqlite contention")
                    error.sqlite_errorcode = sqlite3.SQLITE_LOCKED | (1 << 8)
                    raise error
                return sentinel

            try:
                with patch("app.service.time.sleep") as sleep:
                    result = service._with_write_retry(
                        transient_extended_lock,
                        "req-extended-lock",
                    )
            finally:
                service.close()

        self.assertIs(result, sentinel)
        self.assertEqual(attempts, 3)
        self.assertEqual(sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
