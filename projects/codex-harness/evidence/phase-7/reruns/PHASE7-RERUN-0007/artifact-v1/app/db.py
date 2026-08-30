"""SQLite connection and migration entry points for the disposable pilot."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
BUSY_TIMEOUT_MS = 2_000
MIGRATION_RETRY_DELAYS_SECONDS = (0.02, 0.05, 0.1, 0.2)
_MIGRATION_LOCK = threading.Lock()


class Database:
    """A small per-thread SQLite connection registry.

    The database is file-backed by default. ``:memory:`` is supported through a
    private shared-memory URI kept alive by an anchor connection so that the
    per-thread connection rule still holds in tests.
    """

    def __init__(self, db_path: str | Path, *, migrations_dir: str | Path | None = None) -> None:
        self._local = threading.local()
        self.migrations_dir = (
            Path(migrations_dir) if migrations_dir is not None else DEFAULT_MIGRATIONS_DIR
        )
        self.path: Path | None
        self._uri = False
        self._target: str
        self._anchor: sqlite3.Connection | None = None
        if str(db_path) == ":memory:":
            self.path = None
            self._uri = True
            self._target = f"file:appointment-pilot-{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._anchor = self._open_connection()
        else:
            self.path = Path(db_path)
            if self.path.exists() and self.path.is_dir():
                raise ValueError("db_path must identify a file, not a directory")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._target = str(self.path)

    def _open_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._target,
            uri=self._uri,
            timeout=BUSY_TIMEOUT_MS / 1000,
            isolation_level=None,
            check_same_thread=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        return connection

    def connection(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = self._open_connection()
            self._local.connection = connection
        return connection

    def close_thread_connection(self) -> None:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None

    def close(self) -> None:
        self.close_thread_connection()
        if self._anchor is not None:
            self._anchor.close()
            self._anchor = None

    def migrate(self, *, fail_after: int | None = None) -> Any:
        from .migrations import MigrationError, MigrationRunner

        # Service-level helpers may construct one Database per worker. Keep
        # migration discovery/checksum/apply atomic within this process so a
        # concurrent helper cannot race the schema_migrations read. Every call
        # revalidates the applied state and schema; a process-local cache must
        # never turn later database corruption into a false success.
        with _MIGRATION_LOCK:
            runner = MigrationRunner(self, self.migrations_dir)
            for delay in (*MIGRATION_RETRY_DELAYS_SECONDS, None):
                try:
                    return runner.migrate(fail_after=fail_after)
                except (MigrationError, sqlite3.OperationalError) as exc:
                    cause = exc.__cause__
                    message = str(exc).lower()
                    cause_message = str(cause).lower() if cause is not None else ""
                    locked = (
                        "database is locked" in message or "database is locked" in cause_message
                    )
                    if not locked or delay is None:
                        raise
                    time.sleep(delay)
            raise AssertionError("bounded migration retry loop did not return")
